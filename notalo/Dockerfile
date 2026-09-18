# Render 배포 시 Root Directory를 notalo/ 로 지정.
FROM python:3.11-slim

# poppler=pdf2image, fonts-nanum=라벨 폰트(나눔스퀘어), fonts-noto-cjk=폴백, libgl1/libglib2.0=opencv-python(비-headless) 런타임 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils fonts-nanum fonts-noto-cjk libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}
