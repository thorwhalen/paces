# 09 — Subgenre candidates: what to build after dance, and what each one would force

*What this file is for: the POC's subgenre is dance choreography, and dance is a
**conveniently easy** case — one body, a metronomic grid, a total order, every step visual,
nothing consumed or produced. If the second subgenre is also a body-in-a-room case, the core
learns nothing and the "genre / subgenre" split will be decoration. This file enumerates 16
candidate subgenres, states for each what the core cannot do generically, and closes with a
concrete recommendation for subgenres #2 and #3 plus the list of things dance is currently
letting you fudge. Read `07-annotation-model.md` first — everything below is written against
that document's proposed `StepDocument` field names.*

---

## 0. Vocabulary, and what a "subgenre" is in this codebase

Do not invent a word. Per `04-reelee-core.md` §3 (reported verified there; I did not re-run
it), the fleet already has the two levels:

| level | fleet type | where | this project |
|---|---|---|---|
| genre | `nw.Genre` (frozen dataclass, `$PP/t/nw/nw/genres.py`) | one-file registration from *your* package | `step_by_step` |
| **subgenre** | **`nw.Template`** (`slug`, `title`, `description`, `params`) | `Genre.templates` | `dance_moves`, `judo_throw`, `recipe`, … |

`Template.params` is **opaque to nw** — the owning package validates and interprets it. So a
subgenre is, mechanically, *a params dict plus the code that reads it*. That code is exactly
the set of seams from `03-design-brief.md` §6 bound to different implementations. Which means
**"what does this subgenre require?" == "which seam does it re-bind, and does that seam exist
yet?"** That is the question this file answers per candidate.

`muvid.genre_music_video.MUSIC_VIDEO` registers a genre with **zero** nw Transforms and is
still a first-class catalog citizen — so a `step_by_step` genre carrying its own pipeline is a
supported shape, not a fight with the substrate. [reported verified in `04-reelee-core.md`]

### The seven-slot specialisation surface

Every candidate below is described against the same seven slots. If a subgenre needs nothing
outside these, the core generalises. If it needs an eighth thing, that is a **core-forcing**
requirement and is flagged **⚠**.

| # | slot | `StepDocument` field / seam | dance's binding |
|---|---|---|---|
| 1 | **step delimiter** — what ends a step | (semantics of `Step`) | a fixed number of 8-counts |
| 2 | **segmentation signal** — how a machine finds it | `segmenter=` | notes-as-prior + beat grid + LLM on contact sheets |
| 3 | **duration unit** | `Measure.unit` + `MetricGrid` | `"eight"`, grid = 129 bpm / 8 subdivisions / origin 51.2 s |
| 4 | **span roles** — the passes over the material | `SourceSpan.role` | `performance` (at-tempo) / `instruction` (slow demo) |
| 5 | **subject + privacy** | `subject_locator=`, `stylizer=` | YOLO11s person box; cv2 stylize + narrowed head band |
| 6 | **per-step payload** — what the learner looks at | `ArtifactRef.role` | a 2.5–6 s auto-cropped looping clip |
| 7 | **renderer / transport** — how the guide is "played" | `renderer=` | one page, 8-count metronome at measured tempo |

### The segmentation-signal taxonomy (this is the `segmenter=` vocabulary)

Nine signals cover all 16 candidates. Naming them now is worth more than any single subgenre,
because `segmenter=` should be a registry keyed on these, not an if-chain.

| key | signal | needs | subgenres |
|---|---|---|---|
| `metric` | beat / bar / score grid | `mixing.audio.beats.beat_grid` **[exists]** | dance, music, some fitness |
| `motion` | motion-energy bursts with rest boundaries | `kodokan.segment.find_segments` **[exists]** | kata, sports, juggling, skate |
| `speech` | imperative verbs / discourse markers in the transcript | `mixing.chapters.detect_chapters` (LLM) **[exists]** | recipe, makeup, first aid, lab |
| `cut` | shot changes in an edited video | **nothing in the fleet** — see §1.1 | recipe, makeup, craft, hair |
| `state` | the artefact being built visibly changed | nothing; needs a visual-diff pass | craft, repair, calligraphy, assembly |
| `object` | which tool/ingredient is in hand changed | nothing wired; `mediapipe` installed | cooking, repair, makeup, lab |
| `ui` | UI/terminal events, OCR of on-screen text | `pytesseract` installed; `walkthru` owns the doc model | screencasts |
| `period` | repetition counting / self-similarity | `kodokan.segment.self_similarity_matrix` + `estimate_period` **[exists]** | workout, physio, juggling |
| `prior` | align a notes document to the timeline | `muvid.align.align_lyrics` + `register_aligner`; `braidio.sources.TimedLineSegmentSource` **[exists]** | **all of them** — and the only one the POC actually used |

### 1.1 The one cheap capability that is missing, and unblocks six subgenres

**Verified by running it on this machine:** `ffmpeg` at `/opt/homebrew/bin/ffmpeg` ships
`scdet` ("Detect video scene change", `threshold` default 10), plus `freezedetect`,
`blackdetect`, `silencedetect` and `thumbnail`. **Verified** in the `p12` env
(`~/.pyenv/versions/3.12.12/envs/p12/bin/python`): `scenedetect` is **not installed**;
`madmom`, `easyocr`, `paddleocr` are **not installed**; `mediapipe`, `rtmlib`, `ultralytics`,
`onnxruntime`, `insightface`, `supervision`, `pytesseract`, `torch`, `transformers`,
`dtaidistance`, `librosa`, `mlx_whisper`, `cv2`, `skimage` **are**.

Nothing in the fleet does shot-cut detection (`05-fleet-inventory.md` §7 lists five
segmenters, none of them visual-cut). Yet **every professionally edited YouTube tutorial —
cooking, makeup, craft, repair — is already segmented by its editor**, and the cut list is the
single highest-precision prior available for those subgenres. A `segmenter="cut"` built on
`ffmpeg -vf scdet` costs no new dependency and serves cooking, makeup/hair, knitting,
woodworking, assembly and lab protocols at once. `freezedetect` is the companion signal for
craft ("the camera holds on the finished stitch"). **Build this before the second subgenre.**
[inferred: I did not run `scdet` on a real video this session — only confirmed the filter and
its options exist.]

---

## 1. The master table

Difficulty and Value are 1–5. **Difficulty** = engineering distance from the dance POC (5 =
needs a capability nobody in the fleet has). **Value** = size of the audience × how much the
output beats what a person could make by hand in an afternoon.

| # | subgenre | typical source | step delimiter | signal(s) | duration unit | payload | transport | D | V | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **Martial arts form / throw** | 1–4 min official demo, fixed camera, 3–6 repeats of *one* technique | one demonstration (a whole throw) | `motion` + `period` | reps; "kuzushi/tsukuri/kake" phases | slow-mo clip + skeleton overlay | none; scrub + quiz | **2** | 4 | **roadmap now (#2)** |
| 2 | **Cooking recipe** | 5–20 min edited YouTube, hands + counter, voice-over | one instruction ("fold in the flour") | `speech` + `cut` + `object` | minutes / "until golden" | still or 3 s clip; often *text only* | per-step timers, checklist | **4** | 5 | **roadmap now (#3)** |
| 3 | **Software screencast / tool tutorial** | 5–40 min screen recording, no body at all | one command / one file save | `ui` + OCR + `speech` | none (keystrokes) | code diff, cropped screen region | stepper, copy-button | **3** | 5 | **later — but see `walkthru` first (§2.3)** |
| 4 | **Yoga / pilates / mobility flow** | 10–60 min single take, one body, fixed camera | one asana or one transition | `prior` + `speech` + `motion` | breaths; seconds held | loop clip (same as dance) | paced transport, breath cue | **2** | 4 | **roadmap later — cheap, but teaches the core little** |
| 5 | **Physio / rehab protocol** | 30–120 s per exercise, clinician-filmed, often unlisted | one exercise | `prior` + `period` | reps × sets × frequency/week | loop clip + form cue | daily-plan checklist, adherence log | 3 | 4 | later |
| 6 | **Craft: knitting / crochet** | 10–30 min top-down hands, edited | one stitch pattern / one row | `state` + `cut` + `speech` | rows / stitches | close-up loop **plus a chart** | row counter | **4** | 4 | later |
| 7 | **Luthiery / woodworking / repair** | 15 min–2 h, multi-session, tool close-ups | one operation on the workpiece | `state` + `object` + `cut` | "until fits"; grit; passes | before/after still pair | checklist + BOM | **5** | 3 | later |
| 8 | **Assembly (IKEA-style, kits)** | 3–20 min, static overhead, often no speech | one part joined | `state` + `object` | parts / fasteners | before/after still + part callout | DAG stepper | **5** | 3 | later |
| 9 | **Makeup & hair** | 10–20 min edited, face fills frame | one product / one tool | `cut` + `object` + `speech` | strokes; "blend until…" | close-up loop | product list, before/after | 3 | 3 | later |
| 10 | **Musical instrument technique** | 5–20 min, hands + instrument, split screen | one bar / one exercise | `metric` (score-following) + `prior` | bars / beats at tempo N | loop clip + tab/notation | metronome with tempo ramp | **4** | 4 | later — closest cousin to dance |
| 11 | **Sports technique (golf, climbing beta)** | 30 s–5 min, multi-angle, slow-mo | one phase of one motion | `motion` + `period` | phases; "positions" | slow-mo loop + overlay lines | phase scrubber, A/B vs self | 3 | 3 | later |
| 12 | **Sign language** | phrase-level clips or continuous signing | one sign / one clause | `motion` (hand lowering, pauses) | signs / glosses | tight hand+face loop | gloss ↔ video quiz | **5** | 3 | never *as a fluency product*; maybe as a phrase-book |
| 13 | **Juggling / skate tricks** | 10–60 s phone clips, self-filmed | one trick attempt | `period` + `motion` | catches / revolutions | slow-mo loop | trick tree (prereqs) | 3 | 2 | later / hobby |
| 14 | **Calligraphy / drawing** | 3–15 min overhead, hands + paper, often silent | one stroke / one letter | `state` + `freezedetect` | strokes | loop clip + stroke-order overlay | stroke-order animation | 3 | 3 | later |
| 15 | **First aid / safety drill** | 2–10 min, scripted, institutional | one action in a protocol | `speech` + `prior` | steps; "30 compressions" | clip + warning card | timed drill, pass/fail | 3 | 3 | **never without a domain owner** — liability |
| 16 | **Lab / wet-bench protocol** | 5–30 min, bench-top, narrated | one pipetting/incubation op | `speech` + `object` + `cut` | volumes / minutes / °C | still + reagent callout | protocol checklist + timers | 4 | 3 | never (v1); the notes are already better than the video |

---

## 2. The serious candidates

### 2.1 Martial arts form / throw — **build this second**

**Content.** The user already has the corpus: the official *Kodokan 100 Techniques* YouTube
playlist, ingested by `kodokan.acquire.download_techniques(playlist_items=…)`. One video per
technique, 1–4 minutes, fixed camera, tatami, two people in white. Each video shows the *same*
throw 3–6 times, varying speed and angle, with a low-motion reset (walk back, re-grip, bow)
between demonstrations.

**This inverts the POC's source topology, and that is the point.** Dance was *one video, many
steps*. Judo is *one video, one step, many spans* — and *many videos, one document*. The
`StepDocument` already has the right shape for this (`Step.spans: list[SourceSpan]`,
`StepDocument.sources: list[Source]`) but it has never been exercised that way. If the schema
survives judo, `sources`/`spans` are real; if it doesn't, better to learn it at subgenre #2
than #5.

**Step unit and delimiter.** The step is *one whole technique* (a named throw), and its spans
are its demonstrations. Within a step there is a canonical three-phase decomposition every
judoka knows — **kuzushi** (off-balance) / **tsukuri** (entry) / **kake** (execution) — which
is exactly `Step.steps` (recursive sub-steps) with `duration` in a unit that has **no metric
grid at all**.

**Segmentation signal — already written, verified by reading the source.**
`$PP/t/kodokan/kodokan/segment.py`:

```python
def segment_demonstrations(seq, min_two_person_frac=0.3) -> list[Segment]
# Segment(index, start_s, end_s, start_frame, end_frame, peak_activity, two_person_frac)
```

Its module docstring states the design directly: *"Scene-cut detection finds nothing in a
continuous take, so we segment by **rhythm**: build a 1-D motion-energy signal and take the
high-motion runs as demonstrations."* Three robustness pieces are already implemented —
hysteresis thresholding (so slow-motion reps don't split), a **two-person gate**
(`min_two_person_frac`), and a self-similarity-matrix + autocorrelation period cross-check
(`self_similarity_matrix`, `estimate_period`) which the docstring calls "RepNet-style". Energy
sources are fusable: `pose_motion_energy(pose_seq, conf_thresh=0.2)` (pose-only) and
`optical_flow_energy(...)` (pose-free, dense Farneback).

That is `segmenter="motion"` **already built and dataset-validated** (10 techniques ·
84 demonstrations · 18.3k frames, per the kodokan README).

**Duration unit.** `Measure(value="1", unit="demonstration")`, or `unit="phase"` for
sub-steps. **`MetricGrid` is `None`.** Dance's page cannot render without a tempo; the judo
page must render without one. That single fact is the cheapest possible test that
`MetricGrid | None` is honoured all the way through `resolve()` and into the renderer.

**Span roles.** Dance's `performance` / `instruction` become `full_speed` / `slow_motion` /
`alternate_angle`. **Same idea, different vocabulary → confirms `role` should stay an open
`Slug`, not an enum.**

**Subject + privacy.** ⚠ **Two people, with roles.** `kodokan.track.estimate_poses_tracked`
gives "stable tori/uke identity (BoT-SORT + spatial continuity)". The POC's crop envelope,
face-slot logic and privacy band all assume one subject and all break here
(`02-technical-recipes.md` §"Everything here assumes one subject"). Privacy is *not* needed —
the source is an official public instructional playlist — which is itself useful: it proves
`stylizer=identity` is the right default.

**Payload and renderer.** Slow-motion loop, optionally with the skeleton drawn on
(`kodokan.viz.render_skeleton_video(seq, out_path=…, source_video=…)`, or
`blank_canvas=True` for a pure-skeleton anonymised variant — a *second, free* privacy
strategy the dance POC didn't have).

The renderer is where judo pays for itself twice: **`kodokan.flashcards` +
`kodokan.learning` already exist** and are UI-agnostic by design.
`flashcards.make_problem(...)` builds `name_to_video` / `video_to_name` multiple-choice
problems with *confusable* distractors; `learning.py` ships five swappable spaced-repetition
strategies (`UniformRandom`, `Leitner`, `SM2`, `ConfusionWeighted`, `FSRSLite`) behind
`make_strategy(key, **params)` / `list_strategies()`, reconstructing per-item state by
replaying a flat response history (no mutable server state). **This is a second renderer over
the same AST, already written, in a different modality (quiz, not guide).** Nothing would
prove the parse/render split harder.

**Honest warning, from the kodokan README's own "Status & honest limits":** technique
*recognition* does not work — "every 2D descriptor *and* MediaPipe 3D joint angles sit at
chance (separation AUC ≈ 0.49–0.56)". Do not scope anything that needs the machine to *name*
a throw from pixels. Naming comes from the playlist metadata / notes prior. Segmentation,
comparison (`kodokan.compare`, joint-angle soft-DTW, speed-invariant) and scoring against a
*known* reference all work.

**Also note kodokan is dormant** — last commit 2026-07-16 per `05-fleet-inventory.md` §8 — and
its heavy deps are optional extras (`pip install -e '.[all]'`), data lives outside the repo at
`~/kodokan_data` (`KODOKAN_DATA_DIR`).

**Verdict: roadmap now, as subgenre #2.** Highest ratio of "core lessons learned" to "code
written" of anything on this list, because ~70 % of the analysis and a whole second renderer
already exist as tested code.

---

### 2.2 Cooking recipe — **build this third, and expect it to reshape the document**

**Content.** 5–20 minutes, edited, hands-and-counter framing with occasional face-to-camera,
voice-over or on-screen text, often no continuous take at all. Filmed by the creator for an
audience, which means it is already cut into shots that *approximately* correspond to steps.
Public corpora are enormous (`YouCook2`, `RecipeQA`); the public benchmark that matters is
**COIN** — 11,827 videos, 180 tasks in 12 domains, 46,354 annotated segments, **3.91 step
segments per video averaging 14.91 s**, 778 unique step labels
([COIN, CVPR 2019](https://arxiv.org/abs/1903.02874)). Two numbers to internalise from that:
real-world instructional videos have **very few steps** (≈4, not the dance POC's 9) and each
step is **~15 s**, not 3.7 s. Design the renderer for a short list of chunky steps.

**Step delimiter.** One spoken imperative over one continuous action: *"fold the flour in
three additions"*. Not a duration, not a beat — a **verb applied to an ingredient with a
tool**.

**Segmentation signal.** Three cheap ones stack, and they agree often enough to cross-check:
`cut` (the editor already cut where you want to cut — §1.1), `speech` (imperative verbs in the
ASR transcript; `mixing.chapters.detect_chapters(transcript, segment_fn=…)` is the existing
LLM-backed shape), and `object` (which tool/ingredient is in hand). The POC's own `prior`
signal is *stronger here than anywhere else*, because the notes document is usually a
**structured** recipe (schema.org/Recipe JSON-LD is on most recipe pages) rather than free
prose. ⚠ **That means "parse the notes" becomes a domain parser with a real schema, not an LLM
read** — a code path the dance case never needed.

**Duration unit.** ⚠ **Two units at once, and one of them is not a duration.**
`Measure(value="8", unit="minute")` coexists with a *termination condition*: "until golden",
"until it pulls away from the side". A recipe step's length is `min(clock, condition)`. The
proposed `Measure` cannot express "until X" at all. Options: a `Measure` subtype with
`until: str | None`, or `Step.attrs["termination"]`. Either way, **this is the first candidate
that breaks `Measure`.**

Also ⚠ **steps run in parallel** (the oven preheats while you chop) and some are **optional**
or **conditional** ("if using fresh yeast…"). `Step.optional` exists; parallel does not. A
recipe is a partial order.

**Span roles.** Weak. There is rarely a "run-through then breakdown" structure — the video *is*
the breakdown. Roles become `demonstration` / `result` / `b_roll`. ⚠ **Many steps have no
usable span at all** (the video cuts away; "let it rest overnight" has no footage). The
document must tolerate `Step.spans == []` and the renderer must render such a step gracefully.
Dance's nine-out-of-nine coverage hid this.

**Subject + privacy.** No body to track. `subject_locator=` binds to **hands + workpiece**, or
to nothing (`subject_locator=None` → fixed crop, or `burns.content.salient_box` on a
representative frame). Privacy is a non-issue. **This is what proves `subject_locator=` is a
seam and not a euphemism for "find the person".**

**⚠ The core-forcing requirement: a resource track.** A recipe has an **ingredient list with
quantities** and a **tool list**, both of which are (a) top-level document content, (b)
referenced *by* steps, (c) scalable (×2 servings), and (d) the thing the user actually prints.
There is no slot for this in the proposed `StepDocument`. Nor is there one for the *state of
the artefact* ("the dough is now shaggy"). This generalises: knitting has yarn+needles,
woodworking has a cut list and a bill of materials, assembly has a parts inventory, lab has
reagents. **Adding a `resources: list[Resource]` track with `Step`-level references is the
single largest schema change any subgenre on this list demands, and five subgenres demand it.**

**Rendering.** Almost nothing survives from the dance page. No metronome — a recipe has no
tempo. Instead: a **scalable ingredient list**, a **checklist with per-step countdown timers**
(the ones that map to `unit="minute"`), a **prep/cook split**, "mise en place" as a derived
view, and a print/kitchen mode with big type and no video autoplay. The per-step visual is
often a *still*, and often optional. Deep links into the source still matter.

**Verdict: roadmap now, as subgenre #3.** Not because it is easy — it is the hardest of the
three recommendations — but because it is the only candidate that attacks the *document* while
judo attacks the *analysis*. It is also the one with an audience larger than everything else on
this list combined.

---

### 2.3 Software screencast / tool tutorial — high value, but check `walkthru` before writing a line

**Content.** A screen recording, 5–40 minutes, voice-over, no body. The "camera" is a
framebuffer; the subject is text.

**Step delimiter.** A command executed, a file saved, a build run, a navigation. Crisply
defined and *machine-observable* — this is the only subgenre on the list where segmentation
can be **deterministic** rather than statistical.

**Segmentation signal.** `ui` + OCR. The research is mature: the standard pipeline is
"split into frames → dedupe → classify code-containing frames → localise the code region →
OCR" ([psc2code](https://arxiv.org/pdf/2103.11610),
[CodeSCAN](https://arxiv.org/pdf/2409.18556) — 12,000 VS Code screenshots, 24 languages, 90+
themes, plus IDE-element detection and binarisation before OCR;
[CodeT5-OCRfix](https://dl.acm.org/doi/abs/10.1109/ASE56229.2023.00184) post-corrects OCR with
a code-aware model). `pytesseract` is installed **[verified]**; `easyocr`/`paddleocr` are not.
Cheap first cut: `ffmpeg scdet` on a screencast fires on window/scroll changes, and a terminal
prompt regex over OCR'd text is a near-perfect step delimiter for CLI tutorials.

**⚠ The core-forcing requirement: the per-step payload is not a clip.** It is *text* — a
command, a diff, a file path — plus maybe a cropped screen region. `ArtifactRef.role` is
already open (`clip | gif | poster | …`) but everything downstream in the POC assumes video.
A `role="code"` / `role="diff"` payload with a copy-to-clipboard button in the renderer is a
different rendering contract.

**The reason this is "later" and not "now": `walkthru` may already own it.**
`$PP/t/walkthru/walkthru/core/schema.py` is a Pydantic v2 SSOT of
~30 models (`DemoDocument, Section, CommandStep, Beat, Tracks, Timing, Anchor,
NarrationAnchor, WordTiming, CameraKeyframe, AssetRef, Locator, Target, Rect`, five `*Cue`
types) with `resolve_timeline(document) -> Timeline` in `core/timeline.py`, JSON/WebVTT/SRT
exporters, and a committed JSON Schema at `$PP/t/walkthru/schema/`
[reported verified in `05-fleet-inventory.md` §4.6]. Its conventions —
"**relative, anchor-based time**, no absolute timestamps", "**separate tracks**… associated to
steps **by anchor**", "discriminated unions, not flag soup" — are the conventions
`07-annotation-model.md` independently arrives at. And `walkthru` goes the *other* direction:
it **authors** a demo and records it. `stepped` would **recover** a demo from a recording.

**The right move is probably an adapter, not a subgenre**: make `stepped`'s analysis emit a
`walkthru.DemoDocument`, and let walkthru's renderers play it. `walkthru` already contains the
worked example of doing exactly that across a package boundary —
`ecosystem/reelee/render_target.py` maps its Timeline onto reelee's render contract *without
importing reelee's internal model*, with the reasoning written out. **Decide this with the
user before treating screencasts as a subgenre.** It is a boundary question, and boundaries are
the expensive thing to move.

**Verdict: later, and possibly "never as a subgenre" — an integration instead.**

---

### 2.4 Yoga / pilates / mobility flow — the cheapest possible second subgenre, and that is the argument against it

**Content.** 10–60 minutes, one body, fixed camera, single continuous take, teacher narrating
throughout. Structurally the *most* similar thing to dance on this list.

**Step delimiter.** One asana (a held shape) or one transition between shapes. ⚠ A held pose
has internal structure — **enter / hold / exit** — which is `Step.steps` again, but with the
"hold" sub-step having a duration and near-zero motion. That inverts `motion` segmentation:
here the *low*-energy plateaus are the content and the high-energy bursts are the boundaries.
A `segmenter="motion"` written for judo must therefore be parameterised by polarity, not
hard-coded. Cheap lesson, real lesson.

**Duration unit.** ⚠ **Breaths** — `Measure(value="5", unit="breath")` — a unit with a
*variable, learner-controlled* mapping to wall clock. `MetricGrid` exists but its "tempo" is
set by the user in the renderer, not measured from the source. Dance measures the grid from the
audio; yoga negotiates it with the learner. Different, and it forces `MetricGrid.tempo_bpm` to
be overridable at render time.

**Mirroring.** ⚠ Nearly every yoga sequence is performed **left side then right side**. That is
`Step.variant_of` plus a `mirrored` flag, and the *clip* for the right side can be the
horizontal flip of the left side's clip — a rendering trick, not new analysis. `SourceSpan.role
= "mirrored"` is already in the proposed vocabulary.

Everything else — one subject, body tracking, loop clips, a paced transport — is dance again.

**Verdict: roadmap later.** It would ship fast and demo well, and it is the obvious commercial
neighbour of dance. But as subgenre #2 it would let every fudge in §3 survive, and the
`step_by_step` genre would end up being "the body-in-a-room genre" with a general name. Ship it
*after* one non-body subgenre has forced the document open.

---

### 2.5 Craft: knitting & crochet — the sharpest test of `state` segmentation

**Content.** 10–30 min, top-down or over-the-shoulder on the hands, edited, narrated. A large,
loyal, *already-online* audience with an established written notation (`k2tog`, `yo`, `ssk`)
and chart conventions.

**Step delimiter.** One stitch pattern, or one row. Note the fractal problem: the *atomic*
action (one stitch) repeats hundreds of times, the *step* is the pattern, and the *document* is
the garment. ⚠ Three levels of nesting where dance had two.

**Segmentation signal.** `state` — the fabric visibly grew — plus `cut` and `speech`. The
`period` signal is unusually strong here (a row is a literal repetition), and
`kodokan.segment.estimate_period` transfers directly. Hand tracking would be `mediapipe`
(installed, never wired in this fleet).

**Duration unit.** Rows and stitches. **No wall-clock grid whatsoever**, and — importantly —
**the durations in the document do not sum to the video's duration.** Dance's document is
isomorphic to a timeline; a knitting pattern is not. Any renderer that assumes
`sum(step.duration) == source duration` breaks here.

**⚠ Core-forcing:** the per-step payload includes a **chart** (a generated 2-D diagram), which
is a `role="diagram"` artifact rendered *from the document*, not extracted from the video.
That is a new kind of artifact: **synthesised, not derived**. `fig: "tete"` in the POC's
`clips.json` was a hand-written hint at the same idea.

**Verdict: later.** Genuinely valuable, genuinely hard, and it needs a domain expert to judge
whether the output is right.

---

### 2.6 Luthiery / woodworking / repair, and 2.7 Assembly — the same problem, and the hardest one

Grouped because they share the two things that make them hard.

**⚠ The order is a DAG, not a sequence.** You can sand while glue dries; you must fit the neck
before you finish it; iFixit-style repair guides are *reversible* (the reassembly is the
reverse traversal). `StepDocument.steps` is `list[Step]` with "ORDER IS SEMANTIC" — a total
order. Supporting a partial order means either `Step.depends_on: list[Slug]` or accepting that
the document stores *one linearisation* and records the constraints in `attrs`. **Decide this
before writing the schema, because retrofitting a DAG onto a shipped list is a migration.**

**⚠ Mistakes are content.** The public benchmark here is
[Assembly101](https://arxiv.org/abs/2203.14712) (CVPR 2022): 4,321 sequences, 513 hours, 101
take-apart toy vehicles, 8 static + 4 egocentric views, >100K coarse and 1M fine-grained action
segments, 18M 3D hand poses — and it explicitly "proposes a novel task of **detecting
mistakes**". For repair and assembly, "here is where people get it wrong, and here is what it
looks like when you did" is at least as valuable as the happy path. Nothing in the proposed
`StepDocument` holds a *negative* example. (`OpenQuestion` is uncertainty, not error.)

Also: multi-session sources (a lutherie build is filmed over weeks across a dozen videos),
tiny visual differences that a 300 px loop cannot show, and safety warnings that are legally
load-bearing.

**Verdict: later, both.** High prestige, low throughput, and the audience per document is
small. Worth revisiting only once the resource track and DAG ordering exist for other reasons.

---

### 2.8 Musical instrument technique — the closest structural cousin to dance

Worth a section because it is the only other subgenre with a **real metric grid**, and the
fleet already has grid machinery.

**Step delimiter.** A bar, a phrase, or a numbered exercise. **Segmentation signal** is
`metric` again, but the grid can come from a *score* rather than from beat tracking — which is
strictly better, because it survives rubato and the slow practice tempo. The fleet has
`$PP/t/antescofo` (Python client for **Antescofo**, the
score-following system: `AntescofoClient.load_score(...)`, `.start()`) and
`$PP/t/audiate` ("render a symbolic music score to audio… MIDI,
MusicXML, ABC, Humdrum-kern, MEI… the universal pivot is MIDI") **[verified by reading their
`__init__.py` docstrings]**. `mixing.audio.beats.beat_grid` gives `.tempo_bpm` / `.beat_times`
but **downbeats are always empty on the shipped backend** (`05-fleet-inventory.md` §7) — which
is exactly the gap a score-follower fills.

**⚠ Core-forcing:** the same step is demonstrated **at several tempi** (slow practice → target
tempo), so the `performance`/`instruction` role pair becomes a *continuum* —
`SourceSpan.attrs["tempo_bpm"]` — and the renderer wants a **tempo ramp** ("start at 60, add 5
bpm each pass"), not a fixed metronome. The dance transport is one special case of that.

Also ⚠ **the payload is two synchronised views** (hands close-up + notation/tab), which is
`ArtifactRef` with a `layout` relationship the schema does not express.

**Verdict: later**, but it is the natural fourth, and it makes the "metric grid" machinery
general instead of dance-shaped.

---

### 2.9 Physio / rehab — the one with a real customer, and a real obligation

**Content.** Short, unglamorous, often filmed by the clinician on a phone for one patient.
Frequently *private* — which makes the POC's anonymisation pipeline relevant again, this time
for legal rather than courtesy reasons.

**⚠ Core-forcing:** the duration unit is a **prescription**, not a duration —
`3 sets × 12 reps, 2×/day, 6 weeks`. That is three orthogonal quantities plus a schedule.
And the document has a **second timeline** (the treatment programme over weeks) layered on the
first (the sequence within a session). `Cue` and `Anchor` handle within-step time; nothing
handles across-session time.

**⚠** It also wants **adherence logging** — the renderer becomes stateful and per-user.
`kodokan.learning`'s design is the precedent worth copying: per-item state reconstructed by
*replaying* a flat, append-only response history, "no mutable server state to corrupt".

**Verdict: later.** Real value, real users, but it drags a whole user-state layer into a
library that currently produces static pages. Do it when there is a customer asking.

---

### 2.10 Sign language — say no, and say why

Included because it looks like a perfect fit and is not.

Segmentation is a live research problem, not a solved one: boundaries are genuinely ambiguous,
frame-level annotation is scarce, and the difficulty is that sign combines "hand configuration,
movement, location, and facial expressions" simultaneously
([sign segmentation survey work](https://arxiv.org/pdf/2011.12986),
[ACL 2025 SRW](https://aclanthology.org/2025.acl-srw.93/),
[Hands-On, 2025](https://arxiv.org/html/2504.08593)). Useful cue for a cheap version: linguists
note boundaries are detectable even by non-signers via **pauses and hand-lowering** — i.e. a
`motion`-style signal with inverted polarity, same as yoga.

The deal-breakers are not technical: **the face carries grammar**, so the POC's anonymisation
pipeline would destroy the content outright (a sharper version of the raised-arm failure in
`01-what-was-built.md` §4); and a hearing engineer shipping a sign-language learning product
without Deaf authorship is a reputational and ethical problem regardless of output quality.

**Verdict: never as a fluency product.** A narrow, honestly-scoped *phrase book* built from an
already-glossed source (spans given, not detected) is defensible, and would only exercise the
"many short sources, one step each" topology that judo already covers more cheaply.

---

### 2.11 The rest, compressed

- **Makeup & hair** — mechanically the easiest of the "edited YouTube" family (`cut` + `speech`
  + product names from ASR), and it needs a **product list** = the same resource track cooking
  needs. Face fills the frame, so no crop problem and no privacy option. Ships free once
  cooking exists. *Later.*
- **Sports technique** — the payload is a slow-mo loop **with overlay geometry** (swing plane,
  spine angle), i.e. a `role="overlay"` artifact derived from pose. `kodokan.compare` (soft-DTW
  joint-angle, speed-invariant) + `kodokan.score` (reference-based 0–100 with per-joint,
  per-phase feedback) already do "compare a learner's attempt to a reference". That is a whole
  product — *but it is a coaching product, not a guide product*, and it needs the learner to
  upload video. Out of scope for a rendering library. *Later.*
- **Juggling / skate tricks** — the interesting bit is the **trick tree** (prerequisites), i.e.
  a document that is a graph over steps rather than a sequence — the same DAG requirement as
  assembly. Tiny audience, self-filmed phone clips. *Hobby.*
- **Calligraphy / drawing** — `freezedetect` is the segmentation signal (the artist pauses on
  the finished stroke), the payload wants **stroke-order animation** synthesised from the
  document, and there is a genuinely lovely renderer here. *Later.*
- **First aid / safety drills** — high stakes, low ambiguity, but shipping a generated CPR guide
  without an accredited body's sign-off is negligent. **Never without a domain owner** who
  signs the output.
- **Lab / wet-bench protocols** — the honest problem is that the *written* protocol
  (protocols.io) is already better than any video, so the library would be adding video to text
  rather than extracting text from video. Inverts the value proposition. *Never (v1).*

---

## 3. Recommendation

### Build order

| | subgenre | why this one |
|---|---|---|
| #1 | dance (done) | the POC |
| **#2** | **martial arts / judo throw** | ~70 % of the analysis and a whole second renderer already exist as tested code in `kodokan`. Breaks the **analysis** side: no metric grid, two subjects, inverted source topology, motion-based segmentation. Ships in days, not weeks. |
| **#3** | **cooking recipe** | Breaks the **document** side: resource track, "until done" durations, empty spans, partial order, no subject, no transport. The largest audience on the list. |
| #4 (pick one) | **yoga** for revenue, **musical instrument** for architecture | yoga is nearly free and demos beautifully; music generalises the metric grid properly and has `antescofo`/`audiate` behind it. |

Do **not** make #2 yoga or #3 makeup. Both are "dance with different nouns". Two body-in-a-room
subgenres in a row and the genre/subgenre split is decoration.

The principle to state out loud and defend: **the second subgenre should be chosen to break
something.** Judo breaks the analyser; cooking breaks the document. Between them they cover
both halves of the parse/render split, which is the whole architectural bet.

Prerequisite, before #2: build `segmenter="cut"` on `ffmpeg -vf scdet` (§1.1). No new
dependency, and it is the primary signal for six of the sixteen candidates.

### What #2 and #3 force the core to get right that dance alone lets you fudge

Nine items. Each names the subgenre that exposes it, so the next agent can decide which to fix
now and which to defer honestly.

| # | dance lets you fudge | forced by | what the core must do |
|---|---|---|---|
| 1 | one subject, always a person | judo (2 people), cooking (no person), screencast (no body) | `subject_locator=` must be genuinely pluggable **and nullable**; crop, face-slot and privacy logic must not assume "the person" |
| 2 | a metric grid always exists | judo, knitting, screencast | `MetricGrid \| None` honoured end-to-end, **including in the renderer**. A guide must render with no tempo |
| 3 | `Measure` is a number in a unit | cooking ("until golden"), physio (3×12, 2×/day) | a duration may be a **condition** or a **prescription**. Extend `Measure` or accept a documented `attrs` escape hatch — but decide, don't drift |
| 4 | every step has a clip | cooking (cut-aways, overnight rests) | `Step.spans == []` and `artifacts == []` must be first-class, and the renderer must degrade well |
| 5 | the payload is a video loop | screencast (code), knitting (chart), music (notation) | `ArtifactRef.role` must cover **synthesised** artifacts (rendered *from* the document) as well as derived ones (cut *from* the source) |
| 6 | one video, many steps | judo (many videos, one step each; many spans per step) | exercise `sources` + `spans` plurality for real; a `Step` must address several `Source`s |
| 7 | total order, executed once | cooking (parallel, optional), assembly/repair (DAG) | at minimum record dependencies; at most make the document a partial order. **This is the one that is expensive to retrofit — settle it before v1 ships** |
| 8 | nothing is consumed or produced | cooking, knitting, woodworking, assembly, lab, makeup | a **resource track** (`resources: list[Resource]` + per-step references, with scaling). Five subgenres need it; the schema has no slot |
| 9 | one renderer with one transport | judo (quiz), cooking (timers + checklist), physio (adherence) | `renderer=` must be a **registry**, and `kodokan.flashcards`/`learning` should be wired as the second registered renderer — it exists, it is UI-agnostic, and it costs almost nothing to prove the point |

Items 7 and 8 are the two that are cheap now and expensive later. Everything else can be added
at a boundary that already exists.

---

## Open questions for the next agent

1. **Is `walkthru` the screencast subgenre, or a renderer target?** (§2.3.) `walkthru`'s
   `DemoDocument` and `stepped`'s `StepDocument` are two designs of the same object arrived at
   independently, pointing in opposite directions (author-then-record vs record-then-recover).
   Someone has to decide whether they converge, adapt, or coexist. I could not settle it
   without the user.
2. **Total order or partial order?** I recommend recording `depends_on` from day one and
   letting renderers linearise, but I have no evidence about how badly a DAG complicates the
   editing story (`03-design-brief.md` §5.5, locks).
3. **Where does the resource track live** — in `StepDocument`, or in a subgenre-specific
   sidecar keyed by step id? A sidecar keeps the core clean and makes cross-subgenre renderers
   dumber. I lean core, because ingredients/tools/materials/parts is not five things, it is one.
4. **Is there a second real corpus?** Judo has the Kodokan 100 playlist already downloaded and
   segmented. Cooking has no user-owned corpus that I found — someone should pick 3–5 specific
   recipe videos as the fixture set *before* designing the cooking subgenre, the way
   `choregraphie.html` anchored dance.
5. **Does the user want a coaching product?** `kodokan.compare` + `kodokan.score` (learner video
   vs reference, per-joint feedback) is a different product on the same substrate, and it keeps
   surfacing (sports, physio, music, judo). Out of scope as written — but if it is on the
   roadmap, `SourceSpan.role` should reserve a `learner_attempt` role now.
6. **Unverified claims I am leaving behind:** I did not run `ffmpeg scdet` on a real video, did
   not import `kodokan` (only read its source and README), did not run any `nw`/`reelee` code,
   and did not re-verify the fleet capability table in `05-fleet-inventory.md` §7. Everything
   attributed to those docs is second-hand and marked as such.

## References

- [COIN: A Large-scale Dataset for Comprehensive Instructional Video Analysis (CVPR 2019)](https://arxiv.org/abs/1903.02874) — 11,827 videos, 180 tasks, 12 domains, 46,354 segments, 3.91 steps/video, 14.91 s/step.
- [Assembly101 (CVPR 2022)](https://arxiv.org/abs/2203.14712) — 4,321 sequences, 513 h, 101 toys, 12 views, 1M fine-grained segments, 18M 3D hand poses; mistake-detection task.
- [psc2code: Denoising Code Extraction from Programming Screencasts](https://arxiv.org/pdf/2103.11610); [CodeSCAN](https://arxiv.org/pdf/2409.18556); [CodeT5-OCRfix (ASE 2023)](https://dl.acm.org/doi/abs/10.1109/ASE56229.2023.00184).
- [RepNet / Counting Out Time (CVPR 2020)](https://openaccess.thecvf.com/content_CVPR_2020/papers/Dwibedi_Counting_Out_Time_Class_Agnostic_Video_Repetition_Counting_in_the_CVPR_2020_paper.pdf); [A Short Note on Evaluating RepNet (2024)](https://arxiv.org/abs/2411.08878) — the family `kodokan.segment.self_similarity_matrix` imitates dependency-free.
- [Sign language segmentation with temporal convolutional networks](https://arxiv.org/pdf/2011.12986); [Sign Language Video Segmentation Using Temporal Boundary Identification (ACL SRW 2025)](https://aclanthology.org/2025.acl-srw.93/); [Hands-On: Segmenting Individual Signs from Continuous Sequences (2025)](https://arxiv.org/html/2504.08593).
