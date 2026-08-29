# 07 — The intermediate representation (the "AST")

**What this file is for.** You are about to design the data model that sits between *analysis*
(parse a video + a doc + a prompt into structure) and *rendering* (emit a web page, a PDF, a
deck). This file tells you what the existing ecosystem already provides so you do not rebuild
it, what the POC's own intermediate files empirically prove the model must hold, which
established formats are worth borrowing from and which are traps, and then recommends a
concrete two-layer model with a schema sketch. The single most important finding: **`lacing`
(`$PP/t/lacing`) already is the annotation substrate, and `reelee` already ships the
regenerate-without-losing-human-edits machinery on top of it** — the new library should own a
small *document* type and delegate everything below it.

---

## 1. Ground truth: what the POC's intermediate artifacts actually held

All paths below were read under the session scratchpad
`/private/tmp/claude-501/-Users-thorwhalen-Downloads/0f75703c-6761-4aa0-b796-aafe02c94155/scratchpad/vid/`.
I read every one of them.

> **Editor's note (added after this file was written).** That scratchpad has since been
> cleaned up. Everything cited here that still matters was copied into **`poc-reference/`**
> next to this file — see `poc-reference/README.md`. Map: `clips.json`, `crops.json`,
> `transcript.json`, `source.info.json` → `poc-reference/artifacts/`; the rendered page and
> `page/_script.js`'s `ROUTINE` (inside it) → `poc-reference/render/rendered-page.html`;
> `tools/*.py` → `poc-reference/tools/`. The large binaries (`source.mp4`, `audio16k.wav`,
> `beats.npy`, `feat.npy`, `media/*`) were not copied; the video is re-downloadable and
> `02-technical-recipes.md §1` has the exact command.

| file | shape | what it really is |
|---|---|---|
| `clips.json` | list of 15 objects | the **per-source-span** table (see below) |
| `crops.json` | `{clip_id: [x, y, w, h]}` | a **derivation recipe**, persisted so re-runs are stable and hand-overridable |
| `page/_script.js` `const ROUTINE = [...]` | 9 objects | the **step structure** — the actual document |
| `transcript.json` | whisper `{text, segments[408], language}` — `segments[i]` = `{id, seek, start, end, text, tokens, avg_logprob, no_speech_prob, words?}` | machine evidence |
| `beats.npy`, `feat.npy`, `audio16k.wav` | numpy | machine evidence (tempo → 129 bpm) |
| `source.info.json` | yt-dlp dump: `id=q_TUyxUhoEw`, `duration=651`, `fps=30`, `1280x720`, `chapters=None` | source descriptor |
| `media/{id}.{mp4,gif,jpg}` | 15 × 3 files | derived artifacts |
| `tools/*.py` | 14 scripts | the (unrepeatable) pipeline |

### 1.1 `ROUTINE` — the step structure (verified, quoted)

```js
{ n:6, eights:4, title:"Genou vers le bas",
  figs:[{k:"genou"}],
  subs:[{eights:4, label:"Main sur le genou, puis la main s'essuie le front"}],
  cue:"se hace difícil respirar" },
```

Nine entries. `sum(eights) == 44`, `44*8 == 352` beats — matches the page copy "44 × 8 temps,
~129 bpm". Fields observed: `n` (ordinal id), `eights` (**duration in the domain's own unit**),
`title`, `subs[]` (`{eights, label, cue?}` — sub-steps with their own domain durations),
`figs[]` (renderer asset keys), `cue` (a lyric landmark), `note` (an *open question*),
`hideSubs` / `shownSubs` (presentation overrides).

### 1.2 `clips.json` — one row per (step, source-span)

```json
{"id":"b4a","block":4,"kind":"main","src":"RT","start":103.3,"dur":5.2,
 "cap":"Jambes tendues bien écartées, le bassin pulse sur place…",
 "yt_expl":305,"yt_run":96,"tab":"hanches + regard","fig":"tete"}
```

**This is the file that proves the multi-span requirement.** Verified numerically:

- `src` ∈ {`RT`, `BD`}. `RT` rows have `start` ∈ [68.2, 201.8] (n=6); `BD` rows have
  `start` ∈ [231.3, 511.0] (n=9). The transcript's first line is *"je vais essayer de vous
  faire un filage d'abord"* — so **one source video contains two passes over the same
  routine**: a run-through with music (~45–215 s) then a spoken move-by-move breakdown
  (~220–520 s). `src` names which pass the extract was cut from.
- **Every row carries `yt_run` (∈ [51,193]) *and* `yt_expl` (∈ [228,515])** — a deep-link
  timestamp into *both* passes, regardless of which one the extract came from. A model with
  one span per step loses half of this outright.
- `start`/`dur` ≠ the step's span. b2: `yt_run=96` but the extract starts at `68.2`. The
  extract is a *chosen excerpt* inside (or near) the step's span, picked for how it looks in a
  loop. Two different things, both needed.
- `block` is the join key back to `ROUTINE.n`. 9 steps → 15 rows: 6 steps have a second row
  (`kind:"alt"`) which is sometimes a sub-step (b5/b5b = the two `subs` "d'un côté"/"de
  l'autre côté"), sometimes an *optional variant* (b6b, "Facultatif — si tu le sens"), and
  sometimes a second camera angle on the same move (b9b, "le lancer de bras en gros plan").
  Do not assume alt ↔ sub-step.
- `cap` (per-span prose) differs from `ROUTINE.subs[].label` (per-sub-step prose) which differs
  from `title`. **Descriptions attach at three levels, and one of them is the span, not the
  step.**
- `fig` duplicates `ROUTINE.figs[].k`; `tab`, `fig`, and the hue ramp in `_script.js` are pure
  renderer concerns.

### 1.3 The pain the POC actually hit (design pressure, not speculation)

1. **Two hand-maintained SSOTs.** `ROUTINE` (in JS) and `clips.json` (in JSON) both describe
   the same nine steps, joined by an integer. `tools/build_page.py` reconciles them at build
   time and *rewrites `ROUTINE` with string replacement*. This is the single strongest argument
   for one document.
2. **Regeneration destroyed edits.** `build_page.py` literally does
   `script.replace('note:"À remplacer par les 1ers déhanchés ?"', '')` — human/AI decisions
   ("what the video settles") were applied by patching generated text. There is no lock, no
   provenance, no way to re-run analysis without redoing this by hand.
3. **`shownSubs` — presentation leaking into structure.** Block 9's `subs` is literally
   `[avancer, lever]` repeated 4×, and `shownSubs` is a hand-written collapsed view of it.
   The structure wanted a `repeat`, not a display override.
4. **`note` fields are open questions**, and the page renders a resolved list ("Ce que la vidéo
   tranche"). Uncertainty and its resolution are first-class content, not scratch.
5. **`crops.json` exists because auto-crop needed to be overridable.** Derivation *parameters*
   had to be persisted separately from the derived file.

---

## 2. `lacing` — the annotation substrate (VERIFIED, use it)

`$PP/t/lacing`, branch `main`, **v0.0.34**, MIT,
deps `pydantic>=2.6, intervaltree>=3.1, argh, dol`. I imported it and ran it:

```python
>>> from lacing import TimeInterval
>>> TimeInterval.from_seconds('231.3','236.3', rate=1000).to_wire()
{'start': {'v': 231300, 'r': 1000}, 'end': {'v': 236300, 'r': 1000}}
```

Its own one-line summary: *"A standoff, interval-keyed annotation system… a
`MutableMapping[TimeInterval, list[Annotation]]` facade with rational time, ELAN-style tier
stereotypes, and Allen's interval algebra."* Status per its README: Phase 0–2 complete;
frontend on the roadmap. This is **not** a toy — `reelee`'s `pyproject.toml` pins
`lacing>=0.0.31`.

### 2.1 The types you get (real signatures, `lacing/model.py`, `time.py`, `tier.py`, `artifact.py`)

```python
RationalTime(value: int, rate: int = DEFAULT_RATE)          # .from_seconds(str|Fraction) raises on lossy
                                                            # .from_seconds_lossy(..., mode="round"|"floor"|"ceil")
TimeInterval(start: RationalTime, end: RationalTime)        # half-open; .to_wire() -> {'start':{'v','r'},'end':…}

class MediaRef(BaseModel):        kind="media";  asset_id: str;  interval: TimeInterval
class NodeRef(BaseModel):         kind="node";   scene_path: str; interval: TimeInterval
class AnnotationRef(BaseModel):   kind="annotation"; target_id: UUID; interval: TimeInterval|None
Reference = Annotated[MediaRef|NodeRef|AnnotationRef, Field(discriminator="kind")]

class Provenance(BaseModel):      # W3C PROV-O subset, inline on EVERY annotation
    was_generated_by: str         # "user:<handle>" | "agent:<model>@<hash>" | "adapter:<fmt>" | "processor:<n>"
    was_attributed_to: str
    was_derived_from: list[UUID | AssetId]   # AssetId = bare 64-hex SHA-256
    generated_at_time: RationalTime
    activity: str = "create"      # create|import|derive|migrate|infer

class Annotation(BaseModel):      # frozen, extra="forbid"
    id: UUID; tier: str; reference: Reference
    body: dict; body_schema_uri: str   # r"^annot://schema/[a-z0-9-]+/v\d+$"
    provenance: Provenance; confidence: float|None

class Artifact(BaseModel):        # content-addressed generated file
    asset_id: str                 # SHA-256 hex of the bytes, r"^[0-9a-f]{64}$"
    kind: Literal["image","video","audio","json","text","binary"]
    path: Path|None; url: str|None; bytes_size: int; duration_s: float|None; mime: str|None
    provenance: Provenance
    # Artifact.from_path(...) / .from_bytes(...) / .to_media_ref(interval) -> MediaRef

class Tier: name; stereotype: TierStereotype; parent: str|None; metadata: dict
TierStereotype = NONE | TIME_SUBDIVISION | INCLUDED_IN | SYMBOLIC_SUBDIVISION | SYMBOLIC_ASSOCIATION
```

`Artifact`'s module docstring is explicit about why it lives here: *"Multiple producers (falaw,
an, nw, artful, mixing) need to express 'I produced a file.' Putting `Artifact` in any one of
them forces a wrong-direction dependency."* The new library is another such producer.

### 2.2 The three digests — this is the regeneration answer, already solved

`lacing/digest.py` spells out a boundary you would otherwise get wrong (quoted):

> - `hash_bytes`/`hash_file` — SHA-256 over an **artifact's bytes**. *"are these two files the same file?"*
> - `annotation_etag` (under `lacing.server`) — BLAKE2b-128 over the **whole annotation**, `id` and `provenance` included. *"has this record been touched since I read it?"* … **deliberately unstable across regenerations**.
> - `annotation_value_digest` — SHA-256 over the **value**, `id` and `provenance` **excluded**. *"did the answer actually change?"*

> *"A regeneration that produces byte-identical content mints a fresh `uuid4` `id` and a fresh
> `provenance.generated_at_time`, so `annotation_etag` changes while `annotation_value_digest`
> does not. That difference is the entire point."*

Rule of thumb it states once: ***key the cache on inputs; address the value by content; record
both in the trace.***

Also present and relevant: `lacing/oplog.py` (`OpLogEntry{clock, operation, target_id, payload,
actor}`, `InMemoryOpLog`, `SqliteOpLog`, `replay_oplog`) — an append-only Lamport-clocked
mutation log that can reconstruct any past state; `lacing/quality.py` (κ, α, interval IoU);
`lacing/schema.py` (`register_body_schema`, `register_migration`, `export_json_schemas`
→ JSON Schema → Zod codegen upstream); adapters for TextGrid, WebVTT, W3C Web Annotation,
`.annot` SQLite, ELAN EAF, JAMS, Label Studio, **OpenTimelineIO**.

Existing body schemas you can reuse or copy: `lacing/bodies/word.py`
(`annot://schema/word/v1` = `{text, speaker}`) and `reference_lock.py` (a first-class
"this is canonical" decision — read it, the *pattern* is directly applicable to locking a
human-approved step name).

### 2.3 `nw` and `reelee` — the layer above (VERIFIED)

- `$PP/t/nw` — *"Narrative Workflow — the substrate audiovisual production apps are built
  on."* Owns `Genre`/`Template`, `prepare → plan → execute` with a cost gate, the `Transform`
  contract, and **`nw/freshness.py`**: `stale_after(project_root, changed_id)`,
  `all_stale`, `stale_verdicts`; **`nw/graph.py`**: `descendants_of`, `derived_from`,
  `annotations_at_tier`, `open_project_stores`. Freshness is computed by walking
  `provenance.was_derived_from`. Existing bodies: `nw/bodies/section.py`
  (`annot://schema/section/v1` = `{section_id, label, energy, mood}`) and `shot.py`
  (`shot/v1` = `{shot_id, section_id, render_strategy, environment, characters,
  description, camera, framing, notes}`). Also `nw/script_segmentation.py`, `nw/storyboard.py`.
- `$PP/tt/reelee` — `reelee/edits.py` is the production implementation of the requirement
  *"analysis is re-runnable, human edits must not be lost"*. Read its module docstring; the two
  load-bearing properties are quoted verbatim:
  > *"1. Invocations run in dependency order, against the current graph… 2. **A regenerated
  > annotation replaces the one it supersedes, adopting its `id`** (`_adopt_output_identity`).
  > The graph is a set of nodes whose values are re-derivable, not an append-only log."*

  And `overwritten_body_values(project, ann_id, body_patch) -> dict` — *"the pre-patch values
  of exactly the keys `body_patch` would OVERWRITE… Re-applying the result as a patch restores
  the body byte for byte"* — which is how an AI edit tool stays out of the destructive-tools
  list *on the merits*. `update_annotation_body` treats the envelope (`id`, `tier`,
  `reference`, `body_schema_uri`, `confidence`) as immutable and only merges `body` shallowly,
  bumping `generated_at_time` so freshness fires while preserving `was_generated_by` — *"a user
  edit isn't a re-derivation."*

**Take this whole mechanism. Do not re-derive it.**

---

## 3. `an` — NOT an annotation library (VERIFIED; the name misleads)

`$PP/t/an`, branch `main`. It is *"AI-driven structured animation in Python"* (renamed from
`anima`). Nothing interval-annotation in it. Two things are still worth stealing:

- **`an/ir/`** — a three-layer IR: `scene.md` (human Markdown) ↔ `ir/scene.json`
  (Pydantic SSOT) → disposable per-backend render code, with `an/ir/sync.py`
  (`markdown_to_ir`, `ir_to_markdown`, `sync`), `an/ir/validate.py` (`validate_schema` vs
  `validate_semantic`, split so callers pick strictness), and `an/ir/migrate.py` — a migration
  registry keyed on **`(kind, from_version, to_version)`**, because the repo versions two
  document kinds independently. Copy the migrate registry shape; **be wary of the bidirectional
  Markdown↔JSON sync** — it is the part most likely to bite you (see §6.4).
- **`an/iterate.py`** — free-text instruction → *typed JSON patches* on the IR
  (`{"op":"set"|"append"|"delete", "path":"timeline/0/duration", "value":…}`), validated then
  applied, with each iteration recorded in a decisions store. That is the right shape for
  "AI edits the document".
- `an/ir/assets.py` header notes a licence/rights field *"proposed upstream as
  `lacing.Artifact.rights` (lacing#34)"* — i.e. not yet in `Artifact`. Relevant here: the POC
  page carries a long attribution/rights paragraph about restyling to avoid redistributing the
  choreographer's likeness. **Rights are content in this domain.**

---

## 4. `walkthru` — the closest existing document shape (VERIFIED; strongly relevant, and nobody told you about it)

`$PP/t/walkthru`, branch `main`, MIT. *"Turn a sequence of application **commands** into an
**editable, re-renderable demo/tour artifact**… `walkthru` owns the **representation** (the
*Demo Document*) and the playback/capture engine. It does **not** render the final video…
*Owning representation, not pixels, is the load-bearing boundary of the whole design.*"*

That is the same boundary you are being asked to draw. Its schema
(`walkthru/core/schema.py`, Pydantic v2, JSON Schema at `schema/demo-document.schema.json`,
Zod codegen in `ts/`):

```python
class DemoDocument(_Base):
    id: Id
    meta: Meta
    sections: list[Section]
    tracks: Tracks


class Section(_Base):
    id: Id
    title: str | None
    steps: list[Step]


Step = Annotated[CommandStep | Beat, Field(discriminator="kind")]


class Tracks(_Base):
    cues: list[Cue]
    narration: list[NarrationSegment]
    camera: list[CameraKeyframe]


class Anchor(_Base):
    step_id: Id
    local_offset_ms: int


class Timing(_Base):
    duration_ms: int
    hold_after_ms: int | None
    wait_for: WaitFor | None
```

Conventions in its module docstring, all of which you should adopt verbatim:

- *"**camelCase on the wire, snake_case in Python.**"* (`alias_generator=to_camel`,
  `populate_by_name=True`, `extra="forbid"`).
- *"**Separate tracks.** … cues, narration, and camera live on their own `Tracks`, associated
  to steps **by anchor** — the anchor is the SSOT for that association (no denormalized
  `cueRefs` on steps; see `DECISIONS.md` §D8)."*
- *"**Discriminated unions, not flag soup.**"*
- *"**Reserved seams, not built features.** `CommandStep.next` is a type-level branching seam
  with no traversal in the engine."* (§D11, "inner-platform-effect guardrails".)
- Narration is the Descript model: *"text is the source of truth; audio and timing are
  regenerable"* — `NarrationSegment.audio_ref: AssetRef|None` is explicitly regenerable, and
  `CommandStep.poster` carries the same comment: *"a regenerable reference, not the SSOT."*
- `walkthru/core/timeline.py` `resolve_timeline(document) -> Timeline` computes absolute times
  from relative ones. **Absolute time is never stored.**

**Where it does NOT fit:** walkthru's steps *produce* output time (`duration_ms` of a demo it
will play); yours *consume* source time (spans in media that already exists). It has no
`source span`, no notion of several spans per step, and no domain-unit duration. Borrow the
shape, the conventions and `DECISIONS.md`; do not subclass the type.

---

## 5. Established formats — one line each, and whether they fit

Sourced from `~/.claude/skills/annotation-systems/SKILL.md` and its
`references/annotation-systems-survey.md` (58 citations), plus the format details already
implemented in lacing's adapters.

| format | gets right | fit |
|---|---|---|
| **W3C Web Annotation** (JSON-LD) | `(Body, Target)` as the universal primitive; 9 selector types; **`refinedBy` selector chains** (quote + position + range) that degrade gracefully when the source shifts | **export target, not internal model.** No temporal reasoning. lacing already has the adapter. |
| **Annotation Graphs** (Bird & Liberman) | nodes = time points, arcs = labeled intervals; tiers are just arc types; handles overlap + partial order natively | the correct *theory*; lacing is its Python instantiation. Don't re-derive. |
| **OTIO** | `RationalTime(value, rate)`; Timeline→Stack→Track→Clip; **markers attach to any item** with `marked_range` relative to the parent's time frame; adapter plugin system | **borrow the time type and the "clip has a `source_range` into media time" idea.** The whole editorial hierarchy is overkill. lacing has an OTIO adapter for hand-off to an editor. |
| **ELAN EAF** | five tier stereotypes; **TIME_SLOT indirection** — annotations point at named anchors, not embedded timestamps, so one edit moves every tier | stereotypes: yes, adopted verbatim by `lacing.TierStereotype`. TIME_SLOT indirection: **consider it for step boundaries** (see §6.3 open question). |
| **Praat TextGrid** | adjacency-complete interval tiers — every instant is in exactly one interval | too rigid: your steps have gaps (the video's non-routine talk) and your spans overlap across passes. |
| **JAMS** | `(time, duration, value, confidence)` observations; **per-namespace schemas inside a generic container**; multi-annotator native | **steal the per-namespace-schema pattern** — it is exactly `body_schema_uri`. |
| **brat standoff** | `.ann` character offsets; **discontinuous spans** via `;`-separated pairs | wrong medium, but the discontinuity lesson holds: a step can be interrupted (the choreographer stops mid-move to talk). |
| **CoNLL-U / BIO** | token-level tagging as a *training* representation | irrelevant to the document; possibly relevant to a step-boundary classifier's I/O. |
| **WebVTT / TTML chapters** | WebVTT is web-native, CSS-styleable, and a browser can consume it directly; TTML/IMSC is the broadcast heavyweight | **an output format**, and a good one: a chapter track falls straight out of the step list. lacing has a WebVTT adapter. Not an IR — one flat label per cue, no nesting, no sub-steps, no attributes. |
| **YouTube chapters** | dead simple: timestamps in the description, must start at `00:00`, ≥3 chapters, each ≥10 s | **an output format**, one line of rendering. `source.info.json` shows `chapters: None` — the source video has none, which is exactly the gap the library fills. |
| **Lottie / glTF / USD** | per-property keyframes; USD's *"any attribute can have time samples"* | out of scope for a step document; relevant only if a renderer animates figurines. |
| **the "AST" analogy** | separates *parse* from *interpret*; one tree, many back-ends; positions preserved so you can map back to source | **the right frame — with one correction.** A programming-language AST's spans are *into one text*. Yours are *into several media, in several roles*. The closer analogue is a **source map**: the tree is the artifact, and every node carries a set of back-references into the sources it came from. |

**Pitfalls the survey names that apply directly** (§I): inline annotations; **float time**; no
schema versioning; no provenance; **tight model/UI coupling**; *"custom format with no adapter
story — your annotations will outlive your tool."*

---

## 6. RECOMMENDATION

### 6.0 Two layers, one direction of flow

```
   ┌─ StepDocument (document.json) ────────────────────────┐   committed to git
   │  ordered steps · domain durations · source spans      │   hand-editable
   │  · artifact refs · cues · locks · open questions      │   THE CONTRACT for renderers
   └───────────────────────────────────────────────────────┘
              ▲  projection (regeneration, respects locks)
              │
   ┌─ lacing store (project.annot, SQLite) ────────────────┐   gitignored, regenerable
   │  every claim as an Annotation: transcript words,      │   THE EVIDENCE
   │  beats, passes, detections, step candidates,          │
   │  Artifact lineage, PROV-O provenance, op-log          │
   └───────────────────────────────────────────────────────┘
```

**Do not** make the document a thin view over the store, and **do not** make the store optional.
They answer different questions and have different lifetimes. The document is small, ordered,
readable, and diffable; a human and an LLM edit *it*. The store is large, unordered, and
machine-owned; it holds the transcript, the 408 whisper segments, the beat grid, the per-frame
YOLO boxes, and the lineage of every generated file. **The document is derivable from the
store; the store is not derivable from the document.**

Flow is one-way: analysis writes the store, a projection writes the document, human/AI edits
land on the document and are recorded as *locks*, the next regeneration re-projects and skips
locked paths. Nothing flows document → store. (This is deliberately simpler than `an/ir/sync.py`'s
bidirectional Markdown↔JSON round-trip — see §8.)

### 6.1 `StepDocument` — the schema sketch

Pydantic v2, `alias_generator=to_camel`, `populate_by_name=True`, `extra="forbid"` on every
model except the explicit `attrs` bags. Wire format JSON; JSON Schema exported for Zod codegen
(copy `walkthru/ts/scripts` and `lacing.schema.export_json_schemas`).

```python
# ── identity & units ────────────────────────────────────────────────────────────
Slug = Annotated[
    str, Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
]  # NOT a uuid4 — git-readable
Decimal = Annotated[
    str, Field(pattern=r"^-?\d+(\.\d+)?$")
]  # exact via Fraction; diffs cleanly


class Measure(_Base):
    """A duration in the DOMAIN's own unit. Never seconds unless the domain is seconds."""

    value: Decimal  # "2", "0.5", "12"
    unit: Slug  # "eight" | "bar" | "rep" | "second" | "page" | "beat"


class MetricGrid(_Base):
    """How the domain unit relates to wall-clock, when it does at all. Optional by design:
    a 'reps' domain has no grid; a dance routine does (this is what drives the metronome)."""

    unit: Slug  # "eight"
    subdivisions: int = 1  # 8 beats per eight
    tempo_bpm: Decimal | None = None  # "129"
    origin: Decimal | None = None  # seconds into `origin_source` where unit 0 starts
    origin_source: Slug | None = None


# ── sources & spans ─────────────────────────────────────────────────────────────
class Source(_Base):
    id: Slug  # "celine-yt"
    kind: Literal["video", "audio", "image", "document", "url"]
    uri: str  # https://youtu.be/q_TUyxUhoEw
    asset_id: str | None = None  # lacing.Artifact.asset_id of the local copy, if any
    duration_s: Decimal | None = None
    title: str | None = None
    attribution: str | None = None  # "Chorégraphie, danse et vidéo : Céline Pradeu"
    rights: str | None = (
        None  # this domain NEEDS this; lacing.Artifact.rights is only proposed
    )
    attrs: dict[str, Any] = {}


class SourceSpan(_Base):
    """ONE step's presence in ONE source, in ONE role. A step has a LIST of these."""

    source: Slug
    role: Slug = "performance"  # open vocab; seen: performance | instruction |
    # closeup | mirrored | reference
    start: Decimal  # seconds in the source's own media time
    end: Decimal
    excerpt: tuple[Decimal, Decimal] | None = (
        None  # loopable sub-window, chosen for looks
    )
    label: str | None = None  # POC `tab`: "hanches + regard"
    caption: str | None = None  # POC `cap`: prose about THIS span
    confidence: float | None = None
    attrs: dict[str, Any] = {}


# ── derived artifacts ───────────────────────────────────────────────────────────
class ArtifactRef(_Base):
    """WHAT, never HOW. The recipe lives in the lacing store."""

    role: Slug  # clip | gif | poster | thumbnail | waveform | audio
    asset_id: str | None = None  # 64-hex SHA-256 — the join key into the lacing store
    uri: str  # "media/b4a.mp4" — relative, deploy-portable
    mime: str | None = None
    width: int | None = None
    height: int | None = None
    duration_s: Decimal | None = None
    derived_from: Slug | None = None  # which SourceSpan.role it came from
    attrs: dict[str, Any] = {}


# ── cues (their own track, anchored) ────────────────────────────────────────────
class Cue(_Base):
    id: Slug
    kind: Slug  # lyric | count | audio-landmark | caption | warning
    text: str  # "se hace difícil respirar"
    anchor: "Anchor"  # step_id + offset in the domain unit
    duration: Measure | None = None
    source: Slug | None = None
    at_s: Decimal | None = None  # optional resolved time in that source
    attrs: dict[str, Any] = {}


class Anchor(_Base):
    step: Slug
    offset: Measure | None = None  # relative, in the domain unit. NEVER absolute.


# ── provenance & edit protection ────────────────────────────────────────────────
class Lock(_Base):
    """A human (or approved-AI) decision that regeneration MUST NOT overwrite."""

    path: str  # JSON pointer relative to the node: "/name", "/spans/1/caption"
    by: str  # "user:thor" | "agent:opus-5@<hash>"
    at: str  # ISO-8601 UTC, second resolution (diff-stable)
    was: Any | None = None  # the pre-edit value — makes the edit reversible
    reason: str | None = None


class Origin(_Base):
    """Back-reference into the evidence layer. Lets a renderer say 'why', and lets
    regeneration know what it may replace."""

    annotation_id: str | None = None  # UUID in the lacing store
    value_digest: str | None = (
        None  # lacing.digest.annotation_value_digest — 'did it change?'
    )
    generated_by: str | None = None  # "processor:segment_steps" | "user:thor"
    confidence: float | None = None


# ── the step ────────────────────────────────────────────────────────────────────
class Step(_Base):
    id: Slug  # "b4", "b4a" — stable across re-runs, human-meaningful
    name: str  # "Déhanchés"
    duration: Measure  # {"value":"8","unit":"eight"}
    description: str = ""
    spans: list[SourceSpan] = []  # >= 0; SEVERAL ROLES IS THE NORM, NOT THE EXCEPTION
    artifacts: list[ArtifactRef] = []
    steps: list["Step"] = []  # sub-steps: a step is a step
    repeat: int = 1  # block 9 = repeat 4 of a 2-substep cycle
    optional: bool = False  # b6b: "Facultatif — si tu le sens"
    variant_of: Slug | None = None  # b9b is another angle on b9, not a new step
    tags: list[Slug] = []
    questions: list["OpenQuestion"] = []
    origin: Origin | None = None
    locks: list[Lock] = []
    attrs: dict[
        str, Any
    ] = {}  # namespaced: attrs["render.web"] = {"fig":"soleil", "hue":48}


class OpenQuestion(_Base):
    """The POC's `note` fields, promoted. Uncertainty is content."""

    id: Slug
    text: str
    status: Literal["open", "settled", "dropped"] = "open"
    resolution: str | None = None
    evidence: list[SourceSpan] = []


# ── the document ────────────────────────────────────────────────────────────────
class StepDocument(_Base):
    kind: Literal["StepDocument"] = "StepDocument"
    schema_version: str = "0.1.0"
    id: Slug
    title: str
    lang: str = "en"  # BCP-47
    domain: Slug = "generic"  # "dance" | "recipe" | "workout" | "assembly" | …
    metric: MetricGrid | None = None
    sources: list[Source] = []
    steps: list[Step] = []  # ORDER IS SEMANTIC
    cues: list[Cue] = []  # separate track, anchored by step id (walkthru D8)
    questions: list[OpenQuestion] = []
    credits: str | None = None
    attrs: dict[str, Any] = {}
```

`resolve(doc) -> ResolvedDocument` is a pure function that computes absolute metric offsets and
(where a `MetricGrid` exists) wall-clock times — the analogue of
`walkthru.core.timeline.resolve_timeline`. **Absolute positions are computed, never stored.**

### 6.2 How each stated requirement is met

| requirement | where it lands |
|---|---|
| ordered steps: id, name, domain-unit duration, description, sub-steps, open attrs | `StepDocument.steps: list[Step]`; `Measure`; recursive `Step.steps`; `attrs` |
| one or more time spans in one or more source media | `Step.spans: list[SourceSpan]`, each `(source, role, start, end)` |
| **several source spans for the same step** | `SourceSpan.role` — the POC's `RT`/`BD` become `role="performance"` / `role="instruction"`; `yt_run`+`yt_expl` are two spans, `src` is which one carries the `excerpt` used for the clip |
| cues (lyrics / audio landmarks) | `StepDocument.cues`, anchored by `(step, offset)` |
| derived artifacts without knowing how they were made | `ArtifactRef` = role + `asset_id` + uri. The *how* is `lacing.Artifact.provenance.was_derived_from` and a `derivation-recipe` annotation (the POC's `crops.json`) in the store |
| survives re-generation; human edits not lost | `Lock` list per node + `Origin.value_digest`; regeneration is `reelee.edits.regen`'s algorithm — re-derive, **adopt the superseded id**, skip locked paths, and use `annotation_value_digest` to stop propagating when nothing changed |
| plain JSON, git-diffable | see §6.5 |

### 6.3 Projection contract: lacing tiers → document

Register these body schemas (`lacing.schema.register_body_schema`) in the new package's
`bodies/`, alongside the ones that already exist:

| tier | stereotype | parent | body schema | holds |
|---|---|---|---|---|
| `source.pass` | `NONE` | — | `annot://schema/media-pass/v1` | *"[45s, 215s] is a performance pass; [220s, 520s] is an instruction pass"* — **detecting this is a first-class Phase-1 job** and is what made the POC's dual timestamps possible |
| `step` | `NONE` | — | `annot://schema/step/v1` | one annotation **per (step, span)**; body carries `step_id`, `role`, `name`, `description` |
| `step.sub` | `INCLUDED_IN` | `step` | `annot://schema/step/v1` | sub-steps |
| `cue` | `INCLUDED_IN` | `step` | `annot://schema/cue/v1` | lyric/audio landmarks |
| `transcript.segment` / `transcript.word` | `NONE` | — | `word/v1` (**exists**) | whisper output |
| `beat` | `NONE` | — | `annot://schema/beat/v1` | `beats.npy` |
| `derivation` | `SYMBOLIC_ASSOCIATION` | `step` | `annot://schema/derivation-recipe/v1` | crop box, fps, palette — the *parameters*, so a re-run is stable and a human override survives |

`step/v1` body ≈ `{step_id, parent_step_id, role, name, description, duration_value,
duration_unit, ordinal}`. Note the shape mirrors `nw/bodies/section.py`'s
`SectionBodyV1{section_id, label, energy, mood}` — the `*_id` field is *"Stable id within a
project… **Distinct from the annotation id**"*. Same discipline: document ids are slugs,
store ids are UUIDs, and they are related by a body field, never conflated.

### 6.4 Regeneration algorithm (adapt `reelee/edits.py`, don't reinvent)

1. Re-run analysis → new annotations in the store, each with fresh `uuid4` + provenance.
2. For each, compute `annotation_value_digest`. Unchanged digest ⇒ **stop propagating**; the
   downstream artifacts are still valid and cost nothing.
3. Changed digest ⇒ the regenerated annotation **adopts the id of the one it supersedes**
   (`_adopt_output_identity`), so downstream `was_derived_from` edges keep resolving.
4. Re-project to a candidate `StepDocument`.
5. Three-way merge against the committed document: for every `Lock.path` on a node, keep the
   committed value and record `Origin.value_digest` of what was rejected. For everything else,
   take the new value.
6. Emit the diff. `nw.stale_after` tells you which artifacts to rebuild.

An LLM edit tool should be `an/iterate.py`-shaped — typed JSON patches
(`{"op":"set","path":"/steps/3/name","value":…}`) that are validated before application, that
write a `Lock` with `was` populated (so `overwritten_body_values`'s reversibility property
holds at the document layer too), and that append to the op-log.

### 6.5 Serialisation & git rules

- One `document.json` per guide, UTF-8, `ensure_ascii=False`, **2-space indent**, LF, trailing
  newline. French/Spanish text must be readable in a diff.
- Keys emitted in **declaration order** (Pydantic default) — stable across runs; never `sort_keys`
  for a model, since declaration order is the semantic order.
- **No floats anywhere on the wire.** Decimal strings (`"231.3"`) — exact via `Fraction`,
  no `0.30000000000000004`, and they diff as one token. Parse to `RationalTime` on load.
- **No absolute local paths, no per-run timestamps, no uuid4s** in the committed document.
  `Lock.at` is the only timestamp, and it changes only when a human edits.
- `ArtifactRef.uri` is relative to the document. `asset_id` is the durable identity.
- Sidecars: `project.annot` (SQLite lacing store, **gitignored**), `media/` (artifacts, either
  gitignored or LFS), `document.json` (committed). Per `~/.claude/skills/app-data-lifecycle`,
  the store and media belong under `~/.local/share/stepped/<project>/`, not next to the code.
- Export adapters ship from day one (the survey's *"custom format with no adapter story"*
  pitfall): **WebVTT chapters**, **YouTube chapter block**, W3C Web Annotation, and `.annot`.
  The first three are ~20 lines each and prove the AST/renderer split immediately.

---

## 7. What I deliberately left out, and why

| left out | why |
|---|---|
| **Branching / non-linear step graphs** (`next`, conditionals) | walkthru reserved exactly this seam (`CommandStep.next`) and its `DECISIONS.md` §D11 titles the entry *"Inner-platform-effect guardrails: reserve the seam, don't build it"* — the engine never traverses it. A step document is a **sequence**. Don't even reserve it until a second domain demands it. |
| **Multi-annotator distributions / soft labels / IAA** | the skill is right that disagreement is signal — for *corpus* annotation with many annotators. This is one author plus one agent. `lacing.quality` has κ/α when a labeling-tool product appears. `confidence` alone is enough now. |
| **Allen relations stored on the document** | they are *query-time* predicates over intervals, and `lacing.allen` already provides all 13 plus the composition table. Materializing them would be a denormalized cache with no invalidation story. |
| **A general interval store in the document** | that IS lacing. A second interval index in the document layer is the mistake this whole design exists to avoid. |
| **Absolute times / a resolved timeline** | computed by `resolve()`. Storing them makes every duration edit a whole-file diff (walkthru's *"there are no absolute timestamps"*). |
| **Presentation** — colors, tab labels, figurine keys, hue ramps, `hideSubs`/`shownSubs` | survey pitfall #5, *"tight model/UI coupling"*. All of it goes in `attrs` under a renderer namespace (`attrs["render.web"]`). `shownSubs` disappears entirely once `repeat` exists. |
| **Embedded media bytes / base64** | `asset_id` + relative `uri`. Content addressing is already the ecosystem's idiom. |
| **A full i18n layer** | `lang` on the document. A second language is a second document until someone actually asks; a `dict[lang, str]` on every text field would double the schema for a hypothetical. |
| **A `kind`/`type` discriminated union on `Step`** | the POC needed exactly one step type. `Beat`-like non-content steps (a title card, a rest) can be `Step(tags=["rest"], spans=[])`. Add the union at the third real variant, not the first. |
| **`TimeInterval` on the document's spans** | `{"start":{"v":231300,"r":1000},"end":…}` is correct and unreadable. Decimal strings on the wire, `RationalTime` in memory, one converter in the loader. Inside the lacing store, rational all the way. |
| **A DSL / Markdown authoring layer** | `an/ir/sync.py` proves it can be done and its bidirectional round-trip is the riskiest code in that package. JSON + typed patches first; add a Markdown face only after the JSON contract has survived two renderers. |

---

## 8. Open questions for the next agent

1. **Is `stepped` a new package, or a `nw` genre?** `nw`'s pitch is *"apps supply their own
   body schemas, Transforms, and genres — without modifying `nw`"*, and `reelee`/`muvid`/
   `braidio` are already built that way. If you register a `stepped` genre you inherit
   `prepare → plan → execute`, the cost gate, freshness, and the job layer for free — but you
   also inherit `nw`'s project-folder shape and its dependency weight. I could not settle
   whether the "guide" output fits `nw`'s `projection_entrypoint` model (it renders a *page*,
   not a video). **Decide this before writing a line of the model** — it determines whether
   `StepDocument` is a `nw` body schema or a standalone type.
2. **Is `StepDocument` one document or two?** I recommend one, but the POC's `ROUTINE` (stable,
   authored, short) and `clips.json` (churny, machine-derived, long) had genuinely different
   edit rhythms. A `document.json` + `spans.json` split would diff better under heavy
   re-analysis. I lean strongly to one file; I have not tested the diff behaviour on a real
   re-run.
3. **Should step boundaries use ELAN-style TIME_SLOT indirection?** Steps are adjacent — moving
   one boundary should move two steps. With inline `start`/`end` per span that is two edits
   that can drift apart. lacing does not currently expose named time anchors. Worth prototyping
   before v1 freezes the wire format.
4. **`SourceSpan.role` vocabulary.** I derived `performance` / `instruction` from one video.
   A recipe video has `overview` / `step-demo` / `plating`; a workout has `demo` / `real-time`.
   Is there a domain-independent core set, or is `role` fully open with a per-domain registry
   (the `nw.Genre` pattern)? Unsettled.
5. **How does `variant_of` differ from a sub-step, really?** b5/b5b are sub-steps; b6/b6b are
   an optional add-on; b9/b9b are two camera angles on one move. I gave you three fields
   (`steps`, `optional`, `variant_of`) for three cases and I am not confident that is the right
   cut rather than one `relation: Slug` field.
6. **Where does the steering prompt live?** The POC's third input (the prompt that shaped tone,
   language, and what to emphasise) has no home in this model. Candidates: a `Source` of
   `kind="document"`, a `StepDocument.attrs` entry, or a separate `guide-intent` annotation in
   the store. It matters for regeneration — re-running analysis with a changed prompt should
   invalidate descriptions but not span boundaries.
7. **Rights as a first-class field.** `an/ir/assets.py` says a rights field is *"proposed
   upstream as `lacing.Artifact.rights` (lacing#34)"* — not yet shipped. This domain needs it
   (the POC restyled every clip specifically to avoid redistributing the choreographer's
   likeness, and says so in the page footer). Either push lacing#34 or carry `Source.rights` +
   `ArtifactRef.attrs["rights"]` locally and migrate later.
8. **Verify `walkthru`'s status claims.** I read its README and `walkthru/core/schema.py` and
   confirmed the schema exists; I did **not** run its tests or check whether `schema/demo-document.schema.json`
   is current with the Pydantic source. Its `PLAN.md` and `DECISIONS.md` §D1/D8/D10/D11 are
   worth reading in full before you finalise conventions — several of your decisions are
   already argued there.
