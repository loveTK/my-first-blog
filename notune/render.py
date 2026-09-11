"""라벨 오버레이. 배경박스/폰트 85% 규칙은 7단계."""
import os

from PIL import Image, ImageDraw, ImageFont

RED, BLUE = "#C8102E", "#1F4FBF"  # 높은음자리 / 낮은음자리


def font(size):
    for p in ("C:/Windows/Fonts/malgunbd.ttf", "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()  # ponytail: 한글 폰트 없으면 □로 나옴


def overlay(page_rgb, labels):
    """labels: [{"x","y","text","clef"}] → PIL RGB 이미지."""
    img = Image.fromarray(page_rgb)
    d = ImageDraw.Draw(img)
    f = font(20)  # ponytail: 고정 20px. 7단계에서 staff-space 기준으로.
    for l in labels:
        assert {"x", "y", "text", "clef"} <= l.keys(), l
        d.text((l["x"], l["y"]), l["text"], fill=RED if l["clef"] == "treble" else BLUE, font=f)
    return img
