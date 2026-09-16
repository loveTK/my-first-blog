"""라벨 없는 실제 스캔(AudioLabs v2, IMSLP 등) → 현재 모델의 검출을 라벨로 쓴 타일(의사라벨).
사용: py -3 train/pseudo_label.py <이미지 폴더> <출력 폴더> [--conf 0.6]
AudioLabs v2는 마디 박스만 있고 음표 라벨이 없어서 이 방법뿐. <출력>/preview/*.jpg 를 사람이 보고
틀린 페이지는 images/train·labels/train 에서 지운다. ponytail: 모델이 놓친 음표는 '배경'으로 학습됨 → 검토 없이 쓰면 놓침이 굳는다."""
import glob
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import core  # noqa: E402
from prep_ds2 import tile_page  # noqa: E402


def main(src, dst, conf):
    oi, ol, pv = (os.path.join(dst, *p) for p in (("images", "train"), ("labels", "train"), ("preview",)))
    for d in (oi, ol, pv):
        os.makedirs(d, exist_ok=True)
    total = 0
    for path in sorted(p for p in glob.glob(os.path.join(src, "*")) if p.rsplit(".", 1)[-1].lower() in ("png", "jpg", "jpeg", "pdf")):
        for pi, page in enumerate(core.load_pages(path)):
            gray = cv2.cvtColor(page, cv2.COLOR_RGB2GRAY)
            try:
                ss = float(np.median([s["space"] for s in core.detect_staves(core.binarize(gray))]))
            except AssertionError:
                print("오선 못 찾음, 건너뜀:", path)
                continue
            dets = [d for d in core.detect_symbols(cv2.cvtColor(core.flatten(gray), cv2.COLOR_GRAY2RGB), ss) if d["conf"] >= conf]
            k = core.TRAIN_SS / ss
            im = cv2.resize(cv2.cvtColor(page, cv2.COLOR_RGB2BGR), None, fx=k, fy=k, interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_LINEAR)
            boxes = [(core.CLASSES.index(d["cls"]), (d["x"] - d["w"] / 2) * k, (d["y"] - d["h"] / 2) * k, (d["x"] + d["w"] / 2) * k, (d["y"] + d["h"] / 2) * k) for d in dets]
            stem = f"pl_{os.path.splitext(os.path.basename(path))[0]}_{pi}"
            total += tile_page(im, boxes, oi, ol, stem)
            for _, x1, y1, x2, y2 in boxes:
                cv2.rectangle(im, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 1)
            cv2.imwrite(os.path.join(pv, stem + ".jpg"), im, [cv2.IMWRITE_JPEG_QUALITY, 80])
            print(f"{stem}: ss={ss:.1f} 검출 {len(boxes)} 누적 타일 {total}")
    assert total, "타일 0개"
    print(f"완료: 타일 {total}. {pv} 검토 후 학습")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], float(a[a.index("--conf") + 1]) if "--conf" in a else 0.6)
