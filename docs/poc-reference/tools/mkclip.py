#!/usr/bin/env python
"""Cut a clip of the dancer from source.mp4, auto-cropped to her, as GIF / MP4 / WebP.

    mkclip.py --start 96.0 --dur 4.0 --out out/b4.gif [--fps 12] [--width 460]
              [--aspect 0.8] [--pad 0.18] [--fmt gif]

The crop box is found by differencing each frame against the empty-room plate
(bg.png), taking a robust envelope of the dancer's per-frame bounding boxes over
the clip, padding it, and forcing `aspect` (= width / height).
Prints the chosen crop so it can be reused / overridden.
"""
import argparse, os, subprocess, cv2, numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, 'source.mp4')
BG = os.path.join(ROOT, 'bg.png')


_MODEL = None


def _person_boxes(start, dur, probe_fps=5):
    """Per-frame bounding boxes of the dancer over [start, start+dur), via YOLO."""
    global _MODEL
    import warnings; warnings.filterwarnings('ignore')
    from ultralytics import YOLO
    if _MODEL is None:
        _MODEL = YOLO(os.path.join(ROOT, 'yolo11s.pt'))
    cap = cv2.VideoCapture(SRC)
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frames = []
    for t in np.arange(start, start + dur, 1.0 / probe_fps):
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000)
        ok, fr = cap.read()
        if ok:
            frames.append(fr)
    cap.release()
    boxes = []
    for i in range(0, len(frames), 8):
        for r in _MODEL.predict(frames[i:i + 8], classes=[0], conf=0.3, imgsz=768, verbose=False):
            b = r.boxes.xyxy.cpu().numpy()
            if len(b) == 0:
                continue
            k = int(np.argmax((b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])))
            boxes.append(b[k].tolist())
    return np.array(boxes), W, H


def crop_box(start, dur, aspect=0.8, pad=0.18, lo=4, hi=96):
    boxes, W, H = _person_boxes(start, dur)
    if len(boxes) == 0:
        return 0, 0, W, H
    x0 = np.percentile(boxes[:, 0], lo); y0 = np.percentile(boxes[:, 1], lo)
    x1 = np.percentile(boxes[:, 2], hi); y1 = np.percentile(boxes[:, 3], hi)
    bw, bh = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    bw *= (1 + 2 * pad); bh *= (1 + 2 * pad)
    # force aspect
    if bw / bh < aspect:
        bw = bh * aspect
    else:
        bh = bw / aspect
    # clamp inside the frame, shrinking if necessary
    if bw > W:
        bw = W; bh = bw / aspect
    if bh > H:
        bh = H; bw = bh * aspect
    cx = min(max(cx, bw / 2), W - bw / 2)
    cy = min(max(cy, bh / 2), H - bh / 2)
    return int(round(cx - bw / 2)), int(round(cy - bh / 2)), int(round(bw)), int(round(bh))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--start', type=float, required=True)
    p.add_argument('--dur', type=float, required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--fps', type=float, default=12.5)
    p.add_argument('--width', type=int, default=460)
    p.add_argument('--aspect', type=float, default=0.8, help='crop width/height')
    p.add_argument('--pad', type=float, default=0.18)
    p.add_argument('--fmt', default=None, help='gif|mp4|webp (default: from --out)')
    p.add_argument('--crop', default=None, help='override, ffmpeg order: w:h:x:y')
    p.add_argument('--colors', type=int, default=160)
    a = p.parse_args()

    if a.crop:
        cw, ch, cx, cy = (int(v) for v in a.crop.split(':'))
    else:
        cx, cy, cw, ch = crop_box(a.start, a.dur, a.aspect, a.pad)
    fmt = a.fmt or os.path.splitext(a.out)[1].lstrip('.')
    w = a.width; h = int(round(w / a.aspect)) if not a.crop else int(round(w * ch / cw))
    w -= w % 2; h -= h % 2
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or '.', exist_ok=True)
    vf = f'crop={cw}:{ch}:{cx}:{cy},fps={a.fps},scale={w}:{h}:flags=lanczos'

    if fmt == 'gif':
        pal = a.out + '.png'
        subprocess.run(['ffmpeg','-y','-ss',str(a.start),'-t',str(a.dur),'-i',SRC,
                        '-vf', vf + f',palettegen=max_colors={a.colors}:stats_mode=diff',
                        pal,'-loglevel','error'], check=True)
        subprocess.run(['ffmpeg','-y','-ss',str(a.start),'-t',str(a.dur),'-i',SRC,'-i',pal,
                        '-lavfi', vf + '[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle',
                        '-loop','0', a.out,'-loglevel','error'], check=True)
        os.remove(pal)
    elif fmt == 'webp':
        subprocess.run(['ffmpeg','-y','-ss',str(a.start),'-t',str(a.dur),'-i',SRC,
                        '-vf', vf, '-vcodec','libwebp','-lossless','0','-q:v','62',
                        '-preset','picture','-loop','0','-an','-vsync','0',
                        a.out,'-loglevel','error'], check=True)
    else:
        subprocess.run(['ffmpeg','-y','-ss',str(a.start),'-t',str(a.dur),'-i',SRC,
                        '-vf', vf, '-an','-c:v','libx264','-profile:v','main','-pix_fmt','yuv420p',
                        '-crf','26','-movflags','+faststart', a.out,'-loglevel','error'], check=True)
    size = os.path.getsize(a.out)
    print(f'{a.out}  crop={cw}:{ch}:{cx}:{cy}  out={w}x{h}  {size/1024:.0f} KB')


if __name__ == '__main__':
    main()
