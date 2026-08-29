# 05 — The `video_gen` fleet: what already exists

**What this file is for.** You are about to design and build `stepped`, a library that
parses instructional media (a video + a doc + a steering prompt) into a time-aligned
annotation structure ("the AST") and renders that structure into guides. Almost every
mechanical thing you will need — interval annotations with provenance, ffmpeg wrapping,
word-level transcription, content-addressed artifact stores, a two-phase plan→execute
Transform contract, HTML/PDF projection from an annotation graph, a genre/template
registry, MCP + HTTP surfacing — already exists and is installed and importable on this
machine. This file inventories it so you neither rebuild it nor waste a day on a stub.
**Read §1 first: the POC you are generalising has committed source on disk, and it has a
predecessor app built by the same pipeline. Neither was in your brief.**

---

## 0. How I judged (verified vs inferred)

**Verified** (ran it / read it):

- All 21 packages below import cleanly from `~/.pyenv/versions/p12/bin/python`
  with cwd `$PP` = `$PP`, each resolving to the **local source
  tree**, not a PyPI wheel. 21/21 OK.
- Versions from each `pyproject.toml`; test-file counts from `find … -name 'test_*.py'`;
  last-commit dates/branches from `git log -1` / `git branch --show-current`. Every fleet
  repo is on `main`.
- All module paths, docstrings, class names and signatures quoted below were read from the
  files named.

**Inferred** (argue with it): the maturity labels and relevance scores. Basis: commit count
+ last-commit date, test-file count, whether docstrings describe *shipped* vs *planned*
behaviour, and whether the module graph has real depth.

**Two corrections to your brief.**

1. The member list you were given is not the `video_gen` workspace. The real file,
   `$PP/vs_workspaces/video_gen.code-workspace`, also contains **`reelee`**
   (`$PP/tt/reelee`) and **`reelee-web`** (`$PP/tt/reelee-web`). A parallel manifest at
   `~/.cache/reelee-review-main/docs/video_gen_manifest.json` adds **`wrapex`** (legacy,
   superseded by `acture`). `reelee` is the most relevant package in the fleet and was
   missing from your list. That manifest's own summary of the federation, verbatim:

   > "AI-enhanced audiovisual tools. Federation: application layer (reelee, muvid) →
   > orchestration (nw) → capabilities (lacing, falaw, an, lookbook, mixing, mv) →
   > helpers (dol, i2, qh, _zodals, wrapex). Work from the top app, delegate substance to
   > focused packages below."

2. The two packages most directly on point for `stepped` — **`kodokan`** and **`yb`** —
   are *not* in the workspace at all. See §1 and §6.

---

## 1. Start here: the POC's own source, and its predecessor

### 1.1 The Que Calor page is committed at `$PP/tt/tw_platform/apps/que_calor_dance/`

```
apps/que_calor_dance/
├── app.toml                    # enlace app manifest (see below)
└── frontend/
    ├── index.html              # 54,803 bytes — the WHOLE page, hand-authored, no build
    ├── icon.png
    └── media/                  # 17 MB: b1.{mp4,gif,jpg} … b9.{mp4,gif,jpg}, og.jpg,
                                #   og-square.jpg, icon-192.png, favicon-64.png, …
```

`index.html` is a single self-contained file: CSS custom-property tokens
(`--ink/--paper/--sun/--rose`, Anton/Karla/DM Mono from Google Fonts), then markup, then
inline JS. Its interactive element ids are `play, reset, bpm, bpm-val, count, pips, grid,
now-next, now-title, ribbon, recap, sound` — i.e. a transport with BPM control, an 8-count
pip row, a block grid and a now/next readout. Three media derivatives per block
(`mp4` loop, `gif` fallback, `jpg` poster).

`app.toml` is the design brief for the whole POC, in the author's own words. Quoted in
full because it settles several questions you would otherwise re-litigate:

> "Static, frontend-only: an index.html plus ~3 MB of short looping mp4 extracts and one
> 4.7 MB full run-through. No backend, no npm build — auto-discovered through platform.toml
> `apps_dirs`, mounted at /que_calor_dance/.
>
> The media is COMMITTED on purpose: git is its source of truth, which is the case
> ADR-0001's guard explicitly sanctions (deploy.py `_check_no_conflated_data`) and what
> makes the `--delete` on frontends/ correct for it. It is page content, not runtime data —
> so no `[data]` section and no cmd-push-data.
>
> The page carries `<meta name="robots" content="noindex">` and credits the choreographer:
> the source video is unlisted, so this stays link-only. **The extracts are also stylized
> (cartoon render + anonymised face, same pipeline as kodokan's) so her image is not
> redistributed as-is.**"

Description string: *"Chorégraphie Que Calor, bloc par bloc : le compte des 8 au tempo et
un extrait vidéo par mouvement."* — nine blocks, 44 × 8 counts.

**There is no generator.** The page is hand-authored HTML with no template, no JSON index,
no build script anywhere in `tw_platform`. `grep -rl 'que_calor'` over the whole repo hits
only `app.toml`. Producing that generator *is* `stepped`'s job.

### 1.2 The predecessor: the kodokan web app — same shape, with a JSON index

`$PP/tt/papp/migrated_apps/kodokan/` is an earlier instance of exactly this output format,
and it *does* have a machine-generated index:

```
migrated_apps/kodokan/
├── app.toml, server.py, kdk_learning.py, kdk_stores.py, migrate_data.py
├── data/    catalog.json  throws.json  sets.json  vocab.json     # in git: "code-shaped"
├── frontend/ index.html, assets/
└── (clips live OUT of the app dir, in ~/.local/share/kodokan/clips)
```

`data/catalog.json` — 84 techniques, generated by
`$PP/t/kodokan/examples/export_webapp_data.py`:

```json
{"n_techniques": 84,
 "techniques": {
   "uchimatagaeshi": {
     "name": "Uchi-mata-gaeshi",
     "clips": [{"file": "clips/rzOSmEiuVtg.mp4", "videoId": "rzOSmEiuVtg",
                "source": "efficient_judo",
                "url": "https://www.youtube.com/watch?v=rzOSmEiuVtg&t=2s"}, …],
     "sources": ["efficient_judo", "kodokan_ijf"],
     "confusable": ["morotegari", "ogoshi", …]}}}
```

**That JSON is a first draft of your AST**: named item → N clips, each with a source video
id, a deep link with `&t=<seconds>`, and derived cross-item relations. Note the
lifecycle split, stated in `generate_webapp_clips.py`'s docstring and worth internalising:

> "Two outputs, two very different lifecycles — do not merge them: **clips** → the app's
> DATA root (`~/.local/share/kodokan/clips`)… Media: regenerable, big, not in git…
> **catalog.json** → the app's `data/` directory, which *is* in git. It is code-shaped:
> small, structured, reviewed in diffs, deployed with the code."

(Que Calor deliberately breaks that rule and commits its media — because 17 MB of page
content is not runtime data. `app.toml` says so explicitly.)

### 1.3 The stylize / anonymise pipeline exists — as two example scripts in `kodokan`

**`$PP/t/kodokan/examples/generate_stylized_clips.py`** is the pipeline `app.toml` names.
Its docstring is the spec:

> "Pipeline per clip (one demo repetition of one throw):
>  cut segment from the source video
>  → **B1 stylization** (`cv2.stylization` — painterly)
>  → **person segmentation** (YOLO11-seg, MPS) → replace background with two FLAT colours
>    (wall/floor sampled per clip) — deletes ALL logos + burned-in text
>  → **face transform** (insightface RetinaFace detection, gated to the person mask + short
>    hold; **AnimeGANv2 `face_paint` on a context-padded crop**, composited into a feathered
>    ellipse) — a cartoon face, not a blur"

Functions: `_load_models`, `_b1(frame)`, `_person_instances(fr, seg)`, `_head_band(mask)`,
`_flat_bg(frames, seg)`, `_faces(det, seg, fr, pm)`, `_anime_face(anime)`,
`_ellipse(shape, box, pad=0.12, feather=0.14)`, `_blur_bands(...)`,
`process_clip(models, src_video, start, dur, out_path, mode="animegan")`, `main()`.
Model weights at `~/kodokan_data/style_models/face_paint_512_v2_0.onnx`; ffmpeg at
`/opt/homebrew/bin/ffmpeg`; device `mps`; skip-existing so it is resumable.

**`$PP/t/kodokan/examples/generate_webapp_clips.py`** is the cutter: `_rep_segments(demos)`,
`_index_videos()`, `_blur_filter(source)` (gaussian-blur the burned-in technique name so
the flashcard answer is not readable), `_make_clip(src_file, source, start, dur, out_file)`.

**These are scripts, not library API.** They hardcode absolute paths
(`APP_DIR = Path("$PP/tt/papp/migrated_apps/kodokan")`),
`/opt/homebrew/bin/ffmpeg`, and `mps`. Promoting `process_clip` into a real,
parametrised `kodokan` (or `stepped`) function with an injectable model set is a
half-day of work and removes the single biggest "not built" item on your list.

---

## 2. The fleet at a glance

| Package | Path | One-line purpose (author's words where quoted) | Maturity | Relevance |
|---|---|---|---|---|
| **lacing** | `$PP/t/lacing` | "A standoff, interval-keyed annotation system… `MutableMapping[TimeInterval, list[Annotation]]` facade with rational time, ELAN-style tier stereotypes, and Allen's interval algebra." | **real** — v0.0.34, 87 commits, 33 test files, 8 round-trip adapters, SQLite+Postgres, FastAPI + MCP servers | **HIGH — this IS your AST substrate.** |
| **mixing** | `$PP/t/mixing` | "Tools for **video and audio editing** in Python — slicing, fades, audio replace/mix, Ken Burns, thumbnails, subtitles, speech-to-text + filler removal, TTS dubbing, and chapter detection." | **real** — v0.0.38, 94 commits, 29 test files, lazy-import facade, 5 Claude skills | **HIGH — ffmpeg + transcription + segmentation.** |
| **nw** | `$PP/t/nw` | "**Narrative Workflow** — the substrate audiovisual production apps are built on… `nw` owns the engine: the typed project facade, the `prepare → plan → execute` split with a cost gate, the Transform contract, an async job layer, a provenance graph with freshness queries, and QA reports." | **real** — v0.0.33, 77 commits, 21 test files | **HIGH — already the parse→AST→render architecture.** |
| **reelee** *(missing from your list)* | `$PP/tt/reelee` | "the workspace between an idea and a finished video… it builds your project as a network of editable pieces… and keeps every piece reachable, swappable, and reusable." | **real, most active** — 41.7k LOC, ~180 modules, 130 test files, tip 2026-08-27, 13 skills, HTTP + MCP | **HIGH — the reference implementation.** |
| **artful** | `$PP/t/artful` | "Storyboard data model and exporters — lacing-native panels along a timeline." | **early but complete for scope** — v0.0.10, 19 commits, 5 modules, 3 test files | **HIGH — closest existing "steps pinned to intervals" body schema.** |
| **walkthru** | `$PP/t/walkthru` | "Turn a sequence of application **commands** into an **editable, re-renderable demo/tour artifact**… walkthru owns the *representation* (the Demo Document) and the playback/capture engine. It does **not** render the final video." | **real (Python side)** — v0.0.18, 43 commits, 20 test files | **HIGH — nearest conceptual sibling; its `PLAN.md`/`DECISIONS.md` are a design log for your problem.** |
| **burns** | `$PP/t/burns` | "Ken Burns pan/zoom video effects… a clean, render-agnostic motion spec underneath so the same path drives the Python renderer here and the TypeScript one in `ts/`." | **real, small, finished** — v0.0.9, 19 commits, 9 modules | **MEDIUM — the "pure spec + two renderers" pattern in miniature; `salient_box` for auto-crop.** |
| **braidio** | `$PP/t/braidio` | "**Weave *commentary* — solo, duo, panel, debate, interview, documentary — with source clips into a production.**" | **real** — v0.0.21, 62 commits, 18 test files, on PyPI, live MCP connector, imported by reelee | **MEDIUM — the fleet's hardened YouTube ingest; a self-contained HTML timeline view.** |
| **muvid** | `$PP/t/muvid` | "Tools to make music videos — three ways… The AI pipeline orchestrates the local ecosystem (`falaw`, `lookbook`, `lacing`, `an`, `mixing`) into a song-to-video pipeline." | **real** — v0.0.32, 78 commits, 31 test files (~60 real modules; the 1.1M-LOC figure is fixtures + `misc/`) | **MEDIUM — `align.py` and `footage/edl.py` are shapes to copy.** |
| **falaw** | `$PP/t/falaw` | "Agent-friendly Python facade over fal.ai for generating and managing AI media (images, video, audio)." | **real** — v0.0.40, 95 commits, 36 test files, `Plan`/`execute_plan` + cost rollups + content-addressed cache | **MEDIUM — only if you generate media. `nw.Transform.plan()` returns a `falaw.Plan`.** |
| **illustration** | `$PP/t/illustration` | "Find **existing** images to illustrate narrated video — cross-modal text-to-image retrieval… Not an image *generator*." | **real** — v0.0.6, 18 commits, 22 test files, 4 providers, licence-first | **LOW–MEDIUM — only if a guide wants stock imagery per step.** |
| **lookbook** | `$PP/t/lookbook` | "Distill raw image pools into optimized, high-diversity reference sets for training personalized models." | **real** — v0.0.11, 28 commits, 11 test files, all 5 phases shipped, HTTP + MCP | **LOW — only `embedders/arcface.py` grazes your needs, and it detects, not anonymises.** |
| **an** | `$PP/t/an` | "AI-driven structured animation in Python. The user is the **director**; an AI agent is the **assistant orchestrator**; existing animation libraries… are the **executors**." | **real, large** — v0.1.78, 187 commits, 105 test files | **LOW — a whole animation stack you don't need. Its `SceneIR` is 10 minutes of prior-art reading on "authored Markdown ↔ validated JSON IR".** |
| **dol** | `$PP/i/dol` | "Base builtin tools make and transform data object layers (dols)… tools to make your interface with data be domain-oriented, simple, and isolated from the underlying data infrastucture." | **real, mature, zero-dep** — v0.3.65 | **MEDIUM — mandatory store abstraction.** |
| **xdol** | `$PP/i/xdol` | "Extended Data Object Layers - dol-based tools" | **real, small** — v0.1.12 | **MEDIUM — `xdol.Registry` is the fleet's standard plugin registry.** |
| **i2** | `$PP/i/i2` | "Core tools for minting code." | **real, mature** — v0.1.67 | **MEDIUM — signatures/wrappers for surfaces; `castgraph` for liberal inputs.** |
| **qh** | `$PP/i/qh` | "**Quick HTTP web-service construction** — From Python functions to production-ready HTTP services." | **real** — used by `reelee.server`, `lookbook.http` | **MEDIUM — the fleet's HTTP convention.** |
| **acture** | `$PP/tt/acture` | "a **development tool** for building… a command-dispatch architecture in TypeScript/React apps. Define an operation once as a command; it becomes a command palette entry, a keyboard shortcut, an AI tool call, an MCP server tool, a macro step, an e2e test action, an undo entry…" | **real** — v1.13, 19 npm + 1 PyPI package, 88 commits, tip 2026-08-27 | **MEDIUM — mandatory *frontend* convention; irrelevant until the SPA.** |
| **zodal** | `$PP/i/_zodals/zodal` | "Schema-driven affordances for collections, resources, and beyond. Declare your data shape once via Zod v4 schemas." | **early-but-real, dormant** — 22 commits, last **2026-07-14** (oldest tip in the fleet), 3 packages, 52 TS files | **MEDIUM (frontend only) — mandated, but unattended.** |
| **lacing-ui** | `$PP/tt/lacing-ui` | "React/TypeScript frontend for lacing — a standoff, interval-keyed annotation system for time-based media." | **early** — 11 commits, last 2026-08-15, 41 TS files, MSW-mocked by default | **MEDIUM — the half-built timeline editor for your AST.** |
| **reelee-web** *(missing from your list)* | `$PP/tt/reelee-web` | The reelee SPA. "There is no backend code in this repo." | **real** — 361 TS files, tip 2026-08-27 | **MEDIUM — the reference frontend + the codegen chain.** |
| **kodokan** *(outside the workspace)* | `$PP/t/kodokan` | "Study Kodokan Judo throws from video via body-pose analysis: download technique demonstrations, extract two-person skeletons, split each clip into its repeated demonstrations, visualize them, and compare/score demonstrations." | **real, dormant** — v0.0.18, 15 modules, 12 test files, last commit **2026-07-16** | **HIGH — the closest existing analogue to `stepped`, and the pipeline that made the POC's clips.** |
| **yb** *(outside the workspace)* | `$PP/t/yb` | "Streamline media publishing: **prepare a piece of media once, publish it anywhere**… plus a download module for pulling videos back down." | **real** — v0.1.8, 6 test files | **MEDIUM — the clean YouTube ingest entry point.** |

---

## 3. The architectural fact that should reshape your design

**`nw` already implements "Phase 1 produces an annotation graph; Phase 2 renders it", and
`reelee` runs it in production.** Your parsing/AST/renderer framing is the federation's
existing spine under different names:

| Your concept | Fleet's name | Where |
|---|---|---|
| The AST | a **lacing annotation graph** — standoff `Annotation`s over `TimeInterval`s in a per-project SQLite store, with `provenance.was_derived_from` edges | `lacing.store.SqliteStore`, `nw.graph.ProjectGraph` |
| A node type | a **body schema** — a Pydantic model registered at `annot://schema/<name>/v<N>` | `lacing.schema.register_body_schema`; `reelee/bodies/*.py` (35 of them) |
| A parse step | a **Transform** — `plan()` (pure data + skeleton annotations carrying provenance) then `execute()` (runs, writes, reports cost) | `nw.transforms.Transform` / `BaseTransform` |
| A renderer | a **projection entrypoint** on a **Genre** | `nw.genres.Genre.projection_entrypoint` |
| The kind of thing being made | a **Genre** + **Template** (pure data, registered from your package; `nw` ships none) | `nw.register_genre(nw.Genre(...))` |
| Incremental re-render | **freshness with early cutoff** — Salsa-style verifying traces; one digest compare instead of loading a 40 MB video | `nw.freshness.stale_after(project_root, changed_id)` |
| "Render the AST as a document" | `render_artifact_exhibit(annotations, out_dir=…, formats=("html","pdf","md"))` | `lacing.exhibit` |

A `stepped` genre registration would be one file:

```python
nw.register_genre(
    nw.Genre(
        slug="stepped_routine",
        title="Step-by-step routine",
        body_schema_uris=("annot://schema/routine-step/v1", ...),
        transform_names=("video_to_transcript.scribe", "transcript_to_steps.llm", ...),
        projection_entrypoint="steps_to_web_guide.html",
        templates=(nw.Template(slug="dance_routine", title="Dance routine"),),
    )
)
```

**Read before designing:** `$PP/t/nw/nw/transforms/__init__.py` (lines 55–300),
`$PP/t/nw/nw/genres.py`, `$PP/t/nw/nw/freshness.py`, and
`$PP/tt/reelee/reelee/transforms/beat_to_panel/segment.py` — a shipped "one input
annotation → N output annotations, LLM-driven, provenance-stamped" Transform, structurally
the same operation as "one instructional video → N routine steps".

The schema pipeline is settled, per `$PP/t/walkthru/DECISIONS.md` §D1:
**Pydantic (Python) is the SSOT → export JSON Schema → codegen Zod for TypeScript.**
Never hand-write the TS types. Reference implementation:
`reelee.exports.export_schemas(target_dir)` → `reelee-web/schemas/` → `src/types/generated/`.

---

## 4. HIGH-relevance packages: the concrete pieces

### 4.1 `lacing` — `$PP/t/lacing/lacing/`

Everything is `frozen=True` Pydantic v2.

| Path | Name / signature | Use it for |
|---|---|---|
| `time.py` | `RationalTime(value: int, rate: int = 1000)`, `.from_seconds(...)`, `.to_seconds()`; `TimeInterval(start, end)`, `.from_seconds(a, b, rate=…)`, half-open, `.duration`, `.shift(by)` | Time. **Never floats** — "Time in lacing is always rational, never float." `to_seconds()` is an explicit one-way escape hatch. |
| `model.py` | `Annotation(id: UUID, tier: str, reference: Reference, body: dict, body_schema_uri: str, provenance: Provenance, confidence: float|None)`; `.interval` property | The universal AST node. "One envelope, typed body… No polymorphic class hierarchy." |
| `model.py` | `MediaRef(asset_id, interval)` / `NodeRef(scene_path, interval)` / `AnnotationRef(target_id, interval)`, discriminated on `kind` | Point a step at `[t0,t1)` of the source video. `NodeRef.scene_path` is a slash-separated path — the hook for hierarchy. |
| `model.py` | `Provenance(was_generated_by, was_attributed_to, was_derived_from: list[UUID|64-hex], generated_at_time, activity)`; `partition_provenance_refs(refs) -> (uuids, asset_ids)` | Lineage. `was_generated_by` conventions: `user:<handle>`, `agent:<model>@<hash>`, `adapter:<format>`, `processor:<name>`. `activity ∈ {create, import, derive, migrate, infer}`. |
| `store/base.py` | `IntervalAnnotationStore` Protocol: `MutableMapping[TimeInterval, list[Annotation]]` + `.intersects/.during/.contains/.overlaps/.meets/.starts/.finishes/.equals(query)`, `.relate(...)`, `.by_tier(name)`, `.at_tier(name, query)`, `.add/.remove/.all/.extend`, `.tiers()/.add_tier/.get_tier` | Query the AST by time without writing interval math. Backends: `MemoryStore` (intervaltree), `SqliteStore` (R*Tree, the `.annot` file format), `PostgresStore` (GiST + EXCLUDE). |
| `tier.py` | `Tier(name, stereotype, parent, metadata)`, `TierStereotype` (the five ELAN ones — "names match ELAN exactly so EAF round-trips are trivial"), `validate_tier_constraint(...)` | Layers: `blocks`, `moves`, `counts`, `words`. Parent/child constraints come free. |
| `schema.py` | `register_body_schema(uri, model)`, `validate(body, uri)`, `json_schema(uri)`, `export_json_schemas(target_dir)`, `register_migration(...)`, `migrate(body, from_uri=…, to_uri=…)`, `migrate_to_latest(body, from_uri=…)` | Define node types, get JSON Schema for the Zod codegen, version them. |
| `artifact.py` | `Artifact` (Pydantic), `.from_path(...)`, `.from_bytes(...)`, `.to_media_ref(interval)`; `hash_file(path)`, `hash_bytes(data)` — SHA-256, **bare 64-hex** | Every generated file (cropped clip, poster frame, og image) is an `Artifact` with a content-hash identity. |
| `artifact_store.py` | `ArtifactStore(MutableMapping)` — a *catalog* (`id → record`) + a *blob store* (`content_hash → bytes`), both **injected** `MutableMapping`s. `.save(...)`, `.put_blob(data)`, `.put_blob_stream(chunks)`, `.get_blob(h)`, `.iter_blob(h)`, `.blob_path(h)`, `.has_blob(h)`, `.count_refs(h)`. Constructors: `.in_memory()`, `.from_directory(...)`, `.from_s3(...)`, `.from_sql(...)`, `.from_aws(...)` | **Your media asset store — built, and already S3-capable. Do not write another.** |
| `exhibit.py` | `render_artifact_exhibit(annotations, *, out_dir, formats=("html","pdf","md"), title="Artifact exhibit", image_resolver=None) -> list[Path]` | **Annotation graph → HTML today.** "HTML is the authored format; the PDF and Markdown derive from it so the three never drift." Images written content-addressed under `out_dir/images/`; PDF via weasyprint (the only engine that carries in-document anchors through as clickable links); MD via `dn.html_to_markdown`. |
| `tracks/subtitle.py` | `SubtitleBuilder(store, asset_id=…)` context manager with `.section(label, t0, t1)`, `.line(text, t0, t1)`, `.word(...)`; `SubtitleTrack.lines_in(a,b)`, `.words_in(a,b)`, `.sections_covering(t)`, `.all_lines/.all_words/.all_sections` | The `(sections, lines, words)` trio in **float seconds** with the `Annotation`/`MediaRef`/`Provenance` plumbing hidden. Copy it as `tracks/steps.py`. |
| `adapters/` | `load(source, format=None, …)`, `dump(store, dest, format=…)`, `register_adapter(...)`, `registered()`. Eight: `textgrid`, `webvtt`, `web_annotation`, `annot`, `eaf`, `jams`, `label_studio`, `otio` | Free I/O. **WebVTT out of your step index for free**; OTIO out for an NLE; Label Studio in for hand-correction. |
| `quality.py` | `interval_iou`, `boundary_iou`, `cohen_kappa`, `krippendorff_alpha` | Score auto-segmentation against a hand-annotated ground truth. |
| `oplog.py` | `OpLog`, `InMemoryOpLog`, `SqliteOpLog`, `replay(...)` | Undo/redo + time-travel over AST edits. |
| `cli.py` | `lacing convert / query / validate / migrate / list-formats` (argh) | Inspect `.annot` files while developing. |
| `server/` | FastAPI (`lacing.server:app`): REST CRUD + ETag + import/export + op-log + `/state-at` time travel; `server/mcp.py`: 10 MCP tools | If the AST should be editable over HTTP/MCP, done. |
| `processors.py` | `register_processor`, `run_sync`, `run_async` (+ optional Arq) | Registered analyses over a store; shipped: `low_confidence_review`, `detect_density_change_points`. |

Gotcha: `Annotation.body` keys **must be strings** (`_body_keys_must_be_strings`), enforced
at construction — a store round-trip would otherwise silently annihilate int keys (lacing#24).

### 4.2 `mixing` — `$PP/t/mixing/mixing/`

**Lazy by design**: `import mixing` pulls neither moviepy nor opencv.

| Path | Signature | Use it for |
|---|---|---|
| `transcript/scribe.py` | `transcribe(audio, *, api_key=None, model_id="scribe_v1", timestamps_granularity="word", tag_audio_events=True, diarize=False, language_code=None, extra_fields=None, timeout=600.0, cache: CacheArg=False, refresh=False) -> dict` | **Word-level transcription of the spoken breakdown.** ElevenLabs Scribe, stdlib-only HTTP. Returns `{"words":[{"text","start","end","type","confidence"},…]}`; non-word events (`type != "word"`) carry `(laughs)` etc. `cache=True` keys on SHA-256(audio bytes) + params — set it. Needs `$ELEVENLABS_API_KEY`. |
| `chapters.py` | `detect_chapters(transcript, *, duration=None, min_chapters=3, max_chapters=8, min_spacing=10.0, target_count=None, segment_fn=None, model=None) -> list[Chapter]`; `Chapter(start: float, title: str)`; `default_segment_fn` | **Closest existing "segment the breakdown into named blocks".** `segment_fn` is the DI seam: `(segments, target_count) -> [{"start": float, "title": str}]`. Eats a Scribe dict, a words list, SRT text, or cue dicts. Deliberately "target-neutral" — formatting is a publication layer's job. |
| `audio/segmentation.py` | `find_segments(audio, *, strategy="silence"|"energy_novelty"|"self_similarity"|"speech_music"|callable, min_segment_duration=0.0, max_segment_duration=None, merge_gap=0.0, pad_start=0.0, pad_end=0.0, **kw) -> list[Segment]`; `extract_segments(...) -> list[Path]`; `Segment(start, end, label, score)` with `.as_start_end()` / `.as_offset_duration()` | Unsupervised audio boundaries when there is no speech. `self_similarity` = Foote's checkerboard novelty (ICME 2000), the standard tool for continuous takes. |
| `audio/beats.py` | `beat_grid(audio, *, sample_rate, hop_length, start_bpm=120.0, backend="librosa") -> BeatGrid`; `BeatGrid(beat_times, downbeat_times, onset_env, onset_hop_s, sample_rate, tempo_bpm)`, `.to_dict()` | **The routine's measured tempo for the 8-count metronome — implemented.** `pip install 'mixing[beats]'`. **`downbeat_times` is always empty** on the only shipped backend (librosa has no downbeat tracker; madmom deliberately excluded for licensing) — you must find the "1" yourself. |
| `srt.py` | `Cue(index, start, end, text)`, `parse_srt`, `dump_srt`, `srt_time_to_seconds`, `seconds_to_srt_time`, `shift_srt_timestamps` | Canonical SRT; pure, dependency-free, the SSOT after three divergent reimplementations were consolidated. |
| `transcript/formats.py` | `words_to_srt(words, *, max_chars=80, sentence_endings=".?!")`, `words_to_srt_remapped(...)`, `words_to_prose(...)`, `remap_time_after_cuts(t, cuts)` | Scribe words → SRT / readable prose; keep timestamps honest after trimming. |
| `transcript/pipeline.py` | `remove_fillers(media, out_dir, …) -> FillerRemovalResult`; `build_cuts`, `keeps_from_cuts`, `apply_keeps`, `extract_audio` | End-to-end "extract audio → transcribe → detect fillers → ffmpeg cut → write transcripts". `extract_audio` alone is worth knowing. |
| `video/video_ops.py` | `Video(src, *, time_unit="seconds")` — `video[10:20]` is a lazy view, `video[100]` a frame array; `.save(output)`, `.save_frame(...)`, `.frames`, `.to_clip()`, `.fps`, `.duration`, `.frame_count`, context manager. Plus `crop_video(src, start, end, *, time_unit, output)`, `loop_video`, `change_speed`, `replace_audio`, `normalize_audio`, `concatenate_videos`, `overlay_ambient_bed`, transitions (`crossfade_transition`, `fade_through_black`, `overlap_blend`, `slow_motion_blend`, `trim_and_crossfade`) | **Per-block looping extract**: `crop_video(src, t0, t1)` → `loop_video(...)`. Note `crop_video` is **temporal**, not spatial (see §7). |
| `video/video_util.py` | `get_video_dimensions`, `resize_to_dimensions`, `normalize_video_dimensions` | Resize/normalize before concatenation. |
| `video/thumbnail.py` | `make_thumbnail(video, *, at_time=None, text=None, output=None, size=(1280,720)) -> Path` | Poster frame per block (`b1.jpg` in the POC); optional title over a dark gradient band. Defaults to 85% of duration. |
| `video/genai.py` | `generate_video(prompt, …)` via Google Vertex Veo — optional, `mixing[gen]`, explicitly *not* wired into the lazy facade | Escape hatch if fal isn't the right generator. |
| `egress.py` | `deliver(...)` / `write_egress(...)`; `is_path_output`, `is_sink`, `resolve_output_path` | **Adopt this convention.** "Every result-producing function takes one `output` argument whose *role* is constant and *type* is open": `None` → in-memory (object producers) or beside-input (file producers); path → write; directory → auto-name; callable → `output(result)`. |
| `util.py` | `has_ffmpeg() -> bool`, `require_package(name)`, `to_seconds(v, *, unit, rate)` | Startup preflight (its docstring warns that missing ffmpeg degrades *silently*); the fleet's lazy-heavy-import idiom. |
| `.claude/skills/` | `mixing`, `mixing-audio`, `mixing-video`, `mixing-transcript`, `mixing-dubbing` | The README says these are the intended agent entry point. Load them before writing calls. |

### 4.3 `nw` — `$PP/t/nw/nw/`

| Path | Name | Use it for |
|---|---|---|
| `transforms/__init__.py` | `Transform` Protocol: `name`, `input_kinds: tuple[str,…]` (first = primary, rest = context), `output_kind`, `is_batch`, `impl_version`, `.plan(...) -> (falaw.Plan, skeletons)`, `.execute(...) -> TransformResult`. Subclass `BaseTransform`. Register via `register_transform(name, impl)` or `@register_transform("a_to_b.flavor")`. Naming: `<from_kind>_to_<to_kind>[.<flavor>[.<variant>]]` | **Your parse steps.** "Every 'A → B' arrow in an audiovisual workflow… is a Transform." Skeletons carry provenance *before* execution, so a dry run shows what will be produced and from what. Registration refuses an empty `output_kind`. |
| `transforms/__init__.py` | `TransformInputs(primary, context: dict[str, tuple[Annotation,…]])`; `TransformResult(annotations, artifacts, cost_usd_actual, cache_hit_savings_usd, has_unknown_costs, failed, blocked, .is_complete)`; `FailedOutput(skeleton, status, reason, error, blocked_by)`; `OnFailure = "halt"|"isolate"` | Fan-out with per-item isolation: "with 200 panels, one rate-limited call discarding 199 paid renders is the failure mode this exists to prevent." |
| `transforms/__init__.py` | `transform_catalog()`, `list_transforms()`, `get_transform(name)`, `stamp_transform_identity(plan, transform)`, `DFLT_IMPL_VERSION` | The JSON-able capability surface an HTTP route / MCP tool builder / agent selects from. |
| `genres.py` | `Genre(slug, title, description, body_schema_uris, transform_names, strategy_names, projection_entrypoint, templates, intake_kinds, cost_profile, defaults, status, folder_conventions)`, `Template(slug, title, description, params)`, `register_genre`, `get_genre`, `genre_catalog()`, `describe_genre`, `recommend_genre(kind)`, `resolve_defaults`, `resolve_genre`, `register_genre_resolver/initializer/project_factory` | Declare "a stepped routine guide" as pure data. "`nw` ships **no** built-in genres… adding a genre is a one-file registration." The substrate owns a Template's identity; the app validates its opaque `params`. |
| `graph.py` | `ProjectGraph(project_root)` over `project.annot.sqlite`; `descendants_of(root, id)`, `derived_from(root, id)`, `annotations_at_tier(root, tier)`, `iter_all_annotations(root)`, `open_project_stores(root)`, `all_project_stores(root)`, `collect_orphan_traces(root)`; `StoredSection/StoredShot/StoredDecision/…` | Project-level AST reader/writer; walks provenance across *all* stores in a project. |
| `freshness.py` | `stale_verdicts(root, changed_id)`, `stale_after(root, changed_id) -> list[Annotation]`, `stale_verdicts_all(root)`, `all_stale(root)`, `FreshnessVerdict` | **Incremental re-render.** Build-Systems-à-la-Carte "verifying trace" rebuilder with Salsa backdating: "One 32-byte digest comparison replaces loading a 40 MB video, which is what makes cutoff free rather than pointless." |
| `project.py` | `Project` — folder facade: spec read/write/update, `character_dir`/`environment_dir`/`shot_dir`, `set_title`, `set_global_style`, `log_decision`, `read_summary() -> ProjectSummary`; `ResumptionBrief` ("where we left off": decision tail, what the last authored change reaches downstream, recorded spend, deterministic next actions, plus a `caveats` field for what those numbers do *not* know) | Project-is-a-folder with an agent-resumption story already worked out. |
| `script_segmentation.py` | `segment_script_into_panels(script, *, target_panel_count, llm=…) -> list[PanelProposal]`; `build_prompt(script, *, target_panel_count)` | **Directly reusable shape**: free-form prose → N proposals with descriptions and durations, LLM injected as a callable so tests use a deterministic stub. Pure — persisting is the caller's job. Explicitly "not *yet* a `Transform`". |
| `jobs.py` | `enqueue`, `estimate`, `list_jobs`, `get_job`, `cancel_job`, `to_dict`, `JobsConfig`, `Job/JobProgress/JobCost`, `DurationLearningMiddleware`, `predict_total_s` | Long, cancellable, resumable work with live progress + ETA + cost + idempotency, over `au.ThreadBackend`. You will want it the first time a 40-min video takes 12 minutes to parse. |
| `storyboard.py` | `open_storyboard(project)`, `save_storyboard(project, sb, *, panel_intervals)`, `storyboard_from_shots(project)`, `storyboard_db_path`, `project_asset_id` | The `artful` ↔ folder-project bridge; the wiring pattern to imitate. |
| `inspect.py` | `shot_report(...)`, `compose_report(...)`, `Gap`, `FrozenSegment` | QA over a timeline — where are the holes. |
| `bodies/` | `section`, `shot`, `decision`, `character_ref`, `environment_ref`, `render_result`, `genre_envelope`, `verifying_trace` | Eight substrate body schemas, registered on `import nw`. |

**Warning:** `nw/workflow.py` + `nw/renderers/` are the *shot* render unit, baking in
`ShotSpec` + an open-string `render_strategy` + `output.mp4`. Its own docstring (measured
2026-08-27) says they have **zero call sites outside `nw`** and "new callers should go
through the Transform registry instead". Do not model `stepped` on `nw.workflow` — and do
not delete it either; it is load-bearing *inside* nw.

### 4.4 `reelee` — `$PP/tt/reelee/reelee/`

The full working instance, 41.7k LOC. What to steal:

- **`bodies/`** — 35 registered body schemas (`beat`, `panel_draft`, `panel_prompt`,
  `panel_duration`, `panel_layout`, `narration`, `voiceover`, `clip`, `animatic`,
  `treatment`, `scene_breakdown`, `output_intent`, `pipeline`, `storybook`, …). Read five
  for the house style.
- **`bodies/beat_segmentation.py`** — "wraps a list of beat-ids that, together, constitute
  one *alternative* segmentation of the same narrative source. Multiple alternates may
  exist; exactly one is marked `active`… alternates are kept, never deleted." **You want
  exactly this** for "here are three candidate segmentations; the user picks one."
- **`bodies/storybook.py`** — `annot://schema/storybook/v1` + `annot://schema/storybook-step/v1`.
  `StorybookStepBodyV1(index: int, narration: str, command_id: str, params: dict,
  before_image, after_image, collapsed, dispatch_ok, …)`. **reelee already has a
  "sequence of narrated steps" AST** — but it is UI-tour-specific (an acture `command_id`,
  before/after screenshots). Precedent and pattern, not a schema you can reuse verbatim.
  Note the documented trick: "`before_image`/`after_image` hold a path relative to the
  capture manifest *today*; once persisted into the project graph they become artifact ids
  — same field, richer referent."
- **`storybook.py`** — the two-adapters-one-core pattern, stated outright: "Two ways in,
  **one render core**… `steps_from_capture` — the *disk* input adapter… `steps_from_project`
  — the *graph* input adapter… Both yield the same `(meta, [(step, before_path, after_path)])`
  intermediate with **resolved local image paths**, so the rendering code below is
  identical regardless of source." Plus `ingest_capture` (disk→graph, screenshots become
  content-addressed project artifacts), `list_storybooks(project)`.
- **`print_pdf.py`** — `render_manual_pdf(steps, *, title, intro=None, paper_size="A4",
  cover=True, director=None, project_label="storybook", out=None) -> bytes`. Consumes
  "step mappings / objects exposing `index`, `narration`, `command_id`, `before_image`,
  `after_image`, `collapsed`, `dispatch_ok`" with images already resolved to local paths.
  Also `render_pdf(project, …)` for the picture-book, with per-page layouts driven by
  `panel-layout/v1` annotations from the `paginate` Transform.
- **`storyboard_export.py`** — `PanelView` (frozen: `index, panel_id, caption, shot_id,
  framing, camera, transition_in, notes, image_path`), `StoryboardFormat(name, label,
  description, template, page_orientation)`, `STORYBOARD_FORMATS` (`film` / `marketing` /
  `childrens_book`), `collect_panel_views(project, image_resolver=…)`,
  `render_storyboard_html(project, *, format, title, subtitle, image_resolver) -> str`,
  `export_storyboard(...) -> bytes`. Templates: Jinja2 at
  `reelee/data/storyboard_templates/{_base,film,marketing,childrens_book}.html.j2`.
  **"The panel data is format-agnostic — every format consumes the same `PanelView`
  sequence. A format *is* its template."** Directly transplantable to "one step index,
  many guide formats". Adding one is documented as: drop a `.html.j2` in the templates dir.
- **`transforms/`** — 25+ shipped Transforms. Read `beat_to_panel/segment.py` (1→N, LLM +
  deterministic rule table), `normalizers/treatment_to_beats.py`, `panel_to_duration.py`,
  `clips_to_animatic.py` (a **mixing-only** Transform with a zero-call `Plan` — proof you
  can have free Transforms), `continuity/*` (7 rule modules with `local_cv` / `vision_llm`
  strategy variants).
- **`shot_timing.py`** — `ShotTimingStrategy` Protocol + `NarrationLedTiming` /
  `TargetDurationTiming` + `get_shot_timing_strategy(name, **config)`; `PanelInfo`,
  `PanelTiming`. Pure, no I/O, no LLM. "How long each panel holds" = "how long each step's
  clip loops".
- **`exports.py`** — `export_schemas(target_dir) -> list[Path]` (lacing body schemas *and*
  reelee's non-body wire models, one shared `index.json` discriminated by `kind`),
  `export_project_json(project)`, `write_project_json(project, out_path)`,
  `export_artifact_exhibit(...)`. **The codegen contract.**
- **`capabilities.py`** — `capability_manifest() -> list[dict]`: one machine-readable table
  of every tool's wire name, whether it spends money, whether it destroys work, its
  required capability and its browser twin. Written because three repos were re-deriving
  those facts by hand and one of them silently un-metered a whole family of paid tools.
- **`server.py`** (`build_http_app(project_root)`, qh-wrapped), **`mcp/server.py`**
  (`build_mcp_server(project_root)`, fastmcp, with authz / destructive / outpath
  middlewares), **`cli.py`**, **`walkthrough.py`** (`steps_for_journey(name)` — canonical
  step-by-step guidance served identically to MCP and HTTP).
- **`.claude/skills/`** — read `reelee-add-body-schema`, `reelee-add-transform`,
  `reelee-where-does-this-go`, `reelee-substrate-gotchas`. They are the distilled rules.

### 4.5 `artful` — `$PP/t/artful/artful/`

Five modules, exactly on point: panels along a timeline persisted as lacing annotations
(`annot://schema/storyboard-panel/v1`).

- `schema.py`: `PanelBody(panel_id, caption, framing, camera, transition, notes,
  images: tuple[PanelImage,…], …)`, `PanelImage(path|url, role, caption)`,
  `Storyboard(title, asset_id, style, panels)`, `ModelSheet`, `new_panel_id(prefix="p")`.
- `store.py`: `save_storyboard(sb, store, *, panel_intervals)`, `load_storyboard(store, …)`,
  `panel_intervals_from_panels([(id, t0, t1), …])`, `make_prov(was_generated_by, was_attributed_to)`.
- `exports.py`: `to_markdown(sb)` / `from_markdown(text)` — **round-trip-safe**
  ("`from_markdown(to_markdown(s))` preserves every field"), described as "the canonical
  'give an LLM a storyboard to read or write' format" — and `to_html(sb)`, a self-contained
  contact sheet.
- `shot_schedule.py`: `ShotScheduleBody` — the ordered, model-constraint-aware shot list
  *preceding* the panels.

**The Markdown round-trip is the most reusable idea here.** Your aide-mémoire input and
your LLM-authored step list can be the same round-trippable Markdown, with the annotation
store as the persisted form. `artful` is also explicit that it is **not** the renderer.

### 4.6 `walkthru` — `$PP/t/walkthru/walkthru/`

Read `PLAN.md` and `DECISIONS.md` first — two deliverables of a design log for "own the
representation, not the pixels", written *after* inspecting this exact ecosystem.

- `core/schema.py` — the **Demo Document**, Pydantic v2 SSOT, ~30 models
  (`DemoDocument, Meta, Section, CommandStep, Beat, Tracks, Timing, Anchor,
  NarrationAnchor, NarrationSegment, WordTiming, CameraKeyframe, AssetRef, TTS,
  Locator, Target, Rect, ScrollAnchor, ElementReady, NetworkIdle`, five `*Cue` types).
  Conventions worth copying wholesale, verbatim from the docstring:
  - "**camelCase on the wire, snake_case in Python**" — `alias_generator=to_camel` + `populate_by_name=True`.
  - "**Relative, anchor-based time.** Durations are integer **milliseconds**; there are *no absolute timestamps*. Cues, narration, and camera anchor to a `(stepId, localOffsetMs)` pair; global time is derived by composition."
  - "**Separate tracks.** Commands live in `sections[].steps`; cues, narration, and camera live on their own `Tracks`, associated to steps **by anchor** — the anchor is the SSOT for that association (no denormalized `cueRefs`)."
  - "**Discriminated unions, not flag soup.**"
  - "**Runtime gates are not timeline time.** `Timing.waitFor` tells a *live runner* when a step's effect has landed; the wall-clock it costs is never written back into the SSOT."
  - "**Reserved seams, not built features.** `CommandStep.next` is a type-level branching seam with no traversal in the engine."
  - `demo_document_json_schema() -> dict`; committed JSON Schema + fixtures at `$PP/t/walkthru/schema/`.
- `core/timeline.py` — `resolve_timeline(document) -> Timeline`, `iter_resolved_steps(document)`,
  `ResolvedStep/ResolvedCue/ResolvedNarration/ResolvedCamera`. "The single place that turns
  the relative SSOT into absolute milliseconds… every downstream adapter shares one timing
  model rather than re-deriving it." Step occupies `[start, start+durationMs)`, then `holdAfterMs`.
- `core/engine.py` — `play(doc, executor, observers)`, `record(...)`, `iter_events(...)`.
  Pure, async, every effect injected; sync-or-async observers awaited transparently.
- `adapters/export/json_target.py` — `to_json(document, indent=2)`, `JsonArtifactTarget`:
  "the frozen JSON projection — walkthru's primary renderer hand-off."
- `adapters/export/{webvtt,srt}.py` — `narration_to_webvtt(doc)`, `narration_to_srt(doc)`.
- `ecosystem/reelee/render_target.py` — `timeline_to_panels`, `timeline_to_plans`,
  `render_plans`, `render_demo_video`, `ReeleeRenderTarget`, `PanelPlan`. A worked example
  of mapping your document onto someone else's render contract *without* importing their
  internal model, with the reasoning written out ("Reconstructing that graph just to feed
  back data we already hold as a clean Timeline would bleed reelee's whole internal model
  across the firewall").
- `ports/__init__.py` — the `RenderTarget` / executor / waiter Protocols.

Note: the README defers the live capture/play engine to "`acture-walkthru`", which I could
**not** find. The equivalent that *does* exist is **`acture-capture`**
(`$PP/tt/acture/packages/capture`): "Drive a command-dispatch app through a **narrated
journey**, screenshot the UI **before and after each command**, and emit a **manifest** that
renders to an illustrated manual (PDF) or a narrated video." That manifest is what
`reelee.storybook.steps_from_capture` ingests.

---

## 5. MEDIUM-relevance packages: the concrete pieces

### 5.1 `burns` — `$PP/t/burns/burns/`
- `path.py`: `BurnsPath` (keyframes + easing; `.evaluate(t) -> Rect` for `t ∈ [0,1]`, pure,
  deterministic, frame-count-free; `to_dict`/`from_dict`), `ken_burns_path(index, *, style="push"|"drift", zoom, pan, easing)`,
  `Rect(x, y, w, h)` normalized to `[0,1]`, top-left origin.
- `content.py`: **`salient_box(image, …) -> Box`**, `content_aware_path(...)`,
  `content_aware_path_for(image, *, face_boxes=…, …)` — "keep the subject… and any injected
  face boxes framed". **Your auto-crop primitive** (stills; apply to a representative frame
  and reuse the rect for the clip).
- `render.py`: `ken_burns_video(image, path, *, duration, …)`,
  `ken_burns_film([(image, path, duration), …], …)` — single encode pass, no seams, optional audio.
- `ts/` — a TypeScript port (`kenburnz`) driven by the same JSON path spec. **Proof that
  "pure spec → two renderers" works in this fleet.**

### 5.2 `braidio` — `$PP/t/braidio/braidio/`
- `mcp/_media.py`: `download_audio(...)` via yt-dlp, with `SourceCredentials` (`.check()`),
  `classify_download_error(...)`, `as_tool_error(...)`, and typed errors
  `SourceAuthRequired` / `SourceCredentialsRejected` / `SourceUnavailable`. **The fleet's
  only hardened YouTube ingest**: it handles bot gates, a Netscape cookie jar at
  `<data root>/credentials/youtube-cookies.txt`, jar-expiry detection, and turns yt-dlp's
  one undifferentiated error string into causes that each name their own fix. Refresh
  procedure: `misc/docs/youtube_ingest_credentials.md`.
- `timeline.py`: `BeatSpan`, `TimelineBreakdown` (`.totals()`, `.shares()`,
  `.to_html(title)`), `build_timeline(...)`. **A self-contained HTML timeline view generated
  from a render ledger** — a small, readable Phase-2 model. "The render now *records* its
  timeline instead of anyone probing the output after the fact."
- `sources.py`: `SegmentSource` Protocol, `TimedLine`, `TimedLineSegmentSource` (token-F1
  matcher over time-aligned lines, handling exact / sub-line / multi-line references),
  `find_segment(...)`, `load_timing(...)`, `cut_quote(...)`. **"Resolve a *reference* to a
  cuttable `[start, end]` window"** — precisely "the aide-mémoire says 'the arm-wave bit';
  where is that in the video?"
- `script.py`: `Script` = ordered beats (`Narration | Dialogue | SegmentBeat`).
  `formats.py`: named format presets (`DEEP_DIVE`, `panel`, `debate`, `documentary_vo`, …)
  as "a high-quality bundle of defaults you can render in one call" — the Template pattern.
- `transforms/`: an nw-Transform layer imported only when `nw` is available; `import braidio`
  never requires it. **The optional-substrate-layer pattern to copy.**

### 5.3 `muvid` — `$PP/t/muvid/muvid/`
- `align.py`: `align_lyrics(...)`, `align_scribe_greedy(...)`, `align_user_provided(...)`,
  `align_whisperx_lite(...)`, `align_stars(...)`, `write_alignment_store(...)`;
  `register_aligner(spec)` / `list_aligners()` / `aligner_info(name)`;
  `WordAlignment / LineAlignment / SectionAlignment / AlignmentResult`.
  **The worked example of "authored text + machine transcript → a 3-tier lacing store"** —
  exactly "hand-written aide-mémoire + Scribe transcript → step boundaries". Pluggable
  aligners behind a registry.
- `footage/edl.py`: `EdlEntry(song_start, song_end, clip_id)` (null `clip_id` = an explicit
  gap), `Transition`, `AssemblyCut`, `FootageAlignment`, `fill_gaps(entries, duration)`,
  `validate_edl(...)` ("the ONE gate every path passes before any cutting"),
  `derive_cuts(...)` (centralizes the sign convention so no third-party strategy desyncs).
  **The fleet's ledger/EDL data structure.**
- `footage/lacing_bridge.py`: `editor_document(proj, *, attributed_to) -> {tiers, annotations}`
  — a project as a lacing document "in SONG TIME on one shared axis… so any lacing-native
  surface (lacing-ui's multitrack Timeline first) renders it without knowing muvid exists" —
  and `edl_from_annotations(...)` back. **The contract to imitate if you want lacing-ui to
  edit your step index.** Record kinds: `clip-alignment/v1`, `clip-score-track/v1`,
  `music-video-edl/v1`.
- `contracts.py`: "all cross-package type translation lives in exactly one module". Adopt it.
- `ui/app.py`: `create_app(root)` / `serve(root=…, host="127.0.0.1", port=7800)` — localhost
  FastAPI + one static HTML page polling `/api/status`. Explicitly "not a multi-tenant SaaS".
- `visualize/`: deterministic ffmpeg-only visualizers (`still, ken_burns, cqt, spectrum,
  waves, bars, scope`) — free, key-free, `verify_video` + `report` included.

### 5.4 `falaw` — `$PP/t/falaw/falaw/`
- `generate_image(prompt, *, quality, image_size, model_id, extra)`, `text_to_speech(...)`,
  `operations/video.py: text_to_video(...)` / `image_to_video(...)`,
  `call_fal(application, arguments, on_event=…)`, `cached_call_fal(...)`.
- `Plan` / `execute_plan(plan, *, concurrency)` / `execute_plan_isolated(...) -> ExecutionReport`
  / `plan_dependencies(plan)` — the object `nw.Transform.plan()` returns.
- `estimate_scene_cost(scene) -> CostRollup`; `ModelRecord.cost_estimate: CostEstimate|None`
  with kinds `per_call|per_image|per_second|per_token|per_megapixel`; priceless models land
  in the rollup's `skipped` list "so audits surface drift".
- `ProgressEvent` bus: `subscribe(cb)` global, `on_event=` per-call; kinds
  `queued, progress, log, done, error, cache_hit`.
- `operations/llm.py`: `llm_complete(...)` (via `fal-ai/any-llm`), `parse_screenplay(...)`,
  `apply_note_to_beat/scene(...)`. **Text-only — the substrate has no vision endpoint.**
- `bridges/{mcp,service,skill}.py` — MCP / HTTP / Claude-skill bridges from one tool registry.
- `journal.note/issue/improvement(...)` — cross-session notes.

### 5.5 `dol` / `xdol` / `i2` / `qh`
- **`dol`** (v0.3.65, pure python, zero deps): the `Mapping`/`MutableMapping` store
  discipline. `dol.filesys`, `dol.caching`, `dol.kv_codecs`, `dol.trans`, `dol.paths`,
  `dol.appendable`, `dol.content`. Per the user's global `app-data-lifecycle` rule, **every
  asset store in `stepped` should be a `dol` store** so local files can grow into S3.
- **`xdol.Registry`** (`xdol/registry.py`): "the dict-pattern that recurs across packages
  (`falaw.registry`, `lacing.processors`, `lookbook.registry`, …)" — `register(k, v)`,
  `register_decorator(k)`, `alias(a, k)`, lazy loading, `on_conflict` policies,
  `Subscription`. `MutableMapping`-compatible, builtin-only. Use it for step-type /
  renderer / segmenter registries.
- **`i2`**: `i2.signatures` + `i2.wrapper` (surface adapters), `i2.castgraph` (cost-aware
  multi-hop type conversion — "a file path instead of a loaded object"), `i2.multi_object`
  (`Pipe`, `FuncFanout`). Ships 5 Claude skills.
- **`qh`**: `mk_app([f1, f2, …]) -> FastAPI`, `qh.testing.test_app`, `qh.stores_qh`,
  `qh.jsclient`, `qh.au_integration`. One route per function, OpenAPI free. Used by
  `reelee.server` and `lookbook.http`.

### 5.6 Frontend trio (only when you get there)
- **`zodal`** (`@zodal/core|store|ui`): `defineCollection(zodSchema)`, `DataProvider`,
  `toFormConfig`/`toColumnDefs`, `explain(field)`, `createBifurcatedProvider()` for the
  metadata-vs-content split. **Last commit 2026-07-14 — the oldest tip in the fleet**, and
  it is a mandatory convention. Expect to fix things.
- **`acture`**: the *mandatory* frontend command-dispatch convention per `reelee-web`'s
  README ("*This is the federation's mandatory convention*"). One
  `defineCommand({id, label, schema, execute})` becomes palette entry + hotkey + AI tool +
  MCP tool + e2e action + undo entry + telemetry event. `wrapex` is its **deprecated**
  predecessor; `lacing-ui` still uses `command-wrapex` and its own README says "no new
  wrapex surface should be added".
- **`lacing-ui`**: Vite + React 19 + Biome + shadcn (vendored) + wavesurfer.js v7 +
  dnd-timeline + `@tanstack/react-virtual` + react-hook-form. `npm run codegen` regenerates
  Zod from lacing's committed JSON Schema; `npm run dev` uses MSW mocks; `npm run dev:real`
  needs `uvicorn lacing.server:app` on :8000.

---

## 6. The two packages outside the workspace

### 6.1 `kodokan` — `$PP/t/kodokan` — the closest existing analogue to `stepped`

v0.0.18, 15 modules, 12 test files, **last commit 2026-07-16** (dormant ~6 weeks, complete
and importable). Its README states the pipeline:

```
acquire (yb) ─► pose (rtmlib / YOLO, tracked tori/uke) ─► segment (motion-energy)
       └─► dol stores (Parquet pose + JSON segments) ─► visualize (overlay / blank / Rerun)
       └─► compare two demos (joint-angle DTW) ─► score + eval harness
```

| Module | Names | Why you care |
|---|---|---|
| `acquire.py` | `download_techniques(...)`, `download_source(...)`, `list_techniques(...)`, `local_clips(dir)`, `canonical_technique_key(title)` | Thin wrapper over `yb.download`, keeping the source URL with every clip. |
| `pose.py` / `track.py` | `PoseSequence`, `estimate_poses(video)`, `estimate_poses_tracked(video, source_url=…)`, `identity_swap_rate(seq)` | Pose extraction with persistent person identity — **the obvious enrichment for a dance-step AST**. |
| `segment.py` | `pose_motion_energy(seq)`, `optical_flow_energy(video, frame_range=…)`, `find_segments(energy, frames, fps, **kw)`, `self_similarity_matrix`, `estimate_period`, `segment_demonstrations(seq, *, min_two_person_frac=0.0, use_optical_flow=False, **kw)`, `Segment` | **Unsupervised segmentation of a continuous take into repeated moves.** Hysteresis thresholding so slow-motion reps are not split; a RepNet-style autocorrelation cross-check on rep count. A *better* fit for "segment a dance run-through" than anything in the `video_gen` fleet. |
| `compare.py` | `joint_angles(kp)`, `angle_features(seq)`, `compare(a, b) -> dict` (DTW distance + warping path), `distance_matrix(seqs)`, `per_angle_deviation(result)`, `time_stretch(...)` | "Am I doing it right?" scoring. Honest caveat in the docstring: 2D joint angles are **not** viewpoint-invariant. |
| `store.py` | `pose_store(dir)`, `segments_store(dir)`, `sequence_to_tidy_df(seq)`, `sequence_to_parquet_bytes`, `load_all_tidy(store)`, `check_tidy_integrity`, `store_integrity_report()` | dol-backed; tidy/long Parquet as the analysis SSOT. |
| `viz.py` | `render_skeleton_video(seq, out_path=…, source_video=…, blank_canvas=…)`, `log_to_rerun(...)` | A skeleton-on-blank-canvas render **is** a face-anonymised, stylized clip — free and deterministic, as an alternative to the AnimeGAN path. |
| `flashcards.py` / `learning.py` | `Problem`, `make_problem`, `confusable_distractors`, `score_response`, `next_target`, `log_response`, `responses_store`, `build_catalog`, `build_confusability`; `Strategy` + `UniformRandom / Leitner / SM2 / ConfusionWeighted / FSRSLite`, `make_strategy(key)`, `list_strategies()` | **A whole spaced-repetition learning layer over a segmented video corpus.** If `stepped` ever renders a *practice* output rather than a *guide* output, it is written, research-cited, and UI-agnostic ("This module is the (UI-agnostic) logic + storage; a web UI plugs into it later"). |
| `examples/generate_stylized_clips.py`, `generate_webapp_clips.py`, `export_webapp_data.py`, `batch_pipeline.py`, `segment_review.py` | see §1.3 | The POC's actual clip pipeline. Scripts, not API. |

Its dependency discipline is the model to copy: "`import kodokan` needs only **numpy**;
everything heavy is an optional extra (imported lazily on first use), so the import never
fails for a missing one" — extras `[pose, viz, analysis, storage, acquire]`.

### 6.2 `yb` — `$PP/t/yb` — v0.1.8

`yb/download/youtube.py`: `download_youtube_video(url, …)`, `download_youtube_audio(...)`,
`download_youtube_playlist(...)`, `youtube_video_info(url)`, `youtube_playlist_info(...)`,
`default_download_dir()`. Destination defaults to `$YB_DOWNLOAD_DIR` or `~/Downloads`, named
`Title (video_id).mp4`, with configurable sidecar metadata and any raw yt-dlp option passed
through. The README states the division of labour: "The media work itself (transcription,
chapter detection, thumbnails, dubbing/translation) lives in the `mixing` package; `yb` is
the publication layer on top." Also: `yb.content.PublicationContent` (platform-neutral
title/description/keywords/chapters/captions/thumbnail) + thin per-destination adapters —
**the same "one representation, many targets" shape you want.** Skills available in-session:
`yb-download`, `yb-publish`, `yb-podcast`.

---

## 7. The POC's capabilities → where each already lives

| POC capability | Existing home | Status |
|---|---|---|
| Pull the source video off YouTube | `yb.download_youtube_video` / `download_youtube_audio` / `download_youtube_playlist` · `braidio.mcp._media.download_audio` (audio only, cookie-hardened) · `kodokan.acquire.download_source` | **exists** |
| Word-level transcript of the spoken breakdown | `mixing.transcript.transcribe(..., timestamps_granularity="word", cache=True)` | **exists** |
| Segment the routine into N named blocks | `mixing.chapters.detect_chapters(transcript, segment_fn=…)` (LLM, from speech) · `nw.script_segmentation.segment_script_into_panels` (LLM, from prose) · `reelee.transforms.beat_to_panel.segment` (LLM, 1→N, provenanced) · `kodokan.segment.segment_demonstrations` (**unsupervised, from motion**) · `mixing.audio.find_segments` (unsupervised, from audio) | **exists in 5 shapes; none is exactly yours** |
| Align a hand-written doc to the video's timeline | `muvid.align.align_lyrics` + `register_aligner` · `braidio.sources.TimedLineSegmentSource` (quote → `[start,end]`) | **exists** |
| Store blocks as a queryable, provenanced time index | `lacing` (`Annotation` + `TimeInterval` + `SqliteStore` + `Tier`) | **exists** |
| Measured tempo / 8-count metronome | `mixing.audio.beats.beat_grid` → `.tempo_bpm`, `.beat_times` | **exists**; downbeats do **not** (always empty on the shipped backend) |
| Per-block looping video extract | `mixing.video.crop_video` + `loop_video` · `kodokan/examples/generate_webapp_clips.py::_make_clip` | **exists** |
| Auto-crop the extract | `burns.content.salient_box` gives the rect; **nothing in the fleet applies a spatial crop to video** | **partial — see §8** |
| Cartoon-stylize + face-anonymise | `kodokan/examples/generate_stylized_clips.py::process_clip` (cv2 stylization → YOLO11-seg flat background → RetinaFace + AnimeGANv2 face paint) — **the pipeline that made the POC** · alternative: `kodokan.viz.render_skeleton_video(blank_canvas=True)` | **exists as a script, not as API** |
| Deep links back into the source at each timestamp | derived from `MediaRef.interval`; see the `&t=<s>` URLs in kodokan's `catalog.json` | **exists** |
| Generated wordmark / og image | `falaw.generate_image` (paid) · `mixing.video.thumbnail.make_thumbnail` (frame + text overlay, free) | **exists** |
| Render the index to an interactive HTML page | `lacing.exhibit.render_artifact_exhibit` · `reelee.storyboard_export.render_storyboard_html` + Jinja2 (**the pattern to copy**) · `braidio.timeline.TimelineBreakdown.to_html` · `artful.exports.to_html` | **three static generators exist; none is interactive** |
| Also render to PDF / WebVTT / SRT / OTIO | `lacing.adapters.dump(store, dest, format=…)` · `walkthru.adapters.export.{webvtt,srt}` · `reelee.print_pdf.render_manual_pdf` / `render_pdf` · `lacing.exhibit` (pdf, md) | **exists** |
| Incremental re-render after an edit | `nw.freshness.stale_after` | **exists** |
| Long parse with progress, ETA, cancel | `nw.jobs.enqueue / get_job / cancel_job` | **exists** |
| A "practice / quiz" output instead of a guide | `kodokan.flashcards` + `kodokan.learning` (5 spaced-repetition strategies) | **exists** |
| HTTP surface | `qh.mk_app` (see `reelee.server`) | **exists** |
| MCP surface | `fastmcp` (see `reelee.mcp.server`, `braidio.mcp`) or `py2mcp.mk_mcp_from_refs` (see `$PP/tt/tw_platform/apps/*_mcp/server.py`) | **exists** |
| Deploy the page | `tw_platform` enlace app: an `app.toml` + a `frontend/` dir, auto-discovered via `platform.toml apps_dirs`. Skills: `twp-deploy`, `tw-deploy` | **exists** |

---

## 8. What is thin, stale, missing, or a trap

**Stale / dormant (still importable, just unattended):**
- `zodal` — last commit **2026-07-14**, 22 commits. Oldest tip in the fleet, and a
  *mandatory* frontend convention. Expect to fix things.
- `kodokan` — last commit 2026-07-16. Complete, dormant, and the most on-point package.
- `lacing-ui` — 11 commits, last 2026-08-15. MSW-mocked by default.
- `wrapex` — explicitly legacy, superseded by `acture`. Do not add surface to it.

**Thin but honest (small on purpose, not stubs):** `artful` (5 modules / 3 test files),
`burns` (9 modules / 4 test files), `xdol` (7 modules / 4 test files). All finished for
their declared scope.

**Genuinely missing:**
- **No spatial video crop.** `mixing.video.crop_video` is *temporal* despite the name (as
  is `crop_audio`). `video_util.py` has `get_video_dimensions` / `resize_to_dimensions` /
  `normalize_video_dimensions` — resize, not crop-to-rect. `burns` crops stills only. You
  will write `crop_video_to_rect` (an ffmpeg `crop=` filter, or moviepy via `Video.to_clip()`).
- **No vision LLM in the substrate.** `reelee/transforms/continuity/_vision.py` says it
  plainly: "The substrate has no vision endpoint yet — `falaw.llm_complete` is text-only."
  Its `vision_llm` strategies run against a mock that "never calls a model, never bills,
  and always reports 'no conflict'". Wire-in point: `set_vision_backend(backend)` with
  `(image_a, image_b, question) -> VisionVerdict`. If `stepped` wants "watch the video and
  name the move", **you are building that seam, not reusing it.**
- **No downbeat detection.** `BeatGrid.downbeat_times` is always empty (librosa has none;
  madmom deliberately excluded for licensing). Your 8-count's "1" must come from elsewhere.
- **No metronome / click-track generator.** `rg -i metronome` over `$PP/t` and `$PP/tt` hits
  only `sonification` and `sung`, neither in the fleet. The POC's metronome is
  hand-written JS in `index.html`.
- **No face *blur*.** Detection exists (`reelee…_cv.face_appearance_distance` via a Haar
  cascade; `lookbook.embedders.arcface` via InsightFace; RetinaFace inside kodokan's
  example). The *replacement* (AnimeGAN face paint) exists only in that example script.
- **`acture-walkthru`** — referenced by walkthru's README, not on disk. `acture-capture` is
  the real thing.

**Traps:**
- `nw/workflow.py` + `nw/renderers/` — zero external call sites; use the Transform registry.
  Do not "clean them up" either.
- `qh`'s `pyproject.toml` says `version = "0.0.17"` but the imported module reports
  `__version__ == "0.5.0"`. Trust neither.
- `muvid` looks like 2934 files / 1.1 M LOC to a naive `find`; the real package is ~60
  modules. The bulk is `tests/` fixtures and `misc/`.
- **`$PP/my_packages.pth` is GENERATED and read-only** (user's global CLAUDE.md, "broken 4
  times"). If `stepped` joins the ecosystem, run `priv pkg add-package <path>` — never
  hand-edit, never edit `packages.pth.in` directly.
- A PyPI wheel can silently shadow a local source tree. If an import behaves as though your
  edits do not exist, run `priv align` before debugging anything else.

**Shipped Claude skills — load these instead of reading source** (all under
`<repo>/.claude/skills/`): `mixing`, `mixing-audio`, `mixing-video`, `mixing-transcript`,
`mixing-dubbing`; `lacing-architecture`, `lacing-time-and-intervals`,
`lacing-schema-codegen`, `lacing-adapter-authoring`; `artful`, `artful-markdown`,
`artful-shot-schedule`; `burns`; `using-walkthru`, `walkthru-schema`, `walkthru-adapter`,
`walkthru-dev`; `falaw`; `braidio`; `illustration`; `muvid` +3; `lookbook` ×9; `an` ×13;
`reelee-add-body-schema`, `reelee-add-transform`, `reelee-where-does-this-go`,
`reelee-substrate-gotchas` (+9 more). **`nw` and `kodokan` ship none** — for those, read the
module docstrings, which are unusually good.

---

## 9. Open questions for the next agent

1. **Should `stepped` be an `nw` genre, or a peer of `nw`?** Registering `stepped_routine`
   as an `nw.Genre` buys the project facade, freshness, jobs, the cost gate and the
   Transform registry for one file — but `Transform.plan()` returns a `falaw.Plan`, and the
   model assumes a project-is-a-folder. A guide generated from a YouTube URL may want
   neither. `reelee.transforms.clips_to_animatic` proves a *Transform* can return a
   zero-call Plan; **I did not verify that a whole genre can be zero-cost and fal-free.**
2. **Is `lacing`'s flat, standoff model rich enough to be the AST?** Hierarchy is expressed
   by tier parent/child stereotypes and by `provenance.was_derived_from`, not by nesting.
   "9 blocks × 4 moves × 8 counts" is naturally a tree. Whether ELAN tier stereotypes carry
   that, or whether `NodeRef.scene_path` (a slash-separated path — possibly the intended
   answer) is the hook, is unsettled.
3. **Where does the interactive-page renderer live?** All four existing HTML generators emit
   *static* documents. The POC page has a running transport, a BPM control and looping
   video — real client-side state, 55 KB of hand-authored HTML+JS. Does Phase 2 become a
   fifth Jinja template with inline JS (cheap, matches `reelee.storyboard_export`), a
   Vite/React app in the `zodal`+`acture` convention (expensive, matches `reelee-web`), or
   an emitted JSON index + a fixed player app (matches the kodokan app)? **I found no
   precedent in the fleet for a *generated* interactive page.** My read: the kodokan model
   (generated `catalog.json` + a hand-written player) is the cheapest honest split and
   already has a working instance.
4. **What is the actual `stepped` repo?** `$PP/pocs/stepped/` contained only an empty
   `docs/` — no git repo, no `pyproject.toml`, no package dir. Whether it becomes a `$PP/t/`
   fleet member (and joins the manifest via `priv pkg add-package`) or stays under `pocs/`
   is undecided.
5. **Does the Que Calor block index exist anywhere as data?** The nine blocks, their
   timestamps, names and 8-count structure live only as markup inside
   `apps/que_calor_dance/frontend/index.html`. Extracting them into a JSON/annotation
   fixture is probably your first concrete task — it gives you a ground-truth target for
   Phase 1 and an input fixture for Phase 2. I did not do it.
6. **Should `kodokan`'s example scripts be promoted into a package?** `process_clip` (the
   stylize/anonymise pipeline) and `_make_clip` (the cutter) are the two most valuable
   pieces of code found, and both live in `examples/` with hardcoded absolute paths,
   `/opt/homebrew/bin/ffmpeg` and `mps`. Promoting them — into `kodokan`, into `mixing`, or
   into `stepped` — is a placement decision I could not make for you. `mixing` is the
   natural home for a `stylize_clip(...)` verb, but it would pull in torch/onnx/YOLO.
7. **Keys and cost.** `mixing.transcript.transcribe` needs `$ELEVENLABS_API_KEY`; `falaw`
   needs `$FAL_KEY`; `braidio`'s YouTube ingest may need a provisioned cookie jar; the
   AnimeGAN weights must be at `~/kodokan_data/style_models/face_paint_512_v2_0.onnx`.
   **I checked none of these are present.**
8. **Is `reelee` the parent, not the sibling?** Given `bodies/storybook.py` +
   `storybook.py` + `print_pdf.render_manual_pdf` (a narrated-steps AST, two input
   adapters, one render core, an illustrated-manual renderer), a real option is that
   `stepped` is an *ingest + renderer pair on top of reelee* rather than a new substrate.
   The blocker is that reelee's step schema is UI-tour-shaped (`command_id`, before/after
   screenshots) — but "generalize `storybook-step/v1` to any narrated step with a media
   interval instead of a command id" is a smaller change than a new library. Worth costing
   before you commit.
