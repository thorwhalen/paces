# 03 — Visual signals for segmentation and alignment

**Question this file answers:** given a video and a list of artifacts (steps, blocks, chapters,
script lines, move names), *what can you get out of the pixels* that tells you which span of the
video each artifact belongs to — and what does each of those things cost, break on, and require?

The POC used almost none of this. It used person *boxes* for cropping and person *masks* for
anonymisation, and got every boundary from audio plus the source document. This file closes that
gap, and the headline is not the one the brief expected: **pose is not the most valuable visual
signal for alignment. Per-frame vision-language embeddings are.** Pose is second, and it earns its
place on a different axis (periodicity and movement identity, not boundaries).

**Verification legend.** **[verified]** = I ran it in the p12 env on this Mac and the number in the
table is the number my terminal printed. **[from docs]** = read from the library's docs/source, not
executed here. **[inferred]** = my judgement; argue with it.

---

## 0. The short answer

| If you need… | Use | Cost / min of 720p30 | § |
|---|---|---|---|
| **Boundaries between semantically different-looking spans** (the common case) | **SigLIP2 frame embeddings + Foote novelty** | **4.4 s @ 6 Hz (MPS)** | §8 |
| **Which artifact goes in which span, from a text description** | SigLIP2 text↔image score matrix + an order-prior DP | +0.15 s for the text side | §8.3 |
| Hard cuts in edited footage | PySceneDetect `AdaptiveDetector` | 2.3 s | §3 |
| A cheap 1-D "is something happening" curve | ffmpeg `lavfi.scene_score`, or numpy frame-diff | 0.8 s / 2.2 s | §3.3, §4.1 |
| Where the *movement* is, and how strong | Farneback flow, or pose motion energy | 7.5 s @ 6 Hz / 19 s | §4, §6.1 |
| **Tempo/period of a repeating movement** | autocorrelation of any motion curve | free (on top of the curve) | §6.3 |
| **Phase of a grid** (the POC's "landmark read off a contact sheet") | visual impact peaks + offset sweep against the beat grid | free | §6.4 |
| "This move again, somewhere else in the video" | subsequence DTW over joint angles | 0.35 s per query | §6.5 |
| Burnt-in step titles / slide text | crop + upscale + tesseract | 14 s @ 1 Hz | §10 |
| Named human actions from a fixed vocabulary | **don't** — see §7 | — | §7 |

**The three things to actually remember:**

1. **Cut detection is not section detection.** On a real product-tour video with five semantic
   sections, PySceneDetect's best detector found 10 cuts of which only 2 were real boundaries, and
   ffmpeg's thresholded scene detector found 2 of the 5. SigLIP2-embedding novelty found
   **5 of 5 to within 0.3 s**. [verified, §8.2]
2. **The order prior is where the accuracy comes from.** A dynamic program that assigns N *ordered,
   non-overlapping* artifacts to N spans over the SigLIP2 score matrix recovered all four internal
   boundaries to ≤0.3 s. The per-artifact argmax on the same matrix got 4 of 6 right and produced a
   confident wrong answer for an artifact that has no span in the video. [verified, §8.3]
3. **Device choice moves cost by 6×, and the defaults are wrong.** `rtmlib` with `device="mps"` is
   6× faster than `device="cpu"` (the fleet's `kodokan.pose` defaults to `"cpu"`); mediapipe's
   *GPU delegate* is 2× **slower** than its CPU path on an M1 Max, and crashes the process unless
   you feed it SRGBA. [verified, §5.4]

---

## 1. The rig

Everything below ran on **Apple M1 Max / 64 GB / macOS 15 (Darwin 24.6)**, in
`~/.pyenv/versions/3.12.12/envs/p12/bin/python`, ffmpeg 8.1 (Homebrew), fully
offline except for one-time model downloads.

Three clips, each **60.0 s, 1280×720, 30 fps, H.264**:

| Clip | What it is | Used for |
|---|---|---|
| **A** | a private handheld clip downscaled to 720p30; one person, static camera, indoor low light | timing and detection-rate only; its content is not analysed or described here |
| **B** | `reeleewebguidedtournarrated.mp4`, first 60 s — a narrated screen-recorded product tour with five clearly-labelled sections and animated transitions | the alignment accuracy experiments; ground truth in §10.3 |
| **C** | synthetic, generated for this file: a blob oscillating at **exactly 0.800 s**, three hard cuts at **15/30/45 s**, and a **150 bpm** click track | ground-truth validation of the periodicity and phase machinery |

Clip C is worth keeping as a test fixture — it is the only way to tell "the method works" from
"the video happened to cooperate". The generator, in full:

```python
W, H, FPS, DUR, PERIOD, BPM, CUTS = 1280, 720, 30, 60.0, 0.8, 150.0, [15.0, 30.0, 45.0]
vw = cv2.VideoWriter("syn_raw.mp4", cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
noise = np.random.default_rng(0).integers(0, 12, (H, W, 3), dtype=np.uint8)
bgs = [(30, 30, 40), (60, 20, 20), (20, 60, 20), (20, 20, 60)]
for i in range(int(DUR * FPS)):
    t = i / FPS
    img = np.full((H, W, 3), bgs[sum(t >= c for c in CUTS)], np.uint8) + noise
    ph = (t % PERIOD) / PERIOD
    y = int(
        200 + 380 * abs(np.sin(np.pi * ph)) ** 0.6
    )  # |sin| -> a sharp impact at the bottom
    x = int(
        W / 2 + 220 * np.sin(2 * np.pi * t / 7.0)
    )  # slow lateral drift, aperiodic vs PERIOD
    cv2.circle(img, (x, y), 60, (230, 230, 240), -1)
    cv2.rectangle(img, (x - 14, y - 160), (x + 14, y - 60), (200, 180, 120), -1)
    vw.write(img)
vw.release()
# click track: one 1 kHz + 60 Hz ping per beat, then mux with ffmpeg -c:v libx264 -shortest
```

**Timing convention.** All clips are exactly 60 s, so *"seconds measured" = "seconds per minute of
720p30 video"*. Where a method was run at a reduced sampling rate that is stated. Marked ⊕ = the
number includes decoding; ⊖ = frames were decoded first and only inference was timed (add ~2.4 s).

---

## 2. Decode is the floor, and it is lower than you think

You cannot spend less than the cost of getting pixels into numpy. Measure it once so you know what
a method actually costs on top of it. **[verified]**

| How | Rate | s / min | Notes |
|---|---|---|---|
| `cv2.VideoCapture.read()` full 720p | 30 fps | **2.37** | simplest; what `kodokan.pose` does |
| `cap.grab()` + `retrieve()` every 5th | 6 fps out | 1.04 | `grab()` skips the decode of frames you throw away |
| ffmpeg rawvideo pipe → 320 px gray | 30 fps | **2.11** | gives you an `(F, 180, 320) uint8` array directly |
| ffmpeg rawvideo pipe → 320 px gray | 6 fps | **1.33** | `fps=6` in the filter chain; ffmpeg drops before scaling |
| PyAV `decode()` only | 30 fps | 5.08 | slower than cv2 here |
| PyAV `decode()` + `to_ndarray('rgb24')` | 30 fps | 7.47 | 3× cv2; do not use it as a default |

Once you have the gray array, the cheap signals are free:

```
frame-diff energy over (1801, 180, 320)      0.125 s   [verified]
301×301 cosine self-similarity on raw gray   0.23  s   [verified]
```

**Recommendation.** Make the decoder a seam with an ffmpeg-pipe default, not cv2:

```python
def gray_frames(path, *, rate_hz=6.0, width=320) -> tuple[np.ndarray, np.ndarray]:
    """(F, H, W) uint8 + (F,) times. One subprocess, no per-frame Python."""
```

Everything in §3, §4 and §6.1 can be computed from that one array. Pose and embeddings need colour
and more resolution, so they get their own reader.

**Gotcha [verified].** Importing both `cv2` and `av` in the same process prints
`objc[…]: Class AVFFrameReceiver is implemented in both …libavdevice.61… and …libavdevice.62…`.
It is a duplicate-symbol warning, not a crash, but it appears on stderr of every run and will
pollute any log you parse. Pick one.

---

## 3. Shot / scene cut detection

### 3.1 PySceneDetect

Not installed. `pip install scenedetect` (**0.7.1**, **BSD-3-Clause**, pure Python over OpenCV, no
model weights, fully offline). **[verified]**

```python
from scenedetect import detect, AdaptiveDetector, ContentDetector

scenes = detect("clip.mp4", AdaptiveDetector(), show_progress=False)
cuts = [
    s[0].seconds for s in scenes[1:]
]  # .seconds; get_seconds() is deprecated in 0.7
```

| Detector | Clip C (truth 15/30/45) | Clip B (truth 22.25/29.25/36.25/42.25/49.25) | s / min ⊕ |
|---|---|---|---|
| `ContentDetector()` (thr 27, default) | **1 of 3** — found only 15.0 | **0 of 5** — returned no scenes at all | 2.20 |
| `ContentDetector(threshold=15)` | 3 of 3, exact | 10 cuts, of which 2 are real boundaries (22.4, 29.53) | 2.04 |
| `AdaptiveDetector()` (default) | **3 of 3, exact** | same 10: 3.93, 9.03, 14.17, 16.57, 21.73, 22.4, 24.4, 29.53, 34.63, 53.13 | 2.34 |
| `HashDetector()` / `ThresholdDetector()` | — | 0 | ~2.0 |

Three things fall out of that table:

- **The default threshold of 27 is tuned for hard cuts in natural footage and silently returns
  nothing on graded or animated transitions.** Clip B has five unmistakable section changes and
  `ContentDetector()` at defaults returned an **empty list** — not one whole-video scene, an empty
  list. Any wrapper must treat "no scenes" as "detector declined", not "one scene". **[verified]**
- **`AdaptiveDetector` is the better default.** It matched `ContentDetector(15)` exactly on both
  clips without needing a hand-tuned threshold, at the same cost.
- **Even when it fires, it is answering the wrong question.** Eight of the 10 cuts on clip B are
  page-turn and panel animations *inside* a section. Cut detection tells you where the *picture* changed. It
  does not tell you where the *subject* changed. For that, §8.2.

### 3.2 When NOT to use it

- **Single-take, static-camera video** — the entire choreography-POC genre. There are no cuts.
  A cut detector on such a clip is 2.3 s spent to learn nothing, and worse, a low threshold will
  then fire on lighting flicker and on the subject crossing the frame.
- As a *segmenter* of a continuous performance. It is a *cut* detector.
- As a *first* pass on anything screen-recorded or motion-graphics-heavy: you will drown in
  transitions.

### 3.3 ffmpeg's own scene score — the cheapest novelty curve there is

Two recipes, both **[verified]**, no Python, no dependencies beyond ffmpeg:

```bash
# (a) thresholded cut times
ffmpeg -hide_banner -nostats -i clip.mp4 -an -vf "select='gt(scene,0.10)',showinfo" -f null - 2>&1 \
  | sed -n 's/.*pts_time:\([0-9.]*\).*/\1/p'

# (b) the WHOLE per-frame novelty curve, as a parseable file — this is the useful one
ffmpeg -hide_banner -nostats -v error -i clip.mp4 -an \
  -vf "select='gt(scene,0)',metadata=print:file=scene.txt" -f null -
# scene.txt alternates:  frame:0 pts:512 pts_time:0.0333333 / lavfi.scene_score=0.000760
```

On clip B, (b) cost **0.8 s** and produced 1587 scores. The **top 8 scores** were at
`29.37, 22.40, 21.73, 16.57, 53.13, 42.13, 0.13, 49.17` — which contains **4 of the 5 true section
boundaries** (22.25, 29.25, 42.25, 49.25) and misses only the low-contrast Timeline→Document change
at 36.25. Thresholded at 0.25 it found **nothing**; at 0.10, four events. **[verified]**

**Verdict:** ffmpeg's `scene` is a *weak but nearly free* novelty curve. Use it as a curve, never as
a detector, and never as your only boundary source. Its licence is ffmpeg's (LGPL/GPL depending on
build) but you are shelling out, not linking.

---

## 4. Motion energy and optical flow

### 4.1 Frame differencing — the one you should almost always start with

```python
g = gray_frames(path, rate_hz=30, width=320)[0].astype(np.int16)
energy = np.abs(np.diff(g, axis=0)).mean(axis=(1, 2))  # (F-1,)
```

**2.1 s decode + 0.13 s compute per minute.** **[verified]** It gives you a usable activity curve,
it is the input to the periodicity machinery in §6.3, and its ACF recovered clip C's 0.800 s period
with r=0.98. Its failure modes are exactly two, and both have a cheap fix:

- **A cut is a huge spike that poisons every downstream statistic.** On clip C, blanking ±2 frames
  around each known cut raised the ACF peak from r=0.915 to **r=0.983**. **[verified]** Always
  deglitch against your cut list before autocorrelating.
- **Camera motion swamps subject motion.** Frame diff cannot tell a pan from a dancer. If the camera
  moves, you need flow (§4.2) with global-motion compensation, or pose (§5) which is intrinsically
  subject-relative. `muvid.footage.scoring.motionbeat` already does camera-compensated motion
  envelopes — reuse it rather than rewriting.

### 4.2 Dense optical flow — Farneback

`cv2.calcOpticalFlowFarneback`, OpenCV 4.13 (**Apache-2.0**), CPU only. Already installed.

```python
flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
energy = np.hypot(flow[..., 0], flow[..., 1]).mean()
```

| Config | s / min ⊕ | Note |
|---|---|---|
| scale 0.4 (512 px), every frame | **28.99** | `kodokan.segment.optical_flow_energy` defaults |
| scale 0.4, every 5th frame | 7.46 | |
| scale 0.25 (320 px), every 2nd | 6.52 | best cost/quality point measured |

**[verified]** On clip C, the Farneback ACF found 0.800 s at **r=0.985** — the single cleanest
periodicity signal of everything tested, better than frame-diff and better than pose. It is
robust for exactly the reason it is expensive: it measures *displacement*, not *change*, so a
flicker or an exposure shift does not register.

**When NOT to use it.** At full frame rate on anything longer than a few minutes — 29 s/min is
0.48× realtime and it is not parallelised. Drop to 6 Hz first and check whether you lost anything;
on clip C the 6 Hz curve carried the period just as well.

### 4.3 RAFT — better flow, GPU-only in practice

`torchvision.models.optical_flow.raft_small / raft_large`, **BSD-3-Clause**, weights bundled with
torchvision (already installed, `Raft_Small_Weights.C_T_V2`). **[verified]**

```python
from torchvision.models.optical_flow import raft_small, Raft_Small_Weights
import torchvision.transforms.functional as TF

m = raft_small(weights=Raft_Small_Weights.DEFAULT).eval().to("mps")
a = TF.normalize(batch_t, [0.5] * 3, [0.5] * 3)
b = TF.normalize(batch_t1, [0.5] * 3, [0.5] * 3)
flow = m(a, b)[-1]  # (B,2,H,W); [-1] = final refinement iter
mag = flow.pow(2).sum(1).sqrt().mean(dim=(1, 2))
```

| Config | Device | s / min ⊖ |
|---|---|---|
| RAFT-small, 512 px, every frame | MPS | **35.5** |
| RAFT-small, 512 px, 6 Hz | MPS | 9.84 |
| RAFT-small, 512 px, 6 Hz | **CPU** | **141.1** |
| RAFT-large, 512 px, 6 Hz | MPS | 22.5 |

**[verified].** RAFT-small on MPS costs about the same as Farneback on CPU and is substantially more
accurate on large displacements and textureless regions. **RAFT on CPU is 14× slower than on MPS**
— it is an MPS-only option, and therefore a hard dependency on torch being present and healthy.

**When NOT to use it.** For an *energy envelope*, which is what alignment actually consumes. The
extra precision of RAFT is spent on the per-pixel field and then thrown away by the `.mean()`.
Reach for RAFT only when you need the field itself: global-motion estimation, subject-vs-camera
separation, or warping.

---

## 5. Pose estimation

### 5.1 What is installed

| | version | licence | device | in p12? |
|---|---|---|---|---|
| **mediapipe** Tasks `PoseLandmarker` | 0.10.35 | Apache-2.0 (code + models) | CPU (see 5.4) | yes |
| **rtmlib** → RTMPose/RTMDet ONNX | 0.0.15 | Apache-2.0 (rtmlib); OpenMMLab Apache-2.0 weights | CPU or **CoreML** | yes |
| **ultralytics** YOLO11-pose | 8.4.75 | **AGPL-3.0** ⚠ | MPS / CPU | yes |
| torchvision (for RAFT, 4DHumans backbones) | 0.24.0 | BSD-3 | MPS | yes |

⚠ **Ultralytics is AGPL-3.0.** Everything the fleet has built on YOLO11 so far (the POC's person
boxes, `kodokan`'s `ultralytics` backend) is fine for internal use, but if any of this ships as a
hosted surface, AGPL §13 reaches the network-served code. `mixing.audio.beats` already excluded
`madmom` on exactly this ground — be consistent: **make YOLO an opt-in backend, never the default.**
rtmlib + mediapipe are both Apache-2.0 and cover the same ground.

### 5.2 A real snippet: video → `(F, K, 3)` keypoint array

mediapipe Tasks, the current API (**[verified]** — this exact code produced `(1801, 33, 4)`):

```python
import cv2, numpy as np, mediapipe as mp
from mediapipe.tasks import python as mpp
from mediapipe.tasks.python import vision

opts = vision.PoseLandmarkerOptions(
    base_options=mpp.BaseOptions(model_asset_path="pose_landmarker_full.task"),
    running_mode=vision.RunningMode.VIDEO,  # VIDEO gives temporal smoothing + tracking
    num_poses=1,
)
lm = vision.PoseLandmarker.create_from_options(opts)

cap = cv2.VideoCapture(path)
fps = cap.get(cv2.CAP_PROP_FPS)
out, n = [], 0
while True:
    ok, frame = cap.read()
    if not ok:
        break
    img = mp.Image(
        image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    )
    r = lm.detect_for_video(img, int(n / fps * 1000))  # timestamp in ms, must increase
    out.append(
        [[p.x, p.y, p.z, p.visibility] for p in r.pose_landmarks[0]]
        if r.pose_landmarks
        else [[np.nan] * 4] * 33
    )
    n += 1
kp = np.asarray(
    out, np.float32
)  # (F, 33, 4); x,y are NORMALISED 0..1, z is relative depth
lm.close()
cap.release()
```

Models are **not** bundled — download once (Apache-2.0, ~6/9/31 MB):

```bash
B=https://storage.googleapis.com/mediapipe-models/pose_landmarker
for m in lite full heavy; do curl -L -o pose_landmarker_$m.task $B/pose_landmarker_$m/float16/latest/pose_landmarker_$m.task; done
# hands + the canned gesture classifier, same pattern:
curl -L -o hand_landmarker.task     https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task
curl -L -o gesture_recognizer.task  https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/latest/gesture_recognizer.task
```

The other two backends, both already wrapped by `kodokan.pose` with a COCO-17 output contract:

```python
from rtmlib import Body  # RTMDet + RTMPose, ONNX, auto-downloads to ~/.cache/rtmlib

body = Body(
    mode="lightweight", backend="onnxruntime", device="mps"
)  # "mps" -> CoreMLExecutionProvider
kpts, scores = body(frame_bgr)  # (n,17,2), (n,17)

from ultralytics import YOLO  # AGPL

r = YOLO("yolo11n-pose.pt")(
    frames_list, device="mps", verbose=False
)  # pass a LIST -> batched
kp = r[0].keypoints.data.cpu().numpy()  # (n,17,3)
```

### 5.3 Cost, on clip A, one person **[verified]**

| Backend | model | rate | device | s / min | detection rate |
|---|---|---|---|---|---|
| mediapipe | lite | 30 fps | CPU | **22.2** ⊕ | 1800/1801 |
| mediapipe | full | 30 fps | CPU | 34.8 ⊕ | 1798/1801 |
| mediapipe | full | 6 fps | CPU | 12.3 ⊕ | 361/361 |
| mediapipe | heavy | 30 fps | CPU | **134.6** ⊕ | 1801/1801 |
| mediapipe | lite | 30 fps | **GPU delegate** | **45.6** ⊕ | 1800/1801 |
| rtmlib | lightweight | 6 fps | CPU | 28.1 ⊕ | 361/361 |
| rtmlib | lightweight | 6 fps | **mps/CoreML** | **10.9** ⊕ | 361/361 |
| rtmlib | balanced | 6 fps | CPU | **138.3** ⊕ | 361/361 |
| rtmlib | balanced | 6 fps | mps/CoreML | 23.2 ⊕ | 361/361 |
| ultralytics | yolo11n-pose, one frame at a time | 30 fps | MPS | 33.0 ⊕ | 1801/1801 |
| ultralytics | **yolo11n-pose, batched ×16** | 30 fps | MPS | **19.2** ⊕ | 1801/1801 |
| ultralytics | yolo11s-pose, batched ×16 | 30 fps | MPS | 23.5 ⊕ | 1801/1801 |
| ultralytics | yolo11n-pose | 6 fps | CPU | 17.5 ⊕ | 361/361 |

**Fastest full-rate pose on this machine: YOLO11n-pose, batched, MPS — 19.2 s/min** (0.32× realtime),
but AGPL. **Fastest Apache-2.0 full-rate pose: mediapipe lite on CPU — 22.2 s/min.** At 6 Hz, which
is enough for every alignment purpose in §6, **rtmlib lightweight on CoreML at 10.9 s/min** wins and
gives you COCO-17 and multi-person for free.

### 5.4 Four gotchas that cost me an hour each

1. **`mp.solutions` no longer exists.** In mediapipe 0.10.35 there is no `mediapipe.solutions`, no
   `mediapipe.python.solutions`, no `mp.solutions.pose`, no `Holistic` legacy solution. Every
   tutorial older than ~2024 is dead code. The Tasks API is the only API; it does have
   `vision.HolisticLandmarker`, plus `PoseLandmarker`, `HandLandmarker`, `FaceLandmarker`,
   `GestureRecognizer`, `ObjectDetector`, `ImageSegmenter`, `ImageEmbedder`. **[verified]**
2. **mediapipe's GPU delegate is a trap on macOS.** With `Delegate.GPU` and an `SRGB` image it does
   not raise — it **aborts the process** with
   `Check failed: status_or_buffer is OK (UNKNOWN: unsupported ImageFrame format: 1)`. Feed it
   `ImageFormat.SRGBA` (`cv2.COLOR_BGR2RGBA`) and it runs — and is then **2× slower than the CPU
   path** (45.6 s vs 22.2 s). Do not offer a GPU option for mediapipe on Apple Silicon. **[verified]**
3. **`rtmlib`'s `device` argument is worth 6×.** `device="mps"` maps to `CoreMLExecutionProvider`
   (see `rtmlib/tools/base.py::check_mps_support`), and onnxruntime 1.23.1 in this env does expose
   `CoreMLExecutionProvider`. `balanced` mode goes from 138.3 s to 23.2 s. **`kodokan.pose` passes
   `device or "cpu"` for the rtmlib backend** — that default is leaving 6× on the table and should
   be changed to auto-detect. **[verified]**
4. **Ultralytics only batches if you hand it a list.** `model(frame)` in a loop is 33 s/min;
   `model(list_of_16_frames)` is 19.2 s/min. Same weights, same device. **[verified]**

### 5.5 3-D pose — what it would take

**[from docs]**, none of it installed:

| Option | Install | Reality on this Mac |
|---|---|---|
| mediapipe `world_landmarks` | already there | free with the 2-D call; a metric-ish root-relative skeleton, weak absolute depth. **Try this first** — it is one attribute away. |
| `rtmlib.RTMPose3d` / `Wholebody3d` | already there (`from rtmlib import RTMPose3d`) | ONNX, so CoreML applies. Unverified here; the class exists in 0.0.15. |
| **4DHumans / HMR2.0** | conda-ish repo install, PyTorch, SMPL body model behind a registration wall | SMPL is **non-commercial** for the standard licence. Heavy (~seconds/frame). A research detour, not a v1 seam. |
| `kodokan.canon3d` | in-fleet, 105 lines | already exists; read it before adding anything. |

**Recommendation.** Do not put 3-D in v1. The one thing 3-D actually buys for alignment is
viewpoint-invariant movement comparison (§6.5) — and `kodokan.compare` already documents that
limitation honestly. Leave a `features=` seam and fill it later.

---

## 6. From pose to segmentation — the part that is least documented

This is where the brief is right that the ground is thin. Here is what survives contact.

### 6.1 Motion energy from pose

```python
xy, conf = kp[..., :2], kp[..., 2]  # (F,P,K,2), (F,P,K)
disp = np.linalg.norm(np.diff(xy, axis=0), axis=-1)  # (F-1,P,K)
w = np.minimum(conf[1:], conf[:-1])
w[w < 0.2] = 0
energy = np.concatenate(
    [[0], np.nansum(disp * w, (1, 2)) / (np.nansum(w, (1, 2)) + 1e-9)]
)
```

That is `kodokan.segment.pose_motion_energy` verbatim, and it is correct: confidence-weighted,
NaN-tolerant, normalised by present-keypoint mass so a dropped person does not read as stillness.
**Take it as-is.** The only thing missing is *scale normalisation* — displacement in pixels means a
subject who walks toward the camera reads as more energetic. Divide by torso length
(`‖shoulder_mid − hip_mid‖`) per frame before summing. **[inferred]**

Pose energy vs flow energy: **pose is subject-relative and free of camera motion; flow is denser and
does not need a person.** Fuse them (`kodokan.segment.segment_demonstrations(use_optical_flow=True)`
already does, by min-max normalising each and averaging) rather than choosing.

### 6.2 Hysteresis runs — high-motion spans as segments

`kodokan.segment.find_segments` turns a 1-D energy curve into intervals with a two-threshold
hysteresis (on above `high_quantile=0.5`, off below `low_quantile=0.25`), gap-merging and a minimum
duration. This is the right shape and it is already written. Two notes:

- **Quantile thresholds are relative to the clip.** On a clip that is uniformly active it will
  invent boundaries; on a clip with one burst it will find one segment. That is fine for
  "demonstrations separated by resets" and wrong for "continuous choreography". Expose absolute
  thresholds as an alternative. **[inferred]**
- **"Motion energy minima = pose transitions" is real but weak.** It holds when the movement
  vocabulary has genuine stops (judo demos, exercise reps, craft steps between tool changes). It
  fails on anything continuous — dance, walking, talking-with-hands — where the minima are noise.
  Do not sell it as a general segmenter; sell it as a *hypothesis generator* whose output feeds the
  assignment step in §11.

### 6.3 Periodicity — the thing that works best, and is nearly free

Autocorrelate any motion curve. Validated against clip C's exact 0.800 s ground truth **[verified]**:

| curve | top ACF peaks (period s, r) | recovered? |
|---|---|---|
| frame-diff | 0.800 (0.915), 1.600, 2.400 | ✓ |
| frame-diff, cuts deglitched | **0.800 (0.983)** | ✓ |
| Farneback | **0.800 (0.985)**, 1.600, 2.400 | ✓ |

```python
def acf_periods(x, rate_hz, *, lo_s=0.3, hi_s=3.0, sigma=1.0, k=3):
    x = gaussian_filter1d(np.asarray(x, float), sigma)
    x -= x.mean()
    a = np.correlate(x, x, "full")[x.size - 1 :]
    a /= a[0] + 1e-12
    lo, hi = int(lo_s * rate_hz), min(int(hi_s * rate_hz), len(a) - 1)
    pk, _ = find_peaks(a[lo:hi])
    pk += lo
    top = pk[np.argsort(a[pk])[::-1]][:k]
    return [(float(l / rate_hz), float(a[l])) for l in top]
```

That is `kodokan.segment.estimate_period` generalised to return the top-k rather than the argmax —
**return the top-k, because the harmonics are the point.** On clip C the peaks are 0.800/1.600/2.400;
the true unit is the shortest, but which harmonic is the *musically meaningful* one (beat vs bar vs
8-count) is exactly the ambiguity the POC resolved with a duration sanity check. Hand the caller all
three and let the audio side disambiguate.

On real pose from clip A, mediapipe-full and YOLO11n — two completely independent pipelines —
agreed on the top wrist-trajectory ACF peak to the sample: **0.767 s, r = 0.371 and 0.398
respectively**, with the same second peak at 1.500 s. **[verified]** Cross-backend agreement on
the ACF peak is a cheap and strong confidence signal; use it.

**Caveats, all [verified] on real data:**
- Position curves (`wrist_y`) autocorrelate far more strongly than derivative curves
  (`|Δwrist|`, r 0.37 vs 0.11). **Autocorrelate positions and angles, not speeds.**
- Whole-body motion energy is a *worse* periodicity signal than a single well-chosen joint
  (r 0.15 vs 0.37 on the same clip). Periodicity wants a **specific** channel — pick the joint with
  the highest ACF peak rather than averaging the body.
- **RepNet** (Dwibedi et al., CVPR 2020, class-agnostic repetition counting from a temporal
  self-similarity matrix) is the published version of this. The original is TensorFlow/Colab;
  PyTorch reimplementations exist but none is a maintained pip package. **[from docs]** The 20-line
  ACF above got the exact right answer on ground truth, so **do not take the dependency.** The one
  thing RepNet adds is robustness to *varying* period, which ACF genuinely cannot do — note it as a
  future backend behind the same `periods()` seam.

### 6.4 Phase — automating "the landmark read off a contact sheet"

The POC's step 3 was: tempo gives spacing, but you still need an offset, so a human found a visible
periodic landmark on a contact sheet. Here is that, automated, validated on clip C **[verified]**:

```python
# 1. a visual "onset" curve: half-wave-rectified deceleration -> impact spikes
env = gaussian_filter1d(motion_curve, 1.0)
onset = np.maximum(np.diff(env, prepend=env[0]), 0)

# 2. impacts
pk, _ = find_peaks(onset, height=np.quantile(onset, 0.90), distance=int(0.2 * rate_hz))
hits = pk / rate_hz


# 3. sweep the offset against the audio beat grid, maximise a soft alignment score
def bas(a, b, sigma=0.06):  # AIST++ Beat Alignment Score, localized
    return float(
        np.mean(
            [np.exp(-0.5 * ((t - b[np.argmin(np.abs(b - t))]) / sigma) ** 2) for t in a]
        )
    )


offsets = np.linspace(-0.4, 0.4, 81)
best = offsets[int(np.argmax([bas(hits + o, beat_times) for o in offsets]))]
```

Result on clip C (ground truth: impacts every 0.800 s, click track 150 bpm):

```
visual impact peaks:  n=75, median gap 0.800 s        (truth 0.800)  ✓
librosa.beat.beat_track driven by the VISUAL envelope -> 75.0 bpm, median gap 0.800 s  ✓
BAS(visual hits -> audio beats), sigma=.06: 0.946   null 0.377 +- 0.044   z = +12.9
phase sweep: best offset +0.020 s -> BAS 0.992
```

Two reusable tricks in there:

- **`librosa.beat.beat_track` works on a non-audio onset envelope.** Pass
  `onset_envelope=visual_curve, sr=22050, hop_length=int(round(22050/video_fps))` and it returns
  times in seconds on the video clock. You get librosa's whole tempo-and-phase DP for free on a
  visual signal. **[verified]** (`librosa` 0.11.0, **ISC**, already installed.)
- **Always compute the null.** BAS against a *dense* beat grid is high by construction: with
  σ=0.12 s and beats every 0.4 s, uniformly random "hits" already score 0.69. Report
  `z = (BAS − mean(null)) / sd(null)` over ~300 shuffles, not BAS. **[verified]**

**The honest negative.** The same pipeline run on clip A's real wrist trajectories produced
**z = +1.0 at σ=0.06** — i.e. no significant alignment between visual impacts and the audio beat,
and a visual tempo estimate of 106–129 bpm against an audio tempo of 152. **[verified]** Whether
that is the subject genuinely not moving on the beat or the method failing, I cannot tell from one
clip — which is the point: **this method must report its own null-hypothesis z and refuse to answer
below a threshold.** A phase estimate with z < 2 is not an answer.

### 6.5 Matching a known movement against the stream — subsequence DTW

`dtaidistance` 2.4.0 (**Apache-2.0**), already installed. `kodokan.compare` already builds COCO-17
joint-angle features and DTW-compares two clips; what it lacks is the *subsequence* form, which is
the one alignment needs.

```python
from dtaidistance.subsequence.dtw import subsequence_alignment

sa = subsequence_alignment(
    query_feats, stream_feats
)  # both (T, D) float64, C-contiguous
best = sa.best_match()
t0, t1 = best.segment[0] / rate_hz, best.segment[1] / rate_hz
for m in sa.kbest_matches(k=6):
    ...
```

**[verified]** on 8-D joint-angle features from clip A: a 2 s query against a 60 s stream costs
**0.35 s** (0.11 M DTW cells) and finds itself exactly (`value 0.000`, segment identical). A full
pairwise DTW distance matrix over sixty 1-second tiles costs **10.0 s** — O(n²), so tile-clustering
does not scale past a couple of minutes without pruning.

**The failure mode you must handle:** unnormalised subsequence DTW **prefers short matches**. Every
`kbest_matches` hit after the self-match was 0.7–1.6 s long against a 2 s query, because a shorter
path accumulates less cost. **[verified]** Fixes, in order of cheapness: (a) constrain the match
length to `[0.7, 1.4] × len(query)` and re-rank by cost/length; (b) use a Sakoe–Chiba band;
(c) z-normalise each feature channel over the query window (the UCR-suite `window`/`psi` idea).
Do not ship raw `best_match()`.

**When NOT to use DTW.** When you do not already have a *reference performance* of the movement.
DTW answers "where does this known thing recur", not "what are the things". For the latter you want
§8. And remember `kodokan.compare`'s own honest caveat: **2-D joint angles are not viewpoint
invariant**, so a query shot from a different angle reads as a different movement.

### 6.6 Clustering into motion primitives — the one to be sceptical of

The literature move is: window the pose feature stream, embed, cluster (k-means / GMM / HDBSCAN),
call the clusters "primitives", and read segment boundaries off cluster changes. **[from docs]** It
is a paper technique. In practice, on the kind of material reelee handles:

- Cluster count is unknown and the result is extremely sensitive to it.
- Clusters latch onto *pose* (standing / seated / arms up) rather than *movement*.
- The boundaries it produces are not the boundaries a human annotator would draw, and there is no
  way to steer it toward them.

**[inferred]** Skip it in v1. The steerable version of the same idea — "give me a text description
and I will find the span" — is §8, it costs less, and it is verifiable against a written document,
which is exactly the input the reelee use case already has.

---

## 7. Gesture and action recognition off the shelf

### 7.1 mediapipe `GestureRecognizer`

**[verified]** on clip A, 30 fps, CPU: **56.5 s / min**, hand detected in 88% of frames. The label
distribution it returned over the whole clip:

```
{'None': 1909, 'Thumb_Up': 394, 'Closed_Fist': 34, 'Thumb_Down': 11, 'Open_Palm': 1}
```

The vocabulary is fixed and tiny: `None, Closed_Fist, Open_Palm, Pointing_Up, Thumb_Down, Thumb_Up,
Victory, ILoveYou`. **Two thirds of hand-frames are `None`.** For any domain gesture — a dance
move, a knife cut, a knot — the answer is always `None`. It is a UI-control classifier.

It *does* ship a retraining path (`mediapipe_model_maker`, few-shot on top of the frozen hand
embedding). **[from docs]** If a subgenre ever needs 5–10 named hand shapes and you can label a few
hundred frames, that is the cheapest custom classifier on offer. Not v1.

### 7.2 Video-text models: X-CLIP tested, and it lost

`microsoft/xclip-base-patch32` (197 M params, **MIT**), zero-shot over 8-frame clips every 3 s on
clip B, MPS: **3.29 s for 20 clips = 3.3 s/min, 165 ms/clip.** Cheap. **[verified]**

And wrong. Against five text prompts describing clip B's five sections, it answered
"a gallery grid of thumbnails" for 13 of 20 windows and "a text document" for 7, getting only the
Document section (36–42 s) right. Boundaries: none recoverable.

Integration friction worth recording **[verified]**: in transformers 4.57 `XCLIPProcessor.__call__`
**silently drops** the `videos=` argument — you get back only `input_ids`/`attention_mask` and the
model then fails with `AttributeError: 'NoneType' object has no attribute 'shape'`. The workaround
is to call the video processor positionally and rename the key:

```python
px = proc.video_processor(
    [list_of_8_frames], return_tensors="pt"
)  # positional, not videos=
out = model(
    input_ids=tk["input_ids"],
    attention_mask=tk["attention_mask"],
    pixel_values=px["pixel_values"].to("mps"),
)
p = out.logits_per_video.softmax(-1)
```

**VideoMAE / TimeSformer / V-JEPA 2 [from docs, not run]:** all are Kinetics-400/600 classifiers or
self-supervised video encoders. Kinetics labels are "playing drums", "tai chi", "cutting
watermelon" — a 400-word closed vocabulary of *generic* human activities. Nothing in it names a
dance block, a craft step, or a section of a UI tour. `MCG-NJU/videomae-base` weights are
**CC-BY-NC-4.0** — non-commercial, which alone should end the conversation for a shipped package.

**Verdict on the whole category.** For *this* problem — align written artifacts to spans —
per-frame image-text embeddings (§8) beat video-clip models decisively at comparable cost, are
open-vocabulary, need no temporal window tuning, and give you a per-frame curve you can feed to a
constrained assigner. **Do not put an action-recognition model in v1.** If a subgenre later needs
true temporal discrimination (distinguishing "sitting down" from "standing up", which a per-frame
model genuinely cannot), that is the moment to revisit, and V-JEPA 2 is the one to try first.

---

## 8. Frame embeddings — the actual answer

This is the method the POC was missing and it is the one that should be built first.

### 8.1 Cost **[verified]**, clip B, MPS

| Model | dim | rate | device | s / min ⊖ | licence | cached in ~/.cache/huggingface? |
|---|---|---|---|---|---|---|
| `google/siglip2-base-patch16-224` | 768 | 2 Hz | MPS | **1.57** | Apache-2.0 | **yes** |
| `google/siglip2-base-patch16-224` | 768 | 6 Hz | MPS | **4.38** | Apache-2.0 | yes |
| `google/siglip2-base-patch16-224` | 768 | 2 Hz | CPU | 6.16 | Apache-2.0 | yes |
| `openai/clip-vit-base-patch32` | 512 | 2 Hz | MPS | 1.73 | MIT | yes |
| `google/siglip2-so400m-patch14-384` | 1152 | — | — | not benchmarked | Apache-2.0 | yes |
| `facebook/dinov2-base` | 768 | — | — | not benchmarked | Apache-2.0 | yes |

Text encoding is negligible: **0.15 s for 6 prompts.** Model load is 3.2–3.6 s and is the dominant
cost on short clips — cache the model, not the embeddings.

```python
from transformers import AutoProcessor, AutoModel
import torch, numpy as np

mid = "google/siglip2-base-patch16-224"
proc, m = (
    AutoProcessor.from_pretrained(mid),
    AutoModel.from_pretrained(mid).eval().to("mps"),
)

with torch.inference_mode():  # images
    px = proc(images=rgb_frames_batch, return_tensors="pt").to("mps")
    E = (
        torch.nn.functional.normalize(m.get_image_features(**px), dim=-1)
        .float()
        .cpu()
        .numpy()
    )

with torch.inference_mode():  # text
    tk = proc(
        text=prompts, padding="max_length", return_tensors="pt"
    )  # SigLIP needs max_length
    T = torch.nn.functional.normalize(m.get_text_features(**tk), dim=-1).numpy()

S = E @ T.T  # (n_frames, n_artifacts) cosine score matrix — THE evidence matrix
```

`padding="max_length"` is mandatory for SigLIP/SigLIP2 (unlike CLIP) — the text tower is trained
with a fixed 64-token context. **[from docs, and required to make the above run]**

### 8.2 Boundaries: Foote novelty over the embeddings

No text, no artifacts, no labels — just "where does the picture stop meaning the same thing".

```python
D = E @ E.T  # (F,F) cosine self-similarity
K = int(2.0 * rate_hz)  # half-kernel, 2 s
nov = np.zeros(len(E))
for i in range(K, len(E) - K):
    a, b = slice(i - K, i), slice(i, i + K)
    nov[i] = D[a, a].mean() + D[b, b].mean() - 2 * D[a, b].mean()
peaks, _ = find_peaks(
    nov, height=np.quantile(nov[nov > 0], 0.85), distance=int(3 * rate_hz)
)
```

Clip B, SigLIP2 at 6 Hz, ground truth boundaries **22.25 / 29.25 / 36.25 / 42.25 / 49.25 s**
(established independently, §10.3):

| Method | boundaries found | error |
|---|---|---|
| **SigLIP2 novelty, K = 2 s** | **22.5, 29.5, 36.5, 42.2, 49.2** (+ one FP at 53.2) | **≤ 0.3 s on all five** |
| SigLIP2 novelty, K = 1 s | 16.7, 22.5, 29.5, 36.5, 42.2, 49.2, 53.2 | all five, +2 FP |
| SigLIP2 novelty, K = 4 s | identical to K = 2 s | — |
| ffmpeg `lavfi.scene_score`, top-8 | 22.4, 29.4, 42.1, 49.2 | 4 of 5, misses 36.25 |
| PySceneDetect `AdaptiveDetector` | 3.93, 9.03, 14.17, 16.57, 21.73, **22.4**, 24.4, **29.53**, 34.63, 53.13 | **2 of 5** (22.4, 29.53); misses 36.25/42.25/49.25; 8 FPs |
| PySceneDetect `ContentDetector()` default | *none* | 0 of 5 |

**[verified].** This is the headline result of the file. Five semantic boundaries, located to
within a third of a second, for 4.4 s of compute per minute, offline, Apache-2.0, from a model
already in the cache. `K` barely matters between 2 and 4 s. Note that `mixing.audio.segmentation`
already implements Foote checkerboard novelty for audio self-similarity — **this is the same
function with a different feature matrix**, which is an argument for making the novelty operator
modality-agnostic in the new package rather than writing a second one.

### 8.3 Assignment: the order prior is what makes it accurate

Given the score matrix `S` (frames × artifacts) and the fact that the artifacts occur **in order and
do not overlap**, this DP finds the boundaries:

```python
S = (S - S.mean(0)) / (S.std(0) + 1e-9)  # z per artifact over time
S = S - S.mean(
    1, keepdims=True
)  # contrastive: subtract the per-frame mean over artifacts
S = uniform_filter1d(S, size=int(rate_hz), axis=0)
cum = np.vstack([np.zeros(Q), np.cumsum(S, 0)])
dp = np.full((Q, F + 1), -1e9)
bk = np.zeros((Q, F + 1), int)
for q in range(Q):
    for f in range((q + 1) * MIN, F + 1):
        starts = np.arange(q * MIN, f - MIN + 1)
        val = (0 if q == 0 else dp[q - 1, starts]) + (cum[f, q] - cum[starts, q])
        j = int(np.argmax(val))
        dp[q, f] = val[j]
        bk[q, f] = starts[j]
# backtrack from f=F
```

Both normalisation steps matter. The z-step removes each prompt's intrinsic bias (some phrasings
score higher against everything); the contrastive step turns absolute similarity into *relative*
evidence, which is what the DP should be maximising.

Result on clip B, five ordered prompts, min span 2 s **[verified]**:

| Assigned span | Truth | Error |
|---|---|---|
| 0.0 – **22.2** s — *"a page from a picture book with one photo and a caption"* | 0 – 22.25 | **0.05 s** |
| 22.2 – **29.5** s — *"a grid gallery of many image thumbnails"* | 22.25 – 29.25 | **0.25 s** |
| 29.5 – **36.5** s — *"a video editing timeline with clips laid out in tracks"* | 29.25 – 36.25 | **0.25 s** |
| 36.5 – **42.3** s — *"a page of written prose text, a script document"* | 36.25 – 42.25 | **0.05 s** |
| 42.3 – 59.8 s — *"a node graph diagram with boxes connected by lines"* | 42.25 – 49.25 | end overruns |

Four of five boundaries within a quarter-second. The last span overruns because the video **returns
to the first view at 49.25 s** and the artifact list did not include a second entry for it — the DP
is required to cover the timeline, so it stretched the last artifact. That is not a bug in the DP,
it is the **coverage assumption** being wrong, and it is a design decision the package must expose:
*must the artifacts tile the media, or may there be unassigned gaps?* Both are one line of DP apart
(add a "no artifact" state with a fixed score).

**Contrast with argmax.** The same score matrix, read greedily per artifact (best 4 s window),
across six prompts:

| Prompt | argmax window | Correct? |
|---|---|---|
| "a grid gallery of image thumbnails" | 23.5 – 27.5 s | ✓ |
| "a video editing timeline with clips" | 30.5 – 34.5 s | ✓ |
| "a node graph network diagram…" | 43.5 – 47.5 s | ✓ |
| "a page of written text, a document" | 37.5 – 41.5 s | ✓ (1 s late) |
| "a storyboard of shot cards" | 37.5 – 41.5 s | ✗ (truth 0–22 and 49–60) |
| **"a kanban board with cards in columns"** | 43.5 – 47.5 s, peak z **+0.95** | ✗ — **there is no kanban view in this clip at all** |

**[verified].** That last row is the most important line in this document. **An artifact with no
true span still produces a confident-looking argmax.** Any alignment API must have a *reject*
option — a per-artifact null score, or a calibrated "no match" threshold from the score
distribution — or it will confabulate a timestamp for every artifact you hand it, including the
ones that are not in the video.

### 8.4 When NOT to use embeddings

- **When the spans look identical.** Nine dance blocks shot in one take against one wall are, to
  SigLIP2, the same image. Embedding novelty will find nothing, correctly. That genre needs pose
  periodicity (§6.3) and audio (file 02).
- **When the artifact text is not visually descriptive.** "Block 4" carries no signal. The method
  needs a *description*, which means either the source document has one or an LLM writes one first.
- **As the only evidence.** It is one curve among several. Fuse.

---

## 9. Hand / object interaction — the craft and cooking subgenres

**[verified]** costs on clip A / clip B, 30 fps:

| Method | s / min | Licence | Output |
|---|---|---|---|
| mediapipe `HandLandmarker`, 2 hands, CPU | **55.6** ⊕ | Apache-2.0 | 21 landmarks/hand + handedness; hand present in 88% of frames |
| mediapipe `GestureRecognizer` | 56.5 ⊕ | Apache-2.0 | the above + an 8-class label (§7.1) |
| `yolo11n.pt` detect, batched ×16, MPS | **11.8** ⊖ | **AGPL-3.0** | COCO-80 boxes |
| `yolo11s.pt` detect, batched ×16, MPS | 16.4 ⊖ | AGPL-3.0 | COCO-80 boxes |

Object detection is **cheaper than pose** and much cheaper than hands. The "tool changed = step
boundary" idea is therefore affordable: run YOLO at 2–6 Hz, build a per-class presence curve, and
feed the *change points of the class-presence vector* into the same novelty/DP machinery as §8.
The class vector is a low-dimensional embedding; nothing new is needed.

**Two cautions, one of them verified.** COCO-80 does not contain the objects craft videos are about
— no needle, no chisel, no whisk, no yarn. And small detectors hallucinate on non-natural imagery:
on clip B (a screen recording) `yolo11n` reported **1455 `tv`** and 340 `person`, while `yolo11s` on
the identical frames reported **1402 `person`** and 52 `tv`. **[verified]** Two model sizes from the
same family, opposite answers. If you want objects that matter, the honest options are an
open-vocabulary detector (OWLv2, Grounding DINO — **[from docs]**, neither installed, both heavier
than everything above) or, again, §8's text-image similarity on a hand-region crop.

**Recommendation [inferred].** For craft/cooking, the ordering that pays is:
hand-presence curve (cheap, from `HandLandmarker` confidence, no landmark analysis) →
novelty on SigLIP2 embeddings of a **crop around the hands** → the §8.3 DP against the written
steps. Full hand landmark kinematics is a later refinement, not a v1 seam.

---

## 10. OCR and on-screen text

### 10.1 tesseract, which is what you already have

`tesseract 5.5.2` (Homebrew, **Apache-2.0**) + `pytesseract` 0.3.13, both installed. **[verified]**

| Config | ms / frame | s / min at 1 Hz |
|---|---|---|
| full 720p frame, `--psm 6` | 573 | 34.4 |
| full 720p frame, `--psm 11` (sparse) | 564 | 33.8 |
| **60 px-tall band, upscaled ×3, `--psm 7`** | **240** | **14.4** |
| same band, ×3 + Otsu threshold | 230 | 13.8 |

Quality on the same frame, which matters more than the timing:

```
full 720p           'DG REELEE see Storyboard Timeline Document Kanban Gallery Network Inspector [PROJECT] » Search'
full 720p ×2        '© 6 REELEE nee Storyboard Timeline Document Kanban Gallery Network Inspector wb PROJECT e Searc'
top band (no scale) ''                                       <- empty; tesseract needs ~30 px cap height
top band ×3         '* .,e2e- q © O REELEE Bag ace Storyboard Timeline Document Kanban Gallery Network Inspector © P'
top band ×3 + Otsu  '* ,e2e- . © O REELEE project Storyboard Timeline Document Kanban Gallery Network Inspector wD P'
```

**The rules, all [verified] above:** (1) crop to the region you care about — it is 2.4× faster *and*
more accurate; (2) upscale ≥3× with `INTER_CUBIC` — 720p UI text is below tesseract's working size
and un-upscaled crops return the empty string; (3) Otsu-threshold light-on-dark UI; (4) pick the
right `--psm` (7 = single line, 6 = block, 11 = sparse).

### 10.2 EasyOCR / PaddleOCR — **[from docs]**, neither installed

| | install | licence | Apple Silicon | when |
|---|---|---|---|---|
| **EasyOCR** | `pip install easyocr` (pulls its own torch models, ~100 MB on first run) | Apache-2.0 | works on MPS via torch | scene text, angled text, non-Latin scripts; much better than tesseract on video frames, ~3–5× slower on CPU |
| **PaddleOCR** | `pip install paddleocr paddlepaddle` | Apache-2.0 | paddlepaddle wheels for arm64 macOS have historically been the friction point — verify before committing | best accuracy of the three on dense/rotated text; the heaviest install |

**[inferred]** Do not take either as a dependency in v1. Ship tesseract (already present, zero new
deps) behind an `ocr=` seam, and name EasyOCR as the intended second backend so the seam has a real
target rather than being speculative.

### 10.3 The trick worth stealing: OCR as a ground-truth generator

The five true section boundaries used throughout §8 were not hand-annotated. They came from 30 lines
that OCR the page heading at 2 Hz and run-length-encode the result **[verified]**:

```python
band = frame[85:145, 150:700]  # where the big heading lives
g = cv2.resize(
    cv2.cvtColor(band, cv2.COLOR_BGR2GRAY),
    None,
    fx=3,
    fy=3,
    interpolation=cv2.INTER_CUBIC,
)
label = next(
    (w for w in VOCAB if w in pytesseract.image_to_string(g, config="--psm 7").lower()),
    None,
)
```

```
0.0 – 22.0 s  picture      22.5 – 29.0 s  gallery    29.5 – 36.0 s  timeline
36.5 – 42.0 s document     42.5 – 49.0 s  network    49.5 – 59.5 s  picture
```

Any video that burns in a step title, a chapter card, a slide number or a UI heading is
**self-labelling**. That is not a fallback method, it is the *best* method when it applies: exact,
cheap, and it produces the evaluation set that everything else in this file is scored against.
The package should look for it first and short-circuit.

---

## 11. The facade shape

Every method above is one of exactly four things. That is the whole interface.

```python
# ── the currency ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Curve:
    """One evidence signal on the media clock. 1-D or (T, D)."""

    values: np.ndarray  # (T,) or (T, D)
    t0: float  # seconds of values[0]
    hop_s: float  # seconds between samples
    name: str  # 'motion_energy', 'siglip2', 'scene_score', 'pose_kp'
    mask: np.ndarray | None = None  # (T,) bool: where the signal is valid

    def times(self) -> np.ndarray: ...


Span = tuple[float, float]  # half-open seconds; lacing.TimeInterval at the edges


# ── the four verbs ────────────────────────────────────────────────────────────
class Featurizer(Protocol):
    """media -> a Curve. §2-§5, §8.1, §9. Every visual method is one of these."""

    def __call__(
        self, media: MediaRef, *, span: Span | None = None, rate_hz: float = 6.0
    ) -> Curve: ...


class Boundarizer(Protocol):
    """Curve -> candidate boundary times. §3, §6.2, §8.2."""

    def __call__(self, curve: Curve, **kw) -> list[float]: ...


class Scorer(Protocol):
    """(artifacts, Curve) -> (T, n_artifacts) evidence. §6.5, §8.1, §10."""

    def __call__(self, artifacts: Sequence[Artifact], curve: Curve) -> Curve: ...


class Assigner(Protocol):
    """evidence + constraints -> one Span per artifact, or None. §8.3."""

    def __call__(
        self,
        evidence: Curve,
        *,
        ordered: bool = True,
        overlap: bool = False,
        cover: bool = True,
        min_dur_s: float = 0.0,
        snap_to: Sequence[float] | None = None,
    ) -> list[Span | None]: ...
```

Five design points that the measurements force:

1. **`rate_hz` is the master cost knob, and it belongs on the *interface*, not inside each method.**
   Every table in this file is really a table of "cost per sample × sample rate". Making it a
   uniform keyword lets the agent surface trade accuracy for time in one place.
2. **`Featurizer` returns a `Curve`, not spans.** Methods that "detect segments" (PySceneDetect,
   hysteresis) are `Boundarizer`s consuming a curve, and the ones that can only give you boundaries
   (PySceneDetect) still expose their internal score as a curve when they have one. This is what
   lets `ffmpeg scene_score`, embedding novelty and audio novelty all feed the same peak-picker.
3. **The `Assigner` is where the accuracy lives and there should be exactly one.** §8.3's DP is a
   restricted case of `muvid/footage/select_score.py`'s beat-snapped semi-Markov Viterbi, which
   already has length constraints, boundary snapping, a switch penalty and infeasibility
   classification. **Generalise that one; do not write a second.** `snap_to=` is how the beat grid
   from file 02 and the cut list from §3 enter the visual pipeline.
4. **`Span | None`.** §8.3's kanban result makes the nullable return type non-negotiable. Every
   `Scorer` must also publish enough of its score distribution for the assigner to compute a null.
5. **`Curve` is `muvid.footage.scoring.grid.ScoreTrack` with the clip fields removed.** That module
   already has `resample_to_grid`, robust normalisation, coverage masks and a staleness
   fingerprint. Lift it; do not re-derive it.

**Registration.** Copy `muvid/footage/strategy.py`'s lazy registry pattern —
`_LAZY: {slug: "module:func"}` — so `list_methods()` can enumerate torch-backed and
transformers-backed featurizers without importing torch. That property is what makes the
agent-picks-a-method surface viable: the agent needs the *catalogue with costs* cheaply, and only
then pays for the one it chose. Each registration should carry the columns of §13 as metadata
(`needs`, `rate_hz_default`, `s_per_min`, `device`, `licence`) — that table is the agent's menu.

---

## 12. Dependency ledger

**Already in p12 — a visual v1 needs zero new packages:**
`opencv 4.13`, `numpy 2.2.6`, `scipy 1.16.3`, `mediapipe 0.10.35`, `rtmlib 0.0.15`,
`onnxruntime 1.23.1` (with `CoreMLExecutionProvider`), `ultralytics 8.4.75` (AGPL),
`torch 2.9.0` + `torchvision 0.24.0` (MPS available), `transformers 4.57.1`,
`dtaidistance 2.4.0`, `pytesseract 0.3.13` + `tesseract 5.5.2`, `librosa 0.11.0`,
`av 16.0.1`, `imageio-ffmpeg`, `moviepy 2.2.1`, `Pillow 11.3.0`, `scikit-image`, `scikit-learn`.

**Already in the HF cache (no download):** `google/siglip2-base-patch16-224`,
`google/siglip2-so400m-patch14-384`, `openai/clip-vit-base-patch32`, `facebook/dinov2-base`.

**One-time asset downloads (not pip):** mediapipe `.task` files (6/9/31 MB); rtmlib ONNX bundles
(auto, to `~/.cache/rtmlib`, 18–20 MB for `lightweight`); ultralytics `.pt` (auto).

**New dependency, and the only one I would take:** `scenedetect` (BSD-3-Clause, pure Python over
OpenCV, ~2 s/min). And even that is optional — ffmpeg's `lavfi.scene_score` (§3.3) covers the cheap
case for free, and §8.2 beats both on the case that matters.

**Would be new, and I recommend against in v1:** `easyocr`/`paddleocr` (§10.2), any
Kinetics-pretrained video model (§7.2), 4DHumans/SMPL (§5.5), a RepNet port (§6.3),
OWLv2/GroundingDINO (§9).

---

## 13. The cost table

One minute of 720p30 video, Apple M1 Max, offline. ⊕ includes decode, ⊖ excludes it (add ~2.4 s).
All **[verified]**.

| Method | rate | device | s / min | licence | new dep? |
|---|---|---|---|---|---|
| ffmpeg `lavfi.scene_score` (full curve) | 30 | CPU | **0.8** | ffmpeg | no |
| ffmpeg pipe → 320 px gray | 6 | CPU | 1.3 | — | no |
| SigLIP2-base image embeddings | 2 | MPS | **1.6** ⊖ | Apache-2.0 | no |
| CLIP ViT-B/32 image embeddings | 2 | MPS | 1.7 ⊖ | MIT | no |
| ffmpeg pipe → 320 px gray | 30 | CPU | 2.1 | — | no |
| PySceneDetect `ContentDetector` | 30 | CPU | 2.2 | BSD-3 | **yes** |
| PySceneDetect `AdaptiveDetector` | 30 | CPU | 2.3 | BSD-3 | **yes** |
| cv2 decode + numpy frame-diff energy | 30 | CPU | 2.5 ⊕ | Apache-2.0 | no |
| X-CLIP base-p32 zero-shot, 8-frame clips /3 s | — | MPS | 3.3 ⊖ | MIT | no |
| **SigLIP2-base image embeddings** | **6** | **MPS** | **4.4** ⊖ | Apache-2.0 | no |
| SigLIP2-base image embeddings | 2 | CPU | 6.2 ⊖ | Apache-2.0 | no |
| Farneback flow, 320 px | 15 | CPU | 6.5 ⊕ | Apache-2.0 | no |
| Farneback flow, 512 px | 6 | CPU | 7.5 ⊕ | Apache-2.0 | no |
| RAFT-small, 512 px | 6 | MPS | 9.8 ⊖ | BSD-3 | no |
| rtmlib RTMPose `lightweight` | 6 | CoreML | **10.9** ⊕ | Apache-2.0 | no |
| YOLO11n **detect**, batched ×16 | 30 | MPS | 11.8 ⊖ | **AGPL** | no |
| mediapipe Pose `full` | 6 | CPU | 12.3 ⊕ | Apache-2.0 | no |
| tesseract, cropped band ×3 | 1 | CPU | 14.4 | Apache-2.0 | no |
| YOLO11n-pose, batched ×16 | 30 | MPS | **19.2** ⊕ | **AGPL** | no |
| mediapipe Pose `lite` | 30 | CPU | **22.2** ⊕ | Apache-2.0 | no |
| RAFT-large, 512 px | 6 | MPS | 22.5 ⊖ | BSD-3 | no |
| rtmlib RTMPose `balanced` | 6 | CoreML | 23.2 ⊕ | Apache-2.0 | no |
| Farneback flow, 512 px | 30 | CPU | 29.0 ⊕ | Apache-2.0 | no |
| tesseract, full 720p frame | 1 | CPU | 34.4 | Apache-2.0 | no |
| mediapipe Pose `full` | 30 | CPU | 34.8 ⊕ | Apache-2.0 | no |
| RAFT-small, 512 px | 30 | MPS | 35.5 ⊖ | BSD-3 | no |
| mediapipe Pose `lite`, **GPU delegate** | 30 | GPU | 45.6 ⊕ | Apache-2.0 | no |
| mediapipe `HandLandmarker`, 2 hands | 30 | CPU | 55.6 ⊕ | Apache-2.0 | no |
| mediapipe `GestureRecognizer` | 30 | CPU | 56.5 ⊕ | Apache-2.0 | no |
| RAFT-small, 512 px | 6 | **CPU** | 141.1 ⊖ | BSD-3 | no |
| rtmlib RTMPose `balanced` | 6 | **CPU** | 138.3 ⊕ | Apache-2.0 | no |
| mediapipe Pose `heavy` | 30 | CPU | 134.6 ⊕ | Apache-2.0 | no |
| — subsequence DTW, 2 s query vs 60 s, 8-D | — | CPU | 0.35 / query | Apache-2.0 | no |
| — pairwise DTW, 60 × 60 one-second tiles | — | CPU | 10.0 | Apache-2.0 | no |

**A default budget that fits in ~7 s/min:** ffmpeg gray pipe at 6 Hz (1.3) + frame-diff energy
(0.1) + ffmpeg scene score (0.8) + SigLIP2 at 6 Hz (4.4). That gives you an activity curve, a cut
curve, a semantic-novelty curve and a text-scoreable embedding matrix — enough for §8.2 boundaries,
§8.3 assignment, §6.3 periodicity, and a duration sanity check. Pose is a *second* pass, run only on
the spans the first pass says are movement-dominated. That gating is exactly what the POC did to
Whisper with the sub-bass ratio, applied to the visual side.

---

## 14. What this changes about the fleet

- **`kodokan` is the pose front-end, and it is 90% there.** `pose.py` (backends + `PoseSequence`),
  `segment.py` (motion energy, hysteresis, self-similarity, `estimate_period`) and `compare.py`
  (joint angles + DTW) are the right code. What they need: `device="mps"` as the rtmlib default
  (§5.4.3), top-k periods rather than argmax (§6.3), subsequence DTW with a length constraint
  (§6.5), torso-normalised motion energy (§6.1), and — the big one — **a way to emit a `Curve` on a
  shared media clock instead of a bespoke dataclass**.
- **Nothing in the fleet computes frame embeddings.** §8 is entirely new code, it is the highest-
  value item in this document, and it is about 80 lines.
- **`muvid.footage.scoring.grid.ScoreTrack` is the `Curve` type** and
  `muvid/footage/select_score.py` is the `Assigner`. Both are written and reviewed. The visual work
  is mostly producing tracks for machinery that already exists.
- **`mixing.audio.segmentation`'s Foote checkerboard is §8.2's novelty operator** with a different
  feature matrix. Factor it out of the audio module rather than writing it twice.

---

## Open questions

1. **Does the §8.2/§8.3 result survive the genre it was built for?** Every accuracy number here
   comes from clip B, a screen recording with five visually distinct sections — the easy case. The
   hard case is nine dance blocks in one take against one wall, where consecutive spans are nearly
   identical images. My expectation **[inferred]** is that embedding novelty finds *nothing* there
   and correctly reports low confidence, and that pose periodicity + audio carry it. That needs one
   experiment on the actual POC video before any of this is designed around.
2. **What is the null model for "this artifact is not in the video"?** §8.3's kanban row proves it
   is needed; I do not know the right form. Candidates: a learned threshold on the contrastive
   z-score; a "background" prompt that competes with the real ones; a permutation test over shuffled
   artifact order. This is the single most important open design question.
3. **Cover or gap?** Must the artifacts tile the media (the DP as written), or may spans be
   unassigned? The correct answer is probably per-caller, and it is one DP state apart — but the
   *default* matters and I do not know which way it should go.
4. **Fusion.** All of §4, §6, §8 produce curves on the same clock. Does the assigner take a weighted
   sum, a product of likelihoods, or a per-artifact learned combination? `ScoreTensor`'s robust
   per-metric normalisation is the machinery; the weights are the question. What sets them —
   the agent, a calibration set, or the per-curve confidence (the ACF `r`, the BAS `z`, the
   cross-backend agreement of §6.3)?
5. **Does cross-backend agreement generalise as a confidence signal?** mediapipe and YOLO11n agreed
   to the sample on the top ACF peak of clip A. If that holds, "run two cheap pose backends and
   trust the agreement" is a better confidence estimate than any single model's scores — and it
   costs less than one `heavy` model. One clip is not evidence.
6. **When is the visual side allowed to overrule the document?** The POC's duration sanity check
   proved the source document wrong about its own tempo. §8.3's boundaries are accurate enough to do
   the same for *step boundaries*. What is the policy — flag, correct, or refuse?
7. **Is `rate_hz` really one knob?** Boundaries want high temporal resolution and tolerate a weak
   feature; identity wants a strong feature and tolerates 1–2 Hz. A single `rate_hz` may be the
   wrong abstraction, and the right one may be two passes (coarse-to-fine: locate candidates at
   2 Hz, refine each candidate at 30 Hz in a ±2 s window). That would cut §8's cost further and I
   have not tested it.
8. **Licence policy for ultralytics.** It is AGPL-3.0, it is currently the fastest full-rate pose
   *and* the cheapest object detector, and it is already load-bearing in the POC and in `kodokan`.
   `mixing.audio.beats` set the precedent of excluding `madmom` on licence grounds. Is YOLO an
   opt-in backend, a dev-only tool, or does it need to go? This is a decision, not a research
   question, and it should be made before the first commit.
