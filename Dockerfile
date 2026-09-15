# homr(순수 파이썬 OMR, PyTorch/ONNX Runtime)만 있으면 되므로 Audiveris 시절과
# 달리 JVM 빌드가 필요 없다 — 이미지 한 장으로 끝.

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# homr 모델(세그멘테이션+트랜스포머, 약 120MB)을 빌드 시점에 미리 받아둔다.
# 안 받아두면 배포 후 첫 요청 때 사용자가 그 다운로드를 기다려야 한다.
RUN python3 -c "from homr.main import download_weights; download_weights(False, False, False)"

COPY . .

# gunicorn 기본 워커 타임아웃(30초)은 OMR 처리 시간보다 짧을 수 있어서 늘려둔다.
CMD gunicorn -b 0.0.0.0:${PORT:-8080} --timeout 600 --workers 1 webapp:app
