# `paces` — a library for turning instructional video into learning material

*Put it through its paces.* The name is settled (`adr/0002`); so is the core abstraction
(`adr/0003`). These docs were written while the package was still called `stepped` — where the
prose says "stepped", read `paces`.

---

## What this is

A working proof-of-concept exists. In one session, a YouTube video of a choreographer teaching
a dance, plus a hand-written HTML aide-mémoire, plus a paragraph of steering prompt, became a
deployed interactive practice page: <https://thorwhalen.com/que_calor_dance/>.

The user now wants that generalised into a library, integrated with the **reelee** /
`video_gen` fleet. Your job is to research, design and build it. **This folder exists so you
do not start from scratch.** It records what was built, the parameters that were expensive to
find, the failures and what each one teaches, the user's own framing of the generalisation,
and an inventory of what already exists in the fleet.

Nothing here is a design you must follow. It is evidence and framing. Argue with it.

## Read in this order

| | file | why |
|---|---|---|
| 1 | **`01-what-was-built.md`** | The POC, factually. Includes the incident list — every failure is a requirement in disguise. |
| 2 | **`03-design-brief.md`** | The user's own framing: the parse→AST→render metaphor they explicitly asked to have recorded, the three generalisation axes, and the constraints the POC discovered. |
| 3 | **`04-reelee-core.md`** | What reelee is, what a reelee "genre" is, and what to reuse. **This determines the package boundary**, so read it before deciding anything structural. |
| 4 | **`07-annotation-model.md`** | The proposed shape of the AST — the contract between analysis and rendering. |
| 5 | **`05-fleet-inventory.md`** | What already exists across `video_gen`, and honestly which parts are stubs. |
| 6 | **`02-technical-recipes.md`** | Every technique with working parameters. Reference, not narrative — come back to it when implementing. |
| 7 | **`06-surfaces-and-conventions.md`** | House style: architecture-first seams, qh, py2mcp, storage, frontend, deploy. |
| 8 | **`08-naming-candidates.md`** | PyPI-verified name options, and a better word for the "subject" axis. |
| 9 | **`09-subgenre-candidates.md`** | What to build after dance, and what each choice would force the core to get right. |
| 10 | **`10-session-archaeology.md`** | The 27 MB session transcript, and how to query it when these docs fall short. |
| — | **`adr/`** | The decisions. **`0003` `video + segmenter`** — read it before designing the analysis phase. `0002` the name. `0001` the alignment engine (intent) — note that much of what you'd otherwise build already exists in `muvid`, `mixing` and `kodokan`. |
| — | **`alignment/`** | The research behind that ADR: one file per method family, prepared so you don't start from a literature search. |
| — | **`KICKOFF.md`** | A paste-ready prompt to start a fresh session on this. |
| — | **`REGISTRATION.md`** | **One command still pending** to register `paces` in the `video_gen` group, and why `priv pkg add-package` is deliberately deferred. |
| — | **`poc-reference/`** | The actual scripts and data. Read `poc-reference/README.md` first — several of those files are recorded dead ends. |

## The one-paragraph version

Take instructional media (a video of someone teaching something) plus optional notes and a
steering prompt. **Analyse**: extract signals (audio structure, transcript, beat grid, subject
tracking), segment into named steps, align against the notes, and emit a structured step
document — an *AST*. **Render**: consume that AST to produce learning material — an
interactive practice page today, other guides later. The AST is the contract; the analyser and
the renderers depend on it and not on each other. A shared core handles step-by-step
instructional content in general (reelee's word: **genre**); *subgenres* — dance, kata,
recipe, repair — specialise the segmentation signals, the duration unit, and the rendering.

## Four findings from the research that change the starting position

These came out of `04`–`07` and are worth knowing before you read anything else, because each
one removes work you might otherwise plan for.

1. **"Genre" is an `nw` concept, not a reelee one.** `nw` (`$PP/t/nw`) owns `Project`,
   `Transform`, `Genre`, freshness and jobs, with a real registry
   (`register_genre`, `register_genre_resolver`, `register_genre_initializer`,
   `register_genre_project_factory`). If you want a "step-by-step" genre with a "dance"
   subgenre, that machinery already exists and reelee is a *consumer* of it. `04-reelee-core.md`.
2. **reelee is deliberately small.** Its own `__init__` says the substance lives in the focused
   packages below it — `lacing`, `falaw`, `nw`, `artful` — and reelee's surface is
   orchestration. That strongly suggests this library is **another focused package below
   reelee**, not a fork of it and not a plugin inside it. Confirm with the user, but start from
   that hypothesis.
3. **`lacing` is already the annotation substrate**, and reelee already ships
   regenerate-without-losing-human-edits machinery on top of it. That is constraint §5 of
   `03-design-brief.md` — the one that looked hardest — already solved. `07-annotation-model.md`
   recommends owning only a small *document* type and delegating everything below it.
4. **The step structure was never in `clips.json`.** It was in the page's own
   `const ROUTINE = [...]`; `clips.json` is the *span* table. Reading the POC as a two-layer
   model (steps ↕ spans) rather than one flat list is the single most useful reframe in these
   docs.
5. **Most of the analysis phase already exists in the fleet, unwired.** `muvid/align.py` is an
   aligner registry with dispatch and a `lacing` writeback; `muvid.footage.select_score` is a
   constrained sequence solver; `mixing.audio` has beat grids, speech/music segmentation and
   cross-correlation offset alignment; `kodokan` has a complete, tested, Apple-Silicon-native
   **pose front-end that has never been pointed at an alignment problem**. `adr/0001` and
   `alignment/00-existing-in-fleet.md` have the map. Do not write a second one of any of these.

## What the POC actually proves

- Separating analysis from rendering is real, not architectural decoration: the media was
  re-rendered three times and the page a dozen times from unchanged manifests.
- A step legitimately has **several source spans** (at-tempo run-through *and* slow
  explanation). Six of nine blocks shipped both. A one-span model is wrong on day one.
- Cheap signals go a long way: a sub-bass energy ratio separates speech from music in five
  lines and did more work than anything else in the session.
- An LLM looking at timestamped contact sheets makes genuinely good editorial calls about
  which few seconds show a move — and is slow and expensive doing it.

## What the POC does *not* prove

- **Nothing here segmented a video cold.** The nine steps came from the input document; the
  analysis confirmed, corrected and timed them. Cold segmentation is a different, harder
  problem and the POC has no evidence about it.
- Everything assumed **one subject**. Two people breaks the crop envelope, the face-slot logic
  and the privacy mask simultaneously.
- The renderer was a patched copy of the input document. There is no template contract yet.

## Suggested first moves

1. Read `04-reelee-core.md`, then settle the **integration shape** with the user. The research
   points at "a focused package below reelee, registering an `nw` genre" — test that
   hypothesis rather than assuming it. Boundaries are the expensive thing to move later.
2. ~~Settle the name~~ — **done, `paces`** (`adr/0002`). Still open: the better word for the
   "subject" axis. Leading candidates in `08-naming-candidates.md §6`: `discipline`, `craft`,
   `grammar`, `idiom`. **Do not run another availability sweep** — 684 names are already
   checked, and that file is now also the name pool for sub-packages this work spawns.
3. ~~The v1 scope fork~~ — **dissolved by `adr/0003`.** Segmentation is a seam, not a stage:
   `video + segmenter=`, kept open-closed by a strategy pattern. A segmenter's information can
   be **intrinsic** (features of the media), **external-explicit** (coordinates handed over),
   **external-derived** (computed from the surrounding annotations), or **mixed** — and mixed is
   the normal case. Many *intrinsic* segmenters share one shape — featurize → reduce → threshold
   → regularize — which the package should ship as composable stages so common cases are
   assembled rather than authored. "Ask the user" is first-class. Read that ADR, then
   `alignment/07-segmenter-strategies.md` **with its correction preamble**, then decide which
   two segmenters v1 ships.
4. Write the AST schema and validate it by **re-expressing the POC's `clips.json` in it**
   (`poc-reference/artifacts/clips.json`). If the dance case does not round-trip, the schema is
   wrong. That is a cheap, real test available on day one.
5. Only then pick seams and build (`03-design-brief.md §6`, `06-surfaces-and-conventions.md`).

## Open questions for the user

Collected from across these docs; raise them early rather than guessing.

1. ~~Notes required in v1, or cold segmentation?~~ Answered by `adr/0003`.
2. Integration shape with reelee? (decides the package boundary — the live one)
3. Is the renderer part of this library or a sibling package?
4. How much of the analysis may be LLM-driven — what is the acceptable cost per project?
5. What is the editing story? Human edits must survive re-analysis.
6. ~~The name~~ (`paces`, `adr/0002`) — but still the word for the "subject/genre" axis.

## Provenance

Built from session `0f75703c-6761-4aa0-b796-aafe02c94155` (2026-08-27/28). The full transcript
is on disk and queryable — `10-session-archaeology.md`. Docs `01`, `02`, `03`, `10` and
`poc-reference/README.md` were written from direct session context; `04`–`09` were researched
by subagents and each carries its own "verified vs inferred" notes.
