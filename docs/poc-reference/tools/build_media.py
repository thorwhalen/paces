"""Render every clip in clips.json to media/: mp4 (page) + poster jpg + gif (download)."""

import json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mkclip

OUT = "media"
os.makedirs(OUT, exist_ok=True)
clips = json.load(open("clips.json"))
crops = {}
for c in clips:
    box = mkclip.crop_box(c["start"], c["dur"], aspect=0.8, pad=0.16)
    crops[c["id"]] = box
    cw, ch, cx, cy = box[2], box[3], box[0], box[1]
    args = [
        "--start",
        str(c["start"]),
        "--dur",
        str(c["dur"]),
        "--crop",
        f"{cw}:{ch}:{cx}:{cy}",
    ]
    PY = sys.executable

    def run(extra):
        subprocess.run([PY, "tools/mkclip.py"] + args + extra, check=True)

    run(["--out", f"{OUT}/{c['id']}.mp4", "--width", "560", "--fps", "25"])
    run(
        [
            "--out",
            f"{OUT}/{c['id']}.gif",
            "--width",
            "300",
            "--fps",
            "10",
            "--colors",
            "128",
        ]
    )
    # poster: middle frame of the clip
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(c["start"] + c["dur"] / 2),
            "-i",
            "source.mp4",
            "-frames:v",
            "1",
            "-vf",
            f"crop={cw}:{ch}:{cx}:{cy},scale=360:-1",
            "-q:v",
            "5",
            f"{OUT}/{c['id']}.jpg",
            "-loglevel",
            "error",
        ],
        check=True,
    )
json.dump(crops, open("crops.json", "w"), indent=1)
tot = sum(os.path.getsize(f"{OUT}/{f}") for f in os.listdir(OUT))
print("TOTAL", round(tot / 1e6, 2), "MB")
