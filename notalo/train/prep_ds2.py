"""DeepScoresV2(dense) → YOLO 타일 데이터셋.
사용: py -3 train/prep_ds2.py <ds2_dense 폴더> <출력 폴더> [--max-images N]
ds2_dense/ 안에 deepscores_train.json, deepscores_test.json, images/ 가 있어야 함.
페이지(≈1960x2772)를 1024 타일로 잘라 저장 — 통째로 줄이면 음표머리가 5px가 돼서 못 잡음."""
import json
import os
import random
import sys

import cv2
import numpy as np

TILE, STRIDE = 1024, 896  # 128px 겹침
# 0~8: 기존(음높이용). 9~12: 리듬용 추가 클래스 — 지금은 core.py가 픽셀 추측(_flags/_dotted)으로 때우는 것들.
# core.py의 CLASSES와 순서·개수가 반드시 같아야 함(인덱스로 매핑). 한쪽만 고치면 추론이 깨짐.
CLASSES = ["notehead_black", "notehead_half", "notehead_whole", "sharp", "flat", "natural", "clef_g", "clef_f", "clef_c",
           "flag8th", "flag16th", "beam", "augmentation_dot"]
# DS2 카테고리명 부분 문자열 → 우리 클래스. OnLine/InSpace/Small 변형은 전부 같은 클래스로 합침
# ponytail: flag/beam/dot 이름은 DeepScoresV2 공식 카테고리 표기 추정(실제 다운로드 못 해서 미검증).
# 실행 전에 확인: python -c "import json;d=json.load(open('<ds2>/deepscores_train.json'));print(sorted({v['name'] for v in d['categories'].values()}))"
# 이 스크립트가 "미분류 카테고리"로 뭘 건너뛰는지도 한번 찍어보면 이름이 다른지 바로 앎(아래 cls_of 밑 統計 참고).
NAME_MAP = [("noteheadBlack", 0), ("noteheadFull", 0), ("noteheadHalf", 1), ("noteheadWhole", 2), ("noteheadDoubleWhole", 2),
            ("accidentalSharp", 3), ("keySharp", 3), ("accidentalFlat", 4), ("keyFlat", 4),
            ("accidentalNatural", 5), ("keyNatural", 5), ("clefG", 6), ("clefF", 7), ("clefC", 8),
            ("flag8th", 9), ("flag16th", 10), ("flag32nd", 10), ("flag64th", 10),  # 32분 이상은 16분과 합침(둘 다 흔치 않고, core.py에서 dur 계산 시 상한 있음)
            ("beam", 11), ("augmentationDot", 12)]


def cls_of(name):
    for key, c in NAME_MAP:
        if name.startswith(key):
            return c
    return None


def load(json_path):
    d = json.load(open(json_path))
    cats = {str(k): v["name"] for k, v in d["categories"].items()}
    anns = d["annotations"]
    if isinstance(anns, list):  # 형식이 dict/list 둘 다 있어서 방어
        anns = {str(a.get("id", i)): a for i, a in enumerate(anns)}
    imgs = d["images"]
    assert imgs and anns, json_path
    return cats, anns, imgs


def boxes_of(img, cats, anns):
    out = []
    for aid in img["ann_ids"]:
        a = anns[str(aid)]
        c = next((cls_of(cats[str(ci)]) for ci in a["cat_id"] if str(ci) in cats and cls_of(cats[str(ci)]) is not None), None)
        if c is not None:
            x1, y1, x2, y2 = a["a_bbox"]
            out.append((c, x1, y1, x2, y2))
    return out


def tile_page(img_path, boxes, out_img_dir, out_lbl_dir, stem):
    im = img_path if isinstance(img_path, np.ndarray) else cv2.imread(img_path)  # 경로 또는 이미 읽은 배열
    assert im is not None, img_path
    H, W = im.shape[:2]
    if H < TILE or W < TILE:  # 타일보다 작은 페이지는 흰색으로 채워 맞춤
        im = cv2.copyMakeBorder(im, 0, max(TILE - H, 0), 0, max(TILE - W, 0), cv2.BORDER_CONSTANT, value=(255, 255, 255))
        H, W = im.shape[:2]
    n = 0
    ys = sorted(set(list(range(0, H - TILE + 1, STRIDE)) + [H - TILE]))  # 마지막 타일은 끝에 맞춤(가장자리 누락 방지)
    xs = sorted(set(list(range(0, W - TILE + 1, STRIDE)) + [W - TILE]))
    for ty in ys:
        for tx in xs:
            lines = []
            for c, x1, y1, x2, y2 in boxes:
                ix1, iy1, ix2, iy2 = max(x1, tx), max(y1, ty), min(x2, tx + TILE), min(y2, ty + TILE)
                if ix2 - ix1 <= 0 or iy2 - iy1 <= 0:
                    continue
                if (ix2 - ix1) * (iy2 - iy1) < 0.5 * (x2 - x1) * (y2 - y1):
                    continue  # 절반 넘게 잘린 박스는 버림
                cx, cy = ((ix1 + ix2) / 2 - tx) / TILE, ((iy1 + iy2) / 2 - ty) / TILE
                lines.append(f"{c} {cx:.6f} {cy:.6f} {(ix2 - ix1) / TILE:.6f} {(iy2 - iy1) / TILE:.6f}")
            if not lines and random.random() > 0.1:
                continue  # 빈 타일은 10%만 (배경 학습용)
            name = f"{stem}_{tx}_{ty}"
            cv2.imwrite(os.path.join(out_img_dir, name + ".png"), im[ty:ty + TILE, tx:tx + TILE])
            open(os.path.join(out_lbl_dir, name + ".txt"), "w").write("\n".join(lines))
            n += 1
    return n


def main(src, dst, max_images):
    random.seed(0)
    for split, jf in (("train", "deepscores_train.json"), ("val", "deepscores_test.json")):
        cats, anns, imgs = load(os.path.join(src, jf))
        random.shuffle(imgs)
        imgs = imgs[:max_images] if split == "train" else imgs[:max(20, max_images // 8)]
        oi, ol = os.path.join(dst, "images", split), os.path.join(dst, "labels", split)
        os.makedirs(oi, exist_ok=True)
        os.makedirs(ol, exist_ok=True)
        total = 0
        for k, img in enumerate(imgs):
            total += tile_page(os.path.join(src, "images", img["filename"]), boxes_of(img, cats, anns), oi, ol, os.path.splitext(img["filename"])[0])
            if k % 20 == 0:
                print(f"{split} {k + 1}/{len(imgs)} 페이지, 타일 {total}")
        print(f"{split}: 타일 {total}개")
    with open(os.path.join(dst, "data.yaml"), "w") as f:
        f.write(f"path: {os.path.abspath(dst)}\ntrain: images/train\nval: images/val\nnames: {CLASSES}\n")
    print("data.yaml 생성:", os.path.join(dst, "data.yaml"))


if __name__ == "__main__":
    args = sys.argv[1:]
    n = int(args[args.index("--max-images") + 1]) if "--max-images" in args else 300
    main(args[0], args[1], n)
