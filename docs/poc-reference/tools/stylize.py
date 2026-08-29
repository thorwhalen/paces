"""Stylize a clip into the anime/cartoon look, so the dancer is not recognisable.

Same pipeline as kodokan's `examples/generate_stylized_clips.py` (issue #39 + its
face-privacy ADR), adapted to this project: one dancer, arbitrary crop, and a
STREAMING frame loop so the 2:46 run-through doesn't have to fit in RAM.

    painterly       cv2.stylization(sigma_s=60, sigma_r=.45) at half res
    background      YOLO11n-seg person mask -> two flat colours (wall / floor)   [--bg flat]
    face            RetinaFace (gated to the person mask, 6-frame hold)
                    -> AnimeGANv2 face_paint_512_v2 in a feathered ellipse
                    -> plus a soft blur on top  (BLUR=1: AnimeGAN alone leaks identity)
    safety net      any head band with no anime face on it gets blurred anyway
"""

import argparse, json, os, subprocess, sys
from pathlib import Path

os.environ.setdefault("YOLO_VERBOSE", "False")
os.environ.setdefault("GLOG_minloglevel", "3")
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
ANIMEGAN = Path.home() / "kodokan_data" / "style_models" / "face_paint_512_v2_0.onnx"
YOLOSEG = Path.home() / "Dropbox/py/proj/t/kodokan/yolo11n-seg.pt"
FF = "ffmpeg"
DEVICE = "mps"
ORT_PROVIDERS = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
BLUR_ANIME_FACES = os.environ.get("BLUR_ANIME_FACES", "1") == "1"
ANIME_EVERY, SEG_EVERY = 12, 2
NARROW_HEAD_BAND = os.environ.get("NARROW_HEAD_BAND", "1") == "1"


def load_models():
    from ultralytics import YOLO
    import onnxruntime as ort
    from insightface.app import FaceAnalysis

    seg = YOLO(str(YOLOSEG))
    anime = ort.InferenceSession(str(ANIMEGAN), providers=ORT_PROVIDERS)
    det = FaceAnalysis(
        name="buffalo_l", allowed_modules=["detection"], providers=ORT_PROVIDERS
    )
    det.prepare(ctx_id=0, det_size=(640, 640), det_thresh=0.35)
    return seg, anime, det


# ── per-frame ops (verbatim from kodokan) ──────────────────────────────────
def _b1(frame):
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    return cv2.resize(
        cv2.stylization(small, sigma_s=60, sigma_r=0.45),
        (w, h),
        interpolation=cv2.INTER_LINEAR,
    )


def _person_instances(fr, seg):
    r = seg.predict(fr, classes=[0], device=DEVICE, verbose=False)[0]
    h, w = fr.shape[:2]
    if r.masks is None:
        z = np.zeros((h, w), np.uint8)
        return z, []
    inst = [
        cv2.resize((m > 0.5).astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)
        for m in r.masks.data.cpu().numpy()
    ]
    union = (
        np.clip(np.sum(inst, axis=0), 0, 1).astype(np.uint8)
        if inst
        else np.zeros((h, w), np.uint8)
    )
    return union, inst


def _head_band(mask):
    """The head region of a person mask: kodokan's top-28%-of-row-extent band, but
    narrowed horizontally to a window above the shoulders.

    Kodokan blurred the full-width band because two judoka overlap and a head can be
    anywhere in it. Here there is one dancer, and several blocks are ARMS-ABOVE-THE-HEAD
    (bloc 3's droites, bloc 7's bras alternés, bloc 9's lancer) — a full-width band
    smears the very thing the clip exists to show. The shoulder columns sit under the
    head even when the arms are up, so they give a stable window; it is widened by 0.7x
    the shoulder width so a tilted head stays covered."""
    ys = np.where(mask.any(axis=1))[0]
    if len(ys) == 0:
        return np.zeros_like(mask)
    y0, y1 = ys[0], ys[-1]
    ph = max(1, y1 - y0)
    band = mask.copy()
    band[y0 + int(ph * 0.28) :] = 0
    if not NARROW_HEAD_BAND:
        return band
    sh = mask[y0 + int(ph * 0.28) : y0 + int(ph * 0.48)]
    cols = np.where(sh.any(axis=0))[0]
    if len(cols) == 0:
        return band
    cx = int(np.median(np.where(sh)[1]))
    halfw = max(int(mask.shape[1] * 0.09), int((cols[-1] - cols[0]) * 0.70))
    win = np.zeros_like(band)
    win[:, max(0, cx - halfw) : cx + halfw] = 1
    return band * win


def _flat_bg(frames, seg):
    h, w = frames[0].shape[:2]
    acc = np.zeros((h, w, 3), np.float32)
    cnt = np.zeros((h, w), np.float32)
    for f in frames:
        bgm = _person_instances(f, seg)[0] == 0
        acc[bgm] += f[bgm]
        cnt[bgm] += 1
    cnt[cnt == 0] = 1
    bg = acc / cnt[..., None]
    rowcol = np.median(bg, axis=1)
    lo, hi = int(h * 0.30), int(h * 0.78)
    hy = lo + int(np.argmax(np.linalg.norm(np.diff(rowcol, axis=0), axis=1)[lo:hi]))
    wall = np.median(rowcol[int(h * 0.05) : int(h * 0.25)], axis=0)
    floor = np.median(rowcol[int(h * 0.82) : int(h * 0.97)], axis=0)
    flat = np.empty((h, w, 3), np.float32)
    flat[:hy] = wall
    flat[hy:] = floor
    return flat.astype(np.uint8)


def _faces(det, fr, pm):
    h, w = fr.shape[:2]
    big = cv2.dilate(pm, np.ones((25, 25), np.uint8))
    out = []
    for f in det.get(fr):
        x0, y0, x1, y1 = f.bbox.astype(int)
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        if 0 <= cy < h and 0 <= cx < w and big[cy, cx]:
            out.append((x0, y0, x1, y1))
    return out


def _anime_face(anime):
    iname = anime.get_inputs()[0].name

    def run(bgr):
        rgb = cv2.cvtColor(cv2.resize(bgr, (512, 512)), cv2.COLOR_BGR2RGB).astype(
            np.float32
        )
        x = (rgb / 127.5 - 1.0).transpose(2, 0, 1)[None]
        y = anime.run(None, {iname: x})[0][0]
        return cv2.cvtColor(
            ((y.transpose(1, 2, 0) + 1.0) * 127.5).clip(0, 255).astype(np.uint8),
            cv2.COLOR_RGB2BGR,
        )

    return run


def _ellipse(shape, box, pad=0.12, feather=0.14):
    h, w = shape
    x0, y0, x1, y1 = box
    m = np.zeros((h, w), np.float32)
    cv2.ellipse(
        m,
        ((x0 + x1) // 2, (y0 + y1) // 2),
        (int((x1 - x0) / 2 * (1 + pad)), int((y1 - y0) / 2 * (1 + pad))),
        0,
        0,
        360,
        1.0,
        -1,
    )
    return cv2.GaussianBlur(m, (0, 0), max(1.0, feather * (x1 - x0)))


def _clamp(box, w, h, pad):
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    return (
        max(0, int(x0 - bw * pad)),
        max(0, int(y0 - bh * pad)),
        min(w, int(x1 + bw * pad)),
        min(h, int(y1 + bh * pad)),
    )


def _blur_bands(comp, bands, h, w):
    if bands.max() <= 0:
        return comp
    m = cv2.GaussianBlur(bands, (0, 0), 4)[..., None]
    k = max(9, int(min(h, w) * 0.05) | 1)
    return (comp * (1 - m) + cv2.GaussianBlur(comp, (k, k), 0) * m).astype(np.uint8)


# ── driver ────────────────────────────────────────────────────────────────
def _cut(src, start, dur, vf, out, crf="18"):
    cmd = [FF, "-y"]
    if start is not None:
        cmd += ["-ss", f"{start:.2f}", "-t", f"{dur:.2f}"]
    cmd += ["-i", str(src), "-an"]
    if vf:
        cmd += ["-vf", vf]
    cmd += [
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        crf,
        "-preset",
        "veryfast",
        str(out),
    ]
    subprocess.run(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
    )


def stylize(models, tmp_src, out_path, flat_bg=True, audio_from=None, crf="26"):
    seg, anime_sess, det = models
    anime = _anime_face(anime_sess)
    cap = cv2.VideoCapture(str(tmp_src))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    flat = None
    if flat_bg:
        samples = []
        for i in np.linspace(0, max(0, n - 1), 8).astype(int):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
            ok, f = cap.read()
            if ok:
                samples.append(f)
        flat = _flat_bg(samples, seg)
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    enc = [
        FF,
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{w}x{h}",
        "-r",
        f"{fps}",
        "-i",
        "-",
    ]
    if audio_from:
        enc += [
            "-i",
            str(audio_from),
            "-map",
            "0:v",
            "-map",
            "1:a?",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-shortest",
        ]
    else:
        enc += ["-an"]
    enc += [
        "-c:v",
        "libx264",
        "-profile:v",
        "main",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        crf,
        "-preset",
        "veryfast",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    proc = subprocess.Popen(
        enc, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    ker = np.ones((7, 7), np.uint8)
    slot_cache, pm, insts, faces, hold, fi = {}, None, [], [], 0, 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if pm is None or fi % SEG_EVERY == 0:
            union, insts = _person_instances(f, seg)
            pm = cv2.morphologyEx(union, cv2.MORPH_CLOSE, ker)
        pmf = cv2.GaussianBlur(pm.astype(np.float32), (0, 0), 2)[..., None]
        styl = _b1(f)
        comp = (
            (styl * pmf + flat * (1 - pmf)).astype(np.uint8)
            if flat is not None
            else styl
        )

        d = _faces(det, f, pm)
        if d:
            faces, hold = d, 0
        elif hold < 6:
            hold += 1
        else:
            faces = []
        anime_cov = np.zeros((h, w), np.float32)
        for slot, box in enumerate(sorted(faces, key=lambda b: b[0])):
            cx0, cy0, cx1, cy1 = _clamp(box, w, h, 0.6)
            if cx1 - cx0 < 8 or cy1 - cy0 < 8:
                continue
            tile, age = slot_cache.get(slot, (None, 999))
            if tile is None or age >= ANIME_EVERY:
                tile = anime(f[cy0:cy1, cx0:cx1])
                slot_cache[slot] = (tile, 0)
            else:
                slot_cache[slot] = (tile, age + 1)
            a = cv2.resize(tile, (cx1 - cx0, cy1 - cy0))
            ell = _ellipse((h, w), box)
            m = ell[cy0:cy1, cx0:cx1, None]
            comp[cy0:cy1, cx0:cx1] = (a * m + comp[cy0:cy1, cx0:cx1] * (1 - m)).astype(
                np.uint8
            )
            anime_cov = np.maximum(anime_cov, ell)
        safety = np.zeros((h, w), np.float32)
        for im in insts:
            safety = np.maximum(
                safety, _head_band(im).astype(np.float32) * (anime_cov < 0.4)
            )
        comp = _blur_bands(comp, safety, h, w)
        if BLUR_ANIME_FACES:
            comp = _blur_bands(comp, anime_cov, h, w)
        proc.stdin.write(np.ascontiguousarray(comp).tobytes())
        fi += 1
    cap.release()
    proc.stdin.close()
    proc.wait()
    return fi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video")
    ap.add_argument("--start", type=float)
    ap.add_argument("--dur", type=float)
    ap.add_argument("--vf", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--bg", default="flat", choices=["flat", "keep"])
    ap.add_argument("--audio", action="store_true")
    ap.add_argument("--crf", default="26")
    a = ap.parse_args()
    tmp = a.out + ".src.mp4"
    _cut(a.video, a.start, a.dur, a.vf, tmp)
    models = load_models()
    n = stylize(
        models,
        tmp,
        a.out,
        flat_bg=(a.bg == "flat"),
        audio_from=tmp if a.audio else None,
        crf=a.crf,
    )
    os.remove(tmp)
    print(f"{a.out}  {n} frames  {os.path.getsize(a.out) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
