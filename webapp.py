"""
name_on_notes_pitch.py 를 웹앱으로 감싼 것.
악보(PDF/JPG/PNG) 업로드 -> process() 그대로 실행 -> 결과 파일 다운로드.

실행: python3 webapp.py  (기본 0.0.0.0:5000)
homr(순수 파이썬 OMR)만 pip install 되어 있으면 됨 — 자바/JVM 불필요.
"""

import os
import sys
import tempfile
import uuid

from flask import Flask, request, send_file, render_template_string

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
from name_on_notes_pitch import process, default_output_path, NOTE_NAMES  # noqa: E402

app = Flask(__name__)
UPLOAD_DIR = tempfile.mkdtemp(prefix="notepitch_web_")

FORM = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>계이름 자동 삽입</title>
<style>
body{font-family:sans-serif;max-width:480px;margin:40px auto;padding:0 16px}
label{display:block;margin-top:12px}
input,select{width:100%;padding:6px;box-sizing:border-box}
button{margin-top:20px;padding:10px 20px}
</style></head><body>
<h2>악보 계이름 자동 삽입</h2>
<form method="post" action="/process" enctype="multipart/form-data">
  <label>악보 파일 (PDF/JPG/PNG)<input type="file" name="input" required></label>
  <label>계이름 언어
    <select name="lang">{lang_options}</select>
  </label>
  <label>라벨 배치
    <select name="label_style">
      <option value="smart">smart</option>
      <option value="overlay">overlay</option>
      <option value="lane">lane</option>
    </select>
  </label>
  <label><input type="checkbox" name="show_duration" style="width:auto"> 음표 길이 표시</label>
  <button type="submit" id="submitBtn">계이름 삽입</button>
  <p id="status" style="display:none;color:#555">처리 중... 파일에 따라 1~5분 걸릴 수 있음. 페이지를 벗어나지 마세요.</p>
</form>
<script>
document.querySelector("form").addEventListener("submit", function () {
  document.getElementById("submitBtn").disabled = true;
  document.getElementById("submitBtn").textContent = "처리 중...";
  document.getElementById("status").style.display = "block";
});
</script>
</body></html>"""


@app.route("/")
def index():
    lang_options = "".join(f'<option value="{k}">{k}</option>' for k in sorted(NOTE_NAMES))
    return render_template_string(FORM.replace("{lang_options}", lang_options))


@app.route("/process", methods=["POST"])
def do_process():
    f = request.files.get("input")
    if not f or not f.filename:
        return "파일을 선택하세요", 400

    ext = os.path.splitext(f.filename)[1] or ".pdf"
    in_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}{ext}")
    f.save(in_path)
    out_path = default_output_path(in_path)
    print(f"요청 받음: {f.filename} -> 처리 시작")

    try:
        process(
            in_path, out_path,
            lang=request.form.get("lang", "ko"),
            label_style=request.form.get("label_style", "smart"),
            show_duration="show_duration" in request.form,
        )
    except Exception as e:
        return f"처리 실패: {e}", 500

    download_name = os.path.basename(f.filename)
    download_name = os.path.splitext(download_name)[0] + "_note" + ext
    return send_file(out_path, as_attachment=True, download_name=download_name)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
