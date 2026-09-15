"""검출 → 음높이 → 라벨 위치. 3~7단계에서 채운다."""
import os

import cv2
import numpy as np


def load_pages(path):
    """PDF/JPG/PNG → RGB numpy 페이지 리스트. 기울어진 스캔은 여기서 바로 세움(출력 악보도 같이 바로 선다)."""
    if path.lower().endswith(".pdf"):
        from pdf2image import convert_from_path  # poppler 필요
        pages = [np.array(p.convert("RGB")) for p in convert_from_path(path, dpi=200)]
    else:
        bgr = cv2.imread(path)
        pages = [] if bgr is None else [cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)]
    assert pages, f"못 읽음: {path}"
    return [deskew(p) for p in pages]


def skew_angle(gray, max_deg=3.0):
    """스캔 기울기(도). 오선이 수평이면 행 잉크 투영이 뾰족해짐(제곱합 최대) → 그 각을 찾음.
    1/4 축소본으로 0.25° 거친 탐색 → 0.05° 정밀 탐색."""
    small = cv2.resize(gray, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    ink = (binarize(small) > 0).astype(np.float32)
    h, w = ink.shape
    ctr = (w / 2, h / 2)

    def score(deg):
        m = cv2.getRotationMatrix2D(ctr, deg, 1.0)
        r = cv2.warpAffine(ink, m, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        p = r.sum(axis=1)
        return float((p * p).sum())

    def best(angles):
        # 1/4 축소본에선 ±0.1° 안이 같은 점수(평탄) → 평탄 구간의 가운데. 첫 최대값을 쓰면 -0.1°로 치우쳐 멀쩡한 페이지도 돌림
        sc = np.array([score(a) for a in angles])
        i = j = int(sc.argmax())
        while i > 0 and sc[i - 1] >= 0.995 * sc[j]:
            i -= 1
        k = j
        while k + 1 < len(sc) and sc[k + 1] >= 0.995 * sc[j]:
            k += 1
        return float((angles[i] + angles[k]) / 2)

    b = best(np.arange(-max_deg, max_deg + 1e-6, 0.25))
    return best(np.arange(b - 0.25, b + 0.25 + 1e-6, 0.05))


def deskew(page_rgb):
    """기울어진 페이지를 바로 세움(흰 배경 채움). 0.1° 미만이면 원본 그대로(깨끗한 렌더에 보간 번짐 안 줌)."""
    deg = skew_angle(cv2.cvtColor(page_rgb, cv2.COLOR_RGB2GRAY))
    if abs(deg) < 0.1:
        return page_rgb
    h, w = page_rgb.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1.0)
    return cv2.warpAffine(page_rgb, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))


def flatten(gray):
    """고르지 않은 조명(그림자·누런 종이) 보정: 배경 밝기로 나눠 흰 종이로 만든다.
    배경 = 1/4 축소본을 닫힘 연산(팽창→침식)으로 기호를 지운 것. 커널은 폭의 1/40 ≈ 3~4 staff space."""
    h, w = gray.shape
    small = cv2.resize(gray, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    k = max(int(w / 160) | 1, 5)
    bg = cv2.morphologyEx(small, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    bg = cv2.resize(cv2.GaussianBlur(bg, (0, 0), k / 2), (w, h), interpolation=cv2.INTER_LINEAR)
    bg = np.maximum(bg, 32).astype(np.float32)
    out = np.minimum(gray.astype(np.float32) * 255.0 / bg, 255.0)
    return out.astype(np.uint8)


def binarize(gray):
    """잉크=255, 배경=0. 조명 보정 후 Otsu."""
    _, ink = cv2.threshold(flatten(gray), 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    return ink


def _line_rows(ink, thr):
    """임계값 넘는 연속 행 덩어리마다 잉크 최대 행 하나 = 선 후보 (덩어리 중심을 쓰면 옆 글자 행과 붙었을 때 밀림)."""
    h, w = ink.shape
    row_ink = (ink > 0).sum(axis=1)
    is_line = row_ink > thr
    lines, y = [], 0
    while y < h:
        if is_line[y]:
            y0 = y
            while y < h and is_line[y]:
                y += 1
            lines += [y0 + k for k in _peaks(row_ink[y0:y])]
        y += 1
    return lines


def _peaks(v, min_sep=6):
    """덩어리 안의 잉크 봉우리들. 번진 스캔에서 이웃한 두 선이 한 덩어리로 붙어도 각각 잡음."""
    if len(v) < min_sep:
        return [int(np.argmax(v))]
    out = []
    for i in range(len(v)):
        if v[i] < 0.5 * v.max() or (i > 0 and v[i] < v[i - 1]) or (i + 1 < len(v) and v[i] < v[i + 1]):
            continue
        if out and i - out[-1] < min_sep:
            if v[i] > v[out[-1]]:
                out[-1] = i
            continue
        out.append(i)
    return out


def _make_staff(ink, ys):
    """5선 y → staff dict. 5선이 함께 지나는 가로폭이 좁으면(가사·제목 행이 묶인 것) None."""
    w = ink.shape[1]
    band = (ink[int(ys[0]) - 1:int(ys[4]) + 2] > 0)
    cols = np.where(band.sum(axis=0) >= 5)[0]  # 5개 선 다 지나는 열 = 오선 구간
    if len(cols) == 0 or cols[-1] - cols[0] < 0.3 * w:
        return None
    space = (ys[4] - ys[0]) / 4
    x0, x1 = int(cols[0]), int(cols[-1])
    clef_x1, mask_x1 = _clef_key_end(ink, ys, space, x0)
    return {"lines": ys, "space": space, "x0": x0, "x1": x1, "clef_x1": clef_x1, "mask_x1": mask_x1}


def _group_strict(ink, lines):
    """연속 5개 등간격."""
    staves, i = [], 0
    while i + 4 < len(lines):
        gaps = [lines[i + k + 1] - lines[i + k] for k in range(4)]
        if max(gaps) < 1.3 * min(gaps):
            s = _make_staff(ink, lines[i:i + 5])
            if s:
                staves.append(s)
                i += 5
                continue
        i += 1
    return staves


def _group_lenient(ink, lines):
    """등간격 5개를 이어가되, 간격이 0.7g 미만인 끼어든 후보(빔·가사 행)는 건너뜀."""
    w = ink.shape[1]
    staves, i = [], 0
    while i < len(lines):
        found = None
        for j in range(i + 1, min(i + 4, len(lines))):
            g = lines[j] - lines[i]
            if g < 3 or g > w / 30:
                continue
            ys, k = [lines[i], lines[j]], j
            while len(ys) < 5 and k + 1 < len(lines):
                k += 1
                d = lines[k] - ys[-1]
                if d < 0.7 * g:
                    continue
                if d > 1.3 * g:
                    break
                ys.append(lines[k])
            if len(ys) == 5:
                s = _make_staff(ink, ys)
                if s:
                    found = (s, k)
                    break
        if found:
            staves.append(found[0])
            i = found[1] + 1
        else:
            i += 1
    return staves


def _group_ref(ink, lines, ref, row_ink):
    """기준 간격(ref)으로 다음 선 자리를 예측하고 가장 가까운 후보(±0.25ref)를 고른다.
    빔·가사 행처럼 끼어든 후보는 자리에 안 맞으니 자연히 무시됨(빽빽한 16분음표 빔 시스템용).
    5선 중 1개까지는 후보에 없어도 예측 자리에 잉크가 조금(폭의 10%)이라도 있으면 그 자리로 채움."""
    w = ink.shape[1]
    arr = np.array(lines, dtype=float)
    staves, used = [], set()
    for y0 in lines:
        if y0 in used:
            continue
        ys, missing = [float(y0)], 0
        while len(ys) < 5:
            exp = ys[-1] + ref
            cand = arr[(np.abs(arr - exp) <= 0.25 * ref) & (arr > ys[-1])]
            if len(cand):
                ys.append(float(cand[np.abs(cand - exp).argmin()]))
            else:
                r = int(round(exp))
                if missing or r + 2 >= len(row_ink) or row_ink[max(r - 2, 0):r + 3].max() < 0.1 * w:
                    break
                ys.append(float(r + int(row_ink[max(r - 2, 0):r + 3].argmax()) - min(r, 2)))
                missing += 1
        if len(ys) < 5:
            continue
        s = _make_staff(ink, ys)
        if s:
            staves.append(s)
            used.update(int(y) for y in ys)
    return staves


def detect_staves(ink):
    """오선 → [{"lines":[y*5], "space":float, "x0","x1","mask_x1"}].
    mask_x1: 음자리표+조표 끝 x (hollow 음표 검출에만 적용할 마스크 경계).
    1) 진한 선 기준(페이지 최대 잉크의 60%)으로 찾고, 2) 옅게 인쇄된 시스템은 낮은 임계값으로 보완.
    보완: 1)에서 오선 간격을 알면 그 간격으로 자리를 맞춰 찾고(_group_ref), 모르면 등간격 탐색(_group_lenient).
    보완 오선은 기존 오선과 세로로 겹치거나 선 간격이 크게 다르면 버림(가짜 방지).
    기울기는 load_pages의 deskew가, 조명 얼룩은 binarize의 flatten이 미리 처리."""
    h, w = ink.shape
    row_ink = (ink > 0).sum(axis=1)
    row_max = row_ink.max()
    staves = _group_strict(ink, _line_rows(ink, max(0.6 * row_max, 0.2 * w)))
    ref = float(np.median([s["space"] for s in staves])) if staves else None
    low = _line_rows(ink, 0.2 * w)
    extra = _group_ref(ink, low, ref, row_ink) if ref else _group_lenient(ink, low)
    for s in extra:
        if ref and not 0.7 * ref < s["space"] < 1.3 * ref:
            continue
        if any(s["lines"][0] <= t["lines"][4] + t["space"] and t["lines"][0] <= s["lines"][4] + s["space"] for t in staves):
            continue
        staves.append(s)
    staves.sort(key=lambda s: s["lines"][0])
    assert staves, "오선 못 찾음"
    for s in staves:
        s["ly"] = _track_lines(ink, s)
    return staves


def _track_lines(ink, s):
    """휜 스캔(책 등 쪽이 굽어 오선이 활처럼 휨)용: 5줄을 x 방향으로 따라가며 열마다 실제 y를 기록 → (5, W) 배열.
    창(2ss 폭)마다 5줄이 함께 움직인 세로 오프셋을 잉크 합이 최대인 곳으로 찾는다(빔이 한 줄에 겹쳐도 나머지 4줄이 버팀).
    전체 행 투영으로 찾은 s["lines"]는 페이지 일부에서만 맞을 수 있어, 가장 잘 맞는 창에서 시작해 양쪽으로 추적."""
    h, w = ink.shape
    ss, base = s["space"], np.array(s["lines"], dtype=float)
    win, r = max(int(2 * ss), 8), max(int(0.35 * ss), 2)
    xs = list(range(s["x0"], max(s["x1"] - win + 1, s["x0"] + 1), win))
    on = ink > 0
    profs = []
    for x in xs:
        p = on[:, x:x + win].sum(axis=1).astype(np.float32)
        p3 = p.copy()  # 줄 두께 2~3px → 이웃 행 최대값(±1)로 관대하게
        p3[1:] = np.maximum(p3[1:], p[:-1])
        p3[:-1] = np.maximum(p3[:-1], p[1:])
        profs.append(p3)

    def score(p, d):
        ys = np.clip(np.round(base + d).astype(int), 0, h - 1)
        return float(p[ys].sum())

    start = max(range(len(xs)), key=lambda i: score(profs[i], 0))
    off = np.zeros(len(xs))
    for order in (range(start + 1, len(xs)), range(start - 1, -1, -1)):
        prev = 0.0
        for i in order:
            cands = range(int(prev) - r, int(prev) + r + 1)
            d = max(cands, key=lambda d: score(profs[i], d))
            if score(profs[i], d) < 1.5 * win:  # 줄이 거의 안 보이는 창(끝 여백 등)은 이전 값 유지
                d = prev
            off[i] = prev = d
    if len(off) >= 3:  # 창 하나의 튐(빔·화음 덩어리) 완화
        off = np.array([np.median(off[max(i - 1, 0):i + 2]) for i in range(len(off))])
    centers = np.array(xs, dtype=float) + win / 2
    cols = np.interp(np.arange(w, dtype=float), centers, off) if len(xs) > 1 else np.full(w, off[0])
    return base[:, None] + cols[None, :]


def line_y(s, k, x):
    """오선 s의 k번째 줄(0=맨 위)이 열 x에서 지나는 y. 휜 페이지에선 열마다 다름."""
    ly = s.get("ly")
    if ly is None:
        return float(s["lines"][k])
    return float(ly[k, min(max(int(x), 0), ly.shape[1] - 1)])


def _clef_key_end(ink, ys, space, x0):
    """오선 밴드 열 투영에서 음자리표 덩어리 → 조표·박자표 덩어리 순서로 따라감.
    반환: (음자리표 끝 x, 조표/박자표 끝 x)."""
    top, bot = int(ys[0] - 2 * space), int(ys[4] + 2 * space)
    band = ink[max(top, 0):bot].copy()
    for y in ys:  # 오선 자체는 지워서 열 잉크 계산에서 제외
        r = int(y) - max(top, 0)
        band[max(r - 2, 0):r + 3] = 0
    col = band.sum(axis=0) > 0
    # 잉크 열 덩어리(blob) → [(시작x, 끝x)]
    blobs, x = [], x0
    while x < len(col):
        if col[x]:
            xs = x
            while x < len(col) and col[x]:
                x += 1
            blobs.append((xs, x))
        x += 1
    # 음자리표 = x0 근처(4ss 안) 첫 넓은(≥1.5ss) 덩어리. 그 앞의 브레이스·바선은 건너뜀
    ci = next((k for k, (xs, xe) in enumerate(blobs) if xe - xs >= 1.5 * space and xs - x0 < 4 * space), None)
    if ci is None:  # 음자리표 없는 오선(이어지는 줄 등). 음자리표는 YOLO가 따로 잡으니 여기선 x0로 둠
        return x0, x0
    clef_x1 = end = blobs[ci][1]
    # 조표·박자표: 틈 ≤1.3ss로 이어지고 폭 ≤1.9ss. 음표 무리(빔·화음)는 더 넓어서 멈춤.
    # ponytail: 조표 바로 뒤(틈≤1.3ss) 홀로 있는 2분음표는 마스크에 먹힘 → 실측 후 임계값 조정
    for xs, xe in blobs[ci + 1:]:
        if xs - end > 1.3 * space or xe - xs > 1.9 * space:
            break
        end = xe
    return clef_x1, end


TRAIN_SS = 16.5  # 학습 데이터(DeepScoresV2) staff space(px). 추론 전 페이지를 이 크기로 맞춤
TILE, STRIDE = 1024, 896
CLASSES = ["notehead_black", "notehead_half", "notehead_whole", "sharp", "flat", "natural", "clef_g", "clef_f", "clef_c"]
WEIGHTS = os.environ.get("NOTALO_WEIGHTS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "weights", "notes.onnx"))
_sess = None


def _session():
    global _sess
    if _sess is None:
        import onnxruntime as ort
        _sess = ort.InferenceSession(WEIGHTS, providers=["CPUExecutionProvider"])
    return _sess


def detect_symbols(page_rgb, ss, conf=0.3):
    """YOLO(ONNX) 타일 추론 → [{"x","y","w","h","cls","conf"}] (페이지 픽셀 좌표, x/y=중심).
    페이지를 학습 staff space로 리사이즈 → 1024 타일(겹침 128) → 클래스 무관 NMS."""
    scale = TRAIN_SS / ss
    img = cv2.resize(page_rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
    H, W = img.shape[:2]
    if H < TILE or W < TILE:
        img = cv2.copyMakeBorder(img, 0, max(TILE - H, 0), 0, max(TILE - W, 0), cv2.BORDER_CONSTANT, value=(255, 255, 255))
        H, W = img.shape[:2]
    ys = sorted(set(list(range(0, H - TILE + 1, STRIDE)) + [H - TILE]))
    xs = sorted(set(list(range(0, W - TILE + 1, STRIDE)) + [W - TILE]))
    sess, name = _session(), _session().get_inputs()[0].name
    boxes, scores, clss = [], [], []
    for ty in ys:
        for tx in xs:
            tile = img[ty:ty + TILE, tx:tx + TILE].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
            out = sess.run(None, {name: tile})[0][0]  # (4+nc, N): cx,cy,w,h, class scores
            sc = out[4:]
            cls = sc.argmax(axis=0)
            cf = sc.max(axis=0)
            keep = cf > conf
            for (cx, cy, w, h), c, f in zip(out[:4].T[keep], cls[keep], cf[keep]):
                boxes.append([float(cx - w / 2 + tx), float(cy - h / 2 + ty), float(w), float(h)])
                scores.append(float(f))
                clss.append(int(c))
    dets = []
    if boxes:
        idx = cv2.dnn.NMSBoxes(boxes, scores, conf, 0.5)
        for i in np.array(idx).reshape(-1):
            x, y, w, h = boxes[i]
            dets.append({"x": int((x + w / 2) / scale), "y": int((y + h / 2) / scale), "w": w / scale, "h": h / scale,
                         "cls": CLASSES[clss[i]] if clss[i] < len(CLASSES) else str(clss[i]), "conf": scores[i]})
    assert isinstance(dets, list)
    return dets


def _staff_of(y, staves):
    return min(range(len(staves)), key=lambda i: abs((staves[i]["lines"][0] + staves[i]["lines"][4]) / 2 - y))


def _has_ledger(ink, x, y, ss):
    """머리 주변(±0.6ss 행)에 머리보다 넓은(1.8ss) 가로 잉크 줄 = 덧줄."""
    half = int(0.6 * ss)  # 덧줄이 짧은 서체(gutenberg 등)도 잡히게 머리 폭(≈1.2ss)만 본다
    rows = ink[max(int(y - 0.6 * ss), 0):int(y + 0.6 * ss) + 1, max(x - half, 0):x + half + 1] > 0
    assert rows.size
    return bool(rows.all(axis=1).any())


def detect_barlines(ink, s, heads, ss):
    """마디선 x 목록. 오선 1~5줄을 세로로 꽉 채운 얇은 잉크 열 중 음표머리(기둥) 근처가 아닌 것."""
    # 오선 안쪽만(위아래 1px 제외: 마디선은 정확히 줄에서 끝나 바깥은 비어있음). 휜 페이지라 열마다 줄 y가 다름
    on = ink > 0
    full = np.array([on[int(line_y(s, 0, x)) + 1:int(line_y(s, 4, x)), x].all() for x in range(s["x0"], s["x1"] + 1)])
    hx = np.array([h["x"] for h in heads]) if heads else np.zeros(0)
    xs, x = [], 0
    while x < len(full):
        if full[x]:
            x0 = x
            while x < len(full) and full[x]:
                x += 1
            cx = s["x0"] + (x0 + x - 1) / 2
            if x - x0 <= 0.35 * ss and (hx.size == 0 or np.abs(hx - cx).min() > 0.9 * ss):
                if not xs or cx - xs[-1] > 1.0 * ss:  # 겹마디선은 하나로
                    xs.append(cx)
        x += 1
    return xs


LETTERS = "CDEFGAB"
CLEF_BOTTOM = {"clef_g": 4 * 7 + 2, "clef_f": 2 * 7 + 4, "clef_c": 3 * 7 + 3, "clef_c_tenor": 3 * 7 + 1}  # 맨 아래 줄 = E4 / G2 / F3(알토) / D3(테너)


def _clef_kind(d, s):
    """YOLO는 C 음자리표를 한 클래스로 봄. 기호 중심이 가운데 줄보다 반 칸 이상 위면 테너(4번째 줄), 아니면 알토."""
    if d["cls"] == "clef_c" and d["y"] < line_y(s, 2, d["x"]) - 0.5 * s["space"]:
        return "clef_c_tenor"
    return d["cls"]


def _step_pitch(y, s, clef, x=None):
    """머리 (x,y) → (계이름 글자, 옥타브). 그 열의 맨 아래 줄에서 반칸(ss/2) 단위로 올라간 수 = 음계 계단."""
    bottom = line_y(s, 4, x) if x is not None else s["lines"][4]
    step = int(round((bottom - y) / (s["space"] / 2)))
    idx = CLEF_BOTTOM[clef] + step
    assert 0 <= idx < 9 * 7, (y, clef)
    return LETTERS[idx % 7], idx // 7


SHARP_ORDER, FLAT_ORDER = "FCGDAEB", "BEADGCF"


def _dedupe(ds, ss):
    """같은 기호에 상자 2개(조각 검출) → x 0.4ss 이내이고 세로로 절반 이상 겹치면 신뢰도 높은 것만."""
    ds, kept = sorted(ds, key=lambda d: -d["conf"]), []
    for d in ds:
        dup = False
        for k in kept:
            ov = min(d["y"] + d["h"] / 2, k["y"] + k["h"] / 2) - max(d["y"] - d["h"] / 2, k["y"] - k["h"] / 2)
            if abs(d["x"] - k["x"]) < 0.4 * ss and ov > 0.5 * min(d["h"], k["h"]):
                dup = True
                break
        if not dup:
            kept.append(d)
    return sorted(kept, key=lambda d: d["x"])


def assign_pitches(ink, staves, dets, heads):
    """음자리표·조표·임시표(마디 내 유지) 반영해 heads에 pitch 채움. 반환: heads (pitch, clef 추가).
    조표 = 음자리표/마디선 뒤 음표가 나오기 전의 임시표 묶음. 개수로 정함(♯ F C G D A E B / ♭ B E A D G C F 순), 제자리표 묶음은 조표 취소."""
    ss = float(np.median([s["space"] for s in staves]))
    by_staff = {i: [] for i in range(len(staves))}
    for d in dets:
        if d["cls"].startswith("notehead"):
            continue
        si = _staff_of(d["y"], staves)
        if abs(d["y"] - (staves[si]["lines"][0] + staves[si]["lines"][4]) / 2) < 4 * ss:
            by_staff[si].append(d)
    for si, s in enumerate(staves):
        hs = sorted((h for h in heads if h["staff"] == si), key=lambda h: h["x"])
        syms = by_staff[si]
        clefs = _dedupe([d for d in syms if d["cls"].startswith("clef")], 1.5 * ss) or [{"x": s["x0"], "cls": "clef_g"}]  # ponytail: 음자리표 못 찾으면 높은음자리표
        accs = _dedupe([d for d in syms if not d["cls"].startswith("clef")], ss)
        bars = detect_barlines(ink, s, hs, ss)
        key, measure_acc, cur_bar, cur_clef = {}, {}, -1, _clef_kind(clefs[0], s)
        events = [("clef", d["x"], d) for d in clefs] + [("acc", d["x"], d) for d in accs] + [("head", h["x"], h) for h in hs]
        events.sort(key=lambda e: e[1])
        head_since_anchor, group = False, []  # group: 음자리표/마디선 뒤 음표 전에 나온 임시표들(조표 후보)

        def flush():
            nonlocal group, key
            if not group:
                return
            kinds = {g["cls"] for g in group}
            if kinds == {"natural"}:
                key = {}
            elif "sharp" in kinds:
                key = {l: 1 for l in SHARP_ORDER[:sum(g["cls"] == "sharp" for g in group)]}
            else:
                key = {l: -1 for l in FLAT_ORDER[:sum(g["cls"] == "flat" for g in group)]}
            group = []

        for kind, x, d in events:
            bar = sum(1 for b in bars if b < x)
            if bar != cur_bar:
                flush()
                cur_bar, measure_acc, head_since_anchor = bar, {}, False
            if kind == "clef":
                flush()
                cur_clef, head_since_anchor = _clef_kind(d, s), False
            elif kind == "acc":
                alter = {"sharp": 1, "flat": -1, "natural": 0}[d["cls"]]
                ay = d["y"] + 0.28 * d["h"] if d["cls"] == "flat" else d["y"]  # ♭은 고리(아래쪽)가 음 위치. 박스 중심은 0.7ss 위
                # 바로 오른쪽(0.3~3ss)에 같은 높이 머리가 있으면 그 음표의 임시표
                near = [h for h in hs if 0.3 * ss < h["x"] - x < 3.0 * ss and abs(h["y"] - ay) < 0.6 * ss]
                if near:
                    flush()
                    letter, octv = _step_pitch(near[0]["y"], s, cur_clef, near[0]["x"])
                    measure_acc[(letter, octv)] = alter
                elif not head_since_anchor:
                    group.append(d)  # 조표 후보 (묶음은 다음 음표/마디선/음자리표에서 확정)
                # 그 외(음표 뒤에 홀로 있는 임시표)는 무시 — 화음 임시표 등은 near에서 잡힘
            else:
                flush()
                head_since_anchor = True
                letter, octv = _step_pitch(d["y"], s, cur_clef, d["x"])
                alter = measure_acc.get((letter, octv), key.get(letter, 0))
                d["pitch"] = f"{letter}{'#' if alter > 0 else 'b' if alter < 0 else ''}{octv}"
                d["clef"] = "bass" if cur_clef == "clef_f" else "treble"
    return heads


def detect_notes(page_rgb):
    """음표 머리 검출 + 음높이 → [{"x","y","pitch","clef"}]. pitch 예: C4, F#5, Bb3."""
    ink = binarize(cv2.cvtColor(page_rgb, cv2.COLOR_RGB2GRAY))
    staves = detect_staves(ink)
    if not os.path.exists(WEIGHTS):  # 가중치 미배포 상태(학습 중)엔 빈 결과 — 서비스는 안 죽게
        return []
    ss = float(np.median([s["space"] for s in staves]))
    dets = detect_symbols(page_rgb, ss)
    heads = []
    for d in dets:
        if not d["cls"].startswith("notehead"):
            continue
        si = _staff_of(d["y"], staves)
        s = staves[si]
        top, bot = line_y(s, 0, d["x"]), line_y(s, 4, d["x"])  # 휜 페이지: 그 열의 줄 위치
        if not (top - 6 * ss < d["y"] < bot + 6 * ss) or d["x"] > s["x1"] + ss:
            continue
        outside = max(top - d["y"], d["y"] - bot)
        if outside > 0.75 * ss and not _has_ledger(ink, d["x"], d["y"], ss):
            continue  # 오선 밖인데 덧줄 없음 = 템포 표시(♩=96) 머리
        heads.append({"x": d["x"], "y": d["y"], "staff": si, "hollow": d["cls"] != "notehead_black", "conf": d["conf"]})
    # 같은 머리에 상자 2개(클래스 다른 중복 검출) → 신뢰도 높은 것만
    heads.sort(key=lambda h: -h["conf"])
    kept = []
    for h in heads:
        if not any(abs(h["x"] - k["x"]) < 0.5 * ss and abs(h["y"] - k["y"]) < 0.5 * ss for k in kept):
            kept.append(h)
    heads = kept
    assign_pitches(ink, staves, dets, heads)
    assert all("pitch" in h for h in heads)
    # ss/staff_top/staff_bot은 7단계 라벨 배치용
    return [{"x": h["x"], "y": h["y"], "pitch": h["pitch"], "clef": h["clef"], "staff": h["staff"], "ss": ss,
             "staff_top": line_y(staves[h["staff"]], 0, h["x"]), "staff_bot": line_y(staves[h["staff"]], 4, h["x"])} for h in heads]


NAMES = {  # 고정도: C=도. 옥타브는 표기 안 함
    "ko": ["도", "레", "미", "파", "솔", "라", "시"],
    "en": ["C", "D", "E", "F", "G", "A", "B"],
    "it": ["Do", "Re", "Mi", "Fa", "Sol", "La", "Si"],
    "ja": ["ド", "レ", "ミ", "ファ", "ソ", "ラ", "シ"],
    "de": ["C", "D", "E", "F", "G", "A", "H"],
}


def note_name(pitch, lang):
    """'F#5' → '파♯' / 'F♯' / 'Fis' 등. 독일식은 -is/-es, 예외 Es·As·B(=Hb)."""
    assert lang in NAMES and pitch[0] in LETTERS, (pitch, lang)
    alter = pitch[1] if len(pitch) > 1 and pitch[1] in "#b" else ""
    name = NAMES[lang][LETTERS.index(pitch[0])]
    if lang == "de":
        return name + "is" if alter == "#" else {"E": "Es", "A": "As", "H": "B"}.get(name, name + "es") if alter == "b" else name
    return name + {"#": "♯", "b": "♭", "": ""}[alter]


def _overlap(a, b, gap=1):
    return a[0] < b[2] + gap and b[0] < a[2] + gap and a[1] < b[3] + gap and b[1] < a[3] + gap


def _chords(notes, ss):
    """같은 오선에서 x가 0.35ss 안에 붙은 머리 = 화음 한 덩어리. x순 정렬된 그룹 리스트."""
    groups = []
    for n in sorted(notes, key=lambda n: (n["staff"], n["x"], n["y"])):
        if groups and groups[-1][0]["staff"] == n["staff"] and abs(groups[-1][-1]["x"] - n["x"]) < 0.35 * ss:
            groups[-1].append(n)
        else:
            groups.append([n])
    return groups


def place_labels(notes, lang, position, mode="greedy"):
    """음표 → [{"x","y","text","clef","size"}] (x,y=박스 왼쪽 위).
    greedy: 아래→위→좌우 0.5ss→폰트 85% 순서로 겹치지 않는 첫 자리. 화음은 세로 스택.
    lane: 오선 아래(위) 레인에 x 겹침 없이 층층이. 라벨끼리 절대 안 겹침.
    overlay: 머리 위에 덮어씀."""
    assert position in ("below", "above") and mode in ("greedy", "lane", "overlay"), (position, mode)
    if not notes:
        return []
    import render
    ss = notes[0]["ss"]
    out = []
    if mode == "overlay":
        size = 1.0 * ss
        for n in notes:
            text = note_name(n["pitch"], lang)
            w, h = render.text_size(text, size)
            out.append({"x": int(n["x"] - w / 2), "y": int(n["y"] - h / 2), "text": text, "clef": n["clef"], "size": size})
        return out

    heads = [(n["x"] - 0.6 * ss, n["y"] - 0.5 * ss, n["x"] + 0.6 * ss, n["y"] + 0.5 * ss) for n in notes]
    placed = []
    lanes = {}  # lane: (staff, side) -> [레인별 마지막 x끝]
    for g in _chords(notes, ss):
        g = sorted(g, key=lambda n: n["y"])  # 위 음 → 위 줄
        text = "\n".join(note_name(n["pitch"], lang) for n in g)
        clef, cx = g[0]["clef"], sum(n["x"] for n in g) / len(g)
        top, bot = g[0]["y"] - 0.5 * ss, g[-1]["y"] + 0.5 * ss
        if mode == "lane":
            size = 1.2 * ss
            w, h = render.text_size(text, size)
            n0 = g[0]
            same = [m for m in notes if m["staff"] == n0["staff"]]
            base = (max(n0["staff_bot"], max(m["y"] for m in same)) + 0.8 * ss) if position == "below" \
                else (min(n0["staff_top"], min(m["y"] for m in same)) - 0.8 * ss - h)
            key = (n0["staff"], position)
            ends = lanes.setdefault(key, [])
            x0 = cx - w / 2
            lane = next((i for i, e in enumerate(ends) if x0 > e + 2), len(ends))
            if lane == len(ends):
                ends.append(0)
            ends[lane] = x0 + w
            y0 = base + lane * (h + 2) if position == "below" else base - lane * (h + 2)
            out.append({"x": int(x0), "y": int(y0), "text": text, "clef": clef, "size": size})
            continue
        # greedy
        mine = [heads[notes.index(n)] for n in g]
        others = [r for r in heads if r not in mine]
        chosen = None
        for size in (1.3 * ss, 1.3 * ss * 0.85):
            w, h = render.text_size(text, size)
            below, above = bot + 0.3 * ss, top - 0.3 * ss - h
            order = [below, above] if position == "below" else [above, below]
            cands = [(cx - w / 2 + dx, y) for y in order for dx in (0, -0.5 * ss, 0.5 * ss)]
            for x0, y0 in cands:
                r = (x0, y0, x0 + w, y0 + h)
                if not any(_overlap(r, p) for p in placed) and not any(_overlap(r, o) for o in others):
                    chosen = (x0, y0, size)
                    break
            if chosen:
                break
        if not chosen:  # ponytail: 자리 없으면 그냥 아래(겹침 허용). 리더라인은 안 함
            size = 1.3 * ss * 0.85
            w, h = render.text_size(text, size)
            chosen = (cx - w / 2, bot + 0.3 * ss, size)
        x0, y0, size = chosen
        w, h = render.text_size(text, size)
        placed.append((x0, y0, x0 + w, y0 + h))
        out.append({"x": int(x0), "y": int(y0), "text": text, "clef": clef, "size": size})
    return out
