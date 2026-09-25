"""깨끗한 픽스처(<slug>.png + .json)로 열화 변형 생성 — 정답 좌표는 같은 변환으로 옮김.
  -skew.png : 1.5° 기울임(스캔 비뚤어짐, deskew 경로)
  -photo.jpg: 축소 0.6배 + 흐림 + 조명 기울기 + 노이즈 + JPEG q60(폰 사진)
실행: py -3 tests/degrade_fixtures.py   (기존 변형은 덮어씀)"""
import glob
import json
import os

import cv2
import numpy as np

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SKEW_DEG, PHOTO_SCALE = 1.5, 0.6


def save(name, img, notes):
    cv2.imwrite(os.path.join(FIX, name), img, [cv2.IMWRITE_JPEG_QUALITY, 60] if name.endswith(".jpg") else [])
    json.dump({"notes": notes}, open(os.path.join(FIX, os.path.splitext(name)[0] + ".json"), "w", encoding="utf-8"))


for png in sorted(glob.glob(os.path.join(FIX, "*.png"))):
    slug = os.path.splitext(os.path.basename(png))[0]
    if slug.endswith(("-skew", "-photo")):
        continue
    img = cv2.imread(png)
    notes = json.load(open(os.path.splitext(png)[0] + ".json", encoding="utf-8"))["notes"]
    h, w = img.shape[:2]
    pts = np.array([[n["x"], n["y"]] for n in notes], dtype=np.float32)

    m = cv2.getRotationMatrix2D((w / 2, h / 2), SKEW_DEG, 1.0)
    rot = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))
    p = cv2.transform(pts[None], m)[0]
    save(slug + "-skew.png", rot, [{**n, "x": int(round(x)), "y": int(round(y))} for n, (x, y) in zip(notes, p)])

    rng = np.random.default_rng(0)
    small = cv2.resize(img, None, fx=PHOTO_SCALE, fy=PHOTO_SCALE, interpolation=cv2.INTER_AREA).astype(np.float32)
    sh, sw = small.shape[:2]
    light = np.linspace(1.0, 0.6, sw, dtype=np.float32)[None, :, None] * np.linspace(0.85, 1.0, sh, dtype=np.float32)[:, None, None]
    photo = cv2.GaussianBlur(small, (0, 0), 1.0) * light + rng.normal(0, 6, small.shape).astype(np.float32)
    save(slug + "-photo.jpg", np.clip(photo, 0, 255).astype(np.uint8),
         [{**n, "x": int(round(n["x"] * PHOTO_SCALE)), "y": int(round(n["y"] * PHOTO_SCALE))} for n in notes])
    print(slug, "→ -skew.png, -photo.jpg")
