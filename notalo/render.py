"""라벨 오버레이: 흰 배경박스(90% 불투명, 테두리 없음) + 색 글자."""
import functools
import os

from PIL import Image, ImageDraw, ImageFont

RED, BLUE = (200, 16, 46), (31, 79, 191)  # 높은음자리 #C8102E / 낮은음자리 #1F4FBF
PAD = 2


@functools.lru_cache(maxsize=32)
def font(size):
    # 나눔스퀘어 Bold: 한글+가나+라틴+♯♭ 전부 포함(확인됨). 같은 px에서 Noto보다 작게 나와 1.15배.
    # 뒤는 폴백(Noto Sans CJK도 ko/ja/en 다 됨, 두껍고 투박함).
    for p, k in (
        ("/usr/share/fonts/truetype/nanum/NanumSquareB.ttf", 1.15),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 1.0),
        ("C:/Windows/Fonts/malgunbd.ttf", 1.0),
    ):
        if os.path.exists(p):
            return ImageFont.truetype(p, int(size * k))
    return ImageFont.load_default()  # ponytail: 폰트 없으면 □로 나옴


def text_size(text, size):
    """(w, h) 픽셀. 여러 줄이면 줄 단위 최대폭 × 줄 수."""
    f = font(size)
    lines = text.split("\n")
    boxes = [f.getbbox(t) for t in lines]
    assert boxes
    return max(b[2] - b[0] for b in boxes) + 2 * PAD, sum(b[3] - b[1] for b in boxes) + 2 * PAD * len(lines)


def overlay(page_rgb, labels):
    """labels: [{"x","y","text","clef","size"}] (x,y=박스 왼쪽 위) → PIL RGB 이미지."""
    img = Image.fromarray(page_rgb).convert("RGBA")
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for l in labels:
        assert {"x", "y", "text", "clef", "size"} <= l.keys(), l
        f = font(l["size"])
        w, h = text_size(l["text"], l["size"])
        d.rectangle((l["x"], l["y"], l["x"] + w, l["y"] + h), fill=(255, 255, 255, 230))
        y = l["y"] + PAD
        for line in l["text"].split("\n"):
            b = f.getbbox(line)
            d.text((l["x"] + PAD - b[0], y - b[1]), line, fill=RED if l["clef"] == "treble" else BLUE, font=f)
            y += b[3] - b[1] + 2 * PAD
    return Image.alpha_composite(img, layer).convert("RGB")
