"""Agent-callable tool surface over ``paces`` — plain functions with JSON-able
arguments returning JSON-ready values, deliberately CLI/MCP/HTTP-agnostic.

This module is the SSOT for "what paces can do": every surface (the ``argh``
CLI in ``__main__.py`` today; ``py2mcp``/``qh`` wrappers tomorrow) dispatches
over ``_dispatch_funcs`` and nothing else. Arguments that carry structure
(steps, grids, documents) accept a Python object, a JSON string, or a path to
a JSON file, so the same function serves the library, the shell, and an agent.
"""

from __future__ import annotations

import json
from pathlib import Path

from paces import (
    model,
    projection,
    render as render_module,
    segmenters as segment_module,
)


def _structured(value, *, what: str = "argument"):
    """A mapping/list as-is; a str as a file path (if it exists) or JSON."""
    if value is None or not isinstance(value, str):
        return value
    path = Path(value)
    if path.exists():
        value = path.read_text(encoding="utf-8")
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"{what} must be a JSON value or a path to a JSON file; "
            f"got {value[:80]!r} ({error})"
        ) from None


def _as_document(document) -> model.StepDocument:
    if isinstance(document, model.StepDocument):
        return document
    return model.StepDocument.model_validate(_structured(document, what="document"))


def _segmentation_to_dict(seg: segment_module.Segmentation) -> dict:
    def _step(s: segment_module.SegStep) -> dict:
        return {
            "id": s.id,
            "name": s.name,
            "spans": [list(span) for span in s.spans],
            "confidence": s.confidence,
            "children": [_step(c) for c in s.children],
            "source": s.source,
            "evidence": dict(s.evidence),
        }

    return {
        "steps": [_step(s) for s in seg.steps],
        "boundaries": list(seg.boundaries),
        "unit": seg.unit,
        "grid": (
            seg.grid.model_dump(mode="json", by_alias=True, exclude_none=True)
            if seg.grid is not None
            else None
        ),
        "confidence": seg.confidence,
        "method": seg.method,
        "flags": list(seg.flags),
        "elapsed_s": seg.elapsed_s,
        "spent_usd": seg.spent_usd,
    }


def _segmentation_from_dict(payload) -> segment_module.Segmentation:
    if isinstance(payload, segment_module.Segmentation):
        return payload
    payload = _structured(payload, what="segmentation")

    def _step(row: dict) -> segment_module.SegStep:
        return segment_module.SegStep(
            id=row["id"],
            name=row.get("name", ""),
            spans=tuple(tuple(span) for span in row.get("spans", ())),
            confidence=row.get("confidence", 0.0),
            children=tuple(_step(c) for c in row.get("children", ())),
            source=row.get("source", ""),
            evidence=row.get("evidence", {}),
        )

    grid = payload.get("grid")
    return segment_module.Segmentation(
        steps=tuple(_step(row) for row in payload.get("steps", ())),
        boundaries=tuple(payload.get("boundaries", ())),
        unit=payload.get("unit", "seconds"),
        grid=model.MetricGrid.model_validate(grid) if grid else None,
        confidence=payload.get("confidence", 0.0),
        method=payload.get("method", ""),
        flags=tuple(payload.get("flags", ())),
        elapsed_s=payload.get("elapsed_s", 0.0),
        spent_usd=payload.get("spent_usd", 0.0),
    )


# ── the verbs ───────────────────────────────────────────────────────────────


def segment(
    media: str | None = None,
    *,
    steps=None,
    boundaries=None,
    grid=None,
    segmenter: str | None = None,
    k: int | None = None,
    output: str | None = None,
) -> dict:
    """Cut media into steps using whatever else is present (ADR-0003).

    ``steps``, ``boundaries`` and ``grid`` accept JSON values, JSON strings,
    or paths to JSON files. Returns the segmentation as a JSON-ready dict
    (also written to ``output=`` when given) — honest about naming
    (``flags: ['naming-abstained']``) and about refusal
    (``flags: ['no-signal', 'try: ...']``); never a fabricated step list.
    """
    result = segment_module.segment(
        media,
        segmenter=segmenter,
        steps=_structured(steps, what="steps"),
        boundaries=_structured(boundaries, what="boundaries"),
        grid=_structured(grid, what="grid"),
        k=k,
    )
    payload = _segmentation_to_dict(result)
    if output:
        Path(output).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return payload


def to_document(
    segmentation,
    *,
    doc_id: str = "guide",
    title: str = "",
    source: str | None = None,
    domain: str = "generic",
    lang: str = "en",
    output: str | None = None,
) -> dict:
    """Project a segmentation into a step document (the committed artifact).

    ``source`` is the media URI the spans refer into. With ``output=``, the
    canonical wire form is also written to that path.
    """
    # A source is usually a plain URI; a JSON object (inline or in a file)
    # gives the full Source record (title, attribution, rights, ...).
    if isinstance(source, str) and (
        source.lstrip().startswith("{") or source.endswith(".json")
    ):
        source = _structured(source, what="source")
    doc = projection.to_document(
        _segmentation_from_dict(segmentation),
        doc_id=doc_id,
        title=title,
        source=source,
        domain=domain,
        lang=lang,
    )
    text = model.dumps_document(doc)
    if output:
        Path(output).write_text(text, encoding="utf-8")
    return json.loads(text)


def render(document, *, output: str | None = None, renderer: str = "html") -> str:
    """Render a step document into learning material.

    ``renderer='html'`` (v1's one implementation) produces the self-contained
    practice page. Returns the output path when ``output=`` is given,
    otherwise the rendered text itself.
    """
    renderers = {"html": render_module.render_html}
    if renderer not in renderers:
        raise ValueError(
            f"unknown renderer {renderer!r}; available: {sorted(renderers)}"
        )
    text = renderers[renderer](_as_document(document))
    if output:
        Path(output).write_text(text, encoding="utf-8")
        return output
    return text


def resolve(document) -> dict:
    """Compute absolute offsets and wall-clock times for a document's steps."""
    return model.resolve(_as_document(document))


def validate(document) -> dict:
    """Schema + semantic check of a step document; returns ``{"issues": [...]}``."""
    return {"issues": model.validate_document(_as_document(document))}


def list_segmenters() -> dict:
    """The registered segmentation capabilities: name → what it needs/gives."""
    return {
        name: {
            "summary": cap.summary,
            "gives": cap.gives,
            "needs": sorted(cap.needs),
            "requires": list(cap.requires),
            "licence": cap.licence,
        }
        for name, cap in segment_module.capabilities().items()
    }


_dispatch_funcs = [segment, to_document, render, resolve, validate, list_segmenters]
