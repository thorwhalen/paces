"""Locate each cropped block clip inside filage.mp4 by multi-scale template matching.
Gives ground-truth spans in filage-time for a semantic-matching evaluation."""

import cv2, numpy as np, glob, os, json, sys

SP = "/private/tmp/claude-501/-Users-thorwhalen-Downloads/0f75703c-6761-4aa0-b796-aafe02c94155/scratchpad"
MED = "$PP/tt/tw_platform/apps/que_calor_dance/frontend/media"
frames = [
    cv2.cvtColor(cv2.imread(p), cv2.COLOR_BGR2GRAY)
    for p in sorted(glob.glob(f"{SP}/frames/*.jpg"))
]
# frames are 400x225 (scaled from 854x480), 1 fps, frame i covers [i, i+1)
print("frame shape", frames[0].shape)


def first_frame(clip):
    cap = cv2.VideoCapture(f"{MED}/{clip}.mp4")
    ok, fr = cap.read()
    cap.release()
    return cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)


RT = {"b2": 68.2, "b3": 80.9, "b4a": 103.3, "b4b": 118.4, "b7": 161.6, "b9": 201.8}
out = {}
for clip, src_start in RT.items():
    tpl0 = first_frame(clip)
    best = (-2, None, None)
    for w in range(120, 260, 10):  # template width in the 400px-wide frame space
        h = int(round(w * tpl0.shape[0] / tpl0.shape[1]))
        if h >= frames[0].shape[0]:
            continue
        tpl = cv2.resize(tpl0, (w, h), interpolation=cv2.INTER_AREA)
        for i, f in enumerate(frames):
            r = cv2.matchTemplate(f, tpl, cv2.TM_CCOEFF_NORMED)
            v = float(r.max())
            if v > best[0]:
                best = (v, i, w)
    out[clip] = dict(
        score=best[0],
        filage_t=best[1],
        tpl_w=best[2],
        src_start=src_start,
        implied_T0=round(src_start - best[1], 2),
    )
    print(
        f"{clip:5s} score={best[0]:.3f} filage_t={best[1]:4d}s tplw={best[2]:3d} "
        f"src_start={src_start:6.1f} implied_T0={src_start - best[1]:7.2f}"
    )
json.dump(out, open(f"{SP}/locate.json", "w"), indent=1)
