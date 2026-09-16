"""MUSCIMA++(손글씨, 실제 종이 스캔) → YOLO 타일. 사용: py -3 train/prep_muscima.py <MUSCIMA-pp 폴더> <출력 폴더>
폴더 안 어디든 *.xml(MuNG v1 CropObject / v2 Node)과 같은 이름의 .png 를 찾는다.
페이지 staff space를 core.detect_staves로 재서 16.5px(DS2와 동일)로 맞춘 뒤 prep_ds2.tile_page로 자른다.
출력 폴더를 DS2 타일 폴더로 주면 images/train, labels/train에 섞인다(val은 DS2 원본 유지)."""
import glob
import os
import sys
import xml.etree.ElementTree as ET

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import core  # noqa: E402
from prep_ds2 import tile_page  # noqa: E402

NAME_MAP = [("noteheadfull", 0), ("notehead-full", 0), ("noteheadblack", 0), ("noteheadhalf", 1), ("notehead-empty", 1), ("noteheadwhole", 2),
            ("sharp", 3), ("flat", 4), ("natural", 5), ("g-clef", 6), ("gclef", 6), ("f-clef", 7), ("fclef", 7), ("c-clef", 8), ("cclef", 8)]


def cls_of(name):
    n = name.lower()
    if "double" in n or "key" in n and "signature" in n:  # 겹올림표·조표 묶음 노드는 클래스 없음
        return None
    return next((c for k, c in NAME_MAP if k in n), None)


def boxes_of(xml_path):
    out = []
    for node in ET.parse(xml_path).getroot().iter():
        if node.tag not in ("Node", "CropObject"):
            continue
        c = cls_of(node.findtext("ClassName") or node.findtext("MLClassName") or "")
        if c is None:
            continue
        t, l, w, h = (int(node.findtext(k)) for k in ("Top", "Left", "Width", "Height"))
        out.append((c, l, t, l + w, t + h))
    return out


def main(src, dst):
    oi, ol = os.path.join(dst, "images", "train"), os.path.join(dst, "labels", "train")
    os.makedirs(oi, exist_ok=True)
    os.makedirs(ol, exist_ok=True)
    pngs = {os.path.splitext(os.path.basename(p))[0]: p for p in glob.glob(os.path.join(src, "**", "*.png"), recursive=True)}
    total = 0
    for xml in sorted(glob.glob(os.path.join(src, "**", "*.xml"), recursive=True)):
        stem = os.path.splitext(os.path.basename(xml))[0]
        if stem not in pngs:
            continue
        im = cv2.imread(pngs[stem])
        if im.mean() < 128:  # 흰 잉크/검은 배경 버전이면 뒤집음
            im = 255 - im
        try:
            ss = float(np.median([s["space"] for s in core.detect_staves(core.binarize(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)))]))
        except AssertionError:
            print("오선 못 찾음, 건너뜀:", stem)
            continue
        k = core.TRAIN_SS / ss
        im = cv2.resize(im, None, fx=k, fy=k, interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_LINEAR)
        boxes = [(c, x1 * k, y1 * k, x2 * k, y2 * k) for c, x1, y1, x2, y2 in boxes_of(xml)]
        total += tile_page(im, boxes, oi, ol, "mpp_" + stem)
        print(f"{stem}: ss={ss:.1f} 박스 {len(boxes)} 누적 타일 {total}")
    assert total, f"타일 0개: {src} 안에 xml+png 쌍이 있는지 확인"
    print("완료: 타일", total)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
