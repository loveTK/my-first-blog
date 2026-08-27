"""
악보 위에 계이름(고정도) 자동 삽입 프로토타입 v2
--------------------------------------------------
PDF/JPG/PNG 악보를 입력받아 음표 머리(notehead)를 검출하고,
오선 위치 + 음자리표(그랜드스태프 가정: 위=높은음자리, 아래=낮은음자리) + 조표를 이용해
실제 음이름을 계산한 뒤, 각 음표 위에 고정도 계이름(도레미파솔라시, 항상 C=도)을 써넣는다.

음표 길이(리듬):
- 스템 유무 + 노트헤드가 속이 찬지/빈지 + 스템 끝의 플래그(꼬리)/빔 존재 여부로
  온음표/2분음표/4분음표/"8분음표 이하"를 판별은 하지만, 기본값은 표시하지 않는다.
  --show-duration을 줘야 라벨 옆에 (온)/(2)/없음/(8)로 표시한다.
- 8분/16분/32분음표는 서로 구분하지 않고 전부 "(8)"로 뭉뚱그린다. 플래그 개수를
  세어 세분해보려 했으나, 이 해상도에서는 신뢰도가 떨어져(다른 기호 자동검출
  시도들과 동일한 문제) 포함하지 않았다.
- 화음(노트헤드 여러 개가 스템 하나를 공유)은 스템이 위/아래 양쪽으로 길게
  이어지는데, 8분음표 플래그의 곡선이 만드는 가짜 구멍도 똑같은 모양이라 한때
  이를 걸러내는 필터를 넣었었다. 그 필터가 화음의 가운데/아래쪽 음까지 통째로
  지워버리는 게 더 심각한 문제라 필터 자체를 제거했다 — 그 결과 8분음표 이하의
  플래그가 드물게 별도 노트헤드로 오검출될 수 있다(화음을 잃는 것보다는 나은
  트레이드오프).

한계 (v1):
- 그랜드 스태프(피아노보) 전용: 각 시스템이 [높은음자리, 낮은음자리] 순서로 위→아래 배치된다고 가정
- 낱개 임시표(그 음에만 붙는 ♯♭♮)는 반영하지 못함 — 조표(key signature)만 반영
- 보표 중간에 음자리표가 바뀌는 표기(레저 라인 절약용)는 인식하지 못함
  (템플릿 매칭으로 시도했으나 저해상도에서 오탐/미탐이 많아 폐기)
- 조표는 자동 검출하지 않음: 곡 중간 조표 변경은 --key-map으로 수동 지정
  (자동 검출도 시도했으나 200dpi 기준 임시표가 너무 작아 개수/모양 구분 불가로 폐기)
- 잔음표/꾸밈음(장식음, cue-size grace note)은 정식 노트헤드보다 작아서 놓칠 수 있음
  (노트헤드 검출 커널이 표준 크기 기준이라 이보다 작은 잉크 덩어리는 모폴로지
  open 단계에서 지워짐). 더 작은 커널로 2차 검출을 시도했으나, 8분음표 빔(beam)의
  두꺼운 부분이나 음자리표 곡선에서도 비슷한 크기의 가짜 블롭이 다수 검출되어
  (실제 누락된 꾸밈음보다 오탐이 더 많음) 폐기 — 단 한 줄에 1~3개 정도 발생하는
  수준으로 드묾

엔진(--engine):
- cv(기본): 이 파일 자체의 OpenCV 노트헤드 검출 + 오선 위치 기반 음이름 계산.
  꾸밈음 누락, 조표 수동 지정 필요 등 위 한계를 그대로 가짐.
- audiveris: 실제 OMR 엔진인 Audiveris(별도 설치 필요, AUDIVERIS_BIN 참고)로
  음표를 검출해 MusicXML로 뽑아낸 뒤, 그 피치/박자 정보를 이 스크립트의
  라벨 배치 로직에 그대로 얹는다. cv 엔진의 약점이던 꾸밈음 누락, 조표 자동
  미검출, 낱개 임시표 미반영이 모두 해결됨(smallHeads 스위치를 켜서 꾸밈음도
  검출, 라벨은 Audiveris가 음표마다 계산한 <alter> 값을 그대로 사용 — 조표뿐
  아니라 낱개 임시표까지 반영됨). 단, 노트헤드의 화면 좌표 자체는
  Audiveris가 아니라 이 스크립트가 직접 검출한 오선/마디 위치 + 음이름을 오선
  상 위치로 역산해서 계산한다(Audiveris 좌표계를 그대로 못 믿어서가 아니라,
  라벨 배치용 좌표계를 cv 엔진과 통일하기 위함). 한 마디 안에 여러 성부가
  겹치는 경우 시간축(divisions) 기준으로 x를 보간하므로 얼추 맞지만 완벽하진
  않음. --flats/--sharps/--key-map은 audiveris 엔진에서는 무시된다(조표를
  Audiveris가 직접 인식하므로).

계이름 언어(--lang):
- ko(기본): 도레미파솔라시 / solfege: Do Re Mi Fa Sol La Si / letter: C D E F G A B
- ja: ド レ ミ ファ ソ ラ シ (일본어 가타카나 솔페이지)
- 독일식(H/B 임시표 표기 등 반음별 고유 이름 체계)은 별도 명명 규칙이 필요해 포함하지 않았다.

출력 파일명:
- -o를 안 주면 입력 파일과 같은 위치에 "원본파일명_note.확장자"로 자동 저장한다.

사용법:
    python name_on_notes_pitch.py input.pdf --flats 4
    python name_on_notes_pitch.py input.pdf --sharps 2 --lang solfege
    python name_on_notes_pitch.py input.pdf -o output.pdf --lang ja
    # 곡 중간 조표 변경: 5번째 시스템부터 ♯3개, 8번째 시스템부터 ♭5개
    python name_on_notes_pitch.py input.pdf --key-map "5:sharps=3,8:flats=5"
"""

import argparse
import functools
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FLAT_ORDER = ['B', 'E', 'A', 'D', 'G', 'C', 'F']
SHARP_ORDER = ['F', 'C', 'G', 'D', 'A', 'E', 'B']
LETTERS_ASC = ['C', 'D', 'E', 'F', 'G', 'A', 'B']  # 옥타브 내 오름차순

NOTE_NAMES = {
    'ko': {'C': '도', 'D': '레', 'E': '미', 'F': '파', 'G': '솔', 'A': '라', 'B': '시'},
    'solfege': {'C': 'Do', 'D': 'Re', 'E': 'Mi', 'F': 'Fa', 'G': 'Sol', 'A': 'La', 'B': 'Si'},
    'letter': {'C': 'C', 'D': 'D', 'E': 'E', 'F': 'F', 'G': 'G', 'A': 'A', 'B': 'B'},
    'ja': {'C': 'ド', 'D': 'レ', 'E': 'ミ', 'F': 'ファ', 'G': 'ソ', 'A': 'ラ', 'B': 'シ'},
}


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
    """검출된 오선 중심좌표 리스트를 5개씩 묶어서 스태프(보표) 단위로 그룹핑.

    line_centers에는 제목/가사/셈여림 등에서 잡힌 노이즈 라인이 실제 오선 앞뒤에
    섞여 들어올 수 있다. 고정 보폭(5칸씩)으로만 훑으면 노이즈 라인 하나 때문에
    이후 모든 그룹의 정렬이 어긋나 버리므로, 5줄 묶음이 유효하지 않으면 한 칸만
    건너뛰고 재동기화를 시도한다."""
    staves = []
    i = 0
    n = len(line_centers)
    while i <= n - 5:
        group = line_centers[i:i + 5]
        # 5줄 간 간격이 서로 비슷한지 확인(노이즈 라인 제외)
        diffs = np.diff(group)
        if diffs.min() > 0 and diffs.max() / diffs.min() < 1.6:
            staves.append(group)
            i += 5
        else:
            i += 1
    return staves


def group_into_systems(staves):
    """스태프를 2개씩(높은음자리+낮은음자리) 묶어서 시스템으로 그룹핑.

    그냥 순서대로 2개씩 묶으면, 스태프 하나가 통째로 검출에서 빠졌을 때
    그 뒤 모든 스태프가 한 칸씩 밀려 서로 다른 시스템의 높은음자리/
    낮은음자리끼리 잘못 묶인다 — 그러면 음이름이 조용히 다 틀어지는데,
    이건 라벨이 아예 없는 것보다 훨씬 나쁘다(틀린 정보를 맞는 것처럼 보여줌).
    같은 시스템 안 높은음자리-낮은음자리 간격은 시스템 간 간격보다 뚜렷이
    좁으므로(실측: 줄간격의 4~7배 vs 9배 이상), 그 간격으로 실제로 붙어있는
    스태프끼리만 묶는다. 다음 스태프와 안 붙어 있으면(간격이 너무 넓으면)
    그 스태프는 짝을 잃은 것으로 보고 버린다."""
    systems = []
    i = 0
    n = len(staves)
    while i + 1 < n:
        spacing = (staves[i][-1] - staves[i][0]) / 4.0
        gap = staves[i + 1][0] - staves[i][-1]
        if spacing > 0 and gap / spacing <= 8.0:
            systems.append({'treble': staves[i], 'bass': staves[i + 1]})
            i += 2
        else:
            i += 1
    return systems


# ---------- 음이름 계산 ----------

def step_to_note(step0_letter, step0_octave, step):
    idx0 = LETTERS_ASC.index(step0_letter)
    total = idx0 + step
    letter = LETTERS_ASC[total % 7]
    octave = step0_octave + total // 7
    return letter, octave



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


def parse_key_map(spec):
    """--key-map "5:sharps=3,8:flats=5" 형태의 문자열을
    {시스템전역번호: (flats, sharps)} 딕셔너리로 파싱.
    시스템 전역번호는 문서 전체를 통틀어 1부터 센 시스템(그랜드스태프) 순번이며,
    지정된 번호부터 다음 지정 전까지 그 조표가 적용된다."""
    mapping = {}
    if not spec:
        return mapping
    for part in spec.split(','):
        part = part.strip()
        if not part:
            continue
        if ':' not in part or '=' not in part:
            raise ValueError(f"--key-map 형식 오류: '{part}' (예: 5:sharps=3)")
        sys_str, kv = part.split(':', 1)
        key, val = kv.split('=', 1)
        sys_num = int(sys_str.strip())
        key = key.strip()
        val = int(val.strip())
        if key == 'sharps':
            mapping[sys_num] = (0, val)
        elif key == 'flats':
            mapping[sys_num] = (val, 0)
        else:
            raise ValueError(f"--key-map 항목은 flats 또는 sharps만 지정 가능: '{part}'")
    return mapping


def effective_key(key_map, default_flats, default_sharps, sys_num):
    """전역 시스템번호 sys_num 시점에 적용되는 (flats, sharps)를 key_map에서 조회.
    sys_num 이하인 항목 중 가장 큰 번호의 값을 쓰고, 없으면 기본값을 쓴다."""
    flats, sharps = default_flats, default_sharps
    for k in sorted(key_map):
        if k <= sys_num:
            flats, sharps = key_map[k]
        else:
            break
    return flats, sharps


def apply_key_signature(letter, flats=0, sharps=0, lang='ko'):
    names = NOTE_NAMES[lang]
    if flats > 0 and letter in FLAT_ORDER[:flats]:
        return names[letter] + '♭'
    if sharps > 0 and letter in SHARP_ORDER[:sharps]:
        return names[letter] + '♯'
    return names[letter]


# ---------- 음표 길이(리듬) 판별 ----------

def find_stem(binary, x, y, r, spacing):
    """노트헤드에 붙은 스템(막대)을 찾는다. 노트헤드 중심 근처 작은 박스 안의
    모든 어두운 점에서 위/아래로 연속된 어두운 길이를 재서 최댓값을 취한다
    (스템이 정확히 중심 바로 위/아래가 아니라 오른쪽/왼쪽 가장자리에 붙기 때문에
    한 지점만 스캔하면 놓치기 쉽다).
    반환: {'up': (길이, dx, dy), 'down': (길이, dx, dy)}"""
    H, W = binary.shape
    stem_search = int(spacing * 4.5)
    dx_range = range(-int(spacing * 0.9), int(spacing * 0.9) + 1)
    dy_range = range(-int(r * 0.8), int(r * 0.8) + 1)
    best_up = (0, 0, 0)
    best_down = (0, 0, 0)
    for dx in dx_range:
        xx = x + dx
        if xx < 0 or xx >= W:
            continue
        for dy in dy_range:
            y0 = y + dy
            if y0 < 0 or y0 >= H or binary[y0, xx] == 0:
                continue
            n, yy = 0, y0
            while yy >= 0 and yy > y0 - stem_search and binary[yy, xx] > 0:
                n += 1
                yy -= 1
            if n > best_up[0]:
                best_up = (n, dx, dy)
            n, yy = 0, y0
            while yy < H and yy < y0 + stem_search and binary[yy, xx] > 0:
                n += 1
                yy += 1
            if n > best_down[0]:
                best_down = (n, dx, dy)
    return {'up': best_up, 'down': best_down}


def classify_duration(binary, x, y, r, spacing, stem, is_hollow, staff_line_ys=()):
    """스템 유무 + 속이 찬/빈 노트헤드 + 스템 끝의 플래그(꼬리)/빔 존재 여부로
    음표 길이를 대략 분류한다.
    반환: 'whole'(온음표) | 'half'(2분음표) | 'quarter'(4분음표) | 'short'(8분음표 이하)
    'short'는 8분/16분/32분을 세분하지 않는다 — 플래그 개수 세기는 이 해상도에서
    신뢰도가 떨어져(다른 기호 자동검출 시도들과 동일한 문제) 포함하지 않았다.

    is_hollow는 호출 쪽(detect_noteheads가 만든 hollow_set)에서 미리 판정된 값을
    받는다 — 오선이 노트헤드 중앙을 가로지르면 그 지점만 픽셀로 다시 샘플링할
    경우 오선 자체의 어두운 픽셀 때문에 판정이 뒤집히기 때문이다.
    staff_line_ys는 같은 이유로 플래그 폭을 잴 때 오선이 지나가는 행을 건너뛰기
    위해 쓴다 — 오선은 그 행 전체가 어두워서, 건너뛰지 않으면 플래그의 폭으로
    오인된다."""
    stem_len = max(stem['up'][0], stem['down'][0])
    has_stem = stem_len > spacing * 2.2

    if not has_stem:
        return 'whole' if is_hollow else 'quarter'
    if is_hollow:
        return 'half'

    direction, (length, dx, dy) = (
        ('up', stem['up']) if stem['up'][0] >= stem['down'][0] else ('down', stem['down'])
    )
    tip_x = x + dx
    tip_y = (y + dy - length) if direction == 'up' else (y + dy + length)
    span = int(spacing * 1.6)
    max_width = 0
    half_win = int(spacing)
    for t in range(span):
        yy = tip_y + t if direction == 'up' else tip_y - t
        if yy < 0 or yy >= binary.shape[0]:
            continue
        if any(abs(yy - ly) <= 1 for ly in staff_line_ys):
            continue  # 오선이 지나가는 행은 폭 측정에서 제외
        x0, x1 = max(0, tip_x - half_win), tip_x + half_win
        row = binary[yy, x0:x1]
        center = tip_x - x0
        if center < 0 or center >= len(row) or row[center] == 0:
            continue
        w, i = 1, center - 1
        while i >= 0 and row[i] > 0:
            w += 1
            i -= 1
        i = center + 1
        while i < len(row) and row[i] > 0:
            w += 1
            i += 1
        max_width = max(max_width, w)

    return 'short' if max_width > spacing * 0.6 else 'quarter'


DURATION_SUFFIX = {'whole': '(온)', 'half': '(2)', 'quarter': '', 'short': '(8)'}


# ---------- 노트헤드 검출 (v1과 동일) ----------

def guess_staff_spacing(line_centers):
    """검출된 오선 중심좌표들의 간격(줄 간격) 중앙값을 추정한다."""
    diffs = np.diff(line_centers) if len(line_centers) > 1 else [14]
    small = [d for d in diffs if d < np.median(diffs) * 2.5] if len(diffs) else [14]
    return max(4, int(np.median(small))) if small else 14


def detect_noteheads(pil_img, staff_spacing=None):
    img_np = np.array(pil_img.convert("L"))
    _, binary = cv2.threshold(img_np, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    line_centers = detect_staff_lines(img_np)
    if staff_spacing is None:
        staff_spacing = guess_staff_spacing(line_centers)

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
    # 오선이 노트헤드 중앙을 가로지르면 그 자리만 픽셀 샘플링으로는 속이
    # 찬/빈 판정이 흔들리므로, 리듬 판별에 쓸 수 있게 hollow 여부를 원본에서
    # 바로 태깅해서 함께 반환한다
    hollow_set = set(hollow)

    return noteheads, staff_spacing, line_centers, hollow_set


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


# ---------- Audiveris 엔진 연동 ----------

AUDIVERIS_BIN = os.environ.get(
    "AUDIVERIS_BIN", "/home/user/audiveris/dist/app-5.11.0/bin/Audiveris"
)
AUDIVERIS_JAVA_HOME = os.environ.get(
    "AUDIVERIS_JAVA_HOME", "/usr/lib/jvm/java-25-openjdk-amd64"
)
AUDIVERIS_MAX_PIXELS = 19_500_000  # Audiveris 자체 상한(2000만)보다 약간 여유


def ensure_max_pixels(img, max_px=AUDIVERIS_MAX_PIXELS):
    """Audiveris는 너무 큰 이미지를 거부하므로(2000만 픽셀), 넘으면 비율 유지 축소."""
    if img.width * img.height <= max_px:
        return img
    scale = (max_px / (img.width * img.height)) ** 0.5
    return img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))))


def run_audiveris_export(img, workdir, name="page"):
    """페이지 이미지를 Audiveris(-batch -export, smallHeads 스위치 켬)로 돌려서
    MusicXML(.mxl) 경로를 반환한다. smallHeads를 켜야 꾸밈음(그레이스 노트)도
    노트헤드로 잡힌다(기본은 꺼져 있어서 CUE_BEAMS 단계가 통째로 스킵됨)."""
    png_path = os.path.join(workdir, f"{name}.png")
    ensure_max_pixels(img).save(png_path)

    env = dict(os.environ)
    env["JAVA_HOME"] = AUDIVERIS_JAVA_HOME
    env["PATH"] = f"{AUDIVERIS_JAVA_HOME}/bin:" + env.get("PATH", "")

    out_dir = os.path.join(workdir, "audiveris_out")
    os.makedirs(out_dir, exist_ok=True)
    cmd = [
        AUDIVERIS_BIN, "-batch", "-export",
        "-constant", "org.audiveris.omr.sheet.ProcessingSwitches.smallHeads=true",
        "-output", out_dir, png_path,
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)
    mxl_path = os.path.join(out_dir, f"{name}.mxl")
    if not os.path.exists(mxl_path):
        raise RuntimeError(
            f"Audiveris 실행 실패 (returncode={result.returncode}):\n"
            f"{result.stdout[-1500:]}\n{result.stderr[-1500:]}"
        )
    return mxl_path


def parse_audiveris_mxl(mxl_path):
    """Audiveris가 만든 .mxl에서 시스템별 -> 마디별 음표 목록을 뽑아낸다.
    악보 상의 x/y 좌표는 쓰지 않는다(이 스크립트가 직접 검출한 오선/마디 좌표계로
    다시 배치할 것이므로). 대신 각 음표의 마디 내 발음 시점(divisions 단위)을
    구해두면, 그 마디의 픽셀 폭 안에서 비율로 x를 보간할 수 있다 — <backup>/
    <forward>를 반영해서 계산하므로 성부가 여러 개라도 겹치는 시점끼리는 겹치는
    x 근방에 놓인다.
    반환: (systems, clef_of_staff)
      systems = [ [ [note_dict, ...] (마디), ... ] (시스템), ... ]
      clef_of_staff = {스태프번호: 'treble'|'bass'}"""
    with zipfile.ZipFile(mxl_path) as zf:
        xml_name = next(n for n in zf.namelist() if n.endswith(".xml") and "META-INF" not in n)
        root = ET.fromstring(zf.read(xml_name))

    part = root.find("part")
    if part is None:
        return [], {}

    clef_of_staff = {}
    systems = []
    cur_system = None

    for measure in part.findall("measure"):
        print_el = measure.find("print")
        is_new_system = (
            cur_system is None
            or (print_el is not None and print_el.get("new-system") == "yes")
        )
        if is_new_system:
            cur_system = []
            systems.append(cur_system)

        attrs = measure.find("attributes")
        if attrs is not None:
            for clef_el in attrs.findall("clef"):
                num = int(clef_el.get("number", "1"))
                sign = clef_el.findtext("sign", "G")
                clef_of_staff[num] = "treble" if sign == "G" else "bass"

        cursor = 0
        measure_total = 0
        measure_notes = []
        for child in measure:
            if child.tag == "note":
                is_chord = child.find("chord") is not None
                is_grace = child.find("grace") is not None
                dur = int(child.findtext("duration", "0"))
                staff = int(child.findtext("staff", "1"))
                pitch_el = child.find("pitch")
                note_type = child.findtext("type")
                start_time = cursor
                if pitch_el is not None:
                    measure_notes.append({
                        "start": start_time,
                        "staff": staff,
                        "letter": pitch_el.findtext("step"),
                        "octave": int(pitch_el.findtext("octave")),
                        "alter": int(pitch_el.findtext("alter", "0")),
                        "is_grace": is_grace,
                        "type": note_type,
                    })
                if not is_chord and not is_grace:
                    cursor += dur
                    measure_total = max(measure_total, cursor)
            elif child.tag == "backup":
                cursor -= int(child.findtext("duration", "0"))
            elif child.tag == "forward":
                cursor += int(child.findtext("duration", "0"))
                measure_total = max(measure_total, cursor)

        for n in measure_notes:
            n["measure_total"] = max(measure_total, 1)
        cur_system.append(measure_notes)

    if not clef_of_staff:
        clef_of_staff = {1: "treble", 2: "bass"}
    return systems, clef_of_staff


def note_to_y(letter, octave, staff_lines, clef):
    """y_to_note()의 역함수: 음이름+옥타브를 오선 위 y 픽셀 좌표로 되돌린다."""
    spacing = (staff_lines[-1] - staff_lines[0]) / 4.0
    half = spacing / 2.0
    bottom_line_y = staff_lines[-1]
    idx = LETTERS_ASC.index(letter)
    step0_letter, step0_octave = ('E', 4) if clef == 'treble' else ('G', 2)
    idx0 = LETTERS_ASC.index(step0_letter)
    total = (octave - step0_octave) * 7 + idx
    step = total - idx0
    return bottom_line_y - step * half


ALTER_SUFFIX = {-2: '♭♭', -1: '♭', 0: '', 1: '♯', 2: '♯♯'}


def audiveris_label(letter, alter, lang):
    """Audiveris가 알려준 실제 alter(그 음표 하나에 실제로 적용된 반음표)로
    라벨을 만든다 — 조표뿐 아니라 낱개 임시표까지 반영되므로 cv 엔진보다 정확."""
    return NOTE_NAMES[lang][letter] + ALTER_SUFFIX.get(alter, '')


AUDIVERIS_DURATION_SUFFIX = {
    'whole': '(온)', 'half': '(2)', 'quarter': '',
    'eighth': '(8)', '16th': '(16)', '32nd': '(32)', '64th': '(64)',
}


# ---------- 라벨 그리기 ----------

@functools.lru_cache(maxsize=None)
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


def fit_font_to_diameter(draw, text, diameter, max_size, min_size=6):
    """text가 지름 diameter인 원 안에 들어가도록 폰트 크기를 max_size부터
    줄여가며 찾는다 (overlay 모드: 라벨을 노트헤드 크기에 정확히 맞추기 위함)."""
    size = max_size
    font = get_font(size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    while size > min_size and (tw > diameter or th > diameter):
        size -= 1
        font = get_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    return font, tw, th


TREBLE_COLOR = (200, 30, 30)   # 빨강
BASS_COLOR = (30, 60, 200)     # 파랑


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


def rect_has_ink(binary, rect):
    """사각형 영역 안에 원본 악보 잉크(음표/운지번호/셋잇단음표 숫자/스템/빔/오선 등)가
    있는지 검사. 비율(예: 12%) 기준은 라벨 박스가 크면 작은 숫자 기호 하나는
    전체 면적 대비 비중이 작아서 안 걸리는 문제가 있었고, 절대 개수 기준(6px)도
    라벨 가장자리에 숫자 끄트머리 몇 픽셀만 걸치는 경우는 여전히 놓쳐서 라벨이
    숫자를 살짝 가리는 문제가 있었다. 기호를 아주 조금이라도 가리는 걸 원치
    않으므로 어두운 픽셀이 하나라도 있으면 충돌로 본다."""
    x0, y0, x1, y1 = rect
    x0, y0 = max(0, int(x0)), max(0, int(y0))
    x1, y1 = min(binary.shape[1], int(x1)), min(binary.shape[0], int(y1))
    if x1 <= x0 or y1 <= y0:
        return False
    return bool((binary[y0:y1, x0:x1] > 0).any())


def rects_overlap(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)


def rect_overlap_area(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ox = max(0, min(ax1, bx1) - max(ax0, bx0))
    oy = max(0, min(ay1, by1) - max(ay0, by0))
    return ox * oy


def find_label_spot(draw, binary_full, placed_rects, x, y, r, text, font, font_size, pad=2):
    """노트헤드 모양/원본 악보 기호를 라벨이 가리지 않도록 놓을 자리를 찾는다.
    1) 원래대로 노트헤드 바로 위부터 시작해서, 잉크(다른 기호)나 이미 놓인
       라벨과 겹치면 점점 더 위로 밀어낸다.
    2) 그래도 안 되면 아래쪽, 그다음 좌우를 시도한다.
    3) 완전히 안 겹치는 후보가 하나도 없으면(아주 빽빽한 화음 등), 그중
       "겹침이 가장 적은" 후보를 쓴다. 예전에는 이럴 때 무조건 노트헤드
       바로 위 고정 위치로 돌아갔는데, 그러면 겹치는 다른 라벨과 전혀
       조율되지 않아서 두 라벨이 서로 겹쳐 그려지는 문제가 있었다."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    step = th + 2
    base = r + font_size * 0.6

    candidates = []  # (tx, ty) = 텍스트 좌상단 좌표
    for i in range(5):
        candidates.append((x - tw / 2, y - base - i * step))   # 점점 더 위로
    for i in range(3):
        candidates.append((x - tw / 2, y + base + i * step))   # 아래쪽
    candidates.append((x + r * 1.6, y - th / 2))                # 오른쪽
    candidates.append((x - r * 1.6 - tw, y - th / 2))           # 왼쪽

    best_rect, best_score = None, None
    for tx, ty in candidates:
        rect = (tx - pad, ty - pad, tx + tw + pad, ty + th + pad)
        ink = rect_has_ink(binary_full, rect)
        overlap = sum(rect_overlap_area(rect, pr) for pr in placed_rects)
        if not ink and overlap == 0:
            return tx + tw / 2, ty, rect
        score = (1 if ink else 0, overlap)
        if best_score is None or score < best_score:
            best_score, best_rect = score, (tx, ty, rect)

    tx, ty, rect = best_rect
    return tx + tw / 2, ty, rect


def process(input_path, output_path, flats=0, sharps=0, key_map=None, lang='ko',
            font_scale=1.0, label_style='smart', show_duration=False, dpi=200, debug=False,
            engine='cv'):
    key_map = key_map or {}
    pages = load_pages(input_path, dpi=dpi)
    out_pages = []
    total = 0
    unmatched = 0
    global_sys_offset = 0  # 이전 페이지까지 누적된 시스템 개수 (조표 맵 조회용 전역 순번 기준)
    workdir = tempfile.mkdtemp(prefix="notepitch_") if engine == 'audiveris' else None

    for pi, page in enumerate(pages):
        if engine == 'audiveris':
            img_np_full = np.array(page.convert("L"))
            _, binary_full = cv2.threshold(img_np_full, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            line_centers = detect_staff_lines(img_np_full)
            spacing = guess_staff_spacing(line_centers)
            staves = group_into_staves(line_centers)
            systems = group_into_systems(staves)
            noteheads, hollow_set, note_stems = [], set(), {}
        else:
            noteheads, spacing, line_centers, hollow_set = detect_noteheads(page)
            staves = group_into_staves(line_centers)
            systems = group_into_systems(staves)
            img_np_full = np.array(page.convert("L"))
            _, binary_full = cv2.threshold(img_np_full, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            note_stems = {}

        # 이 페이지의 각 시스템(페이지 로컬 인덱스)에 대응하는 문서 전체 기준 전역 순번(1부터)
        global_sys_nums = [global_sys_offset + i + 1 for i in range(len(systems))]

        if engine == 'cv':
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

            # 음표 길이 판별에 쓸 스템 정보를 미리 계산해둔다.
            # (예전에는 여기서 "위/아래 둘 다 스템이 길게 이어지면 가짜"로 보고
            # 걸러냈는데, 화음(여러 노트헤드가 스템 하나를 공유)의 가운데/아래쪽
            # 노트헤드도 정확히 같은 모양이라 화음의 음이 통째로 사라지는 심각한
            # 오탐이 발생했다. 8분음표 이하 플래그의 곡선이 이따금 별도 노트헤드로
            # 오검출되는 문제보다 화음을 지우는 쪽이 훨씬 치명적이라 필터링 자체를
            # 없앴다 — 폭 기준 재구분도 시도했으나 파일마다 spacing이 달라 화음과
            # 플래그를 안정적으로 가르지 못했다.)
            for (x, y, r) in noteheads:
                note_stems[(x, y, r)] = find_stem(binary_full, x, y, r, spacing)

        img = page.convert("RGB").copy()
        draw = ImageDraw.Draw(img)
        font_size = max(10, int(spacing * 1.3 * font_scale))
        font = get_font(font_size)
        placed_rects = []  # 이 페이지에 그린 라벨 사각형들 (겹침 방지용)

        # ---- audiveris 엔진: Audiveris로 음표(피치/박자/조표)를 먼저 뽑아둔다.
        # (아래 마디 구간 계산에서 이 시스템별 마디 개수를 그대로 쓸 것이므로
        # 마디 구간 계산보다 먼저 실행)
        av_systems, clef_of_staff = [], {}
        if engine == 'audiveris':
            try:
                mxl_path = run_audiveris_export(page, workdir, name=f"p{pi + 1}")
                av_systems, clef_of_staff = parse_audiveris_mxl(mxl_path)
            except Exception as e:
                print(f"  [{pi + 1}/{len(pages)}] Audiveris 실패: {e}")
            n_sys = min(len(av_systems), len(systems))
            if len(av_systems) != len(systems):
                print(f"  [경고] Audiveris 시스템 수({len(av_systems)}) != "
                      f"자체 검출 시스템 수({len(systems)}) — 앞쪽 {n_sys}개만 매칭")
            # Audiveris가 이따금 시스템 끝에 음표 없는 유령 마디를 하나 더
            # 보고할 때가 있다 — 내용이 없으니 그냥 잘라낸다.
            for av_measures in av_systems:
                while len(av_measures) > 1 and not av_measures[-1]:
                    av_measures.pop()

        # 시스템별 마디 구간 미리 계산 (overlay가 아닌 라벨 배치에 사용)
        system_measures = []       # [[ (x_left,x_right), ... ], ...]  시스템별 마디 리스트
        for si, sysm in enumerate(systems):
            start_x = find_staff_start_x(img_np_full, sysm['treble'][2])
            end_x = find_staff_end_x(img_np_full, sysm['treble'][2])
            clef_end = start_x + spacing * 15

            if engine == 'audiveris':
                # 자체 바라인 검출은 임시표/운지번호를 바라인으로 오인하는 등
                # 신뢰도가 낮아서(마디 수가 어긋나면 Audiveris 마디와 위치
                # 인덱스가 밀려 라벨이 엉뚱한 자리에 겹쳐 그려진다), 대신
                # Audiveris가 직접 센 마디 개수로 오선 구간을 균등 분할한다.
                # 마디마다 폭이 정확히 비례하진 않지만(내용 밀도 무시), 최소한
                # 마디 인덱스는 항상 어긋나지 않는다.
                n = len(av_systems[si]) if si < len(av_systems) else 0
                if n > 0:
                    step = (end_x - clef_end) / n
                    bounds = [clef_end + step * i for i in range(n + 1)]
                    measures = list(zip(bounds[:-1], bounds[1:]))
                else:
                    measures = []
            else:
                y_top = sysm['treble'][0] - spacing
                y_bottom = sysm['bass'][-1] + spacing
                barlines = find_all_barlines(img_np_full, y_top, y_bottom, clef_end, end_x + 2)
                bounds = [clef_end] + barlines
                if bounds[-1] < end_x - spacing:
                    bounds.append(end_x)
                measures = list(zip(bounds[:-1], bounds[1:]))

            system_measures.append(measures)

        # label_style='lane'용: 시스템마다 클레프별 고정 레인 y좌표
        # (높은음자리 레인은 시스템 맨 위보다 더 위, 낮은음자리 레인은 맨 아래보다 더 아래)
        system_lane_ys = [
            {'treble': sysm['treble'][0] - spacing * 4.5, 'bass': sysm['bass'][-1] + spacing * 3.5}
            for sysm in systems
        ]

        # ---- audiveris 엔진: 뽑아둔 음표를 위에서 계산한 마디 구간 위에 배치 ----
        audiveris_notes = []
        if engine == 'audiveris':
            for si in range(min(len(av_systems), len(systems))):
                av_measures = av_systems[si]
                own_measures = system_measures[si]
                n_meas = len(own_measures)  # 위에서 av_measures 개수로 만들었으므로 항상 일치
                for mi in range(n_meas):
                    lo, hi = own_measures[mi]
                    pad = (hi - lo) * 0.08
                    lo2, hi2 = lo + pad, hi - pad
                    seen = {}  # (staff,start) -> 같은 박에 이미 놓인 음표 수(화음/꾸밈음 겹침 방지용)
                    for n in av_measures[mi]:
                        clef = clef_of_staff.get(n['staff'], 'treble' if n['staff'] == 1 else 'bass')
                        lines = systems[si]['treble'] if clef == 'treble' else systems[si]['bass']
                        y = note_to_y(n['letter'], n['octave'], lines, clef)
                        frac = n['start'] / n['measure_total'] if n['measure_total'] else 0
                        x = lo2 + frac * (hi2 - lo2)
                        # 화음 노트는 전부 같은 start(같은 박)라 x가 겹쳐서 나오는데,
                        # 라벨 배치 알고리즘이 가로로 퍼뜨릴 여지가 없어져 라벨끼리
                        # 겹치는 문제가 있었다. 같은 박 음표끼리 x를 살짝 벌려준다.
                        k = seen.get((n['staff'], n['start']), 0)
                        seen[(n['staff'], n['start'])] = k + 1
                        if n['is_grace']:
                            x -= (k + 1) * spacing * 0.9
                        elif k:
                            x += k * spacing * 0.55
                        r = max(3, int(round(spacing * 0.5)))
                        audiveris_notes.append({
                            'x': int(x), 'y': int(y), 'r': r, 'sys_idx': si, 'clef': clef,
                            'letter': n['letter'], 'octave': n['octave'], 'alter': n['alter'],
                            'type': n['type'],
                        })

        # ---- 음이름 계산 + 라벨 그리기 ----
        page_matched = 0
        note_source = audiveris_notes if engine == 'audiveris' else (
            {'x': x, 'y': y, 'r': r} for (x, y, r) in noteheads
        )
        for item in note_source:
            x, y, r = item['x'], item['y'], item['r']

            if engine == 'audiveris':
                best_sys_idx = item['sys_idx']
                clef = item['clef']
                letter, octave, alter = item['letter'], item['octave'], item['alter']
                label = audiveris_label(letter, alter, lang)
                dur_key = item['type'] if item['type'] in AUDIVERIS_DURATION_SUFFIX else 'quarter'
                if show_duration:
                    label += AUDIVERIS_DURATION_SUFFIX.get(dur_key, '')
            else:
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

                sys_flats, sys_sharps = effective_key(key_map, flats, sharps, global_sys_nums[best_sys_idx])

                letter, octave = y_to_note(y, lines, clef)
                label = apply_key_signature(letter, flats=sys_flats, sharps=sys_sharps, lang=lang)
                stem = note_stems.get((x, y, r)) or find_stem(binary_full, x, y, r, spacing)
                duration = classify_duration(binary_full, x, y, r, spacing, stem,
                                              is_hollow=(x, y, r) in hollow_set,
                                              staff_line_ys=lines)
                if show_duration:
                    label += DURATION_SUFFIX[duration]
            color = TREBLE_COLOR if clef == 'treble' else BASS_COLOR

            if label_style == 'overlay':
                # 2) 노트헤드 원과 정확히 같은 크기/위치에 라벨을 겹쳐 쓴다.
                # 고정 폰트 크기를 그대로 쓰면 글자가 원보다 커서 옆 음표의
                # 라벨과 겹쳤다 — 노트헤드 지름 안에 들어가도록 글자 크기를
                # 그때그때 줄인다.
                diameter = 2 * r
                fit_font, tw, th = fit_font_to_diameter(draw, label, diameter, font_size)
                lx, ly = x, y - th / 2
                draw_label_with_bg(draw, lx, ly, label, fit_font, color, pad=0)
            elif label_style == 'lane':
                # 3) 오선 바깥 고정 레인(클레프별 한 줄)에 x만 노트에 맞춰 배치
                lane_y = system_lane_ys[best_sys_idx][clef]
                lx, ly, lrect = find_label_spot(draw, binary_full, placed_rects, x, lane_y, 0,
                                                 label, font, font_size)
                draw_label_with_bg(draw, lx, ly, label, font, color)
                placed_rects.append(lrect)
            else:  # 'smart' (기본, 1+2 조합)
                lx, ly, lrect = find_label_spot(draw, binary_full, placed_rects, x, y, r,
                                                 label, font, font_size)
                draw_label_with_bg(draw, lx, ly, label, font, color)
                placed_rects.append(lrect)
            if debug:
                draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(0, 120, 255))

            page_matched += 1

        total += page_matched
        global_sys_offset += len(systems)
        out_pages.append(img)
        sys_range = f"{global_sys_nums[0]}~{global_sys_nums[-1]}" if global_sys_nums else "-"
        print(f"  [{pi+1}/{len(pages)}] 오선간격={spacing}px, 시스템={len(systems)}개(전역 #{sys_range}), "
              f"음이름={page_matched}개")

    ext = os.path.splitext(output_path)[1].lower()
    if ext == ".pdf":
        out_pages[0].save(output_path, save_all=True, append_images=out_pages[1:])
    else:
        out_pages[0].save(output_path)

    print(f"완료: 음이름 {total}개 부착 (매칭 실패 {unmatched}개) -> {output_path}")


def default_output_path(input_path):
    """-o를 안 주면 입력 파일과 같은 위치에 '원본파일명_note.확장자'로 저장"""
    root, ext = os.path.splitext(input_path)
    return f"{root}_note{ext}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="악보 위 음표마다 고정도 계이름 삽입")
    parser.add_argument("input")
    parser.add_argument(
        "-o", "--output", default=None,
        help="출력 파일 경로. 생략하면 입력 파일과 같은 위치에 '원본파일명_note.확장자'로 저장"
    )
    parser.add_argument("--flats", type=int, default=0, help="조표의 ♭ 개수 (곡 시작부터 적용되는 기본값)")
    parser.add_argument("--sharps", type=int, default=0, help="조표의 ♯ 개수 (곡 시작부터 적용되는 기본값)")
    parser.add_argument(
        "--key-map", default=None,
        help="곡 중간 조표 변경 지정. '전역시스템번호:flats=N' 또는 '...:sharps=N'을 콤마로 나열. "
             "예: '5:sharps=3,8:flats=5' -> 5번째 시스템부터 ♯3개, 8번째 시스템부터 ♭5개. "
             "시스템 전역번호는 --key-map 없이 한 번 먼저 돌려서 나오는 "
             "'시스템=N개(전역 #A~B)' 로그로 확인한 뒤 지정한다."
    )
    parser.add_argument(
        "--lang", default="ko", choices=sorted(NOTE_NAMES.keys()),
        help="계이름 표기 언어: ko(도레미, 기본) / solfege(Do Re Mi) / letter(C D E) / ja(ドレミ)"
    )
    parser.add_argument(
        "--font-scale", type=float, default=1.0,
        help="라벨 글자 크기 배율 (기본 1.0이 이미 기존 v2보다 큰 크기; 더 키우려면 1.2 등으로)"
    )
    parser.add_argument(
        "--label-style", default="smart", choices=["smart", "overlay", "lane"],
        help="라벨 배치 방식: smart(기본, 빈 공간 탐색+겹침 최소화) / "
             "overlay(노트헤드 위치에 라벨을 그대로 겹쳐 씀) / "
             "lane(오선 바깥 클레프별 고정 레인에 일렬로 배치)"
    )
    parser.add_argument(
        "--show-duration", action="store_true",
        help="온음표/2분음표/8분음표 이하 표시 (온)/(2)/(8)를 라벨에 덧붙인다. 기본은 끔"
    )
    parser.add_argument(
        "--engine", default="cv", choices=["cv", "audiveris"],
        help="음표 검출 엔진: cv(기본, 자체 OpenCV 검출) / "
             "audiveris(실제 OMR 엔진 Audiveris로 검출 — 꾸밈음/조표/낱개 임시표까지 반영, "
             "--flats/--sharps/--key-map은 무시됨)"
    )
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    output_path = args.output or default_output_path(args.input)
    key_map = parse_key_map(args.key_map) if args.key_map else {}
    process(args.input, output_path, flats=args.flats, sharps=args.sharps, key_map=key_map,
            lang=args.lang, font_scale=args.font_scale, label_style=args.label_style,
            show_duration=args.show_duration,
            dpi=args.dpi, debug=args.debug, engine=args.engine)
