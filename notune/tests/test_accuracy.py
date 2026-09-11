"""정확도 게이트: 음높이 ≥98%, 누락 ≤1%, 오탐 ≤0.5%. 채점 로직은 2단계.
실행: py -3 tests/test_accuracy.py  (pytest 안 씀 — 의존성 추가 금지)"""
import glob
import os

FIX = os.path.join(os.path.dirname(__file__), "fixtures")

if __name__ == "__main__":
    assert os.path.isdir(FIX), FIX
    imgs = [p for p in glob.glob(os.path.join(FIX, "*")) if p.rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "pdf")]
    # ponytail: 2단계에서 정답 JSON 로드 → core.detect_notes 비교 → 3개 지표 계산 → 게이트 판정.
    print(f"fixtures {len(imgs)}장 — 채점은 2단계에서")
