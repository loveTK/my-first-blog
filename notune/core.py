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


def detect_notes(page_rgb):
    """음표 머리 검출 + 음높이 → [{"x": int, "y": int, "pitch": "C4"}]."""
    gray = cv2.cvtColor(page_rgb, cv2.COLOR_RGB2GRAY)
    assert gray.ndim == 2
    # ponytail: 미구현(빈 리스트). 3단계 오선 → 4단계 머리 → 5단계 음높이 순으로 채움.
    return []


def place_labels(notes, lang, position):
    """음표 → [{"x","y","text","clef"}] 라벨 위치. 6단계(언어) + 7단계(배치)."""
    assert position in ("below", "above"), position
    # ponytail: 미구현. 6단계 계이름 딕셔너리, 7단계 배치 규칙(NOTUNE_PLAN §1.3).
    return []
