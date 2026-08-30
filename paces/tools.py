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
    edits as edits_module,
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
    metadata=None,
    segmenter: str | None = None,
    k: int | None = None,
    output: str | None = None,
) -> dict:
    """Cut media into steps using whatever else is present (ADR-0003).

    ``steps``, ``boundaries``, ``grid`` and ``metadata`` accept JSON values,
    JSON strings, or paths to JSON files — ``metadata`` notably takes a
    yt-dlp ``.info.json`` (its ``chapters`` become a named segmentation).
    Returns the segmentation as a JSON-ready dict (also written to
    ``output=`` when given) — honest about naming
    (``flags: ['naming-abstained']``) and about refusal
    (``flags: ['no-signal', 'try: ...']``); never a fabricated step list.
    """
    result = segment_module.segment(
        media,
        segmenter=segmenter,
        steps=_structured(steps, what="steps"),
        boundaries=_structured(boundaries, what="boundaries"),
        grid=_structured(grid, what="grid"),
        metadata=_structured(metadata, what="metadata"),
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
    doc = _as_document(document)
    text = renderers[renderer](doc)
    if output:
        _warn_if_page_leaves_media_behind(doc, document, output)
        Path(output).write_text(text, encoding="utf-8")
        return output
    return text


def _warn_if_page_leaves_media_behind(doc, document, output) -> None:
    """A page rendered away from the document's directory shows dead clips:
    ``ArtifactRef.uri`` is document-relative (ADR-0005 §1). Warn, loudly."""
    import warnings

    def _steps(steps):
        for step in steps:
            yield step
            yield from _steps(step.steps)

    has_relative_media = any(
        not artifact.uri.startswith(("http://", "https://", "/"))
        for step in _steps(doc.steps)
        for artifact in step.artifacts
    )
    if not has_relative_media:
        return
    if not (isinstance(document, str) and Path(document).is_file()):
        return
    doc_dir = Path(document).resolve().parent
    out_dir = Path(output).resolve().parent
    if doc_dir != out_dir:
        warnings.warn(
            f"rendering to {out_dir} but the document (and its media/) live "
            f"in {doc_dir} — the page's relative media uris will not "
            "resolve there",
            stacklevel=3,
        )


def resolve(document) -> dict:
    """Compute absolute offsets and wall-clock times for a document's steps."""
    return model.resolve(_as_document(document))


def validate(document) -> dict:
    """Schema + semantic check of a step document; returns ``{"issues": [...]}``."""
    return {"issues": model.validate_document(_as_document(document))}


def edit(
    document,
    edits,
    *,
    by: str,
    reason: str | None = None,
    output: str | None = None,
) -> dict:
    """Apply typed patches to a document; every edit writes a Lock.

    ``edits`` is a list of ``{"op": "set", "path": "/steps/b4/name",
    "value": ...}`` (JSON value, string, or file path). ``by`` identifies the
    editor ("user:thor", "agent:<model>"). Locked paths survive
    regeneration (see ``merge``).
    """
    doc = edits_module.apply_edits(
        _as_document(document),
        _structured(edits, what="edits"),
        by=by,
        reason=reason,
    )
    text = model.dumps_document(doc)
    if output:
        Path(output).write_text(text, encoding="utf-8")
    return json.loads(text)


def merge(committed, fresh, *, output: str | None = None) -> dict:
    """Merge a fresh analysis projection against the committed document.

    Locked paths keep the committed value; everything else takes the fresh
    value; protected committed-only steps survive. This is how re-running
    analysis never eats a hand edit.
    """
    doc = edits_module.merge_regenerated(_as_document(committed), _as_document(fresh))
    text = model.dumps_document(doc)
    if output:
        Path(output).write_text(text, encoding="utf-8")
    return json.loads(text)


def measure_grid(
    media: str,
    *,
    unit: str = "eight",
    subdivisions: int = 8,
    total_units: float | None = None,
    output: str | None = None,
) -> dict:
    """Measure a metric grid (tempo, macro-structure, estimated origin) from
    a local media file. Needs the [audio] extra.

    Returns ``{"grid", "confidence", "flags", "evidence"}`` — origin is an
    estimate (first beat of the music region) and the flags say so; override
    with an explicit ``grid=`` on ``segment`` when it is wrong.
    """
    from paces.measure import measure_grid as _measure_grid

    measurement = _measure_grid(
        media, unit=unit, subdivisions=subdivisions, total_units=total_units
    )
    payload = {
        "grid": measurement.grid.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "confidence": measurement.confidence,
        "flags": list(measurement.flags),
        "evidence": dict(measurement.evidence),
    }
    if output:
        Path(output).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return payload


def derive(
    document,
    *,
    media,
    output: str | None = None,
    subject_locator: str | None = None,
    roles: str = "clip,gif,poster",
    aspect: float | None = None,
    pad: float | None = None,
) -> dict:
    """Derive real media (clip + gif + poster) for every excerpt-bearing
    span and write the refs into the document. Needs the [media] extra.

    ``document`` must be a *path* here (the anchor for the ``media/`` dir
    and the crop-recipes sidecar — ADR-0005 §1); library callers with an
    in-memory document use :func:`paces.derivation.derive_document` with an
    explicit store. ``media`` is one local file, or ``{"<source-id>":
    "<path>"}`` when several sources carry excerpts. ``subject_locator`` is
    a lazy ``"module:attr"`` ref to an ADR-0005 §3 locator; the default is
    no crop. The updated document is written back to ``output`` (default:
    the document path itself — derive's media side effects and the refs
    pointing at them must not go out of sync); the returned payload carries
    ``flags`` — read them, they are the honesty report.
    """
    from paces import derivation

    if not isinstance(document, str) or not Path(document).is_file():
        raise ValueError(
            "derive takes the document as a file path — the document's "
            "directory anchors media/ and the recipes sidecar (ADR-0005); "
            "for in-memory documents use paces.derivation.derive_document "
            "with media_store= and recipes_path="
        )
    locator = None
    if subject_locator is not None:
        import importlib

        module_name, _, attr = subject_locator.partition(":")
        if not module_name or not attr:
            raise ValueError(
                f"subject_locator must be a 'module:attr' ref, got {subject_locator!r}"
            )
        locator = getattr(importlib.import_module(module_name), attr)
    # media: a dict passes through; a string is a JSON mapping (inline or
    # .json file) or, most commonly, the media file's own path.
    if isinstance(media, str) and (
        media.lstrip().startswith("{") or media.endswith(".json")
    ):
        media = _structured(media, what="media")
        if not isinstance(media, dict):
            raise ValueError(
                "a JSON media argument must be a mapping "
                '{"<source-id>": "<path>"}; got '
                f"{type(media).__name__}"
            )
    doc_path = Path(document)
    result = derivation.derive_document(
        model.loads_document(doc_path.read_text(encoding="utf-8")),
        media=media,
        doc_path=doc_path,
        subject_locator=locator,
        aspect=derivation.DFLT_ASPECT if aspect is None else aspect,
        pad=derivation.DFLT_PAD if pad is None else pad,
        roles=tuple(role.strip() for role in roles.split(",") if role.strip()),
    )
    text = model.dumps_document(result.document)
    out_path = Path(output or doc_path)
    if out_path.resolve().parent != doc_path.resolve().parent:
        import warnings

        warnings.warn(
            f"writing the derived document to {out_path.parent} while its "
            f"media/ and recipes sidecar stay in {doc_path.parent} — the "
            "written document's relative media uris will not resolve there",
            stacklevel=2,
        )
    out_path.write_text(text, encoding="utf-8")
    return {
        "document": json.loads(text),
        "flags": result.flags,
        "derived": result.derived,
    }


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


_dispatch_funcs = [
    segment,
    to_document,
    render,
    derive,
    edit,
    merge,
    resolve,
    validate,
    measure_grid,
    list_segmenters,
]
