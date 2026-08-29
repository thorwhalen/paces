"""Estimate the empty-room background: high percentile per pixel (the dancer is dark)."""

import cv2, numpy as np

cap = cv2.VideoCapture("source.mp4")
samples = []
for t in np.linspace(50, 640, 240):
    cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000)
    ok, fr = cap.read()
    if ok:
        samples.append(fr)
cap.release()
st = np.stack(samples)
bg = np.percentile(st, 88, axis=0).astype(np.uint8)
cv2.imwrite("bg.png", bg)
print("bg.png", bg.shape, len(samples))
