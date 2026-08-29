# 03 — Design brief

*What this file is for: the framing the user gave for generalising the POC, made precise,
plus the constraints the POC discovered. **This is not the design.** It is the set of things
the design must account for, and the record of one metaphor the user explicitly asked to have
written down. Where a sentence is the user's own framing it is marked ⟨user⟩; everything else
is inference from the session and is fair game to overturn.*

---

## 1. The central metaphor — parse, AST, interpret

⟨user⟩ *"The key here is, like in a lot of reelee stuff, to separate two important aspects of
the output. The linked artifacts (the annotation system), and the rendering. In a first phase
we analyze the inputs (and other intermediate artifacts) and create annotations, indices,
ledgers, linked artifacts. In a second we 'render' this in some way. This input +
intermediate-artifacts + output-rendering reminds me of parsing code (input as text) and
creating an AST, and then using the AST to 'execute' or 'interpret' (the rendering part)."*

Mapped onto the compiler analogy:

| compiler | this library | in the POC |
|---|---|---|
| source text | source media + notes + steering prompt | mp4, `choregraphie.html`, the prompt |
| lexer / tokens | signal extraction | audio features, ASR segments, beat grid, person boxes |
| parser | segmentation + alignment | the count grid, the ten window-picking agents |
| **AST** | **the step document** | `clips.json` |
| symbol table / side tables | derived-asset ledger | `crops.json`, `media/*` |
| interpreter / backend | renderer | the HTML template + ffmpeg |
| multiple backends | multiple renderers | page today; PDF, deck, app, print tomorrow |

Two things the analogy buys, and one it costs:

- **A stable contract.** Renderers depend on the AST, never on the analyser. In the POC the
  media was re-rendered three times and the page a dozen times without `clips.json` changing.
  That is the evidence this split is real and not architectural decoration.
- **Optimisation passes.** Anything that improves the AST in place — resolving a contradiction
  between doc and video, merging duplicate steps, inferring a missing name — is a *pass*, and
  passes compose. The verification agent that caught blocks 1 and 2 sharing a move was a pass.
- **The cost:** an AST is normally produced by a deterministic parser. Here the "parser"
  includes an LLM looking at contact sheets. So the AST must be **editable and re-derivable
  without losing the edits** — a constraint no compiler has. See §5.

Where the analogy misleads: do not reach for a grammar. The input is not a language; there is
no production rule that segments a video. The value is in the *staging*, not in parsing theory.

## 2. The three generalisation axes ⟨user⟩

### 2.1 The subject axis — *needs a better name*

⟨user⟩ *"Subject [propose a better name for this!]. Here it was a dance routine. But could be
instructions of all kinds. More aligned if it's some kind of step by step instructions whose
corresponding steps can easily be segmented out of the video, and explained (from the video
and/or doc or other kind of annotations), given names, etc."*

Reelee already has a word for the analogous axis: **genre**. ⟨user⟩ *"we want to reuse a core
for the step-by-step general situation (what reelee calls 'genre'), but also use the
advantages of specialization: we want to have a dance-moves 'subgenre', and perhaps 2 or 3
other subgenres."*

So the intended shape is:

```
genre:    step-by-step instructional content segmented out of a video
subgenre: dance routine  |  martial-arts form  |  recipe  |  … (see 09-subgenre-candidates.md)
```

Candidate replacements for "subject" are collected in `08-naming-candidates.md`; **align with
reelee's existing vocabulary unless there is a reason not to** (`04-reelee-core.md` reports
what a reelee genre actually is).

The defining property, worth stating sharply because it bounds the whole product: *content
where a teacher demonstrates a nameable, ordered sequence, usually end-to-end first and then
broken down.* The "end-to-end then broken down" structure is not incidental — it is what gives
each step **two source spans**, and that turned out to be the most load-bearing fact in the POC.

### 2.2 The input axis

The POC took **video + doc + prompt**. Generalise each:

| input | POC | generalises to | notes |
|---|---|---|---|
| primary media | one YouTube video | several videos, audio-only, a photo sequence, a screen recording | multi-source is not exotic: the *same step* legitimately appears in more than one place |
| notes | a hand-written HTML aide-mémoire | any doc: markdown, PDF, a transcript, a numbered list, nothing at all | in the POC it supplied the step list; see §4 |
| steering prompt | one paragraph of free text | a first-class, persisted, re-runnable input | see §3 |

### 2.3 The output axis

⟨user⟩ *"Here, we have a webpage that has links to the original video, that can be 'played'
with a metronome going through the steps in a paced manner… But we could imagine other kinds
of 'guides' or 'learning materials'."*

The renderer boundary is where subgenre specialisation is most visible and most affordable.
The dance page's metronome is meaningless for a recipe; a recipe's shopping list is
meaningless for a kata. Both are *renderers over the same AST*.

## 3. The steering prompt is a first-class input

This is the strongest single lesson of the POC and it deserves to be a design constraint, not
a convenience.

The user's prompt carried two things no analysis would have produced:

1. **The macro-structure.** *"first the person on the video talks, then she goes through the
   whole phases, while music is playing, then she breaks them down and explains."* That one
   sentence is what made the segmentation tractable — it told the analyser there were two
   passes over the same material and which was which.
2. **A warning about the inputs' disagreement.** *"it may not be exactly as described in the
   phases — I think she changed a few things: The artifact shows less/more-simple stuff, but
   should be more or less the same, same order."*

Consequences for the design:

- The prompt must be **persisted with the project** and replayable, not consumed once at the
  CLI. It is part of the source, like a compiler flag file.
- It is where **subgenre-specific hints** naturally live before there is UI for them
  ("count in 8s", "she demonstrates each move twice", "ignore the first 40 seconds").
- A design that treats the prompt as optional flavouring will produce a library that only
  works on content whose structure the analyser already happens to guess.

## 4. The notes document is a hypothesis, not ground truth

The POC's nine blocks came from `choregraphie.html`, not from analysis. Nothing in the session
segmented a video cold. Two things followed:

- The doc was **wrong in measurable ways** — its tempo was 100 bpm against an actual 129 — and
  the analysis corrected it.
- The doc carried **explicit open questions** ("soleil des bras, ou les premiers déhanchés ?")
  and the analysis *answered three of them*.

So the design should treat notes as **a prior over the step list, with confidence**, and the
analyser's job as *confirm / correct / resolve / add*, emitting a diff the human can inspect.
"The doc said X, the video shows Y" is a first-class output, not a warning to swallow.

Corollary, and a scoping decision to take early: **does v1 require notes at all?** Segmenting
a video into named steps with no prior list is a substantially harder problem, and the POC has
no evidence about it either way.

## 5. Constraints the POC discovered

Each of these cost real time. They are requirements in disguise; `01-what-was-built.md §4`
has the full incident list.

1. **A step has *many* spans, not one.** Run-through and breakdown are the same step seen
   twice. Six of nine blocks shipped both. A `{step → one time range}` model is wrong on day
   one. The POC's flat `src: "RT" | "BD"` field is the minimum viable version of this idea and
   `07-annotation-model.md` proposes the real one.
2. **Duration is domain-specific.** The dance's unit is the 8-count, and seconds are derived
   (`8 × 60/bpm`). A recipe's unit is minutes-or-until-done; a rep-based workout's is reps.
   Storing only seconds throws away the thing the learner actually counts.
3. **Derived assets are a separate layer.** `crops.json` is a cache; `media/*.mp4` are
   outputs. Neither belongs in the semantic model, both need addressing from it.
4. **The privacy transform can destroy the content.** A blanket head blur erased the raised
   arms in the three blocks *about* raised arms. Anonymisation must know what the step is
   about, or be tunable per step.
5. **Human edits must survive re-analysis.** Captions were hand-tuned; media was regenerated
   three times. Any model that is clobbered by re-running the analyser is unusable.
6. **Analysis is expensive and re-run often.** ~11 minutes of agents to pick ten windows,
   ~25 minutes of GPU-ish work to stylize. Caching by content hash, and resumability, are not
   polish.

## 6. Seams to declare on turn 1

Per `~/.claude/skills/architecture-first/SKILL.md`, a seam is one keyword argument defaulting
to the strongest implementation that needs no new dependency. Candidates, offered as a
starting list to argue with rather than a design:

| seam | default | replaced by |
|---|---|---|
| `transcriber=` | `mlx_whisper` large-v3-turbo | faster-whisper, a hosted ASR, an existing transcript |
| `subject_locator=` | YOLO11s person boxes | pose, hands, an object detector, a fixed crop |
| `stylizer=` | identity (no stylization) | the kodokan pipeline, a cheaper blur tier, a hosted model |
| `segmenter=` | align-to-notes | cold segmentation, beat grid, scene cuts, ASR imperatives |
| `renderer=` | the practice page | PDF, deck, print, app |
| `store=` | local `dol` files | S3 via `s3dol` |
| `llm=` | Claude via the house convention | any |

Note `stylizer=` defaults to **identity**: it is heavy, it needs non-commercially-licensed
weights, and most subgenres will not want a cartoon filter. The POC needed it because the
subject was an identifiable private person in an unlisted video.

## 7. Build order ⟨user⟩

⟨user⟩ *"As usual for things involving BE and FE: Starting with the backend in python, then
slapping ai artifacts on top, as well as web services (with qh) and mcps (with py2mcp), and FE."*

`06-surfaces-and-conventions.md` documents each. The architecture-first skill's guidance
applies: in v1 ask only *"would this surface need the core to change?"*, then build the one
surface that was asked for.

## 8. Relationship to reelee

⟨user⟩ *"This should be integrated with our video_gen group/fleet, also known as 'reelee',
reusing the tools of the fleet where appropriate."*

`04-reelee-core.md` and `05-fleet-inventory.md` report what exists. The open question for the
next agent is the **shape** of the integration, and it is a real fork:

- a **subgenre/plugin inside reelee**, if reelee's genre machinery already does most of this;
- a **sibling package that depends on reelee** for project/storage/annotation primitives;
- an **independent core** that reelee can call.

Do not decide this from the outside. Read `04-reelee-core.md` first, then argue it with the
user — it determines the package boundary, and boundaries are the one thing that is expensive
to move later.

---

## Open questions for the user (raise these early)

1. **Notes required in v1, or cold segmentation?** Biggest scope fork in the project.
2. **Integration shape with reelee** (§8) — decides the package boundary.
3. **Is the renderer part of this library or a sibling?** The POC's renderer was a patched
   copy of the input document; a real one needs a template contract, and that could be its own
   package.
4. **How much of the analysis may be LLM-driven?** Ten agents looking at contact sheets is
   accurate, slow and expensive. Where is the acceptable cost per project?
5. **What is the editing story?** If a human fixes a caption or nudges a boundary, where does
   that live so re-analysis does not eat it?
