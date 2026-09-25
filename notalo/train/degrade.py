"""스캔 열화 증강: 깨끗한 DeepScoresV2 타일에 '나쁜 스캔' 효과를 입힌 복사본을 만든다.
사용: py -3 train/degrade.py <데이터셋 폴더> [--ratio 0.5] [--copies 1]
prep_ds2.py가 만든 images/train, labels/train 옆에 <이름>_dgN.png / .txt를 추가한다(원본은 그대로 둔다).
박스 좌표는 바꾸지 않는다 — 기하 변형(회전·왜곡) 없이 화질만 망가뜨림. 기울기는 추론 때 core.deskew가 잡는다.

효과(각각 확률적으로 섞임): 번짐(가우시안·저해상도 재확대), 얼룩 조명(기울기+비네팅), 누런 종이(대비 저하),
잉크 굵기 변화(침식·팽창 = 옅게 인쇄/번진 인쇄), 노이즈(가우시안·점), JPEG 압축, 뒷면 비침."""
import glob
import os
import random
import shutil
import sys

import cv2
import numpy as np


def blur(im, rng):
    if rng.random() < 0.5:
        return cv2.GaussianBlur(im, (0, 0), rng.uniform(0.6, 1.8))
    f = rng.uniform(0.45, 0.8)  # 낮은 dpi로 스캔한 뒤 키운 것처럼
    small = cv2.resize(im, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (im.shape[1], im.shape[0]), interpolation=rng.choice([cv2.INTER_LINEAR, cv2.INTER_CUBIC]))


def lighting(im, rng):
    h, w = im.shape[:2]
    ramp_x = np.linspace(rng.uniform(0.55, 1.0), rng.uniform(0.55, 1.0), w, dtype=np.float32)[None, :]
    ramp_y = np.linspace(rng.uniform(0.6, 1.0), rng.uniform(0.6, 1.0), h, dtype=np.float32)[:, None]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = rng.uniform(0.2, 0.8) * w, rng.uniform(0.2, 0.8) * h
    vign = 1.0 - rng.uniform(0.0, 0.35) * (((xx - cx) / w) ** 2 + ((yy - cy) / h) ** 2) * 2
    return np.clip(im.astype(np.float32) * (ramp_x * ramp_y * vign)[..., None], 0, 255).astype(np.uint8)


def paper(im, rng):
    """누런/회색 종이 + 대비 저하: 흰색이 200~240, 검정이 20~70쯤."""
    lo, hi = rng.uniform(15, 70), rng.uniform(195, 240)
    out = im.astype(np.float32) / 255.0 * (hi - lo) + lo
    tint = np.array([rng.uniform(0.9, 1.0), rng.uniform(0.93, 1.0), 1.0], dtype=np.float32)  # BGR: 파랑을 조금 빼 누렇게
    return np.clip(out * tint[None, None, :], 0, 255).astype(np.uint8)


def ink_weight(im, rng):
    k = np.ones((2, 2), np.uint8) if rng.random() < 0.7 else np.ones((3, 3), np.uint8)
    if rng.random() < 0.5:
        return cv2.dilate(im, k)  # 밝은 값 확장 = 잉크 얇아짐(옅은 인쇄)
    return cv2.erode(im, k)  # 잉크 굵어짐(번진 인쇄)


def noise(im, rng):
    out = im.astype(np.float32) + rng.normal(0, rng.uniform(4, 18), im.shape).astype(np.float32)
    if rng.random() < 0.4:  # 점 노이즈(먼지·토너 얼룩)
        m = rng.random(im.shape[:2]) < rng.uniform(0.0005, 0.004)
        out[m] = rng.uniform(0, 90)
    return np.clip(out, 0, 255).astype(np.uint8)


def jpeg(im, rng):
    ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, int(rng.uniform(25, 70))])
    assert ok
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def bleed(im, rng, pool):
    """뒷면 비침: 다른 타일을 좌우 반전해 옅게 겹침."""
    other = cv2.imread(rng.choice(pool))
    if other is None or other.shape != im.shape:
        return im
    ghost = cv2.GaussianBlur(cv2.flip(other, 1), (0, 0), 1.2).astype(np.float32)
    a = rng.uniform(0.08, 0.22)
    return np.clip(im.astype(np.float32) * (1 - a) + ghost * a, 0, 255).astype(np.uint8)


def degrade(im, rng, pool):
    """효과를 확률적으로 골라 순서대로 적용. 최소 2개는 들어가게."""
    steps = [(0.7, blur), (0.6, lighting), (0.6, paper), (0.5, ink_weight), (0.6, noise), (0.4, jpeg)]
    chosen = [f for p, f in steps if rng.random() < p]
    while len(chosen) < 2:
        chosen.append(rng.choice([f for _, f in steps]))
    if rng.random() < 0.25:
        im = bleed(im, rng, pool)
    for f in chosen:
        im = f(im, rng)
    return im


def main(root, ratio, copies):
    rng = np.random.default_rng(0)
    random.seed(0)
    img_dir, lbl_dir = os.path.join(root, "images", "train"), os.path.join(root, "labels", "train")
    srcs = sorted(p for p in glob.glob(os.path.join(img_dir, "*.png")) if "_dg" not in os.path.basename(p))
    assert srcs, f"타일 없음: {img_dir} (prep_ds2.py 먼저)"
    pick = random.sample(srcs, int(len(srcs) * ratio))
    n = 0
    for k, p in enumerate(pick):
        im = cv2.imread(p)
        stem = os.path.splitext(os.path.basename(p))[0]
        for c in range(copies):
            out = degrade(im, rng, srcs)
            cv2.imwrite(os.path.join(img_dir, f"{stem}_dg{c}.png"), out)
            shutil.copy(os.path.join(lbl_dir, stem + ".txt"), os.path.join(lbl_dir, f"{stem}_dg{c}.txt"))
            n += 1
        if k % 200 == 0:
            print(f"{k + 1}/{len(pick)} 타일, 열화본 {n}")
    print(f"완료: 원본 {len(srcs)} + 열화본 {n} (val은 손대지 않음 — 깨끗한 기준으로 평가)")


if __name__ == "__main__":
    args = sys.argv[1:]
    ratio = float(args[args.index("--ratio") + 1]) if "--ratio" in args else 0.5
    copies = int(args[args.index("--copies") + 1]) if "--copies" in args else 1
    main(args[0], ratio, copies)
