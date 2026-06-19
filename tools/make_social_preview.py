"""Generate the GitHub social preview card (1280x640).

Reuses the existing logo at docs/assets/midas-agent.png. Deterministic — same
inputs produce byte-identical output. No external font deps: uses Pillow's
built-in default + bundled system fonts when available.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT / "docs" / "assets" / "midas-agent.png"
OUT = ROOT / "docs" / "assets" / "social-preview.png"

W, H = 1280, 640
BG = (13, 17, 23)
INK = (240, 246, 252)
MUTE = (139, 148, 158)
ACCENT = (210, 168, 79)


def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in (
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def main() -> None:
    card = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(card)

    logo = Image.open(LOGO).convert("RGBA")
    target_h = 360
    ratio = target_h / logo.height
    logo = logo.resize((int(logo.width * ratio), target_h), Image.LANCZOS)
    card.paste(logo, (90, (H - logo.height) // 2), logo)

    text_x = 90 + logo.width + 60
    draw.text((text_x, 150), "MIDAS", fill=INK, font=_font(110))
    draw.text((text_x, 280), "Local-first AI agent", fill=ACCENT, font=_font(46))
    draw.text(
        (text_x, 360),
        "Approvals  ·  Receipts",
        fill=MUTE,
        font=_font(34),
    )
    draw.text(
        (text_x, 410),
        "Dashboard  ·  CLI  ·  Ollama  ·  MCP",
        fill=MUTE,
        font=_font(34),
    )

    draw.rectangle((0, H - 6, W, H), fill=ACCENT)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    card.save(OUT, "PNG", optimize=True)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
