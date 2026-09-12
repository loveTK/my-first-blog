"""POST /convert (file, lang, position) → [원본]_plus.[ext]. 서버 저장 없음."""
import collections
import os
import shutil
import tempfile
import time

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

import core
import render

app = FastAPI()

MAX_UPLOAD = 20 * 1024 * 1024  # 20MB. 공개 API 무제한 업로드로 인한 리소스 고갈 방지
RATE_LIMIT, RATE_WINDOW = 10, 60  # IP당 60초에 10건. ponytail: 메모리 딕셔너리(재시작하면 리셋, 컨테이너 1대 전제)
_hits = collections.defaultdict(list)


def _check_rate_limit(ip):
    now = time.time()
    hits = [t for t in _hits[ip] if now - t < RATE_WINDOW]
    if len(hits) >= RATE_LIMIT:
        raise HTTPException(429, "너무 많은 요청입니다. 잠시 후 다시 시도하세요.")
    hits.append(now)
    _hits[ip] = hits


@app.post("/convert")
async def convert(request: Request, file: UploadFile, lang: str = Form("ko"), position: str = Form("below")):
    _check_rate_limit(request.client.host)
    ext = os.path.splitext(file.filename)[1].lower()
    assert ext in (".pdf", ".jpg", ".jpeg", ".png"), ext
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "파일이 너무 큽니다(20MB 제한).")
    tmp = tempfile.mkdtemp()
    src, out = os.path.join(tmp, "in" + ext), os.path.join(tmp, "out" + ext)
    with open(src, "wb") as f:
        f.write(data)
    imgs = [render.overlay(p, core.place_labels(core.detect_notes(p), lang, position))
            for p in core.load_pages(src)]
    if ext == ".pdf":
        imgs[0].save(out, save_all=True, append_images=imgs[1:])
    else:
        imgs[0].save(out)
    name = os.path.splitext(file.filename)[0] + "_plus" + ext
    return FileResponse(out, filename=name, background=BackgroundTask(shutil.rmtree, tmp))


app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), html=True))
