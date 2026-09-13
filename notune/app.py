"""POST /convert (file, lang, position) → [원본]_plus.[ext]. 서버 저장 없음."""
import collections
import hashlib
import hmac
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

FREE = 2  # 쿠키 기반 무료 횟수. ponytail: 쿠키 지우면 리셋됨(스펙 허용). 결제(PayPal)는 별도 신호 후
SECRET = os.environ.get("NOTUNE_SECRET", "dev-secret").encode()  # 배포에선 환경변수로. 없으면 서명 위조 가능


def _sign(n):
    return hmac.new(SECRET, str(n).encode(), hashlib.sha256).hexdigest()[:16]


def _used(request):
    n, _, sig = request.cookies.get("nt_used", "").partition(".")
    return int(n) if n.isdigit() and hmac.compare_digest(sig, _sign(n)) else 0


@app.get("/credits")
def credits(request: Request):
    return {"left": max(FREE - _used(request), 0)}


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
    used = _used(request)
    if used >= FREE:
        raise HTTPException(402, f"무료 {FREE}회를 모두 사용했습니다. 결제 기능은 준비 중입니다.")
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
    resp.set_cookie("nt_used", f"{used + 1}.{_sign(used + 1)}", max_age=365 * 24 * 3600, httponly=True, samesite="lax")
    return resp


app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), html=True))
