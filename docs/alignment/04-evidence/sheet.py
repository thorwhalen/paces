"""Contact sheet with burned-in absolute timestamps (PIL, no ffmpeg drawtext)."""

import subprocess, math, os, glob
from PIL import Image, ImageDraw, ImageFont


def sheet(src, t0, t1, step, out, cols=6, tile_w=400):
    tmp = "_sh"
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
            src,
            "-to",
            str(t1),
            "-vf",
            f"fps=1/{step},scale={tile_w}:-2",
            "-q:v",
            "3",
            f"{tmp}/t_%04d.jpg",
            "-y",
        ],
        check=True,
    )
    ps = sorted(glob.glob(f"{tmp}/*.jpg"))
    ims = [Image.open(p) for p in ps]
    w, h = ims[0].size
    rows = math.ceil(len(ims) / cols)
    lab = 26
    sh = Image.new("RGB", (cols * w, rows * (h + lab)), (12, 12, 14))
    d = ImageDraw.Draw(sh)
    try:
        fnt = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 18)
    except Exception:
        fnt = ImageFont.load_default()
    for i, im in enumerate(ims):
        r, c = divmod(i, cols)
        x, y = c * w, r * (h + lab)
        sh.paste(im, (x, y + lab))
        t = t0 + i * step
        d.text(
            (x + 6, y + 3),
            f"{int(t // 60)}:{t % 60:05.2f}  t={t:.2f}s",
            fill=(255, 210, 60),
            font=fnt,
        )
    sh.save(out, quality=88)
    return sh.size, len(ims)


def visual_tokens(w, h, tier="high"):
    """Documented rule: ceil(w/28)*ceil(h/28) patches, after downscaling to fit
    the tier's long-edge and visual-token caps (aspect preserved)."""
    LE, MT = (2576, 4784) if tier == "high" else (1568, 1568)
    s = min(1.0, LE / max(w, h))
    w2, h2 = w * s, h * s
    while math.ceil(w2 / 28) * math.ceil(h2 / 28) > MT:
        w2 *= 0.99
        h2 *= 0.99
    return math.ceil(w2 / 28) * math.ceil(h2 / 28), (round(w2), round(h2))


V = "$PP/tt/tw_platform/apps/que_calor_dance/frontend/media/filage.mp4"
for cols, step, tw, label in [
    (6, 2.0, 400, "coarse 36-tile @2s"),
    (6, 0.5, 400, "fine 18-tile @0.5s"),
    (4, 1.0, 560, "12-tile @1s wide"),
]:
    n_target = 36 if cols == 6 and step == 2 else (18 if step == 0.5 else 12)
    t1 = step * n_target
    (W, H), n = sheet(
        V, 0, t1, step, f"sheet_{label.split()[0]}.jpg", cols=cols, tile_w=tw
    )
    kb = os.path.getsize(f"sheet_{label.split()[0]}.jpg") // 1024
    for tier in ("high", "standard"):
        tk, (w2, h2) = visual_tokens(W, H, tier)
        print(
            f"{label:22s} {n:3d} tiles {W}x{H} {kb:4d}KB | {tier:8s} -> {w2}x{h2} "
            f"{tk:5d} vis-tok = {tk / n:6.1f}/tile, {int(tk / n / (tw * tw * 0.5625 / 784) * 100):3d}% of native tile detail"
        )
