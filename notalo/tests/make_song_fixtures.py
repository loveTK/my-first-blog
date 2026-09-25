"""songs/<slug>.ly → tests/fixtures/<slug>.png + .json (정확도 픽스처). 정답은 LilyPond가 찍은 음표머리 좌표·음높이 — 검출기 안 씀.
NoteHead.output-attributes로 SVG에 (계이름, 변화표, 옥타브, 머리 중심 오프셋)을 찍고, 같은 악보의 200dpi PNG 좌표계로 옮긴다.
실행: py -3 tests/make_song_fixtures.py [slug ...]   (lilypond 필요 — 개발 PC에서 돌리고 산출물을 커밋)"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from songs import SONGS  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SONGS_DIR = os.path.join(ROOT, "songs")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
LETTERS = "CDEFGAB"
ATTR = r"""\layout { \context { \Score \override NoteHead.output-attributes = #(lambda (g)
  (let ((p (ly:event-property (ly:grob-property g 'cause) 'pitch)) (x (ly:grob-extent g g X)) (y (ly:grob-extent g g Y)))
    (list (cons 'data-note (format #f "~a ~a ~a ~a ~a" (ly:pitch-notename p) (ly:pitch-alteration p) (ly:pitch-octave p)
                                   (/ (+ (car x) (cdr x)) 2) (/ (+ (car y) (cdr y)) 2)))))) } }
"""
NOTE_RE = re.compile(r'<g data-note="([^"]*)">(?:\s*<a[^>]*>)?\s*<g transform="translate\(([^,]+), ([^)]+)\)">')


def pitch_str(name, alt, octv):
    alt = Fraction(alt)
    return f"{LETTERS[int(name)]}{'#' if alt > 0 else 'b' if alt < 0 else ''}{4 + int(octv)}"


def build(slug):
    with tempfile.TemporaryDirectory() as tmp:
        ly = os.path.join(tmp, "fx.ly")  # 곡과 다른 이름이어야 함(같으면 자기 자신을 include해서 멈춤)
        with open(ly, "w", encoding="utf-8") as f:
            f.write('\\version "2.22.0"\n' + ATTR + f'\\include "{os.path.join(SONGS_DIR, slug + ".ly")}"\n')
        base = os.path.join(tmp, "out")
        for fmt in (["-dresolution=200", "--png"], ["-dbackend=svg"]):
            subprocess.run(["lilypond", "-I", SONGS_DIR, *fmt, "-o", base, ly], check=True, capture_output=True)
        pngs, svgs = glob.glob(base + "*.png"), glob.glob(base + "*.svg")
        assert len(pngs) == 1 and len(svgs) == 1, (slug, "한 페이지 곡만", pngs, svgs)  # ponytail: 여러 페이지면 페이지마다 픽스처로 쪼개면 됨
        svg = open(svgs[0], encoding="utf-8").read()
        W, H = Image.open(pngs[0]).size
        x0, y0, w, h = map(float, re.search(r'viewBox="([^"]+)"', svg).group(1).split())
        notes = []
        for m in NOTE_RE.finditer(svg):
            name, alt, octv, ex, ey = m.group(1).split()
            tx, ty = float(m.group(2)), float(m.group(3))
            cx, cy = tx + float(Fraction(ex)), ty - float(Fraction(ey))  # LilyPond는 y가 위로, SVG는 아래로
            notes.append({"x": round((cx - x0) * W / w), "y": round((cy - y0) * H / h), "pitch": pitch_str(name, alt, octv)})
        assert notes, slug
        os.makedirs(OUT, exist_ok=True)
        shutil.copy(pngs[0], os.path.join(OUT, slug + ".png"))
        json.dump({"notes": notes}, open(os.path.join(OUT, slug + ".json"), "w", encoding="utf-8"))
        print(f"{slug}: {len(notes)} notes, {W}x{H}")


if __name__ == "__main__":
    for s in (sys.argv[1:] or SONGS):
        build(s)
