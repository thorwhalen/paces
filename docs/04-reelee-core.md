# 04 — reelee core: what it is, what its genre/project/AST model really looks like, and what to reuse

**What this file is for.** You are about to design a library that turns instructional media (a
video of a choreographer + a doc + a steering prompt) into an intermediate annotated
representation and then renders that into guides. The user wants it to live in — or at least
integrate with — the `video_gen` federation whose top application package is **reelee**. This
file is a first-hand read of the reelee codebase (and its two siblings `reelee-org`,
`reelee-web`) so you do not have to rediscover: what reelee actually is, what a *genre* is
(it's an `nw` concept, not a reelee one), what a project is on disk, whether the
analysis/render split you want already exists (it partly does, and *not* where the docs say),
what the public surfaces are, and what you should and should not reuse. Every path here is
absolute and every claim is marked **[verified]** (I ran it or read the exact line) or
**[inferred]** (my judgement).

Repo state at time of writing (2026-08-28): `reelee` on `main`, clean tree, HEAD
`7480f1f`, 252 commits since 2026-05-14. `reelee-web` on `main`, HEAD `d022bc3`.
`reelee-org` is **not a git repo** at that path. **[verified]**

---

## 1. Orientation map — read these first

| Thing | Absolute path |
|---|---|
| reelee package | `/Users/thorwhalen/Dropbox/py/proj/tt/reelee/reelee/` |
| reelee agent guide (the densest single doc) | `/Users/thorwhalen/Dropbox/py/proj/tt/reelee/CLAUDE.md` (219 lines) |
| System overview (the vision; §5 layers, §6 "three-layer IR") | `/Users/thorwhalen/Dropbox/py/proj/tt/reelee/docs/reelee_system_overview.md` |
| Substrate handoff — what already exists below reelee | `/Users/thorwhalen/Dropbox/py/proj/tt/reelee/docs/substrate_readiness.md` |
| Gotchas from the substrate builder | `/Users/thorwhalen/Dropbox/py/proj/tt/reelee/docs/learnings_so_far.md` |
| Tested how-tos (executed in CI by `tests/test_how_tos.py`) | `/Users/thorwhalen/Dropbox/py/proj/tt/reelee/docs/how_tos/` |
| Dev skills (13) | `/Users/thorwhalen/Dropbox/py/proj/tt/reelee/.claude/skills/` |
| Handoffs (8, May–Aug 2026) | `/Users/thorwhalen/Dropbox/py/proj/tt/reelee/.claude/handoffs/` |
| Federation package manifest (absolute paths of all members) | `/Users/thorwhalen/Dropbox/py/proj/tt/reelee/docs/video_gen_manifest.json` |
| ADR — hosted MCP connector tool surface | `/Users/thorwhalen/Dropbox/py/proj/tt/reelee/docs/adr_connector_tool_surface.md` |
| Storage notes / migration plan | `.../docs/storage_architecture_notes.md`, `.../docs/storage_migration_plan.md` |

There is **no `misc/docs/` and no `adr/` directory** in reelee — ADRs are single files under
`docs/` (only one exists: `adr_connector_tool_surface.md`). `misc/` holds three dev scripts.
**[verified]**

---

## 2. What reelee *is*, in the author's own words

`README.md`:

> `reelee` is the workspace between an idea and a finished video.
>
> Bring whatever you have — a single sentence, a full script with storyboards and voice takes,
> or anything in between — and reelee organizes it, fills in what's missing, and helps you
> produce video without losing the pieces along the way. Today's AI video tools give you a
> finished clip and no handles on it. […] Reelee works the other way around: it builds your
> project as a network of editable pieces — treatment, scenes, characters, storyboards, voice,
> drafts, cuts — and keeps every piece reachable, swappable, and reusable.

`reelee/__init__.py` docstring:

> reelee is the top application package of the ``video_gen`` federation. Per the prime
> directive it stays *small*: the audiovisual substance lives in the focused packages below
> (``lacing``, ``falaw``, ``nw``, ``artful``, …) and reelee's own surface is orchestration,
> interfaces, and new artifact types.

`CLAUDE.md`, the **prime directive** — this is the single most important policy for you:

> Work *from* the top application package (reelee), but do **as little work as possible inside
> it**. Reusable substance belongs in the focused packages below. reelee consumes the substrate
> mostly *through* `nw`.
>
> When something doesn't obviously fit any existing package, **stop and tell the user** — it
> may warrant a new focused package.

The routing table that operationalises it is
`/Users/thorwhalen/Dropbox/py/proj/tt/reelee/.claude/skills/reelee-where-does-this-go/SKILL.md`.
Read it before you write a line: it will tell you that "segment a video into steps" is
`mixing`/`nw` territory, not app territory.

### The federation map (from `CLAUDE.md` + `docs/video_gen_manifest.json`) **[verified]**

| Layer | Packages (absolute paths under `/Users/thorwhalen/Dropbox/py/proj/`) |
|---|---|
| Application | `tt/reelee`, `t/muvid` (music video), `t/braidio` (audio "commentary weave") |
| Orchestration | `t/nw` — *Narrative Workflow*: Project, Transform, Genre, freshness, jobs |
| Capabilities | `t/lacing` (annotation graph, `Artifact`, provenance, exhibits), `t/falaw` (fal.ai; pure-data `Plan`, cost at plan time, SHA-256 cache), `t/artful` (storyboard panels), `t/an` (structured animation), `t/lookbook` (reference-image curation), `t/mixing` (audio/video editing), `t/burns` (Ken Burns motion), `t/foley` (ambient/SFX) |
| Helpers | `i/dol` (storage), `i/xdol` (`Registry`), `i/i2`, `i/qh` (Python→HTTP), `i/_zodals` |
| Frontend | `tt/reelee-web` (React/Vite; `_zodals` + `acture`), `tt/lacing-ui` |

Also present but **not in the manifest**: `t/burns`, `t/foley`, `t/braidio`, `t/yb`
(YouTube download/publish). All are real deps in reelee's `pyproject.toml`. **[verified]**

---

## 3. GENRE — the thing you asked about

### Where it lives

**Genre is an `nw` concept, not a reelee one.** The model is
`/Users/thorwhalen/Dropbox/py/proj/t/nw/nw/genres.py` (33 KB). reelee's binding is
`/Users/thorwhalen/Dropbox/py/proj/tt/reelee/reelee/genres.py` (16 KB) and is deliberately thin.
`nw/genres.py` docstring **[verified]**:

> A **Genre** is a pure-data descriptor of a *kind* of audiovisual production (music video,
> narrative video, commentary weave, music visualizer, ...). It is the first-class
> formalization of what nw informally called an "app": a bundle declared *over the substrate
> that already exists*, carrying no engine of its own. […] adding a genre is a **one-file
> registration**.
>
> nw ships **no** built-in genres: concrete genres register themselves from their own packages
> (``muvid``, ``braidio``) or from the studio host (``reelee``).

### What a Genre is, exactly

`nw.Genre` — a frozen dataclass, pure data, references substrate pieces **by name**:

```python
@dataclass(frozen=True)
class Genre:
    slug: str
    title: str
    description: str = ""
    body_schema_uris: tuple[str, ...] = ()      # lacing body schemas its artifacts validate against
    transform_names: tuple[str, ...] = ()       # nw.transforms entries forming its pipeline DAG
    strategy_names: tuple[str, ...] = ()        # optional nw.renderers strategies
    projection_entrypoint: str | None = None    # the final assemble/render step
    folder_conventions: Mapping[str, str] = {}  # compare=False
    status: str = "available"                   # "available" | "experimental" | "planned"
    templates: tuple[Template, ...] = ()        # named presets == "subgenres"
    intake_kinds: tuple[str, ...] = ()          # "what are you making?" answers that select it
    cost_profile: str | None = None             # routing tag for the cost gate ("per_clip", "tts")
    defaults: Mapping[str, Any] = {}            # "start from scratch" params; compare=False
```

`nw.Template` — the **subgenre**:

```python
@dataclass(frozen=True)
class Template:
    slug: str
    title: str
    description: str = ""
    params: Mapping[str, Any] = {}   # OPAQUE to the substrate; the owning app defines the meaning
```

The critical design point, straight from the `nw.genres` docstring **[verified]**:

> The substrate owns a Template's *identity* (slug/title/description) and carries a
> genre-defined ``params`` payload it does **not** interpret — the app that owns the genre
> validates and resolves those params (reelee reads ``output_intent`` / ``flavor``; braidio
> reads a ``format_id``).

`projection_entrypoint` must be one of the genre's own `transform_names` or `strategy_names` —
enforced in `__post_init__`, raises `ValueError`. **[verified]**

### The five registries and their contracts (`nw/genres.py`) **[verified]**

| Registry (`xdol.Registry`, `on_conflict="error"`) | Registrar | Contract |
|---|---|---|
| `nw.genres` | `register_genre(genre)` | the catalog |
| `nw.genre_resolvers` | `register_genre_resolver(slug, resolver)` | `(genre, template) -> params`; optional — reelee's params are static so it registers none |
| `nw.genre_initializers` | `register_genre_initializer(slug, fn)` | `fn(genre, template, project, params) -> None`; seeds a fresh project. Must confine writes to `project` so a failed create fully reverts |
| `nw.genre_project_factories` | `register_genre_project_factory(slug, fn)` | `fn(caller, project_id, *, title, template, params) -> dict` — per-caller project creation for the hosted connector |
| `reelee.flavors.flavors` | `register_flavor(Flavor)` | reelee-only style/model bundle |

Generic helpers: `nw.genre_catalog()`, `nw.describe_genre(slug)`, `nw.recommend_genre(kind)`,
`nw.resolve_defaults(genre, template)`, `nw.resolve_genre(genre, template)`,
`nw.initialize_genre(...)`, `nw.has_genre_project_factory(slug)`, `nw.create_genre_project(...)`.

Verified shapes (I ran these):

```python
>>> sorted(nw.genre_catalog()[0])
['cost_profile','defaults','description','intake_kinds','ready','slug','status','templates','title']
>>> nw.resolve_genre("narrative_video", "childrens_book")
{'genre': 'narrative_video', 'template': 'childrens_book',
 'params': {'output_intent': 'childrens_book', 'flavor': 'fal.children_book'}}
```

Note `resolve_genre` returns **either** a template's params **or** the genre's defaults —
never merged. That is why reelee's validator requires *both* keys on *every* template and on
the defaults (`_validate_reelee_params` in `reelee/genres.py:168`). **[verified]**

### What varies between genres vs what is shared

**Shared, genre-agnostic, serves every genre unchanged** (from the `nw.genres` docstring and
confirmed by reading the code): `nw.Project`, the `prepare → plan → execute` split,
`nw.stale_after` freshness, `nw.jobs`, the cost gate, the lacing annotation envelope, the
Transform Protocol and registry, provenance, `stale`/`regen`.

**Varies per genre:** the *set* of body schemas, the *set* of Transforms, the projection
entrypoint, intake keywords, cost profile, and the opaque `params` vocabulary — plus, at the
app layer, whatever the initializer chooses to seed.

**What reelee adds on top of the shared model** (`reelee/genres.py`):
- validation that every template's `params` carries `output_intent` (a `reelee.bodies.output_intent.OutputIntent` enum member) and `flavor` (a registered `reelee.flavors` slug);
- an initializer that writes the project's `output-intent` annotation (`reelee.edits.set_output_intent`);
- a per-caller project factory that builds inside `reelee.workspace.Workspace`;
- `_REELEE_GENRE_SLUGS` + `is_reelee_hostable(slug)` + `reelee_genre_catalog()` which decorates nw's catalog with `hostable: bool` and `hosted_by: str | None` (reelee#309).

### The only reelee genre that exists

`reelee.genres.NARRATIVE_VIDEO`, slug `narrative_video`. **[verified: `list(nw.genres)` returns
exactly `['narrative_video']` after `import reelee`.]** Its 5 templates ("subgenres") are
`storyboard_contact_sheet`, `cinematic_clip`, `childrens_book`, `motion_graphics`,
`ken_burns_documentary`. Its `transform_names` chain is:

```
treatment_to_beats.llm → beat_to_panel.segment → beat_to_panel.draft
  → panel_to_prompt.cinematic → panel_to_image.cinematic_flux
  → panel_to_clip.fal.default → clips_to_animatic.mixing.default   (= projection_entrypoint)
```

Other genres in the federation, registered from their own packages **[verified by reading]**:
`muvid.genre_music_video.MUSIC_VIDEO` (slug `music_video`, **zero Transforms**, engine-less,
templates are output-canvas presets) at
`/Users/thorwhalen/Dropbox/py/proj/t/muvid/muvid/genre_music_video.py`; and
`/Users/thorwhalen/Dropbox/py/proj/t/braidio/braidio/genre.py`.

> **This is the template for you.** `muvid`'s genre proves you can register a genre with **no
> nw Transforms at all** and still be a first-class citizen of the catalog, the connector's
> create path, and the FE genre picker. A `step_by_step` genre with a `dance_moves` Template
> (and `music_lesson`, `recipe`, `yoga_flow`, … siblings) is a one-file registration in *your*
> package. **[inferred, but directly modelled on a working precedent.]**

### How you would declare a "step-by-step / dance-moves" genre

```python
# stepped/genre.py  — one file, registered from YOUR package, importing only nw
from nw import Genre, Template, register_genre, register_genre_initializer

STEP_BY_STEP = register_genre(Genre(
    slug="step_by_step",
    title="Step-by-step guide",
    description="Segment an instructional video into named, timed steps and render a guide.",
    body_schema_uris=(STEP_BODY_SCHEMA_URI, ROUTINE_BODY_SCHEMA_URI, ...),
    transform_names=("video_to_steps.llm", "step_to_extract.mixing", ...),
    projection_entrypoint="steps_to_page.html",
    intake_kinds=("dance-routine", "recipe", "tutorial"),
    cost_profile=None,          # local ffmpeg = free; set a tag if you spend
    defaults={"guide_format": "interactive_web", "step_style": "loop_clip"},
    templates=(
        Template(slug="dance_moves", title="Dance routine",
                 description="8-count blocks, metronome transport, looping move clips.",
                 params={"guide_format": "interactive_web", "step_style": "loop_clip",
                         "beat_grid": "8_count"}),
        ...
    ),
))
register_genre_initializer(STEP_BY_STEP.slug, _seed_step_by_step_project)
```

Two things to decide up front, because reelee had to and got bitten:
1. **Validate your `params` at registration time, not at create time** — copy
   `reelee.genres._validate_reelee_params`. Its docstring says why: "Enforcing presence here
   moves the failure to registration (dev time) instead of project creation (runtime)."
2. **`params` is opaque to nw** — so your vocabulary is yours, but nothing downstream in nw
   will validate it. Make the initializer the one place it is read.

The end-to-end, CI-executed recipe for creating a project in a genre is
`/Users/thorwhalen/Dropbox/py/proj/tt/reelee/docs/how_tos/create_a_project_in_a_genre.md`.
Read it — its python blocks actually run.

---

## 4. The PROJECT model

### On disk

A project is a **folder**. `nw.Project.__init__` requires the folder to exist and to contain
`project.json`; it auto-migrates pre-graph projects and opens a `ProjectGraph`.
`nw.Project.init(root, *, title, song, force)` creates the conventional subfolders.
`reelee.Project.init(...)` extends it with `seed_prompts=True`.

I ran `python -m reelee demo <dir>` and this is the **real** tree **[verified]**:

```
.
├── project.json                 # the ProjectSpec (schema_version, title, song, characters,
│                                #  environments, sections, shots, global_style, notes)
├── project.annot.sqlite         # THE GRAPH — a lacing SqliteStore. This is the SSOT.
├── .nw/migrated_to_graph        # {"migrated_at": ..., "counts": {...}}
├── prompts/                     # 9 seeded Markdown PromptTemplates (reelee layer)
│   ├── beat_to_panel_draft.md  beat_to_panel_segment.md  extract_characters.md
│   ├── extract_color_script.md extract_environments.md   extract_props.md
│   └── plan_from_intent.md     storybook_journey_planner.md  treatment_to_beats.md
├── characters/  environments/  shots/  output/  lyrics/  script/  song/
```

Not created by `init` but created on demand **[verified by reading]**:
`storyboard.annot.sqlite` (scope `storyboard`), `lyrics/alignment.annot` (scope `alignment`),
`.reelee/artifacts/` (the filesystem `lacing.ArtifactStore`), `.reelee/agent.jsonl`,
`.reelee/saved-views.json`, `.reelee/config.json`, `key_policy.usage.jsonl`.

`nw.graph._scope_paths()` is the SSOT for the three store paths;
`nw.open_project_stores(root)` is the backend-aware way to walk them (there is a Postgres seam
in `nw/graph_backend.py`). **Never open `SqliteStore` paths directly** — reelee has zero direct
opens, everything goes through nw. **[verified]**

### `project.json` is NOT the SSOT

`nw/project.py` docstring says "``project.json`` is the SSOT" — **that sentence is stale**.
`read_spec` "synthesiz[es] from the graph for graph-native fields", `write_spec` calls
`_sync_sections` / `_sync_shots` / `_sync_character_refs` / `_sync_environment_refs` into the
graph, and `docs/learnings_so_far.md` §"Things I'd do differently" says the landed design is
"graph SSOT, project.json synthesized as metadata". **Trust the graph.** **[verified — the two
docs contradict each other and the code sides with the graph.]**

### The graph = "annotations, indices, ledgers, linked artifacts"

This is the part you care about. The data structures, exactly:

**`lacing.Annotation`** (`/Users/thorwhalen/Dropbox/py/proj/t/lacing/lacing/model.py`) — one
envelope, typed body, frozen pydantic, `extra="forbid"`:

```python
class Annotation(BaseModel):
    id: UUID
    tier: str                       # tier name (SqliteStore enforces an FK on this!)
    reference: MediaRef | NodeRef | AnnotationRef   # discriminated on `kind`
    body: dict                      # validated by body_schema_uri; string keys only
    body_schema_uri: str            # r"^annot://schema/[a-z0-9-]+/v\d+$"
    provenance: Provenance
    confidence: float | None
```

**`lacing.Provenance`** — W3C PROV-O subset, inline on *every* annotation:
`was_generated_by: str` (`user:<handle>` / `agent:<model>@<hash>` / `adapter:<format>` /
`transform:<name>@<impl_version>`), `was_attributed_to: str`,
`was_derived_from: list[UUID | AssetId]` (an `AssetId` is a bare 64-hex SHA-256 —
`partition_provenance_refs()` splits the union), `generated_at_time: RationalTime`,
`activity: "create"|"import"|"derive"|"migrate"|"infer"`.

A **real annotation** from the demo project **[verified]**:

```json
{"id": "4a64a441-…", "tier": "beat",
 "reference": {"kind": "media", "asset_id": "7f327854…3d",
               "interval": {"start": {"v": 0, "r": 24000}, "end": {"v": 0, "r": 24000}}},
 "body": {"beat_id": "b-001", "description": "The stairwell spirals up into the dark…",
          "characters": [], "environment": "", "scene_id": "sc-01", "shot_id": null,
          "order": 0, "granularity_hint": null, "semantic_tag": null, "transitions": []},
 "body_schema_uri": "annot://schema/beat/v1",
 "provenance": {"was_generated_by": "agent:reelee.importers.fountain",
                "was_attributed_to": "agent:reelee.importers.fountain",
                "was_derived_from": ["009b36e4-…"],
                "generated_at_time": {"v": 42910203646843, "r": 24000},
                "activity": "import"}}
```

Two things to notice, both load-bearing for you:
- **Time is `RationalTime` (`{v, r}` — value/rate), never floats.** Default rate 24000.
  `lacing.TimeInterval` wraps a start/end pair. For a dance routine keyed to a tempo this is
  *exactly* the right primitive and you should not invent your own.
- **A "timeless" annotation uses a sentinel zero-duration interval `[0,0)` on a `MediaRef`
  keyed by the project's own asset id.** The `reelee-add-body-schema` skill flags this as
  "acknowledged as accidental — if reelee accumulates many timeless kinds, raise a `NodeRef` /
  'no-interval' flavor with the user". **A step-by-step library is *all* timed annotations
  over one media asset, so this footgun mostly does not apply to you.**

**Body schemas** — 29 registered by reelee (`reelee/bodies/*.py`), plus nw's 5+ and lacing's
built-ins and artful's `storyboard-panel/v1`. A demo project's counts **[verified]**:
`beat/v1` ×8, `scene-breakdown/v1` ×3, `treatment/v1` ×1, **`verifying-trace/v1` ×11**.

**The ledgers** (append-only JSONL, deliberately *not* annotations):

| Ledger | Module | Path |
|---|---|---|
| Agent/app event log | `reelee/agent_log.py` | `<project>/.reelee/agent.jsonl` |
| Telemetry breadcrumbs (opt-in) | `reelee/telemetry.py` | project-local |
| Provider-key usage / billing | `reelee/key_policy.py` | `key_policy.usage.jsonl` (file-locked, tail-appended — explicitly *not* routed through the dol doc store, see `reelee/_storage.py`) |
| Decision log | `nw.Project.log_decision(kind, **payload)` | a `decision/v1` annotation tier |

**The indices:**
- `<data_root>/index/{stable_id}.json` — global stable-id → `{root, owner, …}` project index (`reelee.workspace.index_store`, a `dol.JsonFiles`).
- `lacing.ArtifactStore` catalog: `id → record`, plus a content-addressed blob store `hash → bytes`.
- `nw.genres` / `nw.transforms` / `reelee.flavors` — in-process `xdol.Registry` plugin indices.

**Freshness / verifying traces:** `verifying-trace/v1` annotations (tier `verifying-trace`) are
written alongside real writes; `nw.stale_after` uses them for a real verifying-trace early
cutoff. `nw.freshness` exports `FreshnessVerdict`, `all_stale`, `stale_after`, `stale_verdicts`,
`stale_verdicts_all`. **Known defect:** `reelee.edits.all_stale` is a *second, weaker*
definition (compares `generated_at_time` parent-vs-child, no early cutoff, reads a dangling
parent as fresh) — `CLAUDE.md` says it should become a wrapper over a whole-graph verdict
function in nw (nw#39), and is currently not. **[verified from CLAUDE.md line 167.]**

---

## 5. Does reelee already separate analysis from rendering? Is there an AST?

**Short answer: yes, and the AST is the lacing annotation graph itself — but reelee has no
named intermediate type between graph and renderer. Each renderer ships its own bespoke
"collect" function.**

### The analysis side: `nw.Transform`

`/Users/thorwhalen/Dropbox/py/proj/t/nw/nw/transforms/__init__.py`. Docstring:

> A :class:`Transform` generalizes :class:`nw.renderers.Strategy` […] Every "A → B" arrow in an
> audiovisual workflow — screenplay → treatment, beat → storyboard panel, panel → image, clips
> → animatic, shot → rendered clip — is a Transform.

Two-phase, and the split is the whole point:

```python
class Transform(Protocol):
    name: str                    # "<from_kind>_to_<to_kind>[.<flavor>[.<variant>]]"
    input_kinds: tuple[str, ...] # body-schema URIs; [0] is primary, rest are context
    output_kind: str
    is_batch: bool               # does plan() consume all of inputs.primary at once?
    impl_version: str            # behaviour version; salts the falaw cache key
    params_model: type           # a pydantic model → JSON Schema for MCP/CLI for free

    def plan(self, project, inputs: TransformInputs, *, params=None
             ) -> tuple[falaw.Plan, tuple[Annotation, ...]]: ...
        # PURE DATA. No billable calls. Returns a costed Plan + SKELETON output
        # annotations that already carry provenance (was_derived_from → inputs).

    def execute(self, project, plan, skeleton, *, use_cache=True, force=False,
                on_failure: Literal["halt","isolate"]="halt") -> TransformResult: ...
```

`TransformResult` carries `annotations`, `artifacts`, `cost_usd_actual`,
`cache_hit_savings_usd`, `has_unknown_costs`, `failed`, `blocked`, `is_complete`.

**35 Transforms are registered after `import reelee`** **[verified — I ran
`nw.list_transforms()`]**: `beat_to_panel.{segment,draft}`, `treatment_to_beats.llm`,
`panel_to_prompt.cinematic`, `panel_to_image.cinematic_flux`,
`panel_to_clip.{fal.default,kenburns}`, `panel_to_duration.{estimate,narration_led,target_duration}`,
`panel_to_{narration,voiceover,lipsync}.*`, `clips_to_animatic.mixing.default`,
`extract_{characters,environments,props,color_script}.llm.default`,
`continuity.{30_rule,axis_180,character_drift,environment_drift,lighting,time_of_day}`,
`character_to_modelsheet.cinematic`, `environment_to_ambient.foley.default`,
`narrative_to_storyboard.preflight`, `paginate.default`, `panel_alternates.regenerate_n`,
`style_decision.lock`, and 4 `shot_to_render_result.fal.*`.

### The render side: real, but ad hoc

The graph is consumed by **eight** distinct renderers, none of which share a formal IR:

| Renderer | Entry point | Its own "collect" step | Output |
|---|---|---|---|
| Storyboard documents (3 formats) | `reelee.export_storyboard` / `render_storyboard_html` (`reelee/storyboard_export.py`) | `collect_panel_views(project) -> list[PanelView]` | HTML (self-contained, data: URIs) → PDF via weasyprint |
| Picture-book PDF | `reelee/print_pdf.py` (44 KB) | its own | PDF |
| Ken Burns film | `reelee/kenburns_video.py` | reuses `collect_panel_views` + `ShotTimingStrategy` | mp4 (single `burns.ken_burns_film` encode) |
| Illustrated manual (storybook) | `reelee/storybook.py` | `steps_from_capture(dir)` **or** `steps_from_project(project)` → the *same* `(meta, [(step, before, after)])` intermediate | PDF |
| Narrated walkthrough video | `reelee/manual_video.py` | reuses `steps_from_capture` | mp4 |
| Artifact exhibit | `reelee.export_artifact_exhibit` → `lacing.render_artifact_exhibit` | walks annotations + `was_derived_from` + image refs directly | HTML / PDF / Markdown |
| FE JSON snapshot | `reelee.export_project_json(project)` → `{"project_root", "annotations": [model_dump(mode="json"), …]}` | `nw.iter_all_annotations` | JSON for reelee-web |
| JSON Schema dump | `reelee.export_schemas(dir)` | lacing's registry | `schemas/<name>/v<N>.json` + `index.json` → Zod codegen |

The **one place reelee explicitly names the two-adapters-one-render-core pattern** you want is
`reelee/storybook.py`:

> Two ways in, **one render core** (reelee#152). A storybook reaches the renderer either
> straight from a disk capture or from the project graph: `steps_from_capture` — the *disk*
> input adapter; `steps_from_project` — the *graph* input adapter. Both yield the same
> `(meta, [(step, before_path, after_path)])` intermediate with **resolved local image
> paths**, so the rendering code below is identical regardless of source.

And `storyboard_export.py` names the many-renderers-one-view pattern:

> The panel data is format-agnostic — every format consumes the same `PanelView` sequence. A
> format *is* its template. Adding one: 1. Drop `<name>.html.j2` in
> `reelee/data/storyboard_templates/`. 2. Register a `StoryboardFormat` in
> `STORYBOARD_FORMATS`.

`lacing.render_artifact_exhibit` is the purest form — its docstring:

> The annotation graph — annotations + `provenance.was_derived_from` + image references — *is*
> the "artifacts and links" model, so this runs on **any** lacing graph. […] The renderer is
> pure (graph → document) and has no knowledge of where the graph came from.

### The IR that was *designed* but never built

`docs/reelee_system_overview.md` §6 "Three-layer IR for renderable scenes" specifies:
*narrative layer* (structured Markdown/YAML) → *scene graph layer* (SSOT JSON,
renderer-agnostic, diffable) → *render code layer* (generated TS/PixiJS or Python, disposable).

**This is not implemented.** `grep -rl "scene_graph\|scene-graph" reelee/` returns nothing.
**[verified]** Only the narrative layer and the annotation graph exist. Treat §6 as design
intent, not as code you can build on. **[inferred but strongly supported.]**

### What this means for you

- You do **not** need to invent an AST. `lacing.Annotation` + tiers + body schemas + provenance
  edges *is* one, and it is already SQLite-persisted, provenance-tracked, freshness-aware,
  JSON-Schema-exportable, and consumed by five surfaces. **[inferred]**
- What reelee did **not** do, and what you should do, is name the projection between graph and
  renderer as a first-class, typed thing. `PanelView` and the storybook `(meta, steps)` tuple
  are the two half-built precedents. A `StepView`/`GuideView` frozen dataclass + a
  `Renderer` protocol registered in an `xdol.Registry` would be the missing piece the
  federation would actually welcome. **[inferred]**
- `Genre.projection_entrypoint` is the genre-level declaration of "the final render step" —
  but it must name a registered Transform/Strategy, so an HTML-page renderer would either have
  to be an `nw.Transform` or you leave the field `None` (muvid does). **[verified]**

---

## 6. Public API surface

### Python

`reelee/__init__.py` exports ~150 names. The load-bearing ones:

| Area | Names |
|---|---|
| Project | `Project` (extends `nw.Project`; adds `.prompts` MutableMapping + `seed_prompts`) |
| Genres | `genre_catalog`, `describe_genre`, `recommend_genre`, `reelee_genre_catalog`, `register_reelee_genre` |
| Import | `detect_and_import`, `detect_kind`, `import_screenplay`, `import_fountain_text`, `import_prose`, `import_treatment`, `import_beatsheet`, `import_transcribed`, `import_audio`, `import_pdf_screenplay`, `parse_fountain` |
| Orchestrate | `plan_from_intent(project, intent, *, model="sonnet", exclude=frozenset()) -> StagePlan`, `StageComplete`, `OrchestratorError`, `PromptTemplate`, `render`, `to_markdown`, `from_markdown`, `file_prompts` |
| Edit loop | `stale(project, changed) -> list[Annotation]`, `regen(project, changed, *, use_cache=True, force=False) -> RegenResult`, `regen_one`, `regen_all_stale`, `all_stale`, `update_annotation_body`, `delete_annotation`, `duplicate_panel`, `OperationEstimate` |
| Projects | `create_sibling_project(project, folder_name, *, name=None, genre=None, template=None) -> dict`, `list_sibling_projects`, `get_project_metadata`, `update_project_metadata` |
| Render/export | `export_storyboard`, `render_storyboard_html`, `collect_panel_views`, `STORYBOARD_FORMATS`, `PanelView`, `export_artifact_exhibit`, `export_project_json`, `write_project_json`, `export_schemas` |
| Storybook (step-by-step!) | `plan_journey`, `Journey`, `JourneyStep`, `CommandSpec`, `load_command_catalog`, `run_capture`, `capture_and_ingest`, `make_storybook_from_narrative` |
| Plans | `save_plan`, `load_plan`, `list_plans`, `replay_plan`, `ReplayResult` |
| Agent | `Agent`, `AgentSession`, `LLMClient`, `AnthropicLLMClient`, `Tool`, `build_default_tools`, `AgentEvent` |
| Resume | `resume_brief`, `resume_prompt_section` |

Signatures **[verified by `inspect.signature`]**:
```
create_sibling_project(project, folder_name: str, *, name=None, genre=None, template=None) -> dict
stale(project, changed: UUID | str) -> list[Annotation]
regen(project, changed: UUID | str, *, use_cache: bool = True, force: bool = False) -> RegenResult
plan_from_intent(project, intent: str, *, model: str = 'sonnet', exclude: frozenset[str] = frozenset()) -> StagePlan
```

### CLI — `reelee` (entry point `reelee.__main__:main`, built with `argh`)

Commands are plain functions in `/Users/thorwhalen/Dropbox/py/proj/tt/reelee/reelee/cli.py`
listed in `_dispatch_funcs`. **[verified by grep]**:

```
init  import-screenplay  status  transforms  plan  run  plans  replay  stale  regen
export-schemas  export-capabilities  export-json  mcp-serve  export-pdf  export-storyboard
render-video  import-storybook  export-manual-pdf  export-manual-video  make-storybook
demo  agent  backfill-artifacts  gc-artifacts  web-serve
```

The two you should run first: `reelee demo /tmp/x` (offline, no LLM, builds a real project) and
`reelee web-serve --root /tmp/x` (uvicorn on `127.0.0.1:8787`, OpenAPI at `/docs`).

### HTTP — `reelee.server.build_http_app(project_root, ...)`

`qh`-driven. `_build_routes()` (line 672 of `reelee/server.py`, 143 KB) returns a
`{closure: {"methods": [...], "path": "/..."}}` dict; `qh.mk_app` mounts it under
`path_prefix="/api"`. **99 routes** in that dict **[verified by counting `"path":` entries in
the returned literal]**, plus a handful of raw routes attached by `_attach_raw_routes`
(SSE streams, `/api/fal/proxy`, `/api/artifacts/{id}/bytes`, file uploads).

`CLAUDE.md` is emphatic: **"`reelee/server.py` `_build_routes` is the SSOT; don't enumerate
endpoints, or pin their count, in prose"** — so treat my 99 as a snapshot.

Notable route families: `/api/status`, `/api/dump`, `/api/transforms`, `/api/plans`,
`/api/costs`, `/api/stale/{changed_id}`, `/api/freshness`, `/api/resume`, `/api/genres`,
`/api/genres/recommend`, `/api/plan`, `/api/run`, `/api/regen*`, `/api/panels/{id}/*`,
`/api/journey/*`, `/api/jobs*`, `/api/stream/events`, `/api/agent/*`, `/api/telemetry/*`,
`/api/artifacts*`, `/api/preferences`, `/api/saved-views`.

Middleware stack: `_ByoCredentialMiddleware` (innermost, per-request fal key binding), then a
pure-ASGI per-request project router keyed on the `X-Reelee-Project` header. That header is
why project ids must be **ASCII** (`reelee/project_ids.py`, `MAX_PROJECT_ID_LENGTH = 255`).

### MCP — two builds, one tool surface

`reelee/mcp/` — `build_mcp_server(project_root, *, name="reelee", auth=None, middleware=None,
instructions=None, register_extra=None, on_duplicate=None, caller_workspace_root=None,
grant_store=None)`, `serve(project_root, transport="stdio")`, `build_http_app(...)` (OAuth-gated
Streamable HTTP via `py2mcp.http.mk_auth_provider`).

- **stdio build** (`reelee mcp serve`): one bound project, no auth, **plus** falaw's raw
  `falaw_*` media tools.
- **hosted per-caller connector** (`apps.thorwhalen.com/api/reelee_mcp/mcp`): per-caller
  project isolation via `_CallerProjectRouter` + a single `AuthzMiddleware` chokepoint;
  no falaw tools (ADR: `docs/adr_connector_tool_surface.md`).

**Every tool is namespaced `reelee_*`** (`reelee.authz.TOOL_PREFIX`), composed at registration
by `_wire_name`, with **no alias for pre-namespace names** (#293, breaking, landed 2026-08-16).
Three enum-parameterised routers collapse look-alike families: `reelee_catalog(kind=…)`,
`reelee_comment(action=…)`, `reelee_export_document(kind=…)`.

`reelee.capabilities.capability_manifest()` returns **73 rows** **[verified — I ran it]**, one
per registered tool:

```json
{"name": "reelee_advise_shots", "twin_command_id": "shots.advise", "costed": false,
 "destructive": false, "destruction_armed_by": null, "required_capability": null,
 "description": "…", "routes": []}
```

This is the machine-readable contract downstream consumers (tw_platform's connector metering,
reelee-web's `costed-tools.json` / `destructive-tools.json`) read instead of re-deriving.
CLI: `reelee export-capabilities`.

**Two independent approval predicates, deliberately not merged**: `reelee.authz.COSTED_TOOLS`
(spends money) and `reelee.authz.DESTRUCTIVE_TOOLS` (destroys work — costs $0.00, so no budget
gate can ever catch it). If you build any surface over this, keep them apart. **[verified from
CLAUDE.md lines 136-146.]**

### How reelee-web talks to reelee **[verified]**

- `reelee-web` has **no backend code of its own** (`CLAUDE.md` §"Backend wiring"). Its
  `server.py` mounts `reelee.server.build_http_app`.
- Dev: `VITE_REELEE_USE_HTTP=1 npm run dev` — Vite proxies `/api/*` to `http://127.0.0.1:8787`
  (`vite.config.ts:77-82`). Without that flag the FE falls back to **static JSON dumps** from
  `reelee export-json` / `export-schemas`.
- **Types are generated, never hand-written**: `npm run codegen` runs
  `python3 -m reelee export-schemas <reelee-web>/schemas/`, then `json-schema-to-zod` per URI
  in `schemas/index.json`, writing `src/types/generated/`. 46 schema directories are committed
  under `/Users/thorwhalen/Dropbox/py/proj/tt/reelee-web/schemas/`. Envelope types
  (`Annotation`, `MediaRef`, `Provenance`, `RationalTime`) are hand-written in
  `src/types/envelope.ts` on purpose.
- Every user action is an **acture command** (`src/commands/*.ts`, singleton registry in
  `src/commands/registry.ts`) — the SSOT for the action set, keybindings, and palette text.
  Exported to `schemas/commands.json` by `npm run export-commands`; that file is what
  `reelee.storybook_planner` plans journeys over.
- The two agent runtimes (`reelee.agent` over MCP tool names; the FE `ToolLoopAgent` over
  acture command ids) **do not share a registry** — they are reconciled by
  `BACKEND_TWINS` + the committed `schemas/destructive-tools.json` / `costed-tools.json`
  snapshots, with FE ⊇ backend enforced by test.

`reelee-org` is just the marketing site: a single self-contained static page
(`index.html`, `styles.css`, `main.js`, self-hosted fonts) served at `reelee.org`. **Nothing
to reuse there except the design tokens.** **[verified]**

---

## 7. What to REUSE — and what not to

### Reuse, no argument

| Use | Where | Why |
|---|---|---|
| **The annotation graph as your AST** | `lacing` via `nw.Project` / `nw.graph.ProjectGraph` | One envelope, versioned body schemas, inline PROV-O provenance, rational time, SQLite store with a Postgres seam, JSON-Schema export → Zod codegen for free. Reinventing this is months. |
| **`RationalTime` / `TimeInterval`** | `lacing.time` | Integer-tick time. A dance routine at a measured tempo is exactly this. Do not use floats. |
| **`nw.Transform`** for each analysis arrow | `nw.transforms` | plan/execute split, costed-before-spend, provenance-stamped skeletons, `impl_version` cache salting, `on_failure="isolate"` fan-out policy. |
| **Genre + Template** | `nw.genres` | Your "step-by-step" genre with "dance-moves" subgenre is a one-file registration; you inherit the catalog, the create path, the FE picker, and the connector for free. |
| **Freshness / regen** | `nw.stale_after`, `nw.stale_verdicts`, `reelee.edits.regen` | "Change the tempo, which blocks are now stale" is the same machine. Read `reelee/edits.py`'s docstring on **why regen converges** (topological order + identity adoption) before you build your own. |
| **`mixing`** for all video/audio surgery | `/Users/thorwhalen/Dropbox/py/proj/t/mixing` | **[verified signatures]** `crop_video(src, start, end, *, time_unit=…, output=…)`, `loop_video(src, n_loops)`, `concatenate_videos`, `change_speed`, `save_frame`, `make_thumbnail(video, *, at_time, text, size)`, `find_segments(audio, *, strategy=…)`, `extract_segments`, `transcribe(audio, …)` (ElevenLabs Scribe, word timestamps, `cache=`), `srt_for_media`, `detect_chapters(transcript, …) -> list[Chapter]`, `assemble_audio_track`, `text_to_speech`, `ken_burns_film`. This is 80% of your "auto-crop a per-block loop from the source video" work. |
| **`burns`** for pan/zoom | `/Users/thorwhalen/Dropbox/py/proj/t/burns` | `ken_burns_path` (pure `t -> Rect`), `ken_burns_film` (one encode, no concat seams). |
| **`yb`** for YouTube ingest | `/Users/thorwhalen/Dropbox/py/proj/t/yb` | `download_youtube_video`, `download_youtube_audio`, `youtube_video_info`, `set_chapters`. **[verified by import]** |
| **`falaw`** for any paid model call | `/Users/thorwhalen/Dropbox/py/proj/t/falaw` | Pure-data `Plan`, cost known at plan time, SHA-256 content-addressed cache, `execute_plan`. Never call a vendor eagerly. |
| **`lacing.render_artifact_exhibit`** | `lacing/exhibit.py` | Graph → HTML/PDF/Markdown with in-document provenance hyperlinks. Runs on *any* lacing graph. A free "show me the AST" debugging surface on day one. |
| **`reelee.storybook` as the shape to copy** | `reelee/storybook.py` + `manual_video.py` | It is *already* a step-by-step guide generator: `storybook/v1` + `storybook-step/v1` body schemas (`index`, `narration`, `command_id`, `params`, `before_image`, `after_image`, `collapsed`, `dispatch_ok`), two input adapters → one render core → PDF **and** narrated mp4. Your `step/v1` is a sibling of `storybook-step/v1`. |
| **`ShotTimingStrategy`** | `reelee/shot_timing.py` | `NarrationLedTiming` / `TargetDurationTiming` behind a Protocol, both pure. The pattern for "how long is each step on screen". |
| **`qh.mk_app`** for HTTP, **`py2mcp`** for MCP, **`argh`** for CLI | | The federation's fixed answers. `reelee/server.py`'s route dict and `reelee/cli.py`'s `_dispatch_funcs` are the working exemplars. |
| **`xdol.Registry`** for every plugin point | | ⚠️ **Gotcha, verified in `reelee/genres.py:118-123`:** `Registry.get` deviates from `Mapping.get` — with no explicit default it **raises `RegistryMissing`** instead of returning `None`. Use `if k in reg`. |
| **The dol JSON-doc store idiom** | `reelee/_storage.py::json_docs(root)` | 12 lines, gives you a `MutableMapping[str, obj]` over root-relative paths with `indent=2` JSON and mkdir-on-write. |

### Do NOT reuse

| Thing | Why not |
|---|---|
| **`reelee` the package, as a dependency** | It is an *application*, 1.6 MB of Python across 60 modules, with `server.py` at 143 KB, `edits.py` at 106 KB, `agent.py` at 70 KB, and hard deps on `braidio`, `foley`, `lookbook`, `artful`, `burns`, `mixing`. The prime directive says the app layer is where things *stop* being reusable. Depend on `nw` + `lacing` + `mixing`; register your genre into `nw.genres`. **[inferred, but it is literally the repo's own stated rule.]** |
| **`reelee.bodies.output_intent.OutputIntent` and `reelee.flavors`** | These are reelee's *look* vocabulary for AI-generated stills (`static_contact_sheet`, `childrens_book`, `ai_cinematic_clip`, style anchors, negative prompts, fal model ids). None of it means anything for a dance routine. Define your own opaque `params` vocabulary — that is exactly what `Template.params` being opaque is for. |
| **`reelee.edits.all_stale`** | The known-weaker second definition of stale (no early cutoff, mis-reads dangling parents). Use `nw.stale_verdicts` / `nw.stale_after`. |
| **`docs/reelee_dev_plan.md` and `docs/reelee_v0.3_roadmap.md`** | CLAUDE.md line 169: "predate the narrative→storyboard + Path-B work and are **not** the current 'what's next'; treat them as design history". |
| **§6 "Three-layer IR" of the system overview** | Designed, never built. No `scene_graph` anywhere in the code. |
| **`nw/project.py`'s "project.json is the SSOT" claim** | Stale; the graph is the SSOT. |
| **The reelee-web FE wholesale** | It is `UNLICENSED` (proprietary, all rights reserved), coupled to acture + `_zodals` + reelee's exact schema set, and its journey/checkpoint/cost-gate surfaces are narrative-video-specific. Reuse the *pattern* (JSON-Schema → Zod codegen; commands as SSOT) not the code. |
| **`reelee.agent`'s tool loop** | 70 KB, Anthropic-specific, entangled with reelee's authz sets and approval cards. If you need an agent loop, the user has an `ai-assistant-agent-runtime` skill for that decision. |

### The gap you will have to fill

**reelee has no video input path at all.** `grep -rl "youtube\|yt_dlp\|ytdl" reelee/` → nothing.
The importers (`reelee/importers/`) are: fountain, fdx, plain_text, prose, treatment, beatsheet,
pdf_screenplay, transcribed (text; `import_audio` runs STT via `aix.audio` first). There is **no
`import_video`**, no shot-boundary detection, no "segment a video into steps". **[verified]**

Per the prime directive that capability belongs **below** the app layer — most naturally in
`mixing` (which already owns `find_segments`, `detect_chapters`, `transcribe`, `crop_video`) or
in a new focused package. `CLAUDE.md` says: *"When something doesn't obviously fit any existing
package, **stop and tell the user** — it may warrant a new focused package."* That is a decision
to put to the user before you write it. **[inferred]**

---

## 8. Storage conventions

| Concern | Convention | Code |
|---|---|---|
| Small JSON documents | `dol` `MutableMapping` keyed by root-relative POSIX path, `indent=2` UTF-8, mkdir-on-write | `reelee/_storage.py::json_docs`, mirrors `nw.project._json_docs` |
| The annotation graph | `lacing.SqliteStore`, one file per scope: `project.annot.sqlite`, `storyboard.annot.sqlite`, `lyrics/alignment.annot` | `nw/graph.py::_scope_paths`, `nw/graph_backend.py` (Postgres seam) |
| Media blobs | `lacing.ArtifactStore` — a **facade over two injected dol `MutableMapping`s**: `catalog: id → record` and `blobs: hash → bytes`. It never constructs its own backend. | `lacing/artifact_store.py` |
| Which backend | **env only, decided in exactly one module**: `REELEE_ARTIFACT_BACKEND=fs\|aws` (default `fs` → `<project>/.reelee/artifacts`), plus `REELEE_S3_BUCKET`, `REELEE_S3_PREFIX`, `REELEE_S3_ENDPOINT_URL`, `REELEE_S3_REGION`, `REELEE_ARTIFACT_DB_URL`. Misconfigured cloud env **degrades to fs with a warning**, never crashes. | `reelee/storage_config.py` |
| Per-caller project data | `$REELEE_DATA_HOME` or `~/.local/share/reelee` → `{root}/projects/{email}/{project_id}/`, `{root}/projects/{email}/.active`, `{root}/index/{stable_id}.json` | `reelee/workspace.py` |
| Append-only ledgers | plain JSONL, file-locked, **explicitly not** routed through the doc store (a read-modify-write per line would be wrong) | `reelee/key_policy.py`, `reelee/agent_log.py`, `reelee/telemetry.py` |
| Artifact identity | `Artifact.id` is opaque (`art-{kind}-{nanoid}`, minted client-side before bytes exist); `content_hash` is a separate optional SHA-256. **The catalog is keyed by the opaque id, never by the hash.** | `reelee/artifacts.py` |
| Access control | `ArtifactRepository` is the single **policy-enforcement point**; the `PDP` is a pure `(principal, action, resource) -> bool` seam (`allow_all` in v1) | `reelee/artifacts.py` |

The three-way separation `reelee/artifacts.py` names — *data organization* (how bytes are laid
out, owned by `ArtifactStore`) / *infrastructure mapping* (where things are enforced, the
facades) / *access calculus* (who may do what, the PDP) — is a good frame to copy verbatim.

`xdol` is used **only** as `xdol.Registry` (the plugin pattern), not as a storage layer. **[verified]**

---

## 9. Stale, half-built, or abandoned — flagged

- **`reelee/docs/reelee_dev_plan.md`, `reelee_v0.3_roadmap.md`** — superseded, per CLAUDE.md.
- **§6 three-layer IR** in `reelee_system_overview.md` — never built.
- **"project.json is the SSOT"** in `nw/project.py` — contradicted by the code.
- **`reelee.edits.all_stale`** — second, weaker `stale`; blocked on nw#39.
- **`reelee.ai`** — the pluggable AI-provider facade is the one un-built Path-B item (`docs/cheap_ai_facade.md`).
- **ComfyUI as a second execution backend** — largest un-started workstream; plan of record `docs/comfyui_integration_plan.md`. Its §3 "D1–D5" defect list is genuinely useful reading: **all five were the same confusion — location addressing where content addressing is required.** D1–D4 fixed; **D5 (lacing#14, `was_derived_from` could not hold an `asset_id`) is fixed in the model** (`ProvenanceRef = UUID | AssetId` is in the code I read) but CLAUDE.md still calls it "the one remaining live defect" — the doc lags the code. **[verified discrepancy]**
- **`nw.Transform.execute(on_failure=…)`** — the Protocol is `runtime_checkable`, which compares *method names not signatures*, so `isinstance` passes and the `TypeError` arrives at call time. reelee has ~18 overrides that predate the keyword (reelee#299). **Do not iterate over arbitrary registered Transforms passing `on_failure`.** **[verified in nw's own docstring]**
- **`SqliteStore` enforces a foreign key on `tier`** — you must `store.add_tier(Tier(name=…, stereotype=TierStereotype.NONE))` before writing a new tier. `MemoryStore` does not, so a test passes on Memory and fails on Sqlite. **[verified in `reelee-add-body-schema` SKILL.md]**
- **Alternates persistence, comment resolve lifecycle, `ScopePicker`, print high-DPI/bleed** — listed as hidden stubs in CLAUDE.md.
- **FE journey launcher fails open** on a dry-run error (reelee-web#204); the checkpoint modal re-dispatches with no gate.
- **No cumulative spend bound** anywhere ($0.50 × 400 = $200) — #240 part 2, open.

---

## 10. Direction of travel (git log) **[verified]**

252 commits, 2026-05-14 → 2026-08-27. By month: May 136, Jun 32, Jul 28, Aug 56.

- **May** — the whole vertical slice: package shell, body schemas, Transforms, Fountain importer, orchestrator, CLI, MCP, HTTP, reelee-web, PDF export, Ken Burns video, storybook.
- **Jun–Jul** — narrative→storyboard pipeline (normalizers, `OutputIntent`, prompt slots, model sheets, reference locks, continuity), character consistency, cost honesty.
- **Aug — almost entirely surface hardening and multi-tenancy**: hosted per-caller MCP connector (#174), `AuthzMiddleware` chokepoint, destructive-tool gating with real runtime consumers (#270/#264), the `reelee_*` tool namespace + three routers (#293, breaking), the machine-readable capability manifest (#293/#265), HTTP↔MCP parity map (#255), genres-as-plugins (#229/#230/#231/#309), hermetic offline test suite + replay-only cassettes (#260/#269), ASCII project ids (#310).

**Read that as:** the domain model has been stable since June; the last quarter of energy went
into making the *surfaces* honest and multi-tenant. A new genre landing in this substrate today
is landing on settled ground. **[inferred]**

---

## 11. Testing conventions you will inherit if you live here **[verified from CLAUDE.md §Testing]**

- The offline suite (~1300 tests) reaches **nothing**, enforced by four autouse fixtures in
  `tests/conftest.py`: `_no_outbound_network` (a connect/DNS to any non-loopback raises *and* is
  recorded, so it fails even if something swallows the exception), `fake_assets`
  (`falaw.testing.FakeAssets`), `_isolated_falaw_cache`, `_offline_reference_curation`.
- Paid calls are marked `@pytest.mark.live_api` **and** memoized. **Replay is the default and a
  cache miss raises**; recording is `--record-cassettes` / `REELEE_RECORD_CASSETTES=1`.
- **"Key on the semantic input, never on a rendering of global state."** Memoizing
  `fal_client.subscribe` keyed every planner cassette on the *whole Transform registry*, so one
  unrelated registration re-spent money. They memoize at `decide_next_stage` instead. If you
  build a planner over a catalog, you will hit this exact bug.
- `docs/how_tos/*.md` python blocks are **executed in CI** by `tests/test_how_tos.py`. That is
  the cheapest doc-drift defence in the repo and worth stealing.

---

## Open questions for the next agent

1. **Where does video segmentation live?** reelee has no video input. Per the prime directive it
   is not app-layer code. `mixing` already owns `find_segments` / `detect_chapters` /
   `crop_video` / `transcribe`, so "segment an instructional video into named steps" is a
   plausible `mixing` feature — but the *naming/labelling* half is LLM work, which smells like a
   Transform in your own package. **This needs the user's ruling before code.**
2. **Is the new library a genre plugin, a sibling application package, or both?** muvid's
   pattern (own package, registers a genre into `nw.genres`, brings its own project factory,
   zero Transforms in the genre declaration) is the obvious model — but it means your project
   folders are `nw.Project`s and your AST is a lacing graph. Confirm the user wants that
   coupling rather than a standalone library that *optionally* exports to it.
3. **Does `Genre.projection_entrypoint` have to be an `nw.Transform`?** It is validated against
   `transform_names ∪ strategy_names`. An interactive-HTML-page renderer is not naturally either.
   Options: register it as a Transform whose output is an `artifact`; leave the field `None`
   (muvid does); or propose a `renderer_names` field to nw. Not settled.
4. **Should the graph→renderer projection become a named federation abstraction?** `PanelView`
   and storybook's `(meta, steps)` are two independent half-solutions to the same problem, in
   the same package. A `Projection`/`Renderer` protocol + registry looks like a genuine `nw`
   contribution — but that is a federation-level API decision, i.e. the user's.
5. **What is the body-schema URI namespace for a non-reelee app?** All existing URIs are
   `annot://schema/<kebab>/v<N>` in one flat global namespace registered into `lacing`. Two apps
   both wanting `step/v1` would collide (`register_body_schema` behaviour on conflict — I did not
   verify whether it raises). Check `lacing/schema.py` before you claim a name.
6. **Does anything already model a beat grid / tempo?** `lacing.RationalTime` gives exact
   rational time and `nw` has `lyrics/alignment.annot` (a whole alignment scope) — I did not open
   `muvid.align` or the alignment store to see whether a musical-beat/tempo annotation already
   exists. Worth ten minutes before inventing one.
7. **Where does the "hand-written aide-memoire doc" input go?** reelee's importers all produce a
   `narrative-source/v1` annotation then route into the prose/treatment path. A steering document
   for a step-by-step guide is neither prose nor a screenplay — is it a second input to the same
   Transform, or its own annotation tier that the segmenter reads as context? Undecided.
8. **`reelee.capabilities` claims to be the SSOT for out-of-repo consumers.** If your library
   ends up on the same hosted connector, you inherit an obligation to export a compatible
   manifest. I did not check whether `capability_manifest()` is reelee-specific or whether a
   federation-generic version exists.
