"""
악보 위에 계이름(고정도) 자동 삽입 프로토타입 v2
--------------------------------------------------
PDF/JPG/PNG 악보를 입력받아 음표 머리(notehead)를 검출하고,
오선 위치 + 음자리표(그랜드스태프 가정: 위=높은음자리, 아래=낮은음자리) + 조표를 이용해
실제 음이름을 계산한 뒤, 각 음표 위에 고정도 계이름(도레미파솔라시, 항상 C=도)을 써넣는다.

한계 (v1):
- 그랜드 스태프(피아노보) 전용: 각 시스템이 [높은음자리, 낮은음자리] 순서로 위→아래 배치된다고 가정
- 낱개 임시표(그 음에만 붙는 ♯♭♮)는 반영하지 못함 — 조표(key signature)만 반영
- 속이 빈 노트헤드(온음표/2분음표)는 별도 검출 로직 필요 (아직 미포함)

사용법:
    python name_on_notes_pitch.py input.pdf -o output.pdf --flats 4
    python name_on_notes_pitch.py input.pdf -o output.pdf --sharps 2
"""

import argparse
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FLAT_ORDER = ['B', 'E', 'A', 'D', 'G', 'C', 'F']
SHARP_ORDER = ['F', 'C', 'G', 'D', 'A', 'E', 'B']
FIXED_DO = {'C': '도', 'D': '레', 'E': '미', 'F': '파', 'G': '솔', 'A': '라', 'B': '시'}
LETTERS_ASC = ['C', 'D', 'E', 'F', 'G', 'A', 'B']  # 옥타브 내 오름차순


def load_pages(input_path, dpi=200):
    ext = os.path.splitext(input_path)[1].lower()
    if ext == ".pdf":
        from pdf2image import convert_from_path
        return convert_from_path(input_path, dpi=dpi)
    return [Image.open(input_path).convert("RGB")]


# ---------- 오선 검출 ----------

def detect_staff_lines(gray_np):
    """모든 오선의 y좌표(중심)를 검출해서 정렬된 리스트로 반환"""
    row_black_ratio = (gray_np < 128).mean(axis=1)
    threshold = 0.35
    staff_rows = np.where(row_black_ratio > threshold)[0]
    if len(staff_rows) == 0:
        return []

    groups = []
    current = [staff_rows[0]]
    for r in staff_rows[1:]:
        if r - current[-1] <= 2:
            current.append(r)
        else:
            groups.append(current)
            current = [r]
    groups.append(current)
    return [float(np.mean(g)) for g in groups]


def group_into_staves(line_centers):
    """검출된 오선 중심좌표 리스트를 5개씩 묶어서 스태프(보표) 단위로 그룹핑"""
    staves = []
    for i in range(0, len(line_centers) - 4, 5):
        group = line_centers[i:i + 5]
        # 5줄 간 간격이 서로 비슷한지 확인(노이즈 라인 제외)
        diffs = np.diff(group)
        if diffs.max() / max(diffs.min(), 1e-6) < 1.6:
            staves.append(group)
    return staves


def group_into_systems(staves):
    """스태프를 2개씩(높은음자리+낮은음자리) 묶어서 시스템으로 그룹핑"""
    systems = []
    i = 0
    while i + 1 < len(staves):
        systems.append({'treble': staves[i], 'bass': staves[i + 1]})
        i += 2
    return systems


# ---------- 음이름 계산 ----------

def step_to_note(step0_letter, step0_octave, step):
    idx0 = LETTERS_ASC.index(step0_letter)
    total = idx0 + step
    letter = LETTERS_ASC[total % 7]
    octave = step0_octave + total // 7
    return letter, octave


def find_first_barline_x(img_gray, y_top, y_bottom, x_search_start, x_search_end):
    """지정된 y범위(오선 시스템 높이) 안에서 세로로 길게 이어진 검은 선(바라인)의
    x좌표 중 가장 왼쪽 것을 찾는다. 음자리표/조표/박자표는 항상 첫 바라인보다 왼쪽에 있다."""
    band = img_gray[int(y_top):int(y_bottom), :]
    if band.shape[0] == 0:
        return None
    col_black_ratio = (band < 128).mean(axis=0)
    for x in range(int(x_search_start), min(int(x_search_end), len(col_black_ratio))):
        if col_black_ratio[x] > 0.85:
            return x
    return None





def find_staff_start_x(img_gray, y_line, x_max=400):
    """오선 한 줄의 y좌표에서 왼쪽부터 스캔해 실제로 선이 시작되는 x좌표를 찾는다."""
    row = img_gray[int(y_line), :x_max]
    dark = np.where(row < 128)[0]
    return int(dark[0]) if len(dark) else 0


def find_staff_end_x(img_gray, y_line):
    """오선 한 줄의 y좌표에서 오른쪽 끝까지 스캔해 선이 끝나는 x좌표를 찾는다."""
    row = img_gray[int(y_line), :]
    dark = np.where(row < 128)[0]
    return int(dark[-1]) if len(dark) else img_gray.shape[1] - 1


def find_all_barlines(img_gray, y_top, y_bottom, x_start, x_end):
    """지정 구간 안의 모든 바라인 x좌표(그룹핑된 중심값)를 왼쪽부터 정렬해 반환"""
    y_top, y_bottom = int(max(0, y_top)), int(min(img_gray.shape[0], y_bottom))
    band = img_gray[y_top:y_bottom, :]
    if band.shape[0] == 0:
        return []
    col_black_ratio = (band < 128).mean(axis=0)
    cols = [x for x in range(int(x_start), int(min(x_end, len(col_black_ratio))))
            if col_black_ratio[x] > 0.85]
    if not cols:
        return []
    groups = []
    cur = [cols[0]]
    for c in cols[1:]:
        if c - cur[-1] <= 3:
            cur.append(c)
        else:
            groups.append(cur)
            cur = [c]
    groups.append(cur)
    return [int(np.mean(g)) for g in groups]


def exclude_before_first_barline(noteheads, systems, img_gray, spacing):
    filtered = []
    barline_x_cache = {}
    for idx, sysm in enumerate(systems):
        y_top = sysm['treble'][0] - spacing
        y_bottom = sysm['bass'][-1] + spacing
        start_x = find_staff_start_x(img_gray, sysm['treble'][2])  # 오선 중간 줄 기준
        barline_x_cache[idx] = (y_top, y_bottom, start_x)

    for (x, y, r) in noteheads:
        # 해당 노트헤드가 속한 시스템 찾기
        best_idx, best_dist = None, 1e9
        for idx, sysm in enumerate(systems):
            mid = (sysm['treble'][0] + sysm['bass'][-1]) / 2
            d = abs(y - mid)
            if d < best_dist:
                best_dist, best_idx = d, idx
        if best_idx is None:
            filtered.append((x, y, r))
            continue

        y_top, y_bottom, start_x = barline_x_cache[best_idx]
        # 음자리표+조표(+첫 시스템의 경우 박자표)가 차지하는 고정 폭만큼만 제외
        # (바라인 기준이 아니라, 오선 시작점 기준 고정 여유폭 사용 — 첫 마디 음표까지
        #  잘라내는 문제를 피하기 위함)
        clef_zone_end = start_x + spacing * 15
        if x > clef_zone_end:
            filtered.append((x, y, r))
    return filtered


def y_to_note(y, staff_lines, clef):
    """오선 5개 중심좌표(위→아래)와 y좌표로 음이름(letter, octave) 계산"""
    spacing = (staff_lines[-1] - staff_lines[0]) / 4.0  # 줄 간 간격
    half = spacing / 2.0
    bottom_line_y = staff_lines[-1]
    # step: 아래에서 위로 갈수록 +1 (반칸 단위), y는 위로 갈수록 작아짐
    step = round((bottom_line_y - y) / half)
    if clef == 'treble':
        return step_to_note('E', 4, step)
    else:  # bass
        return step_to_note('G', 2, step)


def apply_key_signature(letter, flats=0, sharps=0):
    if flats > 0 and letter in FLAT_ORDER[:flats]:
        return FIXED_DO[letter] + '♭'
    if sharps > 0 and letter in SHARP_ORDER[:sharps]:
        return FIXED_DO[letter] + '♯'
    return FIXED_DO[letter]


# ---------- 코드(화음) 추정 ----------

NATURAL_SEMITONE = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
FLAT_ROOT_NAMES = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']
SHARP_ROOT_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

CHORD_TEMPLATES = [
    ('', [0, 4, 7]),        # major
    ('m', [0, 3, 7]),       # minor
    ('dim', [0, 3, 6]),
    ('aug', [0, 4, 8]),
    ('sus4', [0, 5, 7]),
    ('sus2', [0, 2, 7]),
    ('7', [0, 4, 7, 10]),
    ('maj7', [0, 4, 7, 11]),
    ('m7', [0, 3, 7, 10]),
]


def letter_to_semitone(letter, flats=0, sharps=0):
    st = NATURAL_SEMITONE[letter]
    if flats > 0 and letter in FLAT_ORDER[:flats]:
        st -= 1
    if sharps > 0 and letter in SHARP_ORDER[:sharps]:
        st += 1
    return st % 12


def guess_chord(pitch_classes, flats=0, sharps=0):
    """음 집합(피치클래스 set)으로 가장 그럴듯한 코드명을 추정 (참고용 근사치)"""
    if not pitch_classes:
        return None
    names = FLAT_ROOT_NAMES if flats >= sharps else SHARP_ROOT_NAMES
    best = None  # (score, label)
    for root in range(12):
        for suffix, intervals in CHORD_TEMPLATES:
            template = {(root + iv) % 12 for iv in intervals}
            matched = len(pitch_classes & template)
            extra = len(pitch_classes - template)
            missing = len(template - pitch_classes)
            score = matched - 0.5 * extra - 0.3 * missing
            if best is None or score > best[0]:
                best = (score, f"{names[root]}{suffix}")
    return best[1] if best else None


# ---------- 노트헤드 검출 (v1과 동일) ----------

def detect_noteheads(pil_img, staff_spacing=None):
    img_np = np.array(pil_img.convert("L"))
    _, binary = cv2.threshold(img_np, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    line_centers = detect_staff_lines(img_np)
    if staff_spacing is None:
        diffs = np.diff(line_centers) if len(line_centers) > 1 else [14]
        small = [d for d in diffs if d < np.median(diffs) * 2.5] if len(diffs) else [14]
        staff_spacing = max(4, int(np.median(small))) if small else 14

    nh_h = max(3, int(round(staff_spacing * 0.85)))
    nh_w = max(3, int(round(staff_spacing * 1.05)))

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (nh_w, nh_h))
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_area = (nh_w * nh_h) * 0.25
    max_area = (nh_w * nh_h) * 4.0

    noteheads = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < min_area or area > max_area:
            continue
        (x, y), r = cv2.minEnclosingCircle(c)
        noteheads.append((int(x), int(y), int(max(nh_w, nh_h) / 2)))

    # ---- 빈 노트헤드(온음표/2분음표) 검출: 구멍(hole) 기반 ----
    hollow = detect_hollow_noteheads(binary, nh_w, nh_h)
    noteheads.extend(hollow)

    return noteheads, staff_spacing, line_centers


def detect_hollow_noteheads(binary, nh_w, nh_h):
    """오선/빔에 맞닿아 하나의 큰 잉크 덩어리에 포함된 속이 빈 노트헤드를
    '구멍(hole)' 윤곽선으로 검출한다. 오선이 타원 중앙을 가로지르면 구멍이
    위/아래로 쪼개지므로, 인접한 구멍들을 클러스터링해서 하나로 합친다."""
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return []
    hierarchy = hierarchy[0]

    holes = []
    for i, c in enumerate(contours):
        if hierarchy[i][3] == -1:  # 최상위(구멍이 아닌 바깥 윤곽)는 제외
            continue
        x, y, w, h = cv2.boundingRect(c)
        if w < nh_w * 0.5 or w > nh_w * 1.7:
            continue
        if h < 2 or h > nh_h * 1.4:
            continue
        holes.append([x, y, w, h])

    holes.sort(key=lambda b: (b[0], b[1]))
    used = [False] * len(holes)
    clusters = []
    for i in range(len(holes)):
        if used[i]:
            continue
        group = [holes[i]]
        used[i] = True
        changed = True
        while changed:
            changed = False
            gxs = min(b[0] for b in group)
            gys = min(b[1] for b in group)
            gxe = max(b[0] + b[2] for b in group)
            gye = max(b[1] + b[3] for b in group)
            for j in range(len(holes)):
                if used[j]:
                    continue
                x2, y2, w2, h2 = holes[j]
                x_overlap = min(gxe, x2 + w2) - max(gxs, x2)
                if x_overlap > 0.3 * min(w2, gxe - gxs):
                    gap = max(0, max(gys, y2) - min(gye, y2 + h2))
                    if gap < 6:
                        group.append(holes[j])
                        used[j] = True
                        changed = True

        xs = [b[0] for b in group]; ys = [b[1] for b in group]
        xe = [b[0] + b[2] for b in group]; ye = [b[1] + b[3] for b in group]
        cx = (min(xs) + max(xe)) / 2
        cy = (min(ys) + max(ye)) / 2
        cw = max(xe) - min(xs)
        ch = max(ye) - min(ys)
        if ch < nh_h * 0.5 or ch > nh_h * 1.6:
            continue
        if cw < nh_w * 0.5 or cw > nh_w * 1.6:
            continue
        clusters.append((int(cx), int(cy), int(max(cw, ch) / 2)))

    return clusters


# ---------- 라벨 그리기 ----------

def get_font(size):
    candidates = [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


TREBLE_COLOR = (200, 30, 30)   # 빨강
BASS_COLOR = (30, 60, 200)     # 파랑
CHORD_COLOR = (20, 130, 40)    # 초록 (코드는 참고용이라 다른 색으로 구분)


def draw_label_with_bg(draw, x, y, text, font, text_color, pad=2):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx, ty = x - tw / 2, y
    # 흰 배경 사각형을 먼저 그려서 가독성 확보
    draw.rectangle(
        [tx - pad, ty - pad, tx + tw + pad, ty + th + pad],
        fill=(255, 255, 255)
    )
    draw.text((tx, ty), text, fill=text_color, font=font)


def process(input_path, output_path, flats=0, sharps=0, dpi=200, debug=False):
    pages = load_pages(input_path, dpi=dpi)
    out_pages = []
    total = 0
    unmatched = 0
    total_chords = 0

    for pi, page in enumerate(pages):
        noteheads, spacing, line_centers = detect_noteheads(page)
        staves = group_into_staves(line_centers)
        systems = group_into_systems(staves)
        img_np_full = np.array(page.convert("L"))

        # 오선 시스템에서 너무 멀리 떨어진 검출(제목/텍스트 등 오탐)은 제외
        if systems:
            margin = spacing * 6  # 레저 라인 여유
            valid_ranges = [(s['treble'][0] - margin, s['bass'][-1] + margin) for s in systems]
            noteheads = [
                nh for nh in noteheads
                if any(lo <= nh[1] <= hi for (lo, hi) in valid_ranges)
            ]
            # 각 시스템의 음자리표+조표 구역은 제외
            noteheads = exclude_before_first_barline(noteheads, systems, img_np_full, spacing)

        img = page.convert("RGB").copy()
        draw = ImageDraw.Draw(img)
        font_size = max(8, int(spacing * 0.9))
        font = get_font(font_size)
        chord_font = get_font(int(font_size * 1.05))

        # 시스템별 마디(바라인) 구간 미리 계산 + 코드 추정을 위한 피치클래스 수집 버킷
        system_measures = []       # [[ (x_left,x_right), ... ], ...]  시스템별 마디 리스트
        measure_pitch_sets = []    # [[set(), set(), ...], ...]        시스템별 마디별 피치클래스 집합
        for sysm in systems:
            start_x = find_staff_start_x(img_np_full, sysm['treble'][2])
            end_x = find_staff_end_x(img_np_full, sysm['treble'][2])
            y_top = sysm['treble'][0] - spacing
            y_bottom = sysm['bass'][-1] + spacing
            clef_end = start_x + spacing * 15
            barlines = find_all_barlines(img_np_full, y_top, y_bottom, clef_end, end_x + 2)
            bounds = [clef_end] + barlines
            if bounds[-1] < end_x - spacing:
                bounds.append(end_x)
            measures = list(zip(bounds[:-1], bounds[1:]))
            system_measures.append(measures)
            measure_pitch_sets.append([set() for _ in measures])

        def find_measure_idx(sys_idx, x):
            for mi, (lo, hi) in enumerate(system_measures[sys_idx]):
                if lo <= x <= hi:
                    return mi
            return len(system_measures[sys_idx]) - 1 if system_measures[sys_idx] else None

        # ---- 1차: 음이름 계산 + 라벨 그리기 + 코드용 피치클래스 수집 ----
        page_matched = 0
        note_records = []
        for (x, y, r) in noteheads:
            best_sys_idx, best_dist = None, 1e9
            for si, sysm in enumerate(systems):
                mid = (sysm['treble'][0] + sysm['bass'][-1]) / 2
                d = abs(y - mid)
                if d < best_dist:
                    best_dist, best_sys_idx = d, si
            if best_sys_idx is None:
                unmatched += 1
                continue
            sysm = systems[best_sys_idx]

            treble_mid = (sysm['treble'][0] + sysm['treble'][-1]) / 2
            bass_mid = (sysm['bass'][0] + sysm['bass'][-1]) / 2
            if abs(y - treble_mid) <= abs(y - bass_mid):
                clef, lines = 'treble', sysm['treble']
            else:
                clef, lines = 'bass', sysm['bass']

            letter, octave = y_to_note(y, lines, clef)
            label = apply_key_signature(letter, flats=flats, sharps=sharps)
            color = TREBLE_COLOR if clef == 'treble' else BASS_COLOR

            draw_label_with_bg(draw, x, y - r - font_size * 1.5, label, font, color)
            if debug:
                draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(0, 120, 255))

            page_matched += 1

            mi = find_measure_idx(best_sys_idx, x)
            if mi is not None:
                st = letter_to_semitone(letter, flats=flats, sharps=sharps)
                measure_pitch_sets[best_sys_idx][mi].add(st)

        # ---- 2차: 마디별 코드 추정 + 표시 (참고용 근사치) ----
        page_chords = 0
        for si, sysm in enumerate(systems):
            top_y = sysm['treble'][0] - spacing * 2.6
            for mi, (lo, hi) in enumerate(system_measures[si]):
                pcs = measure_pitch_sets[si][mi]
                chord = guess_chord(pcs, flats=flats, sharps=sharps)
                if chord is None:
                    continue
                cx = (lo + hi) / 2
                draw_label_with_bg(draw, cx, top_y, chord, chord_font, CHORD_COLOR)
                page_chords += 1

        total += page_matched
        total_chords += page_chords
        out_pages.append(img)
        print(f"  [{pi+1}/{len(pages)}] 오선간격={spacing}px, 시스템={len(systems)}개, "
              f"음이름={page_matched}개, 코드={page_chords}개")

    ext = os.path.splitext(output_path)[1].lower()
    if ext == ".pdf":
        out_pages[0].save(output_path, save_all=True, append_images=out_pages[1:])
    else:
        out_pages[0].save(output_path)

    print(f"완료: 음이름 {total}개, 코드(참고용) {total_chords}개 부착 (매칭 실패 {unmatched}개) -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="악보 위 음표마다 고정도 계이름 삽입")
    parser.add_argument("input")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--flats", type=int, default=0, help="조표의 ♭ 개수")
    parser.add_argument("--sharps", type=int, default=0, help="조표의 ♯ 개수")
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    process(args.input, args.output, flats=args.flats, sharps=args.sharps, dpi=args.dpi, debug=args.debug)
