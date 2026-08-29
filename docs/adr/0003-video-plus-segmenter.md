# ADR-0003 — The core abstraction is `video + segmenter`

- **Status:** **Accepted** as the shape to build toward. Decided by thorwhalen, 2026-08-29.
- **Relates to:** `0001` (the alignment engine — what many segmenters will delegate to),
  `../03-design-brief.md §5` (the constraints), `../alignment/07-segmenter-strategies.md`
  (a catalogue of concrete strategies — but see §5, it is organised on a different axis
  from this ADR and over-reaches in one place).
- **Revision note:** an earlier draft of this ADR misread the decision as "the default
  segmenter is selected by how rich your inputs are". That is *a* useful taxonomy but it is not
  the point. Rewritten 2026-08-29 after correction. The user's own words are quoted throughout
  so the next reader can check my reading rather than inherit it.

---

## Context

The handoff framed the biggest open scope question as a fork: *does v1 require a notes document,
or must it segment a video cold?* The POC never segmented cold — its nine steps came from an
input document, and the analysis confirmed, corrected and timed them.

The user dissolved the fork rather than picking a side:

> *"the abstraction I'd like to explore is really **video+segmenter**: Depending on how many
> other inputs/annotations/artifacts are present, the default segmenter could be one thing or
> another. The important thing here is to leave it **open closed**. Some segmenters might be
> video only (but still, there's many ways to do that). The segmenter could be of the type
> you've seen in this 'que calor' project we just did. It could also be **'ask the user'**."*

and then, correcting the first draft of this ADR:

> *"there can be all kinds of segmenters. Segments can be based on features of the video itself,
> or on some external information, which can be explicit, such as actual interval coordinates
> given explicitly by the user, or something that is to be computed given the other annotations
> around. It could also be a mix of both video and other information. What I was trying to
> express there is just that I wanted things to stay **open closed, perhaps a strategy pattern**,
> but that **some structure could already be given on the ways that things can be segmented**.
> For example, whether we segment the video based on detected scenes, big changes in frame
> content, whether someone is talking or not, or based on a beat count, **all of these have to do
> with applying a feature function to the video and audio, and creating a stream of feature
> vectors from which we compute a quantity that is thresholded**. So even though we want to keep
> things open closed in general, we should still **provide the tools to be able to make
> segmenters that correspond to common needs**."*

## Decision

**Segmentation is a seam, not a stage.** `paces` takes media plus a `segmenter=`, and the
segmenter is where the variation lives. Four commitments, in order of importance.

### 1. Open-closed, via a strategy pattern

Adding a new segmenter must require **no modification to existing code** — no hand-maintained
dispatch table, no `if` chain, no change to the core's signature. Segmenters are *registered*,
not wired in.

The fleet already has the pattern: `muvid.footage.strategy`'s registry with **lazy**
registration (`slug → "module:func"`), so listing a heavy strategy does not import numpy
(`../alignment/00-existing-in-fleet.md`). Follow it rather than inventing another.

This is the load-bearing commitment. Everything below is structure *offered* inside it, and
none of it may become a precondition for writing a segmenter.

### 2. Structure: where a segmenter's information comes from

Not a hierarchy and not a selection rule — a map of the space, so the design covers it and so a
new segmenter can be placed.

| source | what it means | examples |
|---|---|---|
| **Intrinsic** | computed from the media itself | scene cuts, frame-content change, speech/no-speech, beat grid, motion energy, pose change |
| **External, explicit** | boundaries handed over directly | the user types interval coordinates; an SRT/chapter file; a previous run's saved segmentation |
| **External, derived** | computed *from the other annotations around*, not from the media | infer boundaries from a step list plus known durations; from a numbered document; from sibling annotations already on the timeline |
| **Mixed** | both, in any combination | the que-calor case: a document's step list *placed* using an intrinsic beat grid |

**Mixed is the normal case, not the exotic one.** The POC is mixed. `../alignment/07`'s tier
table is one slice through this space (it varies the external axis while holding "video present"
fixed); useful, but do not mistake it for the space itself.

### 3. Structure: the shape most intrinsic segmenters share — and the tools for it

The user's observation, which is the actionable half of this ADR:

> *scenes, frame-content change, speech-or-not, beat count — "all of these have to do with
> applying a feature function to the video and audio, and creating a stream of feature vectors
> from which we compute a quantity that is thresholded"*

So provide that pipeline as composable parts, and let a large family of segmenters be built by
combination rather than by writing a segmenter from scratch:

```
media ──► featurize ──► reduce ──► detect ──► regularize ──► boundaries
          (stream of    (→ scalar   (threshold  (optional:
           feature       stream)     / peak-     every k-th,
           vectors,                  pick /      snap to grid,
           with a time               known-K)    min/max length)
           base)
```

| stage | contract | stock implementations to ship |
|---|---|---|
| `featurize` | media → iterable of (time, vector) | frame histogram/embedding, frame-difference, motion energy, onset strength, sub-bass ratio, VAD posterior, pose keypoints, OCR text |
| `reduce` | feature stream → scalar stream | successive distance, self-similarity novelty (Foote), binary-state indicator, deviation from a fitted model |
| `detect` | scalar stream → boundaries | fixed threshold, quantile, **hysteresis** (on above high, off below low), peak-pick, **known-K change-point** |
| `regularize` | boundaries → boundaries | every k-th (this is what turns a beat track into an 8-count grid), snap to a grid, enforce min/max length, merge/split |

Worked mappings, to check the shape is real and not a just-so story:

- **detected scenes** — frame embedding → successive distance → threshold
- **big frame-content change** — same family, cheaper featurizer (histogram)
- **someone talking or not** — VAD posterior → binary indicator → **hysteresis** (the plain
  threshold flickers; this is why `detect` must be a seam and not a constant)
- **beat count** — onset strength → onset novelty → peak-pick (*this is beat tracking*) →
  `regularize`: every 8th beat. Two of the four stages are the same code as scene detection.

`kodokan.segment` already implements a chunk of this (motion energy, optical-flow energy,
hysteresis, self-similarity, `estimate_period`) and `mixing.audio.find_segments` implements
another (silence, energy novelty, self-similarity, speech/music). **Neither is written as
composable stages.** Factoring them into this shape, rather than writing a third one, is the
concrete first task.

Two honest limits on §3:

- It covers **intrinsic** segmenters well and external ones barely. "The user typed the
  intervals" has no featurizer. That is fine — §1 is what accommodates them.
- Some intrinsic methods genuinely do not decompose this way (an end-to-end action-segmentation
  model, an LLM asked for boundaries). The combinators are **an offer, not a taxonomy that must
  cover everything.** A segmenter that ignores them is still a first-class segmenter.

### 4. "Ask the user" is a first-class segmenter

It sits behind the same interface as every automatic one — the *external, explicit* row of §2
with a human supplying the coordinates. Stated explicitly because it is the commitment most
likely to be quietly dropped under delivery pressure.

Two things make it good rather than a cop-out, and both are design work:

- **What the machine pre-computes.** The gap between a 30-minute chore and a 2-minute
  confirmation is the quality of the proposal before the human looks. Even a segmenter that
  cannot commit to boundaries can usually rank candidates. `../alignment/07 §7` makes a good
  point here: the cheapest thing to ask is often *how many*, not *where* — one integer turns
  peak-picking into exact known-K change-point detection.
- **How the answer persists.** Corrections must re-enter as **constraints for the next run**,
  not as a patch on the output — otherwise re-running the segmenter destroys them. Same
  constraint as `../03-design-brief.md §5.5` and `0001`'s open question 4.

## Segmentation and labelling: coupled or not, depending on the case

The user, explicitly:

> *"The separation of segmentation and the labeling of the segments can be strong or not.
> That really depends on the case."*

So this is **not** a law of the design, and an earlier draft was wrong to state it as one.
Treat it as a dial:

- **Strongly separated** — the boundaries come from one signal and the names from another. The
  POC: a beat grid cut, the teacher's speech named. Also: any video-only segmenter that finds
  cuts it cannot name.
- **Coupled** — the same evidence produces both at once. A step list placed on a timeline: each
  span *is* its label. Chapter metadata. An LLM asked for "steps with names and times".

Consequences for the design: the return type must **carry a name when there is one and honestly
omit it when there is not** — not force every segmenter to invent one, and not forbid the ones
that legitimately know. A segmenter that returns unnamed spans is complete, not broken; a
naming stage may or may not follow.

The one strong claim worth keeping from the research, because it was measured rather than
assumed: a segmenter that *invents* plausible names for content it did not understand is worse
than one that returns boundaries and says it does not know — the second is fixable in minutes,
the first is a lie the human must detect first. That is an argument about **honesty under
uncertainty**, not about always separating the two concerns.

## Consequences

**Good**

- The v1 scope fork disappears. v1 ships whichever segmenters are cheapest to get right; the
  rest arrive later without a refactor.
- The POC's approach becomes *one registered strategy* rather than the architecture — the
  correct demotion, since it was tuned to one video.
- §3's combinators mean the common cases are assembled, not authored, while §1 keeps the
  uncommon ones possible.
- "Ask the user" being first-class makes `paces` useful on content nothing can segment
  automatically — which is most content.

**Costs and risks**

- **Speculative generalisation.** A registry plus a combinator kit before there are three real
  implementations is exactly what the house style warns against. Mitigation: build two
  maximally-different segmenters *first* — the que-calor one (mixed) and the ask-the-user one
  (external, explicit) — so the seam is shaped by both rather than by one; extract the §3
  combinators only when a third, intrinsic segmenter actually needs them.
- If a default is chosen automatically, it must be **reported with its confidence and
  overridable by one keyword argument**. Silent selection of a plausible-but-wrong segmenter is
  the failure mode to avoid.

## What `../alignment/07-segmenter-strategies.md` contributes, and where it over-reaches

1,521 lines of concrete strategy catalogue — real libraries, costs per minute, failure modes.
Use it as the menu. Two corrections when reading it:

- **Its organising axis is input-richness tiers (A–G).** That was my brief to it, not the
  user's framing. §2 above is the intended map; the tiers are one slice through it.
- **It states the segmentation/labelling split as a law** ("video-only can find cuts, it almost
  never finds names"; "the default must refuse to name"). Per the section above, that is
  case-dependent. Its underlying measurement — a confident argmax for something absent from the
  video — is sound and worth heeding as an honesty constraint.

Genuinely useful and unaffected by both corrections: `Segmenter = propose ∘ align` as a common
factoring; "video only" being a statement about your *inputs*, not your *modality* (a video
carries audio, which carries a transcript; a URL carries chapters and subtitles); and asking a
human for *K* rather than for boundaries.

## Open questions

1. **What is a segmentation, before it becomes steps?** Boundaries? Spans with confidences?
   Spans with optional names? This return type is the contract every segmenter signs — settle it
   first, and settle it so that "named" and "unnamed" are both first-class (see above).
   `../alignment/07 §9` proposes one; review rather than restart.
2. **How far do the §3 combinators go before they become a straitjacket?** Resolve empirically:
   implement three intrinsic segmenters against them and see which stage stops fitting.
3. **What does a segmenter do when unsure?** Low confidence, nothing, or escalate to `ask`?
   Escalation implies segmenters compose, which is a larger commitment.
4. **How much does a segmenter share with `0001`'s alignment engine?** For the external-derived
   and mixed rows of §2, placement *is* alignment. If most segmenters are thin wrappers over
   that engine, `0001` becomes a dependency of the core seam rather than optional
   infrastructure — which changes the build order. Confirm early.
