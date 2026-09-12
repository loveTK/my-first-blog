"""검출 → 음높이 → 라벨 위치. 3~7단계에서 채운다."""
import os

import cv2
import numpy as np


def load_pages(path):
    """PDF/JPG/PNG → RGB numpy 페이지 리스트."""
    if path.lower().endswith(".pdf"):
        from pdf2image import convert_from_path  # poppler 필요
        pages = [np.array(p.convert("RGB")) for p in convert_from_path(path, dpi=200)]
    else:
        bgr = cv2.imread(path)
        pages = [] if bgr is None else [cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)]
    assert pages, f"못 읽음: {path}"
    return pages


def binarize(gray):
    """잉크=255, 배경=0."""
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    return ink


def detect_staves(ink):
    """오선 → [{"lines":[y*5], "space":float, "x0","x1","mask_x1"}].
    mask_x1: 음자리표+조표 끝 x (hollow 음표 검출에만 적용할 마스크 경계)."""
    h, w = ink.shape
    row_ink = (ink > 0).sum(axis=1)
    # 페이지 최대 잉크 폭 기준 상대 임계값: 첫 시스템에 악기명이 붙어 오선이 더 짧은 경우 등을 대비.
    # ponytail: 기울어진 스캔은 못 잡음. 필요시 deskew 추가.
    is_line = row_ink > max(0.6 * row_ink.max(), 0.2 * w)
    # 연속 행 → 선 하나(두께 반영해 중앙값 사용)
    lines, y = [], 0
    while y < h:
        if is_line[y]:
            y0 = y
            while y < h and is_line[y]:
                y += 1
            lines.append((y0 + y - 1) / 2)
        y += 1
    # 등간격 5개씩 묶기
    staves, i = [], 0
    while i + 4 < len(lines):
        gaps = [lines[i + k + 1] - lines[i + k] for k in range(4)]
        if max(gaps) < 1.3 * min(gaps):
            ys = lines[i:i + 5]
            space = (ys[4] - ys[0]) / 4
            band = (ink[int(ys[0]) - 1:int(ys[4]) + 2] > 0)
            cols = np.where(band.sum(axis=0) >= 5)[0]  # 5개 선 다 지나는 열 = 오선 구간
            x0, x1 = int(cols[0]), int(cols[-1])
            clef_x1, mask_x1 = _clef_key_end(ink, ys, space, x0)
            staves.append({"lines": ys, "space": space, "x0": x0, "x1": x1,
                           "clef_x1": clef_x1, "mask_x1": mask_x1})
            i += 5
        else:
            i += 1
    assert staves, "오선 못 찾음"
    return staves


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
    assert ci is not None, "음자리표 못 찾음"
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
WEIGHTS = os.environ.get("NOTUNE_WEIGHTS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "weights", "notes.onnx"))
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
    half = int(0.9 * ss)
    rows = ink[max(int(y - 0.6 * ss), 0):int(y + 0.6 * ss) + 1, max(x - half, 0):x + half + 1] > 0
    assert rows.size
    return bool(rows.all(axis=1).any())


def detect_barlines(ink, s, heads, ss):
    """마디선 x 목록. 오선 1~5줄을 세로로 꽉 채운 얇은 잉크 열 중 음표머리(기둥) 근처가 아닌 것."""
    top, bot = int(s["lines"][0]) + 1, int(s["lines"][4])  # 오선 안쪽만. 바깥 1px는 마디선이 정확히 줄에서 끝나 비어있음
    full = (ink[top:bot, s["x0"]:s["x1"] + 1] > 0).all(axis=0)
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
CLEF_BOTTOM = {"clef_g": 4 * 7 + 2, "clef_f": 2 * 7 + 4, "clef_c": 3 * 7 + 3}  # 맨 아래 줄 = E4 / G2 / F3 (7음계 절대 인덱스)


def _step_pitch(y, s, clef):
    """머리 y → (계이름 글자, 옥타브). 맨 아래 줄에서 반칸(ss/2) 단위로 올라간 수 = 음계 계단."""
    step = int(round((s["lines"][4] - y) / (s["space"] / 2)))
    idx = CLEF_BOTTOM[clef] + step
    assert 0 <= idx < 9 * 7, (y, clef)
    return LETTERS[idx % 7], idx // 7


def assign_pitches(ink, staves, dets, heads):
    """음자리표·조표·임시표(마디 내 유지) 반영해 heads에 pitch 채움. 반환: heads (pitch, clef 추가)."""
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
        syms = sorted(by_staff[si], key=lambda d: d["x"])
        clefs = [d for d in syms if d["cls"].startswith("clef")] or [{"x": s["x0"], "cls": "clef_g"}]  # ponytail: 음자리표 못 찾으면 높은음자리표
        bars = detect_barlines(ink, s, hs, ss)
        key, measure_acc, cur_bar, cur_clef = {}, {}, -1, clefs[0]["cls"]
        events = [("clef", d["x"], d) for d in clefs] + [("acc", d["x"], d) for d in syms if not d["cls"].startswith("clef")] + [("head", h["x"], h) for h in hs]
        events.sort(key=lambda e: e[1])
        for kind, x, d in events:
            bar = sum(1 for b in bars if b < x)
            if bar != cur_bar:
                cur_bar, measure_acc = bar, {}
            if kind == "clef":
                cur_clef = d["cls"]
            elif kind == "acc":
                alter = {"sharp": 1, "flat": -1, "natural": 0}[d["cls"]]
                ay = d["y"] + 0.28 * d["h"] if d["cls"] == "flat" else d["y"]  # ♭은 고리(아래쪽)가 음 위치. 박스 중심은 0.7ss 위
                letter, octv = _step_pitch(ay, s, cur_clef)
                # 바로 오른쪽(0.3~3ss)에 같은 높이 머리가 있으면 그 음표의 임시표, 아니면 조표
                attached = any(0.3 * ss < h["x"] - x < 3.0 * ss and abs(h["y"] - ay) < 0.6 * ss for h in hs)
                if attached:
                    measure_acc[(letter, octv)] = alter
                else:
                    key[letter] = alter
            else:
                letter, octv = _step_pitch(d["y"], s, cur_clef)
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
        if not (s["lines"][0] - 6 * ss < d["y"] < s["lines"][4] + 6 * ss) or d["x"] > s["x1"] + ss:
            continue
        outside = max(s["lines"][0] - d["y"], d["y"] - s["lines"][4])
        if outside > 0.75 * ss and not _has_ledger(ink, d["x"], d["y"], ss):
            continue  # 오선 밖인데 덧줄 없음 = 템포 표시(♩=96) 머리
        heads.append({"x": d["x"], "y": d["y"], "staff": si, "hollow": d["cls"] != "notehead_black"})
    assign_pitches(ink, staves, dets, heads)
    assert all("pitch" in h for h in heads)
    return [{"x": h["x"], "y": h["y"], "pitch": h["pitch"], "clef": h["clef"]} for h in heads]


def place_labels(notes, lang, position):
    """음표 → [{"x","y","text","clef"}] 라벨 위치. 6단계(언어) + 7단계(배치)."""
    assert position in ("below", "above"), position
    # ponytail: 미구현. 6단계 계이름 딕셔너리, 7단계 배치 규칙(NOTUNE_PLAN §1.3).
    return []
