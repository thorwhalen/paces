# paces — agent notes

## Seams & surfaces (architecture-first, v1 2026-08-29)

| # | Seam | v1 default | Replacement you can point at |
|---|---|---|---|
| 1 | `segmenter=` on `segment()` | auto-select from present facts (`grid-placed` / `explicit`) | the strategies catalogued in `docs/alignment/07` (novelty-k, align-to-steps); `kodokan.segment`; `mixing.audio.find_segments` |
| 2 | `renderer=` on `tools.render()` | `"html"` practice page (stdlib) | the POC page (metronome+clips) at `docs/poc-reference/render/`; PDF/deck per `docs/03 §2.3` |
| 3 | `grid=` values on `segment()` | caller-supplied tempo/origin | `mixing.audio.beat_grid` → measure it from media |

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
- Named next steps: evidence layer → lacing (`docs/07 §6.3`); `paces/genre.py`
  registering `step_by_step` into `nw` (ADR-0004); intrinsic segmenter
  combinators when a third intrinsic segmenter needs them (ADR-0003).
