"""Detect the dancer in every 6th frame (5 fps) of source.mp4 -> boxes.npz."""
import cv2, numpy as np, warnings
warnings.filterwarnings('ignore')
from ultralytics import YOLO

m = YOLO('yolo11s.pt')
cap = cv2.VideoCapture('source.mp4')
fps = cap.get(cv2.CAP_PROP_FPS)
STRIDE = 6
ts, bxs = [], []
i = 0
batch, batch_t = [], []
def flush():
    if not batch: return
    for t, r in zip(batch_t, m.predict(batch, classes=[0], verbose=False, conf=0.3, imgsz=960)):
        b = r.boxes.xyxy.cpu().numpy(); c = r.boxes.conf.cpu().numpy()
        if len(b) == 0:
            ts.append(t); bxs.append([np.nan]*4); continue
        k = int(np.argmax((b[:,2]-b[:,0])*(b[:,3]-b[:,1])))
        ts.append(t); bxs.append(b[k].tolist())
    batch.clear(); batch_t.clear()
while True:
    ok, fr = cap.read()
    if not ok: break
    if i % STRIDE == 0:
        batch.append(fr); batch_t.append(i/fps)
        if len(batch) == 16: flush()
    i += 1
flush(); cap.release()
np.savez('boxes.npz', t=np.array(ts), box=np.array(bxs))
b = np.array(bxs)
print('frames', len(ts), 'missing', int(np.isnan(b[:,0]).sum()))
