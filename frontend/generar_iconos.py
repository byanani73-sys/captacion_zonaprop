"""
Genera los assets PWA para Captación ZonaProp:
  - icon-192.png
  - icon-512.png
  - screenshot-desktop.png  (1280×720)
  - screenshot-mobile.png   (390×844)

Uso:
  python frontend/generar_iconos.py
"""

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    import subprocess, sys
    print("Pillow no está instalado. Instalando...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
    from PIL import Image, ImageDraw, ImageFont

import os

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
BLUE         = (26, 115, 232)    # #1a73e8
WHITE        = (255, 255, 255)
BG_LIGHT     = (232, 240, 254)   # #e8f0fe
DARK_BLUE    = (26, 60, 130)     # texto en screenshots


def best_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFCompact.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_centered(draw, text, font, img_w, img_h, color, y_offset=0):
    bbox   = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (img_w - text_w) / 2 - bbox[0]
    y = (img_h - text_h) / 2 - bbox[1] + y_offset
    draw.text((x, y), text, fill=color, font=font)


# ---------------------------------------------------------------------------
# Íconos de la app  (fondo azul, letras "CZ" blancas)
# ---------------------------------------------------------------------------
def make_icon(size: int, filename: str) -> None:
    img  = Image.new("RGBA", (size, size), BLUE)
    draw = ImageDraw.Draw(img)
    font = best_font(int(size * 0.38))
    draw_centered(draw, "CZ", font, size, size, WHITE)
    path = os.path.join(SCRIPT_DIR, filename)
    img.save(path, "PNG")
    print(f"  ✓ {filename}  ({size}×{size}px)")


# ---------------------------------------------------------------------------
# Screenshots  (fondo azul claro, texto en azul oscuro)
# ---------------------------------------------------------------------------
def make_screenshot(w: int, h: int, filename: str) -> None:
    img  = Image.new("RGB", (w, h), BG_LIGHT)
    draw = ImageDraw.Draw(img)

    # Título principal
    title_font = best_font(int(min(w, h) * 0.055))
    draw_centered(draw, "Captación ZonaProp", title_font, w, h, DARK_BLUE, y_offset=-int(h * 0.04))

    # Subtítulo
    sub_font = best_font(int(min(w, h) * 0.028))
    draw_centered(draw, "Gestión de captación inmobiliaria", sub_font, w, h, DARK_BLUE, y_offset=int(h * 0.04))

    path = os.path.join(SCRIPT_DIR, filename)
    img.save(path, "PNG")
    print(f"  ✓ {filename}  ({w}×{h}px)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Generando assets PWA...")
    make_icon(192, "icon-192.png")
    make_icon(512, "icon-512.png")
    make_screenshot(1280, 720,  "screenshot-desktop.png")
    make_screenshot(390,  844,  "screenshot-mobile.png")
    print("Listo — 4 archivos generados.")


if __name__ == "__main__":
    main()
