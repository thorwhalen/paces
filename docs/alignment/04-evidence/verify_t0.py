import cv2, numpy as np, glob

SP = "/private/tmp/claude-501/-Users-thorwhalen-Downloads/0f75703c-6761-4aa0-b796-aafe02c94155/scratchpad"
MED = "/Users/thorwhalen/Dropbox/py/proj/tt/tw_platform/apps/que_calor_dance/frontend/media"
frames = [
    cv2.cvtColor(cv2.imread(p), cv2.COLOR_BGR2GRAY)
    for p in sorted(glob.glob(f"{SP}/frames/*.jpg"))
]


def ff(c):
    cap = cv2.VideoCapture(f"{MED}/{c}.mp4")
    ok, fr = cap.read()
    cap.release()
    return cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)


RT = {"b2": 68.2, "b3": 80.9, "b4a": 103.3, "b4b": 118.4, "b7": 161.6, "b9": 201.8}
for T0 in (50.9, 51.2, 59.4, 59.8):
    tot = 0
    row = []
    for c, s in RT.items():
        t = int(round(s - T0))
        if not (0 <= t < len(frames)):
            row.append(f"{c}:oob")
            continue
        tpl0 = ff(c)
        best = -2
        for w in range(110, 260, 10):
            h = int(round(w * tpl0.shape[0] / tpl0.shape[1]))
            if h >= frames[0].shape[0]:
                continue
            tpl = cv2.resize(tpl0, (w, h), interpolation=cv2.INTER_AREA)
            for tt in (t - 1, t, t + 1):
                if 0 <= tt < len(frames):
                    best = max(
                        best,
                        float(
                            cv2.matchTemplate(
                                frames[tt], tpl, cv2.TM_CCOEFF_NORMED
                            ).max()
                        ),
                    )
        row.append(f"{c}:{best:.2f}@{t}s")
        tot += best
    print(f"T0={T0:5.1f} mean={tot / len(RT):.3f}  " + "  ".join(row))
