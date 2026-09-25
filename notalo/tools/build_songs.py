"""songs/<slug>.ly → static/songs/<slug>.png(글자 붙은 악보) + .mid + .json(마디별 오른손 글자·코드).
사용: python tools/build_songs.py [slug ...]   (lilypond 필요 — 서버가 아니라 개발 PC에서 돌리고 산출물을 커밋)"""
import json
import os
import subprocess
import sys
import tempfile

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import core  # noqa: E402
import render  # noqa: E402
from songs import SONGS  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "static", "songs")


def bars_of(notes):
    """(system, bar) 순으로 마디 묶음 → [{"n", "rh": "B B B", "chord": "G"}]. 마디 번호는 첫 오선(오른손) 기준으로 시스템을 이어 셈.
    왼손 음은 마디 번호가 오선마다 따로 세어져 어긋날 수 있어 x좌표로 오른손 마디 구간에 넣음(core.chord_labels와 같은 방식)."""
    import bisect
    out, n = [], 0
    ss = notes[0]["ss"]
    for sysno in sorted({x["system"] for x in notes}):
        sysn = [x for x in notes if x["system"] == sysno]
        top = min(x["staff"] for x in sysn)
        bars = sorted({x["bar"] for x in sysn if x["staff"] == top})
        starts = [min(x["x"] for x in sysn if x["staff"] == top and x["bar"] == b) for b in bars]
        for i, bar in enumerate(bars):
            rh = sorted((x for x in sysn if x["staff"] == top and x["bar"] == bar), key=lambda x: x["x"])
            both = [x for x in sysn if max(bisect.bisect_right(starts, x["x"] + 0.5 * ss) - 1, 0) == i]
            n += 1
            out.append({"n": n, "rh": " ".join(core.note_name(x["pitch"], "en") for x in rh), "chord": core.chord_name(both) or ""})
    return out


def build(slug):
    meta = SONGS[slug]
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["lilypond", "-dresolution=200", "--png", "-o", os.path.join(tmp, slug), os.path.join(ROOT, "songs", slug + ".ly")], check=True, capture_output=True)
        page = cv2.cvtColor(cv2.imread(os.path.join(tmp, slug + ".png")), cv2.COLOR_BGR2RGB)
    notes = core.detect_notes(page)
    assert notes, slug
    img = render.overlay(page, core.place_labels(notes, "en", "below") + core.chord_labels(notes))
    a = np.array(img)
    ys, xs = np.where((a < 245).any(axis=2))
    img = img.crop((max(xs.min() - 40, 0), max(ys.min() - 40, 0), min(xs.max() + 40, a.shape[1]), min(ys.max() + 40, a.shape[0])))
    os.makedirs(OUT, exist_ok=True)
    img.save(os.path.join(OUT, slug + ".png"), optimize=True)
    with open(os.path.join(OUT, slug + ".mid"), "wb") as f:
        f.write(core.to_midi([notes], meta["bpm"]))
    bars = bars_of(notes)
    json.dump({"w": img.size[0], "h": img.size[1], "notes": len(notes), "bars": bars}, open(os.path.join(OUT, slug + ".json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"{slug}: {len(notes)} notes, {len(bars)} bars, {img.size[0]}x{img.size[1]}")
    for b in bars:
        print(f"  {b['n']:>2} {b['chord']:<6} {b['rh']}")


if __name__ == "__main__":
    for s in (sys.argv[1:] or SONGS):
        build(s)
