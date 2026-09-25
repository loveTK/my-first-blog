"""POST /convert (file, lang, position) → [원본]_plus.[ext]. 서버 저장 없음."""
import collections
import functools
import html
import json
import os
import re
import secrets
import shutil
import tempfile
import threading
import time

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from PIL import Image
from fastapi.responses import FileResponse, HTMLResponse, Response
from urllib.parse import quote
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.middleware.gzip import GZipMiddleware

import auth
import core
import pay
import render

app = FastAPI()
core._session()  # ONNX 모델을 기동 때 미리 로드(첫 변환에서 1~3초 안 기다리게)
app.include_router(auth.router)
app.include_router(pay.router)
auth.rate_limit = lambda request: _check_rate_limit(request.client.host)

MAX_UPLOAD = 20 * 1024 * 1024  # 20MB. 공개 API 무제한 업로드로 인한 리소스 고갈 방지
RATE_LIMIT, RATE_WINDOW = 10, 60  # IP당 60초에 10건. ponytail: 메모리 딕셔너리(재시작하면 리셋, 컨테이너 1대 전제)
_hits = collections.defaultdict(list)
NO_CREDIT = "크레딧을 모두 사용했습니다. 요금제에서 충전해 주세요."



PREVIEW_DIR = os.path.join(tempfile.gettempdir(), "notalo_preview")  # PDF 첫 페이지 미리보기. 1회 조회 후 삭제, 10분 지나면 정리
os.makedirs(PREVIEW_DIR, exist_ok=True)


def _preview(img):
    now = time.time()
    for f in os.listdir(PREVIEW_DIR):
        fp = os.path.join(PREVIEW_DIR, f)
        if now - os.path.getmtime(fp) > 600:
            os.remove(fp)
    tok = secrets.token_urlsafe(16)
    im = img.copy()
    im.thumbnail((1400, 1400 * 4))
    im.save(os.path.join(PREVIEW_DIR, tok + ".jpg"), quality=85)
    return "/preview/" + tok


@app.get("/preview/{tok}")
def preview(tok: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,40}", tok):
        raise HTTPException(404)
    fp = os.path.join(PREVIEW_DIR, tok + ".jpg")
    if not os.path.exists(fp):
        raise HTTPException(404)
    return FileResponse(fp, media_type="image/jpeg", background=BackgroundTask(os.remove, fp))


@app.get("/credits")
def credits(request: Request):
    return auth.credits(request)  # {"left", "user", "verified"}


def _check_rate_limit(ip):
    now = time.time()
    hits = [t for t in _hits[ip] if now - t < RATE_WINDOW]
    if len(hits) >= RATE_LIMIT:
        raise HTTPException(429, "너무 많은 요청입니다. 잠시 후 다시 시도하세요.")
    hits.append(now)
    _hits[ip] = hits


@app.post("/convert")
async def convert(request: Request, file: UploadFile, lang: str = Form("ko"), position: str = Form("below"),
                  mode: str = Form("greedy"), chords: str = Form("")):
    _check_rate_limit(request.client.host)
    if auth.credits(request)["left"] <= 0:
        raise HTTPException(402, NO_CREDIT)
    ext = os.path.splitext(file.filename)[1].lower()
    assert ext in (".pdf", ".jpg", ".jpeg", ".png"), ext
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "파일이 너무 큽니다(20MB 제한).")
    tmp = tempfile.mkdtemp()
    src, out = os.path.join(tmp, "in" + ext), os.path.join(tmp, "out" + ext)
    with open(src, "wb") as f:
        f.write(data)
    preview = _process(src, out, ext, lang, position, mode, chords=bool(chords))
    name = os.path.splitext(file.filename)[0] + "_plus" + ext
    resp = FileResponse(out, filename=name, background=BackgroundTask(shutil.rmtree, tmp))
    if preview:
        resp.headers["X-Preview"] = preview
    if not auth.spend(request, resp):
        raise HTTPException(402, NO_CREDIT)
    return resp


# ---- job 기반 처리 (무료+애드센스 전환: /processing 페이지로 실제 이동, 페이지뷰로 집계) ----
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
JOB_TTL = 1800  # 30분 지난 job은 정리 (결과 안 받아간 것 포함)
_jobs = {}


def _sweep_jobs():
    now = time.time()
    for jid, j in list(_jobs.items()):
        if now - j["created"] > JOB_TTL:
            shutil.rmtree(j.get("tmp", ""), ignore_errors=True)
            del _jobs[jid]


def _process(src, out, ext, lang, position, mode, progress=lambda done, total: None, notes_out=None, chords=True):
    """페이지 한 장씩: 렌더 → 라벨 → 바로 out에 저장(PDF는 append). 결과를 메모리에 모으지 않아 페이지 수와 무관하게 메모리 일정.
    notes_out(list)을 주면 페이지별 검출 음표를 담아줌(MIDI용). 반환: PDF면 첫 페이지 미리보기 URL, 아니면 None."""
    pages = core.load_pages(src)
    preview, failed = None, 0
    for i, p in enumerate(pages):
        try:
            notes = core.detect_notes(p)
        except AssertionError:  # 오선 못 찾은 페이지(표지·가사·빈 페이지)는 라벨 없이 그대로 내보냄. 전부 실패면 진짜 악보 아님
            failed += 1
            assert failed < len(pages), "오선 못 찾음"
            notes = []
        if notes_out is not None:
            notes_out.append(notes)
        img = render.overlay(p, core.place_labels(notes, lang, position, mode) + (core.chord_labels(notes) if chords else []))
        img.save(out, append=(ext == ".pdf" and i > 0))  # PIL PDF: append=True면 기존 파일에 페이지 추가
        if i == 0 and ext == ".pdf":
            preview = _preview(img)
        progress(i + 1, len(pages))
    return preview


def _run_job(job_id, src, ext, lang, position, mode, chords):
    job, err = _jobs[job_id], ""
    try:
        def progress(done, total):
            job.update(done=done, total=total)  # 진행률 막대용
        out = os.path.join(os.path.dirname(src), "out" + ext)
        notes = job["notes"]  # _process가 페이지마다 append → MIDI가 완료 전에도 처리된 페이지만큼 바로 나옴
        preview = _process(src, out, ext, lang, position, mode, progress, notes, chords)
        job.update(status="done", out=out, preview=preview)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"[:80]
        shutil.rmtree(job.get("tmp", ""), ignore_errors=True)
        job.update(status="error")
    try:
        auth.log_conversion({"ts": time.time(), "ok": int(not err), "pages": job["total"], "notes": sum(len(n) for n in job["notes"]),
                             "seconds": round(time.time() - job["created"], 1), "ext": ext, "lang": lang, "position": position, "err": err,
                             "user": job["who"], "country": job["country"]})
    except Exception as e:  # 기록 실패로 변환이 죽으면 안 됨
        print(f"[log] {type(e).__name__}: {e}", flush=True)


@app.post("/jobs")
async def create_job(request: Request, file: UploadFile, lang: str = Form("ko"), position: str = Form("below"),
                      mode: str = Form("greedy"), chords: str = Form("")):
    _check_rate_limit(request.client.host)
    _sweep_jobs()
    if auth.credits(request)["left"] <= 0:
        raise HTTPException(402, NO_CREDIT)
    ext = os.path.splitext(file.filename)[1].lower()
    assert ext in (".pdf", ".jpg", ".jpeg", ".png"), ext
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "파일이 너무 큽니다(20MB 제한).")
    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, "in" + ext)
    with open(src, "wb") as f:
        f.write(data)
    name = os.path.splitext(file.filename)[0] + "_plus" + ext
    job_id = secrets.token_urlsafe(16)
    _jobs[job_id] = {"status": "processing", "tmp": tmp, "name": name, "created": time.time(), "done": 0, "total": 0, "notes": [],
                     "who": auth.who(request), "country": request.headers.get("cf-ipcountry", "")}  # Cloudflare 프록시가 붙여주는 국가 코드
    threading.Thread(target=_run_job, args=(job_id, src, ext, lang, position, mode, bool(chords)), daemon=True).start()
    return {"id": job_id}


@app.get("/jobs/{job_id}/status")
def job_status(job_id: str):
    _sweep_jobs()  # 결과 받은 뒤에도 job이 남으므로 폴링 때마다 오래된 것 정리
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404)
    return {"status": job["status"], "done": job["done"], "total": job["total"]}


@app.get("/jobs/{job_id}/result")
def job_result(job_id: str, request: Request):
    job = _jobs.get(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(404)
    resp = FileResponse(job["out"], filename=job["name"])  # job은 MIDI 내려받기용으로 JOB_TTL(30분)까지 남겨둠 → _sweep_jobs가 정리
    if job.get("preview"):
        resp.headers["X-Preview"] = job["preview"]
    if not auth.spend(request, resp):
        raise HTTPException(402, NO_CREDIT)
    return resp


@app.get("/jobs/{job_id}/midi")
def job_midi(job_id: str, bpm: int = 90):
    """연습용 MIDI: 검출한 음표를 오선별 타임라인에 음길이대로. 쉼표·붙임줄은 없음(화면에 명시).
    라벨 이미지 렌더링이 끝나길 기다리지 않고, 그때까지 처리된 페이지만으로도 바로 내려받을 수 있음(job["notes"]는 페이지마다 채워짐)."""
    job = _jobs.get(job_id)
    if not job or job["status"] == "error" or not job["notes"]:
        raise HTTPException(404)
    data = core.to_midi(job["notes"], max(40, min(240, bpm)))
    name = os.path.splitext(job["name"])[0] + ".mid"
    return Response(data, media_type="audio/midi", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


# ---------- SEO 랜딩 변형: index.html을 그대로 쓰되 title/H1/설명만 바꿈 (도구·FAQ는 공유, HTML 복사 없음) ----------
# 검색어(Keyword Planner, 미국): sheet music scanner / scanner app / scanner online free 각 5K, sheet music to midi / pdf sheet to midi 각 5K — 전부 경쟁 낮음.
PAGES = {
    "/sheet-music-scanner": {
        "title": "Sheet Music Scanner – Photo/PDF to Letters & MIDI | Notalo",
        "desc": "Free online sheet music scanner. Snap a photo or upload a PDF; Notalo reads the notes and returns the same sheet music with letters under every note, chord symbols, and a MIDI file. No app to install.",
        "h1": "Sheet music scanner: photo or PDF in, letters and MIDI out.",
        "sub": "Scan sheet music with your phone camera or upload a PDF. Notalo reads every note and gives you the sheet back with letters, chord symbols and a MIDI file — online, free, nothing to install.",
        "extra": """<section class="pad" id="scanner-info">
  <h2 class="sec-title">What this scanner reads</h2>
  <p class="sec-sub">Printed sheet music: PDFs exported from notation software, sharp scans, and straight-on phone photos of a printed page. It finds the staff lines, clefs, key signature and every notehead, then works out each pitch and note length.</p>
  <div class="how-grid">
    <div class="how-step"><span class="how-num">1</span><h3>Scan or upload</h3><p>Take a photo of the page or upload a PDF (up to 20MB, multi-page OK). Nothing to install.</p></div>
    <div class="how-step"><span class="how-num">2</span><h3>Notes are recognized</h3><p>Noteheads, clefs, accidentals and key signatures are detected on the image itself — no MusicXML needed.</p></div>
    <div class="how-step"><span class="how-num">3</span><h3>Download three things</h3><p>Your sheet music with letters (or Do Re Mi) under each note, chord symbols above each bar, and a MIDI file to hear what was read.</p></div>
  </div>
  <h2 class="sec-title">Notalo vs. typical sheet music scanner apps</h2>
  <div class="cmp-wrap"><table class="cmp-table">
    <thead><tr><th></th><th>Notalo</th><th>Typical scanner apps</th></tr></thead>
    <tbody>
      <tr><td>Install</td><td>None — runs in the browser</td><td>Phone app, often paid or subscription</td></tr>
      <tr><td>Output</td><td>Sheet music with letters + chords + MIDI</td><td>MusicXML or playback only; no letters on the page</td></tr>
      <tr><td>Price</td><td>Free, ad-supported</td><td>Free tier limited by page count</td></tr>
      <tr><td>Best for</td><td>Beginners who want to play from the page today</td><td>Musicians editing the score in notation software</td></tr>
      <tr><td>Weak spot</td><td>Rests, ties and tuplets are not read; handwritten or blurry pages miss notes</td><td>Varies</td></tr>
    </tbody>
  </table></div>
  <p class="cmp-cta"><a class="btn-p" href="#tool">Scan your sheet music →</a></p>
</section>""",
    },
    "/sheet-music-to-midi": {
        "title": "Sheet Music to MIDI Converter – Free, Online | Notalo",
        "desc": "Convert sheet music to MIDI online for free. Upload a photo or PDF; Notalo reads the notes and gives you a MIDI file with pitches, note lengths and your tempo — plus the sheet music with letters under every note.",
        "h1": "Sheet music to MIDI: upload a photo or PDF, download a MIDI file.",
        "sub": "Notalo reads the notes on your sheet music and turns them into a MIDI file with the right pitches and note lengths, at the tempo you choose. You also get the sheet back with letters under every note and chord symbols.",
        "extra": """<section class="pad" id="midi-info">
  <h2 class="sec-title">How the conversion works</h2>
  <div class="how-grid">
    <div class="how-step"><span class="how-num">1</span><h3>Pitches</h3><p>Each notehead is placed on its staff; the clef, key signature and accidentals in the bar decide the pitch. Right hand and left hand go to separate MIDI tracks.</p></div>
    <div class="how-step"><span class="how-num">2</span><h3>Note lengths</h3><p>Whole, half, quarter, eighth and sixteenth notes are told apart by notehead type, flags and beams; dots make a note half again as long.</p></div>
    <div class="how-step"><span class="how-num">3</span><h3>Tempo</h3><p>Pick any BPM from 40 to 240 on the result page; the file is regenerated at that speed.</p></div>
  </div>
  <h2 class="sec-title">What the MIDI is good for — and its limits</h2>
  <p class="sec-sub">Use it to hear a piece before you can play it, to practice along at a slow tempo, or to import into notation software or a DAW as a starting point. Rests, ties and tuplets are not detected yet, so the timing can drift in busy passages — check the pitches and the feel, don't treat it as a finished arrangement. Clean printed scores convert best; handwritten or blurry pages miss notes.</p>
  <p class="cmp-cta"><a class="btn-p" href="#tool">Convert sheet music to MIDI →</a></p>
</section>""",
    },
}
_INDEX = open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8").read()


def _variant(path):
    v, h = PAGES[path], _INDEX
    url = "https://notalo.xyz" + path
    h = h.replace('<html lang="en">', '<html lang="en" data-page="1">', 1)  # JS가 title/description을 i18n으로 덮어쓰지 않게
    h = re.sub(r"<title>.*?</title>", f"<title>{v['title']}</title>", h, count=1)
    for a in ('name="description"', 'property="og:description"', 'name="twitter:description"'):
        h = re.sub(rf'(<meta {a} content=")[^"]*(")', lambda m: m.group(1) + v["desc"] + m.group(2), h)
    for a in ('property="og:title"', 'name="twitter:title"'):
        h = re.sub(rf'(<meta {a} content=")[^"]*(")', lambda m: m.group(1) + v["title"] + m.group(2), h)
    h = h.replace('<link rel="canonical" href="https://notalo.xyz/">', f'<link rel="canonical" href="{url}">')
    h = h.replace('<meta property="og:url" content="https://notalo.xyz/">', f'<meta property="og:url" content="{url}">')
    h = re.sub(r'<link rel="alternate" hreflang="[^"]*" href="[^"]*">\n', "", h)  # 영어 전용 페이지
    h = re.sub(r'<h1 data-i18n="hero.h1">.*?</h1>', f"<h1>{v['h1']}</h1>", h, count=1)  # data-i18n 제거 → 언어 바꿔도 안 덮임
    h = re.sub(r'<p class="lead" data-i18n="hero.sub">.*?</p>', f'<p class="lead">{v["sub"]}</p>', h, count=1)
    h = h.replace('<section class="pad" id="demo">', v["extra"] + '\n\n<section class="pad" id="demo">', 1)
    assert v["h1"] in h and v["extra"] in h and url in h
    return h


@app.get("/sheet-music-scanner")
def page_scanner():
    return HTMLResponse(_variant("/sheet-music-scanner"))


@app.get("/sheet-music-to-midi")
def page_midi():
    return HTMLResponse(_variant("/sheet-music-to-midi"))


GUIDES = {"/how-to-read-sheet-music": "guide-read.html", "/treble-clef-notes": "guide-treble.html", "/bass-clef-notes": "guide-bass.html"}


@app.get("/how-to-read-sheet-music")
@app.get("/treble-clef-notes")
@app.get("/bass-clef-notes")
def guide_page(request: Request):
    return FileResponse(os.path.join(STATIC_DIR, GUIDES[request.url.path]))


# ---------- 곡 페이지: songs.py 메타 + static/songs/<slug>.{png,mid,json} (tools/build_songs.py 산출물) → static/song.html 템플릿 ----------
from songs import SONGS  # noqa: E402

_SONG_TPL = open(os.path.join(STATIC_DIR, "song.html"), encoding="utf-8").read()


def _song_page(slug):
    m, d = SONGS[slug], json.load(open(os.path.join(STATIC_DIR, "songs", slug + ".json"), encoding="utf-8"))
    url = f"https://notalo.xyz/letter-notes/{slug}"
    year = m.get("year_text", str(m["year"]))
    ld = [{"@context": "https://schema.org", "@type": "MusicComposition", "name": m["title"], "composer": {"@type": "Person", "name": m["composer"]},
           "musicalKey": m["key"], "inLanguage": "en", "url": url, "image": f"https://notalo.xyz/songs/{slug}.png", "license": "https://creativecommons.org/publicdomain/mark/1.0/"},
          {"@context": "https://schema.org", "@type": "Article", "headline": f"{m['title']} piano notes with letters", "url": url, "inLanguage": "en", "datePublished": "2026-09-25",
           "author": {"@type": "Organization", "name": "Notalo"}, "publisher": {"@type": "Organization", "name": "Notalo", "url": "https://notalo.xyz/"}}]
    related = " · ".join(f'<a href="/letter-notes/{k}">{v["title"]}</a>' for k, v in SONGS.items() if k != slug)
    rep = {"TITLE": m["title"], "SLUG": slug, "URL": url, "KEY": m["key"], "TIME": m["time"], "BPM": str(m["bpm"]), "COMPOSER": m["composer"], "YEAR": year,
           "INTRO": m["intro"], "W": str(d["w"]), "H": str(d["h"]), "LD": json.dumps(ld, ensure_ascii=False).replace("</", "<\\/"),
           "BARS": "\n  ".join(f"<tr><td>{b['n']}</td><td>{b['chord']}</td><td>{b['rh']}</td></tr>" for b in d["bars"]),
           "TIPS": "\n  ".join(f"<li>{t}</li>" for t in m["tips"]), "RELATED": related}
    h = _SONG_TPL
    for k, v in rep.items():
        h = h.replace("{{" + k + "}}", v)
    assert "{{" not in h, slug
    return h


@app.get("/letter-notes/{slug}")
def song_page(slug: str):
    if slug not in SONGS or not os.path.exists(os.path.join(STATIC_DIR, "songs", slug + ".json")):
        raise HTTPException(404)
    return HTMLResponse(_song_page(slug))


def _hub(title, desc, url, intro, items):
    lis = "".join(f'<li><a href="/letter-notes/{k}"><strong>{v["title"]}</strong></a> — {v["composer"]}, {v["key"]}, {v["time"]}</li>' for k, v in items)
    ld = json.dumps({"@context": "https://schema.org", "@type": "CollectionPage", "name": title, "url": url, "inLanguage": "en"}).replace("</", "<\\/")
    body = f'<p class="toc"><a href="/">Notalo</a> › {title}</p><h1>{title}</h1><p class="lead">{intro}</p><ul>{lis}</ul>' \
           '<div class="cta"><p><strong>Your own sheet music?</strong> Upload a photo or PDF and get it back with letters under every note, chords and a MIDI file.</p><a class="btn-p" href="/#tool">Add letters to my sheet music</a></div>'
    h = _SONG_TPL.split("<main class=\"article\">")[0] + '<main class="article">' + body + "</main>" + _SONG_TPL.split("</main>")[1]
    h = re.sub(r"<title>.*?</title>", f"<title>{title} | Notalo</title>", h, count=1)
    h = re.sub(r'(<meta name="description" content=")[^"]*(")', lambda mm: mm.group(1) + desc + mm.group(2), h)
    h = re.sub(r'<meta property="og:[^>]*>', "", h)
    h = re.sub(r'<link rel="canonical" href="[^"]*">', f'<link rel="canonical" href="{url}"><meta property="og:url" content="{url}"><meta property="og:title" content="{title}">'
               f'<meta property="og:image" content="https://notalo.xyz/songs/{items[0][0]}.png">', h)
    h = re.sub(r'<script type="application/ld\+json">.*?</script>', f'<script type="application/ld+json">{ld}</script>', h, count=1)
    return h


@app.get("/letter-notes")
def songs_hub():
    return HTMLResponse(_hub("Easy piano songs with letters", "Free easy piano sheet music with the letter written under every note, chord symbols and a MIDI file for each song. Public-domain melodies arranged by Notalo.",
                             "https://notalo.xyz/letter-notes", "Each song below is a public-domain melody arranged for easy piano, with the letter under every note (right hand red, left hand blue), chord symbols, a bar-by-bar letter list, and a MIDI file. Free to print.",
                             [(k, v) for k, v in SONGS.items() if os.path.exists(os.path.join(STATIC_DIR, "songs", k + ".json"))]))


@app.get("/christmas-piano-songs-with-letters")
def christmas_hub():
    return HTMLResponse(_hub("Christmas piano songs with letters", "Easy Christmas piano sheet music with letters under every note: Jingle Bells, Silent Night, Deck the Halls, We Wish You a Merry Christmas. Chords and MIDI included. Free.",
                             "https://notalo.xyz/christmas-piano-songs-with-letters", "Traditional Christmas carols for easy piano, each with the letter under every note, chord symbols and a MIDI file to hear it. All public domain, no lyrics, free to print for lessons and family singalongs.",
                             [(k, v) for k, v in SONGS.items() if v.get("christmas") and os.path.exists(os.path.join(STATIC_DIR, "songs", k + ".json"))]))


@app.get("/processing")
def processing_page():
    return FileResponse(os.path.join(STATIC_DIR, "processing.html"))


# ---------- 홈 ?lang=xx: hreflang이 가리키는 주소를 서버에서도 그 언어로 ----------
# JS만 title/lang을 바꾸면 canonical·og:url이 전부 /를 가리켜 구글이 hreflang을 무시하고 영어 하나로 합침 → 7개 언어가 색인 안 됨.
_I18N_DIR = os.path.join(STATIC_DIR, "i18n")
_I18N = {f[:-5]: json.load(open(os.path.join(_I18N_DIR, f), encoding="utf-8")) for f in os.listdir(_I18N_DIR) if f.endswith(".json")}


@functools.lru_cache(maxsize=None)
def _localized(code):
    t, h = _I18N[code], _INDEX
    if code == "en":
        return h
    esc = lambda s: html.escape(s, quote=True) if "<a " not in s else s  # data-i18n 본문은 JS와 같은 규칙(링크 있으면 HTML)
    url = f"https://notalo.xyz/?lang={code}"
    h = h.replace('<html lang="en">', f'<html lang="{code}">', 1)
    h = re.sub(r"<title>.*?</title>", f"<title>{esc(t['meta.title'])}</title>", h, count=1)
    for a in ('name="description"', 'property="og:description"', 'name="twitter:description"'):
        h = re.sub(rf'(<meta {a} content=")[^"]*(")', lambda m: m.group(1) + esc(t["meta.desc"]) + m.group(2), h)
    for a in ('property="og:title"', 'name="twitter:title"'):
        h = re.sub(rf'(<meta {a} content=")[^"]*(")', lambda m: m.group(1) + esc(t["meta.title"]) + m.group(2), h)
    h = h.replace('<link rel="canonical" href="https://notalo.xyz/">', f'<link rel="canonical" href="{url}">')
    h = h.replace('<meta property="og:url" content="https://notalo.xyz/">', f'<meta property="og:url" content="{url}">')
    h = re.sub(r'(<h1 data-i18n="hero.h1">).*?(</h1>)', lambda m: m.group(1) + esc(t["hero.h1"]) + m.group(2), h, count=1)
    h = re.sub(r'(<p class="lead" data-i18n="hero.sub">).*?(</p>)', lambda m: m.group(1) + esc(t["hero.sub"]) + m.group(2), h, count=1)
    if os.path.exists(os.path.join(STATIC_DIR, "hero", f"sample_{code}.webp")):
        h = h.replace("/hero/sample_en.webp", f"/hero/sample_{code}.webp")  # og:image + 히어로 이미지
    assert url in h
    return h


@app.get("/admin/stats")
def admin_stats(key: str, days: int = 7, exclude: str = ""):
    """변환 기록 JSON. key=NOTALO_SECRET, exclude=내 이메일(LIKE 패턴) → 실제 사용자만."""
    if not secrets.compare_digest(key.encode(), auth.SECRET):
        raise HTTPException(404)
    return auth.conversions(days, exclude)


@app.get("/")
def home(lang: str = ""):
    return HTMLResponse(_localized(lang if lang in _I18N else "en"))


@app.middleware("http")
async def cache_headers(request: Request, call_next):
    """HTML은 매번 재검증(옛 CSS가 새 HTML에 섞이던 문제 재발 방지), ?v= 붙은 정적 파일은 1년 불변, 나머지 정적 파일은 하루."""
    resp = await call_next(request)
    if resp.headers.get("content-type", "").startswith("text/html"):
        resp.headers["Cache-Control"] = "no-cache"
    elif request.url.path.rsplit(".", 1)[-1] in ("css", "js", "png", "jpg", "webp", "woff2", "woff", "ttf", "json", "ico", "mid", "svg", "xml", "txt"):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable" if "v=" in request.url.query else "public, max-age=86400"
    return resp


app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True))
