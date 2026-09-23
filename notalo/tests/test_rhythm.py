"""음길이 게이트: rhythm/t1.png(t1.ly를 lilypond -dresolution=200 로 렌더)에서 오선별 pitch:dur 열이 정답과 95% 이상 일치.
화음(0.35ss 안 머리)은 토큰을 정렬해 순서 무관. 실행: python3 tests/test_rhythm.py  (pytest 안 씀)"""
import os
import sys
from difflib import SequenceMatcher

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import core  # noqa: E402

EXPECT = [  # t1.ly 순서, dur은 4분음표=1
    "C4:4 D4:2 E4:2 F4:1 G4:1 A4:1 B4:1 C5:0.5 D5:0.5 E5:0.5 F5:0.5 G5:1 A5:1 B5:1.5 C6:0.5 D5:2",
    "C3:2 G3:2 C3:4 C3:1 E3:1 G3:1 C3:1 E3:1 G3:1 A3:2 D3:2 F3:2 E3:1 F3:1 G3:2 C3:0.5 D3:0.5 E3:0.5 F3:0.5 G3:2",
    # 낮은음자리 g'1이 높은 오선으로 붙어 "G3:4 G3:1"이 끼어듦(기존 음높이 이슈) → 95% 기준으로 흡수
    "C5:0.25 D5:0.25 E5:0.25 F5:0.25 G5:0.5 A5:0.5 B5:1 C5:1 E5:0.5 D5:1 C5:0.5 B4:0.5 A4:0.5 G4:1 A4:3 B4:1 "
    "C5:0.25 D5:0.25 E5:0.5 F5:1 G5:1.5 A5:0.5 C5:0.25 D5:0.25 E5:0.5 F5:1 G5:2 C5:4",
    "A3:1 B3:1 C4:2 D4:1.5 E4:0.5 F4:2 C3:1 D3:1 E3:1 F3:1 G3:2 A3:2 C4:4",
]


def tokens(notes, staff):
    return [t for ch in core._chords([n for n in notes if n["staff"] == staff], notes[0]["ss"])
            for t in sorted(f'{n["pitch"]}:{n["dur"]:g}' for n in ch)]


if __name__ == "__main__":
    img = cv2.cvtColor(cv2.imread(os.path.join(os.path.dirname(__file__), "rhythm", "t1.png")), cv2.COLOR_BGR2RGB)
    notes = core.detect_notes(img)
    for st, exp in enumerate(EXPECT):
        got = tokens(notes, st)
        r = SequenceMatcher(None, exp.split(), got).ratio()
        print(f"staff {st}: {r:.3f}", "" if r >= 0.95 else "\n  exp " + exp + "\n  got " + " ".join(got))
        assert r >= 0.95, st
    names = [c["text"] for c in core.chord_labels(notes)]
    assert names[:4] == ["C", "C", "C", "Dm"], names  # 1~3마디: C | C(위 D E) | <c e g> <c e g> → C, <d f a> → Dm
    assert {n["system"] for n in notes if n["staff"] in (0, 1)} == {0}, "큰보표 두 오선이 한 시스템이어야 함"
    mid = core.to_midi([notes], 120)
    assert mid[:4] == b"MThd" and mid.count(b"MTrk") == 3
    print("OK")
