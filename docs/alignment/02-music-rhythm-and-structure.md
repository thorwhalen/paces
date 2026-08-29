# 02 — Rhythm and musical structure as a grid

**Question this file answers:** when the media is paced by music, what can the *music* tell
us about where an artifact goes? The POC got its entire segmentation grid from one number
(129.2 bpm) and one visual anchor. This file is the survey of everything that could have
produced those two numbers automatically, measured rather than assumed.

**Verification legend.** **[verified]** = I ran it in this session on this Mac and the number
in the text is the number I got. **[from docs]** = read from a README, docstring or paper, not
executed. **[inferred]** = my judgement; argue with it.

**Test material** (all local, all on an M-series Mac, all offline after first model fetch):

| handle | what | why |
|---|---|---|
| `click129.wav` | synthesised 4/4 drum loop, **exactly 129.200 bpm**, downbeat at t=0, 59.4 s | ground truth for tempo and phase |
| `Down_where_I_live.wav` | real song, 155 s, ~124.4 bpm | realistic 4/4 |
| `I_won,_you_lost.wav` | real song, 155 s, ~85.8 bpm | slower, cleaner meter |
| `long20.wav` | the first track ×8 = 20.7 min | scaling / memory |
| 3 human-speech recordings (en close-mic, podcast, fr) | 234 s of speech frames | the speech/music discriminator |

---

## 0. Headline findings — the six things that should change the design

1. **`beat-this` is the answer to the fleet's downbeat gap, and it is MIT — code *and* weights.**
   `mixing.audio.beats.BeatGrid.downbeat_times` is a reserved empty array precisely because
   madmom's models are CC-BY-NC-SA. `beat-this` has no such problem, needs no madmom, needs no
   new heavy dependency beyond `torch` (already present), and runs a 20-minute file in **2.9 s
   on MPS (424× realtime)** with identical output to CPU. **[verified]** This is the single
   highest-value item in this document. See §2.2.

2. **Never read tempo off a median inter-beat interval.** Neural trackers quantise their output
   to a 20 ms frame grid; the median IBI of `beat-this` on the 129.200 bpm loop is 0.4600 s →
   **130.43 bpm (1.0 % error)**. A least-squares line through the beat times gives
   **129.201 bpm (0.001 % error)** from the same data. **[verified]** §3.1.

3. **The POC's sub-bass band (30–140 Hz) is the wrong band, and it nearly failed.** Real
   close-miked human speech reaches a 30–140 Hz energy ratio of **0.110 at p95** — the POC's
   threshold was 0.10. Moving the band to **20–120 Hz** raises the per-second AUC from 0.875 to
   0.907, and to **0.986 after 9-second smoothing**. The male vocal fundamental lives at
   85–155 Hz; the POC's band was measuring the teacher's voice. **[verified]** §6.1.

4. **Subsequence chroma DTW and onset cross-correlation fail on exactly opposite things**, so
   running both and requiring agreement is a free confidence test. DTW survives a ±10 % tempo
   change and fails on a 1-semitone pitch shift; xcorr does the reverse. **[verified]** §7.1.

5. **A downbeat list gives you a free confidence number for "is a constant-meter bar grid even
   valid here".** Index each downbeat into the beat sequence, histogram `index % meter`: on one
   track the histogram was `[4, 54, 0, 4]` (87 % in one bin → trust the grid), on another
   `[21, 27, 21, 34]` (33 % → the track does not have one stable bar phase). **[verified]** §4.1.

6. **Do not preprocess before beat tracking.** `beat-this` recovered 124.01 bpm and 93 % of beats
   within 70 ms of the clean reference with **speech mixed 6 dB louder than the music**. Running
   `librosa.effects.hpss` first *broke* it into an 83.46 bpm octave error, and cost 10 s.
   **[verified]** §2.6.

---

## 1. The coordinate system: three numbers, not one

A "grid" over musical media is fully described by three things, and they have completely
different failure modes. Conflating them is what makes beat-tracking code fragile.

| number | meaning | who supplies it | how it fails |
|---|---|---|---|
| **period** `p` | seconds per beat | tempo estimator | *octave error* — 2p, p/2, 3p/2 |
| **phase** `φ` | where beat 0 sits | beat tracker, landmark, xcorr | *offbeat lock* — φ + p/2 |
| **meter** `m` | beats per bar | downbeat tracker | *meter error* — 2 vs 4, 3 vs 6 |

The POC's "8-count" is `8p`, and the block boundaries are `φ + k·8p`. Getting `p` right and `φ`
wrong puts every boundary off by a constant — the most damaging error, because it *looks*
correct (all the spacings are right) and is only visible against content.

A useful mental model for the facade: a grid method does not return spans. It returns a
**ruler** — `(φ, p, m, confidence)` plus the raw beat list — and something else turns artifacts
into spans against that ruler. Keep those two jobs in different functions. **[inferred]**

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class Grid:
    """A periodic ruler over media time. `unit_s` is the atom the domain counts in."""

    phase_s: float  # time of index 0
    period_s: float  # seconds per beat
    meter: int = 4  # beats per bar; 0 = unknown
    beats: np.ndarray = ...  # the raw beat instants, NOT assumed periodic
    downbeats: np.ndarray = ...
    confidence: float = 0.0  # see §4.1 — this is computable, not decorative
    source: str = ""  # 'beat-this/final0', 'librosa', 'essentia/multifeature'

    def unit_s(self, beats_per_unit: int = 8) -> float:
        return self.period_s * beats_per_unit

    def index_at(self, t: float, *, beats_per_unit: int = 8) -> float:
        return (t - self.phase_s) / self.unit_s(beats_per_unit)

    def time_at(self, k: float, *, beats_per_unit: int = 8) -> float:
        return self.phase_s + k * self.unit_s(beats_per_unit)
```

`beats` is kept alongside `(phase, period)` deliberately: real music drifts, and snapping to
the *nearest actual beat* beats evaluating the line for anything longer than ~30 s.

---

## 2. Beat and downbeat trackers — the catalogue

Cost figures are wall-clock on an M-series Mac for the 155 s track unless noted, model warm.

| tool | downbeats? | confidence? | licence (code / weights) | new dep? | cost (155 s) | verdict |
|---|---|---|---|---|---|---|
| **`librosa.beat.beat_track`** | ✗ | ✗ | ISC / n-a | **already in p12** | **0.1–0.86 s (≈1000× RT)** | keep as the free first pass |
| **`beat-this`** | ✔ (+ meter) | ✔ via frame logits | **MIT / MIT** | `beat-this` (+torch, present) | 2.9 s CPU · **0.39 s MPS** | **the recommendation** |
| `essentia` `RhythmExtractor2013` | ✗ | ✔ scalar 0–5.32 | **AGPL-3.0** / — | `essentia --pre` | 2.06 s multifeature · 0.49 s degara | disqualified on licence |
| `madmom` `DBNDownBeatTracking` | ✔ | ✗ | BSD-2 / **CC-BY-NC-SA 4.0** | `madmom` from git | not run | disqualified on licence + py312 |
| `BeatNet` | ✔ + realtime | ✗ | inherits madmom | `BeatNet`+`madmom` | not run | disqualified (madmom) |
| `allin1` | ✔ + **structure labels** | ✗ | inherits madmom | heavy | GPU-oriented | disqualified (madmom) |

### 2.1 `librosa.beat.beat_track` — the free baseline **[verified]**

Already installed (librosa 0.11.0). ~**990× realtime** on the 20-minute file (1.25 s); 0.82–0.86 s for the 155 s track.

```python
import librosa

y, sr = librosa.load(path, sr=22050)
tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time", trim=False)
```

**What it gets right.** Tempo. On the synthetic loop it reported 129.199 bpm against a truth of
129.200. On the two real tracks its least-squares tempo agreed with `beat-this` to
**0.05 bpm** (124.40 vs 124.45; 85.76 vs 85.79).

**What it gets wrong — and this is the POC's step-4 problem, quantified.** On `click129.wav`,
which has hi-hats on every eighth, librosa locked to the **offbeat**: least-squares phase
`t0 = 0.693 s` against a period of 0.4651 s, i.e. **0.490 beats — a half-beat off**, with a
residual RMS of **50 ms**. `beat-this` on the same file: residual RMS **9.7 ms** and phase
within 15 ms of truth. **[verified]**

In fairness: on the two *real* tracks librosa's beats sat a median of **32 ms** from
`beat-this`'s (90th percentile 51–63 ms), so its phase was fine there. The failure is
material-dependent, which is exactly why you cannot skip a phase check.

**When NOT to use it.** Anything needing bars, meter, or a phase you will not verify against
content. Never for a grid you will project 3 minutes forward from a single anchor.

**Gotcha.** The first librosa call in a *freshly installed* environment pays a one-time numba
compile — **10.1 s** measured in a new venv, 0.82 s in the warm `p12`. Do not benchmark on a
cold install and conclude librosa is slow. **[verified]**

### 2.2 `beat-this` — the recommendation **[verified]**

Foscarin, Schlüter & Widmer, ISMIR 2024, [CPJKU/beat_this](https://github.com/CPJKU/beat_this).
A transformer over log-mel frames with a shift-tolerant loss and **no DBN post-processing** —
which is the whole point, because the DBN is what dragged madmom (and its non-commercial
weights) into every other neural tracker.

```bash
pip install beat-this        # 1.1.0; pulls einops, rotary-embedding-torch, soxr, torchaudio
```

```python
from beat_this.inference import File2Beats

f2b = File2Beats(
    checkpoint_path="final0", device="mps", dbn=False
)  # dbn=False: no madmom
beats, downbeats = f2b(path)  # two float arrays, seconds
```

Measured, this session:

| checkpoint | device | 155 s track | 20.7 min file | peak RSS |
|---|---|---|---|---|
| `final0` (78 MB) | cpu | 2.9–9.3 s (17–53× RT) | 22.7 s (55× RT) | 2.19 GB |
| `final0` (78 MB) | **mps** | **0.39–0.56 s (280–400× RT)** | **2.9 s (424× RT)** | — |
| `small0` (8.1 MB) | cpu | 2.9 s (53× RT) | 27.3 s (45× RT) | 2.29 GB |
| `small0` (8.1 MB) | **mps** | **0.28 s (550× RT)** | **2.0 s (617× RT)** | — |

For scale: the POC's 10:51 video is **~1.5 s of beat tracking** on `final0`/MPS, or 0.6 s on
`small0`. This is no longer a cost worth optimising against.

`mps` and `cpu` produced **byte-identical beat and downbeat counts** on the 20-minute file
(2566 beats, 879 downbeats). On a *short* file MPS looks slower (3.3 s vs 1.4 s for 59 s) —
that is pure warm-up. **Warm the model once, then use MPS.** **[verified]**

Four things the docs do not tell you, all **[verified]** here:

- **Output is quantised to 20 ms.** `Audio2Frames` emits logits at exactly **50.03 fps**, and
  the beat times are frame centres — the unique inter-beat diffs on the synthetic loop were
  `{0.44, 0.46, 0.48}` and nothing else. Consequence: §3.1.
- **It auto-chunks.** `Spect2Frames.spect2frames` calls `split_predict_aggregate(chunk_size=1500,
  border_size=6, overlap_mode="keep_first")` — 30 s chunks with 6-frame overlap. You do not
  need to window long files yourself, but memory still grows: **2.2 GB for 20 minutes**, so
  budget ~4–6 GB for an hour.
- **There is a per-beat confidence, undocumented.** `Audio2Frames` returns raw logits; the
  sigmoid at the peak frames is a usable score. On 30 s of real music the peak-frame
  probabilities had median 0.992 and p10 0.613 — a clean "this beat is solid / this one is a
  guess" signal that `File2Beats` throws away.
  ```python
  from beat_this.inference import Audio2Frames
  import torch, librosa, numpy as np

  a2f = Audio2Frames(checkpoint_path="small0", device="mps")
  y, sr = librosa.load(path, sr=22050)
  beat_logits, downbeat_logits = a2f(y.astype(np.float64), sr)  # (T,) at 50 fps
  conf = torch.sigmoid(beat_logits)
  ```
- **A fresh install cannot read audio.** `beat_this.preprocessing.load_audio` tries
  `torchaudio.load` → `soundfile` → `madmom`, and raises a maximally unhelpful
  `RuntimeError: Could not load audio from "x.wav"` when all three fail. `torchaudio.load` is
  **already dead in `p12` at 2.9.0** (`ImportError: TorchCodec is required for
  load_with_torchcodec`) and equally dead at the 2.11.0 that `beat-this` installs. It works in
  `p12` only because `soundfile` 0.13.1 happens to be there. **In a clean environment, add
  `soundfile` explicitly.** **[verified]**

**When NOT to use it.** (a) When you only need tempo — librosa is 20× cheaper and just as
accurate. (b) On non-musical audio; it will emit a confident grid over speech. Gate it on the
music spans from §6 first. (c) When the material has no stable meter — check §4.1 before
trusting `downbeats`.

**Meter failure mode, measured.** On `click129.wav` — kick on 1 & 3, snare on 2 & 4, identical
every bar, bass root changing only once per bar — `beat-this` reported downbeats **every 2
beats**, i.e. it heard 2/4 where I wrote 4/4. It is not wrong so much as under-determined: the
only 4-bar cue was the bass line. **Meter is subject to an octave error exactly as tempo is,
and for the same reason.** **[verified]**

### 2.3 `madmom` — why it stays excluded **[verified: read LICENSE; from docs: the rest]**

The licence file splits cleanly: **source is BSD-2-Clause**, but the model files are
**CC-BY-NC-SA 4.0**, with the text *"You must not use the material for commercial purposes"*
and a named contact for commercial licensing. `mixing.audio.beats` already excludes it on
exactly this ground and the docstring says so. Nothing here changes that.

Independently, it is a packaging problem: **PyPI is stuck at 0.16.1 (2018)** — I listed the
available versions, the newest is 0.16.1 — with no cp312 wheel, so every downstream (`allin1`,
`BeatNet`) instructs `pip install git+https://github.com/CPJKU/madmom`, and the known
numpy≥2 incompatibility bites on any modern env. `p12` has numpy 2.2.6.

**Verdict: do not add madmom, and treat "requires madmom" as a disqualifier.** That single
rule removes `allin1`, `BeatNet` and `beat-this --dbn` from the menu at once, which is a large
simplification and worth stating as policy.

### 2.4 `essentia` — the one with a real confidence number **[verified]**

Contrary to the fleet note that it is absent-and-awkward, **a cp312 macOS-arm64 wheel exists**
(`essentia-2.1b6.dev1177-cp312-cp312-macosx_11_0_arm64.whl`, 19.8 MB). `pip index versions
essentia` reports "no matching distribution" only because every release is a pre-release:

```bash
pip install --pre essentia          # works on py3.12 / arm64
```

```python
import essentia.standard as es

audio = es.MonoLoader(filename=path, sampleRate=44100)()
bpm, ticks, confidence, estimates, intervals = es.RhythmExtractor2013(
    method="multifeature"
)(audio)
```

| file | multifeature | degara | truth |
|---|---|---|---|
| `click129.wav` | 129.20 bpm, conf **5.00**, 0.78 s | 129.20 bpm, conf 0.00, 0.22 s | 129.200 |
| `Down_where_I_live` | 124.32 bpm, conf **2.86**, 2.06 s | 124.32, conf 0.00, 0.49 s | (124.45 per beat-this) |
| `I_won,_you_lost` | 85.77 bpm, conf **2.79**, 1.96 s | 85.77, conf 0.00, 0.45 s | (85.79) |

Its **confidence is genuinely useful and nothing else offers one** — a scalar the docs scale
0–5.32 (<1.5 low, 1.5–3.5 moderate, >3.5 high). My measurement matches that reading: 5.00 on a
machine-perfect loop, ~2.8 on real music. Note `degara` **always returns 0.00** — the docstring
says *"ignore this value if using 'degara'"* and it means it. **[verified]**

**But it is AGPL-3.0** (commercial licence available from MTG-UPF). For a package that anything
in the fleet might import, AGPL is a stronger constraint than CC-BY-NC — it reaches network
use. **Verdict: excellent reference implementation, useful for calibrating your own confidence
against, not shippable.** No downbeats either.

### 2.5 `BeatNet` and `allin1` — both blocked by the same dependency **[from docs]**

- **`BeatNet`** (Heydari et al., ISMIR 2021) — joint beat/downbeat/tempo/meter, four modes
  including sub-50 ms-latency realtime. The realtime mode is the only thing in this survey that
  no alternative offers. Requires madmom. Not usable.
- **`allin1`** ([mir-aidj/all-in-one](https://github.com/mir-aidj/all-in-one)) — the most
  *complete* thing here: one call returns `bpm`, `beats`, `downbeats`, `beat_positions` (the
  1/2/3/4 within the bar) **and** `segments` labelled from
  `{start, end, intro, outro, break, bridge, inst, solo, verse, chorus}`. That is §2 and §5 of
  this document in a single function. Its README quotes an RTX 4090 doing 33 min in 73 s.
  Blocked by `pip install git+https://github.com/CPJKU/madmom`, plus NATTEN and demucs. A
  community fork `all-in-one-fix` claims py3.12/torch-2.x support; **inherits the madmom weights
  licence regardless.**
  Worth noting its own warning, which applies to everything in this file: *"Due to variations in
  decoders, MP3 files can have slight offset differences"* — **20–40 ms**. Decode to WAV once,
  align against the WAV, and keep that WAV as the timing authority.

### 2.6 Robustness: voice over music, and why you should not preprocess **[verified]**

The reelee case is not clean music — it is a teacher talking over a track. I mixed 48 s of
close-miked speech (tiled) over 120 s of music at three levels and compared the recovered beats
against `beat-this` on the clean music.

| condition | recovered tempo | median \|Δt\| vs clean | fraction of beats within 70 ms | cost |
|---|---|---|---|---|
| speech **−6 dB** vs music, raw | 124.36 bpm | **0 ms** | 0.99 | 8.3 s |
| speech **0 dB**, raw | 124.26 bpm | **0 ms** | 0.99 | 2.8 s |
| speech **+6 dB** (speech louder), raw | 124.01 bpm | **0 ms** | **0.93** | 9.5 s |
| speech +6 dB, **after `librosa.effects.hpss`** | ✗ **83.46 bpm** | 20 ms | 1.00 (of the wrong grid) | 14.2 s |

Two conclusions:

- **`beat-this` needs no help.** Even with the voice 6 dB *above* the music it recovered the
  tempo to 0.4 bpm and put 93 % of its beats within 70 ms of the clean-audio answer.
- **Harmonic/percussive separation actively hurt it**, turning a correct 124 bpm into an
  83.46 bpm error (≈ 2/3 — a triplet confusion), while adding ~10 s of compute. The same is
  likely true of a demucs drum-stem pass, which is far more expensive again.
  `demucs` 4.1.0 is present in `p12` and it is tempting; **the measurement says don't.**

**When you would still separate:** if the *speech* is what you want (ASR gating, §6), or if the
music is so quiet that `beat-this` returns few beats at all. Test before paying for it.

---

## 3. Tempo, and how it fails

### 3.1 Fit a line; never take a median IBI **[verified]**

Because neural trackers snap to a frame grid, the naive estimate is *systematically* wrong.

```python
def fit_grid(beat_times):
    """Least-squares (phase, period) through a beat list. Residual std is a free QC number."""
    k = np.arange(len(beat_times))
    A = np.vstack([np.ones_like(k), k]).T
    (phase, period), *_ = np.linalg.lstsq(A, beat_times, rcond=None)
    resid = beat_times - (phase + period * k)
    return phase, period, float(resid.std())
```

On `click129.wav`, truth 129.200 bpm:

| estimator | result | error |
|---|---|---|
| `beat-this` median IBI | 0.4600 s → **130.43 bpm** | +1.0 % |
| `beat-this` **LSQ fit** | 0.46439 s → **129.201 bpm** | **+0.001 %** |
| librosa reported tempo | 129.199 bpm | −0.001 % |

Residual RMS from the same fit is the quality gate: **9.7 ms** for `beat-this` on the synthetic
loop, **50 ms** for librosa (offbeat lock, §2.1), 48–71 ms for `beat-this` on real music
(genuine tempo drift, not error). **[verified]**

Caveat that matters for long media: on real tracks the LSQ residual is 48–71 ms, so a single
global line is good for tens of seconds, not minutes. Fit **piecewise** — per structural
section from §5 — or snap to `beats` directly.

### 3.2 Octave errors: detect, then correct

The classic failure: the tracker reports 2p, p/2 or 3p/2. Four detectors, cheapest first:

1. **The duration sanity check — the POC's own win, and it is one line.** If the artifact set
   carries a known count in musical units, the tempo is over-determined:
   ```python
   def implied_bpm(n_units, unit_beats, span_s):
       """44 eight-counts over 170 s of music ⇒ 124.2 bpm. Compare against the tracker."""
       return 60.0 * n_units * unit_beats / span_s
   ```
   The POC's document claimed 100 bpm for 44×8 counts, implying 211 s, against a 170 s music
   span; the tracker's 129 bpm implies 163 s. **The document was wrong and the arithmetic proved
   it.** Formalise the outcome as a ratio and read it as an octave test: a ratio near 1.0 is
   agreement, near 2.0 or 0.5 is an octave error in *one* of the two, and near 1.33/0.75 is a
   dotted/triplet confusion. Anything else means the count or the span is wrong — which is the
   interesting case, because it is the only method in this whole survey that can **falsify the
   input document.**
2. **Cross-tracker agreement.** librosa (0.1–0.9 s) and `beat-this` (0.39 s on MPS) are both cheap
   enough to always run. They agreed to 0.05 bpm on both real tracks. A factor-of-two
   disagreement localises the problem instantly and costs nothing. **[verified]**
3. **`librosa.feature.tempogram_ratio`** — energy at 13 metrical ratios of a candidate bpm
   (sixteenth … whole note, with dotted and triplet variants), from Peeters 2005 / Prockup 2015.
   Given a candidate `p`, comparing band 6 (`×1`) against bands 3 (`×2`) and 9 (`×1/2`) is the
   textbook octave test. **[verified: signature + docstring; I did not tune a decision rule]**
4. **Metrical-profile analysis** — the ISMIR 2010 "Beat Critic" measures eighth-note alternation
   to compare half-time and double-time hypotheses; reported to cut octave errors to 43 % of
   baseline. The simple published post-hoc rule is: take the three highest tempogram peaks, and
   if they form a half/double family, **pick the middle one.** **[from docs]**

### 3.3 When tempo is not constant

Everything above assumes one tempo. For rubato, live playing, or a video assembled from several
takes, use `librosa.beat.plp` (predominant local pulse, one value per frame) rather than a
global bpm, and let the grid be `beats` with no line fitted at all. `librosa.feature.tempo(...,
aggregate=None)` gives a per-frame tempo curve — 2560 frames for the 155 s track. **[verified:
both exist and run; I did not evaluate accuracy on rubato material.]**

---

## 4. Phase — where bar 1 actually is

Tempo gives spacing. Phase is the number that decides whether every downstream boundary is
right or uniformly wrong, and it is the one the POC had to solve by eye.

### 4.1 Route A — take it from a downbeat tracker, but check it first **[verified]**

`beat-this` gives downbeats directly, which is the whole reason to prefer it. But the raw list
is **not** a clean arithmetic progression: fitting a line through the downbeats of
`Down_where_I_live` gives a residual of **4179 ms**, and an apparent 2.87 beats/bar against a
modal gap of 4. The list has dropouts and spurious extras. The fix is to work in **beat index
space**, not time:

```python
def meter_and_phase(beats, downbeats):
    """Robust meter + bar phase from a possibly-ragged downbeat list.
    Returns (meter, phase_index, confidence in [0,1]). Confidence is the fraction of
    downbeats agreeing on one bar phase — the honest answer to 'is a constant bar grid valid'."""
    idx = np.abs(downbeats[:, None] - beats[None, :]).argmin(
        axis=1
    )  # snap to beat indices
    gaps = np.diff(idx)
    meter = int(np.bincount(gaps).argmax())  # modal spacing
    hist = np.bincount(idx % meter, minlength=meter)
    return meter, int(hist.argmax()), float(hist.max() / hist.sum())
```

Measured:

| track | gap histogram | meter | phase histogram | confidence |
|---|---|---|---|---|
| `I_won,_you_lost` | `{1:5, 2:5, 4:51}` | 4 | `[4, 54, 0, 4]` | **0.87 — trust it** |
| `Down_where_I_live` | `{1:10, 2:26, 3:8, 4:57, 5:1}` | 4 | `[21, 27, 21, 34]` | **0.33 — do not** |
| `click129.wav` | `{2:60, 4:2}` | **2** (should be 4) | `[63, 0]` | 1.00 — confidently wrong meter |

Three lessons, each with a design consequence:

- The confidence number is **free and discriminating** — 0.87 vs 0.33 on two ordinary pop
  tracks. Put it on `Grid.confidence` and let `align(method="auto")` route on it.
- A high confidence does **not** rule out a meter octave error (`click129` scored 1.00 on the
  wrong meter). Confidence validates *phase consistency given m*, never *m itself*. Meter
  needs the §3.2 checks or an external count.
- Never LSQ-fit downbeat times directly. Fit the **beats**, then locate the bar phase as an
  integer offset in that index space.

### 4.2 Route B — a visible landmark (what the POC did)

The POC read a periodic visual event (arms overhead once per 2×8) off a contact sheet and back-
solved `t0 = first_landmark − n_eights × eight_duration`. This remains the most reliable option
when the audio is ambiguous, and it generalises: **one anchor plus a grid beats a hundred
guesses.** The automated form is §5 of the gesture/vision file, not this one — but note the
interface it needs is small: a landmark method returns *times*, and this module converts times
to a phase. Keep that seam.

```python
def phase_from_landmark(landmark_t, period_s, *, units_before=0.0, beats_per_unit=8):
    """Back-solve the grid origin from one observed event at a known grid index."""
    return landmark_t - units_before * beats_per_unit * period_s
```

### 4.3 Route C — cross-correlate against a reference **[verified, §7.2]**

If you have the clean master audio and the video's mixed audio, the offset between them is one
`np.correlate` over onset envelopes: **0.001 s**, exact on my test. This is
`mixing.audio.find_audio_offset` and it already exists in the fleet with a confidence field.
Use it whenever a reference exists — it converts an unknown phase into a known one for free.

### 4.4 Route D — onset novelty peaks

Sub-case of C with no reference: pick the strongest onset in the first few seconds and call it
`φ`. Cheap, and wrong often enough (a pickup note, a fade-in, a crowd noise) that it should only
ever be a **fallback with `confidence≈0.2`**, never a default. **[inferred]**

---

## 5. Music structure — intro / verse / chorus, and "the refrain repeats 4×"

This is the section that maps most directly onto reelee's actual problem: *the routine has a
refrain that comes back four times, and the artifacts describing it should land on all four.*

### 5.1 `librosa` Laplacian segmentation — works, with a trap **[verified]**

McFee & Ellis, ISMIR 2014, published as a librosa gallery notebook. Beat-synchronous CQT →
affinity recurrence matrix → combine with a path-continuity graph → normalised Laplacian →
k-means on the leading eigenvectors. **No new dependency**: librosa + scipy + sklearn, all in
`p12`. **3.6 s for the 155 s track (43× realtime).**

**The trap.** The gallery recipe emits a boundary at *every* label change, and labels flip
constantly. At k=6 it produced **27 boundaries**, many 3–4 s apart — unusable as structure. The
recipe as published is a *labeller*, not a boundary detector.

**The fix, and it is a better method than the original.** Sweep k and count votes; real
structural boundaries survive the sweep, spurious ones do not.

```python
votes = {}
for k in range(2, 10):
    X = evecs[:, :k] / (Cnorm[:, k - 1 : k] + 1e-12)
    ids = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(X)
    ids = scipy.ndimage.median_filter(
        ids, size=9, mode="nearest"
    )  # ← 9 beats; do not skip
    for b in 1 + np.flatnonzero(ids[:-1] != ids[1:]):
        votes[beat_times[b]] = votes.get(beat_times[b], 0) + 1
# merge votes within 2 s, keep boundaries with >= 6/8 votes
```

On `Down_where_I_live` the 8/8-vote boundaries were **42.9, 46.8, 84.9, 87.7, 107.5, 121.5,
130.6 s**, with 73.3 and 17.3 at 7/8 — a plausible and *stable* section map, from the same
computation that produced 27 boundaries unfiltered. The eigenvalue gaps
(`0.004, 0.005, 0.007, 0.006, 0.010, …`) also suggest k at a gap, but the vote count is more
robust and needs no threshold tuning. **[verified]**

**When NOT to use it.** Instructional video where the "music" is a single loop — the recurrence
matrix will be uniformly bright and every boundary will be noise. Also anything under ~60 s.

### 5.2 The other structure options

| tool | status | verdict |
|---|---|---|
| **`mixing.audio.segmentation.segment_by_self_similarity`** | in the fleet, tested (Foote checkerboard novelty) | **Use this first.** Already a `find_segments(strategy=...)` entry, no new dep, and the boundary-only cousin of §5.1. |
| `msaf` | **abandoned** — no PyPI release in >12 months, latest 0.1.80, docs pinned to librosa 0.6 | Do not depend on it. Its *algorithms* (Foote, SF, C-NMF, OLDA, 2D-FMC) are worth reading; the package is not worth installing. **[from docs]** |
| `allin1` | best labels available (`verse`/`chorus`/`solo`/…) | Blocked by madmom (§2.5). The only thing that names sections; if labels ever become required, this is the one to revisit. **[from docs]** |
| raw self-similarity + novelty | ~30 lines of numpy over any feature | The right escape hatch: the SSM is feature-agnostic, so the *same* code segments audio chroma, MFCC, pose-angle sequences, or CLIP frame embeddings. **[inferred]** |

**The design point that matters more than the tool choice.** A self-similarity matrix over any
per-frame feature gives both *boundaries* (novelty peaks along the diagonal) and *repetition*
(off-diagonal stripes). Reelee needs the second one — "these four spans are the same refrain" —
and almost every packaged segmenter throws it away in favour of a flat label sequence. **Expose
the SSM, not just its boundaries.** **[inferred]**

---

## 6. Music vs speech vs silence

### 6.1 The sub-bass ratio: it works, the POC's band was wrong **[verified — measured]**

Setup: 234 one-second speech frames (English close-mic, a podcast, French) and 369 music frames
(two songs plus a third track), each frame's normalised magnitude spectrum, energy in a band
over total, gated to `rms > 0.01`. ROC-AUC as a speech/music discriminator, raw and after a
9-second box smoother:

| band | AUC raw | **AUC 9 s-smoothed** | best-threshold acc | speech p95 | music p5 |
|---|---|---|---|---|---|
| 20–80 Hz | 0.910 | 0.960 | 0.860 | 0.026 | 0.001 |
| 20–100 Hz | **0.926** | 0.984 | 0.877 | 0.039 | 0.007 |
| **20–120 Hz** | 0.907 | **0.986** | 0.870 | 0.059 | 0.014 |
| **30–140 Hz (the POC's)** | **0.875** | 0.965 | 0.828 | **0.110** | 0.018 |
| 40–150 Hz | 0.846 | 0.937 | 0.815 | 0.145 | 0.019 |

Read this carefully, because it says three different things:

1. **The POC's band is the worst tested.** Its speech p95 is **0.110** against a threshold of
   0.10 — the POC was one differently-miked speaker away from failure. The cause is physical:
   **male F0 is 85–155 Hz**, so 30–140 Hz measures the voice. Per-file medians in that band:
   English close-mic speech **0.090**, French speech **0.111**, music 0.164–0.170. That is not a
   10× separation, it is 1.5×.
2. **Move the band down.** 20–120 Hz for smoothed decisions, 20–100 Hz if you must decide
   per-second. In 20–80 Hz, the same speech files sit at **0.001–0.031** against music at
   0.037–0.248 — the 10× the POC believed it had.
3. **The smoothing is not a detail, it is most of the method.** AUC 0.875 → 0.965 on the POC's
   own band purely from the 9-second window. The POC's rule was *"bass > 0.10 sustained for
   >10 s"*; the *sustained* is doing the work. Per-second accuracy tops out at 0.88 in **every**
   band — there is no threshold that makes this a per-second classifier.

The whole thing, vectorised, is **0.155 s for 20 minutes (8000× realtime)** — a hundred times
cheaper than any model in this document. **[verified]**

```python
def bass_ratio(y, sr=16000, *, lo=20.0, hi=120.0, frame_s=1.0, smooth_s=9.0):
    """Per-frame low-band energy ratio. Music ≫ speech. AUC ≈ 0.99 after smoothing."""
    n = int(sr * frame_s)
    k = len(y) // n
    fr = y[: k * n].reshape(k, n)
    X = np.abs(np.fft.rfft(fr * np.hanning(n)[None, :], axis=1)) + 1e-10
    f = np.fft.rfftfreq(n, 1 / sr)
    band = (f >= lo) & (f <= hi)
    ratio = X[:, band].sum(1) / X.sum(1)
    rms = np.sqrt((fr**2).mean(1))  # gate: the ratio is meaningless in silence
    w = max(1, int(smooth_s / frame_s))
    return np.convolve(ratio, np.ones(w) / w, mode="same"), rms
```

**Does it generalise? Honestly: mostly, with two named failure modes.** It will call
**bass-light music** (solo voice, acoustic guitar, a cappella, a string quartet) speech, and it
will call **bass-heavy speech** (a close-miked male voice with proximity effect, or anything
with room rumble, traffic, or HVAC) music. Both are visible in the data above. It is an
excellent *first* pass and a bad *only* pass. **[verified for the direction; the specific
material classes are [inferred] from the physics and the p95/p5 tails.]**

### 6.2 The principled alternatives

| method | what it needs | licence | in p12? | cost | when |
|---|---|---|---|---|---|
| **`mixing.audio.segmentation.segment_by_speech_music`** | audio | fleet | ✔ | cheap | **First choice.** Scheirer–Slaney (1997) low-energy-frame-ratio + ZCR variance, already tested, already behind `find_segments(strategy=...)`. Complementary features to the bass ratio — **combine, don't choose**. |
| spectral flatness (`librosa.feature.spectral_flatness`) | audio | ISC | ✔ | ~free | Tonal vs noisy; a third cheap cue for the same vote. |
| **`silero-vad`** | 16 kHz mono | **MIT** | ✗ (new dep, ~2 MB) | <1 ms per 30 ms chunk, CPU | **Best speech/non-speech gate.** `get_speech_timestamps(wav, model, return_seconds=True)`. Note: *speech vs not*, not *speech vs music* — it will fire on sung vocals. **[from docs]** |
| **PANNs / AST audio tagging** | 16 kHz, ~10 s windows | code Apache-2.0, PANNs weights CC-BY-4.0 | ✗ (`panns-inference`; or `MIT/ast-finetuned-audioset` via the already-present `transformers`) | GPU-ish; ~1–5 s per minute CPU **[inferred]** | The **principled** answer: AudioSet has explicit `Speech`, `Music`, `Singing`, `Drum` classes with per-class AP > 0.8 for Speech. Use when the cheap cues disagree, or when you need "is there a drum kit here at all" before beat tracking. **[from docs]** |
| `pyannote.audio` 3.1 | 16 kHz mono | **MIT**, but weights are **gated** — HF account + accepting conditions for two repos + a token | ✗ | GPU-oriented | Diarisation, i.e. *who* speaks — orthogonal to this file. The gate breaks "offline on a Mac" for first use. **[from docs]** |

**Recommended stack for §6, in the package:** bass ratio (20–120 Hz, 9 s smoothing) + Scheirer–
Slaney + spectral flatness as three cheap votes, escalating to PANNs only on disagreement. Three
independent cheap cues that fail on different material beat one model you cannot debug.
**[inferred]**

---

## 7. Audio-to-audio alignment

Three genuinely different problems that get conflated:

- **(a) "Where in this long recording is this known excerpt?"** → subsequence DTW or landmark
  fingerprinting.
- **(b) "By how much are these two recordings of the same thing offset?"** → cross-correlation.
- **(c) "Which track is this?"** → chromaprint/AcoustID. **Gives no time offset at all.**

### 7.1 Subsequence chroma DTW vs onset cross-correlation — the complementarity table **[verified]**

Setup: an 18 s excerpt cut from `Down_where_I_live` at a known **73.40 s**, perturbed seven
ways, then located in the full 155 s track. Both methods use only librosa + numpy — **no new
dependency.**

| perturbation of the query | subseq chroma DTW | onset xcorr | xcorr peak |
|---|---|---|---|
| identical (gain −4 dB + noise) | **+0.18 s** | **exact** | 0.849 |
| time-stretched **+2 %** | **+0.18 s** | ✗ **+56.9 s** | 0.270 |
| time-stretched **+10 %** | **+0.18 s** | ✗ +52.7 s | 0.153 |
| pitch **+1 semitone** | ✗ **+34.0 s** | **exact** | 0.706 |
| pitch **+12 semitones** | **+0.18 s** | **exact** | 0.795 |
| high-passed 300 Hz (phone EQ) | +0.44 s | **exact** | 0.853 |
| heavy noise (SNR ≈ −3 dB) | ✗ +53.2 s | ✗ +57.8 s | 0.415 |

Four things fall out of this table:

- **DTW is tempo-invariant and pitch-fragile; xcorr is the exact reverse.** Run both. If they
  agree within a second, you are done and the confidence is high; if they disagree, the
  *pattern* of disagreement tells you which perturbation you are facing.
- **Chroma is octave-invariant by construction**, so a +12 semitone shift is free while +1 is
  fatal. If pitch shift is expected, transpose-search the chroma (12 circular rolls) — cheap,
  since the DTW itself is only 0.08 s.
- **The xcorr peak value is a usable accept threshold**: 0.71–0.85 on every correct answer,
  0.15–0.42 on every wrong one. **Accept above ~0.5.**
- **DTW's error is a constant +0.18 s**, not noise — CQT frame smearing. Subtract it, or use a
  smaller hop.

Costs, 155 s reference × 18 s query, on CPU: `chroma_cqt` **0.72 s**, `librosa.sequence.dtw`
(subseq, cosine, 6674 × 776 cost matrix) **0.08–0.10 s**, `np.correlate` on onset envelopes
**0.001 s**. Nothing here needs a GPU or a model. **[verified]**

```python
# (a) find a known excerpt inside a long recording
C = librosa.util.normalize(
    librosa.feature.chroma_cqt(y=full, sr=sr, hop_length=512), axis=0
)
Cq = librosa.util.normalize(
    librosa.feature.chroma_cqt(y=query, sr=sr, hop_length=512), axis=0
)
D, wp = librosa.sequence.dtw(X=Cq, Y=C, metric="cosine", subseq=True, backtrack=True)
wp = wp[::-1]
start = librosa.frames_to_time(wp[0, 1], sr=sr, hop_length=512)
end = librosa.frames_to_time(wp[-1, 1], sr=sr, hop_length=512)
```

**When NOT to use DTW.** Low SNR (it failed at −3 dB where xcorr also failed), pitch-shifted
material without a transpose search, and long-vs-long alignment where the O(NM) cost matrix
blows up — 20 min × 20 min at 43 fps is 2.7 G cells. For long-vs-long, use
`global_constraints=True, band_rad=0.05`, or fingerprint instead.

### 7.2 What the fleet already has

`mixing.audio.audio_ops.find_audio_offset_detailed → AudioOffset(offset_s, confidence)` and
`align_clips_to_reference`, with `ALIGNMENT_FEATURES = ('envelope', 'waveform')`. This is
problem (b), already field-calibrated. **Do not reimplement it; import it, and add `'chroma'`
to `ALIGNMENT_FEATURES` so problem (a) lands in the same function.** **[inferred, from the
fleet inventory]**

### 7.3 Fingerprinting — only one of these gives you an offset

| tool | offset? | offline? | licence | verdict |
|---|---|---|---|---|
| **`audfprint`** (dpwe) | **✔ seconds** | ✔ | **MIT** | **The right tool for (a) at scale.** Landmark hashes + consistent-offset voting. Output line: *"Matched query.mp3 5.573 sec 204 raw hashes as …/05-Full_Circle.mp3 **at 50.085 s** with 8 of 9 hashes"*. Its own rule of thumb: *">5 or 6 consistently-timed matching hashes indicate a true match"*, with <1 % of random hashes landing consistently. Not on PyPI — vendor `audfprint.py` or pin a git ref. **[from docs]** |
| `pyacoustid` / Chromaprint / AcoustID | ✗ | **✗ — network API + key** | MIT (lib) | **Wrong tool.** `fingerprint_file` returns `(duration, fingerprint)` for a *whole file*; `lookup` needs an API key and hits acoustid.org. It answers "which released track is this", never "where inside this recording". |
| `dejavu` | ✔ | ✔ | MIT | Same landmark family as audfprint; needs MySQL/Postgres. Only worth it for a large persistent catalogue. **[from docs]** |

**Decision rule.** One reference and one query → DTW + xcorr (§7.1), zero new dependencies.
A *catalogue* of references to search → `audfprint`. Identifying a commercial release →
AcoustID, and accept the network. **[inferred]**

---

## 8. Facade shape — how all of this plugs into one interface

Everything above is either a **grid producer** or a **span producer**, and the difference is
worth encoding, because it is what lets `method="auto"` compose them the way the POC composed
them by hand. Extending the `Method` protocol from `00-existing-in-fleet.md` §5:

```python
# --- 1. Grid producers: audio -> a ruler. No artifacts involved. ------------------
class GridMethod(Protocol):
    name: str  # 'beat-this', 'librosa-beats', 'essentia-multifeature'
    requires: tuple[str, ...] = ()  # importable modules; preflighted before dispatch
    licence: str = "MIT"  # first-class — this is what excludes madmom
    cost: str = "cheap"

    def __call__(self, media: Media, *, span: Span | None = None, **kw) -> Grid: ...


def beat_grid(media, *, method: str = "auto", span=None, **kw) -> Grid: ...


# --- 2. Region producers: audio -> labelled spans. Also no artifacts. -------------
class RegionMethod(Protocol):
    name: str  # 'bass-ratio', 'speech-music', 'laplacian', 'silero'
    labels: tuple[str, ...]  # ('music','speech'), ('A','B','C'), ('speech','silence')

    def __call__(
        self, media: Media, **kw
    ) -> list[Region]: ...  # Region = (start, end, label, score)


def regions(media, *, method: str = "auto", **kw) -> list[Region]: ...


# --- 3. Locators: "where is THIS audio inside THAT audio" -------------------------
def locate(query: Media, reference: Media, *, method: str = "auto") -> Placement: ...
```

Five notes, each earned by something measured above:

1. **`Grid` is a return type, not a side effect.** The POC needed the grid three separate times
   (block boundaries, ASR gating, clip snapping). A method that returns spans directly cannot
   be reused; one that returns a ruler can. `mixing.audio.beats.BeatGrid` is already 90 % of
   this — it needs `phase_s`, `meter` and `confidence` added, and `downbeat_times` actually
   populated by a `backend="beat-this"`.
2. **`licence` on the protocol is load-bearing, not documentation.** Three of the six best
   trackers in §2 are unusable for licence reasons, and two of those are unusable *transitively*
   through madmom. `method="auto"` must be able to filter on it, and the preflight must reject
   `requires=('madmom',)` before anything downloads a weight.
3. **`confidence` must be computed, never defaulted to 1.0.** Every method in this file has a
   real one available: `beat-this` → sigmoid of frame logits and the §4.1 phase histogram;
   essentia → its own scalar; xcorr → peak height (>0.5 accept); DTW → path cost; laplacian →
   vote count out of 8; bass ratio → distance from threshold. The whole point of the agent
   surface is triage, and triage needs numbers.
4. **Regions gate grids, and grids gate everything else.** The POC's real pipeline was
   `regions(music) → beat_grid(within music span) → phase from landmark → ASR gated to speech
   spans`. Encode `span=` on `GridMethod.__call__` so this composition is expressible without
   the caller slicing audio files by hand.
5. **The duration sanity check is a `Prior`, not a method.** "44 eight-counts" is a property of
   the artifact *set*, exactly like "these 9 blocks are ordered". It belongs on `Prior`, where
   the solver can use it to reject a tempo — and it is the only mechanism in this document that
   can tell the caller their **input document is wrong**, which the POC proved is worth having.

**Minimum viable set, in dependency order** (everything except item 3 is already in `p12`):

| # | method | dep | why first |
|---|---|---|---|
| 1 | `bass-ratio` regions | numpy | 8000× RT, does the most work per line of code |
| 2 | `librosa-beats` grid | librosa | free tempo, free second opinion |
| 3 | **`beat-this` grid** | **`beat-this` + `soundfile`** | the only permissive downbeat source |
| 4 | `xcorr` + `dtw` locate | librosa | zero new deps, complementary failure modes |
| 5 | `laplacian` regions | librosa+sklearn | repetition structure, no new deps |

---

## 9. Environment: installed vs new

**Already in `p12`** (`/Users/thorwhalen/.pyenv/versions/3.12.12/envs/p12/bin/python`)
**[verified: import probe]** — librosa 0.11.0 · numpy 2.2.6 · scipy 1.16.3 · scikit-learn 1.7.2 ·
soundfile 0.13.1 · torch 2.9.0 · torchaudio 2.9.0 · mir_eval 0.8.2 · numba 0.61.2 ·
matplotlib 3.10.0 · demucs 4.1.0.

**Absent** **[verified]** — madmom · essentia · BeatNet · beat_this · allin1 · msaf ·
pyannote.audio · panns_inference · silero_vad · acoustid · chromaprint.

Three environment hazards found while testing, all **[verified]**:

- **`torchaudio.load` is already broken in `p12` at 2.9.0**: `ImportError: TorchCodec is
  required for load_with_torchcodec`. Nothing in this file needs it (`beat-this` falls through
  to `soundfile`), but code that assumes `torchaudio.load` works will fail confusingly. The
  forced-alignment op is a separate API and is unaffected.
- **`pip install beat-this` bumps torchaudio to 2.11.0**, which has the same problem. If it is
  installed into `p12`, `soundfile` is what keeps audio loading alive — do not remove it.
- **`python -m venv --system-site-packages` from a pyenv *virtualenv* inherits the base
  interpreter's site-packages, not the virtualenv's.** The venv I built from `p12` could not see
  `p12`'s `soundfile`. Consistent with the CLAUDE.md warning that "`python` is not one
  interpreter"; print `sys.executable` and the resolved `sys.path` before believing a benchmark.

---

## 10. Open questions

1. **Does `beat-this` go into `mixing` as `backend="beat-this"`, or into the new package?**
   `mixing.audio.beats` reserved `downbeat_times` for exactly this and documented the licence
   reasoning. Filling it there gives every fleet consumer downbeats for free, at the cost of
   making `torch` reachable from `mixing[beats]`. Filling it in the new package duplicates a
   `BeatGrid`. My read is **upstream into `mixing`, behind a `mixing[beats-nn]` extra** — but it
   is the same call as open question 6 in `00-existing-in-fleet.md` about the sub-bass ratio,
   and the two should be decided together.
2. **Is a hard "no madmom, no AGPL" policy actually right?** It costs `allin1`'s section labels,
   BeatNet's realtime mode, and essentia's confidence scalar — three capabilities nothing
   permissive replaces. If some reelee work is provably non-commercial, an *optional*
   `align[research]` extra could carry them. That is a licence decision, not a technical one,
   and it should be made once and written down rather than re-litigated per tool.
3. **What is the `Grid` confidence *calibrated against*?** I have six sources of a confidence
   number and no shared scale. `lacing.quality` already ships `boundary_iou` and
   `interval_iou`; the honest move is to hand-annotate one POC video's block boundaries and
   calibrate every method against it. Without that, `method="auto"` is comparing incomparable
   numbers.
4. **How much of §6 survives a bass-light domain?** Every music sample I measured had a drum
   kit. A cappella singing, acoustic guitar, or a spoken-word piece over strings would land in
   the overlap region. Before shipping the bass ratio as the default gate, measure it on one
   genuinely bass-light music file — it is a ten-minute test and it decides whether the default
   is one cue or three.
5. **Does the grid need to survive a re-cut?** Beat-derived spans are timestamps into one
   specific rendering. `mixing.transcript.formats.remap_time_after_cuts` is the only
   time-remapping code in the fleet. If a `Grid` is persisted to `lacing`, it should either
   carry the media hash it was computed against or be re-derivable — otherwise the first re-edit
   silently invalidates every stored span.
6. **`beat_positions` (1/2/3/4 within the bar) — do we need them?** `allin1` returns them,
   `beat-this` does not directly but they are recoverable from `meter_and_phase` (§4.1). An
   8-count grid needs the bar, not the beat position; a *dance* domain that counts "5, 6, 7, 8"
   might need the position. Cheap to add later, and the `Grid` shape above already admits it.
7. **Where does the reference audio come from?** §7 is the highest-precision tool in this file
   and it is unusable without a clean master. For a choreography video the song is a commercial
   release — findable, but with copyright implications for storing it. Is "fetch and cache the
   reference track" a thing this package does, refuses to do, or delegates?
