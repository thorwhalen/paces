"""Excerpt suggestion: mark the loopable sub-window each step's clip is cut
from.

A :class:`~paces.model.SourceSpan` with an ``excerpt`` is what media
derivation (ADR-0005) cuts; nothing upstream sets one. This module holds the
v1 heuristic (issue #3's cost note): **a step's excerpt is its own grid
window** — the span itself — or, with ``units=``, its first N metric units.
Editorial window-picking (the POC spent ~11 min of LLM agents over contact
sheets choosing windows by eye) is a later capability that replaces this
default behind the same seam; corrections meanwhile are ordinary document
edits, which :func:`suggest_excerpts` never overwrites.

Honesty flags over silence: a step whose excerpt cannot be computed (no span
in the wanted role, no recorded extent, no grid for ``units=``) is flagged by
name, never silently skipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

from paces.model import (
    SourceSpan,
    Step,
    StepDocument,
    decimal_str,
    seconds_per_unit,
)

#: The span role a clip is cut from by default — the at-tempo run-through.
DFLT_EXCERPT_ROLE = "performance"


@dataclass
class ExcerptResult:
    """The updated document plus the honesty flags."""

    document: StepDocument
    flags: list[str] = field(default_factory=list)
    suggested: list[str] = field(default_factory=list)  # step ids touched


def _walk_steps(steps: list[Step]):
    for step in steps:
        yield step
        yield from _walk_steps(step.steps)


def _excerpt_locked(step: Step, span_index: int) -> bool:
    prefix = f"/spans/{span_index}/excerpt"
    return any(lock.path.startswith(prefix) for lock in step.locks)


def suggest_excerpts(
    document: StepDocument,
    *,
    units: float | None = None,
    role: str = DFLT_EXCERPT_ROLE,
    overwrite: bool = False,
) -> ExcerptResult:
    """Fill each step's first *role* span with a suggested ``excerpt``.

    Args:
        document: the committed document (worked on a deep copy).
        units: ``None`` (default) → the excerpt is the span's whole window
            (``start``..``end`` — for grid-placed segmentation that IS the
            block's grid window, which is issue #3's acceptance). A number →
            the first that-many metric units from the span's start, computed
            through the document's grid and clipped to the span's end.
        role: which span carries the clip (default ``"performance"`` — the
            run-through). A step whose spans lack the role is flagged.
        overwrite: replace existing excerpts. Off by default — a suggestion
            must never eat a hand-picked window; a locked excerpt
            (``Lock.path`` under ``/spans/<i>/excerpt``) is kept even with
            ``overwrite=True``, with a flag.
    """
    doc = document.model_copy(deep=True)
    result = ExcerptResult(document=doc)
    flags = result.flags

    spu = None
    if units is not None:
        grid = doc.metric
        spu = seconds_per_unit(grid) if grid is not None else None
        if spu is None:
            flags.append(
                "no-grid: units= needs a metric grid with a tempo; "
                "use units=None (the span's whole window) instead"
            )
            return result
        if units <= 0:
            raise ValueError(f"units must be positive, got {units}")

    for step in _walk_steps(doc.steps):
        if not step.spans:
            continue
        index, span = next(
            ((i, span) for i, span in enumerate(step.spans) if span.role == role),
            (None, None),
        )
        if span is None:
            flags.append(f"no-{role}-span:{step.id}")
            continue
        if span.excerpt is not None and not overwrite:
            continue
        if _excerpt_locked(step, index):
            flags.append(f"locked-excerpt-kept:{step.id}")
            continue
        span.excerpt = _suggest_for_span(span, units=units, spu=spu)
        if span.excerpt is None:
            flags.append(f"no-extent:{step.id}")
        else:
            result.suggested.append(step.id)
    return result


def _suggest_for_span(
    span: SourceSpan, *, units: float | None, spu: float | None
) -> tuple[str, str] | None:
    """One span's suggested window, as exact wire decimals — or ``None``
    when the span records no extent to cut (inventing one would be data)."""
    if units is None:
        if span.end is None:
            return None
        return (span.start, span.end)
    end_s = float(Fraction(span.start)) + units * spu
    if span.end is not None:
        end_s = min(end_s, float(Fraction(span.end)))
    end = decimal_str(end_s)
    if Fraction(end) <= Fraction(span.start):
        return None
    return (span.start, end)
