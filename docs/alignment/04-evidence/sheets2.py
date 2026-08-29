import subprocess, math, os, glob, numpy as np
from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO

V = "/Users/thorwhalen/Dropbox/py/proj/tt/tw_platform/apps/que_calor_dance/frontend/media/filage.mp4"
FNT = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 20)


def grab(t0, t1, step, tmp, w=854):
    os.makedirs(tmp, exist_ok=True)
    for f in glob.glob(f"{tmp}/*.jpg"):
        os.remove(f)
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            str(t0),
            "-i",
            V,
            "-to",
            str(t1),
            "-vf",
            f"fps=1/{step},scale={w}:-2",
            "-q:v",
            "2",
            f"{tmp}/t_%04d.jpg",
            "-y",
        ],
        check=True,
    )
    return sorted(glob.glob(f"{tmp}/*.jpg"))


def tile(ims, times, out, cols, tw):
    ims = [
        im.resize((tw, int(round(tw * im.size[1] / im.size[0]))), Image.LANCZOS)
        for im in ims
    ]
    w, h = ims[0].size
    rows = math.ceil(len(ims) / cols)
    lab = 26
    sh = Image.new("RGB", (cols * w, rows * (h + lab)), (10, 10, 12))
    d = ImageDraw.Draw(sh)
    for i, im in enumerate(ims):
        r, c = divmod(i, cols)
        x, y = c * w, r * (h + lab)
        sh.paste(im, (x, y + lab))
        d.text((x + 6, y + 2), f"t={times[i]:.1f}s", fill=(255, 205, 50), font=FNT)
        d.rectangle([x, y + lab, x + w - 1, y + lab + h - 1], outline=(60, 60, 70))
    sh.save(out, quality=90)
    print(out, sh.size, os.path.getsize(out) // 1024, "KB", len(ims), "tiles")


# --- A: full frame, whole video, 36 tiles
ps = grab(0, 166, 166 / 36, "_a")
times = [i * 166 / 36 for i in range(len(ps))]
tile([Image.open(p) for p in ps[:36]], times[:36], "A_full_36.jpg", 6, 400)

# --- B: same instants, person-cropped by YOLO
m = YOLO("yolo11s.pt")
crops = []
for p in ps[:36]:
    im = Image.open(p)
    a = np.array(im)
    r = m.predict(a, classes=[0], conf=0.25, imgsz=768, verbose=False)[0]
    if len(r.boxes) == 0:
        crops.append(im)
        continue
    b = r.boxes.xyxy.cpu().numpy()
    i = np.argmax((b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1]))
    x1, y1, x2, y2 = b[i]
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    hh = (y2 - y1) * 1.25
    ww = hh * 0.8
    box = (
        max(0, cx - ww / 2),
        max(0, cy - hh / 2),
        min(im.size[0], cx + ww / 2),
        min(im.size[1], cy + hh / 2),
    )
    crops.append(im.crop(tuple(map(int, box))).resize((320, 400), Image.LANCZOS))
tile(crops, times[:36], "B_crop_36.jpg", 6, 320)
