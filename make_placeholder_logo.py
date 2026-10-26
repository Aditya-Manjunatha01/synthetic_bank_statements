#!/usr/bin/env python3
"""Draw a placeholder logo at assets/bank_logo_tagline.png ONLY if that file is missing.

Your own bank_logo_tagline.png always wins: copy it into assets/ and this script does nothing.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent / "assets" / "bank_logo_tagline.png"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default(size)


def main():
    if OUT.exists():
        print(f"{OUT} already exists, leaving it untouched")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (640, 150), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([10, 15, 80, 85], fill=(0, 74, 142))
    d.rectangle([22, 27, 68, 73], outline="white", width=5)
    d.text((100, 12), "bank logo", font=font(BOLD, 62), fill=(0, 74, 142))
    d.text((102, 100), "your tagline here", font=font(REG, 30), fill=(70, 70, 70))
    img.save(OUT)
    print(f"wrote placeholder {OUT}")


if __name__ == "__main__":
    main()