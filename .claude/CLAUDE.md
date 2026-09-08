# paces — agent notes

## Seams & surfaces (architecture-first, v1 2026-08-29)

| # | Seam | v1 default | Replacement you can point at |
|---|---|---|---|
| 1 | `segmenter=` on `segment()` | auto-select from present facts (`grid-placed` / `explicit`) | the strategies catalogued in `docs/alignment/07` (novelty-k, align-to-steps); `kodokan.segment`; `mixing.audio.find_segments` |
| 2 | `renderer=` on `tools.render()` | `"html"` practice page (stdlib) | the POC page (metronome+clips) at `docs/poc-reference/render/`; PDF/deck per `docs/03 §2.3` |
| 3 | `grid=` values on `segment()` | caller-supplied tempo/origin; measured from local media when absent (`grid-measured`: mixing speech/music split + beat_grid, origin estimated + flagged) | better origin fitting (issue #2 follow-ons; `kodokan.estimate_period`) |
| 4 | `store=` on `evidence.to_store()` / `from_store()` | none — injected, always: `lacing.MemoryStore` in tests, `SqliteStore` for a project sidecar | any `dol` MutableMapping conforming to `lacing.IntervalAnnotationStore` |

Surface for v1: **CLI** (`argh` over `tools._dispatch_funcs`). MCP (`py2mcp`
string refs), HTTP (`qh`), shipped skills, frontend: questions answered — none
needs a core change — not built.

NOT seams: JSON serialisation rules (docs/07 §6.5, deliberate), the HTML
template internals, CLI parsing, storage (v1 reads/writes explicit paths).

## Ground rules

- `docs/` is the design record: ADRs 0001–0004 are settled; argue before
  overturning. `docs/07-annotation-model.md` owns the schema rationale.
- The round-trip test (`tests/test_roundtrip_poc.py`) is the schema's
  acceptance test — a schema change that breaks it is wrong until the POC
  maps in again.
- No floats on the wire; domain units in `Measure`; absolute times computed
  by `resolve()`, never stored.
- A segmenter may never return a step count it has no evidence for
  (honesty states in `paces/segment.py` docstring).
- The evidence layer (`paces/evidence.py` + `paces/bodies/`, issue #4) owns
  the lacing boundary. Its rules, in one line each: intervals live on
  `Annotation.reference`, never in a body; annotation ids are `uuid5` over a
  stable evidence key, so a re-derivation *is* the same row; an unchanged
  value digest leaves the row completely alone; `locks`, `questions`,
  `artifacts` and span `excerpt` windows are document-layer and never flow
  into the store.
- **Body schema URIs are a flat, fleet-wide namespace and
  `register_body_schema` overwrites silently.** Every URI paces owns is
  prefixed `guide-`; `word/v1` is lacing's and reused. Before adding one,
  check the fleet (`rg 'annot://schema/'` across `$PP`) and pin it in
  `tests/test_evidence_schemas.py`.
- Named next steps: `paces/genre.py` registering `step_by_step` into `nw`
  (ADR-0004); intrinsic segmenter combinators when a third intrinsic
  segmenter needs them (ADR-0003); a CLI/MCP surface over `to_store`
  (needs no core change — the store's on-disk shape is the open question).
