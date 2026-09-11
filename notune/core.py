"""검출 → 음높이 → 라벨 위치. 3~7단계에서 채운다."""
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
    is_line = row_ink > 0.4 * w  # ponytail: 기울어진 스캔은 못 잡음. 필요시 deskew 추가.
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


def remove_lines(ink, ss):
    """오선·덧줄 같은 얇은 가로선 픽셀 제거. 세로로 선보다 두꺼운 잉크(음표·기둥·빔)는 남김."""
    h, w = ink.shape
    row_ink = (ink > 0).sum(axis=1)
    is_line = row_ink > 0.4 * w
    runs, y = [], 0
    while y < h:  # 오선 두께 측정
        if is_line[y]:
            y0 = y
            while y < h and is_line[y]:
                y += 1
            runs.append(y - y0)
        y += 1
    assert runs
    thick = max(int(np.median(runs)), 2)  # 덧줄은 오선보다 굵게(3px) 찍히는 경우 있어 최소 2
    horiz = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (int(1.4 * ss), 1)))
    on = ink > 0
    down = np.zeros((h, w), np.int32)  # 위에서부터 이어진 잉크 길이
    for r in range(1, h):
        down[r] = np.where(on[r], down[r - 1] + 1, 0)
    up = np.zeros((h, w), np.int32)
    for r in range(h - 2, -1, -1):
        up[r] = np.where(on[r], up[r + 1] + 1, 0)
    vrun = down + up - 1  # 둘 다 자기 자신 포함 → 세로 잉크 길이
    out = ink.copy()
    out[(horiz > 0) & (vrun <= thick + 1)] = 0
    assert out.sum() < ink.sum()
    return out


def _has_ledger(ink, x, y, ss):
    """머리 주변(±0.6ss 행)에 머리보다 넓은(1.8ss) 가로 잉크 줄 = 덧줄."""
    half = int(0.9 * ss)
    rows = ink[max(int(y - 0.6 * ss), 0):int(y + 0.6 * ss) + 1, max(x - half, 0):x + half + 1] > 0
    assert rows.size
    return bool(rows.all(axis=1).any())


def _staff_of(y, staves):
    return min(range(len(staves)), key=lambda i: abs((staves[i]["lines"][0] + staves[i]["lines"][4]) / 2 - y))


def detect_heads(ink, staves):
    """음표 머리 → [{"x","y","staff","hollow"}]. filled=열림 연산 잔존 덩어리, hollow=윤곽 계층의 구멍."""
    ss = float(np.median([s["space"] for s in staves]))
    clean = remove_lines(ink, ss)
    heads = []

    # filled: 기둥·빔·플래그(얇음)는 타원 커널 열림으로 사라지고 머리(≈1.2ss×1ss)만 남음
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(0.8 * ss), int(0.6 * ss)))
    opened = cv2.morphologyEx(clean, cv2.MORPH_OPEN, k)
    n, _, stats, _ = cv2.connectedComponentsWithStats(opened)
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        # 높이 <0.75ss: 기울어진 빔이 오선과 겹쳐 두꺼워진 조각(커널 높이만큼만 남음). 머리는 ≈1ss
        if not (0.7 * ss <= w <= 1.7 * ss and 0.75 * ss <= h <= 3.5 * ss):
            continue
        cnt = max(1, round(h / ss)) if w <= 1.4 * ss else 1  # 세로로 붙은 화음(2도) → h/ss개로 분할
        cnt = min(cnt, 3)
        for j in range(cnt):
            heads.append({"x": int(x + w / 2), "y": int(y + h * (j + 0.5) / cnt), "hollow": False})

    # hollow: 구멍 크기가 머리 안쪽(≈0.8ss×0.6ss)인 윤곽. 조표/음자리표 영역은 마스크
    contours, hier = cv2.findContours(clean, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    assert hier is not None
    for c, hh in zip(contours, hier[0]):
        if hh[3] == -1:  # 바깥 윤곽은 건너뜀, 구멍만
            continue
        x, y, w, h = cv2.boundingRect(c)
        pw, ph = cv2.boundingRect(contours[hh[3]])[2:]  # 부모(바깥) 크기
        # 부모 폭 <1ss: ♮♯·숫자. 부모 높이 1.2~2.5ss: ❋(페달)·8va 숫자 (온음표≈1ss, 2분음표+기둥≥2.5ss)
        # 구멍 폭 ≥0.7ss: ♯♮ 안쪽·8va 숫자 구멍(≤0.65ss) 제외. 온음표 0.8, 2분음표 0.85 정도
        if not (0.7 * ss <= w <= 1.3 * ss and 0.35 * ss <= h <= 1.1 * ss and cv2.contourArea(c) > 0.35 * w * h):
            continue
        if pw < 1.0 * ss or 1.2 * ss < ph < 2.5 * ss:
            continue
        cx, cy = int(x + w / 2), int(y + h / 2)
        if any(abs(o["x"] - cx) < 0.6 * ss and abs(o["y"] - cy) < 0.6 * ss for o in heads):
            continue  # 화음 머리·기둥 사이 틈은 구멍처럼 보임 → filled 머리 근처 구멍 무시
        heads.append({"x": cx, "y": cy, "hollow": True})

    # 오선 소속 + 영역 필터 + 중복 병합
    out = []
    for hd in heads:
        si = _staff_of(hd["y"], staves)
        s = staves[si]
        if not (s["lines"][0] - 5 * ss < hd["y"] < s["lines"][4] + 5 * ss) or hd["x"] > s["x1"]:
            continue
        outside = max(s["lines"][0] - hd["y"], hd["y"] - s["lines"][4])
        if outside > 0.75 * ss and not _has_ledger(ink, hd["x"], hd["y"], ss):
            continue  # 오선 밖인데 덧줄 없음 = 템포 표시(♩=96) 같은 장식
        if hd["x"] < (s["mask_x1"] if hd["hollow"] else s["clef_x1"]):  # 마스크: hollow만 조표까지, filled는 음자리표까지
            continue
        if any(abs(o["x"] - hd["x"]) <= 2 and abs(o["y"] - hd["y"]) <= 2 for o in out):
            continue
        hd["staff"] = si
        out.append(hd)
    return out


def detect_notes(page_rgb):
    """음표 머리 검출 + 음높이 → [{"x": int, "y": int, "pitch": "C4"}]."""
    gray = cv2.cvtColor(page_rgb, cv2.COLOR_RGB2GRAY)
    ink = binarize(gray)
    staves = detect_staves(ink)
    heads = detect_heads(ink, staves)
    assert isinstance(heads, list)
    # ponytail: 5단계에서 pitch 채움. 지금은 None.
    return [{"x": h["x"], "y": h["y"], "pitch": None} for h in heads]


def place_labels(notes, lang, position):
    """음표 → [{"x","y","text","clef"}] 라벨 위치. 6단계(언어) + 7단계(배치)."""
    assert position in ("below", "above"), position
    # ponytail: 미구현. 6단계 계이름 딕셔너리, 7단계 배치 규칙(NOTUNE_PLAN §1.3).
    return []
