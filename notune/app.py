"""POST /convert (file, lang, position) → [원본]_plus.[ext]. 서버 저장 없음."""
import os
import shutil
import tempfile

from fastapi import FastAPI, Form, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

import core
import render

app = FastAPI()


@app.post("/convert")
async def convert(file: UploadFile, lang: str = Form("ko"), position: str = Form("below")):
    ext = os.path.splitext(file.filename)[1].lower()
    assert ext in (".pdf", ".jpg", ".jpeg", ".png"), ext
    tmp = tempfile.mkdtemp()
    src, out = os.path.join(tmp, "in" + ext), os.path.join(tmp, "out" + ext)
    with open(src, "wb") as f:
        f.write(await file.read())
    imgs = [render.overlay(p, core.place_labels(core.detect_notes(p), lang, position))
            for p in core.load_pages(src)]
    if ext == ".pdf":
        imgs[0].save(out, save_all=True, append_images=imgs[1:])
    else:
        imgs[0].save(out)
    name = os.path.splitext(file.filename)[0] + "_plus" + ext
    return FileResponse(out, filename=name, background=BackgroundTask(shutil.rmtree, tmp))


app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), html=True))
