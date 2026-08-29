"""Cropped (zoomed-on-dancer) contact sheet: zsheet.py START END STEP OUT.jpg [COLS]"""

import sys, os, subprocess, tempfile, glob
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mkclip import crop_box

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "source.mp4")
start, end, step, out = (
    float(sys.argv[1]),
    float(sys.argv[2]),
    float(sys.argv[3]),
    sys.argv[4],
)
cols = int(sys.argv[5]) if len(sys.argv) > 5 else 6
x, y, w, h = crop_box(start, end - start, aspect=1.2, pad=0.22)
print("crop", x, y, w, h)
tmp = tempfile.mkdtemp()
subprocess.run(
    [
        "ffmpeg",
        "-y",
        "-ss",
        str(start),
        "-to",
        str(end),
        "-i",
        SRC,
        "-vf",
        f"crop={w}:{h}:{x}:{y},fps={1 / step},scale=400:-1",
        "-q:v",
        "3",
        os.path.join(tmp, "f_%03d.jpg"),
        "-loglevel",
        "error",
    ],
    check=True,
)
files = sorted(glob.glob(os.path.join(tmp, "f_*.jpg")))
font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 24)
W, H = Image.open(files[0]).size
rows = (len(files) + cols - 1) // cols
sheet = Image.new("RGB", (cols * W, rows * H), "black")
d = ImageDraw.Draw(sheet)
for i, f in enumerate(files):
    t = start + i * step
    im = Image.open(f)
    px, py = (i % cols) * W, (i // cols) * H
    sheet.paste(im, (px, py))
    d.rectangle([px + 2, py + 2, px + 104, py + 32], fill="black")
    d.text((px + 6, py + 4), f"{t:.1f}", fill="yellow", font=font)
sheet.save(out, quality=86)
print(out, sheet.size, len(files), "tiles")
