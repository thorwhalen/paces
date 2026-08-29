# 07 — Segmenter strategies: one seam, many implementations

**Question this file answers:** the user has settled the core abstraction as **`video + segmenter`**
— *"Depending on how many other inputs/annotations/artifacts are present, the default segmenter
could be one thing or another. The important thing here is to leave it open closed. Some segmenters
might be video only (but still, there's many ways to do that…). It could also be 'ask the user'."*
So: **what are all the ways to cut a video into named steps, organised by what you happen to have,
and what is the one seam that holds them all without ever being edited again?**

**Where this sits.** Files 00–06 answer *"given artifacts and media, where does each artifact go?"*
This file answers the strictly harder question *"where do the artifacts come from?"*, and its main
structural claim is that the two are the same question with one stage bolted on the front. Read
`06-the-planner-surface.md` §1 before §9 here — this file **reuses** its `Capability(needs, gives)`
record rather than proposing a parallel one, and that reuse is load-bearing, not politeness.

---

> ## ⚠ Read this first — two corrections from the user
>
> This file is an excellent concrete catalogue (real libraries, measured costs, failure modes)
> and you should use it as the menu. But two of its framing choices were corrected after it was
> written — see `../adr/0003-video-plus-segmenter.md`:
>
> 1. **Its organising axis — input-richness tiers A–G — was my brief to the research agent, not
>    the user's framing.** The intended map of the space is by *where a segmenter's information
>    comes from*: **intrinsic** (features of the media), **external-explicit** (interval
>    coordinates handed over directly), **external-derived** (computed from the other annotations
>    around), and **mixed** — with mixed being the normal case, not the exotic one. The tiers here
>    are one slice through that space.
>
> 2. **It states the segmentation/labelling split as a law.** It is not. In the user's words:
>    *"The separation of segmentation and the labeling of the segments can be strong or not.
>    That really depends on the case."* Sometimes the same evidence yields both at once (a step
>    list placed on a timeline: each span *is* its label). What survives is the narrower,
>    measured point: a segmenter that **invents** names for content it did not understand is
>    worse than one that admits it does not know.
>
> Also missing here, and central to ADR-0003 §3: many intrinsic segmenters share one
> computational shape — *featurize → reduce to a scalar stream → threshold/peak-pick →
> regularize* — and the package should ship those as **composable stages**, so the common cases
> are assembled rather than authored. Scene detection, frame-change, speech-or-not and beat
> counting are all that same pipeline with different parts.

---

## Verification legend, and one thing you need to know about this machine

- **[verified]** — I ran it on this Mac this session and pasted the output.
- **[from siblings]** — a measured number from files 00–06, cited by file and section. **Every cost
  in this document is of this kind.**
- **[from docs]** — read from a licence file, PyPI metadata, a paper or a library's source, not executed.
- **[inferred]** — my design judgement. §9 is almost entirely this. Argue with it.

> **The p12 interpreter is currently broken and no Python ran this session.**
> `/Users/thorwhalen/.pyenv/versions/3.12.12/envs/p12/bin/python` exits **0 and prints nothing**;
> going through the shim gives
> `pyenv-exec: line 48: …/versions/3.12.12/bin/python3: Undefined error: 0`. **[verified]**
> `/usr/bin/python3` and `/opt/homebrew/bin/python3` work but have no numpy.
> So this file adds **no new numeric measurements**. Its `[verified]` marks are CLI (ffmpeg/ffprobe/
> tesseract), filesystem (`dist-info` inspection of p12's site-packages, source reading), and HTTP
> (PyPI JSON, raw GitHub licence files) checks. Fix the interpreter before re-running anything here.
> Two corrections to sibling files fell out of the filesystem check, in §11.

---

## 0. The short answer

**Two tables. The first is the catalogue collapsed to one line per tier; the second is the seam's
whole selection rule.**

| you have | the default segmenter | cost / min 720p | what you actually get |
|---|---|---|---|
| **video only** | `novelty-k` — fused boundary curve, cut at K or at Foote peaks | **~7 s** | **boundaries, and usually no names** |
| video + a number K from a human | `novelty-k` with `ruptures` known-K | ~7 s | exactly K boundaries, no names |
| video + an ordered step list | `align-to-steps` (= `06`'s `align()`) | ~7 s | named spans |
| video + a structured document | `align-to-steps` + grid + duration check | ~9 s | named spans, sub-steps, counts, **and a diff against the document** |
| video + a steering prompt only | `steer` → propose → `align-to-steps` | ~7 s + 1 LLM call | macro regions first, then steps inside each |
| video + chapters / subtitles / description | `metadata` proposer → `align-to-steps` | **~0.03 s** + refine | named spans, essentially free |
| a human at the keyboard | `ask` with pre-computed candidates | ~7 s + **~2 min of human** | ground truth |

**The five things to remember, before any of the detail:**

1. **Segmentation is two problems, and only one of them is hard for a machine.** *Where are the
   cuts* and *what is each piece called*. Video-only can find cuts; it almost never finds names.
   Every tier below B differs from tier A in exactly one way: **the names came free with the input.**
   Organise the seam around that and the tiers stop being seven designs and become one.

2. **"Video only" is a statement about your inputs, not about your modality.** A video file
   contains audio; audio contains a transcript; a YouTube URL contains chapters, subtitles and a
   re-watch heatmap. The single biggest mistake tier A can make is to reach for pixels first. The
   POC's most valuable feature was a **sub-bass energy ratio** — five lines of numpy over the audio
   track of a "video-only" input (`01-what-was-built.md`, `02 §6.1`).

3. **A segmenter is a proposer composed with `align()`.** `Segmenter = propose_steps ∘ align`.
   Tiers B–F *are* the proposer, handed to you. Tier A has to build one. This decomposition is why
   the seam is open-closed almost for free: **a new segmenter is usually a new proposer, ~40 lines,
   and the placement half is machinery that already exists** (`06 §6.1`, `05 §3`).

4. **The cheapest thing to ask a human is not "where are the boundaries", it is "how many".**
   One integer converts an unsolvable peak-picking problem into `ruptures.KernelCPD(...)
   .predict(n_bkps=K-1)`, which is exact and costs **0.188 s at n=4800** (`05 §7.3`). Design the
   human interaction around K first and boundaries second. §7.

5. **The default video-only segmenter must be allowed to return boundaries and refuse to name
   them.** `03 §8.3`'s kanban row measured a *confident argmax for a thing that is not in the video
   at all*. A segmenter that invents nine plausible step names for a video it did not understand is
   worse than one that says "nine cuts, here they are, I don't know what they're called" — because
   the second is fixable in two minutes by a human and the first is a lie the human has to detect
   before they can fix it. §9.5.

---

# PART 1 — the strategy catalogue

## 1. What a segmenter is, precisely

```
Segmenter :  media  ×  whatever-else-is-present   →   Segmentation
```

and a `Segmentation` is **an ordered set of named spans, plus the boundary set that produced it,
plus a confidence, plus the evidence.** The exact type is §9.1. Two things it is *not*:

- **It is not `align()`.** `align()` (`06 §6.1`) takes a list of artifacts you already have and
  places them. A segmenter may have to *invent* the list. When it does not — tiers B–F — it should
  literally call `align()` and add nothing.
- **It is not a shot detector.** `03 §0` measured this and it is the most useful negative result in
  the sibling set: on a real five-section video, PySceneDetect's best detector found 10 cuts of
  which **2** were real section boundaries. **Cut detection is not section detection.** Shot cuts
  are an *editing* artifact; steps are a *semantic* one; in a single-take tutorial there are zero
  shot cuts and nine steps.

The decomposition that organises everything below:

```
                      ┌─ propose_steps ─┐        ┌─ place ─┐
   media + inputs ────┤                 ├───────►│         ├──► Segmentation
                      └─────────────────┘        └─────────┘
                       tiers B–F: FREE            06 §6.1's align(), always
                       tier  A:   the whole job   05 §3's ordered DP underneath
```

**Tier A is the only tier where the left box is hard.** Everything from §3 onward is short because
the work was already done by files 00–06 and I am not going to repeat it.

---

## 2. TIER A — video only, nothing else

The hard one, and the one the user explicitly asked to have enumerated. Below are **sixteen
distinct families**, grouped by what part of the signal they exploit. For each: what it assumes,
what it outputs, cost per minute of 720p30 on an M1 Max, and when it fails.

**Read §2.0 first — it is where most of tier A's actual answer lives, and it is not visual.**

### 2.0 The reframe: derive the other modalities before touching a pixel

A "video only" input is not a pixel-only input. Three derivations, in increasing cost, each of
which moves you into a *different, easier tier*:

| derivation | how | cost / min | moves you to |
|---|---|---|---|
| **the audio track** | `ffmpeg -i in.mp4 -vn -ac 1 -ar 22050 out.wav` | ~0.1 s **[inferred]** | all of file `02` |
| **the container's own metadata** | `ffprobe -show_chapters -show_format` | **0.026 s, O(1)** **[verified]** | **tier E** (§6) |
| **a transcript** | `mlx_whisper` over speech-gated spans | **17 s** (`06 §1.4`) | tier B, via `04 §7.1` cues |

The middle row is nearly free and almost always skipped. §6 is about it. The bottom row is the
single biggest lever in tier A and gets its own family below (§2.13).

---

### 2.1 Shot / scene cut detection

- **Assumes:** the video was *edited* — there are hard cuts, dissolves or wipes.
- **Outputs:** a boundary set (`gives='boundary'`), no names.
- **Cost:** ffmpeg `lavfi.scene_score` **0.8 s/min**; PySceneDetect `AdaptiveDetector` **2.3 s/min**
  (`03 §13`). TransNetV2 ~6 s/min **[inferred]** — no measurement exists.
- **Fails when:** the tutorial is one continuous take, which is the dominant case in
  teach-a-physical-skill video (the POC's dance video: one take). And it *over*-fires on
  edited footage: 10 cuts for 5 sections (`03 §8.2`).

Three implementations, in order of when you would reach for them:

```bash
# 1. Free, no dependency, and the useful form is the WHOLE CURVE, not the thresholded cuts.
ffmpeg -i in.mp4 -filter:v "select='gt(scene,0)',metadata=print:file=scene.txt" -f null -
# scene.txt alternates:  frame:0 pts:1024 pts_time:0.1 / lavfi.scene_score=0.009853
```
**[verified this session]** — the filter chain runs on ffmpeg 8.1 and emits one `lavfi.scene_score`
line per frame. Rank the curve; never threshold it (`03 §3.3`).

```python
# 2. pip install scenedetect  ->  0.7.1, BSD-3-Clause [verified: PyPI JSON + raw LICENSE]
from scenedetect import detect, AdaptiveDetector
cuts = detect("in.mp4", AdaptiveDetector())
```

```python
# 3. pip install transnetv2-pytorch  ->  1.0.5, MIT [verified: PyPI JSON + soCzech/TransNetV2 LICENSE]
#    The learned SOTA-adjacent shot detector; deps ffmpeg-python, torch>=1.9, pandas.
```
**Verdict [inferred]:** take **neither** dependency in v1. ffmpeg's curve is free and `03 §8.2`
measured embedding novelty beating both on the case that matters. TransNetV2 earns its place only
if a *screencast/montage* subgenre appears where genuine shot detection is the product.

### 2.2 Motion-energy quiescence — "the movement stops between steps"

- **Assumes:** the vocabulary has genuine **stops**. Judo demonstrations, exercise reps, a craft
  step between tool changes, a kata between forms.
- **Outputs:** intervals (`gives='regions'`), no names.
- **Cost:** ffmpeg gray pipe at 6 Hz **1.3 s/min** + frame-diff energy **0.1 s** = **1.4 s/min**
  (`03 §2`, `03 §13`). This is the cheapest visual segmenter that exists.
- **Fails when:** the movement is continuous — dance, walking, talking-with-hands. `03 §6.2` is
  blunt about it: *"the minima are noise. Do not sell it as a general segmenter; sell it as a
  hypothesis generator."*

**Already written, in the fleet, tested:** `kodokan.segment.find_segments(energy, frame_indices,
fps, *, smooth_sigma=4.0, low_quantile=0.25, high_quantile=0.5, min_duration_s=1.0,
merge_gap_s=0.4)` **[verified: read the source]** — two-threshold hysteresis so a slow-motion dip
mid-rep does not split it, gap-merging, minimum duration. Take it as-is.

**One gotcha nobody has written down.** Its thresholds are **quantiles of this clip**, so on a
uniformly-active clip it invents boundaries and on a one-burst clip it finds one segment
(`03 §6.2`). Expose absolute thresholds as an alternative before shipping it as a default.

### 2.3 Pose / skeleton change-points

- **Assumes:** a person is visible, and the *body configuration* changes at step boundaries even
  when the pixels do not.
- **Outputs:** a curve (`gives='curve'`), then §2.2's hysteresis or §2.5's novelty over it.
- **Cost:** `rtmlib` RTMPose `lightweight` at 6 Hz on CoreML **10.9 s/min**; mediapipe Pose `full`
  at 6 Hz **12.3 s/min** (`03 §13`). **This is 8× the cheap curve** — it is a second pass, not a
  first one.
- **Fails when:** no person, several people (the crop/track logic breaks — `03 §5.4`), or the
  subject walks toward the camera (pixel displacement reads as energy — divide by torso length,
  `03 §6.1`).

`kodokan.pose.estimate_poses` and `kodokan.segment.pose_motion_energy` are built, tested and
Apple-Silicon-native, and **dormant** (`00 §1`). The two changes they need before use:
`device="mps"` as the rtmlib default (currently `"cpu"`, and the difference is **6×** — `03 §5.4`),
and torso normalisation.

**Why pose is second and not first:** `03`'s headline. *"Pose is not the most valuable visual signal
for alignment. Per-frame vision-language embeddings are."* Pose earns its place on a **different
axis** — periodicity and movement identity (§2.4, §2.11) — not boundaries.

### 2.4 Repetition and periodicity — a routine that gives you its own ruler

**The most underrated family in tier A, and it is nearly free.** If the content repeats, the period
is a segmenter: it tells you the *duration* of a unit, which converts peak-picking into grid
fitting (`05 §9`), which is a solved problem.

- **Assumes:** something in the frame repeats — a step, a rep, a bar of music, a lap.
- **Outputs:** a grid (`gives='grid'`): `(period, phase)`.
- **Cost:** **free** on top of any curve you already computed — an autocorrelation of a 1-D array.
- **Fails when:** the period *varies* (accelerating reps). ACF genuinely cannot do this.

```python
def acf_periods(x, rate_hz, *, lo_s=0.3, hi_s=3.0, sigma=1.0, k=3):
    """kodokan.segment.estimate_period, generalised to return the top-k. 03 §6.3."""
    x = gaussian_filter1d(np.asarray(x, float), sigma); x -= x.mean()
    a = np.correlate(x, x, "full")[x.size - 1:]; a /= a[0] + 1e-12
    lo, hi = int(lo_s * rate_hz), min(int(hi_s * rate_hz), len(a) - 1)
    pk, _ = find_peaks(a[lo:hi]); pk += lo
    top = pk[np.argsort(a[pk])[::-1]][:k]
    return [(float(l / rate_hz), float(a[l])) for l in top]
```

Four things `03 §6.3` measured that change how you use it:

- On ground truth (a synthetic 0.800 s oscillation) the frame-diff curve recovers **0.800 s at
  r = 0.983**. It works.
- **Return the top-k, not the argmax** — the harmonics (0.800 / 1.600 / 2.400) are the point,
  because *which* harmonic is the musically meaningful unit (beat vs bar vs 8-count) is exactly the
  ambiguity the POC resolved with a duration sanity check (`05 §9.5`).
- **Autocorrelate positions, not speeds** (r 0.37 vs 0.11), and pick **one good joint**, not the
  whole-body average (r 0.37 vs 0.15).
- **Two independent pose backends agreed on the top ACF peak to the sample** (0.767 s, mediapipe
  vs YOLO11n). Cross-backend agreement is a cheap, strong confidence signal.

**Bug to fix before use [verified: read the source]:** `kodokan.segment.estimate_period` defaults to
`min_period_s=1.5, max_period_s=10.0` — tuned for judo reps. A dance beat at 129 bpm is **0.465 s**
and an 8-count is 3.7 s; the current default *cannot see the beat at all*. The bounds must be an
argument the subgenre sets, not a constant.

**RepNet** (Dwibedi et al., CVPR 2020) is the published version of this — class-agnostic repetition
counting from a temporal self-similarity matrix. Original is TensorFlow/Colab; PyTorch ports exist
but none is a maintained pip package **[from docs, `03 §6.3`]**. The 20 lines above got the exact
right answer on ground truth. **Do not take the dependency.** Note it as a future backend behind
the same `periods()` seam — its one genuine advantage is robustness to a *varying* period.

### 2.5 Self-similarity matrices and novelty curves

- **Assumes:** frames *within* a step look more like each other than like frames of the next step.
  This is the weakest possible assumption in tier A and that is why it is the backbone.
- **Outputs:** a boundary curve (`gives='curve'` → `gives='boundary'`).
- **Cost:** **0.23 s** for a 301×301 cosine self-similarity on raw gray (`03 §2`); free on top of
  any feature matrix you already have.
- **Fails when:** consecutive steps look identical — nine dance blocks in one take against one wall.
  Correctly, it finds nothing. That failure is *reported*, not hidden, which is the right behaviour.

```python
# Foote checkerboard novelty. 03 §8.2. E is (F, d) L2-normalised features — ANY features.
D = E @ E.T
K = int(2.0 * rate_hz)                      # half-kernel, 2 s. K barely matters between 2 and 4 s.
nov = np.zeros(len(E))
for i in range(K, len(E) - K):
    a, b = slice(i - K, i), slice(i, i + K)
    nov[i] = D[a, a].mean() + D[b, b].mean() - 2 * D[a, b].mean()
peaks, _ = find_peaks(nov, height=np.quantile(nov[nov > 0], 0.85), distance=int(3 * rate_hz))
```

**Write this operator once, modality-agnostically.** `mixing.audio.segmentation`'s
`self_similarity` strategy already implements Foote checkerboard for audio (`00 §1`,
`00 §3.2`) — `03 §8.2` is *the same function with a different feature matrix*. Factoring it out of
the audio module is a one-afternoon job that removes a whole class of duplication.

### 2.6 Optical-flow discontinuity

- **Assumes:** the *direction and magnitude* of motion changes at a boundary even when its
  magnitude does not — a turn, a direction reversal, a switch from travelling to stationary.
- **Outputs:** a curve.
- **Cost:** Farneback at 512 px / 6 Hz **7.5 s/min**; at 320 px / 15 Hz **6.5 s/min**. RAFT-small on
  MPS **9.8 s/min**, on CPU **141 s/min** (`03 §13`).
- **Fails when:** the camera moves (handheld, pan, zoom) — flow is *not* subject-relative, unlike
  pose. And it is **5× the price of frame differencing for a correlated signal.**

**Verdict [inferred]:** in v1, do not run flow as a boundary source. Frame-diff energy at 0.1 s/min
gives you the same *quiescence* information; flow's extra content — direction — is only worth 7.5
s/min if a subgenre specifically needs it (a "which way did she turn" cue). `kodokan.segment
.optical_flow_energy` exists if you want it, and `segment_demonstrations(use_optical_flow=True)`
already min-max normalises and fuses it with pose energy **[verified: read the source]**.

### 2.7 Visual-embedding change-point — **the strongest video-only boundary method**

- **Assumes:** consecutive steps are **semantically** different-looking. Not pixel-different —
  *meaning*-different.
- **Outputs:** a curve, and (if you also have text) an emission matrix.
- **Cost:** SigLIP2-base at 6 Hz on MPS **4.4 s/min ⊖**, at 2 Hz **1.6 s/min ⊖**; +3.2 s one-time
  model load; text encoding **0.15 s for 6 prompts** (`03 §8.1`). Apache-2.0, already in the HF
  cache, offline.
- **Fails when:** §2.5's failure — one take, one wall, one dancer (`03 §8.4`). And when the artifact
  text is not visually descriptive ("Block 4" carries no signal).

The measured result is the headline of `03` and I will not re-derive it: five semantic boundaries in
a real product-tour video, **all five to within 0.3 s**, where PySceneDetect got 2 of 5 with 8 false
positives and ffmpeg's thresholded detector got 4 of 5 (`03 §8.2`).

```python
mid = "google/siglip2-base-patch16-224"          # in ~/.cache/huggingface already [03 §12]
proc, m = AutoProcessor.from_pretrained(mid), AutoModel.from_pretrained(mid).eval().to("mps")
with torch.inference_mode():
    px = proc(images=rgb_batch, return_tensors="pt").to("mps")
    E = torch.nn.functional.normalize(m.get_image_features(**px), dim=-1).float().cpu().numpy()
# then §2.5's novelty over E.  For the text side: padding="max_length" is MANDATORY for SigLIP.
```

**`facebook/dinov2-base` is the untested alternative and it may be better here.** It is also already
cached (`03 §12`). DINOv2 is self-supervised on images alone, so it encodes *appearance and pose*
rather than *nameable semantics* — which is exactly the axis on which the dance case fails for
SigLIP. **[inferred, and it is the cheapest experiment in this document: swap one model id.]**

### 2.8 On-screen text / OCR — many tutorials literally caption their steps

- **Assumes:** the editor burned in step titles, a lower third, a rep counter, a slide title.
  Extremely common in cooking, software and fitness content; rare in "someone filmed a class".
- **Outputs:** timed text (`gives='timed_text'`) — and when it works, it gives you **boundaries AND
  names in one pass**, which nothing else in tier A does.
- **Cost:** tesseract on a **cropped band** at 1 Hz **14.4 s/min**; on the full 720p frame
  **34.4 s/min** (`03 §13`). `tesseract 5.5.2` and `pytesseract 0.3.13` are installed **[verified]**.
- **Fails when:** the text is stylised, animated, low contrast, or absent; and it is slow enough
  that you must **gate it** — run it on 3 sampled frames as a probe fact (`06 §1.3`'s
  `onscreen_text`), and only run the full pass if the probe sees text.

**The trick worth stealing** (`03 §10.3`): OCR is not only a segmenter, it is a **ground-truth
generator**. A captioned tutorial gives you free labelled data to calibrate every other method on.
That is how you get past `06 §3.4`'s "≥30 labelled runs" bar without hand-labelling anything.

### 2.9 Slide / frame-hash change — the screencast special case

- **Assumes:** a screen recording where the content is *piecewise constant*. Slides, an IDE, a
  document being edited.
- **Outputs:** boundaries.
- **Cost:** essentially free — a perceptual hash over the 320 px gray array you already decoded.
- **Fails when:** anything animates continuously (a cursor, a video embed, a scroll), which turns
  every frame into a new hash. Needs a dead-band, and the dead-band is content-specific.

**[inferred]** This is a 15-line special case of §2.5 with a step-function kernel instead of a
checkerboard. Do not build it as a separate segmenter; build it as an alternative *novelty kernel*
and let the probe's `static_camera` + low `cuts` + high `silence` facts select it.

### 2.10 Hand / object-state change — the craft and cooking axis

- **Assumes:** the step boundary is a **tool change** or an **object state change**, not a body
  change. "Now take the whisk." "Now the dough is smooth."
- **Outputs:** a curve, or discrete events.
- **Cost:** mediapipe `HandLandmarker`, 2 hands, 30 fps: **55.6 s/min** (`03 §13`). At 6 Hz that is
  ~11 s/min **[inferred]**. Object detection (OWLv2 / GroundingDINO) is a new dependency and `03
  §12` recommends against it in v1.
- **Fails when:** hands leave the frame, or the interesting change is in the object and not the hand
  (a sauce thickening).

**Verdict [inferred]:** out of v1. `09-subgenre-candidates.md` is where the decision to build a
cooking/repair subgenre lives; until that decision is made this family has no consumer. It is
listed here so the seam is not designed in a way that excludes it — and it is not, because it is
just another `gives='curve'` capability.

### 2.11 Movement identity — "this move again, somewhere else in the video"

Not a boundary method; a **naming** method, and tier A's only native one.

- **Assumes:** you have an *exemplar* — a clip of a move — and want its other occurrences. In an
  instructional video this is free: the run-through and the breakdown are the **same step twice**
  (`03-design-brief.md §5.1`: six of nine POC blocks shipped both).
- **Outputs:** a placement per query (`gives='placement'`).
- **Cost:** subsequence DTW over 8-D joint angles: **0.35 s per query** (`03 §13`, `03 §6.5`) — on
  top of the pose pass's 10.9 s/min.
- **Fails when:** 2-D joint angles are not viewpoint-invariant — `kodokan.compare` documents this
  caveat honestly **[verified: `00 §1`]**.

**Why this matters more than its cost suggests:** it is the mechanism that turns a *self-supervised*
segmentation into a named one. Segment the breakdown half (where there are pauses, speech and slow
demonstration — all the easy signals), then use each breakdown span as an exemplar to find its
occurrence in the run-through half. **The video labels itself.** `05 §4.3`'s
`librosa.sequence.dtw(subseq=True)` and `kodokan.compare.compare` (DTW via `dtaidistance.dtw_ndim`)
are both already installed **[verified: `dtaidistance 2.4.0` in p12]**.

### 2.12 Audio derived from the video — where tier A's cheap wins actually are

Everything in file `02` applies to a video-only input the moment you run one ffmpeg command. The
four that matter, in cost order:

| method | gives | cost / min | what it buys | cite |
|---|---|---|---|---|
| **sub-bass ratio** (20–120 Hz energy / total, 9 s smoothed) | regions | **0.008 s** | music vs speech vs silence — **21× separation, measured** | `02 §6.1`, `06 §1.3` |
| `beat-this` | grid | **0.14 s** + 3 s load | the beat grid, when there is music. MIT. | `02 §2.2` |
| `librosa.beat.beat_track` | grid | 0.7 s | the no-new-dependency baseline | `02 §2.1` |
| Laplacian structure segmentation | regions | ~2 s | intro / verse / chorus — *the macro cut* | `02 §5.1` |

**This is the single highest value-per-second block in tier A**, and it is why the POC worked. The
sub-bass ratio split the dance video into talk / run-through-with-music / spoken-breakdown for
0.008 s/min, and *that split made everything downstream tractable* — it told the analyser which
half to run ASR on and which half to run beat tracking on. Any tier-A segmenter that does not start
here is slower and worse (`ADR-0001`, and the alignment README says the same thing).

**And a free music detector nobody expected** (`06 §2.3`): the **beat-fit residual** separates music
from speech by **27×** (9–12 ms vs 142–322 ms). You get it for nothing while fitting the grid.

### 2.13 ASR of the video's own narration — **the biggest single lever in tier A**

**Say this out loud because it is easy to miss: video-only does not mean text-free.** If someone is
teaching, they are talking, and what they say is *the step list*. The POC's steps were named "in the
teacher's own words" this way (`ADR-0001`).

- **Assumes:** there is speech, and the speaker announces or narrates transitions.
- **Outputs:** timed text → boundaries → **names**. It is the only tier-A family that routinely
  produces both halves of the problem.
- **Cost:** `mlx-whisper` **17 s/min** (`06 §1.4` catalog), and **you should not pay it on the whole
  file** — gate it to speech regions with §2.12's 0.008 s/min ratio. On the POC's 10:51 video that
  gate cut ASR to roughly the spoken half. `mlx_whisper 0.4.3` and `faster_whisper 1.2.0` are both
  installed **[verified]**.
- **Fails when:** there is no narration (a silent demo over music); the speech is over music
  (**Whisper hallucinates** — `01 §1.4`, and `06 §3.2` encodes that as a `penalties={'music': 5.0}`,
  deliberately not a hard `needs`, so a mixed file still gets ASR *inside* its speech regions);
  or the language is not the one you assumed.

Two ways to get boundaries out of the transcript, and you should run both:

```python
# (a) Classical, free, and measured: lexical cue detection. 04 §7.1.
#     "now", "next", "then", "so we start with", "and finally", imperative verbs, numerals.
#     gives='boundary' from gives='timed_text', ~0 s/min.
# (b) LLM structured extraction over the transcript. 04 §7.2.
#     mixing.chapters.detect_chapters(transcript, *, duration, min_chapters=3, max_chapters=8,
#         min_spacing=10.0, target_count=None, segment_fn=None, model=None) -> list[Chapter]
#     ALREADY EXISTS AND ALREADY ENFORCES DURATION CONSTRAINTS. [verified: read the source]
```

`mixing.chapters.detect_chapters` accepts a Scribe dict, a words list, SRT text, or cue dicts, and
its `_enforce_constraints` handles min-spacing and count bounds **[verified: read the source]**. It
is *"LLM proposes spans over a transcript"*, packaged, in the fleet, today. Tier A's naming problem
is substantially solved by a function that already ships — this is the highest-leverage reuse in
this document.

**Text-side segmentation without an LLM, for completeness [inferred]:** classical topic
segmentation over the transcript — TextTiling (in NLTK), C99, or a cosine-novelty curve over
sentence embeddings from `sentence_transformers 5.5.1` (installed **[verified]**) fed into §2.5's
same Foote operator. It is the identical algorithm on a different feature matrix, which is the third
time that sentence appears in this file and is the strongest argument for factoring the operator out.

### 2.14 LLM over contact sheets, asked cold

- **Assumes:** nothing. This is the "just look at it" method, and it is the only tier-A family that
  can produce *good editorial names* with no other input.
- **Outputs:** boundaries + names + a rationale.
- **Cost:** **billable** — `04 §5.4` measured **$1.16/hour of video on Opus, $0.08 on Haiku**. Plus
  latency: the POC spent ~11 minutes of agent time to pick ten windows (`03-design-brief.md §5.6`).
- **Fails when:** you need sub-second precision (a 4.6 s contact-sheet tile cannot justify a 0.4 s
  boundary — `04 §5.5`, and `06 §1.2` note 5 makes `resolution_s` a first-class field for exactly
  this); and it is non-deterministic, which breaks golden-plan tests.

Two non-negotiables from `04 §5`: **burn the timestamps into the tiles** (§5.2 — not optional), and
**coarse-then-fine** (§5.5) — one cheap pass over the whole video to find macro structure, then a
dense pass inside the region that matters.

**Where it belongs in the design:** not as a default, as an **escalation target** (`06 §3.3` row 4:
*"adjudicating low-confidence spans after the solve — this is where its judgement is actually worth
$1.16/hour"*). `06 §6.3`'s `Budget(usd=0.0)` default means it is not even a candidate until the user
asks for it, and asking is the moment they learn it costs money. That is the right shape.

### 2.15 Unsupervised temporal action segmentation, from the literature

The academic field whose stated task is exactly tier A. I checked what is real and what is
installable, because it is easy to lose a week here.

| method | idea | code | usable on ONE video? | verdict |
|---|---|---|---|---|
| **ABD** (Du et al., **CVPR 2022**) | smooth frame features → frame-wise similarity forms a "⊓" curve per action → detect change points on it | paper only **[from docs]** | **yes — transductive** | **You already have it.** This is §2.5 + `ruptures`. Do not implement a paper; implement the two operators. |
| **TW-FINCH** (Sarfraz et al., **CVPR 2021**) | temporally-weighted 1-NN graph → parameter-free hierarchical clustering of frames | **`pip install finch-clust` 0.2.3, MIT** **[verified: PyPI JSON + raw LICENSE.txt]**; deps scipy/sklearn/numpy | **yes — no training on the target video** | **The one worth taking.** Parameter-free and it gives you a *hierarchy*, which is sub-steps for free. §10. |
| CTE (Kukleva et al., CVPR 2019) | learn a continuous temporal embedding, then cluster | research code | no — needs a corpus | skip |
| **ASOT** (Xu & Gould, **CVPR 2024**) | fused unbalanced Gromov-Wasserstein OT; no action-order assumption | `github.com/mingu6/action_seg_ot` **[from docs]** | no — learns representations over a dataset | skip; revisit if a corpus appears |
| TOT / **UFSA** (2022 / 2024) | OT with frame- and segment-level transcript cues, permutations allowed | research code | no | skip |
| CLOT (**ICCV 2025**) | closed-loop OT, two OT problems + cross-attention | research code | no | skip |
| HVQ (2024) | hierarchical vector quantization | research code | no | skip |
| **StepFormer** (Dvornik et al., **CVPR 2023**) | self-supervised step **discovery and localization**, trained on HowTo100M, no annotations | no maintained package | inference yes, in principle | the closest published thing to `paces`; watch it |
| **Drop-DTW** (Dvornik et al., NeurIPS 2021) | DTW that may **drop** outlier elements from either sequence | `github.com/SamsungLabs/Drop-DTW`, licence not at the expected path **[verified: 404]** | yes | **steal the algorithm, not the repo** — see below |
| GEBD (Shou et al., ICCV 2021) | Generic Event Boundary Detection; Kinetics-GEBD | supervised | — | the right *task formulation*; wrong supervision regime |

**The load-bearing observation about this whole table [inferred].** These methods are benchmarked on
Breakfast / YouTube-Instructional / 50Salads, where the setting is *"many videos of the same
activity, discover the shared action vocabulary"*. **Our setting is one video.** That kills every
corpus-trained row and leaves exactly the two transductive ones — ABD (which is our own §2.5 + §2.16)
and TW-FINCH (which is a 3-line dependency). **The literature's answer to tier A and this document's
answer are the same answer**, which is reassuring and means you can stop reading papers.

**Drop-DTW deserves its own line.** It is DTW with a per-element *drop cost*, so an artifact with no
span and a stretch of media with no artifact are both first-class. That is precisely `05 §2`'s O3 and
O4 relaxations, and `05 §5`'s Needleman–Wunsch gap model is the same idea from the other tradition —
already written up, 25 lines, no dependency (`05 §5.1`). Implement `05 §5`; cite Drop-DTW.

### 2.16 Change-point detection with a known K — the operator that makes K worth asking for

- **Assumes:** you know **how many** steps there are (from a human, a document, a chapter list, or a
  duration/grid argument).
- **Outputs:** exactly K−1 boundaries, optimally, from any curve.
- **Cost:** `ruptures.KernelCPD` **0.188 s at n=4800** — n=4800 is a 40-minute video at a 0.5 s hop
  (`05 §7.3`, `05 §1`). It is free.
- **Fails when:** you do not know K — then you are tuning a penalty, which is peak-picking with
  extra steps.

```python
import ruptures as rpt                                   # 1.1.10, BSD-2-Clause [verified: PyPI JSON]
algo = rpt.KernelCPD(kernel="rbf", min_size=20).fit(signal)   # signal: (n, d)
bkps = algo.predict(n_bkps=K - 1)
```

Two traps `05 §7` measured and you must not re-discover: **use `KernelCPD`, not `Dynp`** (~660×
faster at n=2400, identical optimal answer), and **`jump` defaults to 5**, which silently quantises
every boundary to 5 frames.

`ruptures` is **not installed in p12** **[verified: no `ruptures-*.dist-info`]**. It is the one new
hard dependency this whole design contemplates, and it is optional.

### 2.17 Uniform partition — the baseline you must implement first

- **Assumes:** nothing. Cut into K equal pieces.
- **Cost:** zero.
- **Fails:** always, a bit.

**Build it, register it, and never delete it.** It is the null model. `05 §12` wants an evaluation
harness; a harness without a floor tells you nothing, and *"our clever segmenter beats uniform"* is
the only claim that ever needs defending. `walkthru.core.timeline` is the smarter version of the
same idea — ordered artifacts with authored durations and no media at all (`00 §1`) — and `00 §5`
note 4 is right that the solver should **reduce to it** when there is no signal.

### 2.18 Tier A summary — what to actually run, in what order

```
0.  ffmpeg -vn  ->  wav                                       ~0.1 s/min
1.  sub-bass ratio + probe                                     1.4 s/min   [06 §2.2: 1.31-1.67]
    -> music? speech? silence? static camera? periodic? cuts?
2.  ffmpeg gray pipe 6 Hz + frame-diff energy                  1.4 s/min
    -> ACF periods (free) -> a grid, if the content repeats
3.  ffmpeg lavfi.scene_score (the curve, not the cuts)         0.8 s/min
4.  SigLIP2 frame embeddings @ 6 Hz                            4.4 s/min
    -> Foote novelty -> the boundary curve
    ────────────────────────────────────────────────────────────────────
    running total, everything above:                          ~8.1 s/min
5.  GATED, and only where step 1 says it is worth it:
    beat grid (music spans)                                    0.14 s/min
    ASR (speech spans only)                                   17 s/min * speech_fraction
    pose (movement spans only)                                10.9 s/min * movement_fraction
6.  ESCALATION ONLY, and never by default:
    llm-sheets                                                 $1.16/h Opus, $0.08/h Haiku
```

The **gating in step 5 is the whole design**. It is exactly what the POC did to Whisper with the
sub-bass ratio, applied to every expensive method (`03 §13`). A 30-minute video costs ~4 minutes of
compute for steps 0–4 and stays offline and free.

---

## 3. TIER B — video + a step list (names and order, no times)

**This is the alignment problem proper and it is already fully researched. I am not going to
re-derive it.** Read `05-sequence-alignment-algorithms.md` §0's decision table and `03 §8.3`.

The one-paragraph version, so this section is usable standalone:

- Build an **emission matrix** `S` of shape `(K, T)` — how well step *k* explains frame *t*.
  Producers: SigLIP2 text↔image (`03 §8.3`, +0.15 s), embedding or fuzzy match against the
  transcript (`01 §3.3`, `01 §3.2`), CLAP over audio (`04 §3`), LLM votes (`04 §5`).
- Solve it with the **ordered segmentation DP** (`05 §3`) — ~40 lines, exact, **0.13 s for 9
  artifacts over a 33-minute video**.
- **The order prior is where the accuracy comes from, not the features.** `03 §8.3` measured:
  the DP recovered 4 of 5 boundaries to ≤0.25 s; per-artifact argmax on *the same matrix* got 4 of 6
  and produced a **confident wrong answer for an artifact with no span in the video**. And `05 §0`
  measured a synthetic case where one artifact had *no signal at all* and the DP still placed all
  six boundaries correctly, because neighbours pin it.

**The segmenter is `align()`, with nothing added.** That is the point of §1's decomposition. Tier B
is `Segmenter = identity ∘ align`.

**Two decisions tier B forces on you and the sibling files leave open** (`03` open questions 2, 3):

1. **Cover or gap?** Must the steps tile the media, or may spans be unassigned? The DP as written
   tiles, which is why `03 §8.3`'s last span overran by 10 s. It is one DP state apart (a
   "background" row with a constant emission — `05 §2`). **My recommendation [inferred]: default to
   gaps allowed.** Instructional video has intros, outros, chatter and repeats; requiring a tiling
   makes the *common* case the one that needs a flag.
2. **The null model.** What score means "this step is not in this video"? `03`'s open question 2
   calls it *"the single most important open design question"* and I agree. §9.5 proposes the
   shape it should take at the seam even though the calibration is unknown.

---

## 4. TIER C — video + a full structured document

The que-calor case: a document with **step names, sub-steps, counts, cues, and a tempo** — and,
crucially, one that is **wrong in places**.

Everything from tier B applies, plus four things the structure buys you. Each of these is a
*capability*, not a special case in the segmenter:

| what the document adds | what it enables | cite |
|---|---|---|
| **a count per step** ("4 × 8") | the **duration sanity check** — the highest-value five lines in the POC | `05 §9.5`, `00 §2` |
| **a tempo** ("100 bpm") | a `(offset, period)` grid to fit, so boundaries snap to musical time | `05 §9`, `02 §4` |
| **sub-steps** | a *hierarchy* to place, not a flat list — and the DP can be run per level | `07-annotation-model.md §6.1` |
| **cues** ("genoux souples") | text that CLIP/SigLIP can actually score, unlike "Block 4" | `03 §8.4` |

**The POC's own headline result belongs here and it is a design requirement, not an anecdote:**
the document said **100 bpm**; the audio said **129.2 bpm**; 44 × 8-counts at 100 bpm is 211 s
against a 170 s music span, so the arithmetic proved the *document* wrong (`ADR-0001`,
`02-technical-recipes.md §3`). Nothing in the fleet does this check (`00 §2`).

Which forces the design rule `03-design-brief.md §4` already states and I am restating because it
is the whole difference between tier C and tier B:

> **The document is a hypothesis, not ground truth.** The segmenter's job is *confirm / correct /
> resolve / add*, and **"the doc said X, the video shows Y" is a first-class output**, not a warning
> to swallow.

`Segmentation.flags` (§9.1) is where that output lives, and `06 §4.3`'s *validators are a third kind
of capability* is exactly the right home for the duration check: it `gives` nothing, it `needs`
`artifacts.durations`, and it raises a flag. Register it; do not inline it.

**One thing tier C must not lose.** `03-design-brief.md §5.1`: **a step has many spans.** The
run-through and the breakdown are the same step seen twice; six of nine POC blocks shipped both.
A tier-C segmenter that returns one span per step throws away half of what the video contains.
§9.1's `Step.spans` is a tuple for this reason, and §2.11 is the mechanism that finds the second one.

---

## 5. TIER D — video + a steering prompt only

The user gives you a paragraph. No step list. This tier exists because the POC proves the paragraph
is worth more than it looks.

The actual POC prompt carried two things no analysis would have produced
(`03-design-brief.md §3`):

> *"first the person on the video talks, then she goes through the whole phases, while music is
> playing, then she breaks them down and explains."*
>
> *"it may not be exactly as described in the phases — I think she changed a few things … but
> should be more or less the same, same order."*

The first sentence **is a macro-segmentation**. It says: three regions, in this order, with these
acoustic characters. That converts tier A's hardest problem — where do I even start — into three
easy sub-problems with different best methods.

**The design [inferred], and it is the one place `06 §2.6` already puts the LLM:**

```
steering (free text)  ──one LLM call, no media, structured output, validated──►  Prior
                                                                                  │
                                            ┌─────────────────────────────────────┘
                                            ▼
   Prior.macro = [('talk', 'speech'), ('run-through', 'music'), ('breakdown', 'speech')]
   Prior.ordered = True ; Prior.k_hint = None ; Prior.unit = '8-count' ; Prior.repeats = 2
                                            │
                     ┌──────────────────────┴───────────────────────┐
                     ▼                                              ▼
      §2.12 sub-bass ratio LOCATES the macro regions      each region gets its own
      (0.008 s/min, 21x separation)                       tier-A plan inside it
```

Three properties this shape has that a "give the LLM the video" design does not:

1. **The LLM never sees media.** One call, bounded cost, deterministic downstream. `06 §3.3` is
   emphatic that keeping the LLM out of the control loop is what makes golden-plan tests possible,
   and those are the cheapest regression suite in the design (`06 §8.4`).
2. **The macro claim is *checkable*.** "Then music plays" is a prediction the 0.008 s/min sub-bass
   ratio either confirms or refutes. A steering prompt that the media contradicts is a flag, and
   the user finds out their assumption was wrong — which, per tier C, is a feature.
3. **The prompt is persisted and replayable.** `03-design-brief.md §3`: *"it is part of the source,
   like a compiler flag file."* A design that consumes it once at the CLI produces a library that
   only works on content whose structure the analyser already happens to guess.

**What steering cannot do:** give you names for the steps. It gives you *structure*. Tier D
therefore usually ends in tier A inside each region, which is fine, because tier A inside a
15-second region with a known character is a much easier problem than tier A over 11 minutes.

**Steering as a `Prior` field, not a segmenter.** `06 §6.1`'s `align(..., steering: str = '')`
already has the parameter. Do not add a `SteeringSegmenter`; add a capability that
`gives='prior'` — see §9.3's one honest extension to the fact vocabulary.

---

## 6. TIER E — chapters, subtitles, description, and one signal nobody uses

**Cheap, extremely common, and the tier most likely to be skipped because it is boring.** Four
sources, all of which cost approximately nothing.

### 6.1 Container chapters — `ffprobe`, free, O(1) in duration

```bash
ffprobe -v quiet -print_format json -show_chapters in.mp4
```

**[verified this session]** on a file I built with `-map_metadata` from an FFMETADATA1 chapter block:

```json
{"chapters": [
  {"id": 0, "time_base": "1/1000", "start": 0,     "start_time": "0.000000",
   "end": 8000,  "end_time": "8.000000",  "tags": {"title": "Warm-up"}},
  {"id": 1, "start_time": "8.000000",  "end_time": "17.000000", "tags": {"title": "Block 1 - the basic step"}},
  {"id": 2, "start_time": "17.000000", "end_time": "30.000000", "tags": {"title": "Block 2 - travelling"}}]}
```

**Cost: 0.026 s total** on a 30 s file, and it is **O(1) in media duration** — it reads the container
header, not the stream. **[verified: `time ffprobe …` → `0.026 total`]** MP4, MKV, WebM and Ogg all
carry chapters. This is *names and boundaries, complete, for free*, and it is one subprocess.

### 6.2 YouTube chapters — three sources, tried in order, already implemented

`yt_dlp 2026.03.17` is in p12 **[verified: `version.py`]**, and its YouTube extractor tries three
chapter sources with a documented fallback ladder **[verified: read
`yt_dlp/extractor/youtube/_video.py:4398-4402`]**:

```python
info['chapters'] = (self._extract_chapters_from_json(initial_data, duration)          # markers map
                    or self._extract_chapters_from_engagement_panel(initial_data, duration)
                    or self._extract_chapters_from_description(video_description, duration)
                    or None)
```

The third is the one that matters for instructional content: **timestamps typed into the
description** (`0:00 intro / 1:24 the basic step / …`) are parsed for you, including the loose form
(`_extract_chapters_from_description` calls `_extract_chapters_helper` twice, `strict=False` first
**[verified: `extractor/common.py:4012-4018`]**). You do not need to write a timestamp regex.

```bash
yt-dlp --skip-download --write-info-json <url>     # info.json carries 'chapters', 'subtitles',
                                                   # 'automatic_captions', 'heatmap', 'duration'
```

Cost: one network round trip, ~1–3 s **[inferred]**.

### 6.3 Subtitles and SRT/VTT

- Uploader-provided subtitles are **human-written and cue-timed** — better than any ASR you can run,
  and free.
- **Auto-captions are ASR output you did not have to pay 17 s/min for** (`06 §1.4`). They lack word
  confidences and punctuation is unreliable, but for §2.13(a)'s lexical cue detection that does not
  matter — you need "now", "next", "then" and their times.
- **`srt 3.5.3` is installed in p12** **[verified: `srt-3.5.3.dist-info`]** and needs no new
  dependency. `webvtt-py` (0.5.1, MIT) and `pysubs2` (1.9.0, MIT) are **not** installed
  **[verified: PyPI JSON for versions/licences; absence verified on disk]**. `mixing.chapters
  .detect_chapters` **accepts SRT text directly** **[verified: read the docstring]**, so the whole
  path from a `.srt` file to a chapter list already exists.

### 6.4 The re-watch heatmap — the signal nobody uses

**This is the one genuinely new finding in this file.** `yt_dlp` extracts YouTube's "most replayed"
graph and exposes it as `info['heatmap']` **[verified: read `_extract_heatmap`,
`extractor/youtube/_video.py:2373-2381`]**:

```python
# 100 markers, each:
{'start_time': float_seconds, 'end_time': float_seconds, 'value': intensity_normalized_0_1}
```

For an *instructional* video this is not a vanity metric — **it is crowd-sourced annotation of where
the content is**. People scrub back to the part where the move is actually demonstrated and skip the
introduction. So:

- **as a boundary curve:** it is a 100-bucket signal on the media clock. Feed it to §2.5's novelty
  operator or §2.16's `ruptures` like any other curve. Resolution is `duration/100` — 6.5 s on the
  POC's 10:51 video, which is coarse but not useless.
- **as a prior on *importance*:** high-heatmap spans are where the demonstration is; low ones are
  intro/outro. That is a `Prior` on which regions may be background (§3's cover-or-gap question).
- **as a free validator:** if your segmenter puts a step boundary in the middle of the single most
  re-watched five seconds of the video, you probably cut a demonstration in half. Flag it.

**Cost: zero** — it arrives in the same `info.json` as the chapters. **Availability: only for
YouTube, only for videos with enough views** — the POC's unlisted wedding video will have none.
Which is exactly why it is a *boost*, never a `needs`.

### 6.5 Tier E verdict

**Never a segmenter of its own; always a proposer.** Chapters give a step list with *approximate*
times — YouTube chapter timestamps are typed by a human and are routinely a few seconds early.
So: use them for the **names and the count**, then hand both to tier B's `align()` to get the times
right. That is `Segmenter = chapters ∘ align`, ~40 lines, and it should be in v1 as a *proposer*
rather than as a fourth registered segmenter (§10).

---

## 7. TIER F — ask the user

Not a cop-out and not a fallback. **It is the only method that produces ground truth**, which makes
it the thing every other method is evaluated against (`05 §12`, `06 §8`), the escalation target when
confidence is low (`06 §4`), and the *training data generator* that would let `06 §3.4`'s learned
planner ever exist. Design it as a first-class capability.

### 7.1 The design goal, stated as a number

> **Two minutes, not thirty.** A 10-minute video with 9 steps, segmented by hand in a scrubbing UI,
> is a 20–40 minute job. The machine's job is to make it a 2-minute job. Everything below is in
> service of that one number.

### 7.2 What the machine pre-computes, and why each item removes a specific minute

| pre-computed | removes | cost |
|---|---|---|
| **a boundary candidate set** — top ~40 peaks of the fused curve, ranked | *scrubbing.* The human picks from a shortlist instead of hunting frame by frame | free, from §2.18 |
| **a contact-sheet filmstrip with burnt-in timestamps**, one tile per candidate | *playback.* Most boundaries are recognisable from a still | `04 §5.1`; ~1 s |
| **a proposed K**, with the evidence for it (ACF harmonics, chapter count, novelty peak count) | *counting.* The human confirms a number instead of deriving it | free |
| **the derived transcript, aligned to the strip** | *naming.* The human picks the teacher's own words instead of typing | 17 s/min, or free from tier E |
| **the audio waveform + beat grid under the strip** | *precision.* On rhythmic content the boundary is a downbeat and the eye finds it instantly | 0.14 s/min |

### 7.3 The interaction, in the order it should happen

**Step 1 — one integer.** *"How many steps are in this video?"* with the machine's guess pre-filled
and its reasoning shown. This is the highest-value question you can ask a human, because it is the
one input that converts an ill-posed peak-picking problem into an exactly-solvable one
(§2.16, `05 §7.2`). **If the human answers only this and closes the tab, the segmenter still
improves.** Design the interaction so that is true of every step.

**Step 2 — tap along.** Play at 1× (or 2× for a long video); the human presses the spacebar at each
transition. A 10-minute video is 5 minutes at 2×, and taps require no precision because:

**Step 3 — snap.** Each tap snaps to the nearest candidate boundary within ±1.5 s, or to the nearest
downbeat if there is a grid. The human's job is to be *approximately right*, which humans are fast
at; the machine's job is to be exactly right, which it can do given approximately-right.

**Step 4 — name, from a menu.** For each span, offer: the transcript text spoken in it, the OCR text
visible in it, the chapter title covering it, and a free-text field. Ranked, so the common case is
one keystroke.

**Step 5 — re-solve, and show what moved.** A single pin re-solves *everything* (§7.5). Showing the
human that fixing block 4 also fixed blocks 3 and 5 is what makes the next correction feel worth
making.

### 7.4 The `ask` capability is a *function*, not a UI

```python
def ask(media, *, candidates: Segmentation, ui: Callable[..., Segmentation] | None = None,
        ) -> Segmentation:
    """Human-in-the-loop segmentation. `ui` is the seam."""
```

The default `ui` is a **static self-contained HTML page written to disk and opened in a browser**,
which posts nothing and instead has the human copy back a JSON blob or writes it via a one-shot
local file. It needs no server, no framework, no new dependency, and the POC already proves the
house can build exactly this page (`02-technical-recipes.md §10`). Replaced later by the real
frontend (`06-surfaces-and-conventions.md`), a CLI prompt, a notebook widget, or an *agent*
answering on the user's behalf — which is the case that makes `ask` interesting: **an agent with the
contact sheet in context is a legitimate `ui`**, and it is `llm-sheets` wearing a different hat.

### 7.5 How the human's answer survives a re-run — and where I disagree with `06`

`06 §5` has this almost entirely right and I am reusing it wholesale:

- A correction is a **`Prior.anchor`**, and anchoring is *"a **pruning** of the solver's search,
  never a separate code path"* (`05 §13`). So one pin re-solves all the neighbours for **0.13 s**.
- Corrections are a **log with provenance**, stored separately from the result in `lacing`
  (PROV-O, body-schema registry with migrations — `00 §1`). *"Re-running with a better method keeps
  the human's knowledge. A correction log applied to a fresh solve is a strictly better run; a
  corrected result is a dead end."*
- `media_key` records which rendering a correction was true of, and
  `mixing.transcript.formats.remap_time_after_cuts` migrates the log across a re-cut (`00 §1`).
- **A correction is never silently dropped.** An anchor that makes the problem infeasible is an
  `error` flag with a relaxation-ladder suggestion (`05 §3` classifies infeasibility already).

**Two places where cold segmentation breaks `06 §5` and needs more.** Both come from the same root
cause: `06` assumes the artifact list is *given*, so K is fixed and ids are stable. In tier A neither
is true.

**(a) `06 §5.2` says three verbs — `pin`, `forbid`, `absent` — and explicitly resists `split` and
`merge` because they are expressible as a pin plus a re-solve. That argument holds only when K is
fixed.** In cold segmentation `split` and `merge` *change K*, and a change in K is not expressible as
any constraint on a K-step solve. They are genuinely new information — *the most valuable
information the human can give*, because K is the thing tier A cannot determine (§7.3 step 1).
So the verb set for a segmenter is **five**:

```python
def pin(seg, step_id, span)   -> Correction   # "it is HERE"            -> anchor
def forbid(seg, step_id, span)-> Correction   # "it is not there"       -> allowed mask
def absent(seg, step_id)      -> Correction   # "not in this media"     -> exhaustive=False
def split(seg, at_t)          -> Correction   # "that is two steps"     -> K += 1   [NEW]
def merge(seg, at_t)          -> Correction   # "those are one step"    -> K -= 1   [NEW]
```

`rename` is deliberately **not** a verb: a name is content, not a constraint, and it belongs in the
document layer (`07-annotation-model.md`) where the fleet's regenerate-without-losing-human-edits
machinery already lives (`docs/README.md` finding 3). Keeping the correction log to *constraints
only* is what lets it be replayed against a completely different segmenter.

**(b) `06 §5.4`'s `Correction.artifact_id` cannot be the key.** A step id invented by run 1 may not
exist in run 2 — a better segmenter finds 10 steps where the old one found 9, and every id after the
insertion point now means something different. **Key a correction by its time, not by its id:**

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class Correction:
    verb: Literal['pin', 'forbid', 'absent', 'split', 'merge']
    anchor_t: float                    # WHERE on the media clock. The durable key. [NEW vs 06 §5.4]
    span: Span | None = None
    step_id: str | None = None         # convenience for display; NEVER the join key
    author: str
    at: str                            # ISO timestamp
    media_key: str                     # which rendering this was true of (02 §10.5)
    reason: str = ''
```

`anchor_t` is stable under any change of K, any change of method, and any change of naming; it
survives a re-cut via `remap_time_after_cuts`; and it degrades gracefully — a `pin` whose time now
falls inside a differently-shaped step still constrains that step. **This is the single change this
file makes to `06`'s design, and it is the one that makes human effort a permanent asset rather
than a per-run expense.**

---

## 8. TIER G — hybrid and escalation

The default path, in practice. Nothing above is a whole answer on its own.

**The loop, reusing `06 §4` unchanged:**

```
plan → run → solve → validate → is anything under-determined?
                                    │ no  → done
                                    │ yes → add ONE producer to the SAME solve, re-solve
                                            (never patch one boundary in isolation)
```

Three rules from `06 §4` that a segmenter must not re-litigate:

1. **Escalate by adding evidence, not by patching a boundary.** `05 §10.2` measured fusion
   **halving** boundary MAE. A patched boundary is inconsistent with its neighbours; a re-solve is
   not.
2. **The trigger is `max(posterior width, model-external disagreement)` — never the posterior
   alone.** `05 §11.2` measured a boundary with `sd = 14.8 s` that was *correctly* uncertain, and
   one with `sd = 1.0 s` that was **wrong by 18.5 s**. Confidently wrong is the failure mode that
   destroys trust and it is invisible to a confidence-sorted list.
3. **Never use absolute thresholds** (`06 §4.4`) — every method's score lives in its own regime
   (`04 §8.3`: SigLIP match range 0.095–0.152, CLAP 0.369). Rank, or normalise within a regime, or
   fall back to rank fusion (`05 §10.3`).

**The escalation ladder for a segmenter [inferred], cheapest first:**

```
novelty-k (free-ish)  →  add pose periodicity (10.9 s/min, if person_visible)
                      →  add ASR + transcript cues (17 s/min * speech_fraction)
                      →  add llm-sheets  ($, and only if Budget.usd > 0)
                      →  ask the user    (2 min of human, and it ends the loop)
```

Note the ladder **ends at a human**, deliberately. `06 §4.5`'s "when to give up" and §7 are the same
rung: giving up *is* handing a well-prepared question to a person.

---

# PART 2 — the seam design

## 9. `Segmenter`

House style throughout: keyword-only seams defaulting to the strongest implementation that needs no
new dependency; `collections.abc` at the edges; frozen `slots=True kw_only=True` dataclasses; small
functions; data over classes; functional over OOP.

### 9.1 What a segmentation IS, before it becomes steps

The return type is the most important decision in this file, because it is what every implementation
must produce and every renderer must consume.

```python
Span = tuple[float, float]                    # seconds, half-open, as in lacing
MAPPING_0 = field(default_factory=dict)

@dataclass(frozen=True, slots=True, kw_only=True)
class Step:
    """One named piece of the media. The unit a learner practises."""
    id: str
    name: str = ''                            # '' means "found, not named" -- a VALID state
    spans: tuple[Span, ...] = ()              # MANY, not one: run-through AND breakdown (brief §5.1)
    confidence: float = 0.0
    children: tuple['Step', ...] = ()         # sub-steps, when the input had a hierarchy
    source: str = ''                          # which capability named it
    evidence: Mapping[str, Any] = MAPPING_0   # WHY. Never a bare float (00 §5 note 3)

@dataclass(frozen=True, slots=True, kw_only=True)
class Segmentation:
    """What every segmenter returns. Reviewable, re-runnable, arguable."""
    steps: tuple[Step, ...] = ()              # ordered. MAY BE EMPTY while boundaries is not.
    boundaries: tuple[float, ...] = ()        # the raw cut set, ALWAYS, even when naming failed
    unit: str = 'seconds'                     # '8-count' | 'rep' | 'seconds'   (brief §5.2)
    grid: 'Grid | None' = None                # (phase, period, meter) when one was found (02 §1)
    confidence: float = 0.0
    method: str = ''                          # the plan, as a name
    profile: 'Profile | None' = None          # 06 §2.7 -- what was measured
    plan: 'Plan | None' = None                # 06 §6.2 -- what was chosen and why
    alignment: 'Alignment | None' = None      # 06 §6.2 -- the placement result underneath
    flags: tuple['Flag', ...] = ()            # 06 §4.3 -- validators, incl. the doc-vs-video diff
    corrections: tuple['Correction', ...] = ()# §7.5 -- what a human has said, replayed
    elapsed_s: float = 0.0
    spent_usd: float = 0.0
```

**Six decisions in that, each paid for by something a sibling measured:**

1. **`boundaries` is separate from `steps`, and it is always populated.** This is the type-level
   expression of §0's rule 5. A video-only run that finds nine excellent cuts and cannot name any of
   them returns `steps=()` and `boundaries=(t1…t8)` — a *useful, honest* result that the `ask` UI
   turns into a finished segmentation in two minutes. A shape that forced names would either
   confabulate them (`03 §8.3`'s kanban row) or throw the boundaries away. Both are worse.
2. **`Step.spans` is a tuple.** `03-design-brief.md §5.1`: six of nine POC blocks had both a
   run-through and a breakdown span. *"A `{step → one time range}` model is wrong on day one."*
3. **`unit` is on the segmentation, not derived.** `03-design-brief.md §5.2`: the dance's unit is
   the 8-count and seconds are *derived* (`8 × 60/bpm`). Storing only seconds throws away the thing
   the learner actually counts. A recipe's unit is minutes-or-until-done; a workout's is reps.
4. **`evidence` is a `Mapping`, never a float** (`00 §5` note 3): *"a method that returns only a
   number cannot be composed, argued with, or debugged."*
5. **`plan` and `profile` ride along.** `06 §5.3`: the column that turns *"the tool did badly"* into
   *"the tool never had a transcript because `mlx_whisper` isn't installed"* is the list of what was
   **not** run and why not. It is free to carry and it is the difference between a debuggable tool
   and a mysterious one.
6. **`Segmentation` is not a `StepDocument`.** `07-annotation-model.md §6` owns the document type,
   with cues, derived assets, provenance and edit protection. `Segmentation` is the *analysis
   result*; the document is the *artifact*. The projection is one function
   (`to_document(seg, *, notes=None) -> StepDocument`) and keeping them separate is what lets the
   segmenter be re-run without touching hand-edited captions (`03-design-brief.md §5.5`).

### 9.2 The call signature

**One verb, one seam, and the seam has the name the design brief already declared** —
`03-design-brief.md §6` lists `segmenter=` with default `align-to-notes`. This refines that default
and keeps the name.

```python
def segment(
    media: Media,
    *,
    # ── the seam. None = plan it from what is present (§9.4). A name pins it. ──────────
    segmenter: str | Sequence[str] | Capability | None = None,

    # ── the optional inputs. Their PRESENCE is what selects the default. ──────────────
    steps: Sequence[str] | Sequence[Step] | Mapping[str, str] | None = None,   # tier B
    notes: str | Path | 'StepDocument | None' = None,                          # tier C
    steering: str = '',                                                        # tier D
    metadata: Mapping[str, Any] | None = None,                                 # tier E (info.json)
    k: int | None = None,                                                      # §7.3 step 1
    corrections: Iterable[Correction] = (),                                    # §7.5

    # ── the other seams, each defaulting to the strongest no-new-dependency thing ─────
    solver: str = 'auto',            # 05 §13's registry; 'auto' = ordered_dp with gaps
    budget: 'Budget | float | None' = None,   # None = Budget.default(): 60 s/min, $0, offline
    profile: 'Profile | None' = None,         # None = probe it (06 §2). Pass to reuse.
    catalog: 'Catalog | None' = None,         # Mapping[str, Capability]; the testability seam
    on_progress: Callable[['Event'], None] | None = None,
) -> Segmentation:
    """Cut `media` into named steps, using whatever else is present.

    Returns a Segmentation ALWAYS. A segmenter that cannot name the steps returns
    `boundaries` and `steps=()`; one that cannot find boundaries returns both empty
    with a flag. Neither is an exception -- see §9.5.
    """
```

**Why the inputs are separate keyword arguments rather than one `inputs: Inputs` bag.** Progressive
disclosure. `segment("routine.mp4")` is the whole tier-A call; `segment(v, notes=doc)` is the whole
tier-C call. A bag makes the simple case require constructing an object, which is the failure mode
the house style names first. Internally they normalise into one `Inputs` record at the boundary
(`06 §6.5`) so exactly one place knows the mapping from arguments to facts.

**Three levels, per `06 §6.4`:**

```python
# 1. Simple things simple.
segment("routine.mp4")

# 2. The common real case.
segment("routine.mp4", notes="choregraphie.html",
        steering="9 blocks, in order, 8-counts, roughly 130 bpm; she does a run-through then breaks it down")

# 3. Complex things possible.
prof = probe("routine.mp4", extras=('person',))
p    = plan(prof, require=('pose-rtmlib',), exclude=('siglip2-frames',))
print(p.explain())
seg  = segment("routine.mp4", profile=prof, segmenter=[s.name for s in p.steps])
```

### 9.3 How a segmenter declares what it needs — reusing `Capability` unchanged

**`06 §1.2`'s `Capability(needs, gives, …)` already does this and I am not proposing a second
record.** A segmenter is a capability whose `gives` is a new product; a *proposer* is a capability
whose `gives` is a step list. Concretely:

```python
Product = Literal[
    'grid', 'regions', 'curve', 'timed_text', 'boundary',
    'emission', 'placement', 'alignment', 'placements',   # <- 06 §1.1's nine, UNCHANGED
    'steps',          # NEW: an ordered, named step list -- WITHOUT times
    'segmentation',   # NEW: the §9.1 result -- steps WITH times
]
```

**Two new products, and I want to defend the count.** `06 §1.1` collapsed five sibling Protocols into
one record precisely so that the planner is backward chaining on a small graph; adding products is
adding graph nodes and must be justified.

- **`steps` is not `placements`.** `placements` is *artifacts you were given, now located*.
  `steps` is *a list that did not exist before* — no times, no artifact ids, possibly the wrong
  count. It is the output of §5's steering parser, §6's chapter reader, §2.13's transcript
  extractor, and §7's human. **It is the thing the whole file is about**, and collapsing it into
  `placements` would make the planner unable to express *"first invent a list, then place it"* —
  which is §1's decomposition and therefore the design.
- **`segmentation` is not `alignment`.** `alignment` is boundaries + assignment over a **known K**.
  `segmentation` may have chosen K itself, carries a unit and a grid, and is the package's public
  output. Making it a distinct node is what lets a capability declare
  `needs={'boundary'}, gives='segmentation'` — a pure namer — versus
  `needs={'video'}, gives='segmentation'` — an end-to-end one.

That is **eleven products, two of them new**, and the rest of `06 §1.2`'s record — `needs`,
`requires`, `licence`, `boosts`, `penalties`, `s_per_min`, `usd_per_hour`, `device`, `fixed_s`,
`resolution_s`, `regime`, `calibrated_on`, and the lazy `target: str` — is used **verbatim, with no
new fields**. That is the test of whether the reuse is real, and it passes.

**The fact vocabulary extension.** `06 §1.3` insists the vocabulary stays **closed** — *"a capability
that wants a fact not on this list must either add it to the list (with a probe that measures it,
and a cost) or stop asking."* Segmentation needs **seven** new facts, all in the free
"artifact-set / input" half, none requiring a probe:

| new fact | type | measured by | cost |
|---|---|---|---|
| `steps.given` | bool | was `steps=` passed | free |
| `steps.count` | int | `len(steps)` or `k=` or a chapter count | free |
| `notes.text` | bool | was `notes=` passed at all | free |
| `notes.structured` | bool | does it parse into a hierarchy with counts/cues (tier C vs a flat list) | free |
| `meta.chapters` | int | `len(ffprobe/info.json chapters)` | **0.026 s, O(1)** [verified] |
| `meta.subtitles` | bool | a subtitle track or `.srt` is present | free |
| `human.available` | bool | policy: is a human in this run's loop at all | free |

`meta.heatmap` is deliberately **not** a fact — it is a *curve producer* (§6.4), and the planner
sees it as `gives='curve'` like everything else. Resist the urge to make every input a fact; a fact
is something the **selector** branches on, and the heatmap is something a **solver** consumes.

**`steps.count` is an `int`, not a flag**, exactly as `06 §1.3` made `artifacts.count` an int — and
here it is load-bearing rather than tidy, because it is the difference between §2.16's exact
`KernelCPD(n_bkps=K-1)` and peak-picking.

### 9.4 The default-selection rule — a table, and it is *generated*

**The user's requirement is that the default follows from what is present. It already does, with no
new mechanism:** `06 §3.1`'s three hard filters plus a ranked budgeted walk. The table below is
therefore **not a `dispatch` dict to maintain** — it is what you get by printing the planner's choice
for each input combination, and it is a **test fixture** (`06 §8.4` runs the planner with a fake
catalog and no media at all, in milliseconds).

| inputs present | facts set | plan chosen | cost / min | gives you |
|---|---|---|---|---|
| video | `video` | `probe → curves → foote-novelty → name-abstain` = **`novelty-k`** | ~8 s | boundaries, no names |
| video + `k=9` | `+ steps.count=9` | `novelty-k` with `changepoint(n_bkps=8)` | ~8 s | exactly 8 boundaries |
| video, music detected | `+ music, metronomic` | `+ beat-this → grid-fit`, boundaries snap to downbeats | +0.14 s | boundaries on musical time |
| video, speech detected | `+ speech` | `+ asr-mlx → transcript-cues` | +17 s × speech-frac | boundaries **and names** |
| video, periodic motion | `+ periodic_motion` | `+ pose-rtmlib → acf-periods → grid-fit` | +10.9 s | a unit, and a count from duration/period |
| video + on-screen text | `+ onscreen_text` | `+ ocr-tesseract` | +14.4 s | boundaries **and names** |
| **video + chapters** | `+ meta.chapters=9` | `chapters → align-to-steps` | **+0.03 s** | named spans, refined |
| video + subtitles | `+ meta.subtitles` | `subs → transcript-cues → align-to-steps` | +0.1 s | named spans, no ASR bill |
| video + step list | `+ steps.given, ordered` | **`align-to-steps`** (= `06`'s `align()`) | ~8 s | named spans |
| video + structured doc | `+ notes.structured` | `align-to-steps` + `grid-fit` + `duration-check` | ~9 s | named spans, sub-steps, **doc diff** |
| video + steering only | `+ steering` | `steer → macro regions → per-region plan` | ~8 s + 1 call | structure, then tier A inside |
| any + a human | `+ human.available` | whatever above, then **`ask`** on the low-confidence spans | +2 min human | ground truth |
| budget raised (`usd>0`) | — | `llm-sheets` becomes a *candidate*, and only then | $0.08–1.16/h | editorial names |

**Read the table's shape, not its rows.** Every row below the first is *the previous row plus one
capability*. That is what `needs`/`gives` chaining buys, and it is why adding tier E cost 40 lines
and no edits. The rows are not branches in a function; they are the output of
`argmax(Σ rank − λ·cost)` over the catalog.

**The hard-refusal cases stay rules, per `06 §3.5`:** `forced-align-ctc` needs `artifacts.verbatim`
(paraphrased text produces *confidently wrong* word times), and licence is an allowlist filter, not
a penalty. Neither is a degradation; both are confident lies.

### 9.5 Confidence, and what a segmenter does when it is not sure

**The rule, and it is one sentence:**

> **A segmenter may never return a step count it has no evidence for.**

Which yields four legitimate return states, all of them non-exceptional, and the type in §9.1
expresses all four without a single optional flag:

| state | `boundaries` | `steps` | `confidence` | flags | means |
|---|---|---|---|---|---|
| **confident** | populated | populated, named | high | — | done |
| **found, unnamed** | populated | `()` | boundary confidence | `('naming-abstained',)` | **the tier-A default outcome.** Hand to `ask`. |
| **proposed, uncertain** | populated | populated | low | `('low-confidence', …)` | escalate (§8) or review (`06 §5.3`) |
| **refused** | `()` | `()` | 0.0 | `('no-signal', 'try: k=…, notes=…')` | honest failure, with the fix named |

**Three things confidence must obey, all of them measured by siblings:**

1. **`calibrated_on: str | None` defaults to `None` and that means "not decision-grade"**
   (`06 §1.2` note 3). SigLIP's match range is 0.095–0.152, CLAP's 0.369 (`04 §8.3`). A confidence
   without a stated regime is noise, and making the field `None` by default makes it *structurally
   unable* to be compared — the fusion layer falls back to rank fusion (`05 §10.3`).
2. **Report boundary precision no finer than `max(resolution_s)` of the contributing evidence**
   (`06 §1.2` note 5). A 4.6 s contact-sheet tile cannot justify a 0.4 s boundary; a 100-bucket
   heatmap on an 11-minute video cannot justify better than 6.5 s. Clamp it and say so.
3. **Show a random sample of the *high*-confidence placements in review** (`06 §5.3`). `05 §11.2`
   measured a boundary with `sd = 1.0 s` that was wrong by 18.5 s. Confidently-wrong never surfaces
   in a confidence-sorted list and it is the error that destroys trust.

**And the open one, stated so it is not lost:** `03`'s open question 2 — *what is the null model for
"this step is not in this video"?* — is still open. The seam's answer is that the null must be
**expressible**, not that it is solved: `Step.spans = ()` with a flag is a step that was proposed
and not found, and `05 §2`'s O4 relaxation (a skip in the transition, or a gap in the query) is the
solver-side mechanism. Which threshold decides is a calibration question, and §2.8's OCR
ground-truth trick is the cheapest way to get the data to answer it.

### 9.6 Open-closed: what adding a new segmenter actually costs

**The test of the whole design.** Adding TransNetV2 (§2.1) as a boundary source:

```python
# in paces/segmenters/transnet.py -- A NEW FILE. Nothing else in the package is touched.
register(Capability(
    name='transnet-cuts',
    gives='boundary',
    needs={'video', 'cuts'},                     # only offered on edited footage
    requires=('transnetv2_pytorch', 'torch'),    # preflighted; the error names the pip install
    licence='MIT',                               # [verified: soCzech/TransNetV2 LICENSE]
    target='paces.segmenters.transnet:cuts',     # LAZY -- listing it does not import torch
    summary='Learned shot-boundary detection (TransNetV2).',
    boosts={'cuts': 3.0},
    penalties={'static_camera': 3.0},            # 03 §0: one take -> zero shot cuts, nine steps
    s_per_min=6.0, fixed_s=2.0, device='mps',
    resolution_s=0.04, calibrated_on=None,
))
```

**Files edited: zero. Functions edited: zero.** It becomes a planner candidate, appears in
`list_capabilities()`, is preflighted, is budgeted, is licence-filtered, and is *not* selected on a
single-take dance video because `penalties={'static_camera': 3.0}` says so — and that piece of
knowledge now lives next to the method's measured cost instead of inside a planner `if`, which is
`06 §3.2`'s third and best argument for the linear model.

The same three lines add a proposer (`gives='steps'`), a validator (`gives=None`, raises flags —
`06 §4.3`), or a whole end-to-end segmenter (`gives='segmentation'`). **One record type, one
registration, three kinds of extension.**

**The lazy `target: str` is not optional.** `muvid/footage/strategy.py`'s
`_LAZY_STRATEGIES: {slug: "module:func"}` **[verified in `06 §1.2` note 6]** is the fleet's answer,
and it is what makes *"the catalogue with costs, cheaply"* true — an agent must be able to enumerate
a torch-backed segmenter without importing torch. That property is the agent surface.

### 9.7 What this seam deliberately does not do

- **It does not own the document.** `07-annotation-model.md §6`'s `StepDocument` is downstream, and
  the projection is one function. Regeneration-without-losing-edits is already solved in the fleet
  (`docs/README.md` finding 3) and re-solving it here would be the second copy.
- **It does not own persistence.** `to_store(seg, *, store, asset_id)` → `lacing` stays a separate
  call (`00 §5`). Keep the computation pure; that is what makes both halves testable.
- **It does not own the registry.** `muvid.align` already *is* an aligner registry with dispatch, a
  `requires` preflight and a `lacing` writeback (`00 §3.1`). Generalise that one and have `muvid`
  import it back. **Do not leave two registries in the fleet.**

---

# PART 3 — recommendation

## 10. Build exactly three, and make one of them the default

### The three

**1. `align-to-steps` — the default whenever *anything* supplies a step list.**

It is `06 §6.1`'s `align()` with a `Segmentation` wrapper, and it covers **tiers B, C, D and E**
because all four end in "now place this list". It is the POC's proven path — the only path with
evidence behind it (`docs/README.md`: *"nothing here segmented a video cold"*). Under it:
`05 §3`'s ordered DP with gaps allowed, `03 §8.3`'s emission matrix, `05 §9.5`'s duration check as a
registered validator.

*Ship with it, as proposers rather than segmenters (~40 lines each, `gives='steps'`):*
`chapters` (§6.1–6.2 — ffprobe + yt-dlp, near-free), `subs` (§6.3 — `srt` is already installed), and
`transcript-cues` (§2.13a — free once you have any transcript). **These three proposers are the
highest value-per-line in the entire document** and they are why tier E gets a whole section.

**2. `novelty-k` — the default when you have only a video.**

Defined precisely:

```
derive audio  →  probe (06 §2)  →  build a FUSED boundary curve:
                                      SigLIP2 embedding novelty      (03 §8.2)   4.4 s/min
                                    + frame-diff / motion novelty     (03 §4.1)   1.4 s/min
                                    + audio novelty & sub-bass regions(02 §6.1)   0.8 s/min
              →  cut it:  K known  → ruptures.KernelCPD(n_bkps=K-1)   (05 §7.2)   0.19 s
                          K unknown→ Foote peak-picking, top-N        (03 §8.2)   free
              →  snap to the grid if §2.4 or beat-this found one      (05 §9)
              →  NAME only if a free namer fired (ASR cues / OCR / chapters);
                 otherwise return boundaries with `naming-abstained`.
```

**3. `ask` — human-in-the-loop, and it is the escalation target for both of the above.**

§7's design: K first, tap-along second, snap third, name-from-a-menu fourth. Default `ui` is a
static HTML page written to disk; the seam is `ui=`.

### The default for video-only, and what I am trading away

**`novelty-k` is the default, and it does not name the steps.**

**What I am trading away, explicitly:**

- **Names, in the default path.** This is the whole trade and I want it stated baldly. Naming cold
  costs either **$1.16/hour** (`llm-sheets`, `04 §5.4`) or **17 s/min** (ASR, `06 §1.4`) or a new
  model. Both are available *the moment there is any evidence they will work* — `speech` fires and
  ASR runs; `onscreen_text` fires and OCR runs; a chapter list exists and it is free. What the
  default refuses to do is **invent names from pixels alone**, because `03 §8.3` measured that
  exact failure producing a confident wrong answer for content **that is not in the video at all**.
  A segmenter that hands a human nine correct cuts and no names is a two-minute job to finish. One
  that hands them nine plausible wrong names is a twenty-minute job to *audit*, and the human will
  not do it.

- **Sub-second boundary precision on visually-static content.** `03 §8.4` is explicit: nine dance
  blocks in one take against one wall are, to SigLIP2, the same image. `novelty-k` will find little
  there and **correctly report low confidence**, and the plan will escalate to periodicity + beat
  grid (which is what actually worked in the POC) and then to `ask`. I am accepting a weak default
  on that genre in exchange for a default that is honest about it. **The alternative — making pose
  periodicity the default — costs 10.9 s/min on every video including the 80% that have no person
  doing anything periodic.**

- **`ruptures`, one optional dependency.** BSD-2-Clause, 1.1.10, wheels on Apple Silicon
  **[verified: PyPI JSON; install verified in `05 §7.4`]**. Without it, `novelty-k` falls back to
  Foote peak-picking, which is worse when K is known and identical when it is not. **Make it an
  extra, not a requirement** — and note that this contradicts `05 §7.4`'s own tentative "skip it":
  that verdict was reached before K-from-a-human was on the table, and known-K change-point
  detection is the *entire* payoff of §7.3's first question.

### What I am explicitly NOT building in v1

`transnetv2-pytorch`, `finch-clust`, `scenedetect`, RepNet, RAFT, OWLv2/GroundingDINO, X-CLIP, any
Kinetics-pretrained video model, and every corpus-trained method in §2.15. Each is one `register()`
call away the day something needs it, which is the point of §9.6.

**The one I would revisit first is `finch-clust`** (TW-FINCH, MIT, 3 pure-Python deps,
**[verified: PyPI + LICENSE]**): it is transductive, parameter-free, needs no K, and returns a
*hierarchy* — which is sub-steps for free, and sub-steps are a tier-C requirement that nothing else
in v1 produces cold. Bench it against `novelty-k` on the POC video the day that video is available;
it is a two-hour experiment and it is the highest-information one in this document.

### The first experiment, before any of this is built

`03`'s open question 1, and it invalidates or confirms half of §10 for the price of one afternoon:

> **Run `novelty-k` on the actual POC dance video and see whether embedding novelty finds anything.**
> `03 §8.4` predicts it finds *nothing* and correctly reports low confidence; `03 §8.2`'s 5-of-5
> result came from a screen recording, which is the easy case. If the prediction holds, the
> escalation ladder (§8) is the product and `novelty-k` is just its first rung. If it fails
> *silently* — high confidence, wrong boundaries — then §9.5's honesty rules are not sufficient and
> the default must change.

Also cheap, also unrun: **swap `siglip2-base` for `dinov2-base`** in that same experiment (§2.7).
Both are already in the HF cache; it is a one-string change; and DINOv2 encodes appearance-and-pose
rather than nameable semantics, which is exactly the axis the dance case needs.

---

## 11. Ledger

### 11.1 Dependencies

**Everything in §10 runs on what is already in p12, except one optional package.**

| package | status | version | licence | needed for |
|---|---|---|---|---|
| `ruptures` | **NEW, optional** | 1.1.10 | BSD-2-Clause | §2.16 known-K change points |
| `finch-clust` | new, **not in v1** | 0.2.3 | **MIT** | TW-FINCH (§2.15) |
| `scenedetect` | new, **not in v1** | 0.7.1 | BSD-3-Clause | §2.1 |
| `transnetv2-pytorch` | new, **not in v1** | 1.0.5 | MIT | §2.1 |
| `webvtt-py` / `pysubs2` | new, **not needed** | 0.5.1 / 1.9.0 | MIT / MIT | §6.3 — `srt` covers it |

All five rows **[verified: PyPI JSON API this session]**; the MIT marks on `finch-clust` and
`transnetv2-pytorch` **[verified: raw `LICENSE.txt` / `LICENSE` from GitHub]** because neither
declares a licence in its PyPI metadata and both are research code where you should check.

**Already installed and used by §10 [verified: `dist-info` inspection of p12's site-packages]:**
`torch 2.9.0`, `torchaudio 2.9.0`, `transformers 4.57.1`, `librosa 0.11.0`, `numpy 2.2.6`,
`scipy 1.16.3`, `scikit-learn 1.7.2`, `mediapipe 0.10.35`, `rtmlib 0.0.15`, `onnxruntime 1.23.1`,
`dtaidistance 2.4.0`, `sentence_transformers 5.5.1`, `rapidfuzz 3.14.5`, `mlx_whisper 0.4.3`,
`faster_whisper 1.2.0`, `pytesseract 0.3.13`, `av 16.0.1`, `moviepy 2.2.1`, `Pillow 11.3.0`,
`anthropic 0.75.0`, **`srt 3.5.3`**, **`yt_dlp 2026.03.17`**, and the fleet: `lacing 0.0.34`,
`muvid 0.0.32`, `mixing 0.0.38`, `kodokan 0.0.18`, `scribed 0.0.3`.
System: **ffmpeg / ffprobe 8.1**, **tesseract 5.5.2** **[verified: `--version`]**.

**Two corrections to sibling files, both from the same filesystem check:**
- `03 §12` says `opencv 4.13`. It is **`opencv-python 4.12.0.88`** **[verified]**.
- `03 §12`'s dependency ledger omits **`srt 3.5.3`** and **`yt_dlp 2026.03.17`**, both installed,
  both load-bearing for tier E. `00 §6`'s env survey should gain them too.

### 11.2 Cost, one minute of 720p30, Apple M1 Max, offline

Every number **[from siblings]**, cited. The two `[verified]` rows are this session's ffprobe timing.

| what | s / min | new dep? | cite |
|---|---|---|---|
| `ffprobe -show_chapters` | **0.026 total, O(1)** [verified] | no | §6.1 |
| sub-bass ratio | **0.008** | no | `02 §6.1` |
| `beat-this` (+3 s load) | 0.14 | `beat_this` | `02 §2.2` |
| `ruptures.KernelCPD`, n=4800 | 0.19 total | **`ruptures`** | `05 §7.3` |
| ordered DP, 9 artifacts × 33 min | 0.13 total | no | `05 §3.2` |
| frame-diff energy ⊖ | 0.10 | no | `03 §2` |
| `librosa.beat.beat_track` | 0.7 | no | `02 §2.1` |
| ffmpeg `lavfi.scene_score` | 0.8 | no | `03 §13` |
| ffmpeg gray pipe, 6 Hz | 1.3 | no | `03 §2` |
| **the probe (all facts)** | **1.31–1.67** | no | `06 §2.2` |
| SigLIP2-base, 2 Hz, MPS ⊖ | 1.6 | no | `03 §8.1` |
| Laplacian structure segmentation | ~2 | no | `02 §5.1` |
| PySceneDetect `AdaptiveDetector` | 2.3 | `scenedetect` | `03 §13` |
| **SigLIP2-base, 6 Hz, MPS ⊖** | **4.4** | no | `03 §8.1` |
| Farneback flow, 512 px, 6 Hz | 7.5 | no | `03 §13` |
| **§2.18 tier-A stack, steps 0–4** | **~8.1** | no | this file |
| RAFT-small, 512 px, 6 Hz, MPS ⊖ | 9.8 | no | `03 §13` |
| rtmlib RTMPose `lightweight`, 6 Hz | 10.9 | no | `03 §13` |
| mediapipe Pose `full`, 6 Hz | 12.3 | no | `03 §13` |
| tesseract, cropped band ×3, 1 Hz | 14.4 | no | `03 §13` |
| `mlx-whisper` | 17 | no | `06 §1.4` |
| subsequence DTW, per query | 0.35 / query | no | `03 §13` |
| `llm-sheets` | **$1.16/h Opus, $0.08/h Haiku** | `anthropic` | `04 §5.4` |

**A 30-minute video, tier A, default plan, offline, $0: ~4 minutes of compute.** With ASR gated to a
50 % speech fraction: ~8.5 minutes. That is the number to quote to a user.

---

## Open questions

1. **Does `novelty-k` survive the genre it was not built for?** `03`'s open question 1, unchanged and
   still the most important one. Nothing in this file has been run on the POC dance video, and every
   accuracy claim behind §10's default comes from a screen recording with five visually distinct
   sections. **This is the one experiment to run before writing code.**
2. **Is `dinov2-base` better than `siglip2-base` for boundary novelty on visually-static content?**
   A one-string change, both cached, and it is the difference between §10's default working on
   physical-skill video and not.
3. **What is the null model?** Inherited from `03`'s open question 2 and not solved here. §9.5 makes
   it *expressible*; it does not make it *calibrated*. §2.8's OCR-as-ground-truth trick is the
   cheapest route to the data.
4. **Should `split`/`merge` really be correction verbs, or should K be a separate first-class input
   that a human sets and everything else re-derives?** §7.5(a) argues for verbs; the alternative is
   `Prior.k` with a provenance stamp and no verbs at all, which is simpler and might be enough.
   I do not know which is right and the answer changes the review UI.
5. **Is `anchor_t` sufficient as a correction key across a re-cut?** §7.5(b). `remap_time_after_cuts`
   migrates it, but a correction whose anchor lands inside a *deleted* span has no defined behaviour.
   Drop it, snap it to the cut, or flag it?
6. **Cover or gap, as the default?** §3. I recommend gaps-allowed; `03`'s open question 3 says the
   right answer is probably per-caller and the *default* matters. One DP state apart either way.
7. **Where does the macro/micro split live?** Tier D produces macro regions and then runs tier A
   inside each. Is that recursion in the segmenter, a two-level `Segmentation`, or two `segment()`
   calls the caller composes? The type in §9.1 supports all three via `Step.children` and I have not
   picked one.
8. **Does the heatmap (§6.4) actually correlate with step boundaries?** It is free and the reasoning
   is sound, but I have measured nothing. One afternoon with ten public tutorial videos that have
   both chapters and a heatmap would settle it — and those videos are *also* a free labelled
   evaluation set for everything else in this file, which may be the more valuable output.
9. **Should the segmenter own K-selection at all, or refuse it?** `novelty-k` with unknown K is
   peak-picking with a quantile threshold, which is the least principled thing in §10. The honest
   alternative is that a video-only segmenter with no K **always** returns `naming-abstained` plus a
   ranked candidate set and *requires* a human or a document to commit to a count. That is a smaller,
   more defensible product, and it might be the right v1.
10. **Is `mixing.chapters.detect_chapters` good enough to be the transcript namer, unchanged?**
    It already does LLM-over-transcript with duration constraints and accepts SRT
    **[verified: read the source]**. If yes, tier A's naming problem is ~20 lines of adapter and
    §10's "the default does not name" trade-off gets much weaker whenever there is speech.

---

## References

Papers cited in §2.15, with the claim each supports. All **[from docs]** — read from abstracts,
open-access PDFs and repository metadata this session, not reproduced.

1. Du Z, Wang X, Zhou G, Wang Q. *Fast and Unsupervised Action Boundary Detection for Action
   Segmentation.* CVPR 2022.
   [openaccess.thecvf.com](https://openaccess.thecvf.com/content/CVPR2022/papers/Du_Fast_and_Unsupervised_Action_Boundary_Detection_for_Action_Segmentation_CVPR_2022_paper.pdf)
2. Sarfraz S, Murray N, Sharma V, Diba A, Van Gool L, Stiefelhagen R. *Temporally-Weighted
   Hierarchical Clustering for Unsupervised Action Segmentation.* CVPR 2021.
   [arXiv:2103.11264](https://arxiv.org/pdf/2103.11264) ·
   code: [ssarfraz/FINCH-Clustering](https://github.com/ssarfraz/FINCH-Clustering) ·
   [finch-clust on PyPI](https://pypi.org/project/finch-clust/)
3. Xu M, Gould S. *Temporally Consistent Unbalanced Optimal Transport for Unsupervised Action
   Segmentation.* CVPR 2024. [arXiv:2404.01518](https://arxiv.org/pdf/2404.01518) ·
   code: [mingu6/action_seg_ot](https://github.com/mingu6/action_seg_ot)
4. *CLOT: Closed Loop Optimal Transport for Unsupervised Action Segmentation.* ICCV 2025.
   [arXiv:2507.03539](https://arxiv.org/html/2507.03539)
5. Dvornik N, Hadji I, Derpanis KG, Garg A, Jepson AD. *StepFormer: Self-Supervised Step Discovery
   and Localization in Instructional Videos.* CVPR 2023.
   [openaccess.thecvf.com](https://openaccess.thecvf.com/content/CVPR2023/papers/Dvornik_StepFormer_Self-Supervised_Step_Discovery_and_Localization_in_Instructional_Videos_CVPR_2023_paper.pdf)
6. Dvornik N, Hadji I, Derpanis KG, Garg A, Jepson AD. *Drop-DTW: Aligning Common Signal Between
   Sequences While Dropping Outliers.* NeurIPS 2021.
   code: [SamsungLabs/Drop-DTW](https://github.com/SamsungLabs/Drop-DTW)
7. Mavroudi E, Afouras T, Torresani L. *Learning to Ground Instructional Articles in Videos through
   Narrations.* [arXiv:2306.03802](https://arxiv.org/abs/2306.03802) · HT-Step benchmark,
   [NeurIPS 2023 D&B](https://proceedings.neurips.cc/paper_files/paper/2023/file/9d58d85bfc041b4f901c62ba37a3f322-Paper-Datasets_and_Benchmarks.pdf)
8. Souček T, Lokoč J. *TransNet V2: An Effective Deep Network Architecture for Fast Shot Transition
   Detection.* code + weights: [soCzech/TransNetV2](https://github.com/soCzech/TransNetV2) (MIT) ·
   [transnetv2-pytorch on PyPI](https://pypi.org/project/transnetv2-pytorch/)
9. Zhu W et al. *AutoShot: A Short Video Dataset and State-of-the-Art Shot Boundary Detection.*
   CVPRW 2023.
   [openaccess.thecvf.com](https://openaccess.thecvf.com/content/CVPR2023W/NAS/papers/Zhu_AutoShot_A_Short_Video_Dataset_and_State-of-the-Art_Shot_Boundary_Detection_CVPRW_2023_paper.pdf)
10. Dwibedi D, Aytar Y, Tompson J, Sermanet P, Zisserman A. *Counting Out Time: Class Agnostic Video
    Repetition Counting in the Wild (RepNet).* CVPR 2020. — cited via `03 §6.3`.
11. Truong C, Oudre L, Vayatis N. *Selective review of offline change point detection methods.*
    — the `ruptures` paper. [ruptures on PyPI](https://pypi.org/project/ruptures/) (BSD-2-Clause)
12. Foote J. *Automatic audio segmentation using a measure of audio novelty.* ICME 2000. — the
    checkerboard-kernel novelty operator used in §2.5, `03 §8.2` and `mixing.audio.segmentation`.
