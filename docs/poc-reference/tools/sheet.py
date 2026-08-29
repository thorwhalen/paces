#!/usr/bin/env python
"""Build a labelled contact sheet from a window of the source video.

Usage:  sheet.py START END STEP OUT.jpg [COLS]
Times in seconds (floats). Each tile is labelled with its absolute timestamp.
"""

import subprocess, sys, tempfile, os, glob
from PIL import Image, ImageDraw, ImageFont

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "source.mp4")


def main():
    start, end, step, out = (
        float(sys.argv[1]),
        float(sys.argv[2]),
        float(sys.argv[3]),
        sys.argv[4],
    )
    cols = int(sys.argv[5]) if len(sys.argv) > 5 else 6
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
            f"fps={1 / step},scale=400:-1",
            "-q:v",
            "3",
            os.path.join(tmp, "f_%03d.jpg"),
            "-loglevel",
            "error",
        ],
        check=True,
    )
    files = sorted(glob.glob(os.path.join(tmp, "f_*.jpg")))
    if not files:
        print("no frames")
        return
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 24)
    W, H = Image.open(files[0]).size
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * W, rows * H), "black")
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(files):
        t = start + i * step
        im = Image.open(f)
        x, y = (i % cols) * W, (i // cols) * H
        sheet.paste(im, (x, y))
        d.rectangle([x + 2, y + 2, x + 104, y + 32], fill="black")
        d.text((x + 6, y + 4), f"{t:.1f}", fill="yellow", font=font)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    sheet.save(out, quality=86)
    print(f"{out} {sheet.size} {len(files)} tiles, {start}->{end} step {step}")


main()
