# paces

Turn instructional media into structured, interactive learning material.
*Put it through its paces.*

Take a video of someone teaching something — a dance routine, a kata, a
recipe — plus, optionally, notes and a steering prompt. `paces` segments it
into named steps, builds a structured **step document** (an AST for
step-by-step instruction), and renders that into learning material: a
practice page with counts and deep links today, other guides later.

```bash
pip install paces
```

## Quick example

```python
from paces import segment, to_document, render_html

seg = segment(
    "https://youtu.be/q_TUyxUhoEw",
    steps=[
        ("Mise en place", 2),
        ("Pas pieds pointe et ronde", 6),
        ("Soleil avec les bras", 4),
        ("Déhanchés", 8),
    ],
    grid={"unit": "eight", "subdivisions": 8, "tempoBpm": "129.2", "origin": "51.2"},
)
doc = to_document(
    seg,
    doc_id="que-calor",
    title="Chorégraphie Que Calor",
    source="https://youtu.be/q_TUyxUhoEw",
)
open("page.html", "w").write(render_html(doc))
```

The page lists every step with its counts, links each one back into the video
(both the at-tempo run-through and the slow breakdown, when both are known),
and — because the document carries a metric grid — includes a count-along
transport that paces you through the routine at the measured tempo.

Same thing from the shell:

```bash
paces segment VIDEO_URL --steps steps.json --grid grid.json --output seg.json
paces to-document seg.json --source VIDEO_URL --title "My routine" --output document.json
paces render document.json --output page.html
```

## How it thinks

**Analysis and rendering are separate phases** with a serialisable document
between them — like a parser emitting an AST and a backend interpreting it.
Renderers depend on the document, never on the analyser.

**Segmentation is a seam, not a stage.** `segment(media, segmenter=...)` —
segmenters are registered capabilities, the default follows from what is
present, and "the user typed the boundaries" is a first-class segmenter, not
a fallback. A segmenter that cannot *name* steps returns honest unnamed
boundaries (`flags: ['naming-abstained']`) rather than inventing names.

**The document keeps what the learner actually counts.** A dance step lasts
"4 eights", not "14.86 seconds" — seconds are derived from the metric grid
(tempo + origin), never stored. A step can have *several* source spans (the
run-through and the breakdown are the same step seen twice). Uncertainty is
content (`OpenQuestion`), and human edits are protected from regeneration
(`Lock`).

## The pieces

| you want | reach for |
|---|---|
| cut media into steps | `segment(media, steps=..., grid=...)` → `Segmentation` |
| explicit/human boundaries | `segment(media, boundaries=[...], steps=[names])` |
| the committed artifact | `to_document(seg, ...)` → `StepDocument` |
| a practice page | `render_html(doc)` |
| wall-clock times from counts | `resolve(doc)` |
| sanity checks | `validate_document(doc)` |
| what segmenters exist | `capabilities()` / `paces list-segmenters` |
| add a segmenter | `register(Capability(name=..., gives="segmentation", target="mymod:fn", needs={...}))` — a new file, nothing edited |

## Status

Young and moving. The document schema is validated by round-tripping a real
proof of concept ([an interactive dance-practice
page](https://thorwhalen.com/que_calor_dance/)) through it — see
`tests/test_roundtrip_poc.py`. Media derivation (auto-cropped looping clips),
intrinsic segmenters (scene/beat/speech detection), and the evidence layer
are designed (see `docs/`) and arrive next.
