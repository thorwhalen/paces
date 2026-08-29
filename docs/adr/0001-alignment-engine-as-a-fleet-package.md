# ADR-0001 — An alignment engine as its own tool in the reelee fleet

- **Status:** **Proposed — intent to develop.** This records a direction so the next agent
  designs *around* it instead of quietly re-implementing a piece of it.
  **Correction, after the survey:** this is not greenfield. `muvid/align.py` is already an
  aligner registry with dispatch, a `requires` preflight, frozen result dataclasses and a
  `lacing` writeback — the v0, with only its input type hardcoded. The work is *generalising
  that*, not writing a new one. See "What already exists" below.
- **Date:** 2026-08-28
- **Deciders:** thorwhalen (raised it), recorded during the `stepped` POC handoff
- **Supersedes / superseded by:** —
- **Scope note:** this ADR belongs to the fleet, not to `stepped`. It lives here because
  `stepped` is where the need surfaced. **When the package is created, move this file into
  it** (or into `reelee/docs/`) and leave a pointer behind.

---

## Context

### The recurring task

Across reelee / `video_gen` work, one problem keeps reappearing in different costumes:

> Given some **artifacts** — annotations, steps, script lines, chapters, storyboard beats,
> notes, images — and some **media** (audio and/or video), determine **which span of the media
> each artifact corresponds to.**

In the user's words:

> *"This is a very common task in our reelee work: being able to match and align things. More
> specifically (and frequently in reelee), being able to align annotations/artifacts to
> segments of audio and/or video."*

It is the same problem whether you are placing storyboard panels against a voice-over, finding
where a script line was actually said in a take, locating the nine blocks of a dance routine in
a ten-minute video, or attaching a chapter list to a podcast. Today each of those gets solved
ad hoc, in the project that needs it, and the solution is thrown away.

### What the POC established empirically

The `stepped` POC (see `../01-what-was-built.md`, `../02-technical-recipes.md`) solved one
instance of this without any single dedicated technique. What actually carried the work:

| signal used | contribution |
|---|---|
| sub-bass energy ratio per second | split talk / silence / music+dance / spoken breakdown — the highest value-per-line of the session |
| beat tracking (`librosa`) | the grid spacing: 129.2 bpm → 3.715 s per 8-count |
| a **visible periodic landmark** | the grid's *phase*, which tempo alone cannot give |
| a duration sanity check | caught a factual error in the source document |
| ASR over the spoken half | named the steps, in the teacher's own words |
| an LLM reading timestamped contact sheets | the final editorial call on which seconds show the move |
| the **order prior** (steps are sequential, non-overlapping) | caught two blocks assigned the same move |

Three things fall out of that list and they are the real motivation for this ADR:

1. **No single method was sufficient, and none was even close.** The answer came from
   combining a cheap audio feature, a rhythm model, a text model, a vision-language judgement
   and a structural prior.
2. **The cheapest signal did the most work.** A five-line numpy feature beat everything
   fancier. Any design that reaches for the heavy method first will be slow and worse.
3. **Nothing used pose or gesture detection at all** — the user's own guess about how it worked
   was wrong. That gap is real and is one of the things the research is closing.

### What already exists (surveyed 2026-08-28 — `../alignment/00-existing-in-fleet.md`)

The capability does not exist *as a capability*, but nearly every part of it does, scattered
across two application packages and one toolbox. The survey's own summary: *"the capability
does not exist as a capability, but every one of its parts exists, and three of them are
excellent."*

| what | where | verdict |
|---|---|---|
| **Aligner registry + dispatch** — `register_aligner`, `list_aligners`, `aligner_info`, a `requires` preflight, frozen result dataclasses, `write_alignment_store` → `lacing.SqliteStore` | `t/muvid/muvid/align.py` (624 L) | **The v0.** Its only flaw is that `LyricsDoc` is baked into the signature. Generalise it and have `muvid` import it back — do not write a second one. |
| **Order-prior solver** — a beat-snapped semi-Markov Viterbi DP with `[L_min, L_max]` length constraints, a Potts switch penalty, and infeasibility *classification* with a documented relaxation ladder | `t/muvid/muvid/footage/select_score.py` | **The exact algorithm the order prior needs**, currently aimed at the dual problem (choose shots for a timeline rather than place artifacts on one). |
| **Evidence fusion substrate** — `ScoreTrack` / `ScoreTensor`: many heterogeneous curves resampled onto one media clock, with coverage masks, robust normalisation and a staleness fingerprint | `t/muvid/muvid/footage/scoring/grid.py` | Exactly what multi-method fusion needs. |
| **Audio signal layer** — `find_audio_offset` (cross-correlation, with confidence), `find_segments(strategy=…)` incl. `speech_music`, `beat_grid → BeatGrid` (downbeat field reserved; `madmom` deliberately excluded on licence grounds) | `t/mixing/mixing/audio/` | **Take as-is, do not move.** Best-documented alignment code in the fleet. |
| **Pose / gesture front-end** — `estimate_poses` (RTMPose or YOLO11-pose, `device="mps"`), tracked variant, motion-energy segmentation with hysteresis, `estimate_period` (autocorrelation), joint-angle DTW via `dtaidistance` | `t/kodokan/kodokan/{pose,track,segment,compare}.py` | **Built, tested, Apple-Silicon-native — and dormant.** Never pointed at an alignment problem. The "gesture gap" is *wiring*, not research. `estimate_period` automates exactly the visual-landmark trick the POC did by eye. |
| **Motion ↔ beat scoring** | `t/muvid/muvid/footage/scoring/motionbeat.py` | The fleet already aligns visual motion to audio time — with motion energy, not pose. |
| **Output substrate + quality metrics** — rational-time intervals, Allen relations, PROV-O provenance, and `quality.py`'s `boundary_iou` / `interval_iou` / `cohen_kappa` / `krippendorff_alpha` | `t/lacing` | Settled. It already ships the metrics an aligner must be judged by. |
| **ASR seam** | `t/scribed` (11 backends, young), `mixing.transcript`, `an.audio` | Three parallel entry points exist; pick one seam rather than adding a fourth. |
| A written **literature review** of alignment methods | `t/muvid/misc/docs/alignment_references.md` | Already done. Read it before researching. |

**The genuine gaps**, in the survey's judgement: a constrained order-prior solver stated for
*this* problem; the sub-bass-ratio feature (belongs in `mixing` as a fifth strategy, not in a
new package); the duration sanity check (five lines of arithmetic, nothing does it);
LLM-over-contact-sheets; and true forced alignment (`muvid.align` does greedy token matching
against an already-timed transcript, and its `stars` slot is a deliberate `NotImplementedError`).

### Why this is not just "a function in `stepped`"

The alignment problem is *upstream* of `stepped` and *wider* than it. `stepped` is one
consumer. If the capability lives inside `stepped`, then the next project that needs it either
depends on a step-guide library for an unrelated reason, or copies the code.

There is also a dependency argument, and it cuts the other way from the obvious answer. A good
alignment engine wants optional access to heavy things — torch, madmom, pyannote, CLIP,
mediapipe. Those must not become a transitive dependency of whatever package owns the fleet's
lightweight interval and annotation types. See "Open questions" §1: the boundary between the
*type* layer and the *engine* layer is the thing still to settle.

## Decision

**Intent: develop a dedicated alignment tool for the `video_gen` fleet.** Its job is to map
artifacts onto media spans, and nothing else.

The shape it is intended to have — a proposal for the designing agent to argue with, not a
specification:

```
   artifacts ──┐
               ├──►  probe   ──►  plan  ──►  run  ──►  reconcile  ──►  Alignment
   media    ───┘   (cheap      (choose    (extract     (fuse +
                    profile)    methods)   signals,     resolve
                                           score)       with priors)
```

Four layers, from the bottom:

1. **Signal extractors** — turn media into time series or event sets: audio features, beats and
   downbeats, VAD, ASR with word times, scene cuts, motion energy, pose keypoints, frame
   embeddings, OCR. Each declares what it *requires* and what it *produces*.
2. **Scorers** — turn (artifact, media) into evidence: a similarity-over-time curve, a candidate
   boundary set, a hard span with a confidence.
3. **Alignment algorithms** — turn evidence plus **structural priors** into a globally
   consistent answer. The order prior is the strongest one available and deserves first-class
   support: monotonic DTW, gapped Needleman–Wunsch, CTC segmentation, Viterbi, and
   change-point detection with a *known* number of segments. Grid fitting — solving for
   `(offset, period)` when the domain has a regular unit — is its own primitive; the POC did it
   by hand and it should be a function.
4. **The planner** — the top surface, and the user's own framing of it:

   > *"the highest surface would be an agent that can study the context, what is available, and
   > have a list of possible methods/algorithms/tools it could use. It could use beats. It could
   > use the transcribed words (and transcribe if they're not available). It could use some
   > knowledge of the order of the artifacts to be matched. It could use gestures."*

   For this to be an *agent* rather than a hard-coded pipeline, every method must **declare its
   requirements and products** in a machine-readable way, so the planner reasons over a
   capability table instead of a chain of `if` statements. That declaration format is the
   load-bearing design decision of the whole package.

   The research (`../alignment/06-the-planner-surface.md`) proposes something sharper and
   cheaper than "an agent", and it is worth taking seriously: collapse the five sibling method
   Protocols into **one `Capability(needs, gives, …)` record** — they differ only in what they
   return — which turns planning into backward chaining over a graph of fewer than 30 nodes.
   It measured a context probe at **~1.4 s per minute of media** (flat for long media via
   sampled windows), separating content genres by 20× on a single feature, and argues for a
   deterministic ranked graph walk with **the LLM outside the control loop entirely**. If that
   holds, v1's "planner agent" is ~150 lines of ordinary Python, and the agent's job is to
   *read the plan and the confidences*, not to choose the methods. Test that claim before
   building anything fancier.

Two principles that follow from the POC and should be treated as constraints:

- **Cheap first, escalate on low confidence.** Probing must cost seconds. The expensive methods
  (LLM-over-frames, CLIP-per-frame, pose) run only where the cheap ones were unsure.
- **Every method returns a confidence**, or the fusion layer and the escalation loop cannot
  exist.

### Research already done

Filed under `../alignment/`, one file per family, prepared so the designing agent does not
start from a literature search:

| file | family |
|---|---|
| `00-existing-in-fleet.md` | what the fleet already has, and whether this should be its own package |
| `01-text-to-audio-alignment.md` | ASR word times, forced alignment, fuzzy paraphrase→transcript matching, VAD, diarization |
| `02-music-rhythm-and-structure.md` | beats, downbeats, tempo, phase, music structure, music-vs-speech, audio-to-audio |
| `03-visual-signals.md` | scene cuts, motion energy, **pose and gesture**, repetition detection, OCR |
| `04-semantic-and-llm-matching.md` | CLIP/CLAP embeddings, the contact-sheet LLM pattern, transcript structure extraction |
| `05-sequence-alignment-algorithms.md` | DTW, gapped alignment, CTC-seg, Viterbi, change-point, grid fitting, fusion, evaluation |
| `06-the-planner-surface.md` | the capability model, context probing, selection, escalation, the Python + agent API |

## Consequences

**Good**

- One place where "how do I find where this thing happens in this video" is solved, tested and
  improved. Every fleet project benefits from an improvement to any method.
- The capability declarations make the method set *extensible by an agent* rather than by a
  refactor — adding a new scorer is data, not control flow.
- Alignment becomes **testable**, which it currently is not. Synthetic media with known ground
  truth is cheap to generate and makes regression testing possible.
- `stepped` shrinks to what it is actually about: step semantics and rendering.

**Costs and risks**

- Another package in an already large fleet. The boundary question below must be answered
  before any code, or this becomes a second `lacing` rather than a layer above it.
- A real risk of over-engineering a framework before there are three genuine consumers. The
  honest mitigation: build it *from* `stepped`'s needs, extract only what a second consumer
  actually asks for, and keep the v1 method set small and cheap.
- Heavy optional dependencies need real discipline — extras, lazy imports, and a default path
  that needs nothing beyond numpy/scipy/librosa/ffmpeg.

**Neutral**

- Existing ad-hoc alignment code stays where it is until a consumer wants to move.

## Alternatives considered

| alternative | why not (yet) |
|---|---|
| **A module inside `lacing`** | Argued at length in `../alignment/00-existing-in-fleet.md §4.3`, which calls the case against **decisive**. `lacing`'s runtime deps today are four featherweights (`pydantic`, `intervaltree`, `argh`, `dol`) and it is the substrate `nw`, `muvid`, `artful`, `braidio`, `walkthru` and `reelee` all sit on. An honest alignment engine wants numpy, scipy, librosa, ffmpeg, torch/torchaudio, ultralytics/rtmlib/mediapipe, onnxruntime. Extras hide that from `pip install` but not from `lacing`'s pyproject, CI matrix, licence surface, or the next reader trying to understand what `lacing` *is*. The counter-argument is real — `lacing` already has a processor registry, the quality metrics, and all three surfaces (CLI/HTTP/MCP) — so read §4.3 before overturning it. |
| **Leave it in `stepped`** | Makes every future consumer depend on a step-guide library for an unrelated capability. |
| **One vendored third-party aligner** (e.g. WhisperX for everything) | Solves exactly one family — text↔audio. The POC's evidence is that no single family is enough. |
| **Do nothing; solve it per project** | The status quo. Works, and loses the improvement every time. |

## First moves, if this is approved

In the order the survey implies — note that none of them start with a blank file.

1. **Generalise `muvid/align.py`.** Lift the registry, the `requires` preflight, the result
   dataclasses and the `lacing` writeback out of `muvid`; replace `LyricsDoc` in the signature
   with a general artifact-sequence type; have `muvid` depend on the result. This alone is most
   of the package's skeleton.
2. **Wire the two dormant halves together.** `kodokan`'s pose front-end and `estimate_period`
   have never been pointed at a media clock. That is the "gesture gap" the user asked about,
   and the survey judges it wiring rather than research.
3. **Restate `select_score`'s DP for the primal problem** — N ordered non-overlapping artifacts
   onto a timeline, maximising evidence — rather than for shot selection.
4. **Push the two cheap wins upstream to `mixing`**: the sub-bass ratio as a fifth
   `find_segments` strategy, and the duration sanity check.
5. **Read `t/muvid/misc/docs/alignment_references.md` first.** The literature review is written.

## Open questions

1. **Package or module?** The survey argues *separate package* and calls the case decisive
   (see Alternatives). The residual question is narrower: which of `muvid`'s pieces move out,
   and does `muvid` then import them back or keep private copies? **Decide with the user
   before writing code** — this is the expensive-to-move decision.
2. **What does it return?** An `Alignment` type with per-artifact spans, confidences and
   provenance. Whose types are those — `lacing`'s intervals, or new ones? See
   `../07-annotation-model.md`.
3. **Where does the planner live?** A Python function with a rule table, an LLM-driven agent, or
   both behind one seam. `../alignment/06-the-planner-surface.md` argues the smallest thing that
   works is a rule table for v1.
4. **How are human corrections fed back?** As constraints for a re-run, not as a patch on the
   output — otherwise re-running the analyser destroys them. This is the same constraint as
   `../03-design-brief.md §5.5`.
5. **The name**, if it becomes its own package. Not investigated.
6. **Does the fleet's existing `nw.Transform` contract already give the plan→execute staging**
   this needs, so the planner is an `nw` genre rather than new machinery? Flagged by the reelee
   research (`../04-reelee-core.md`) and worth checking early.
