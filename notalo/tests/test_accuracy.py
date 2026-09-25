"""정확도 게이트: 음높이 ≥98%, 누락 ≤1%, 오탐 ≤0.5%.
fixtures/*.{png,jpg,jpeg,pdf} + 같은 이름 .json 정답 필요.
정답 스키마: {"notes":[{"x":int,"y":int,"pitch":"C4"}, ...]}
픽스처: make_song_fixtures.py(깨끗한 LilyPond 렌더, 커밋됨) → degrade_fixtures.py(기울임·사진 변형, 커밋 안 함 — 실행 전에 한 번 돌릴 것)
실행: py -3 tests/test_accuracy.py  (pytest 안 씀 — 의존성 추가 금지)"""
import glob
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import core  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
MATCH_RADIUS = 15  # ponytail: 고정 픽셀 반경. 3단계 이후 staff-space 기준으로 바꿀 수 있음.


def match(gt, det):
    """gt/det: [{"x","y","pitch"}]. 그리디 최근접 매칭, 반경 밖은 매칭 안 함."""
    used = set()
    pairs = []
    for g in gt:
        best, best_d = None, MATCH_RADIUS + 1
        for di, d in enumerate(det):
            if di in used:
                continue
            dist = ((g["x"] - d["x"]) ** 2 + (g["y"] - d["y"]) ** 2) ** 0.5
            if dist < best_d:
                best, best_d = di, dist
        if best is not None:
            used.add(best)
            pairs.append((g, det[best]))
    return pairs, used


def score_one(gt_notes, det_notes):
    pairs, used = match(gt_notes, det_notes)
    return {
        "gt": len(gt_notes), "det": len(det_notes), "matched": len(pairs),
        "correct_pitch": sum(1 for g, d in pairs if g["pitch"] == d["pitch"]),
        "missing": len(gt_notes) - len(pairs),
        "false_pos": len(det_notes) - len(used),
    }


if __name__ == "__main__":
    assert os.path.isdir(FIX), FIX
    imgs = sorted(p for p in glob.glob(os.path.join(FIX, "*")) if p.rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "pdf"))
    assert imgs, f"fixtures 비어있음(정답 이미지 넣어야 함): {FIX}"

    totals = {"gt": 0, "det": 0, "matched": 0, "correct_pitch": 0, "missing": 0, "false_pos": 0}
    for img_path in imgs:
        json_path = os.path.splitext(img_path)[0] + ".json"
        assert os.path.exists(json_path), f"정답 json 없음: {json_path}"
        with open(json_path, encoding="utf-8") as f:
            gt = json.load(f)
        gt_notes, ignore = gt["notes"], gt.get("ignore", [])  # ignore: 정답을 만들 수 없는 구역(x1,y1,x2,y2). 그 안의 검출은 평가 제외

        det_notes = []
        orig = cv2.imread(img_path)
        for page in core.load_pages(img_path):
            # load_pages = deskew(shrink(원본)) → 검출 좌표를 정답(원본 px) 좌표계로 되돌림: 회전 역변환 후 축소 배율
            f = orig.shape[0] / page.shape[0]
            deg = core.skew_angle(cv2.cvtColor(core.shrink(orig), cv2.COLOR_BGR2GRAY))
            pts = np.array([[n["x"], n["y"]] for n in core.detect_notes(page)], dtype=np.float32).reshape(-1, 1, 2)
            if abs(deg) >= 0.1 and len(pts):  # deskew와 같은 문턱값
                h, w = page.shape[:2]
                pts = cv2.transform(pts, cv2.invertAffineTransform(cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1.0)))
            det_notes += [n for n in ({"x": float(x) * f, "y": float(y) * f, "pitch": d["pitch"]} for d, (x, y) in zip(core.detect_notes(page), pts[:, 0]))
                          if not any(x1 <= n["x"] <= x2 and y1 <= n["y"] <= y2 for x1, y1, x2, y2 in ignore)]

        r = score_one(gt_notes, det_notes)
        for k in totals:
            totals[k] += r[k]
        print(f"{os.path.basename(img_path)}: gt={r['gt']} det={r['det']} matched={r['matched']} "
              f"정답음높이={r['correct_pitch']} 누락={r['missing']} 오탐={r['false_pos']}")

    pitch_acc = totals["correct_pitch"] / (totals["matched"] or 1)
    missing_rate = totals["missing"] / (totals["gt"] or 1)
    fp_rate = totals["false_pos"] / (totals["det"] or 1)

    print(f"\n총 {len(imgs)}장 / gt {totals['gt']}개 / det {totals['det']}개")
    print(f"음높이 정확도 {pitch_acc:.1%} (기준 ≥98%)")
    print(f"누락률 {missing_rate:.1%} (기준 ≤1%)")
    print(f"오탐률 {fp_rate:.1%} (기준 ≤0.5%)")

    gate = pitch_acc >= 0.98 and missing_rate <= 0.01 and fp_rate <= 0.005
    print("PASS" if gate else "FAIL")
    sys.exit(0 if gate else 1)
