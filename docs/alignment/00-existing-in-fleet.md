# 00 — Alignment in the fleet: what already exists

**Question this file answers:** if we build a package whose job is *"given artifacts and
media, find which span of the media each artifact corresponds to"*, what is already built,
what would we be duplicating, and should it be a new package at all?

**Short answer.** The capability does not exist as a capability, but **every one of its
parts exists, and three of them are excellent.** They are scattered across two *application*
packages (`muvid`, `kodokan`) and one *toolbox* (`mixing`), with the output substrate
(`lacing`) already complete and neutral. The single most important finding: **`muvid.align`
is already an aligner registry with a dispatch, a `requires` preflight, result dataclasses
and a `lacing` writeback — it is the package's v0 with `LyricsDoc` hardcoded into the
signature.** Do not write a second one. Generalize that one and have `muvid` import it back.

Verification legend: **[verified]** = I read the source at the path given, and/or imported
it and ran it in the p12 env. **[from docs]** = read from a README/docstring/design doc in
the repo, not executed. **[inferred]** = my judgement, argue with it.

---

## 1. The hit table

Everything the greps turned up, judged by reading the code rather than the name. Sorted by
what it is worth to the new package.

| Where | What it actually does | Maturity | Verdict for an alignment package |
|---|---|---|---|
| `t/muvid/muvid/align.py` (624 L) | **Aligner registry + dispatch.** `_ALIGNERS: dict[str, AlignerSpec]`, `register_aligner`, `list_aligners`, `aligner_info`, `align_lyrics(lyrics, transcript, *, duration_s, aligner=..., **kw)`. 4 registered aligners. Frozen result dataclasses. `write_alignment_store` → `lacing.SqliteStore`. | real; v0.0.32, 2 test files (236 L) | **THE SEED.** Take the shell wholesale; the only thing wrong with it is that its input type is `muvid.lyrics.LyricsDoc`. |
| `t/mixing/mixing/audio/audio_ops.py` (1564 L) | **Cross-correlation offset alignment.** `find_audio_offset`, `find_audio_offset_detailed → AudioOffset(offset_s, confidence)`, `align_clips_to_reference → list[ClipAlignment]`, `onset_envelope`, `ALIGNMENT_FEATURES = ('envelope','waveform')`. | real; 2 test files (426 L), field-calibrated | **TAKE AS-IS, DO NOT MOVE.** Best-documented alignment code in the fleet. |
| `t/mixing/mixing/audio/segmentation.py` (906 L) | **4 segmentation strategies** behind `find_segments(strategy=…)`: `silence`, `energy_novelty`, `self_similarity` (Foote checkerboard), `speech_music` (Scheirer–Slaney low-energy ratio + 4 Hz modulation). Callable passthrough. | real; 190 L tests | **TAKE AS-IS.** `speech_music` is the POC's step-1 (music vs speech gate) already generalized. |
| `t/mixing/mixing/audio/beats.py` (~150 L) | `beat_grid(audio, …) → BeatGrid(beat_times, downbeat_times, onset_env, onset_hop_s, sample_rate, tempo_bpm)`. librosa lazy-imported; `madmom` **deliberately excluded on licence grounds**; `downbeat_times` is an empty array with the field reserved for a stronger backend. | real; 74 L tests | **TAKE AS-IS.** This is the POC's step-2 already packaged, licence audit included. |
| `t/muvid/muvid/footage/select_score.py` (545+ L) | **A beat-snapped semi-Markov Viterbi DP.** Segments a timeline into shots with `[L_min, L_max]` length constraints, boundaries snapped to a beat set, a Potts switch penalty, a soft-max-length overrun penalty, infeasibility *classification* (coverage-gap vs dwell-infeasible) with a documented relaxation ladder. | real, carefully reviewed | **THE OTHER SEED — the exact algorithm the ORDER PRIOR needs**, but written against `FootageAlignment`/`ScoreTensor`/`EdlEntry`. See §3.3. |
| `t/muvid/muvid/footage/scoring/grid.py` (545 L) | **The shared-time-grid tensor.** `ScoreTrack(clip_id, metric, t0, hop_s, raw_values, mask, direction)`, `resample_to_grid`, `compute_norm`/`apply_norm` (robust median/IQR, percentile-clipped, per-metric-global), `ScoreTensor`, crash-consistent npz+manifest persistence, `align_fingerprint()` staleness key. | real | **HIGH.** This is "many heterogeneous evidence curves on one media clock, with coverage masks". Exactly what evidence fusion needs. |
| `t/muvid/muvid/footage/scoring/motionbeat.py` | **Video motion ↔ audio beat alignment.** `motion_beat_bas` (localized AIST++ Beat Alignment Score, `exp(−½(Δt/σ)²)`, σ=0.12 s) and `motion_onset_xcorr` (bounded-lag ±1.0 s normalized xcorr of the camera-compensated motion envelope vs the master onset envelope). | real | **HIGH — and it contradicts the brief's assumption.** The fleet *does* align visual motion to audio time; it just does it with motion energy, not pose. |
| `t/lacing/**` (v0.0.34, 87 commits, 33 test files) | `RationalTime`/`TimeInterval` (rational, half-open), 13 Allen relations, `IntervalAnnotationStore` = `MutableMapping[TimeInterval, list[Annotation]]` (Memory/SQLite/Postgres), PROV-O provenance, body-schema registry + migrations, 8 round-trip adapters, **`quality.py`: `boundary_iou`, `interval_iou`, `cohen_kappa`, `krippendorff_alpha`**, processor registry, CLI + HTTP + MCP (10 tools). Deps: pydantic, intervaltree, argh, dol. | real, mature | **THE OUTPUT SUBSTRATE, settled.** Also already ships the *evaluation metrics* for alignment quality. |
| `t/lacing/lacing/tracks/subtitle.py` | `SubtitleBuilder` / `SubtitleTrack` — the `(sections, lines, words)` tier trio in float seconds, hiding `Annotation`/`MediaRef`/`Provenance`. `lines_in`, `words_in`, `sections_covering`. | real | **HIGH.** The template for "an alignment result as a lacing track facade". |
| `t/muvid/muvid/footage/lacing_bridge.py` | Body schemas `clip-alignment/v1`, `clip-score-track/v1`, `music-video-edl/v1`; `editor_document()` (project → `{tiers, annotations}` all in one media clock) and `edl_from_annotations()` (back). `TIME_RATE = 1_000_000`. | real | **HIGH.** `clip-alignment/v1` is a published body schema for "this artifact sits here on this timeline". Reuse the URI or supersede it deliberately. |
| `t/kodokan/kodokan/segment.py` (313 L) | `pose_motion_energy`, `optical_flow_energy` (Farnebäck), `find_segments` with **hysteresis** (on above `high_quantile`, off below `low_quantile`), a two-person coverage gate, `self_similarity_matrix`, **`estimate_period`** (autocorrelation, RepNet-style), `segment_demonstrations`. | real but **dormant** (tip 2026-07-16) | **HIGH for the gesture gap.** `estimate_period` is the POC's "visible periodic landmark", automated. Not connected to audio time by anything. |
| `t/kodokan/kodokan/compare.py` (140 L) | Joint-angle features from COCO-17 (8 angles), **`compare()` = DTW via `dtaidistance.dtw_ndim`** → `{distance, normalized, path}`; `per_angle_deviation`, `distance_matrix`, `time_stretch`. | real, dormant | **HIGH.** DTW over a video feature sequence already exists in the fleet, with an honest documented caveat (2D joint angles are not viewpoint-invariant). |
| `t/kodokan/kodokan/pose.py`, `track.py` | `estimate_poses(video, …) → PoseSequence` `(F,P,17,3)` COCO-17, backends `rtmlib` (RTMPose, default) / `ultralytics` (YOLO11-pose), `device="mps"`. `estimate_poses_tracked(..., tracker="botsort.yaml")` for persistent identity. | real, dormant | **HIGH.** The pose front-end the brief says is missing is built, tested and Apple-Silicon-native. It has simply never been pointed at an alignment problem. |
| `t/an/an/audio/lipsync.py` + `providers.py` + `injectable_lipsync.py` | Two Protocols: `LipSyncProvider` (audio+transcript → visemes) and **`WordTimingProvider` (audio → `WordTiming = tuple[str,float,float]`)**, explicitly narrow "so external callers (e.g. `muvid`, with its own lyric alignment store) skip a redundant transcription pass". `make_lipsync(name, *, language)`. Capability flag `emits_word_timings`. | real, large (v0.1.78) | **MEDIUM.** Prior art for the *provider* half of the contract, and proof the fleet already wants an injectable alignment. `WordTiming` is a fine wire type. |
| `t/scribed/**` | ASR facade: 11 backends (faster-whisper, whisper.cpp, vosk, whisper, openai, groq, deepgram, assemblyai, elevenlabs, google), `Transcript`/`Segment`/`Word`/`TimeSpan` dataclasses with `.srt`, `list_backends(capability=…)`, `get_default_backend`, VAD Protocol (`EnergyVAD`, `SileroVAD`). `import scribed` is dependency-free; everything behind extras. | **young** — 9 commits, 3 test files, tip 2026-07-28 | **MEDIUM–HIGH.** The "transcribe first if needed" seam is already factored, and the catalog-of-backends-with-cost-metadata shape is the exact shape the *agent* surface needs. Immature, so treat as a seam target, not a hard dep. |
| `t/mixing/mixing/transcript/` | ElevenLabs Scribe wrapper with an on-disk cache, `words_to_srt`, filler detection/removal, cut remapping (`remap_time_after_cuts`). | real | MEDIUM. `remap_time_after_cuts` is the only "time survives an edit" code in the fleet. |
| `t/mixing/mixing/chapters.py` | `detect_chapters(...)` → `Chapter` list, LLM-segmented from a transcript with duration constraints (`_enforce_constraints`). | real | MEDIUM. This is "LLM proposes spans over a transcript", one of the POC's methods, already packaged. |
| `t/walkthru/walkthru/core/timeline.py` | Relative→absolute composition: authored `durationMs`/`holdAfterMs` → `ResolvedStep/Cue/Narration/Camera`. `resolve_timeline(doc) → Timeline`. Pure, dependency-free. | real (v0.0.18, 20 test files) | **MEDIUM — the degenerate case.** Ordered artifacts with known durations and no media at all. The order-prior solver should reduce to this when there is no signal. |
| `t/muvid/muvid/footage/strategy.py` | `SelectionStrategy` registry with **lazy** registration (`_LAZY_STRATEGIES: slug → "module:func"`) so listing a heavy strategy does not import numpy; progressive-disclosure `context=` magic parameter. | real | **HIGH as a pattern**, not as code. This is how to keep an alignment registry importable with zero heavy deps. |
| `t/artful/artful/shot_schedule.py`, `t/braidio/braidio/timeline.py`, `t/yb/yb/podcast/chapters.py`, `t/lacing/lacing/bodies/reference_lock.py` | Ordered-but-untimed shot lists; a render's *recorded* timeline; PSC/ID3 chapter export; "this artifact is canonical" decisions. | real | **Consumers, not engines.** Each is a downstream of an alignment, none computes one. |
| `t/falaw/falaw/cost.py`, `t/nw/nw/project.py`, `tt/reelee/reelee/importers/*`, `i/i2/i2/signatures.py` | "align" = cost alignment / prose / narrative structure; "anchor" = signature machinery. | — | **Unrelated.** Name-only hits. |

Nothing named `align*` exists as a package anywhere in `$PP` **[verified]** — I checked the
directory listing and the generated manifest.

---

## 2. Coverage against the method menu

The brief's starter list, plus what the POC actually used, against what is importable today.

| Method | Exists? | Where | Gap |
|---|---|---|---|
| **Beats / tempo** | **Yes** | `mixing.audio.beat_grid` (librosa, ISC) | No **downbeats** (field reserved, no backend). No **grid construction** (tempo → bar/8-count spacing) and no **phase fitting** — the POC's step 3, and the thing tempo alone cannot give you. |
| **Duration sanity check** | **No** | — | The POC's step 4 (44×8 @ 100 bpm = 211 s vs a 170 s music span ⇒ the *document* is wrong) caught a real error and is five lines of arithmetic. Nothing in the fleet does it. Cheap, high-value, belongs in the core. |
| **Transcribed words** | **Yes, three times** | `scribed` (11 backends), `mixing.transcript` (Scribe + cache), `an.audio.WhisperLipSync` (faster-whisper) | Three parallel ASR entry points; the new package must pick one seam, not a fourth. |
| **Forced alignment (text ⇄ audio)** | **No** | — | `muvid.align` does *greedy token matching against an already-timed transcript*, not CTC forced alignment. `whisperx` is not installed; `torchaudio` 2.9.0 **is**. The `stars` slot is a deliberate `NotImplementedError`. See `t/muvid/misc/docs/alignment_references.md` — the literature review is already written. |
| **ASR gated to non-music spans** | **Half** | `mixing.audio.find_segments(strategy="speech_music")` produces the gate | Nobody composes gate → ASR. That composition *is* the POC's step 5 and is ~10 lines. |
| **Sub-bass energy ratio** | **No** | closest is `segment_by_speech_music` (low-energy ratio + 4 Hz modulation) | The POC's single most valuable feature (energy 30–140 Hz / total, ~10× for music vs speech) is not one of the four strategies. Add it as a fifth `_STRATEGIES` entry **in `mixing`**, not in the new package. |
| **Order prior** | **Barely** | `muvid.align._interpolate_line_times` (private, linear interpolation between anchors) and the monotone cursor in `align_scribe_greedy` | **The biggest genuine gap.** No constrained assignment solver: "N ordered, non-overlapping artifacts → N spans, maximizing evidence". But see §3.3 — the algorithm exists, aimed at the dual problem. |
| **Gestures / pose** | **Yes, unattached** | `kodokan.pose` / `.track` / `.segment` / `.compare` | Complete pose front-end, motion-energy segmentation with hysteresis, repetition-period estimation, and DTW — none of it wired to a media clock or an audio signal. Connecting it is *wiring*, not research. |
| **Motion ↔ beat** | **Yes** | `muvid.footage.scoring.motionbeat` | Motion-energy only (no pose), and coupled to `FramePass`/`ScoreTrack`. |
| **Visual periodic landmark** | **Yes** | `kodokan.segment.estimate_period` + `self_similarity_matrix` | The POC did this by eye off a contact sheet. Automated version exists, dormant. |
| **LLM over timestamped frames** | **Half** | `mixing.chapters.detect_chapters` (LLM over a transcript with duration constraints) | Nothing does LLM-over-contact-sheet. The POC's step 6. |
| **Shot boundaries** | **Yes** | `muvid.footage.scoring.segment.shot_boundaries(clip_path, *, offset_s)` | Fine. |
| **Evaluating an alignment** | **Yes** | `lacing.quality`: `boundary_iou`, `interval_iou`, `cohen_kappa`, `krippendorff_alpha` | Already the right metric set. Nobody points it at an aligner's output. |

---

## 3. The three things worth reading before designing anything

### 3.1 `muvid.align` — the registry that already exists

`/Users/thorwhalen/Dropbox/py/proj/t/muvid/muvid/align.py` **[verified: imported and ran]**

```
>>> import muvid.align as A
>>> A.list_aligners()
['scribe-greedy', 'stars', 'user', 'whisperx-lite']
>>> A.aligner_info('whisperx-lite')
AlignerSpec(name='whisperx-lite', description='Offline: faster-whisper transcribe + greedy match.',
            fn=…, requires=('faster_whisper',))
```

The parts, and why each matters:

- `AlignerSpec(name, description, fn, requires: tuple[str,...])` — and `align_lyrics`
  **preflights `requires` with `__import__` and raises `RuntimeError(f"aligner {aligner!r}
  requires {pkg!r}; install it first (pip install {pkg})")` before dispatching.** That is the
  house `check_requirements` convention, implemented at the seam, already.
- `register_aligner(name, fn, *, description, requires=())` — open for extension; a
  user-registered name works because `AlignerName = str` is deliberately loose.
- `align_lyrics(lyrics, transcript, *, duration_s=0.0, aligner="scribe-greedy",
  **aligner_kwargs)` — one keyword picks the method, everything else forwards. This is the
  seam-as-keyword-argument rule, satisfied.
- Result types are frozen `slots=True kw_only=True` dataclasses, three levels
  (`Word/Line/Section Alignment` under `AlignmentResult`) with query helpers `lines_in(start,
  end)` and `section_for(t)`.
- `write_alignment_store(alignment, *, path, asset_id, rate=1000)` → `lacing.SqliteStore` via
  `SubtitleBuilder`. Note the deliberate `path.unlink()` first, with a comment explaining
  that this always creates a store stamped at lacing's *current* `SCHEMA_VERSION`.
- Surfaced already: CLI `muvid align --aligner=…` (`muvid/__main__.py:29`) and facade
  `muvid.facade.align_lyrics(root, *, aligner=…, **kw)`.

**What is wrong with it, precisely:** three things, all shallow.

1. The signature is `(lyrics: LyricsDoc, transcript: dict)` — domain types from
   `muvid.lyrics`. Generalizing means one parameter pair: *artifacts* and *media*.
2. The tier set is fixed at `(sections, lines, words)` — a text-shaped hierarchy. Dance
   blocks, chapters and steps are one flat ordered tier.
3. `transcript: dict` is the ElevenLabs Scribe response shape leaking through the public
   signature; `whisperx-lite` has to ignore it and take `audio_path=` instead, which the
   docstring apologizes for. The real input is *the media*, and a transcript is one kind of
   derived evidence.

**Recommendation:** the new package's registry *is* this file with those three fixed, and
`muvid.align` becomes a thin adapter that maps `LyricsDoc → artifacts` and re-exports. Do not
leave two registries in the fleet.

### 3.2 `mixing.audio` — the signal layer, already correct

**[verified: signatures below printed from the live objects]**

```python
find_audio_offset_detailed(reference_audio, query_audio, *, sample_rate=16000,
                           min_overlap_ratio=0.5, feature='waveform') -> AudioOffset
align_clips_to_reference(reference_audio, clips, *, reference_duration=None,
                         sample_rate=16000, min_overlap_ratio=0.5,
                         feature='envelope') -> list[ClipAlignment]
beat_grid(audio, *, sample_rate=22050, hop_length=512, start_bpm=120.0,
          backend='librosa') -> BeatGrid
find_segments(audio, *, strategy='silence', min_segment_duration=0.0,
              max_segment_duration=None, merge_gap=0.0, pad_start=0.0,
              pad_end=0.0, **strategy_kwargs) -> list[Segment]
ALIGNMENT_FEATURES == ('envelope', 'waveform')
AudioSource == Union[str, Path, np.ndarray, AudioSegment]
```

Three properties make this the strongest code in the fleet for our purpose, and all three
are things the new package should *inherit as culture*, not just call:

- **Confidence is calibrated against field data, and the docstring says so.** From
  `align_clips_to_reference` **[verified: read the source]**: on a real 6-device shoot, the
  raw-waveform coefficient scored provably-correct alignments at 0.064–0.148 while the
  envelope feature scored the same alignments 0.441–0.634 and a genuine non-match at 0.102.
  Hence `feature='envelope'` is the *default* for the cross-device case and `'waveform'` for
  same-source verification. An alignment engine that reports confidence without saying what
  regime the number was calibrated in is reporting noise.
- **Nothing vanishes because it matched badly.** `align_footage` returns a record for every
  clip, including non-overlapping ones, carrying `overlaps=False` rather than being dropped
  (`t/muvid/muvid/footage/align.py`). Make that a rule of the new package's contract.
- **Licence is audited at the seam.** `beat_grid(backend=…)` accepts only `"librosa"` (ISC)
  and raises for `"madmom"` with the reason inline: madmom's beat *models* are
  academic-licensed. Any new method entry needs the same field.

Heavy imports are lazy throughout (`require_package("librosa")`, `require_package("scipy.signal")`),
so `import mixing.audio` stays light.

### 3.3 `muvid.footage.select_score` — the order-prior solver, aimed at the dual problem

`/Users/thorwhalen/Dropbox/py/proj/t/muvid/muvid/footage/select_score.py` **[verified]**

Its own docstring: *"a beat-snapped semi-Markov Viterbi DP … choose which clip is on-air over
each span of the song so that the weighted composite reward is maximized, cuts land only on
beat (or beat∪shot) boundaries, shot lengths obey `[L_min, L_max]`, and each switch pays a
Potts penalty λ_switch."*

Read the recurrence in `_viterbi(aligns, boundaries, composite, tensor, cfg)` and the
correspondence to our problem is exact:

| `select_score` | alignment of ordered artifacts |
|---|---|
| candidate boundaries `B` (beats, or beats∪shot-cuts) | the same — beats, onsets, silences, shot cuts |
| state = which clip is on air | state = which artifact index is current |
| "consecutive segments must be different clips" | "the artifact index must **increase by exactly one**" — a *stricter*, cheaper constraint |
| `seg_reward(c,i,j)` = time-integral of the normalized composite, prefix-summed → O(1) | evidence that artifact *k* occupies `[B_i, B_j)` |
| `λ_switch` Potts penalty | a prior on block count / a resistance to spurious splits |
| `[L_min, L_max]` with `L_max` **soft** (overrun penalized, not forbidden) | per-artifact duration priors, equally soft |
| infeasibility *classified* (`coverage_gap` vs dwell-infeasible) then retried with `L_min→0` | the same failure taxonomy, and the same "never a silent junk result" rule |
| `allowed(i,j)` clip-domain hook makes a manual pin a *pruning* | a hand-anchored artifact is a pruning, not a reformulation — **exactly** what the POC's manual phase anchor was |

`WeightedSelectionConfig` is the config object: `weights: dict[str,float]`, `lambda_switch`,
`l_min_s`, `l_max_s`, `l_max_overrun_penalty`, `boundary_mode`, `beat_unit`, plus named
`PRESETS` (`"energetic"`, `"contemplative"`). Its docstring states the open-closed property
plainly: *"Adding a metric = a tensor column + a weight; no new strategy code."*

**This is the algorithm the new package needs, and it is already written, reviewed and
tested — against `FootageAlignment`, `ScoreTensor` and `EdlEntry`.** Extracting the
numpy-only kernel (boundaries + a reward matrix + length constraints + a transition penalty
→ a segmentation) is the highest-leverage single move available. Roughly 200 lines, and
muvid keeps its version by calling the extracted one.

---

## 4. Direct answers

### 4.1 Does an alignment capability exist in the fleet today?

**No — but four fifths of one does, and it is better than you would build in a week.**

Precisely:

- There is **no importable general alignment API.** `from <x> import align(artifacts, media)`
  does not exist. Nothing in `$PP` is named `align*` at package level **[verified]**.
- The **dispatch shell** exists exactly once, in `muvid.align`, complete with registry,
  `requires` preflight, result types and `lacing` writeback — but with `LyricsDoc` welded into
  the signature (§3.1).
- The **signal primitives** exist in `mixing.audio`, are domain-neutral, are the
  best-documented code in the fleet on this subject, and are field-calibrated (§3.2).
- The **combinatorial solver** exists exactly once, in `muvid.footage.select_score`, solving
  the dual of our problem against muvid's own types (§3.3).
- The **evidence-fusion layer** exists exactly once, in `muvid.footage.scoring.grid` —
  heterogeneous curves on one media clock with coverage masks, robust per-metric global
  normalization, and a staleness fingerprint.
- The **output substrate** is complete and neutral: `lacing`, including the quality metrics
  you would use to *score* an aligner.
- The **gesture branch** is fully built in `kodokan` — pose, tracking, motion energy with
  hysteresis, periodicity, DTW — and has **never been connected to a media clock or an audio
  signal.** It is dormant (tip 2026-07-16) but not stale in any way that matters.

The honest summary: **the fleet has an alignment engine, disassembled, with two of the parts
inside application packages that will not be dependencies of a general one.** The work is
extraction and one genuinely new piece (the primal order-prior solver, §2), not invention.

There is a second-order finding worth stating: the fleet has **six** independent registries
for "pick a method by name", and one of them (`muvid.footage.strategy`) explicitly documents
the shape as *"the federation's established shape"*. That convention is settled — reuse it,
do not invent a seventh idiom.

| Registry | Selector | Extras |
|---|---|---|
| `mixing.audio.segmentation._STRATEGIES` | `find_segments(strategy=str \| callable)` | `_resolve_strategy` accepts a callable |
| `muvid.align._ALIGNERS` | `align_lyrics(aligner=str)` | `AlignerSpec.requires` preflight |
| `muvid.footage.strategy._STRATEGIES` + `_LAZY_STRATEGIES` | `select_edl(strategy=…)` | lazy `"module:func"` registration; `context=` magic parameter |
| `lacing.processors._PROCESSORS` | `register_processor` / `run_sync` | sync-or-async, op-log aware |
| `scribed.registry` | `list_backends(capability=…)`, `get_default_backend` | availability probing, per-backend config catalog |
| `nw.transforms` | `xdol.Registry` (a `MutableMapping` with `on_conflict`) | the fleet's typed plugin registry |

### 4.2 What a new package should take rather than reinvent

| Take | From | How |
|---|---|---|
| `TimeInterval`, `RationalTime`, `Annotation`, `MediaRef`, `Provenance`, the store Protocol | `lacing` | Hard dependency. Non-negotiable — this is the output type and it is already the fleet's SSOT. |
| Allen relations (`intersects`, `relate`, `during`, …) | `lacing.allen` | Never write an ad-hoc overlap check. lacing's own rule; adopt it. |
| Quality metrics for evaluating an alignment | `lacing.quality` | The evaluation harness, already written **[verified signatures]**: `interval_iou(a: TimeInterval, b: TimeInterval) -> float` (pairwise), `boundary_iou(a: Iterable[TimeInterval], b: Iterable[TimeInterval]) -> float` (set-level — *this is "how good is this alignment vs the reference"*), plus `cohen_kappa` and `krippendorff_alpha` for agreement between two aligners or an aligner and a human. |
| The `(tier-builder, tier-query)` track facade pattern | `lacing.tracks.subtitle` | Write `lacing.tracks.alignment` — or a local equivalent — for the flat ordered-artifact case. |
| Body schema | `muvid.footage.lacing_bridge` `clip-alignment/v1` | Either reuse the URI or supersede it deliberately with a `v2`; do not silently mint a parallel one. |
| Every audio signal primitive | `mixing.audio` | Optional dependency behind an extra. **Do not vendor, do not reimplement**, and add the POC's sub-bass ratio as a fifth `_STRATEGIES` entry *upstream in mixing*. |
| Registry idiom + `requires` preflight + result dataclasses + lacing writeback | `muvid.align` | Move the file, generalize the signature, have muvid depend back on it. |
| The semi-Markov DP kernel | `muvid.footage.select_score._viterbi` | Extract the numpy-only core; muvid calls the extracted one. |
| The evidence-on-one-clock idea, masks, robust normalization | `muvid.footage.scoring.grid` | Extract or re-derive `ScoreTrack`/`resample_to_grid`/`compute_norm`; the *NA is never 0* discipline is the load-bearing part. |
| Pose / motion / DTW / periodicity | `kodokan` | Optional dependency behind a `[pose]` extra, or lift `pose.py` + `segment.py` + `compare.py` if kodokan stays dormant. `dtaidistance` is installed. |
| ASR | `scribed` (preferred seam) or `mixing.transcript` | One seam, injected as a keyword. Do not add a fourth ASR entry point to the fleet. |
| Word-timing wire type + the injectable-provider precedent | `an.audio.lipsync` (`WordTiming`, `WordTimingProvider`) | `an` already carved out a narrow protocol *specifically so an external aligner could feed it*. Honour that contract; it is a ready-made consumer. |
| Lazy registration so the package imports with zero heavy deps | `muvid.footage.strategy._LAZY_STRATEGIES` | Copy the `slug → "module:func"` pattern verbatim. |
| Store abstraction for anything cached (features, transcripts, model outputs) | `dol` | Already a `lacing` dependency, so free. |
| Plugin registry type | `xdol.Registry` | If you want a typed registry rather than a bare dict. |
| Surfaces | `qh` (HTTP), `py2mcp` / `fastmcp` (MCP), `argh` (CLI, already a lacing dep) | The house convention; `lacing` already exposes all three, which is a working reference. |

### 4.3 Separate package, or a module inside `lacing`?

**The case for putting it in `lacing`.** The output of alignment *is* lacing's data model —
same `TimeInterval`, same `Annotation`, same tiers, same provenance, zero impedance. lacing
already has a **processor registry** (`register_processor(func, *, name)`, contract "store +
op-log + kwargs → mutate and/or return") and an aligner is recognizably a processor. It
already ships the **evaluation metrics** an aligner needs to be judged by. It already has
**all three surfaces** — CLI, FastAPI HTTP, MCP with 10 tools — so the brief's "highest
surface is an agent" is substantially pre-built there. And the fleet has ~200 packages
already; not adding one has real value.

**The case against — and it is decisive.** Four arguments, in descending order of force.

1. **Dependency footprint, and who pays it.** lacing's runtime deps today are `pydantic`,
   `intervaltree`, `argh`, `dol` **[verified from `t/lacing/pyproject.toml`]**. Four, all
   featherweight. And lacing is the fleet's *substrate*: `nw`, `muvid`, `artful`, `braidio`,
   `walkthru` and `reelee` all depend on it, most of them for interval types and a store.
   An honest alignment engine's footprint is numpy + scipy + librosa + pydub/ffmpeg +
   torch/torchaudio + ultralytics/rtmlib/mediapipe + onnxruntime + dtaidistance. Extras hide
   that from `pip install`, but they do not hide it from lacing's `pyproject.toml`, its CI
   matrix, its licence surface, or the next reader trying to understand what lacing *is*.
   lacing's beat-adjacent culture is already licence-conscious (`mixing` excludes madmom on
   exactly these grounds); dragging a media-ML licence audit into a package whose current
   story is "MIT, four deps" is a real cost paid by five packages that get nothing back.
2. **Direction of dependency.** Alignment depends on lacing; lacing does not depend on
   alignment. Everything the aligner needs from lacing is already *public API* — there is no
   privileged internal access that co-location would buy. Putting it inside inverts a clean
   arrow for no gain.
3. **Import-time discipline is already a live fight in this fleet, and lacing is the wrong
   place to fight it.** `muvid.footage.strategy` carries `_LAZY_STRATEGIES` explicitly so
   that listing a strategy does not import numpy; `mixing.audio.beats` lazy-imports librosa
   so `import mixing.audio` stays light; `muvid.align` gates `faster_whisper` behind
   `requires`. Every one of these guards is one careless top-level import away from
   breaking. Putting the heaviest such subpackage inside the fleet's most-imported substrate
   maximizes the blast radius of that mistake.
4. **The fleet's own answer is already "one package per capability".** `mixing` (audio/video
   ops), `scribed` (ASR), `lookbook` (embeddings), `illustration` (retrieval), `burns`
   (motion spec), `foley` (SFX), `arioso` (music generation), `kodokan` (pose analysis). Each
   is a capability with a heavy, optional dependency tail and a registry of backends.
   Alignment is the same shape and roughly the same size. And note the tell: **lacing has no
   ASR in it**, despite the fact that its subtitle track, its WebVTT adapter, its TextGrid
   adapter and its `word/v1` body schema are all *about* transcripts. The line has already
   been drawn in exactly this place, deliberately.

There is a fifth, softer argument: the agent surface needs a **catalog** — per-method cost,
licence, latency, hardware, language coverage, failure modes — so it can *choose*. `scribed`
already demonstrates that shape in the fleet (`list_backends(capability=…)`,
`get_config(backend_id)`). A catalog of media-ML backends is not something an interval
annotation substrate should carry.

**Recommendation: a separate package.** With these boundaries, which are the ones that will
be expensive to change later:

- **Hard deps: `lacing` and `numpy`. That is the whole list.** Everything else is an extra
  with a `requires` preflight, and every method is lazily registered (`slug → "module:func"`)
  so `import <pkg>` and `list_methods()` never import numpy's neighbours, let alone torch.
- **It is not a second DSP library.** Signal features stay in `mixing`; pose stays in
  `kodokan`. The new package owns exactly four things: **(a)** the method catalog + the
  agent that picks from it, **(b)** the constrained-assignment solvers (the order prior —
  the one genuinely new piece), **(c)** the evidence-fusion layer (many curves on one media
  clock, with masks), **(d)** the `lacing` writeback. Anything it wants to *compute* it calls
  out for. New features get contributed **upstream** — the sub-bass ratio belongs in
  `mixing.audio.segmentation._STRATEGIES`, not here.
- **`muvid.align` moves in, and `muvid` depends back on it.** Non-negotiable; otherwise the
  fleet has two aligner registries and this document's whole purpose is defeated. Same for
  `_viterbi`: extract the kernel, have `select_score` call it.
- **`kodokan` is a `[pose]` extra**, or — if it stays dormant past this build — its three
  relevant modules (`pose.py`, `segment.py`, `compare.py`) are lifted with attribution. Ask
  before lifting; that is the user's call, not the agent's.

**One honest concession to the other side.** If the package turns out to be *only* the
solvers and the writeback — no catalog, no agent, no pose, no ASR seam — then it is ~400
lines of numpy over lacing types and `lacing.solvers` would be defensible. The thing that
makes it a package is the **agent + catalog**, which is the brief's stated highest surface.
Build that surface early enough to prove the package earns its name; if six months in there
is still no catalog, fold it into lacing and delete the repo.

---

## 5. The facade shape

Small, and deliberately close to what `muvid.align` already is — so the migration is a
rename plus a type generalization, not a rewrite.

```python
# ---- the two nouns ---------------------------------------------------------

@dataclass(frozen=True, slots=True, kw_only=True)
class Artifact:
    """A thing to be placed on a media timeline."""
    id: str
    text: str = ""                     # what a text-matching method sees
    order: int | None = None           # position in a known sequence; None = unordered
    hint: Span | None = None           # a human anchor: pins, not proposes
    meta: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True, kw_only=True)
class Placement:
    """One artifact placed. `span is None` means 'this method abstained', never 'nowhere'."""
    artifact_id: str
    span: Span | None                  # Span = tuple[float, float], seconds
    confidence: float = 1.0
    method: str = ""                   # which method produced it
    evidence: Mapping[str, Any] = field(default_factory=dict)   # why — beats, matched words…

# ---- the one verb ----------------------------------------------------------

def align(
    artifacts: Sequence[Artifact],
    media: Media,                      # path | (audio_path, video_path) | a loaded handle.
                                       # NOT lacing's MediaRef — that is an OUTPUT type,
                                       # naming the asset an Annotation points at.
    *,
    method: str = "auto",
    prior: Prior | None = None,        # ordered / non-overlapping / durations / anchors
    **method_kwargs,
) -> list[Placement]:
    """Place each artifact on the media timeline. Returns one Placement per artifact,
    ALWAYS — an unplaced artifact carries span=None, it is never dropped."""
```

The plug-in contract, one Protocol:

```python
@runtime_checkable
class Method(Protocol):
    name: str
    consumes: tuple[str, ...]          # 'audio' | 'video' | 'text' | 'transcript' | 'order'
    produces: str                      # 'spans' | 'boundaries' | 'evidence'
    requires: tuple[str, ...] = ()     # importable module names; preflighted before dispatch
    licence: str = "MIT"               # the madmom lesson: licence is a first-class field
    cost: str = "cheap"                # 'cheap' | 'gpu' | 'network' | 'billable'
    def __call__(self, artifacts, media, *, prior=None, **kw) -> list[Placement]: ...
```

Five notes on why it is shaped this way, each traceable to something already in the fleet:

1. **`method: str = "auto"` is the one seam.** Same as `find_segments(strategy=…)`,
   `align_lyrics(aligner=…)`, `select_edl(strategy=…)`. `"auto"` is where the agent lives:
   it reads `consumes`/`requires`/`cost` against what the caller actually has and picks. The
   catalog fields are what make that possible, which is why they are on the Protocol and not
   in a docstring.
2. **`Placement.span` is `Optional`, and nothing is ever dropped.** Directly from
   `muvid.footage.align`: *"including clips that do not overlap the song, which carry
   `overlaps=False` rather than being omitted. Nothing may vanish from the record just
   because it matched badly."*
3. **`evidence` is a mapping, not a float.** The POC's value came from *composed* evidence
   (sub-bass split → beat grid → visual phase anchor → duration check → gated ASR → LLM).
   A method that returns only a number cannot be composed, argued with, or debugged.
4. **`prior` is separate from `artifacts`.** "These 9 blocks occur in order and do not
   overlap" is a property of the *set*, not of any artifact; and it is the input to the
   solver, which is the one piece the fleet does not have. `walkthru.core.timeline` is the
   degenerate case (order + durations, no media) and the solver should reduce to it.
5. **Two functions on top, and only two.** `list_methods()` and `method_info(name)` — the
   `muvid.align` pair, which is also what the agent and the MCP surface both need. Resist a
   third.

Writeback stays a separate call, as `muvid.align` already has it:
`to_store(placements, *, path | store, asset_id, tier="alignment")` → `lacing`. Keep the
computation pure and the persistence explicit; that is what makes both testable.

---

## 6. The p12 env, alignment-relevant

`/Users/thorwhalen/.pyenv/versions/3.12.12/envs/p12/bin/python` **[verified: import probe]**

**Present.** numpy 2.2.6 · scipy 1.16.3 · scikit-learn 1.7.2 · librosa 0.11.0 · soundfile
0.13.1 · pydub 0.25.1 · pyloudnorm 0.2.0 · torch 2.9.0 · **torchaudio 2.9.0** · torchvision
0.24.0 · transformers 4.57.1 · sentence-transformers 5.5.1 · faster-whisper 1.2.0 ·
mlx-whisper 0.4.3 · openai-whisper 1.1.10 · demucs 4.1.0 · basic-pitch 0.3.0 · **dtaidistance
2.4.0** · rapidfuzz 3.14.5 · jiwer 4.0.0 · mediapipe 0.10.35 · ultralytics 8.4.75 · rtmlib
0.0.15 · onnxruntime 1.23.1 · insightface 1.0.1 · opencv 4.13.0 · av 16.0.1 · moviepy 2.2.1 ·
imagehash 4.3.2 · intervaltree 3.1.0 · praatio 6.2.2 · pympi 1.71 · jams 0.3.5 ·
opentimelineio 0.18.1 · srt 3.5.3 · networkx 3.5 · numba 0.61.2 · openai 2.11.0 · anthropic
0.75.0 · lacing 0.0.34 · mixing 0.0.38 · muvid 0.0.32 · dol 0.3.65 · i2 0.1.67.

**Absent, and relevant.** `whisperx` · `pyannote.audio` · `speechbrain` · `madmom` (excluded
on licence, not by accident) · `essentia` · `aubio` · `msaf` · `ctc-forced-aligner` ·
`montreal-forced-aligner` · `aeneas` · `openl3` · `panns-inference` · `ruptures` · `stumpy` ·
`tslearn` · `fastdtw` · `silero-vad` · `webrtcvad` · `scenedetect` · `hmmlearn`.

Three consequences worth carrying forward:

- **`torchaudio` 2.9.0 is present.** Its forced-alignment API is the cheapest route to real
  CTC alignment without adding `whisperx` — the one thing `muvid`'s own reference doc
  (`t/muvid/misc/docs/alignment_references.md`, plus a saved WhisperX DeepWiki dump and the
  STARS paper) already identifies as the upgrade path. Verify the API against docs; I did not
  run it.
- **`dtaidistance` is present** and is already the fleet's DTW (`kodokan.compare`). No new
  DTW dependency is needed for the first three solvers.
- **`ruptures` / `stumpy` are absent**, so change-point detection and motif discovery would
  each be a new dependency. `mixing`'s Foote self-similarity plus `kodokan`'s
  autocorrelation period cover most of what the POC needed without either.

Two environment hazards observed while probing **[verified]**: importing `basic_pitch` prints
CoreML/TFLite warnings, and `av` + `cv2` ship duplicate `libavdevice` dylibs (objc warns
"may cause spurious casting failures and mysterious crashes"). Neither blocked anything here,
but a video decode path that touches both is worth pinning to one.

---

## 7. Open questions

1. **Is `kodokan` alive?** Tip 2026-07-16, the oldest of the relevant repos, but it holds the
   entire gesture branch (pose, tracking, hysteresis segmentation, periodicity, DTW) and it
   built the POC's clips. Depend on it, or lift `pose.py`/`segment.py`/`compare.py`? That is
   the user's call, and it is the single biggest scope fork in the design.
2. **Which ASR seam?** Three exist: `scribed` (right shape, 11 backends, but 9 commits and 3
   test files), `mixing.transcript` (Scribe-only, network, but cached and battle-used),
   `an.audio.WhisperLipSync` (faster-whisper, local). Committing to `scribed` also means
   accepting responsibility for hardening it.
3. **Extract `_viterbi`, or reimplement?** Extraction gives a reviewed, feasibility-classifying
   solver and forces a `muvid` change in the same PR. Reimplementation is cleaner and risks
   the fleet carrying two DPs. The precedent (`mixing.audio` shared by `muvid` and others)
   says extract.
4. **What is the artifact–span cardinality?** The POC was 1:1, ordered, non-overlapping. Do we
   commit to that in v1 (which makes the DP trivial and the API honest), or admit 1:N (an
   artifact recurs), N:1 (several artifacts on one span), and overlap from the start? This
   decision propagates into the body schema and is expensive to change after.
5. **Reuse `clip-alignment/v1` or mint a new body schema?** `muvid.footage.lacing_bridge`
   already publishes it, and `lacing`'s schema registry has migrations. Reuse costs a
   compatibility constraint; a fresh URI costs a second thing readers must learn.
6. **Where does the sub-bass ratio land?** My recommendation is upstream, as a fifth
   `mixing.audio.segmentation._STRATEGIES` entry — but that makes `mixing` a hard dependency
   of the POC's most valuable single feature. Acceptable?
7. **Does the "auto" agent live in the package, or above it?** The brief says the highest
   surface is an agent. If the agent is `falaw`/LLM-backed it drags a heavier tail than the
   solvers do; a rule-based `"auto"` (match `consumes` against available inputs, cheapest
   first) may cover most cases and keeps the package's deps honest. Worth deciding before the
   first commit, since it determines whether the catalog fields are advisory or load-bearing.
8. **Downbeats.** `BeatGrid.downbeat_times` is a reserved empty array with no backend, and
   the POC needed *phase*, not just tempo. Beat-This / BeatNet would fill it; both need a
   licence check that `mixing`'s madmom exclusion suggests will not be trivial.
9. **Do we own "does this alignment survive an edit"?** `mixing.transcript.formats.remap_time_after_cuts`
   is the only time-remapping code in the fleet. If aligned artifacts must follow the media
   through cuts, that belongs somewhere — and it is not obviously here.
