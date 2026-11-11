"""Genera assets/smartcfo.ico (e un PNG di anteprima) per l'applicazione."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parent / "assets"
S = 1024  # disegno ad alta risoluzione, poi ridimensionato


def _font(size):
    for name in ("segoeuib.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def build() -> Image.Image:
    # Sfondo: quadrato arrotondato con gradiente blu notte -> blu
    grad = Image.new("RGB", (S, S))
    top, bottom = (14, 42, 82), (31, 111, 209)
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / (S - 1)
        gd.line([(0, y), (S, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=220, fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)

    # Istogramma crescente
    base = 820
    bars = [(170, 600), (330, 480), (490, 360), (650, 250)]
    for x, top_y in bars:
        d.rounded_rectangle([x, top_y, x + 120, base], radius=22, fill=(255, 255, 255, 235))

    # Linea di trend con freccia (verde)
    green = (46, 204, 113, 255)
    pts = [(200, 520), (390, 400), (540, 300), (800, 150)]
    d.line(pts, fill=green, width=44, joint="curve")
    d.polygon([(860, 100), (720, 130), (830, 240)], fill=green)

    # Moneta € in basso a destra
    cx, cy, r = 790, 770, 150
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(245, 183, 49, 255), outline=(255, 255, 255, 255), width=18)
    f = _font(200)
    d.text((cx, cy + 6), "€", font=f, fill=(14, 42, 82, 255), anchor="mm")
    return img


def main():
    OUT_DIR.mkdir(exist_ok=True)
    img = build()
    img.resize((256, 256), Image.LANCZOS).save(OUT_DIR / "smartcfo.png")
    img.save(OUT_DIR / "smartcfo.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Icona creata in {OUT_DIR}")


if __name__ == "__main__":
    main()
