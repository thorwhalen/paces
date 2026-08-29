"""Segmentation is a seam, not a stage (ADR-0003).

``segment(media, ...)`` takes media plus a ``segmenter=``, and the segmenter
is where the variation lives. Segmenters are *registered* capabilities —
adding one is a new file with one ``register(Capability(...))`` call; nothing
existing is edited. The default is selected from what is present (the facts),
reported in ``Segmentation.method``, and overridable by the one keyword.

A segmenter's information can be intrinsic (features of the media), external
explicit (coordinates handed over), external derived (computed from the
surrounding annotations), or mixed — mixed being the normal case. v1 ships the
two maximally different ones so the seam is shaped by both rather than by one:

- ``grid-placed`` (external, derived — the que-calor shape): an ordered step
  list with domain durations, placed on the timeline by a metric grid.
- ``explicit`` (external, explicit — "ask the user", first-class): boundaries
  or spans supplied directly, named when names were supplied, honestly unnamed
  when not.

Honesty rules (``docs/alignment/07 §9.5``): a segmenter may never return a
step count it has no evidence for. Four legitimate return states — confident /
found-unnamed / proposed-uncertain / refused — all expressed by the type, none
by an exception.
"""

from __future__ import annotations

import importlib
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Callable

from paces.model import MetricGrid, seconds_per_unit

Span = tuple[float, float]  # seconds, half-open

# Confidence constants: placement from user-supplied inputs is arithmetic, so
# what these grade is trust in the inputs, not in any inference.
DFLT_EXPLICIT_CONFIDENCE = 0.95  # a human said so
DFLT_GRID_CONFIDENCE = 0.9  # exact given the grid; the grid itself may drift


@dataclass(frozen=True, slots=True, kw_only=True)
class SegStep:
    """One named piece of the media, as an analysis result.

    ``name=''`` means "found, not named" — a VALID state, not an error.
    ``spans`` is a tuple because a step legitimately appears in several places
    (run-through AND breakdown).
    """

    id: str
    name: str = ""
    spans: tuple[Span, ...] = ()
    confidence: float = 0.0
    children: tuple["SegStep", ...] = ()
    source: str = ""  # which capability produced it
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True, kw_only=True)
class Segmentation:
    """What every segmenter returns. Reviewable, re-runnable, arguable.

    ``boundaries`` is separate from ``steps`` and populated even when naming
    failed: nine excellent unnamed cuts are a useful, honest result. ``steps``
    may be empty while ``boundaries`` is not.
    """

    steps: tuple[SegStep, ...] = ()  # ordered; MAY be empty while boundaries is not
    boundaries: tuple[float, ...] = ()  # the raw cut set, always
    unit: str = "seconds"  # "eight" | "rep" | "seconds"
    grid: MetricGrid | None = None
    confidence: float = 0.0
    method: str = ""  # which capability ran (the ADR's "reported default")
    flags: tuple[str, ...] = ()  # 'naming-abstained', 'no-signal', 'try: ...'
    elapsed_s: float = 0.0
    spent_usd: float = 0.0


@dataclass(frozen=True, slots=True, kw_only=True)
class Capability:
    """What one method needs, gives, and costs. Selection reads ONLY this.

    The record from ``docs/alignment/06 §1.2``, reused unchanged so the
    eventual planner and the segmenter registry share one declaration format.
    ``target`` is a lazy ``"module:func"`` ref — listing a heavy capability
    must not import its dependencies.
    """

    name: str
    gives: str  # 'segmentation' | 'steps' | 'boundary' | 'curve' | ...
    summary: str
    target: str  # "module:func", resolved lazily
    needs: frozenset[str] = frozenset()  # facts; hard filter
    requires: tuple[str, ...] = ()  # importable modules; preflighted
    licence: str = "MIT"
    base: float = 0.0  # prior preference; breaks ties
    s_per_min: float = 0.0
    usd_per_hour: float = 0.0
    device: str = "cpu"
    fixed_s: float = 0.0
    resolution_s: float = 1.0  # finest boundary this method can justify
    calibrated_on: str | None = None  # None = confidence not decision-grade


_CAPABILITIES: dict[str, Capability] = {}


def register(capability: Capability) -> Capability:
    """Register a segmentation capability; returns it for assignment."""
    _CAPABILITIES[capability.name] = capability
    return capability


def capabilities() -> Mapping[str, Capability]:
    """The registered capability catalog (read-only view)."""
    return dict(_CAPABILITIES)


def _resolve_target(capability: Capability) -> Callable:
    module_name, _, func_name = capability.target.partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, func_name)


def _preflight(capability: Capability) -> list[str]:
    """Missing importable requirements, with the install named."""
    missing = []
    for module_name in capability.requires:
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append(module_name)
    return missing


# ── input normalisation & facts ─────────────────────────────────────────────


def _slugify(text: str) -> str:
    """A git-readable slug from free text ('Déhanchés' → 'dehanches')."""
    import re
    import unicodedata

    ascii_text = (
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug or "step"


def _normalize_steps(steps: Sequence | None) -> list[dict]:
    """Accept names, (name, duration) pairs, or mappings; emit uniform dicts.

    Uniform shape: ``{id, name, duration (float units or None), spans, children}``.
    """
    if steps is None:
        return []
    rows: list[dict] = []
    for i, item in enumerate(steps):
        if isinstance(item, str):
            row = {"name": item}
        elif isinstance(item, Mapping):
            row = dict(item)
        elif isinstance(item, Sequence):
            name, duration = item
            row = {"name": name, "duration": duration}
        else:
            raise TypeError(
                f"steps[{i}]: expected a name, a (name, duration) pair, or a "
                f"mapping — got {type(item).__name__}"
            )
        row.setdefault("id", _slugify(row.get("name", "")) or f"step-{i + 1}")
        row["duration"] = (
            None if row.get("duration") is None else float(row["duration"])
        )
        row["spans"] = [tuple(map(float, s)) for s in row.get("spans", ())]
        row["children"] = _normalize_steps(row.get("children") or row.get("steps"))
        rows.append(row)
    return rows


def _normalize_grid(grid: MetricGrid | Mapping | None) -> MetricGrid | None:
    if grid is None or isinstance(grid, MetricGrid):
        return grid
    return MetricGrid.model_validate(dict(grid))


def _facts(
    *,
    media: str | None,
    steps: list[dict],
    boundaries: Sequence[float] | None,
    grid: MetricGrid | None,
    k: int | None,
) -> frozenset[str]:
    """The free half of the fact vocabulary (docs/alignment/07 §9.3): what is
    present among the inputs. Probed (intrinsic) facts arrive with the first
    intrinsic segmenter."""
    facts = set()
    if media:
        facts.add("media")
    if steps:
        facts.add("steps")
        if all(row["duration"] is not None for row in steps):
            facts.add("steps.durations")
        if any(row["spans"] for row in steps):
            facts.add("steps.spans")
    if boundaries:
        facts.add("boundaries")
    if grid is not None and grid.tempo_bpm is not None and grid.origin is not None:
        facts.add("grid")
    if k is not None:
        facts.add("k")
    return frozenset(facts)


# ── the facade ──────────────────────────────────────────────────────────────


def segment(
    media: str | None = None,
    *,
    segmenter: str | Capability | None = None,
    steps: Sequence | None = None,
    boundaries: Sequence[float] | None = None,
    grid: MetricGrid | Mapping | None = None,
    k: int | None = None,
    catalog: Mapping[str, Capability] | None = None,
) -> Segmentation:
    """Cut *media* into named steps, using whatever else is present.

    Returns a :class:`Segmentation` ALWAYS. A segmenter that cannot name the
    steps returns ``boundaries`` and ``steps=()``; when nothing applies the
    result is the refused state (``flags=('no-signal', 'try: ...')``), not an
    exception.

    The seam: ``segmenter=None`` selects from what is present; a name pins it.

    >>> seg = segment(boundaries=[0, 10, 20], steps=['intro', 'verse'])
    >>> [(s.name, s.spans) for s in seg.steps]
    [('intro', ((0.0, 10.0),)), ('verse', ((10.0, 20.0),))]
    """
    started = time.perf_counter()
    catalog = dict(catalog) if catalog is not None else dict(_CAPABILITIES)
    step_rows = _normalize_steps(steps)
    grid = _normalize_grid(grid)
    facts = _facts(media=media, steps=step_rows, boundaries=boundaries, grid=grid, k=k)
    inputs = {
        "media": media,
        "steps": step_rows,
        "boundaries": tuple(float(b) for b in boundaries) if boundaries else (),
        "grid": grid,
        "k": k,
    }

    if segmenter is not None:
        capability = (
            segmenter
            if isinstance(segmenter, Capability)
            else catalog.get(str(segmenter))
        )
        if capability is None:
            known = ", ".join(sorted(catalog)) or "(none registered)"
            raise ValueError(f"unknown segmenter {segmenter!r}; registered: {known}")
        missing_facts = capability.needs - facts
        if missing_facts:
            raise ValueError(
                f"segmenter {capability.name!r} needs inputs you did not "
                f"provide: {sorted(missing_facts)} (facts present: {sorted(facts)})"
            )
    else:
        candidates = [
            cap
            for cap in catalog.values()
            if cap.gives == "segmentation"
            and cap.needs <= facts
            and not _preflight(cap)
        ]
        if not candidates:
            return Segmentation(
                confidence=0.0,
                flags=(
                    "no-signal",
                    "try: steps=[(name, duration), ...] with grid=, "
                    "or boundaries=[t0, t1, ...]",
                ),
                elapsed_s=time.perf_counter() - started,
            )
        capability = max(candidates, key=lambda cap: cap.base)

    missing_modules = _preflight(capability)
    if missing_modules:
        raise ImportError(
            f"segmenter {capability.name!r} requires "
            f"{', '.join(missing_modules)} — pip install them first"
        )
    result: Segmentation = _resolve_target(capability)(inputs)
    return Segmentation(
        steps=result.steps,
        boundaries=result.boundaries,
        unit=result.unit,
        grid=result.grid,
        confidence=result.confidence,
        method=capability.name,
        flags=result.flags,
        elapsed_s=time.perf_counter() - started,
        spent_usd=result.spent_usd,
    )


# ── the two v1 segmenters ───────────────────────────────────────────────────


def _segment_grid_placed(inputs: Mapping[str, Any]) -> Segmentation:
    """Place an ordered step list on the timeline using a metric grid.

    The que-calor shape: cumulative domain durations from the grid's origin,
    ``span = origin + cumulative_units * seconds_per_unit``. Children subdivide
    their parent's span the same way.
    """
    grid: MetricGrid = inputs["grid"]
    spu = seconds_per_unit(grid)
    origin = float(grid.origin)  # guaranteed by the 'grid' fact

    def _place(rows: list[dict], at_units: float) -> tuple[list[SegStep], float]:
        placed = []
        for row in rows:
            duration = row["duration"]
            start = origin + at_units * spu
            end = origin + (at_units + duration) * spu
            children, _ = _place(row["children"], at_units)
            placed.append(
                SegStep(
                    id=row["id"],
                    name=row["name"],
                    spans=((start, end),),
                    confidence=DFLT_GRID_CONFIDENCE,
                    children=tuple(children),
                    source="grid-placed",
                    evidence={"duration_units": duration, "offset_units": at_units},
                )
            )
            at_units += duration
        return placed, at_units

    steps, total_units = _place(inputs["steps"], 0.0)
    boundaries = tuple(origin + units * spu for units in _cumulative(inputs["steps"]))
    return Segmentation(
        steps=tuple(steps),
        boundaries=boundaries,
        unit=grid.unit,
        grid=grid,
        confidence=DFLT_GRID_CONFIDENCE,
    )


def _cumulative(rows: list[dict]) -> list[float]:
    offsets, at = [0.0], 0.0
    for row in rows:
        at += row["duration"]
        offsets.append(at)
    return offsets


def _segment_explicit(inputs: Mapping[str, Any]) -> Segmentation:
    """Adopt boundaries supplied explicitly (by a human or a prior run).

    N boundaries make N-1 spans. Names zip on when a step list of the right
    length was supplied; otherwise the result is honestly unnamed
    (``naming-abstained``), never invented.
    """
    boundaries = tuple(sorted(inputs["boundaries"]))
    spans = list(zip(boundaries, boundaries[1:]))
    step_rows = inputs["steps"]
    flags: tuple[str, ...] = ()
    steps: tuple[SegStep, ...] = ()
    if step_rows and len(step_rows) == len(spans):
        steps = tuple(
            SegStep(
                id=row["id"],
                name=row["name"],
                spans=(span,),
                confidence=DFLT_EXPLICIT_CONFIDENCE,
                source="explicit",
            )
            for row, span in zip(step_rows, spans)
        )
    else:
        if step_rows:
            flags = (
                f"step-count-mismatch: {len(step_rows)} steps vs {len(spans)} spans",
            )
        else:
            flags = ("naming-abstained",)
        steps = tuple(
            SegStep(
                id=f"seg-{i + 1}",
                spans=(span,),
                confidence=DFLT_EXPLICIT_CONFIDENCE,
                source="explicit",
            )
            for i, span in enumerate(spans)
        )
    return Segmentation(
        steps=steps,
        boundaries=boundaries,
        confidence=DFLT_EXPLICIT_CONFIDENCE,
        flags=flags,
    )


GRID_PLACED = register(
    Capability(
        name="grid-placed",
        gives="segmentation",
        summary=(
            "Place an ordered step list with domain durations on the timeline "
            "using a metric grid (tempo + origin). The que-calor path."
        ),
        target="paces.segmenters:_segment_grid_placed",
        needs=frozenset({"steps", "steps.durations", "grid"}),
        base=1.0,
        resolution_s=0.1,
    )
)

EXPLICIT = register(
    Capability(
        name="explicit",
        gives="segmentation",
        summary=(
            "Adopt boundaries supplied explicitly — by a human ('ask the "
            "user' is first-class), a chapter file, or a previous run."
        ),
        target="paces.segmenters:_segment_explicit",
        needs=frozenset({"boundaries"}),
        base=0.5,
        resolution_s=0.01,
    )
)
