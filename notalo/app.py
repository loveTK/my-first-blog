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
from fastapi.responses import FileResponse, Response
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


@app.get("/processing")
def processing_page():
    return FileResponse(os.path.join(STATIC_DIR, "processing.html"))


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True))
