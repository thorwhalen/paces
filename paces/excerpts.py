"""Excerpt suggestion: mark the loopable sub-window each step's clip is cut
from.

A :class:`~paces.model.SourceSpan` with an ``excerpt`` is what media
derivation (ADR-0005) cuts; nothing upstream sets one. This module holds the
v1 heuristic (issue #3's cost note): **a step's excerpt is its own grid
window** — the span itself — or, with ``units=``, its first N metric units.
Editorial window-picking (the POC spent ~11 min of LLM agents over contact
sheets choosing windows by eye) is a later capability that replaces this
default behind the same seam; corrections meanwhile are ordinary document
edits, which a suggestion must never eat:

- an existing excerpt is only replaced under ``overwrite=True``, and even
  then only by a real new suggestion — **never by nothing** (a heuristic
  that cannot compute a window keeps what the human picked, with a flag);
- a step carrying any span-level lock that could denote an excerpt gets
  **no suggestions at all**: lock paths are recorded in index form and a
  regeneration merge reorders spans (``edits.py``'s own premise), so "which
  span does ``/spans/0/excerpt`` mean now?" cannot be answered here —
  abstaining loses a default; guessing can silently undo a locked edit.

Honesty flags over silence: every span this module skips or cannot fill is
flagged by name.
"""

from __future__ import annotations

import math
import re
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

#: A lock path that could denote a span's excerpt: the whole spans list, a
#: whole span, or anything mentioning an excerpt. A narrower span field
#: (caption, label) denotes that field under any reordering and never blocks.
_SPAN_LOCK = re.compile(r"^/spans(/\d+)?$|^/spans/.*excerpt")


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


def _excerpts_locked(step: Step) -> bool:
    return any(_SPAN_LOCK.search(lock.path) for lock in step.locks)


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
            run-through). A step whose spans lack the role is flagged; a
            step with SEVERAL role spans gets a suggestion on the first and
            a ``multiple-<role>-spans:`` flag for the rest (the POC's b8
            shape — the other moments still derive once excerpts are set by
            hand or a future picker).
        overwrite: replace existing excerpts with new suggestions. Off by
            default; replacement never degrades to deletion, and a span-
            locked step abstains entirely (see the module docstring).
    """
    if units is not None:
        if not math.isfinite(units) or units <= 0:
            raise ValueError(f"units must be a positive number, got {units}")
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

    for step in _walk_steps(doc.steps):
        if not step.spans:
            continue
        role_spans = [span for span in step.spans if span.role == role]
        if not role_spans:
            flags.append(f"no-{role}-span:{step.id}")
            continue
        if len(role_spans) > 1:
            flags.append(f"multiple-{role}-spans:{step.id}")
        if _excerpts_locked(step):
            flags.append(f"locked-excerpt-kept:{step.id}")
            continue
        span = role_spans[0]
        if span.excerpt is not None and not overwrite:
            continue
        suggestion = _suggest_for_span(span, units=units, spu=spu)
        if suggestion is None:
            # nothing computable: keep whatever is there — replacement must
            # never degrade to deletion — and say so
            flags.append(f"no-extent:{step.id}")
            continue
        span.excerpt = suggestion
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
