# ADR-0004 — paces is a focused package below reelee; the core depends on nothing heavy

- **Status:** Accepted (built to in the first commit; cheap to amend before anything depends
  on it — argue if you disagree).
- **Decided:** 2026-08-29, by the kickoff session, per the standing instruction to settle the
  boundary before code. The research hypothesis (`../README.md` finding 2, `../04-reelee-core.md`)
  is **confirmed**, with one sharpening about dependency direction.
- **Relates to:** `0003` (the core abstraction), `../04-reelee-core.md` (the evidence),
  `../07-annotation-model.md` (the two-layer IR this implies).

---

## Decision

**`paces` is a focused package below reelee — not a fork of it, not a plugin inside it.**
The muvid pattern: its own package, its own PyPI release (claimed 2026-08-29,
<https://pypi.org/project/paces/>), eventually registering a `step_by_step` genre into
`nw.genres` from its own `paces/genre.py`.

**The sharpening: the core has no fleet dependencies.** v1's runtime dependency is `pydantic`
alone. The fleet integrations are *consumers and optional layers*, not the core:

| layer | depends on | status |
|---|---|---|
| `paces.model` (the `StepDocument` IR) + `paces.segment` (the seam) + `paces.render` | `pydantic` only | **v1, built** |
| evidence store (`to_store(seg)` → lacing annotations, per `../07 §6.3`) | `lacing` (extra) | next, designed in `../07` |
| grid *measurement* (tempo/beats from media) | `mixing.audio.beat_grid` (extra) | seam exists (`grid=`), impl pointable |
| genre registration (`paces/genre.py`) | `nw` (extra) | when reelee integration is wanted |

## Why

1. **Every argument in `../04-reelee-core.md` §7 holds on inspection.** reelee is an
   application (its own prime directive says substance lives below it); `nw.Genre` is pure
   data registered from the owning package; muvid proves a genre with zero Transforms is a
   first-class citizen. Nothing about paces needs to live inside reelee.
2. **The user declared paces a public library.** A public `pip install paces` must not drag
   in an application. `lacing` and `nw` are on PyPI and lightweight, so even they *could* be
   core deps — but v1's one-command test (segment → document → render) does not touch them,
   and architecture-first says ship only what the test reaches. `pydantic`-only keeps the
   contract (`StepDocument` → JSON Schema → Zod) with the smallest possible surface.
3. **The document/store split (`../07 §6.0`) makes the layering natural.** The committed,
   hand-editable `StepDocument` is paces' own type and needs no substrate. The evidence layer
   (transcripts, beat grids, detections, provenance) is where `lacing` enters — and it enters
   behind one projection function, exactly as designed.

## What this rules out

- **Depending on `reelee`** — it is an app; `../04 §7` "Do NOT reuse" is explicit.
- **A hard `nw`/`lacing` dependency in v1** — they arrive as extras when their layer is built.
- **Waiting for the alignment engine (`0001`)** — it stays a *pointable replacement* behind
  the `segmenter=` seam. When it exists (generalised from `muvid/align.py`), its methods
  register as capabilities; nothing in paces' core changes.

## Consequences

- paces registers in the fleet like any member: `$PP/t/paces`, own GitHub repo, wads CI,
  PyPI on merge. Done in the same session as this ADR.
- The `step_by_step` genre + `dance_moves` template is a **named next step**, one file,
  modelled on `muvid/genre_music_video.py` — deferred until the reelee surface is asked for.
- Body-schema URIs (`annot://schema/step/v1` etc., `../07 §6.3`) are claimed when the lacing
  layer is built, not before — check `lacing.schema.register_body_schema` conflict behaviour
  then (open question 5 of `../04`).
