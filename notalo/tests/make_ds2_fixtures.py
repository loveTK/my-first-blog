"""DeepScoresV2 test 페이지에서 정확도 픽스처 생성 (정답은 주석 데이터로만 계산, 검출기 안 씀).
정답 음높이 = 음자리표(주석) + rel_position(주석) + 조표(keySharp/keyFlat 주석) + 임시표(accidental* 주석, 마디 내 유지).
마디선은 DS2에 주석이 없어서 이미지에서 직접 찾음(오선 1~5선 사이 전부 잉크인 세로줄, 음표 bbox 제외).
한계: 8va/옥타브 음자리표·타악기 페이지 제외, 붙임줄로 이어진 임시표는 마디 넘어가면 유지 안 함(파이프라인과 동일 규칙).
실행: py -3 tests/make_ds2_fixtures.py <ds2_dense 폴더> [페이지수=20]"""
import bisect
import json
import os
import re
import shutil
import sys

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import core  # noqa: E402  오선 "선 위치"만 빌려 씀(주석 staff bbox는 선과 안 맞는 경우가 있음). 음표·기호 검출은 안 씀

DS2 = sys.argv[1]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 20
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
LETTERS = "CDEFGAB"
MID = {"clefG": 4 * 7 + 6, "clefF": 3 * 7 + 1, "clefCAlto": 4 * 7 + 0, "clefCTenor": 3 * 7 + 5}  # 가운데 줄의 절대 온음계 인덱스
SHARPS, FLATS = "FCGDAEB", "BEADGCF"
BAD = {"clef8", "clef15", "clefUnpitchedPercussion", "ottavaBracket"}

d = json.load(open(os.path.join(DS2, "deepscores_test.json")))
cats, anns = d["categories"], d["annotations"]
name_of = lambda a: cats[a["cat_id"][0]]["name"]


def barlines(img_path, staff, heads):
    x1, y1, x2, y2 = staff
    ss = (y2 - y1) / 4
    g = np.array(Image.open(img_path).convert("L"))
    band = g[int(y1) + 2:int(y2) - 1, :] < 128  # 1선~5선 사이 안쪽만
    col = band.all(axis=0)
    for hx1, hy1, hx2, hy2 in heads:  # 음표 bbox 구간은 제외
        col[int(hx1) - 1:int(hx2) + 2] = False
    xs, out = np.flatnonzero(col), []
    for x in xs:
        if not out or x - out[-1] > ss:
            out.append(int(x))
    return out


def build(img):
    path = os.path.join(DS2, "images", img["filename"])
    A = [anns[a] for a in img["ann_ids"]]
    page = core.load_pages(path)[0]
    ink = core.binarize(cv2.cvtColor(page, cv2.COLOR_RGB2GRAY))
    staffs = [(s["x0"], s["lines"][0], s["x1"], s["lines"][4], s["lines"][2]) for s in core.detect_staves(ink)]
    if len(staffs) != sum(name_of(a) == "staff" for a in A):
        return None  # 오선 수가 주석과 다르면 이 페이지는 건너뜀
    notes, ignore = [], []
    for st in staffs:
        sx1, sy1, sx2, sy2, mid = st
        ss = (sy2 - sy1) / 4
        on = lambda a, pad=3: sy1 - pad * ss <= (a["a_bbox"][1] + a["a_bbox"][3]) / 2 <= sy2 + pad * ss and a["a_bbox"][0] >= sx1 - 6 * ss
        heads = []
        for a in A:
            if name_of(a).startswith("notehead"):
                rp = int(re.search(r"rel_position:(-?\d+)", a["comments"]).group(1))
                bx = a["a_bbox"]
                cy, ey = (bx[1] + bx[3]) / 2, mid - rp * ss / 2
                if abs(cy - ey) < 0.6 * ss:  # rel_position이 이 오선 기준으로 맞아떨어지는 음표만 (오선 귀속 판정)
                    heads.append((bx, rp))
        if not heads:
            continue
        clefs = sorted((a["a_bbox"][0], name_of(a)) for a in A if name_of(a) in MID and on(a, 1))
        if not clefs or clefs[0][0] > min(h[0][0] for h in heads):  # DS2 주석에 첫 음자리표가 빠진 오선이 있음 → 정답 불가, 평가 제외 구역
            first_head = min(h[0][0] for h in heads)
            ignore.append([int(sx1) - 1, int(sy1 - 3 * ss), int(clefs[0][0]) if clefs else int(sx2) + 1, int(sy2 + 3 * ss)])
            if not clefs:
                continue
        keys = sorted((a["a_bbox"][0], name_of(a)) for a in A if name_of(a) in ("keySharp", "keyFlat", "keyNatural") and on(a, 1))
        accs = [(a["a_bbox"], name_of(a)) for a in A if name_of(a).startswith("accidental") and on(a)]
        bars = barlines(path, st[:4], [h[0] for h in heads])
        measure_acc = {}
        cur_bar = -1
        for bx, rp in sorted(heads, key=lambda h: h[0][0]):
            hx1, hy1, hx2, hy2 = bx
            cx, cy = (hx1 + hx2) / 2, (hy1 + hy2) / 2
            clef = max((c for c in clefs if c[0] < cx), default=None)
            if not clef:
                continue
            idx = MID[clef[1]] + rp
            letter, octave = LETTERS[idx % 7], idx // 7
            # 조표: 음표 왼쪽 조표들 중 마지막 묶음
            left = [k for k in keys if k[0] < cx]
            grp = []
            for k in left:
                grp = grp + [k] if grp and k[0] - grp[-1][0] < 3 * ss else [k]
            # 조표 묶음 안의 제자리표는 이전 조표 취소용 → 개수에서 뺌 (예: ♮♮♮♮♭♭ = 플랫 2개)
            ns, nf = sum(k[1] == "keySharp" for k in grp), sum(k[1] == "keyFlat" for k in grp)
            key = {l: "#" for l in SHARPS[:ns]} if ns else {l: "b" for l in FLATS[:nf]}
            # 마디
            b = bisect.bisect_left(bars, cx)
            if b != cur_bar:
                cur_bar, measure_acc = b, {}
            # 붙은 임시표
            for abx, an in accs:
                ay = (abx[1] + abx[3]) / 2 + (0.28 * (abx[3] - abx[1]) if "Flat" in an else 0)
                if 0 <= hx1 - abx[2] < 2.5 * ss and abs(ay - cy) < 0.6 * ss:
                    measure_acc[(letter, octave)] = {"Sharp": "#", "Flat": "b", "Natural": "", "DoubleSharp": "x", "DoubleFlat": "bb"}[an.replace("accidental", "").replace("Small", "")]
            acc = measure_acc.get((letter, octave), key.get(letter, ""))
            notes.append({"x": int(cx), "y": int(cy), "pitch": f"{letter}{acc}{octave}"})
    return path, notes, ignore


os.makedirs(OUT, exist_ok=True)
per_font, made = {}, 0
for img in d["images"]:
    names = {name_of(anns[a]) for a in img["ann_ids"]}
    font = img["filename"].split("-aug-")[1].split("-")[0]
    if BAD & names or per_font.get(font, 0) >= 4:  # 폰트(악보 서체)별 최대 4장
        continue
    r = build(img)
    if not r or len(r[1]) < 40:
        continue
    per_font[font] = per_font.get(font, 0) + 1
    path, notes, ignore = r
    shutil.copy(path, os.path.join(OUT, img["filename"]))
    json.dump({"notes": notes, "ignore": ignore, "source": "DeepScoresV2 test (CC BY 4.0)"}, open(os.path.join(OUT, img["filename"][:-4] + ".json"), "w"))
    made += 1
    print(img["filename"], len(notes), "ignore", len(ignore))
    if made >= N:
        break
