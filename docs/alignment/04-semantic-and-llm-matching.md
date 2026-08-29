# 04 — Semantic matching and LLM-in-the-loop

*What this file is for: the family of methods that match an artifact to a span of media
through **meaning** rather than through a shared signal — "the step called *genou dedans*"
against a video of someone dropping a knee inward. It is the most capable family and the
most expensive, and — as measured below — the one most likely to return a confident wrong
answer. Reader: the agent who will design the alignment package. Sibling of
`00-existing-in-fleet.md`, whose `Method` Protocol and `Placement` dataclass this file
extends rather than replaces.*

**Verification legend.** **[verified]** = I ran it in `p12` this session and the number in
the table is the number my terminal printed. **[from docs]** = read from official
documentation or a model card I fetched; not executed. **[inferred]** = my judgement,
argue with it.

---

## 0. The one-paragraph verdict

I built a ground-truth alignment of the POC's own choreography run-through (§1) and ran the
whole semantic family against it. **Frame-wise vision-language matching (CLIP, SigLIP 2,
SigLIP 2 so400m) cannot tell these nine dance moves apart — it is statistically
indistinguishable from chance on full frames, and only weakly above chance once you crop to
the subject.** Scaling the model 3× and the resolution 3× changes nothing; the failure is
representational, not capacity. **Audio-language matching (CLAP) lost outright to the POC's
five-line sub-bass ratio — 170× slower and less accurate** on the exact discrimination the
POC needed. What *does* work is (a) the LLM-with-contact-sheets pattern, which is the
workhorse and is worth writing up properly (§5), (b) a **coarse-then-fine search**
decomposition, which the current literature independently confirms is the right shape at
hour scale (§6), and (c) an almost-free **lexical cue detector over the ASR transcript**,
which located instruction boundaries to within a second for the cost of a regex (§7). The
single most load-bearing design finding is in §8: **a VLM's raw cosine tells you whether an
artifact appears in this media at all, and its z-score tells you where — and the standard
normalisation that gives you the second destroys the first.** Those are two different
confidences, and a fusion layer needs both, computed differently.

---

## 1. The evaluation harness (so every claim below is checkable)

Everything in this file was measured against a real ground truth that I reconstructed from
the POC's own shipped artefacts. **[verified]** Reproduce it like this:

| Fact | How it was established |
|---|---|
| `filage.mp4` (166 s, 854×480, the stylized run-through) is `source[50.9 : 216.9]` | Multi-scale `cv2.matchTemplate` of each 560×700 block clip's first frame into every 1 fps frame of `filage.mp4`, over template widths 110–260 px. Candidate `T0`s from the two mutually-consistent matches; the winner scores ≥ 0.77 on **all six** run-through clips (mean 0.819) where the rivals drop to 0.66. |
| The routine is 44 eights at 129.2 bpm = 3.715 s/eight = 163.5 s | `ROUTINE` in the shipped page (`eights: 2,6,4,8,4,4,4,4,8`), and it matches the 166 s file to 1.5 %. |
| The nine block spans in `filage` time | `cumsum(eights) × 3.715`. Every one of the six independently-located clips falls inside its own block. That is six independent confirmations of one arithmetic model. |

```
block  1  0.0– 7.4   Mise en place
block  2  7.4–29.7   Pas pieds pointe et ronde        (clip b2  located @ 17.3 s)
block  3 29.7–44.6   Soleil avec les bras             (clip b3  located @ 30.0 s)
block  4 44.6–74.3   Déhanchés                        (b4a @ 52.4 s, b4b @ 67.5 s)
block  5 74.3–89.2   Moulinets de bras
block  6 89.2–104.0  Genou vers le bas
block  7 104.0–118.9 Pas pieds pointe, bras alternés  (clip b7  located @ 110.7 s)
block  8 118.9–133.7 Taper dans les mains du voisin
block  9 133.7–163.5 Avancer / reculer sur le refrain (clip b9  located @ 150.9 s)
```

Sources: `/Users/thorwhalen/Dropbox/py/proj/tt/tw_platform/apps/que_calor_dance/frontend/index.html`
(the `MEDIA` and `ROUTINE` objects) and `.../frontend/media/*.mp4`.

**Chance baseline.** With nine queries and an argmax over the timeline, the expected number
of queries whose peak lands in its own block is `Σ dur_i / 163.5 = 1.0`. So *one hit out of
nine is chance*, and `P(X ≥ 3 | Poisson(1)) = 0.08`. Any claim of "it got 3/9" is **not**
a claim of success. Keep this number in front of you for all of §2.

**Threat to validity, and why it does not bite.** `filage.mp4` is the *stylized* render
(cartoon shading, two-tone background, anonymised face), not the raw source, so results
could be depressed by domain shift. Tested: SigLIP 2 scores *"a photograph of a person"*
above *"a cartoon illustration of a person"* on **92 % of the 166 frames** (mean cosine
0.0945 vs 0.0838) **[verified]**. The encoder does not think it is looking at a cartoon.
The failures below are about pose and action semantics, not about the render.

**The scripts that produced every number in this file** are kept beside it in
`/Users/thorwhalen/Dropbox/py/proj/pocs/stepped/docs/alignment/04-evidence/`. They are
throwaway quality — absolute paths hard-coded, no argument parsing — but they run as-is
under `p12` and they are the evidence:

| Script | Produces |
|---|---|
| `locate.py`, `verify_t0.py` | the ground truth of this section |
| `eval_vlm.py`, `eval2.py`, `eval_crop.py`, `eval_so400m.py` | §2 accuracy tables |
| `domain.py` | §1 domain-shift control, §2.5 scene-type separations |
| `eval_clap.py` | §3.1 CLAP vs sub-bass |
| `sheet.py`, `sheets2.py`, `tokmath.py` | §5 contact sheets and the token math |
| `asr_cues.py` | §7.1 ASR + regex cue detection |
| `eval_calib.py` | §8.1 true-vs-decoy calibration |

`eval2.py`, `eval_crop.py`, `eval_calib.py` and `eval_so400m.py` `exec()` the preamble of
`eval_vlm.py` to share the ground truth and the query sets; run `eval_vlm.py` first, it
writes the score matrices the others reuse. `sheet.py` / `sheets2.py` need `ffmpeg` on PATH
and the media under `tw_platform/apps/que_calor_dance/frontend/media/`.

---

## 2. Vision-language embeddings — CLIP, SigLIP, and friends

### 2.1 The shape of the method

Encode every sampled frame once; encode each artifact's text once; take the cosine of every
(text, frame) pair. You now have a `(n_artifacts × n_frames)` similarity matrix on a shared
clock — which is exactly `muvid.footage.scoring.grid.ScoreTensor`'s data model, so it drops
into the fleet's existing fusion layer for free. Peak-pick, or hand the matrix to a solver.

### 2.2 Measured throughput on this Mac **[verified]**

166 frames of 400×225 JPEG, `torch` 2.9.0, `device="mps"`, batch 32, models from the local
HF cache.

| Model | Params | Native px | Device / dtype | Encode | Throughput | Emb dim | **s per minute of video @ 1 fps** |
|---|---|---|---|---|---|---|---|
| `openai/clip-vit-base-patch32` | 151 M | 224 | mps fp32 | 0.65 s | **254.6 fps** | 512 | **0.24 s** |
| `google/siglip2-base-patch16-224` | 375 M | 224 | mps fp32 | 1.62 s | **102.4 fps** | 768 | **0.59 s** |
| `google/siglip2-so400m-patch14-384` | 1136 M | 384 | mps fp16 | 48.9 s | **3.4 fps** | 1152 | **17.6 s** |

Model load (cold, from disk) is 2.6 s / 4.1 s / ~25 s respectively. Text encoding is
negligible (9 queries, < 0.1 s). At 1 fps sampling **the two base models are effectively
free** — a 90-minute video is under a minute of compute. `so400m` at 384 px is 30× slower
and, per §2.3, buys nothing.

### 2.3 Measured accuracy on the POC's actual problem **[verified]**

Task A: nine French block descriptions, argmax over 166 one-second frames. Task B: the six
person-cropped run-through clips (560×700), each scored against all nine texts, mean-pooled
over the clip's frames, top-1 retrieval. **Expected-at-chance: 1.0/9 and 0.67/6.**

| Model | Query lang | A: full frame | B: person-cropped | DP boundary error (median / max) |
|---|---|---|---|---|
| SigLIP 2 base/16-224 | **FR** | 2 / 9 | **3 / 6** (top-3 4/6) | 9.5 s / 31.8 s |
| SigLIP 2 base/16-224 | EN | 3 / 9 | 1 / 6 (top-3 4/6) | 9.8 s / 38.6 s |
| SigLIP 2 so400m/14-384 | FR | 2 / 9 | 2 / 6 | — |
| SigLIP 2 so400m/14-384 | EN | 3 / 9 | 2 / 6 | — |
| CLIP ViT-B/32 | **FR** | 1 / 9 | — | 25.5 s / 76.9 s |
| CLIP ViT-B/32 | EN | 2 / 9 | — | 42.6 s / 66.3 s |

Read this carefully, because the two columns say different things.

- **Column A is a null result.** 1–3 hits where chance is 1.0. `P(X ≥ 3 | Poisson(1)) = 0.08`.
  There is no evidence that full-frame VLM matching localises a dance move at all.
- **Column B is a real, weak signal.** `P(X ≥ 3 | Binomial(6, 1/9)) = 0.021`. Cropping to
  the subject moves it from nothing to something. This is the single highest-leverage knob
  in the entire family, and it costs one YOLO pass.
- **Scaling does not help.** so400m is 3× the parameters, 3× the pixels, 30× the cost, and
  no better on either task. Do not reach for a bigger encoder to fix this.
- **CLIP with French is degenerate.** All nine French queries peaked at the *same frame*
  (t = 1.5 s). CLIP's text tower is English-only; feeding it French produces nine nearly
  identical embeddings, and what you then measure is a frame-popularity prior, not a match.
  SigLIP 2, which is trained on multilingual WebLI, scores French **at or above** English
  here. **For a French corpus this is not a preference, it is a correctness constraint.**

### 2.4 Normalisation tricks do not rescue it **[verified]**

The obvious diagnosis of column A is a query-agnostic frame prior — several queries peak on
the same frames. The standard fixes were all tried on the SigLIP 2 base matrix:

| Post-processing | FR hits/9 | EN hits/9 |
|---|---|---|
| raw cosine | 2 | 3 |
| per-query z-score over time (row) | 2 | 3 |
| per-frame centring (column) | 2 | 2 |
| double-normalised (both) | 2 | 2 |
| double-norm + 5 s box smooth | 3 | 2 |
| double-norm + 11 s box smooth | 3 | 2 |
| softmax over queries per frame, τ = 0.01 | 3 | 1 |

Nothing escapes the chance band. **Do not ship a "we just need better normalisation" plan.**
(Column centring is still worth doing for a *different* reason — see §8.2.)

### 2.5 Where this family does work, measured

On the same frames, SigLIP 2 separates **scene type** cleanly and **person state** not at all
**[verified]**, mean cosine over all 166 frames:

```
0.1188  "a person dancing"
0.1156  "a person standing still talking to the camera"   <- +0.003 apart, on 100% dancing footage
0.0945  "a photograph of a person"
0.0935  "a wide shot of a person in a room"
0.0838  "a cartoon illustration of a person"
0.0626  "a close-up of a person's face"                   <- 2x below "dancing": real separation
0.0564  "a slide with text on it"                         <- 2x below: real separation
```

The rule this implies, and it is the rule to write into the catalog:

> **VLM frame scoring answers "what kind of shot is this?" It does not answer "what is the
> body doing?"** Use it for shot-type gating, slide/whiteboard/screen detection, close-up
> vs wide, indoor/outdoor, "is the product on screen", "is anyone in frame". Never for a
> move, a gesture, a technique, or anything whose identity is a body configuration.

Note the contrast with the POC's cheapest feature: the talk-vs-dance split that SigLIP 2
resolves at +0.003 is resolved by the **sub-bass energy ratio at a 10× separation, from
audio, at 1443× realtime** (§3.3). *Pick the modality that carries the distinction.* That is
the whole lesson.

### 2.6 The model shortlist, with licences **[verified via the HF Hub API]**

| Model | Params | Licence | FR? | In `p12` cache? | Verdict |
|---|---|---|---|---|---|
| `google/siglip2-base-patch16-224` | 375 M | **apache-2.0** | **yes** (multilingual WebLI) | **cached** | **The default.** Best FR-per-second on this box. |
| `google/siglip2-so400m-patch14-384` | 1136 M | apache-2.0 | yes | downloaded this session | Only if you have a task where §2.3 column B goes above 4/6. Not this one. |
| `openai/clip-vit-base-patch32` | 151 M | no licence field on the HF repo (upstream `openai/CLIP` is MIT) | **no — English only** | **cached** | Legacy. Keep only for English + comparability with older work. |
| `facebook/PE-Core-L14-336` | — | apache-2.0 | not claimed | no | Meta's Perception Encoder, strong on video/spatial benchmarks. Needs the `perception-encoder` library — a **new dependency outside `transformers`**. |
| `jinaai/jina-clip-v2` | 865 M | **cc-by-nc-4.0** | yes, 89 langs, FR named | no | Best-documented multilingual CLIP; matches/beats NLLB-CLIP-SigLIP by up to 4 % on cross-lingual retrieval **[from docs]**. **Non-commercial licence — do not put it behind a default.** |
| `LanguageBind/LanguageBind_Video_FT` | — | MIT | no | no | Video-native, see §4. |

### 2.7 When NOT to use vision-language embeddings

- The distinction is a body configuration, a hand shape, a technique, a phase of a motion.
- The artifact text is a *name* rather than a description ("le soleil", "block 4") — the
  encoder has never seen that lexicon; write a visual description or don't bother.
- You have fewer than ~5 artifacts and a strong order prior: the DP has nothing to chew on
  and a beat grid will beat it by two orders of magnitude (9.5 s median boundary error here
  versus ±0.1 s from `librosa.beat.beat_track` + a phase anchor).
- The subject is small in frame and you are not going to crop. Below ~15 % of frame height
  the person occupies about 15 of the tile's patches; there is no pose information left.

---

## 3. Audio-language embeddings — CLAP

### 3.1 The measurement **[verified]**

I built a signal with known boundaries — 40 s of the POC's music, 36.2 s of French speech,
6 s of digital silence, 40 s more music — and ran CLAP against the POC's own five-line
feature. Three text queries (`"music playing"`, `"a person speaking"`, `"silence"`),
argmax per window, 5 s windows at 1 s hop, 48 kHz mono. CPU (CLAP has no MPS path in
`transformers` 4.57.1).

| Method | Wall clock, 122 s of audio | Realtime factor | Frame accuracy | music recall | speech recall | silence recall |
|---|---|---|---|---|---|---|
| **Sub-bass ratio** (30–140 Hz / total, 1 s frames, numpy only) | **0.085 s** | **1443×** | **0.934** | 0.94 | 0.94 | 0.83 |
| `laion/clap-htsat-unfused` | 14.4 s | 8.5× | 0.856 | **1.00** | 0.64 | 0.33 |
| `laion/larger_clap_general` | 24.7 s | 4.9× | 0.703 | **1.00** | 0.08 | 0.67 |

**CLAP loses to five lines of numpy, by 170× in cost and 8 points in accuracy, on the one
audio discrimination the POC actually needed.** The bigger CLAP is worse than the smaller
one. And note the giveaway in the raw cosines: on speech windows *all three* queries score
**negative** (`music -0.058 / speech -0.052 / silence -0.169` for htsat-unfused) — CLAP is
out of distribution on continuous speech and the argmax is picking the least-bad of three
bad options. Its music recall of 1.00 is real; its speech detection is an artefact.

(Caveat: the speech here is macOS `say` TTS, not a human. TTS is unusually clean, which if
anything *favours* CLAP. **[verified]** that the ASR in §7.1 mis-transcribed it in ways human
speech would not, so treat the speech row as indicative, not exact.)

### 3.2 What CLAP is actually for

CLAP is an **open-vocabulary sound-event retriever**. It earns its keep exactly when you
have no classifier for the event and no cheap spectral proxy: *"where does the sizzling
start"*, *"find the doorbell"*, *"where does the crowd cheer"*, *"the first time the engine
revs"*, *"when does the rain start"*. For those, nothing cheaper exists and CLAP at ~7 s per
minute of audio is a bargain.

It is **not** a speech/music/silence discriminator, not a speaker-change detector, not a
music-structure analyser, and not a substitute for VAD. `mixing.audio.segmentation`'s
`speech_music` strategy (Scheirer–Slaney low-energy ratio + 4 Hz modulation) and the POC's
sub-bass ratio own that ground and win on every axis.

| Model | Licence **[verified]** | Notes |
|---|---|---|
| `laion/clap-htsat-unfused` | apache-2.0 | **cached in `p12`.** Faster and more accurate of the two here. The default if CLAP is wanted at all. |
| `laion/larger_clap_general` | apache-2.0 | **cached in `p12`.** Bigger, 2× slower, worse here. |
| `microsoft/msclap` (CLAP 2023) | **ms-pl** | Stronger on ESC-50/audio-captioning benchmarks **[from docs]**. `ms-pl` is a source-available reciprocal licence — **flag it in the catalog, it is not Apache**. Needs the `msclap` pip package (new dep). |

### 3.3 When NOT to use CLAP

Whenever a cheap spectral or temporal feature encodes the distinction. Speech vs music vs
silence, loudness, tempo, onsets, pitch, harmonicity, dropouts — every one of those has a
five-line numpy answer that is 100–1000× faster and more accurate. Reach for CLAP only when
the query is genuinely an open-vocabulary *semantic* sound event.

---

## 4. Video-native retrieval models, and whether they beat frame-wise CLIP

**Verdict: not for this package, not in v1. [inferred, from the evidence below]**

The video-native encoders — InternVideo2, LanguageBind, VideoPrism, VideoCLIP-XL — pool a
clip of frames into one embedding, so they can in principle represent *motion*, which is
exactly what §2 shows frame-wise CLIP cannot. InternVideo2 (50 M video-text + 50 M
video-audio-speech-text pairs) leads zero-shot text→video retrieval on the standard
benchmarks and is evaluated on temporal grounding (QVHighlights, Charades-STA)
**[from docs]**.

Four reasons to leave them out of v1:

1. **The benchmark that matters says frame-wise CLIP already wins at long horizons.**
   ExtremeWhenBench (2,273 open-form queries over 194 videos, mean 75.7 min) reports
   **CLIP frame retrieval at 0.269 mIoU against 0.003–0.115 for every end-to-end video
   model tested**, including Gemini-3.5-flash **[from docs]**. Video-native encoders help
   on 10-second clips; the problem in this package is a 10-minute timeline.
2. **The distribution mismatch is the same one that killed §2.** These models are trained on
   web video-caption pairs — *"a man is cooking pasta"*, not *"the forearm windmills from the
   elbow"*. Nothing in that training distribution teaches the fine-grained body-configuration
   vocabulary the POC needed.
3. **Dependency cost is real.** None is a plain `transformers` `AutoModel`. InternVideo2's
   Stage2 checkpoints are **apache-2.0 but gated** on the Hub **[verified]**; LanguageBind
   is MIT but ships its own model classes; `decord` (the usual video loader) is **not
   installed** and has poor Apple-Silicon support — `av` 16.0.1 and `cv2` 4.13.0 are
   installed and either can substitute, but you write that adapter.
4. **Cheap approximation available.** Mean-pooling frame embeddings over a window
   recovers a large fraction of clip-level retrieval performance. That is what §2.3 column B
   did (mean over a clip's frames), and it needs zero new dependencies.

**Seam, not implementation.** Make `frame_encoder=` and `pooling=` keyword arguments so a
video-native encoder can be dropped in later without touching the fusion layer. Do not ship
one.

---

## 5. The LLM-with-contact-sheets pattern, written up properly

This was the workhorse of the POC and it is the strongest method in this family. Here it is
as a reusable technique rather than a session anecdote.

### 5.1 The pattern

1. Decode frames at a chosen step with `ffmpeg`.
2. Tile them into a grid.
3. **Burn the absolute timestamp into every tile.**
4. Send the sheet to a vision LLM, images before text.
5. Ask for timestamps, in a schema, with a required justification per answer.
6. Coarse pass to find the region; fine pass inside it to find the boundary.

Reference implementation, verified to run this session
(`scratchpad/sheet.py`, `scratchpad/sheets2.py`) — this is essentially the POC's
`poc-reference/tools/sheet.py` with the geometry made explicit:

```python
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
        "2",
        f"{tmp}/t_%04d.jpg",
    ]
)
# ... then PIL: paste each tile, and stamp it
d.text((x + 6, y + 2), f"t={t0 + i * step:.1f}s", fill=(255, 205, 50), font=mono_20)
d.rectangle(
    [x, y + lab, x + w - 1, y + lab + h - 1], outline=(60, 60, 70)
)  # a border per tile
```

Three details that are not optional:

- **`ffmpeg`'s `-ss S -i in -to E` is an *absolute* end timestamp in this position**, not a
  duration. Re-verified this session (0→166 at 166/36 s gave exactly 36 tiles). It has
  differed across ffmpeg versions; assert the tile count rather than trusting it.
- **The Homebrew `ffmpeg` build in use has no `drawtext` filter** — burn timestamps with
  PIL. (Same build also lacks `libwebp`.) **[verified in the POC, still true.]**
- **A one-pixel border per tile.** Without it, adjacent tiles of a static camera on a flat
  background visually merge and the model miscounts which timestamp belongs to which image.

### 5.2 Why burned-in timestamps are not optional

The model has no clock. Every alternative — "the 14th image", ordinal labels in the text
block, a legend — makes the answer depend on the model counting a grid correctly, which is
exactly the thing vision models are documented to be bad at (*"Claude can give approximate
counts of objects in an image but might not always be precisely accurate"* **[from docs]**).
A burned-in `t=52.4s` makes the answer **self-evidencing**: the model quotes a string that
is visibly present in the pixels, and you can verify the citation by cropping that tile.
It converts a counting task into a reading task.

Stamp the **absolute** media time, never a within-sheet offset. Fine passes are cropped
windows; a relative label silently reintroduces the arithmetic you removed.

### 5.3 The tile budget — how many frames actually fit

Claude charges `⌈w/28⌉ × ⌈h/28⌉` visual tokens, one per 28×28 patch, after downscaling to
fit **both** a long-edge cap and a visual-token cap **[from docs]**. Two tiers: high-res
(Claude 4.7 and later — 2576 px / 4784 tokens) and standard (1568 px / 1568 tokens). I ran
the official reference implementation (its own `resized_size(1075,1520) == (924,1307)`
assertion passes) over realistic sheet geometries **[verified]**:

| Sheet | Tiles | Pixels | High-res tier | tok/tile | Standard tier | tok/tile |
|---|---|---|---|---|---|---|
| one 400×225 frame alone | 1 | 400×225 | 135 | 135 | 135 | 135 |
| one 854×480 frame alone | 1 | 854×480 | 558 | 558 | 558 | 558 |
| 6×2 @ 400 px | 12 | 2400×510 | 1634 | 136 | 672 | 56 |
| 6×4 @ 400 px | 24 | 2400×1020 | 3182 | 133 | 1344 | 56 |
| **6×6 @ 400 px** | **36** | **2400×1500** | **4644** | **129** | 1550 | 43 |
| 6×6 @ 560 px | 36 | 3360×2106 | 4698 | 130 | 1550 | 43 |
| 4×3 @ 560 px | 12 | 2240×1020 | 2960 | 247 | 1456 | 121 |
| 8×5 @ 300 px | 40 | 2400×940 | 2924 | 73 | 1232 | 31 |
| 6×8 @ 400 px | 48 | 2400×2000 | 4725 | 98 | 1548 | 32 |

Design constants that fall out of this, and they are worth hard-coding as defaults:

- **`2400 × 1500` is very close to the largest sheet a high-res-tier model does not
  downscale** (4644 ≤ 4784 tokens). The POC's 6×6 @ 400 px sheet landed there by feel. Keep
  it. Above ~2400×1540 you start paying for pixels the model never sees.
- **On the high-res tier, tiling is *free* in tokens** — 129 tok/tile in a 36-tile sheet vs
  135 tok for the same tile sent alone. The saving from tiling is **one request instead of
  36**, and the prompt amortised once. It is *not* a resolution saving.
- **On the standard tier, tiling costs detail**: the same sheet is downscaled to 1376×860,
  43 tok/tile, ~230×145 px per tile. If you must use a standard-tier model, drop to
  12 tiles.
- **The `>20 images per request` cliff.** More than 20 image blocks in one request triggers
  a stricter per-image dimension limit — resize everything to ≤2000 px per side or be
  rejected **[from docs]**. **A 2400 px sheet therefore caps you at 20 image blocks per
  request, sheets and any other images combined.** Assert it.

### 5.4 Cost, in dollars

Image tokens only, using the model prices in the `claude-api` skill's cached table
**[from docs]**, applied to the verified token counts above:

| Sheet | Sampling | Sheets per hour of video | Opus 5 ($5/M) | Sonnet 5 ($2/M) | Haiku 4.5 ($1/M, standard tier) |
|---|---|---|---|---|---|
| 36-tile @ 2 s | 0.5 fps | 50 | **$1.16** | $0.46 | $0.08 |
| 24-tile @ 2 s | 0.5 fps | 75 | $1.19 | $0.48 | $0.10 |
| 36-tile @ 0.5 s (fine) | 2 fps | 200 | $4.64 | $1.86 | $0.31 |

Per sheet: $0.0232 / $0.0093 / $0.0016. Add the prompt and the output; a structured answer
for 36 tiles is a few hundred output tokens, so on Opus 5 output adds roughly another
$0.005–0.01 per sheet **[inferred]**. **Rule of thumb: ~$1–2 per hour of video for a coarse
pass on a frontier model, ~5× that for a fine pass over a shortlisted region.** Batch API
halves it **[from docs]**; the coarse pass is the ideal batch workload because every sheet
is independent.

Two cost levers that matter more than model choice:

- **Prompt caching.** The system prompt + the artifact list + the schema are identical across
  every sheet in a run. Put them first, cache them, and put the volatile sheet last;
  cached input reads at ~0.1× **[from docs]**. Verify with
  `usage.cache_read_input_tokens` — if it is 0 across sheets, something volatile
  (a timestamp, an unsorted dict) is in the prefix.
- **Do not send the coarse pass to a frontier model.** Coarse localisation is a
  "which of these 36 pictures shows a person with both arms overhead" task. Haiku on the
  standard tier does it for **$0.08/hour**, 14× cheaper than Opus. Spend the frontier model
  on the fine pass only.

### 5.5 Coarse then fine, and what each pass can actually read

I generated the two sheets and read them myself, which is the honest way to characterise
this **[verified]**.

**Coarse: 36 tiles over the whole 166 s (4.6 s step), person-cropped, 1920×2556.** What is
legible: the standing intro (t=0–9 s); the travelling step with arms open (t=18–23 s); the
long legs-wide/hips section (t=27–101 s); **both arms thrown overhead at t=152.2 s**, which
is the POC's periodic visual landmark and falls correctly inside block 9 (133.7–163.5 s).
What is *not* legible: any distinction between "moulinets de bras", "bras alternés vers le
haut" and "taper dans les mains" — all three are sub-second arm events and a 4.6 s sampling
step simply never lands on them.

**Fine: 18 tiles at 0.5 s over a 9 s window, full frame, 2400×750.** The walk–pose–walk–
ramène cycle of the base step is readable frame by frame.

The rule:

> **A coarse pass finds *events* and *regions*. It cannot find a *move*. A move whose
> identity is carried by motion at sub-second scale needs a step at or below half the move's
> period, which means a fine pass over a window you already shortlisted.**

Step sizes that worked, in this order: **1–3 s coarse, then 0.4–0.5 s fine.** Keep sheets at
or under 36 tiles either way.

### 5.6 Cropping to the subject — and its own failure mode

§2.3 showed cropping is what moves VLM matching from noise to signal, and the same is true
for the LLM. In a full-frame 400×225 tile of this wide shot the dancer is roughly 75 px
tall — about **15 of the tile's 135 patches**. That is the entire evidence budget for a body
pose, and it is why both the encoder and the model struggle.

But I also generated a *per-frame* YOLO11s crop sheet and it exposed the failure mode
**[verified, visible in `scratchpad/B_crop_36.jpg`]**: on 8 of 36 tiles the detector's box
was small or the subject far, and the crop came out tiny with black padding — worse than the
uncropped tile. **Per-frame crops are unstable.** Use the POC's actual recipe instead:
sample the window at ~5 fps, take the largest person box per frame, then a **robust
percentile envelope** (4th percentile of left/top, 96th of right/bottom), pad ~16 %, force
the target aspect, clamp. **One fixed crop per window, never a per-frame crop.** That is
already written in `poc-reference/tools/mkclip.py` and it should be lifted verbatim.

### 5.7 What to ask for, and how to make the answer verifiable

Ask for structured output (`output_config.format` — *not* the deprecated `output_format`
**[from docs]**), and make every field either checkable or an admission of doubt:

```jsonc
{
  "matches": [{
    "artifact_id":  "block_6",
    "timestamp_s":  null,          // null == "not on this sheet". Required, not optional.
    "tile_label":   "t=93.5s",     // MUST be copied verbatim from the burned-in text
    "evidence":     "deep plié, both knees rolling inward, hands on thighs",
    "confidence":   "high|medium|low",
    "alternatives": [{"timestamp_s": 89.2, "why": "similar plié, knees less inward"}]
  }]
}
```

Five rules, each earning its place:

1. **`tile_label` must be copied from the pixels.** If the returned label is not a string
   your generator burned in, the answer is fabricated. This is a free, mechanical
   hallucination detector — reject the row, do not argue with it.
2. **`null` must be a legal answer, and the prompt must say so twice.** Otherwise every
   sheet produces nine confident answers, including the sheets containing none of them.
   This is the single largest source of error in the pattern.
3. **`evidence` is a free-text description of the *pixels*, not a restatement of the query.**
   A row whose evidence paraphrases the artifact text is a row where the model matched the
   words, not the image. Cheap to check with a string overlap.
4. **`alternatives` turns "wrong" into "second-ranked"**, which is what a fusion layer can
   actually use, and it makes the model's uncertainty legible instead of hidden.
5. **Images before text.** Documented to perform better **[from docs]**, and it puts the
   volatile content after the cacheable prefix, which is also what §5.4 wants.

### 5.8 Cross-checking several agents

Worth doing, cheap, and the design has one subtlety.

- **Same model, independent sheets.** Overlap consecutive sheets by 2–4 tiles. A boundary
  that both sheets report within one step is corroborated; a boundary only one sheet sees is
  a candidate. This is nearly free (you were sampling anyway) and it is the strongest of the
  three.
- **Same model, different framing.** Ask for the boundary once as *"where does block 6
  start"* and once as *"where does block 5 end"*. Agreement within a step is real evidence;
  disagreement localises a genuinely ambiguous transition, which is exactly what you want to
  surface to a human.
- **Different models.** Real but weaker than it looks: two frontier VLMs share training
  distributions and fail correlatedly. Use it to catch blunders, never to compute a
  probability.
- **Do not average timestamps.** Take the median, or keep all candidates as evidence rows
  and let the solver decide. Averaging two answers that straddle a real cut produces a
  boundary in the middle of nothing.

**Cross-checking's real job is disagreement detection, not accuracy improvement.** Budget it
as a gate that routes ~10 % of spans to a human, not as an accuracy multiplier.

---

## 6. Direct video-input LLMs vs contact sheets

### 6.1 What is available

| Path | Native video? | Sampling | Token rate | Notes |
|---|---|---|---|---|
| **Gemini 3 / 3.5** | **yes** | fixed 1 fps | **258 tok/frame default, 66 tok/frame at low `media_resolution`; ≈300 and ≈100 tok/s of video incl. 32 tok/s audio** | Up to 1 h at default res, 3 h at low res on 1 M-context models. Accepts and emits `MM:SS` timestamps in prompts. Files API to 20 GB paid / 2 GB free; 100 MB inline. **[from docs]** |
| **Claude** | no — images only | you choose | `⌈w/28⌉×⌈h/28⌉`, capped 4784 (high-res) | Contact sheets are the video path. 100 images/request at 200 k context, 600 otherwise; the >20-image dimension cliff applies. **[from docs]** |
| **Qwen3-VL 8B** (`mlx-community/Qwen3-VL-8B-Instruct-4bit`) | yes, frame sequences | you choose | local | **apache-2.0 [verified]**, runs on Apple Silicon via `mlx-vlm`. `mlx` is installed; `mlx_vlm` is **not** — one new dependency for a fully offline vision LLM. |

### 6.2 The comparison, in the units that matter

At the contact-sheet geometry of §5.3 (36 tiles @ 400 px, one frame per 2 s) Claude sees
**129 tokens per frame = 65 tokens per second of video**. Gemini's native path is 258
tok/frame at 1 fps (≈300 tok/s with audio), or 66 tok/frame at low resolution (≈100 tok/s).

Per hour of video, input tokens only:

| Path | Frames/s seen | Tokens/hour | Cost/hour **[inferred from published rates]** |
|---|---|---|---|
| Claude contact sheets, 0.5 fps, 36-tile | 0.5 | 232 k | ~$1.16 (Opus 5) / ~$0.08 (Haiku, std tier) |
| Gemini 3, low `media_resolution`, 1 fps | 1.0 | 360 k | ~$1.4 |
| Gemini 3, default, 1 fps | 1.0 | 1.08 M | ~$4.3 |

**They are the same order of magnitude.** So choose on properties, not price:

| | Contact sheets | Native video input |
|---|---|---|
| Sampling rate | **you choose, per pass** — 0.4 s fine, 5 s coarse | fixed at 1 fps |
| Cropping | **you crop** — the §5.6 lever, worth more than anything else here | whole frame |
| Audio | separate, and you control the ASR | included, transcribed by the provider |
| Timestamps | **burned into pixels — self-evidencing** | model-internal; you trust the offsets |
| Hallucination check | tile-label verbatim check (§5.7) | none available |
| Portability | any vision LLM, including local Qwen3-VL | one provider |
| Cache | prefix caching across sheets works naturally | whole-video prefix |

**Recommendation [inferred]: contact sheets are the default and native video is a seam.**
The two properties that decide it are variable sampling (a coarse pass at 5 s and a fine
pass at 0.4 s in the same pipeline — impossible at a fixed 1 fps without paying for the fine
rate everywhere) and the verbatim tile-label hallucination check, which has no equivalent on
the native path. Native video wins when the artifact needs *audio-visual* co-reference —
"the moment he says X while pointing at Y" — because it is transcribing and watching in one
pass.

### 6.3 The published evidence on which shape wins

ExtremeWhenBench (194 videos, mean 75.7 min, max 9 h) **[from docs]**:

| Approach | Charades-STA mIoU (short) | ExtremeWhenBench mIoU (hour-scale) |
|---|---|---|
| Qwen3.5-9B end-to-end | 0.579 | 0.110 |
| InternVL3.5 end-to-end | 0.359 | 0.003 |
| GPT-4o end-to-end | 0.299 | 0.013 |
| Gemini-3.5-flash end-to-end | 0.466 | 0.115 |
| **CLIP frame retrieval** | 0.332 | **0.269** |
| **Retrieve-then-ground hybrid** | — | **0.354** |

Three conclusions to carry into the design:

1. **End-to-end video models collapse at hour scale** (5–120× drops). Anything that says
   "just send the video to the model" is a short-video assumption.
2. **~85 % of errors are search failures, not localisation failures.** Spend the budget on
   finding the right *region*, not on refining a boundary you found in the wrong place.
3. **The retrieve-then-ground hybrid wins with 6 minutes of context.** This is exactly the
   POC's coarse-then-fine pass, and exactly the "gate ASR to the non-music spans" move.
   **Make cheap-gate-then-expensive-refine the package's default control flow, not an
   optimisation.**

---

## 7. Structured extraction from the transcript

The transcript is where an instructional video *says* what it is doing. Two methods, and
the cheap one is much better than it has any right to be.

### 7.1 The cheap classical one: lexical cue detection **[verified]**

I synthesised 36 s of French instruction, ran `mlx_whisper` `whisper-large-v3-turbo`
(`language='fr'`, `word_timestamps=True`) — **4.1 s, 8.8× realtime** — and ran a pure-regex
cue detector over the word-timed output. No spaCy, no LLM, no new dependency.

```python
ORDINAL = (
    r"(?:et\s+là|et\s+puis|ensuite|après\s+ça|après\s+quoi|puis|maintenant|d'abord|"
    r"pour\s+commencer|enfin|pour\s+finir|on\s+enchaîne|on\s+passe\s+à|"
    r"la\s+prochaine|voilà|d'accord|alors)"
)
IMPER = r"\b(?:vous\s+)?(\w{3,}(?:ez|issez))\b"  # French 2pl imperative / instructional present
CLOSERS = r"(?:voilà|d'accord|ok|c'est\s+tout|ça\s+y\s+est)"
```

Output against the script's real boundaries:

| Fired at | Cue | Ground truth |
|---|---|---|
| 1.0 s | ORDINAL `puis` | (intro) |
| 2.3 s | IMPERATIVE `vous mettez` | block start 2.0 s ✓ |
| 10.4 s | ORDINAL `Et là` | block start 10.4 s ✓ **exact** |
| 15.4 s | ORDINAL `on enchaîne` | block start 14.8 s ✓ (0.6 s late) |
| 21.0 s | CLOSER `Voilà` | end of block ✓ |
| 22.0 s | ORDINAL `Maintenant` | block start 22.0 s ✓ **exact** |
| 24.1 / 26.2 / 27.9 s | IMPERATIVE `Vous avancez` / `vous lèvez` / `vous redescendez` | the three sub-steps of the refrain ✓ |
| 29.5 s | CLOSER `D'accord` | end of block ✓ |

**One miss, and it is the instructive one.** The script said *"Ensuite vous faites le pas de
base"* at 5.0 s; Whisper wrote **"En suite"** as two words, and the regex `ensuite` did not
match. **ASR orthography breaks literal lexical matching.** The fix is not a longer regex:
normalise before matching (lowercase, strip accents, collapse whitespace **including inside
candidate cue phrases**) and match with `rapidfuzz.partial_ratio ≥ 88` — `rapidfuzz` 3.14.5
is **already installed**. Same class of bug will hit *"et là"* → *"était"*, *"après ça"* →
*"après sa"*.

Why this method is worth its place at the top of the catalog:

- **Cost is nil** on top of an ASR pass you were doing anyway.
- **Sub-second precision**, from word timestamps — two orders of magnitude better than the
  9.5 s median the VLM DP managed in §2.3.
- **It is an evidence source, not an aligner.** It produces *candidate boundaries*, which is
  exactly the input `muvid.footage.select_score._viterbi` wants (`boundaries = beats ∪
  shot-cuts ∪ cue-times`). Cue times slot into that set with no new machinery.
- **It composes with the order prior**: k artifacts, m candidate boundaries, monotone
  assignment. That is the solver the package already needs.

Upgrade path, if the regex proves brittle: `spaCy` `fr_core_news_sm` (~16 MB) exposes
`Mood=Imp` in `token.morph` **[from docs]** — a real morphological imperative test rather
than a suffix heuristic. `spaCy` is **not installed**; one new dependency, behind a
`[text]` extra. Note the French subtlety it *also* solves: instructional French mostly uses
the **present indicative 2pl** ("vous revenez face"), not the morphological imperative, so
a naive `Mood=Imp` filter would find *less* than the regex above. Test before adopting.

### 7.2 The LLM one: structured extraction over the transcript

For step *names*, paraphrase-tolerant matching, and cue phrases you did not anticipate. This
is already prior art in the fleet — `mixing.chapters.detect_chapters` is "LLM segments a
transcript into spans under duration constraints", complete with `_enforce_constraints`. Do
not write a second one; generalise that.

Shape:

```python
client.messages.create(
    model="claude-opus-5",
    max_tokens=16000,
    output_config={"format": {...}},  # not the deprecated output_format
    cache_control={"type": "ephemeral"},  # transcript is the stable prefix
    system=[{"type": "text", "text": ARTIFACT_LIST_AND_SCHEMA}],
    messages=[{"role": "user", "content": TIMESTAMPED_TRANSCRIPT}],
)
```

Rules, mostly the same as §5.7 for the same reasons:

- **Feed timestamps per segment, and require the answer to quote the source line verbatim.**
  Same self-evidencing trick as the burned-in tile label; same free hallucination check.
- **Never let the model invent a timestamp.** Make the answer field a *segment index*, and
  resolve it to a time yourself. An LLM asked for "the time" will interpolate; an LLM asked
  "which line" cannot.
- **`null` is a legal answer.** Non-negotiable.
- **Gate the ASR first.** The POC's hard-won lesson: Whisper hallucinates hundreds of
  near-empty segments and invented counting numbers over music. Run ASR only on the
  non-music spans found by the sub-bass ratio. Extraction quality is bounded by transcript
  quality, and this is the cheapest possible fix.
- **Cost is trivial** relative to §5: a 10-minute transcript is ~3–5 k tokens, so about
  $0.02–0.05 on Opus 5 for a whole video **[inferred]** — 20–50× cheaper than the vision
  path. **Always try the transcript before the pixels.**

---

## 8. Confidence and calibration

This is the section a fusion layer actually depends on, and it contains the one genuinely
surprising measured result in this file.

### 8.1 Two different confidences, and the standard trick destroys one of them **[verified]**

I scored the nine true French block descriptions and **twelve decoy descriptions of things
that are definitely not in this video** (frying onions, a dog on a beach, a chess game, a
bar chart, a sleeping cat…) against the same 166 frames with SigLIP 2 base.

| Statistic | TRUE queries (n=9) | DECOY queries (n=12) | Separation |
|---|---|---|---|
| peak cosine | 0.095 – 0.152 (μ 0.133) | −0.012 – 0.087 (μ 0.049) | **AUC = 1.00** |
| peak **z-score over time** | 2.12 – 3.10 (μ 2.70) | 1.88 – **5.02** (μ 3.03) | **AUC = 0.35** |
| peak after subtracting the decoy-pool per-frame mean | 0.036 – 0.094 | −0.072 – 0.029 | **AUC = 1.00** |

Read that middle row again. **Per-query z-scoring over the timeline — the standard,
obvious, universally-recommended normalisation, and the one that makes peak-picking work at
all — separates true from decoy queries *worse than a coin flip*.** A decoy reached z = 5.02,
higher than every true query. This is not subtle and it is not a fluke: z-scoring divides
out the per-query mean, and the per-query mean *is* the relevance signal.

So:

> **Relevance** ("does this artifact appear in this media at all?") lives in the **raw
> cosine level**, and is measured against a **decoy pool**.
> **Localisation** ("where?") lives in the **shape of the curve over time**, and is measured
> by z-score or peak prominence.
> They are computed differently, they are not interchangeable, and **a method that returns
> one number is returning whichever of the two it happened to compute.**

### 8.2 The recipe

For every scoring method, return both:

1. **`relevance`** — one scalar per artifact. Score `k` decoys (12 was plenty here;
   auto-generate them by shuffling the *other* artifacts' texts, or keep a fixed
   domain-irrelevant pool) and report the true query's peak as a percentile or a z against
   the decoy peaks. Threshold this for `span=None` (abstention).
2. **`localisation`** — one curve per artifact, plus a peak prominence. z-score over time,
   or better, the **margin between the best peak and the second-best non-adjacent peak**,
   which is what actually predicts whether peak-picking is stable.

Both go in `Placement.evidence`, never collapsed into `Placement.confidence` until the
fusion layer decides how to weigh them.

### 8.3 Confidence numbers are not comparable across methods

Observed cosine ranges this session **[verified]**:

| Method | Range of "a match" | Range of "no match" |
|---|---|---|
| SigLIP 2 base, image-text | 0.095 – 0.152 | −0.012 – 0.087 |
| CLIP ViT-B/32, image-text | 0.227 – 0.313 | (never established — CLIP+FR is degenerate) |
| CLAP htsat-unfused, audio-text | 0.369 (music, correct) | −0.169 to 0.151 |
| Cropped-clip top-1 margin, SigLIP 2 | **+0.0000 to +0.0229** | — |

Three things follow. **(a)** A global threshold like `confidence > 0.3` is meaningless — it
passes everything from CLIP and nothing from SigLIP 2. **(b)** The top-1 margin in the
cropped-clip task went as low as `+0.0000` on a *correct* answer: the winner and runner-up
were numerically tied. Margins at this scale are not decision-grade without the decoy
calibration of §8.2. **(c)** The fleet has already learned this once — `mixing`'s
`align_clips_to_reference` documents that the envelope feature scores correct alignments at
0.441–0.634 while the waveform feature scores the *same* correct alignments at 0.064–0.148.
**An alignment engine that reports a confidence without saying what regime it was
calibrated in is reporting noise.** Put the regime in the catalog, as a field.

### 8.4 Getting a confidence out of an LLM

- **Do not ask for a number.** A `0.0–1.0` self-reported confidence is uncalibrated and
  clusters at 0.8–0.95. Use a **three-level ordinal** (`high|medium|low`) — coarse enough
  that the model can be consistent — and calibrate the levels empirically against a labelled
  set before trusting them.
- **The verbatim `tile_label` check is a *hard* signal** and worth more than any soft one:
  label not in the burned-in set ⇒ confidence 0, discard the row. Free.
- **`alternatives` non-empty is itself a confidence signal** — a row with a plausible
  alternative is a row to route to cross-checking.
- **Self-consistency**: same sheet, same prompt, `n` samples. Agreement rate is a decent
  empirical confidence but costs `n×`. Reserve it for spans where the cheap signals already
  disagree.
- **Overlap agreement across consecutive sheets (§5.8) is the cheapest LLM confidence there
  is** because you were sampling the overlap anyway. Make it the default.

---

## 9. Facade shape

`00-existing-in-fleet.md` proposes a `Method` Protocol whose `__call__` returns
`list[Placement]`. **Every method in this file violates that shape**, and the violation is
informative rather than accidental: none of them produces a span. They produce a *score over
time*, and committing that to a span is the solver's job, not the method's.

So the minimal addition — one narrower Protocol, subsumed by the existing one:

```python
Span = tuple[float, float]


@dataclass(frozen=True, slots=True, kw_only=True)
class Grid:
    """The shared media clock. One per alignment run; every Scorer resamples onto it."""

    t0: float
    hop_s: float
    n: int


@dataclass(frozen=True, slots=True, kw_only=True)
class Evidence:
    """One artifact's score over the grid, with the TWO confidences of section 8 kept apart.

    `curve` answers "where"; `relevance` answers "at all". Never collapse them here --
    the fusion layer decides the weighting, and it needs both to do so.
    """

    artifact_id: str
    curve: "np.ndarray"  # (grid.n,) float32, NaN where the method abstains
    mask: "np.ndarray"  # (grid.n,) bool -- coverage. NaN is never 0.
    relevance: float | None = None  # decoy-calibrated; None = not calibrated
    regime: str = ""  # what the numbers mean: 'cosine/siglip2-base' ...
    detail: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class Scorer(Protocol):
    """A Method whose `produces` is 'evidence'. Every method in doc 04 is one of these."""

    name: str
    consumes: tuple[str, ...]  # 'video' | 'audio' | 'text' | 'transcript'
    produces: str = "evidence"
    requires: tuple[str, ...] = ()
    licence: str = "apache-2.0"
    cost: str = "cheap"  # 'cheap' | 'gpu' | 'network' | 'billable'
    resolution_s: float = 1.0  # the finest boundary this method can justify
    granularity: str = "scene"  # 'scene' | 'event' | 'pose'  -- see below

    def score(self, artifacts, media, *, grid: Grid, **kw) -> list[Evidence]: ...
```

Four fields beyond `00`'s Protocol, each paid for by a measurement in this file:

| Field | Why it exists |
|---|---|
| `Evidence.relevance` separate from `curve` | §8.1. One number cannot carry both, and the normalisation that produces one destroys the other. |
| `Evidence.regime` | §8.3. `0.13` from SigLIP 2 and `0.13` from CLAP are not the same fact. `mixing` learned this the hard way already. |
| `resolution_s` | §5.5. A 4.6 s coarse sheet cannot justify a 0.4 s boundary. The solver must refuse to emit a boundary finer than its evidence. |
| `granularity` | §2.5. `'scene'` methods (shot type, slide, close-up) work. `'pose'` methods do not, measurably. The `"auto"` agent needs to know that a `'pose'` request has no good answer in this family, and say so rather than returning noise. |

The three concrete registrations this file recommends:

```python
"clip-frames"     Scorer  consumes=('video','text')       requires=('torch','transformers')
                          licence='apache-2.0'  cost='cheap'   granularity='scene'
                          resolution_s=<sampling step>
                          # default model google/siglip2-base-patch16-224 -- multilingual,
                          # 0.59 s per minute of video at 1 fps on mps. NOT openai/clip: its
                          # text tower is English-only and French collapses (section 2.3).
                          # kwargs: crop='subject'|'none' (default 'subject' -- section 5.6),
                          #         decoys=<int|Sequence[str]> for the relevance calibration.

"clap-windows"    Scorer  consumes=('audio','text')       requires=('torch','transformers')
                          licence='apache-2.0'  cost='cheap'   granularity='event'
                          # laion/clap-htsat-unfused, ~7 s per minute of audio, CPU.
                          # catalog note: "open-vocabulary sound EVENTS only. For
                          # speech/music/silence use mixing.audio.segmentation -- 170x faster
                          # and more accurate (section 3.1)."

"llm-sheets"      Scorer  consumes=('video','text')       requires=('anthropic','PIL')
                          licence='commercial-api'  cost='billable'  granularity='event'
                          # coarse pass 1-3 s, fine pass 0.4-0.5 s, <=36 tiles, 2400x1500,
                          # burned-in absolute timestamps, verbatim tile_label check.
                          # ~$1.16/hour coarse on Opus 5, ~$0.08/hour on Haiku (section 5.4).

"transcript-cues" Scorer  consumes=('transcript',)        requires=()         # rapidfuzz optional
                          licence='MIT'  cost='cheap'  granularity='event'  resolution_s=0.1
                          # produces candidate BOUNDARIES, not spans. Feed them into the
                          # solver's boundary set alongside beats and shot cuts (section 7.1).
```

And one function the package should own, because three of the four registrations above want
it and it is 40 lines:

```python
def contact_sheet(
    media,
    spans,
    *,
    step_s,
    cols=6,
    tile_w=400,
    crop=None,
    max_tiles=36,
) -> tuple[Path, list[float]]:
    """Tile frames into a timestamped sheet; return the path and the tile times.

    Defaults are the measured optimum for a high-resolution-tier vision model:
    36 tiles at 400 px is 2400x1500 = 4644 visual tokens, just inside the 4784 cap,
    so nothing is downscaled. Raising max_tiles or tile_w buys pixels the model
    never sees. Asserts the tile count against ceil((t1-t0)/step_s) because
    ffmpeg's -ss/-to semantics have moved across versions.
    """
```

**Where these live.** Per `00`'s recommendation the package's hard deps are `lacing` and
`numpy` only. So: `clip-frames`, `clap-windows` and `llm-sheets` are lazily registered
(`slug -> "module:func"`) behind `[vlm]`, `[clap]` and `[llm]` extras; `transcript-cues` has
no dependency beyond the stdlib and can be eager. `contact_sheet` needs `PIL` + an `ffmpeg`
binary — behind `[llm]`.

---

## 10. Environment: what is already here

Checked by import in `/Users/thorwhalen/.pyenv/versions/3.12.12/envs/p12/bin/python`
**[verified]**.

**Present and sufficient.** `torch` 2.9.0 (mps working) · `transformers` 4.57.1 (has
`SiglipModel`, `ClapModel`, `ClapProcessor`) · `sentence-transformers` 5.5.1 ·
`accelerate` 1.10.1 · `safetensors` 0.6.2 · `huggingface_hub` 0.35.3 · `PIL` 11.3.0 ·
`cv2` 4.13.0 · `av` 16.0.1 · `numpy` 2.2.6 · `faiss` 1.13.2 · `sklearn` 1.7.2 ·
`ultralytics` 8.4.75 (YOLO11 for the subject crop) · `rapidfuzz` 3.14.5 (for §7.1's
normalisation fix) · `mlx_whisper` / `faster_whisper` / `openai-whisper` · `anthropic`
0.75.0 · `openai` 2.11.0 · `mlx`.

**Already in the local HF cache — zero download.** `google/siglip2-base-patch16-224` ·
`openai/clip-vit-base-patch32` · `laion/clap-htsat-unfused` · `laion/larger_clap_general` ·
`facebook/dinov2-base` · `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` ·
`mlx-community/whisper-large-v3-turbo`. Downloaded this session:
`google/siglip2-so400m-patch14-384`.

**Absent, and what it would cost.**

| Missing | Needed for | New-dep verdict |
|---|---|---|
| `open_clip_torch` | OpenCLIP checkpoints | Not needed — `transformers` covers SigLIP 2 and CLIP. |
| `spacy` + `fr_core_news_sm` | morphological imperative detection (§7.1) | ~16 MB model + spaCy. Optional, behind `[text]`. Test that it beats the regex first — it may not. |
| `msclap` | MS-CLAP 2023 | Only if `laion` CLAP proves insufficient. **`ms-pl` licence — flag it.** |
| `mlx_vlm` | local Qwen3-VL as an offline `llm-sheets` backend | The interesting one. Would make the LLM path fully offline and free. `mlx` is already installed. |
| `decord` | video-native encoders | Avoid — poor Apple-Silicon support. `av` or `cv2` substitute. |
| `perception-encoder` | Meta PE-Core | Only if PE measurably beats SigLIP 2 on *your* task. It did not get a chance here. |

**Two hazards observed [verified].** `av` and `cv2` ship duplicate `libavdevice` dylibs and
objc warns *"may cause spurious casting failures and mysterious crashes"* on every import of
both — pin the video decode path to one library. And `transformers` warns
`use_fast is unset` for the SigLIP/CLIP processors; pass `use_fast=True` explicitly, it is
measurably faster and will be the default anyway.

---

## 11. Open questions

1. **Is the pose branch the actual answer to §2's null result?** The measured failure is
   "VLMs cannot represent body configuration". `kodokan` already has RTMPose/YOLO11-pose
   behind `estimate_poses(backend=…, device="mps")`, joint-angle features, and DTW via
   `dtaidistance` — all installed, all dormant, and never pointed at a media clock. A
   17-keypoint joint-angle sequence *is* the representation SigLIP 2 lacks. **This file's
   negative result is the strongest argument in the whole design for prioritising the pose
   branch.** But it is a *different family* (signal matching, not semantic), so the artifact
   text still has to be turned into a pose exemplar somehow. Do we require one labelled
   example per artifact — i.e. one-shot from the breakdown clip — and is that acceptable
   product-wise?
2. **Where does the decoy pool come from?** §8.2 needs decoys per run for the relevance
   calibration. Auto-generating them by permuting the other artifacts' texts is free but
   they may not be true negatives (block 4 and block 7 share vocabulary). A fixed
   domain-irrelevant pool is cleaner but has to be curated per domain. Which, and does it
   live in the package or in the caller?
3. **Should `llm-sheets` default to a cheap model?** §5.4 says the coarse pass runs 14×
   cheaper on Haiku at the standard tier and the coarse pass is a "which picture shows X"
   task. But standard-tier tiling costs real detail (43 vs 129 tok/tile), and §5.5 already
   shows the coarse pass is at the edge of what is legible. Needs one measurement on a
   labelled set before it becomes a default.
4. **Does the `>20 images per request` cliff force a design?** At 2400 px sheets you can send
   at most 20 image blocks per request. A 90-minute video at 36-tile/2 s is 75 sheets ⇒ at
   least 4 requests, so the sheets cannot share one conversation. Does the coarse pass become
   one-request-per-sheet plus a fusion step (batchable, cacheable, parallel), or
   20-sheets-per-request with a shared prefix? The first is almost certainly right, and it
   also makes the Batch API's 50 % discount available — confirm before building.
5. **Do we own the transcript, or does `scribed`?** §7 assumes word timestamps. `scribed`
   is the right seam and is young (9 commits); `an.audio.WordTimingProvider` already exists
   as a narrow Protocol carved out *specifically* so an external aligner could feed it.
   Committing to `scribed` means hardening it. This is the same fork as `00`'s open
   question 2 and it should be answered once.
6. **Is `granularity` three values or a lattice?** I proposed `scene | event | pose`. It is
   the field that lets the `"auto"` agent say *"nothing in the catalog can do what you are
   asking"* instead of returning chance-level noise, which after §2 is the most valuable
   thing the agent can say. But three buckets may be too coarse — where does "which of two
   people is speaking" sit?
7. **Should the null result be a test?** The ground truth in §1 is reconstructable in about
   200 lines and it is a *real* alignment task with *real* French artifacts. Making it a
   fixture — "the semantic family must not claim to solve this" — would prevent the package
   from ever silently regressing into confident nonsense. It would also mean shipping a
   dependency on a private video. Store the 166 frame embeddings (166 × 768 floats = 500 KB)
   and the ground-truth spans instead?
8. **Does the two-confidences split (§8.1) belong in `lacing`?** `lacing.quality` already
   owns `boundary_iou`, `interval_iou`, `cohen_kappa`, `krippendorff_alpha` — the metrics
   for judging an alignment. Decoy-calibrated relevance is arguably the same kind of thing
   and would be reusable by every aligner. Or is it engine-internal and lacing stays free of
   it, as it stayed free of ASR?
