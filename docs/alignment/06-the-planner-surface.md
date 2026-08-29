# 06 — The planner surface: the agent that picks the method

**Question this file answers:** files 00–05 produce a menu of ~25 methods with wildly different
inputs, costs and failure modes. What sits on top, looks at a job, and picks?

**The proposal in one sentence.** *Every method in files 00–05 is the same record with a
different `gives` value; the planner is a filter, a linear ranking over ~20 boolean facts
measured by a **1.4 s/min probe**, and a budgeted graph walk — about 150 lines, fully
deterministic, and the LLM is nowhere near the control loop.*

Verification legend: **[verified]** = I ran it in the p12 env this session and pasted the real
output; **[from siblings]** = a measured result from files 00–05, cited by section;
**[inferred]** = my design judgement, which is most of this file — argue with it.

**What this file is.** A proposal to argue with. Sections 1 and 3 are the load-bearing ones;
2 is measured; 4–8 follow from 1 and 3.

---

## 0. The five claims, up front

1. **One record type covers all five sibling Protocols.** `Method` (00 §5), `GridMethod` /
   `RegionMethod` (02 §8), `Featurizer` / `Boundarizer` / `Scorer` / `Assigner` (03 §11),
   `Scorer` (04 §9) and `Solver` (05 §13) differ *only* in what they return. Collapse them
   into `Capability(needs, gives, …)` and planning becomes backward chaining on a graph of
   fewer than 30 nodes. §1.

2. **The probe is cheap enough to always run: measured 1.31–1.67 s per minute of media**
   across three real videos, and it separates the three genres by **20×** on one feature.
   **[verified]** §2. Sampled windows make it flat for long media: **2.9 s for the video
   passes regardless of duration.** **[verified]**

3. **The v1 selector is a hand-written linear score over profile facts — and that is not a
   placeholder, it is the same object a learned planner would be.** `score = Σ wᶠ·profile[f]
   − λ·cost`; v1 sets `w` by hand, v2 fits it from §8's calibration table. The interface
   never changes, so this is not a decision you pay for twice. §3.

4. **Escalation is per-boundary and re-solves, never patches.** 05 §11.2 measured a boundary
   with `sd = 14.8 s` next to an evidence-free artifact (correctly uncertain) and another with
   `sd = 1.0 s` that was **wrong by 18.5 s** (confidently wrong). So the trigger must be
   `max(posterior width, model-external disagreement)`, and the fix is another producer fed
   into the same solve — because 05 §10.2 measured fusion *halving* boundary MAE. §4.

5. **A human correction is a `Prior.anchor`, and anchoring is already just a mask on the DP's
   search** (05 §13 note 1). So correcting one span re-solves all the others for 0.13 s.
   Corrections live in their own log with provenance, survive a method change, and are the
   only artifact of the review pass. §5.

---

## 1. The capability model

### 1.1 The unification

Read the five sibling facade proposals side by side and they are one thing:

| Sibling protocol | file | signature, roughly | **`gives`** |
|---|---|---|---|
| `GridMethod` | 02 §8 | `media → Grid` | `grid` |
| `RegionMethod` | 02 §8 | `media → list[Region]` | `regions` |
| `Featurizer` | 03 §11 | `media → Curve` | `curve` |
| `transcribe` / `force_align` | 01 §6.2 | `media(, text) → list[TimedText]` | `timed_text` |
| `Boundarizer` | 03 §11 | `Curve → list[float]` | `boundary` |
| `Scorer` | 03 §11, 04 §9 | `(artifacts, media\|Curve) → Evidence` | `emission` |
| `locate` | 02 §8 | `(query, reference) → Placement` | `placement` |
| `Solver` / `Assigner` | 05 §13, 03 §11 | `(Evidence…, K, Prior) → Alignment` | `alignment` |
| `Method` | 00 §5 | `(artifacts, media) → list[Placement]` | `placements` |

Nine products, one record. The differences the siblings encoded as *different types* are
better encoded as *one field*, because the planner's whole job is to chain products, and a
type hierarchy is not chainable without hard-coded glue — which is exactly what "an agent
that reasons without hard-coded logic" must not have.

```python
Product = Literal[
    'grid',        # 02: a periodic ruler (phase, period, meter, beats)
    'regions',     # 02, 01 §4: labelled spans — music/speech/silence, VAD, structure
    'curve',       # 03: one signal on the media clock (motion, novelty, embeddings)
    'timed_text',  # 01: text with times — transcript, word times, forced alignment
    'boundary',    # 03, 05: candidate cut times, no labels
    'emission',    # 03, 04, 05: (K, T) — how well artifact k explains frame t
    'placement',   # 02 §7: ONE artifact located (subsequence DTW, xcorr, fingerprint)
    'alignment',   # 05: boundaries + assignment + confidence, from evidence
    'placements',  # 00 §5: the end product — one Placement per artifact
]
```

### 1.2 The declaration

```python
MAPPING_0 = field(default_factory=dict)     # shorthand used throughout this file

@dataclass(frozen=True, slots=True, kw_only=True)
class Capability:
    """What one method needs, gives, and costs. The planner reads ONLY this."""

    # --- identity -----------------------------------------------------------
    name: str                                   # 'bass-ratio', 'beat-this', 'llm-sheets'
    gives: Product
    summary: str                                # one line, shown to a human and an agent
    target: str                                 # "module:func" — LAZY, per muvid.footage.strategy

    # --- the three independent gates ----------------------------------------
    needs: frozenset[str] = frozenset()         # FACTS (§1.3). Hard. Checked against Profile.
    requires: tuple[str, ...] = ()              # IMPORTABLE MODULES. Hard. Preflight, per muvid.align
    licence: str = 'MIT'                        # Hard, policy-filtered. The madmom lesson (02 §2.3)

    # --- ranking ------------------------------------------------------------
    boosts: Mapping[str, float] = MAPPING_0     # fact -> weight added when the fact holds
    penalties: Mapping[str, float] = MAPPING_0  # fact -> weight subtracted when the fact holds
    base: float = 0.0                           # prior preference, breaks ties

    # --- cost, in the three units that actually differ ----------------------
    s_per_min: float = 0.0                      # wall-clock seconds per minute of media
    usd_per_hour: float = 0.0                   # for billable methods; 0 for local
    device: Literal['cpu', 'mps', 'cuda', 'network'] = 'cpu'
    fixed_s: float = 0.0                        # model load / first-call cost, amortised

    # --- what the number it returns MEANS ------------------------------------
    resolution_s: float = 1.0                   # finest boundary this method can justify (04 §9)
    regime: str = ''                            # 'cosine/siglip2-base', 'ratio/bass-20-120' (04 §8.3)
    calibrated_on: str | None = None            # None => confidence is NOT decision-grade
```

**Seven notes, each paid for by something a sibling measured.**

1. **Three gates, not one.** `needs` (facts about *this* job), `requires` (what is installed),
   `licence` (policy) are independent and fail differently: `needs` unmet is *"wrong tool"*,
   `requires` unmet is *"pip install X"* (00 §3.1 — `muvid.align` already raises exactly that
   message), `licence` blocked is *"never, for this deployment"*. Collapsing them into one
   `available: bool` loses the error message, which is the part the user acts on.

2. **`cost` is three numbers, not doc 00's `cost: str = "cheap"`.** A planner that must fit a
   budget cannot rank `'cheap'` against `'billable'`. `s_per_min` is comparable across the
   whole catalog because 02/03/04 measured every method in exactly that unit.
   `usd_per_hour` exists because `llm-sheets` costs $1.16/hour on Opus and $0.08 on Haiku
   (04 §5.4) and *neither number is seconds*. `fixed_s` exists because SigLIP's 4.4 s/min is
   marginal cost after a ~3 s model load — for a 30-second clip the load dominates.

3. **`calibrated_on: str | None` is the most important field, and it is usually `None`.**
   04 §8.3 measured SigLIP's match range at 0.095–0.152 and CLAP's at 0.369 — *"an alignment
   engine that reports a confidence without saying what regime it was calibrated in is
   reporting noise."* Making the field default to `None` means an uncalibrated confidence is
   **structurally unable** to be compared, and the fusion layer must fall back to rank fusion
   (05 §10.3). This is a type-level fix for the failure the siblings found twice.

4. **`boosts`/`penalties` are a linear model with hand-set weights.** See §3.2. This is the
   single design decision I most want argued with, and the argument for it is that it makes
   the v1 rule table and the v2 learned planner *the same object*.

5. **`resolution_s` lets the solver refuse.** 04 §5.5: a 4.6 s contact sheet cannot justify a
   0.4 s boundary. The solver should clamp emitted boundary precision to
   `max(resolution_s of the contributing evidence)` and say so in diagnostics.

6. **`target: str` is lazy, always.** `muvid/footage/strategy.py`'s `_LAZY_STRATEGIES:
   {slug: "module:func"}` **[verified: read the source]** is the fleet's answer, and it is what
   makes `list_capabilities()` enumerate a torch-backed method without importing torch. The
   agent surface is *the catalogue with costs*, cheaply — that property is non-negotiable and
   it is one dict.

7. **No `__call__` on the record.** The record is data; the callable is behind `target`. This
   is what lets the catalog be serialised to JSON for the MCP/agent surface (§7) and what lets
   the planner be tested with a fake catalog and no media at all (§8.4).

### 1.3 The fact vocabulary — closed, ~20 items

`needs` must draw from a **closed** vocabulary or the planner degenerates into string matching.
Every fact is (a) produced by the probe or the artifact set, or (b) a `Product` another
capability gives. That second half is what makes it a plan graph rather than a filter.

**Content facts** — measured by the probe (§2), each a float in `[0, 1]`, not a bool:

| fact | probe signal | measured separation **[verified]** |
|---|---|---|
| `music` | bass ratio 20–120 Hz, 9 s smoothed (02 §6.1) | 0.126 (dance) vs 0.006 (talking head) — **21×** |
| `speech` | RMS gate + inverse bass ratio + ZCR | 0.99 vs 0.01 silence fraction across the three files |
| `silence` | frame RMS below a *relative* floor | 0.99 on a screencast vs 0.00 on music |
| `metronomic` | **beat-fit residual sd** (§2.3 — new) | 9–12 ms (music) vs 142–322 ms (speech) — **27×** |
| `cuts` | ffmpeg `lavfi.scene_score` **rank**, never threshold | 0 (single take) vs 24 (edited) |
| `static_camera` | border-region / centre-region frame-diff ratio | 0.034 (tripod) vs 0.986 (cut-heavy) |
| `person_visible` | one pose pass on ≤10 sampled frames | — (opt-in, §2.4) |
| `periodic_motion` | ACF of the motion curve, top-k (03 §6.3) | r = 0.70 (dance) vs −0.01 (talking head) |
| `onscreen_text` | tesseract on 3 sampled frames, opt-in | — |
| `multi_speaker` | opt-in; not probed by default (01 §5) | — |

**Artifact-set facts** — free, read off the inputs and the `Prior`:

`artifacts.text` · `artifacts.ordered` · `artifacts.count` (an int, not a flag) ·
`artifacts.durations` (per-artifact hints) · `artifacts.exemplar` (an artifact carries a media
clip — 03 §6.5's one-shot case) · `artifacts.language` · `artifacts.verbatim`
(01 §0's P1-vs-P3 fork — *"the agent cannot reliably infer this from the text alone"*, so it is
an input fact, never a probed one).

**Product facts** — the name of any `Product` from §1.1, meaning *"some capability has already
produced one"*. `needs={'emission', 'artifacts.ordered'}` on the `ordered_dp` solver is what
makes the planner chain a scorer in front of it without a line of glue.

> **The vocabulary is closed on purpose.** A capability that wants a fact not on this list must
> either add it to the list (with a probe that measures it, and a cost) or stop asking. That
> constraint is the only thing keeping the planner from becoming twenty special cases.

### 1.4 The catalog, filled in from files 00–05

Every method the siblings recommended, as one table. `s/min` is **[from siblings]** where a
number is given and **[inferred]** where prefixed with `~`; `⊖` excludes decode.

| name | gives | needs | requires | s/min | licence | file |
|---|---|---|---|---|---|---|
| `bass-ratio` | regions | audio | — | **0.008** | fleet | 02 §6.1 |
| `speech-music` | regions | audio | `mixing` | ~0.05 | fleet | 00, 02 §6.2 |
| `vad-silero` | regions | audio | `faster_whisper` | ~0.1 | MIT | 01 §4.1 |
| `librosa-beats` | grid | audio | `librosa` | **0.7** | ISC | 02 §2.1 |
| `beat-this` | grid | audio, music | `beat_this`,`torch` | 0.14 | **MIT** | 02 §2.2 |
| `grid-fit` | grid | boundary \| grid | — | ~0 | — | 05 §9 |
| `laplacian` | regions | audio, music | `librosa`,`sklearn` | ~2 | ISC | 02 §5.1 |
| `xcorr-locate` | placement | audio, artifacts.exemplar | `librosa` | ~1 | ISC | 02 §7.1 |
| `dtw-locate` | placement | audio, artifacts.exemplar | `librosa` | ~1 | ISC | 02 §7.1 |
| `asr-mlx` | timed_text | audio, speech | `mlx_whisper` | **17** | MIT | 01 §1 |
| `asr-faster-whisper` | timed_text | audio, speech | `faster_whisper` | ~20 | MIT | 01 §1 |
| `forced-align-ctc` | timed_text | audio, artifacts.text, artifacts.verbatim | `torchaudio` | **3** | BSD-2 | 01 §2.3 |
| `transcript-cues` | boundary | timed_text | — | ~0 | MIT | 04 §7.1 |
| `embed-order` | emission | timed_text, artifacts.text | `sentence_transformers` | ~1 | Apache-2 | 01 §3.3 |
| `fuzzy-order` | emission | timed_text, artifacts.text | `rapidfuzz` | ~0 | MIT | 01 §3.2 |
| `scene-score` | curve | video | — | **0.8** | ffmpeg | 03 §3.3 |
| `frame-diff` | curve | video | `cv2` \| ffmpeg | **0.1** ⊖ | — | 03 §4.1 |
| `flow-farneback` | curve | video | `cv2` | 7.5 | Apache-2 | 03 §4.2 |
| `siglip2-frames` | curve, emission | video, artifacts.text | `torch`,`transformers` | **4.4** | Apache-2 | 03 §8, 04 §2 |
| `foote-novelty` | boundary | curve | — | ~0 | — | 03 §8.2 |
| `acf-periods` | grid | curve | — | ~0 | — | 03 §6.3 |
| `pose-rtmlib` | curve | video, person_visible | `rtmlib`,`onnxruntime` | **10.9** | Apache-2 | 03 §5 |
| `pose-dtw` | emission | curve, artifacts.exemplar | `dtaidistance` | 0.35/q | Apache-2 | 03 §6.5 |
| `ocr-tesseract` | timed_text | video, onscreen_text | `pytesseract` | 14 | Apache-2 | 03 §10.1 |
| `clap-windows` | emission | audio, artifacts.text | `torch`,`transformers` | 7 | Apache-2 | 04 §3 |
| `llm-sheets` | emission | video, artifacts.text | `anthropic`,`PIL` | *billable* | commercial | 04 §5 |
| `ordered-dp` | alignment | emission, artifacts.ordered | — | ~0 | — | 05 §3 |
| `ordered-dp-gaps` | alignment | emission, artifacts.ordered | — | ~0 | — | 05 §3+5 |
| `needleman-wunsch` | alignment | emission, artifacts.ordered | — | ~0 | — | 05 §5 |
| `viterbi` | alignment | emission | `librosa` | ~0 | ISC | 05 §6.1 |
| `ctc-align` | alignment | emission | `torchaudio` | ~0 | BSD-2 | 05 §6.2 |
| `hungarian` | alignment | emission | `scipy` | ~0 | BSD | 05 §8 |
| `changepoint` | boundary | curve | **`ruptures`** | ~0 | BSD-2 | 05 §7 |
| `duration-check` | — (a *validator*, §4.3) | artifacts.durations | — | ~0 | — | 02 §8.5, 05 §9.5 |

**34 capabilities. 24 of them run on what is already in p12. One new hard dependency in the
whole design (`ruptures`, 05 §14), and it is optional.** That is the number that says the
capability model is not over-engineering: the catalog is real and it is already this big.

---

## 2. Context study — the probe

### 2.1 What it must be

The planner reads a `Profile`, never the media. So the probe's contract is: **cheap enough to
always run, and it must set every fact in §1.3 that does not require an opt-in model.** I built
one and measured it on three real videos of three different genres.

### 2.2 Measured cost and measured separation **[verified]**

Probe implemented in ~90 lines of numpy + two ffmpeg pipes, run in
`/Users/thorwhalen/.pyenv/versions/3.12.12/envs/p12/bin/python` on an M-series Mac, offline.

| | **`filage.mp4`** dance, music, one static take | **talking head** edited, 720p | **screencast** near-silent, 720p |
|---|---|---|---|
| duration | 166 s | 420 s | 178 s |
| **bass ratio p50** (loud frames, 20–120 Hz) | **0.126** | **0.006** | 0.021 |
| silence fraction (RMS gate) | 0.00 | 0.01 | **0.99** |
| `scene_score` > 0.10 | **0** | 24 | 4 |
| border/centre motion ratio | **0.034** | 0.986 | 0.382 |
| **beat-fit residual sd** | **12 ms** | **322 ms** | 142 ms |
| librosa tempo / least-squares tempo | 125.00 / **126.94** | 104.17 / 104.48 | 117.19 / 117.95 |
| motion-ACF top peak `r` | **0.704** | −0.014 | 0.484 |
| **probe wall clock** | **3.64 s** | **11.19 s** | **4.95 s** |
| **s per minute of media** | **1.31** | **1.60** | **1.67** |

Per-stage, averaged: `ffprobe` 0.03 s · audio decode to 16 k mono **0.06 s/min** ·
bass ratio + flatness + ZCR **0.02 s/min** · `librosa.beat_track` ~1.9 s (mostly fixed) ·
`ffmpeg lavfi.scene_score` **0.34 s/min @ 480p, 0.70 s/min @ 720p** · gray frame pipe at 3 Hz
**0.19 s/min @ 480p, 0.50 s/min @ 720p** · motion energy + ACF 0.01 s/min.

**The two headline separations are both essentially free** (0.02 s/min combined) and both
20×–27×. That is a better signal-to-cost ratio than anything else in files 00–05.

### 2.3 One new finding: the beat-fit residual is a free music detector **[verified]**

02 §3.1 says *"never read tempo off a median inter-beat interval; fit a line."* The residual of
that line is thrown away. It should not be — it is the cheapest `metronomic` detector in the
design, and it costs **zero** on top of a tempo fit you were doing anyway:

```python
idx = np.arange(len(beats)); A = np.vstack([idx, np.ones_like(idx)]).T
(period, phase), *_ = np.linalg.lstsq(A, beats, rcond=None)
resid_sd = (beats - A @ [period, phase]).std()          # <— the free fact
metronomic = float(np.clip(1.0 - resid_sd / 0.15, 0, 1))   # 0.15 s ≈ half a beat at 200 bpm
```

Measured `resid_sd`: **9.2 ms** on a synthetic click track, **12 ms** on real dance music,
**142 ms** on a screencast, **322 ms** on speech. librosa's beat tracker *always returns beats*
— on the talking head it confidently reported 104 bpm and 727 beats. The residual is what tells
you that grid is fiction. **[verified]**

This also gives 02 §4.1's "is a constant-meter grid valid here" confidence without needing a
downbeat tracker at all — useful, because `beat-this` is not installed and the downbeat field
is still empty (00 §7.8).

### 2.4 What the probe does NOT do

- **No model loads.** No SigLIP, no whisper, no pose. The whole point is that the probe is the
  thing you run before deciding whether to pay for those. `person_visible` and `onscreen_text`
  are therefore **opt-in probes** (`probe(media, extras=('person', 'text'))`), each ~1 s on ≤10
  sampled frames, and default to `None` = *unknown* — which the planner must treat as
  "cannot satisfy a `needs`" rather than as `False`. **[inferred]**
- **No thresholds baked in.** Every content fact is a float in `[0,1]` with the raw measurement
  kept beside it in `Profile.raw`. §3.2's ranking consumes the float; §4's escalation reads the
  raw value. Turning it into a bool early throws away exactly the margin information
  escalation needs.
- **No writes.** The probe is pure. Caching it is the caller's business (`dol`), and the cache
  key is the media content hash — 02 §10.5's warning that beat-derived spans belong to *one
  rendering* applies to the whole profile.

### 2.5 Long media: sample the video, keep the audio whole **[verified]**

At 1.6 s/min an hour of video profiles in ~96 s, which breaks the "seconds not minutes" rule.
The split is clean, because the two halves scale differently:

- **Audio passes stay whole.** Decode is 0.06 s/min (3.6 s/hour) and the bass ratio is
  0.02 s/min. `beat_track` on an hour is the only real cost, and 02 §2.2's scaling test says a
  20-minute file is fine. Keeping audio whole matters: `music` fractions and the tempo fit are
  *global* facts.
- **Video passes sample.** Measured on the 420 s talking head: three 45-second windows via
  **input-seek** (`-ss` before `-i`, keyframe seek) cost **1.72 s** for the scene score and
  **1.19 s** for the gray pipe, versus **4.93 s** and **3.52 s** whole-file. That is flat in
  total duration — an hour costs the same 2.9 s. **[verified]**

```python
def probe(media, *, sample_video_over_s: float = 600.0, windows: int = 3, window_s: float = 45.0,
          extras: tuple[str, ...] = ()) -> Profile: ...
```

The cost: `cuts` and `static_camera` become estimates from 2 % of a long file. Report that —
`Profile.sampled: bool` — and let §4 escalate to a full pass when a `cuts`-dependent method is
about to be chosen on a sampled profile. **[inferred]**

### 2.6 The steering prompt is a probe input, and it is where the LLM belongs

The user says *"these are the 9 blocks of the routine, in order, each one is 8 counts at about
100 bpm."* That sentence sets `artifacts.ordered`, `artifacts.count=9`, `artifacts.durations`,
a tempo hint, and a duration sanity check — and **no rule is going to parse it**.

So: **one bounded LLM call, before any media is touched, whose entire output is a `Prior` and a
set of fact overrides.** Never a tool loop, never in the selection path, and it sees no media
at all. Concretely:

```python
def read_steering(prompt: str, artifacts, *, llm=..., schema=PriorDraft) -> tuple[Prior, dict[str, float]]:
    """Prompt + artifact texts -> a Prior and fact overrides. Structured output, one call,
    no media, no tools. Returns an EMPTY Prior when `llm` is None -- this is a seam, not a
    dependency, and every default in the package works without it."""
```

Two guards that make this safe: the returned `Prior` is **validated against the artifacts**
(a duration hint whose sum disagrees with the media by >20 % is a *warning*, not a silent
override — that is exactly the POC's step 4, 05 §9.5), and every field it sets is recorded in
`Profile.provenance` as `'steering'` so §5's review surface can show a human what the sentence
did. **[inferred]**

### 2.7 The `Profile` dataclass

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class Profile:
    """Everything the planner is allowed to know. ~25 floats and a dict."""
    duration_s: float
    has_audio: bool
    has_video: bool
    facts: Mapping[str, float]          # §1.3 vocabulary -> [0,1]; ABSENT means unknown
    raw: Mapping[str, Any]              # the measurements behind the facts (curves, beats, tempo)
    prior: "Prior"                      # from the artifact set + §2.6's steering
    sampled: bool = False               # video facts came from windows, not the whole file
    provenance: Mapping[str, str] = MAPPING_0   # fact -> 'probe' | 'steering' | 'user' | 'correction'
    probe_s: float = 0.0
    media_key: str = ''                 # content hash; the cache key AND the staleness key
```

`facts` is a `Mapping`, and **absence means unknown, not false**. That distinction is the same
one 05 §10.4 makes about `Evidence.mask` — *"'no evidence here' and 'evidence says no' must not
be the same number"* — applied one level up. A planner that treats unknown as false will
silently refuse `pose-rtmlib` on every video it did not bother to look at.

---

## 3. Selection

### 3.1 The smallest thing that works

```
candidates = [c for c in catalog
              if c.needs <= satisfied(profile, produced)     # hard: facts + already-produced products
              and all(importable(m) for m in c.requires)     # hard: preflight, per muvid.align
              and licence_ok(c.licence, policy)]             # hard: policy
plan = cheapest chain from {} to 'placements' maximising Σ rank(c) subject to Σ cost(c) ≤ budget
```

That is it. Three filters and a budgeted walk. **The walk is not A\*, and should not be** — the
catalog has 34 nodes, `Product` has 9 values, and every useful plan is 2–5 capabilities deep.
Enumerate all chains under the budget and take the best; it is milliseconds and it is
inspectable. Reach for search when the catalog passes ~200. **[inferred]**

### 3.2 Ranking: a linear model with hand-set weights

```python
def rank(cap: Capability, profile: Profile) -> float:
    s = cap.base
    for fact, w in cap.boosts.items():
        s += w * profile.facts.get(fact, 0.0)
    for fact, w in cap.penalties.items():
        s -= w * profile.facts.get(fact, 0.0)
    return s

def cost(cap: Capability, profile: Profile) -> float:
    return cap.fixed_s + cap.s_per_min * profile.duration_s / 60.0
```

Example declarations, weights taken straight from the siblings' measurements:

```python
Capability(name='beat-this', gives='grid', needs={'audio'},
           requires=('beat_this', 'torch'), licence='MIT',
           boosts={'music': 3.0, 'metronomic': 2.0},      # 02 §2.2: the recommendation, when there IS music
           penalties={'speech': 1.0},                      # 02 §2.6: robust to speech, but not a reason to run
           s_per_min=0.14, fixed_s=3.0, device='mps', base=1.0)

Capability(name='siglip2-frames', gives='emission', needs={'video', 'artifacts.text'},
           requires=('torch', 'transformers'), licence='apache-2.0',
           boosts={'cuts': 2.0},                           # 03 §8.2: 5/5 section boundaries on edited video
           penalties={'static_camera': 2.0,                # 04 §0: indistinguishable from chance on the dance
                      'periodic_motion': 1.5},             #        video — one camera, one wall, one dancer
           s_per_min=4.4, fixed_s=3.0, device='mps',
           regime='cosine/siglip2-base', calibrated_on=None, resolution_s=0.17, base=1.0)

Capability(name='asr-mlx', gives='timed_text', needs={'audio'},
           requires=('mlx_whisper',), licence='MIT',
           boosts={'speech': 4.0},
           penalties={'music': 5.0},                       # 01 §1.4 + the POC: hallucinates over music.
           s_per_min=17.0, device='mps', base=0.0)         # The gate is a PENALTY, not a `needs`, so a
                                                           # mixed file still gets ASR — inside speech regions.
```

**Why a linear model and not an `if`-tree.** Three reasons, and the third is the real one:

1. It is *the same expression* whether the weights are hand-written or fitted. §8's calibration
   table has columns `(profile facts, plan, boundary error)` — exactly the training data for
   these weights. **Replacing the rule table is refitting `w`, not rewriting the planner.**
   That is the architecture-first argument: the seam exists on day one and never moves.
2. It composes with the budget without a special case. An `if`-tree has to be re-derived every
   time you change the budget; `argmax(Σ rank − λ·cost)` just changes `λ`.
3. **It forces every rule to be written as a number attached to a capability, next to its
   measured cost and licence.** The knowledge in files 00–05 is *"SigLIP fails on a static
   single-subject take"* and *"whisper hallucinates over music"* — facts about a **method**,
   not about a pipeline. Put them in the method's record and they survive being reordered,
   composed, and enumerated by an agent. Put them in a planner `if`, and they are invisible to
   `capability_info()` and they rot.

### 3.3 Where the LLM does and does not go

| | v1 | why |
|---|---|---|
| Reading the steering prompt into a `Prior` (§2.6) | **yes** | Nothing else can. Bounded: one call, no media, structured output, validated. |
| Choosing which capabilities to run | **no** | ≤34 candidates × ~20 boolean facts is a domain a linear model saturates. And an LLM in the loop makes the planner non-deterministic, which kills §8.4's golden-plan tests — the cheapest regression suite in the design. |
| Being a *capability* (`llm-sheets`, 04 §5) | **yes** | It is the best method for "which 3 seconds best show this move", and it is registered, budgeted and escalated-to like anything else. |
| Adjudicating low-confidence spans after the solve (§4) | **yes** | This is where its judgement is actually worth $1.16/hour. |
| Explaining the plan and the residual to a human (§5) | **yes** | Free, and it is the surface the user asked for. |

The user's framing — *"an agent that can study the context, what is available, and have a list
of possible methods"* — is satisfied by all five rows. The agent studies the context (§2), sees
what is available (`list_capabilities()`), and picks (§3.1). **The disagreement I am proposing
is only about row 2: the picking should be arithmetic, and the agent should be the thing that
sets up, inspects and overrides the arithmetic.** An agent that can read `plan.explain()` and
say *"no, force `method='pose-dtw'`, I know these are dance moves"* is more useful than one that
re-derives the choice from scratch every run and gets it slightly differently each time.

### 3.4 What would justify replacing the rule table

Say it now so it is falsifiable **[inferred]**:

1. **≥30 labelled runs** in §8's calibration table spanning ≥4 genres, where a fitted `w`
   beats the hand-set `w` on held-out boundary MAE. Then refit and keep the same code.
2. **The catalog passes ~200 capabilities**, or plan depth passes ~6, so exhaustive enumeration
   stops being milliseconds. Then add A\* with `cost` as `g` and `−rank` as an admissible `h`.
   Still not an LLM.
3. **A fact that is genuinely not a number** — "the user has a stylistic preference about where
   cuts land" — shows up and matters. That is the first honest case for a planner-LLM, and I
   have not seen one in files 00–05.

Notably *not* on the list: "the table got long". A 34-row table of weights is fine. A table with
34 special cases in a function body is not, which is why §3.2 is a table of *data*.

### 3.5 The one place a rule beats the model: hard incompatibilities

Two facts should be `needs`/hard-refusal, not a penalty, because getting them wrong is not a
degradation but a *confident lie*:

- **01 §0's P1-vs-P3 fork.** `forced-align-ctc` on paraphrased text produces confidently wrong
  word times. It carries `needs={'artifacts.verbatim'}` — an *input* fact, never probed. And
  01 §6.4's guard runs anyway (`alignment_is_trustworthy`, measured separation 0.07 vs 0.65)
  and abstains. Belt and braces, because 01 §9.7 concludes the safe default is *"always run the
  P3 path and offer to tighten"* — i.e. the plan prefers `embed-order`, and `forced-align-ctc`
  is a **refinement step** whose failure costs precision, not correctness.
- **Licence.** 02 §2.3's madmom exclusion and 05 §14's `aeneas` (AGPL) / `ctc-forced-aligner`
  (no licence declared) are policy, and policy is a filter. `licence_ok` takes an allowlist
  from config, defaulting to permissive-only, and 02 §10.2's open question (should there be an
  `align[research]` extra) is settled by *changing the allowlist*, not the code.

---

## 4. Escalation

### 4.1 The loop

```
profile  = probe(media, artifacts)                       # §2 — ~1.4 s/min, always
plan     = select(profile, budget=budget)                # §3 — milliseconds
evidence = [run(c) for c in plan.producers]              # the cheap tier
result   = solve(evidence, prior)                        # 05 §3 — 0.13 s for 9 × 33 min

for round in range(max_rounds):                          # default max_rounds=2
    suspect = [p for p in result.placements if triggered(p, result)]     # §4.2
    if not suspect: break
    spans   = credible_intervals(result, suspect, coverage=0.9)          # WHERE to look
    extra   = select(profile, budget=remaining,
                     exclude=plan.used, restrict_to=spans)               # §3, again
    if not extra: break                                                  # nothing left to try
    evidence += [run(c, within=spans) for c in extra]
    result    = solve(evidence, prior)                                   # RE-SOLVE, don't patch
    remaining -= cost(extra)

return result, needs_review(result)                      # §5
```

**Four properties this shape has, each earned by a sibling measurement.**

1. **It re-solves; it never patches.** 05 §10.2 measured boundary MAE going 6.36 s → **2.93 s**
   purely from adding weak boundary evidence to a global re-solve. Patching one span with a
   better answer leaves its neighbours where the worse evidence put them; re-solving moves them
   all. The ordered DP costs 0.13 s, so there is no reason not to.

2. **The expensive method is scoped to a span, not to the media.** `within=spans` is the whole
   cost story. `llm-sheets` over 33 minutes is unaffordable; over the 90 % credible interval of
   two suspect boundaries — 03 §8.3's coarse-then-fine shape, which 04 §6.3 says the literature
   independently confirms — it is a handful of sheets. Every `Capability` that can accept
   `within=` should, and 02 §8.4 already argues for `span=` on `GridMethod` for the same reason.

3. **It is at most two rounds by default.** Not because two is principled, but because the
   third round is where a budget disappears with nothing to show. Make `max_rounds` a keyword
   and default it low. **[inferred]**

4. **Escalation can also mean *re-probing*.** If §2.5 sampled the video and the plan wants a
   `cuts`-dependent method, round 1's cheapest escalation is a full `scene-score` pass at
   0.7 s/min — often cheaper than any new method, and it upgrades a fact rather than adding
   evidence. Treat the probe as a capability that gives facts. **[inferred]**

### 4.2 The trigger — never the posterior alone

05 §11.2 is the reason this section exists. Two rows from that measured table:

| boundary | posterior sd | truth | verdict |
|---|---|---|---|
| 3 | **14.8 s** | correct MAP | *correctly* uncertain — the artifact next to it had **no evidence at all** |
| 5 | **1.0 s**, `P(err ≤ 3 s) = 1.00` | **wrong by 18.5 s** | *confidently* wrong |

> *"The posterior is a statement about the model, not about the world."*

So `triggered()` is a **disjunction of one model-internal and at least two model-external
signals**, and the model-external ones are the point:

| signal | cost | catches | source |
|---|---|---|---|
| posterior sd > domain tolerance (05 §12.3) | free (you ran forward–backward) | genuine ambiguity — boundary 3 | 05 §11.1 |
| **producer disagreement**: pairwise boundary MAE between single-producer solves | free, you have the evidence | a producer that is lying — boundary 5 | 05 §11.3 |
| **duration check**: Σ artifact durations vs media span, > 20 % | free | *the input document is wrong* | 02 §8.5, 05 §9.5 |
| **relevance below the decoy floor** | k decoy scorings, ~1 s | "this artifact is not in this media" ⇒ `span=None` | 04 §8.2 |
| solver infeasibility / collapsed segments / order violations | free | a broken `Prior` | 05 §11.3 |
| `alignment_is_trustworthy` fails on forced alignment | free | the P1/P3 confusion (01 §0) | 01 §6.4 |
| **grid concentration `R`** low | free | "there is no grid here" — also §2.3's `resid_sd` | 02 §4.1, 05 §11.3 |

**Six of seven are free.** That is what makes escalation affordable: the deciding is free and
only the acting costs. And the duration check is the only one that can tell you the *input* is
wrong rather than the output — the POC's highest-value five lines (01 §7 R4).

### 4.3 Validators are a third kind of capability

`duration-check` in §1.4's table has `gives=—` because it produces neither evidence nor an
alignment. It reads the result and the prior and emits a **flag**. Three of the triggers above
are like this. Rather than special-case them:

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class Validator:
    name: str
    needs: frozenset[str] = frozenset()
    target: str = ''
    def __call__(self, result, *, prior, profile) -> list["Flag"]: ...

@dataclass(frozen=True, slots=True, kw_only=True)
class Flag:
    check: str                     # 'duration', 'monotonic', 'relevance', 'trustworthy'
    severity: Literal['info', 'warn', 'error']
    scope: Literal['run', 'artifact', 'boundary']
    subject: str | int | None      # artifact_id or boundary index
    message: str                   # human-readable, and it is the escalation reason
    detail: Mapping[str, Any] = MAPPING_0
```

Validators run always, cost ~0, and their `Flag`s are what `needs_review` and `explain()` both
read. The alternative — putting these checks inside the solver — makes them untestable
separately and invisible to the agent surface. **[inferred]**

### 4.4 The trap the escalation logic must not fall into: absolute thresholds

I built a synthetic fixture (§8.2) with four **hard full-frame colour cuts** and ran ffmpeg's
`lavfi.scene_score` over it. **[verified]**

```
top scores: (103.96, 0.270)  (22.32, 0.209)  (74.36, 0.088)  (44.64, 0.079)   <- all four are real
truth:       103.90           22.29           74.30           44.58
threshold >0.25 finds 1 of 4.  Rank top-4 finds 4 of 4, zero false positives.
```

A *maximal* visual change — solid navy to solid maroon, every pixel — scored **0.079**. On 03
§3.3's real screen recording, real section boundaries scored 0.10–0.29. **The same detector's
"obviously a cut" number differs by 3× between two contents.** This is 04 §8.3's regime problem
(*"0.13 from SigLIP 2 and 0.13 from CLAP are not the same fact"*) showing up in a method with no
model in it at all.

Two consequences for the planner, both structural:

- **A capability whose `calibrated_on is None` may only contribute *ranks*, never thresholds.**
  Enforce it: the fusion layer routes uncalibrated evidence through 05 §10.3's `rrf`, and the
  escalation trigger uses quantiles of the method's own output, never a literal.
- **The systematic bias is real too.** Every detected cut landed **+0.03 to +0.06 s late** —
  one to two frames at 25 fps, because a cut is detected on the first frame *of* the new
  segment. A half-frame-interval correction is one line and it is worth more than most of the
  tuning anyone will be tempted to do. **[verified]**

### 4.5 When to give up

Three conditions, in order of how often they will fire **[inferred]**:

1. **Budget exhausted** and flags remain → return with `needs_review` populated. Never silently
   spend more.
2. **No candidate left** that adds a *new* `Product` in the suspect spans → escalation cannot
   help; more of the same evidence will not move a solve that already fused it.
3. **The flags are `duration` or `order`-shaped** → the input is probably wrong, and no amount
   of media analysis fixes a document that says 44×8 at 100 bpm when the music is 129 bpm
   (02 §0.2, the POC's step 4). **Go to the human immediately and lead with the arithmetic**,
   because it is a two-line explanation the human can verify without watching anything.

Giving up must be cheap and loud. `Alignment.placements` still contains every artifact — with
`span=None` where the aligner abstained (00 §5 note 2: *"nothing may vanish from the record
just because it matched badly"*).

---

## 5. The human in the loop

### 5.1 A correction is an anchor, and anchoring is free

05 §13 note 1: *"`anchors` is a **pruning** of the solver's search, never a separate code path —
§3's `allowed` mask is exactly the mechanism."* Everything about the review surface follows
from that one fact:

```
human fixes block 4  →  prior.anchors['b4'] = (t0, t1)  →  re-solve (0.13 s)
                     →  blocks 3 and 5 move too, because the DP now knows where 4 ends
```

**A correction is not a patch on one row; it is information that constrains the whole solve.**
This is the single strongest argument for the review surface writing to a `Prior` rather than
to the result. In the POC, two blocks were assigned the same move (01/00 background); pinning
either one would have fixed the other for free.

### 5.2 Three verbs, and no more

```python
def pin(alignment, artifact_id, span) -> Prior        # "it is HERE"        -> anchors
def forbid(alignment, artifact_id, span) -> Prior     # "it is not there"   -> allowed mask
def absent(alignment, artifact_id) -> Prior           # "not in this media" -> exhaustive=False
```

Resist `split`, `merge`, `nudge`, `reorder`. Every one of those is expressible as a `pin` plus a
re-solve, and each new verb is a new code path in the solver's constraint handling — the place
05 §3.4 says the failure modes already live. **[inferred]**

`forbid` deserves a defence: it is the cheapest correction a human can give (*"that's the
warm-up, not block 1"*) and it costs the solver nothing (one `allowed[k, t] = False`), but it is
the one that most needs to survive a method change — see §5.4.

### 5.3 What the review surface shows, and in what order

Sorted **ascending by confidence** — the reviewer sees the 10 % that needs judgement first. That
is obvious. The non-obvious rule comes from 05 §11.2's boundary 5:

> **Also show a random sample of the high-confidence placements.** The confidently-wrong ones
> (`sd = 1.0 s`, wrong by 18.5 s) will never surface in a confidence-sorted list, and they are
> the errors that damage trust most. Two or three per run is enough to catch a systematically
> broken producer. **[inferred, but the failure it targets is measured]**

Per placement, the surface needs exactly four things:

| | why |
|---|---|
| the media, playable at the span, with ±1 unit of context | the only real check |
| **the evidence, itemised** — which capability said what, and how strongly | 00 §5 note 3: *"a method that returns only a number cannot be composed, argued with, or debugged"* |
| the flags (§4.3), in words | the duration check must be readable as arithmetic, not as a score |
| the neighbours' spans | because §5.1 means the fix will move them |

And one run-level thing: `plan.explain()` — what was chosen, why (the ranked candidates with
their scores), what it cost, and what was *not* run and why not (`needs` unmet / not installed /
licence / over budget). That last column is what turns "the tool did badly" into "the tool never
had a transcript because `mlx_whisper` isn't installed".

### 5.4 Corrections are a log, not a diff

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class Correction:
    artifact_id: str
    verb: Literal['pin', 'forbid', 'absent']
    span: Span | None
    author: str
    at: str                       # ISO timestamp
    media_key: str                # WHICH rendering this was true of (02 §10.5)
    reason: str = ''
```

Stored **separately from the alignment**, in `lacing` (which already ships PROV-O provenance and
a body-schema registry with migrations — 00 §1). Three things this buys, and the third is the
whole point:

1. Re-running with a better method **keeps** the human's knowledge. A correction log applied to
   a fresh solve is a strictly better run; a corrected *result* is a dead end.
2. It is auditable — 05 §12's calibration table wants exactly `(profile, plan, correction)`
   triples, so the review surface *is* the labelling tool. Free training data (§3.4, §8.5).
3. **It is the mechanism for "align this again after the re-edit".** `media_key` says which
   rendering a correction was true of; `mixing.transcript.formats.remap_time_after_cuts` is the
   fleet's only time-remapping code (00 §1) and it is what migrates a correction log across a
   re-cut. Without the log there is nothing to migrate. **[inferred]**

The one rule: **a correction is never silently dropped.** If a re-solve cannot honour an anchor
(it makes the problem infeasible — 05 §3's `select_score` already *classifies* infeasibility),
that is an `error` flag with the relaxation ladder's suggestion, not a quiet ignore.

---

## 6. The Python API

### 6.1 The whole public surface

Six functions and six dataclasses. Everything else is a registration.

```python
# ── the one verb ──────────────────────────────────────────────────────────────
def align(
    artifacts: Sequence[Artifact] | Sequence[str] | Mapping[str, str],
    media: Media,
    *,
    # --- the seams, each defaulting to the strongest no-new-dependency thing ---
    method: str | Sequence[str] | Capability | None = None,   # None = plan it (§3). A name pins it.
    prior: "Prior | None" = None,                             # None = infer from artifacts + steering
    profile: "Profile | None" = None,                         # None = probe it (§2). Pass to reuse.
    budget: "Budget | float | None" = None,                   # None = Budget.default() (§6.3)
    solver: str = 'auto',                                     # 05 §13's registry; 'auto' = ordered_dp
    corrections: Iterable["Correction"] = (),                 # §5.4 — applied as Prior constraints
    steering: str = '',                                       # §2.6 — free text, one LLM call, or ignored
    catalog: "Catalog | None" = None,                         # the seam that makes §8.4 testable
    on_progress: Callable[["Event"], None] | None = None,
) -> "Alignment":
    """Place each artifact on the media timeline.

    Returns one Placement per artifact, ALWAYS -- an unplaced artifact carries span=None.
    """

# ── the four things you call when `align` is not enough ───────────────────────
def probe(media, artifacts=None, *, extras=(), sample_video_over_s=600.0) -> Profile: ...
def plan(profile, *, budget=None, catalog=None, exclude=(), require=()) -> Plan: ...
def solve(evidence, n_artifacts, *, prior, solver='auto', weights=None) -> "SolverResult": ...
def explain(x: "Alignment | Plan | Placement") -> str: ...

# ── the catalogue: the agent's menu ───────────────────────────────────────────
def list_capabilities(*, gives=None, needs=None, installed_only=False) -> list[Capability]: ...
def capability_info(name: str) -> Capability: ...
def register(cap: Capability) -> Capability: ...          # or register_lazy(name, "module:func", **kw)
```

`list_capabilities` / `capability_info` are 00 §5's *"two functions on top, and only two — resist
a third."* I am adding `register` and `explain` and no more, and `register` is the extension
point rather than a query.

### 6.2 The types

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class Alignment:
    """The result. Everything needed to review it, re-run it, or argue with it."""
    placements: tuple[Placement, ...]        # one per artifact, ALWAYS (00 §5 note 2)
    profile: Profile                         # what was measured (§2.7)
    plan: "Plan"                             # what was chosen and why (§6.4)
    flags: tuple[Flag, ...] = ()             # §4.3 validators
    evidence: Mapping[str, "Evidence"] = MAPPING_0    # keyed by capability name, for §5.3
    elapsed_s: float = 0.0
    spent_usd: float = 0.0

    @property
    def needs_review(self) -> tuple[Placement, ...]:
        """Ascending by confidence, plus a sample of the confident ones (§5.3)."""

@dataclass(frozen=True, slots=True, kw_only=True)
class Plan:
    steps: tuple["Step", ...]                # (capability, kwargs, within, est_cost)
    considered: tuple["Rejected", ...]        # (name, why) — the column §5.3 needs
    budget: "Budget"
    est_s: float = 0.0
    est_usd: float = 0.0
    def explain(self) -> str: ...
```

`Artifact`, `Placement`, `Prior`, `Evidence`, `Span` are exactly 00 §5 and 05 §13. **Do not
redefine them here** — that is the point of having read the siblings.

### 6.3 The budget is a small object, not a float

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class Budget:
    seconds: float = 60.0                    # wall clock, per minute of media
    usd: float = 0.0                         # zero => no billable capability is even a candidate
    network: bool = False                    # offline by default -- the house rule
    devices: frozenset[str] = frozenset({'cpu', 'mps'})
    licences: frozenset[str] | None = None   # None => permissive allowlist (§3.5)

    @classmethod
    def default(cls) -> "Budget": ...        # 60 s/min, $0, offline. Everything in files 00-05
                                             # except llm-sheets and diarize-pyannote fits.
```

`usd=0.0` and `network=False` as defaults is the load-bearing choice: **`align()` out of the box
touches no network and spends no money**, and a user gets `llm-sheets` by asking for it
(`budget=Budget(usd=2.0)`), which is also the moment they find out it costs money. Progressive
disclosure with the failure mode facing the right way.

### 6.4 Progressive disclosure, three levels

```python
# 1. Simple things simple.
align(["warm-up", "block 1", "block 2"], "routine.mp4")

# 2. The common real case: steering + a prior.
align(blocks, "routine.mp4",
      steering="9 blocks, in order, 8-counts, roughly 130 bpm",
      budget=Budget(seconds=120))

# 3. Complex things possible: drive it by hand.
prof = probe("routine.mp4", extras=('person',))
p    = plan(prof, require=('pose-rtmlib',), exclude=('siglip2-frames',))
print(p.explain())
res  = align(blocks, "routine.mp4", profile=prof, method=[s.name for s in p.steps])
```

And the `context=` idiom from `muvid/footage/strategy.py` **[verified: read the source]** —
*"a strategy that needs the score tensor declares a keyword-only `context` parameter"* — is
exactly right here: a capability that wants the profile declares `profile` as a keyword-only
parameter and the dispatcher passes it; one that does not, never sees it. Same magic-parameter
dispatch, same reason.

### 6.5 `collections.abc` at the edges

- `Catalog` is a `Mapping[str, Capability]` — so a test passes a `dict` and the default is a
  registry object with lazy resolution. This is the seam that makes §8.4 possible.
- `Profile.facts` is a `Mapping[str, float]`; `Prior.anchors` a `Mapping[str, Span]`.
- Artifacts accept any `Sequence[str] | Mapping[str, str] | Sequence[Artifact]` and normalise
  once at the boundary. A `Mapping` keys by artifact id, which is what makes `corrections`
  round-trip.
- The writeback stays a separate call, per 00 §5: `to_store(alignment, *, store, asset_id)` →
  `lacing`. Keep the computation pure; that is what makes both halves testable.

---

## 7. The agent-facing surface

### 7.1 Two skills, not five

Per the fleet's canonical layout **[verified: `~/.claude/skills/skill-package-setup/SKILL.md`]**
— real files under `{pkg}/data/skills/<name>/` (ships with `pip`, discovered by `gh skill`),
bridged into `.claude/skills/` by symlink.

**`align-getting-started`** — *how to drive it.* When to call `align()` vs `probe()`+`plan()`;
the three-level ladder of §6.4; how to read `explain()`; how to feed a correction back; the
budget defaults and how to raise them. Short. Its job is to stop an agent from reimplementing
the pipeline by hand out of the docstrings — which is exactly what the POC session did, and
what this package exists to prevent.

**`align-when-it-goes-wrong`** — *the judgement.* This is the valuable one, and it is a
translation table from a symptom to a cause, drawn from the siblings' negative results:

| symptom | most likely cause | file |
|---|---|---|
| every span shifted by a constant | grid **phase**, not tempo. Tempo right + phase wrong looks correct | 02 §1 |
| word times confidently wrong | forced alignment on paraphrased text (P1/P3) — check the guard | 01 §0, §6.4 |
| transcript is fluent nonsense | ASR ran over music. Gate it to speech regions | 01 §1.4, POC step 5 |
| all artifacts scored the same | VLM on a static single-subject take — representational, not capacity | 04 §0, §2.3 |
| durations don't add up | **the input document is wrong.** Show the arithmetic | 02 §0.2, 05 §9.5 |
| confident and wrong by ~20 s | a lying producer; check producer agreement, not the posterior | 05 §11.2 |
| boundaries at every cut, not every section | cut detection is not section detection | 03 §0.1 |
| two artifacts on the same span | the order prior was not applied; check `Prior.ordered` | 05 §0, POC step 7 |

### 7.2 What belongs in a skill vs a docstring

The placement test I would use **[inferred]**:

| | goes in |
|---|---|
| what a function does, its arguments, what it returns | **docstring** — it is next to the code and it goes stale visibly |
| the list of methods and their costs | **neither** — `list_capabilities()`. A markdown catalog is stale the moment someone registers a capability, and §1.4's table is already 34 rows |
| when *not* to use a method | **`Capability.penalties` first** (so the planner acts on it), summary in the skill |
| how to recover from a bad result | **skill** — it is a procedure across several calls, and it is judgement |
| the fact vocabulary | **docstring on `Profile`**, because a capability author needs it while writing `needs=` |

The rule underneath: **a skill holds what an agent needs across calls; a docstring holds what it
needs during one.** And anything the *planner* can act on should be data on a `Capability`, not
prose anywhere — prose the planner cannot read is prose that will be contradicted by the
planner's behaviour.

### 7.3 The MCP surface

`py2mcp`'s `mk_mcp_from_refs` over exactly five: `probe`, `plan`, `align`, `explain`,
`list_capabilities`. Two notes:

- **`plan` before `align` is the whole point of exposing both.** An agent that can dry-run a
  plan, read its cost and its rejected candidates, and *then* commit is doing the thing the user
  described. An agent that can only call `align` is a wrapper.
- **`Capability` must serialise to JSON**, which §1.2 satisfies by keeping the callable behind
  `target: str`. The catalog is the agent's menu, and a menu that needs `torch` imported to be
  read is not a menu.

CLI and HTTP follow from the same five via `argh` / `qh`, per 06-surfaces-and-conventions.

---

## 8. Testing

### 8.1 The four tiers

05 §12.4 proposes three (synthetic matrices / semi-synthetic / the POC). The planner needs a
fourth *underneath* them, and it is the cheapest and most useful of the lot.

| tier | fixture | tests | cost |
|---|---|---|---|
| **0** | **a `Profile` as JSON** (§8.4) | **the planner** | microseconds, no media, no deps |
| 1 | synthetic `S` / `b` matrices (05 §12.4) | the solvers | milliseconds |
| **2** | **synthetic MEDIA** (§8.2) | the producers, end to end | ~2 s to build |
| 3 | real media with hidden ground truth (chapters, subtitles) | the producers on real signal | cheap |
| 4 | the POC video, hand-labelled | the whole pipeline, once | an afternoon |

### 8.2 Synthetic media is cheap and underrated — here is one, built and recovered **[verified]**

A 133.6-second video with **exactly known** boundaries, tempo and phase, in ~25 lines and about
2 seconds of ffmpeg:

```python
BPM, PHASE, SR = 129.2, 0.37, 16000
BOUND = [0, 22.29, 44.58, 74.30, 103.9, 133.6]        # the ground truth

# audio: a click (1 kHz + 60 Hz, exp decay) on every beat, PLUS a per-segment sine
#        so the audio carries BOTH the grid and the segment identity
for b in np.arange(PHASE, DUR, per): y[int(b*SR):...] += click
for k, (a, b) in enumerate(zip(BOUND[:-1], BOUND[1:])):
    y[(t >= a) & (t < b)] += 0.12 * np.sin(2*np.pi*(220*(k+1))*t[(t >= a) & (t < b)])

# video: one solid colour per segment + k+1 white boxes = a machine-readable label
#        (drawbox, NOT drawtext -- Homebrew ffmpeg 8.1 has no libfreetype [verified])
ffmpeg -f lavfi -i color=c=0x1b3a5c:s=640x360:r=25:d=22.29 \
       -vf "drawbox=x=20:y=20:w=40:h=40:color=white:t=fill" -c:v libx264 seg0.mp4
# ... then concat + mux the wav.
```

Recovery, run against the fixture **[verified]**:

| what | recovered | truth | error |
|---|---|---|---|
| tempo, least-squares (02 §3.1) | **129.202 bpm** | 129.200 | **0.0015 %** |
| phase | 0.4021 s | 0.3700 | 32 ms (7 % of a beat) |
| beat-fit residual sd | 9.2 ms | — | the `metronomic` fact (§2.3) |
| boundaries, `scene_score` **rank** top-4 | 22.32, 44.64, 74.36, 103.96 | 22.29, 44.58, 74.30, 103.90 | **+0.03 to +0.06 s**, systematic |
| boundaries, `scene_score` **threshold >0.25** | 103.96 only | | **1 of 4 — §4.4** |

**This one fixture already caught two real bugs in the design's assumptions** — the threshold
trap (§4.4) and the one-frame-late bias — for two seconds of ffmpeg. That is the argument for
tier 2 in one line.

**The pathology catalogue** the generator should parameterise, each mapping to a failure the
siblings measured:

| pathology | how to generate | what it must produce |
|---|---|---|
| an artifact with **no** signal | one segment identical to its neighbour | wide posterior, an escalation flag (05 §11.2 boundary 3) |
| an artifact **not present** | one artifact with no segment | `span=None`, not a confident lie (03 §8.3's kanban row) |
| a **wrong duration hint** | claim 44×8 @ 100 bpm over a 129 bpm track | the duration validator fires (05 §9.5) |
| **tempo drift** | ramp the click period 2 % over the file | grid `confidence` drops; `beats` beats `(phase, period)` (02 §1) |
| an **octave error** trap | clicks at 2× on alternating segments | detected, not silently halved (02 §3.2) |
| **music over speech** | mix a TTS/noise-burst track 6 dB under the clicks | region gate splits it; ASR stays gated (02 §2.6, POC step 5) |
| **reordered** artifacts | shuffle two segments | order violations counted, not smoothed over |
| a **re-cut** | drop 5 s from the middle and re-render | corrections migrate by `media_key` (§5.4) |

Two honest caveats: synthetic media has no *semantics*, so it cannot test `siglip2-frames` or
`llm-sheets` meaningfully; and it is unrealistically clean, so a producer that passes tier 2 has
proved it is *wired correctly*, not that it is *accurate*. Tiers 3 and 4 are where accuracy is
measured. Tier 2's job is that every one of the 34 capabilities has a run that must not crash
and must land within a documented tolerance. **[inferred]**

### 8.3 The catalog conformance test

One parametrised test over every registered `Capability` — the thing that keeps §1's model from
rotting as capability 35 arrives:

```python
@pytest.mark.parametrize('cap', list_capabilities(), ids=lambda c: c.name)
def test_capability_conforms(cap, synth_fixture):
    assert cap.gives in get_args(Product)
    assert cap.needs <= FACT_VOCABULARY | set(get_args(Product))   # §1.3 is CLOSED
    assert cap.licence in KNOWN_LICENCES
    assert (cap.calibrated_on is None) or cap.regime               # calibrated => say against what
    assert cap.s_per_min >= 0 and cap.usd_per_hour >= 0
    missing = [m for m in cap.requires if not importable(m)]
    if missing: pytest.skip(f'{cap.name} requires {missing}')
    out = resolve(cap.target)(**fixture_args_for(cap, synth_fixture))
    assert product_type(out) is PRODUCT_TYPES[cap.gives]           # it gives what it says
```

Thirty lines, scales to any catalog size, and it is the only test that can fail when someone
adds a capability that the planner cannot reason about.

### 8.4 The planner's own test needs no media at all

This is the payoff of §1's separation. **A `Profile` is ~25 floats and a dict — check in a
dozen of them as JSON fixtures and assert the chosen plan.**

```python
# tests/profiles/dance-static-music.json   <- produced by probe(), committed
{"duration_s": 166.0, "has_audio": true, "has_video": true,
 "facts": {"music": 0.95, "metronomic": 0.92, "speech": 0.05, "cuts": 0.0,
           "static_camera": 0.97, "periodic_motion": 0.70,
           "artifacts.ordered": 1.0, "artifacts.count": 9, "artifacts.text": 1.0}}

def test_plan_for_static_music_video(profile_fixture):
    p = plan(profile_fixture('dance-static-music'), budget=Budget.default())
    names = [s.capability.name for s in p.steps]
    assert 'bass-ratio' in names and 'librosa-beats' in names
    assert 'siglip2-frames' not in names        # 04 §0: measured null result on exactly this profile
    assert 'ordered-dp' == names[-1]
    assert p.est_s < 60 * profile_fixture('dance-static-music').duration_s / 60
```

Four properties this has that a media-based test cannot: it runs in microseconds, it needs no
optional dependency, it is **deterministic** (which is why §3.3 keeps the LLM out of selection),
and a fixture is a *readable statement of the case* — you can see at a glance what kind of video
it describes. Every genre in the corpus becomes one JSON file and 5 assertions.

The mirror test matters too: **assert what was rejected and why.** `p.considered` should contain
`('llm-sheets', 'budget.usd == 0')` and `('pose-rtmlib', 'needs person_visible: unknown')`. That
is the column §5.3's `explain()` shows a human, so it deserves a test.

### 8.5 Metrics, and the one that is actually about the planner

05 §12.3's six numbers (boundary MAE, max error, `F(window)` curve, mean IoU, coverage, order
violations) are the right report for an *alignment*. The planner needs a seventh, and it is
number 6 on that list promoted to first class:

> **Confidence calibration, bucketed.** Group placements by predicted confidence, report actual
> boundary error per bucket. *"This is the number that tells the agent whether to trust the
> method, and it is the whole point of having an agent choose methods."*

Plus two that are only about the planner **[inferred]**:

- **Regret**: for each labelled run, `error(chosen plan) − error(best plan in the catalog under
  the same budget)`. Computable offline by running everything once per fixture. This is the
  number that says whether §3.2's hand-set weights are any good, and it is the objective §3.4's
  refit would minimise.
- **Budget honesty**: `|actual cost − plan.est_s|`. A planner whose estimates are wrong cannot
  do §4's escalation arithmetic, and `s_per_min` decays as models and machines change. Assert
  it within 2× in CI on the synthetic fixture.

---

## Open questions

1. **Is `needs` really a hard gate, or should everything be a weight?** I made `needs` hard and
   `boosts`/`penalties` soft, and the split feels arbitrary at the edges: `asr-mlx` has
   `needs={'audio'}` and `penalties={'music': 5.0}`, but *"whisper hallucinates over music"* is
   nearly as absolute as *"whisper needs audio"*. A single soft model with very large weights
   is simpler and loses the ability to say *"this method is not applicable"* as a distinct,
   explainable outcome. **My lean: keep the split**, because §5.3's `explain()` needs
   "impossible" and "unlikely" to read differently — but I would not defend it hard.

2. **Who owns the fact vocabulary when it needs a 21st entry?** §1.3 is closed on purpose, but
   the first domain that needs `has_slides` or `is_screencast` will want to extend it, and if
   extension means a PR to this package the model has failed. Options: a `register_fact(name,
   probe_fn, cost_s_per_min)` seam (clean, but now the probe cost is unbounded and §2's budget
   claim evaporates), or a namespaced escape hatch (`x.has_slides`) that the planner treats as
   opaque. **Undecided, and it is the model's biggest scaling risk.**

3. **Is the probe cached per media, per media+extras, or not at all?** `Profile.media_key` says
   per media content hash — but `extras=('person',)` produces a *different* profile for the same
   media, and a correction (§5.4) can set a fact by hand. The obvious answer is a `dol` store
   keyed by `(media_key, frozenset(extras))` with hand-set facts layered on read. The
   non-obvious question is whether the cached profile should be **invalidated when the catalog
   changes** — it should, if a new capability introduces a new fact, and nothing in §2.7 records
   the catalog version.

4. **Does the planner need to know that two capabilities are correlated?** 02 §7.1's headline is
   that subsequence DTW and onset xcorr *"fail on exactly opposite things, so running both and
   requiring agreement is a free confidence test."* The linear model in §3.2 cannot express
   "these two are worth more together than apart" — it will pick the higher-ranked one and stop.
   A `complements: frozenset[str]` field would fix it with a bonus term, at the cost of a
   pairwise interaction the weights can no longer be fitted independently. **This is the first
   real limit of the linear model and I do not have a clean answer.**

5. **What is `budget` measured against — the media, or the job?** §6.3 says `seconds` is per
   minute of media, which makes a 3-second clip get a 3-second budget and never load a model
   (`fixed_s=3.0` alone exceeds it). A flat budget makes an hour-long file unaffordable. Some
   `max(floor, per_minute × duration)` is obviously right and the floor is another magic number.

6. **Should the planner be allowed to choose the `solver`?** §6.1 has `solver='auto'` as a
   separate keyword from `method`, because 05 §13's `Solver.handles` is a *different* dispatch
   key (it intersects `Prior`, not `Profile`). Two dispatchers with two vocabularies is a smell;
   one vocabulary covering both means `Prior` facts join §1.3, which is tidy but merges two
   things the siblings deliberately kept apart (05 §13 note 3: *"the solver must not be able to
   look at the artifacts"*). **My lean: keep them separate and accept the smell** — the solver's
   independence from media is what makes 05's entire verification strategy work.

7. **Where does this package end and `reelee` begin?** The planner reads a steering prompt,
   picks methods, escalates, and asks a human. That is most of an application. 00 §4.3 already
   asks whether this is a package or a module in `lacing`; the planner surface makes the
   question sharper, because the *catalog* is library-shaped and the *escalation loop with a
   human in it* is application-shaped. They may want to be two packages, with the loop living
   wherever the review UI lives.

8. **Two rounds of escalation, and then what?** §4.1 defaults `max_rounds=2` and §4.5 says give
   up loudly. But the honest answer for a long file is probably "escalate a *sample* of the
   suspects, measure whether it helped, and only then spend on the rest" — a bandit, not a fixed
   loop. That is more machinery than v1 deserves, but the fixed loop will look wrong the first
   time someone points this at a 90-minute video with 40 artifacts.
