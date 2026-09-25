"""POST /convert (file, lang, position) → [원본]_plus.[ext]. 서버 저장 없음."""
import collections
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
    preview = None
    for i, p in enumerate(pages):
        notes = core.detect_notes(p)
        if notes_out is not None:
            notes_out.append(notes)
        img = render.overlay(p, core.place_labels(notes, lang, position, mode) + (core.chord_labels(notes) if chords else []))
        img.save(out, append=(ext == ".pdf" and i > 0))  # PIL PDF: append=True면 기존 파일에 페이지 추가
        if i == 0 and ext == ".pdf":
            preview = _preview(img)
        progress(i + 1, len(pages))
    return preview


def _run_job(job_id, src, ext, lang, position, mode, chords):
    try:
        def progress(done, total):
            _jobs[job_id].update(done=done, total=total)  # 진행률 막대용
        out = os.path.join(os.path.dirname(src), "out" + ext)
        notes = _jobs[job_id]["notes"]  # _process가 페이지마다 append → MIDI가 완료 전에도 처리된 페이지만큼 바로 나옴
        preview = _process(src, out, ext, lang, position, mode, progress, notes, chords)
        _jobs[job_id].update(status="done", out=out, preview=preview)
    except Exception:
        shutil.rmtree(_jobs[job_id].get("tmp", ""), ignore_errors=True)
        _jobs[job_id].update(status="error")


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
    _jobs[job_id] = {"status": "processing", "tmp": tmp, "name": name, "created": time.time(), "done": 0, "total": 0, "notes": []}
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
        "title": "Sheet Music Scanner – Photo or PDF to Letters and MIDI, Free Online | Notalo",
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
        "title": "Sheet Music to MIDI Converter – Free, Online, from a Photo or PDF | Notalo",
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


@app.get("/processing")
def processing_page():
    return FileResponse(os.path.join(STATIC_DIR, "processing.html"))


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True))
