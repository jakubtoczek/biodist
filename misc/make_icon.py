"""Generate src/biodist/assets/biodist.ico (+ .png).

Needs Pillow, which the app itself does not: run it with `uv run --with pillow python
misc/make_icon.py` and commit the result.
"""

from pathlib import Path

from PIL import Image, ImageDraw

S = 1024          # drawn big, then downsampled — cheaper than antialiasing by hand
BG, TUBE, FILL, HOT = "#232323", "#d8dde0", "#4a9782", "#e8b64c"

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.21), fill=BG)

# three tubes, filled to different levels: that is what a biodistribution is
for i, (level, colour) in enumerate(((0.30, FILL), (0.72, HOT), (0.46, FILL))):
    w, gap = S * 0.148, S * 0.088
    x = S * 0.22 + i * (w + gap)
    top, bot = S * 0.20, S * 0.80
    r = w / 2
    d.rounded_rectangle([x, top, x + w, bot], radius=r, fill=None, outline=TUBE,
                        width=int(S * 0.026))
    y = bot - (bot - top - r) * level
    d.rounded_rectangle([x + S * 0.026, y, x + w - S * 0.026, bot - S * 0.020],
                        radius=r * 0.8, fill=colour)

out = Path(__file__).resolve().parent.parent / "src" / "biodist" / "assets"
out.mkdir(parents=True, exist_ok=True)
img.resize((256, 256), Image.LANCZOS).save(out / "biodist.png")
img.save(out / "biodist.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                     (128, 128), (256, 256)])
print("wrote", out / "biodist.ico")
