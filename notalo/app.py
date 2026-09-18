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
from fastapi.responses import FileResponse
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
                  mode: str = Form("greedy")):
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
    imgs = [render.overlay(p, core.place_labels(core.detect_notes(p), lang, position, mode))
            for p in core.load_pages(src)]
    if ext == ".pdf":
        imgs[0].save(out, save_all=True, append_images=imgs[1:])
    else:
        imgs[0].save(out)
    name = os.path.splitext(file.filename)[0] + "_plus" + ext
    resp = FileResponse(out, filename=name, background=BackgroundTask(shutil.rmtree, tmp))
    if ext == ".pdf":
        resp.headers["X-Preview"] = _preview(imgs[0])
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


def _run_job(job_id, src, ext, lang, position, mode):
    try:
        pages = core.load_pages(src)
        _jobs[job_id]["total"] = len(pages)
        imgs = []
        for p in pages:
            imgs.append(render.overlay(p, core.place_labels(core.detect_notes(p), lang, position, mode)))
            _jobs[job_id]["done"] = len(imgs)  # 진행률 막대용
        tmp = os.path.dirname(src)
        out = os.path.join(tmp, "out" + ext)
        if ext == ".pdf":
            imgs[0].save(out, save_all=True, append_images=imgs[1:])
        else:
            imgs[0].save(out)
        preview = _preview(imgs[0]) if ext == ".pdf" else None
        _jobs[job_id].update(status="done", out=out, preview=preview)
    except Exception:
        shutil.rmtree(_jobs[job_id].get("tmp", ""), ignore_errors=True)
        _jobs[job_id].update(status="error")


@app.post("/jobs")
async def create_job(request: Request, file: UploadFile, lang: str = Form("ko"), position: str = Form("below"),
                      mode: str = Form("greedy")):
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
    _jobs[job_id] = {"status": "processing", "tmp": tmp, "name": name, "created": time.time(), "done": 0, "total": 0}
    threading.Thread(target=_run_job, args=(job_id, src, ext, lang, position, mode), daemon=True).start()
    return {"id": job_id}


@app.get("/jobs/{job_id}/status")
def job_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404)
    return {"status": job["status"], "done": job["done"], "total": job["total"]}


@app.get("/jobs/{job_id}/result")
def job_result(job_id: str, request: Request):
    job = _jobs.get(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(404)
    resp = FileResponse(job["out"], filename=job["name"], background=BackgroundTask(shutil.rmtree, job["tmp"], ignore_errors=True))
    if job.get("preview"):
        resp.headers["X-Preview"] = job["preview"]
    if not auth.spend(request, resp):
        raise HTTPException(402, NO_CREDIT)
    del _jobs[job_id]
    return resp


@app.get("/processing")
def processing_page():
    return FileResponse(os.path.join(STATIC_DIR, "processing.html"))


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True))
