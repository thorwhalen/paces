"""Turn instructional media into structured, interactive learning material.

Take a video of someone teaching something — plus, optionally, notes and a
steering prompt — segment it into named steps, build a structured step
document (the AST), and render that into learning material: a practice page
today, other guides later. *Put it through its paces.*

Two phases, one contract between them:

- **Analyse** — :func:`segment` cuts media into steps. Segmentation is a seam,
  not a stage: segmenters are registered capabilities and the default follows
  from what is present (ADR-0003).
- **Render** — renderers consume the :class:`StepDocument` and never the
  analyser.

Quickstart::

    from paces import segment, to_document, render_html

    seg = segment(
        "https://youtu.be/...",
        steps=[("Warm-up", 2), ("The turn", 4), ("Finale", 2)],
        grid={"unit": "eight", "subdivisions": 8,
              "tempoBpm": "129.2", "origin": "51.2"},
    )
    doc = to_document(seg, doc_id="my-routine", title="My routine",
                      source="https://youtu.be/...")
    html = render_html(doc)
"""

from paces.model import (
    SCHEMA_VERSION,
    Anchor,
    ArtifactRef,
    Cue,
    Lock,
    Measure,
    MetricGrid,
    OpenQuestion,
    Origin,
    Source,
    SourceSpan,
    Step,
    StepDocument,
    dumps_document,
    loads_document,
    resolve,
    seconds_per_unit,
    validate_document,
)
from paces.projection import to_document
from paces.render import render_html
from paces.segmenters import (
    Capability,
    SegStep,
    Segmentation,
    capabilities,
    register,
    segment,
)

__all__ = [
    # the document (the contract)
    "StepDocument",
    "Step",
    "Measure",
    "MetricGrid",
    "Source",
    "SourceSpan",
    "ArtifactRef",
    "Cue",
    "Anchor",
    "OpenQuestion",
    "Lock",
    "Origin",
    "SCHEMA_VERSION",
    "dumps_document",
    "loads_document",
    "resolve",
    "seconds_per_unit",
    "validate_document",
    # analysis
    "segment",
    "Segmentation",
    "SegStep",
    "Capability",
    "register",
    "capabilities",
    "to_document",
    # rendering
    "render_html",
]
