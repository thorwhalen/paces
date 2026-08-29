# 02 — Technical recipes

*What this file is for: every technique the POC used, with the exact parameters that worked
and the dead ends that did not, so the next agent implements rather than rediscovers. All of
it ran locally on an Apple-Silicon Mac; nothing needed a hosted API. Reference
implementations are in `poc-reference/tools/` — read those files, they are short.*

Environment used throughout: `~/.pyenv/versions/3.12.12/envs/p12/bin/python`
(the `p12` env has librosa, mlx_whisper, ultralytics, onnxruntime, insightface, opencv,
playwright, yt-dlp). `ffmpeg` from Homebrew.

---

## 0. Quick answer: what was used for what

| job | what was actually used | §  |
|---|---|---|
| get the video | `yt-dlp` **with `--remote-components ejs:github`** | 1 |
| split talk / music / breakdown | 1-second RMS + **sub-bass energy ratio** — five lines of numpy | 2 |
| find the count grid | `librosa.beat.beat_track` + a duration sanity check | 3 |
| anchor the grid to a start time | a **visible periodic landmark** read off a contact sheet | 4 |
| speech → text, with times | `mlx_whisper`, `whisper-large-v3-turbo`, `language='fr'` | 5 |
| decide which seconds show a move | **an LLM looking at timestamped contact sheets** | 6 |
| locate the subject in frame | **YOLO11s person boxes** + a robust percentile envelope | 7 |
| stylize / anonymise | `cv2.stylization` + YOLO11n-seg + RetinaFace + AnimeGANv2 + blur | 8 |
| make gifs / mp4s | `ffmpeg` — two-pass palette for gif, libx264 for mp4 | 9 |
| build and verify the page | Playwright + headless Chromium | 10 |

**One correction worth making up front**, because it will otherwise send you looking for a
component that does not exist: there was **no gesture or pose detection**. Person *bounding
boxes* were used for cropping, and body segmentation *masks* for the anonymisation composite —
but nothing classified or recognised a movement. Step boundaries came from the beat grid plus
the input document; step *identity* came from what the teacher says in the breakdown and from
an LLM looking at frames. Pose estimation (mediapipe, rtmlib — both installed) was never used,
and is an obvious thing to try for cold segmentation.

---

## 1. Acquiring the video

```bash
yt-dlp --no-update --remote-components ejs:github \
  -f 'bv*[height<=720]+ba/b[height<=720]' --merge-output-format mp4 \
  -o 'source.%(ext)s' --write-info-json 'https://youtu.be/VIDEOID'
```

**`--remote-components ejs:github` is not optional.** Without it, current YouTube returns
`ERROR: This video is not available` after "Signature solving failed" — which looks like a
permissions problem and is not. It needs a JS runtime on PATH (`deno` or `node`).

`--write-info-json` is worth it: `availability` (`unlisted` here), `duration`, `fps`,
`uploader`, `description` all matter downstream — the "unlisted + copyright" combination
drove a real decision about how the output could be published.

The 720p stream was ample. Do not fetch 1080p+: the analysis downsamples anyway and the
crops come from a region a few hundred pixels wide.

## 2. Macro-structure from audio — the cheapest big win

Separates *talking head* / *silence* / *music* in one pass over 1-second frames. `bass` is
the discriminator; RMS alone will not do it.

```python
import numpy as np, wave

w = wave.open("audio16k.wav")
sr = w.getframerate()
data = (
    np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    / 32768.0
)
for i in range(len(data) // sr):
    x = data[i * sr : (i + 1) * sr]
    X = np.abs(np.fft.rfft(x * np.hanning(len(x)))) + 1e-10
    f = np.fft.rfftfreq(len(x), 1 / sr)
    rms = float(np.sqrt((x**2).mean()))
    bass = float(X[(f >= 30) & (f <= 140)].sum() / X.sum())  # ← the useful one
```

Observed on the POC:

| section | rms | bass |
|---|---|---|
| speech | 0.02–0.05 | **0.01–0.05** |
| silence | ~0.001 | (meaningless — denominator is noise) |
| music | 0.04–0.08 | **0.13–0.31** |

A threshold of `bass > 0.10` sustained for >10 s cleanly isolated the music span. Extract the
audio first with `ffmpeg -i src.mp4 -vn -ac 1 -ar 16000 audio16k.wav`.

## 3. Beat grid

```python
import librosa

y, sr = librosa.load("audio16k.wav", sr=22050, offset=MUSIC_START, duration=MUSIC_DUR)
tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time", trim=False)
```

Gave 129.2 bpm; one 8-count = `8 * 60/129.2` = 3.715 s. **Sanity-check the tempo against the
total**: 44 × 8 counts at 129 bpm = 163 s, and the music span was 170 s — consistent. At the
document's claimed 100 bpm it would have been 211 s, longer than the music. That arithmetic
check is what caught the document's error, and it is cheap to automate.

Beat trackers octave-error routinely. Do not trust the bpm alone; trust bpm *plus* a
phase anchor (next section) *plus* the total-duration check.

## 4. Phase origin from a visual landmark

Beat tracking gives you the *grid spacing*, not where step 1 begins. The POC solved the
offset by finding a visually distinctive, periodic event — the dancer throwing both arms
overhead once per 2×8 in the refrain, legible in a 2 s contact sheet at ≈196, 204, 212 s —
and working backwards:

```
t0 = first_landmark - (eights_before_landmark × eight_duration)
```

Then every block boundary is `t0 + cumulative_eights × eight_duration`, and each one is
verified against the sheet. Generalised: **find one anchor you can see, and let the grid do
the rest.** A cold search over offsets against a motion-energy signal would be the automated
version; untested.

## 5. Speech → text

```python
import mlx_whisper

r = mlx_whisper.transcribe(
    "audio16k.wav",
    path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
    language="fr",
    word_timestamps=False,
    verbose=False,
)
```

45 s for 651 s of audio on an M-series Mac; segments carry `start`/`end`. Set `language`
explicitly — autodetect on a bilingual instructional video (French speech, Spanish song
lyrics) is a coin flip.

**Whisper hallucinates over music.** Across the 170 s run-through it emitted hundreds of
near-empty segments and invented counting numbers. Gate ASR to the non-music spans found in
§2 rather than trying to clean it up afterwards.

The breakdown transcript is where step *names* and *cues* come from. Real examples that
became captions verbatim:

- `[402.1–407.7] "Ensuite vous revenez face / Et là c'est genou dedans / Un, tac, tac, tac"`
- `[369.7–377.7] "Donc là, c'est la roue, en fait, vers l'intérieur. C'est l'avant-bras qui mouline, voilà, vers soi."`
- `[415.0–422.7] "Et quand il commence à dire / C'est difficile de respirer / Vous pouvez avoir comme ça / Des mouvements qui marquent la chaleur"` ← a lyric cue

## 6. Looking at video with an LLM: contact sheets

The workhorse of the session. `poc-reference/tools/sheet.py`:

```bash
python tools/sheet.py START END STEP OUT.jpg [COLS]      # times in seconds
python tools/sheet.py 96 111 0.5 sheets/b4_rt.jpg 6
```

It shells `ffmpeg -ss S -to E -i src -vf fps=1/STEP,scale=400:-1`, tiles the frames with PIL,
and **stamps each tile with its absolute timestamp** — without the stamps the agent cannot
report a usable answer. Keep sheets under ~36 tiles.

Two step sizes, always in this order: a coarse pass (1–3 s) to find where movement happens,
then a fine pass (0.4–0.5 s) on the promising window.

`ffmpeg`'s `-ss S -i in -to E` behaves as an *absolute end timestamp* here (verified: 44→222
at 2 s gave 89 tiles). Do not assume; it has changed across versions.

`zsheet.py` / `sheet_crop.py` (written by subagents mid-session) do the same with a crop, to
judge a wide shot where the subject is small.

## 7. Locating the subject

**Do not use background subtraction.** The first attempt built an empty-room plate as an
88th-percentile-per-pixel composite over 240 sampled frames — a clean, correct-looking
plate — and the detection still failed, because exposure drift made a whole wall differ from
the plate and the largest connected component was that wall, not the person.

What works, `poc-reference/tools/mkclip.py`:

```python
from ultralytics import YOLO

m = YOLO("yolo11s.pt")  # ~19 MB, auto-fetched
r = m.predict(frames, classes=[0], conf=0.3, imgsz=768, verbose=False)
```

Sample the window at ~5 fps, take the largest person box per frame, then a **robust
envelope** — 4th percentile of the left/top edges, 96th of right/bottom — so one bad frame
cannot blow the crop open. Pad ~16 %, force the target aspect (4:5 for portrait cards), clamp
inside the frame, shrinking if needed.

A fixed crop per clip beats a tracking crop: pans are jittery at these durations, and the
percentile envelope already handles a subject who travels.

Full-video tracking at `imgsz=960` over 3255 frames was abandoned — far too slow on CPU
(>45 min). Detect only inside the windows you actually need.

## 8. Stylization / anonymisation

Lifted wholesale from the user's **kodokan** judo project — `~/Dropbox/py/proj/t/kodokan/examples/generate_stylized_clips.py`,
its issue #39 and `misc/docs/adr-video-face-privacy.md`. Adapted in
`poc-reference/tools/stylize.py` (streaming, so a 2:46 clip does not have to fit in RAM).

Three stages per frame:

```python
# 1. painterly — the per-frame bottleneck after AnimeGAN, so run it at half res
small = cv2.resize(frame, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
styl = cv2.resize(cv2.stylization(small, sigma_s=60, sigma_r=0.45), (w, h))

# 2. background → two flat colours, from the person mask
r = seg.predict(fr, classes=[0], device="mps")[0]  # yolo11n-seg.pt
mask = morphologyEx(union_of_instance_masks, MORPH_CLOSE, ones(7, 7))
pmf = GaussianBlur(mask.astype(float32), (0, 0), 2)[..., None]  # feather
comp = styl * pmf + flat * (1 - pmf)

# 3. face → AnimeGANv2 in a feathered ellipse, PLUS a blur on top
det = FaceAnalysis(name="buffalo_l", allowed_modules=["detection"])
det.prepare(ctx_id=0, det_size=(640, 640), det_thresh=0.35)  # low on purpose
# crop padded 60%, resized 512², x/127.5-1, NCHW RGB → face_paint_512_v2_0.onnx
```

Parameters that matter:

| knob | value | why |
|---|---|---|
| `sigma_s, sigma_r` | 60, 0.45 | kodokan's tuned values; half-res is invisible |
| `det_thresh` | 0.35 | deliberately low, to catch small/turned heads |
| `ANIME_EVERY` | 12 | AnimeGAN is ~0.6 s/face; the cache is a throughput device that also happens to stabilise flicker. **Lowering it gives *more* flicker, not less.** |
| `SEG_EVERY` | 2 | segmentation is cheap (~40 ms) |
| detection hold | 6 frames | bridges brief detection dropouts |
| `BLUR_ANIME_FACES` | **1** | kodokan's ADR: *"the cartoon face is a stylized version of the real face, so identity partially leaks."* They re-rendered 372 clips to add this. Do not ship without it. |

**The one deliberate departure from kodokan.** Their safety net blurs the top 28 % of the
person mask, full width, wherever no AnimeGAN face landed. Correct for overlapping judoka;
wrong here, because it smeared the raised arm in exactly the blocks about raised arms.
Narrowed to a horizontal window derived from the *shoulder* columns (rows 28–48 % of the mask
extent), which stay under the head even when the arms are up:

```python
sh   = mask[y0+int(ph*0.28) : y0+int(ph*0.48)]
cx   = int(np.median(np.where(sh)[1]))
halfw = max(int(W*0.09), int((cols[-1]-cols[0]) * 0.70))
band = top_28_percent_band * window(cx ± halfw)
```

Cost: **~28 s per 4-second 560×700 clip**, ~3.5–4 s of compute per second of video. The
2:46 run-through at 854×480 took 23 minutes.

Weights (all local, none auto-fetched for the first):
`~/kodokan_data/style_models/face_paint_512_v2_0.onnx` (8.6 MB — **the one weight with no
automated fetch; keep a copy**), `yolo11n-seg.pt` / `yolo11s.pt` (auto), `~/.insightface/models/buffalo_l/`
(auto, 288 MB, only `det_10g.onnx` used).

Licensing is **unresolved and unverified**. Kodokan's own docs do not settle it, and neither
did this session — InsightFace's model zoo is widely described as research/non-commercial, and
AnimeGANv2's weight provenance runs through a third-party port. Fine for a personal page;
**check both properly before this ships in anything commercial.**

Side effect worth designing around: flat backgrounds compress far better. The same 15 GIFs
went from **24.6 MB to 9.7 MB** purely from stylization.

## 9. Encoding

`poc-reference/tools/mkclip.py` handles gif / mp4 / webp behind one interface.

**mp4 (what the page uses)** — 560×700, 25 fps, ~150–320 KB for 4–6 s:

```
-c:v libx264 -profile:v main -pix_fmt yuv420p -crf 26 -movflags +faststart
```

In the page: `<video muted loop playsinline preload="none" poster=...>` driven by an
`IntersectionObserver` so only visible clips play. Behaves exactly like a GIF, ~20× lighter.

**gif** — two-pass palette, 300 px wide, 10 fps, 128 colours → 0.6–2 MB each:

```
-vf "fps=10,scale=300:-1:flags=lanczos,palettegen=max_colors=128:stats_mode=diff"
-lavfi "…[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle"
```

`libwebp` was **absent** from the Homebrew ffmpeg build — check before relying on webp.

`ffmpeg` has **no `drawtext` filter** in that build either; the contact-sheet timestamps are
burned in with PIL instead.

## 10. Rendering HTML with the browser as the renderer

Playwright + headless Chromium did three jobs, all worth keeping:

1. **Verification.** Screenshot the built page at desktop and mobile viewports, collect
   `pageerror` and any `response.status >= 400`, and assert on measured geometry rather than
   eyeballing:
   ```python
   pg.evaluate("""(() => {
     const clip = card.querySelector('.clip').getBoundingClientRect();
     const bar  = document.querySelector('.transport').getBoundingClientRect();
     return {covered: clip.top < bar.bottom};   # ← a real regression test
   })()""")
   ```
2. **Generating images from the page's own CSS.** The og:image and favicon are a 1200×630
   HTML page screenshotted at DSF 2. The typography and gradient match the site *exactly*,
   for free, forever. Far better than approximating in PIL.
3. **Generating the annotated infographic.** Screenshot one card element, read the real
   bounding boxes of every annotated child out of the DOM, then lay callout connectors onto
   those measured anchors. The arrows cannot drift out of sync with the UI.
   `poc-reference/render/howto.html` + `poc-reference/tools/shot.py`.

## 11. Link previews and page metadata

Non-obvious, cost two round trips:

- A blanket `<meta name="robots" content="noindex">` **kills chat-app link previews**.
  WhatsApp / Signal / iMessage scrape through `facebookexternalhit`, which declines noindex
  pages. Scope it: `<meta name="googlebot|bingbot|duckduckbot|slurp|yandex|applebot|ia_archiver" content="noindex, nofollow">`.
- WhatsApp and iMessage build previews **on the sending device**, with a simpler fetcher than
  a server crawler, and cache per exact pasted string *locally*. A small **JPEG** (60 KB beat
  a 182 KB PNG), plus `og:image:secure_url`, a square second `og:image`, `link rel="image_src"`
  and `itemprop` keys, is the belt-and-braces set. To test past the device cache, append a
  query string.
- Exactly one `<meta name="description">`. The generator emitted two; a lenient parser will
  pick either.

## 12. Deployment (thorwhalen.com)

Short version — full recipe in `06-surfaces-and-conventions.md`.

```
apps/<name>/app.toml                 # access = "public"; no [build] ⇒ no npm step
apps/<name>/frontend/index.html      # + frontend/media/, + frontend/icon.png
```

Auto-discovered via `platform.toml`'s `apps_dirs = ["apps", …]`; no registration needed.
Mounts at `thorwhalen.com/<dirname>/`. Deploy:

```bash
cd ~/Dropbox/py/proj/tt/tw_platform
python deploy.py cmd-deploy --app <name> --force > deploy.log 2>&1; echo $?
```

`--force` is mandatory without a TTY, `--delete` applies to `frontends/` but not `apps/`, and
**the apex route requires a Mac deploy** — CI cannot regenerate the edge config. Commit the
media: `deploy.py`'s conflated-data guard explicitly sanctions *tracked* media.

---

## Open questions for the next agent

- Is per-frame stylization the right cost? 3.5 s of compute per second of video is fine for
  15 short clips and painful for a library. A cheaper anonymisation tier (silhouette-only,
  or face-region-only with the room untouched) should probably be the default.
- The AnimeGANv2 weight has no automated fetch and a non-commercial license. Either vendor a
  replacement or make the stylizer a pluggable seam with a permissive default.
- Everything here assumes **one subject**. Two people (a partner dance, a two-handed craft
  demo) breaks the slot logic, the crop envelope, and the head-band safety net at once.
