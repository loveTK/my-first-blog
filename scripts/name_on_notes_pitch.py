"""
악보 위에 계이름(고정도) 자동 삽입
--------------------------------------------------
PDF/JPG/PNG 악보를 입력받아 homr(트랜스포머 기반 OMR 엔진)로 음표를 검출한 뒤,
실제 음이름을 계산해 각 음표 위에 고정도 계이름(도레미파솔라시, 항상 C=도)을 써넣는다.

homr로 음표(피치/박자/조표/낱개 임시표/꾸밈음)를 MusicXML로 뽑아낸 뒤, 그 정보를
이 스크립트가 직접 검출한 오선/마디 위치 위에 얹는다(라벨 좌표는 homr 좌표계가
아니라 이 스크립트가 검출한 오선 위치로 역산해서 계산한다). 순수 파이썬(PyTorch/
ONNX Runtime)이라 자바/JVM이 필요 없다.

한계:
- 그랜드 스태프(피아노보) 전용: 각 시스템이 [높은음자리, 낮은음자리] 순서로 위→아래 배치된다고 가정
- 한 마디 안에 여러 성부가 겹치는 경우 시간축(divisions) 기준으로 x를 보간하므로
  얼추 맞지만 완벽하진 않음

음표 길이(리듬):
- --show-duration을 줘야 homr이 알려준 음표 종류로 라벨 옆에 (온)/(2)/(8) 등을 표시한다.
  기본값은 표시하지 않는다.

계이름 언어(--lang):
- ko(기본): 도레미파솔라시 / solfege: Do Re Mi Fa Sol La Si / letter: C D E F G A B

출력 파일명:
- -o를 안 주면 입력 파일과 같은 위치에 "원본파일명_note.확장자"로 자동 저장한다.

사용법:
    python name_on_notes_pitch.py input.pdf
    python name_on_notes_pitch.py input.pdf --lang solfege
    python name_on_notes_pitch.py input.pdf -o output.pdf --show-duration
"""

import argparse
import functools
import os
import tempfile
import xml.etree.ElementTree as ET

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

LETTERS_ASC = ['C', 'D', 'E', 'F', 'G', 'A', 'B']  # 옥타브 내 오름차순

NOTE_NAMES = {
    'ko': {'C': '도', 'D': '레', 'E': '미', 'F': '파', 'G': '솔', 'A': '라', 'B': '시'},
    'solfege': {'C': 'Do', 'D': 'Re', 'E': 'Mi', 'F': 'Fa', 'G': 'Sol', 'A': 'La', 'B': 'Si'},
    'letter': {'C': 'C', 'D': 'D', 'E': 'E', 'F': 'F', 'G': 'G', 'A': 'A', 'B': 'B'},
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


def guess_staff_spacing(line_centers):
    """검출된 오선 중심좌표들의 간격(줄 간격) 중앙값을 추정한다."""
    diffs = np.diff(line_centers) if len(line_centers) > 1 else [14]
    small = [d for d in diffs if d < np.median(diffs) * 2.5] if len(diffs) else [14]
    return max(4, int(np.median(small))) if small else 14


# ---------- homr 엔진 연동 ----------

def run_homr_export_batch(pages, workdir):
    """전체 페이지를 한 파이썬 프로세스 안에서 homr(트랜스포머 기반 OMR)로
    돌려 페이지별 MusicXML을 만든다. homr을 라이브러리로 직접 import해서
    호출하므로(CLI를 페이지마다 새로 실행하지 않음), 제일 무거운 트랜스포머
    모델은 첫 페이지에서 한 번만 로드되고 이후 페이지들은 그대로 재사용된다.
    반환: (페이지 인덱스(0부터) -> musicxml 경로 또는 None, 실패 시 에러 상세)"""
    from homr.main import ProcessingConfig, download_weights, process_image
    from homr.music_xml_generator import XmlGeneratorArguments
    from homr.onnx_providers import coreml_available, cuda_available

    use_cuda = cuda_available()
    segnet_use_gpu = use_cuda or coreml_available()
    # CLI(main())는 처리 전에 이걸 자동으로 해주지만, 라이브러리로 직접
    # 호출할 땐 우리가 직접 불러줘야 한다 — 안 그러면 모델 파일이 없다는
    # ONNXRuntimeError로 조용히 실패한다. 이미 받아져 있으면 즉시 리턴.
    download_weights(segnet_use_gpu, transformer_use_gpu=use_cuda, coreml_encoder=False)

    config = ProcessingConfig(
        enable_debug=False, enable_cache=False,
        write_staff_positions=False, read_staff_positions=False,
        selected_staff=-1,
        transformer_use_gpu=use_cuda,
        segnet_use_gpu=segnet_use_gpu,
        coreml_encoder=False,
    )
    xml_args = XmlGeneratorArguments()

    xml_paths = {}
    error_detail = None
    for pi, page in enumerate(pages):
        png_path = os.path.join(workdir, f"p{pi + 1}.png")
        page.save(png_path)
        xml_path = os.path.splitext(png_path)[0] + ".musicxml"
        try:
            process_image(png_path, config, xml_args)
            xml_paths[pi] = xml_path if os.path.exists(xml_path) else None
        except Exception as e:
            xml_paths[pi] = None
            if error_detail is None:
                error_detail = str(e)
    return xml_paths, error_detail


def parse_musicxml(xml_path):
    """homr가 만든 MusicXML에서 시스템별 -> 마디별 음표 목록을 뽑아낸다.
    악보 상의 x/y 좌표는 쓰지 않는다(이 스크립트가 직접 검출한 오선/마디 좌표계로
    다시 배치할 것이므로). 대신 각 음표의 마디 내 발음 시점(divisions 단위)을
    구해두면, 그 마디의 픽셀 폭 안에서 비율로 x를 보간할 수 있다 — <backup>/
    <forward>를 반영해서 계산하므로 성부가 여러 개라도 겹치는 시점끼리는 겹치는
    x 근방에 놓인다.
    반환: (systems, clef_of_staff)
      systems = [ [ [note_dict, ...] (마디), ... ] (시스템), ... ]
      clef_of_staff = {스태프번호: 'treble'|'bass'}"""
    root = ET.parse(xml_path).getroot()

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
    """음이름+옥타브를 오선 위 y 픽셀 좌표로 변환한다."""
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


def note_label(letter, alter, lang):
    """OMR 엔진이 알려준 실제 alter(그 음표 하나에 실제로 적용된 반음표)로
    라벨을 만든다 — 조표뿐 아니라 낱개 임시표까지 반영된다."""
    return NOTE_NAMES[lang][letter] + ALTER_SUFFIX.get(alter, '')


DURATION_SUFFIX = {
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
        "C:/Windows/Fonts/malgunbd.ttf",  # 윈도우 기본 한글 폰트(맑은 고딕, 볼드)
        "C:/Windows/Fonts/malgun.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",  # macOS
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


def process(input_path, output_path, lang='ko',
            font_scale=1.0, label_style='smart', show_duration=False, dpi=200, debug=False):
    pages = load_pages(input_path, dpi=dpi)
    out_pages = []
    total = 0
    first_omr_error = None
    global_sys_offset = 0  # 이전 페이지까지 누적된 시스템 개수 (로그용 전역 순번 기준)
    workdir = tempfile.mkdtemp(prefix="notepitch_")

    print(f"homr 실행 시작 (총 {len(pages)}페이지)...")
    xml_paths, batch_error = run_homr_export_batch(pages, workdir)

    for pi, page in enumerate(pages):
        img_np_full = np.array(page.convert("L"))
        _, binary_full = cv2.threshold(img_np_full, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        line_centers = detect_staff_lines(img_np_full)
        spacing = guess_staff_spacing(line_centers)
        staves = group_into_staves(line_centers)
        systems = group_into_systems(staves)

        # 이 페이지의 각 시스템(페이지 로컬 인덱스)에 대응하는 문서 전체 기준 전역 순번(1부터)
        global_sys_nums = [global_sys_offset + i + 1 for i in range(len(systems))]

        img = page.convert("RGB").copy()
        draw = ImageDraw.Draw(img)
        font_size = max(10, int(spacing * 1.3 * font_scale))
        font = get_font(font_size)
        placed_rects = []  # 이 페이지에 그린 라벨 사각형들 (겹침 방지용)

        # ---- homr로 음표(피치/박자/조표)를 먼저 뽑아둔다.
        # (아래 마디 구간 계산에서 이 시스템별 마디 개수를 그대로 쓸 것이므로
        # 마디 구간 계산보다 먼저 실행)
        omr_systems, clef_of_staff = [], {}
        xml_path = xml_paths.get(pi)
        if xml_path:
            try:
                omr_systems, clef_of_staff = parse_musicxml(xml_path)
            except Exception as e:
                print(f"  [{pi + 1}/{len(pages)}] MusicXML 파싱 실패: {e}")
                if first_omr_error is None:
                    first_omr_error = str(e)
        else:
            print(f"  [{pi + 1}/{len(pages)}] homr 결과 없음"
                  + (f": {batch_error}" if batch_error else ""))
            if first_omr_error is None:
                first_omr_error = batch_error or "알 수 없는 오류"
        n_sys = min(len(omr_systems), len(systems))
        if len(omr_systems) != len(systems):
            print(f"  [경고] homr 시스템 수({len(omr_systems)}) != "
                  f"자체 검출 시스템 수({len(systems)}) — 앞쪽 {n_sys}개만 매칭")
        # homr이 이따금 시스템 끝에 음표 없는 유령 마디를 하나 더
        # 보고할 때가 있다 — 내용이 없으니 그냥 잘라낸다.
        for omr_measures in omr_systems:
            while len(omr_measures) > 1 and not omr_measures[-1]:
                omr_measures.pop()

        # 시스템별 마디 구간 미리 계산 (overlay가 아닌 라벨 배치에 사용)
        system_measures = []       # [[ (x_left,x_right), ... ], ...]  시스템별 마디 리스트
        for si, sysm in enumerate(systems):
            start_x = find_staff_start_x(img_np_full, sysm['treble'][2])
            end_x = find_staff_end_x(img_np_full, sysm['treble'][2])
            clef_end = start_x + spacing * 15

            # 자체 바라인 검출은 임시표/운지번호를 바라인으로 오인하는 등
            # 신뢰도가 낮아서(마디 수가 어긋나면 homr 마디와 위치
            # 인덱스가 밀려 라벨이 엉뚱한 자리에 겹쳐 그려진다), 대신
            # homr이 직접 센 마디 개수로 오선 구간을 균등 분할한다.
            # 마디마다 폭이 정확히 비례하진 않지만(내용 밀도 무시), 최소한
            # 마디 인덱스는 항상 어긋나지 않는다.
            n = len(omr_systems[si]) if si < len(omr_systems) else 0
            if n > 0:
                step = (end_x - clef_end) / n
                bounds = [clef_end + step * i for i in range(n + 1)]
                measures = list(zip(bounds[:-1], bounds[1:]))
            else:
                measures = []

            system_measures.append(measures)

        # label_style='lane'용: 시스템마다 클레프별 고정 레인 y좌표
        # (높은음자리 레인은 시스템 맨 위보다 더 위, 낮은음자리 레인은 맨 아래보다 더 아래)
        system_lane_ys = [
            {'treble': sysm['treble'][0] - spacing * 4.5, 'bass': sysm['bass'][-1] + spacing * 3.5}
            for sysm in systems
        ]

        # ---- 뽑아둔 음표를 위에서 계산한 마디 구간 위에 배치 ----
        omr_notes = []
        for si in range(min(len(omr_systems), len(systems))):
            omr_measures = omr_systems[si]
            own_measures = system_measures[si]
            n_meas = len(own_measures)  # 위에서 omr_measures 개수로 만들었으므로 항상 일치
            for mi in range(n_meas):
                lo, hi = own_measures[mi]
                pad = (hi - lo) * 0.08
                lo2, hi2 = lo + pad, hi - pad
                seen = {}  # (staff,start) -> 같은 박에 이미 놓인 음표 수(화음/꾸밈음 겹침 방지용)
                for n in omr_measures[mi]:
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
                    omr_notes.append({
                        'x': int(x), 'y': int(y), 'r': r, 'sys_idx': si, 'clef': clef,
                        'letter': n['letter'], 'octave': n['octave'], 'alter': n['alter'],
                        'type': n['type'],
                    })

        # ---- 음이름 계산 + 라벨 그리기 ----
        page_matched = 0
        for item in omr_notes:
            x, y, r = item['x'], item['y'], item['r']

            best_sys_idx = item['sys_idx']
            clef = item['clef']
            letter, octave, alter = item['letter'], item['octave'], item['alter']
            label = note_label(letter, alter, lang)
            dur_key = item['type'] if item['type'] in DURATION_SUFFIX else 'quarter'
            if show_duration:
                label += DURATION_SUFFIX.get(dur_key, '')
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

    if total == 0:
        # homr이 모든 페이지에서 실패하면 이전엔 그냥 원본과 똑같은(라벨
        # 하나도 없는) 파일을 조용히 돌려줬다 — 실패를 실패로 알리지 않는 게
        # 더 나쁘다고 판단해 예외를 던지도록 바꿨다. 웹앱 쪽에서 이걸 잡아
        # 사용자에게 실패 메시지로 보여준다.
        detail = f" (원인: {first_omr_error})" if first_omr_error else ""
        raise RuntimeError(f"음표 검출 실패 (음표 0개 검출){detail}")

    ext = os.path.splitext(output_path)[1].lower()
    if ext == ".pdf":
        out_pages[0].save(output_path, save_all=True, append_images=out_pages[1:])
    else:
        out_pages[0].save(output_path)

    print(f"완료: 음이름 {total}개 부착 -> {output_path}")


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
    parser.add_argument(
        "--lang", default="ko", choices=sorted(NOTE_NAMES.keys()),
        help="계이름 표기 언어: ko(도레미, 기본) / solfege(Do Re Mi) / letter(C D E)"
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
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    output_path = args.output or default_output_path(args.input)
    process(args.input, output_path,
            lang=args.lang, font_scale=args.font_scale, label_style=args.label_style,
            show_duration=args.show_duration,
            dpi=args.dpi, debug=args.debug)
