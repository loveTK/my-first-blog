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
            staves.append({"lines": ys, "space": space, "x0": x0, "x1": x1,
                           "mask_x1": _clef_key_end(ink, ys, space, x0)})
            i += 5
        else:
            i += 1
    assert staves, "오선 못 찾음"
    return staves


def _clef_key_end(ink, ys, space, x0):
    """오선 밴드 안에서 x0부터 잉크 덩어리 따라가다 0.6 staff-space 이상 빈 열 나오면 끝.
    음자리표→조표 사이 틈은 그보다 좁고, 조표→첫 음표/박자표 틈은 넓다는 가정."""
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
    end = blobs[ci][1]
    # 조표·박자표: 틈 ≤1.3ss로 이어지고 폭 ≤1.9ss. 음표 무리(빔·화음)는 더 넓어서 멈춤.
    # ponytail: 조표 바로 뒤(틈≤1.3ss) 홀로 있는 2분음표는 마스크에 먹힘 → 실측 후 임계값 조정
    for xs, xe in blobs[ci + 1:]:
        if xs - end > 1.3 * space or xe - xs > 1.9 * space:
            break
        end = xe
    return end


def detect_notes(page_rgb):
    """음표 머리 검출 + 음높이 → [{"x": int, "y": int, "pitch": "C4"}]."""
    gray = cv2.cvtColor(page_rgb, cv2.COLOR_RGB2GRAY)
    ink = binarize(gray)
    staves = detect_staves(ink)
    assert staves
    # ponytail: 4단계 머리 검출 → 5단계 음높이 순으로 채움.
    return []


def place_labels(notes, lang, position):
    """음표 → [{"x","y","text","clef"}] 라벨 위치. 6단계(언어) + 7단계(배치)."""
    assert position in ("below", "above"), position
    # ponytail: 미구현. 6단계 계이름 딕셔너리, 7단계 배치 규칙(NOTUNE_PLAN §1.3).
    return []
