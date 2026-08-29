"""The paces intermediate representation: the ``StepDocument``.

This is the contract between *analysis* (segment media into steps) and
*rendering* (emit a practice page, a PDF, a deck). Renderers depend on this
document and never on the analyser — the parse → AST → render split the whole
package is organised around (``docs/03-design-brief.md §1``).

Design decisions, each argued in ``docs/07-annotation-model.md``:

- **A step has SEVERAL source spans.** The at-tempo run-through and the slow
  explanation are the same step seen twice; ``Step.spans`` is a list and a
  one-span model is wrong on day one.
- **Duration is domain-specific.** A dance counts 8-counts, a workout counts
  reps; ``Measure(value, unit)`` stores the unit the learner actually counts,
  and wall-clock seconds are *derived* via the optional ``MetricGrid``.
- **No floats on the wire.** Times are decimal strings (``"231.3"``) — exact,
  diffable as one token. Absolute positions are computed by :func:`resolve`,
  never stored.
- **camelCase on the wire, snake_case in Python** (the walkthru convention).
- **Uncertainty is content.** The POC's ``note`` fields are promoted to
  :class:`OpenQuestion`; human decisions regeneration must not overwrite are
  :class:`Lock` records.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

SCHEMA_VERSION = "0.1.0"

#: Git-readable stable identifier — deliberately NOT a uuid4.
Slug = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")]

#: Exact decimal number as a string ("231.3") — no float representation drift.
Decimal = Annotated[str, Field(pattern=r"^-?\d+(\.\d+)?$")]


class _Base(BaseModel):
    """Shared model config: camelCase wire, strict fields."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid"
    )


# ── identity & units ────────────────────────────────────────────────────────


class Measure(_Base):
    """A duration in the DOMAIN's own unit — never seconds unless the domain's
    unit is seconds."""

    value: Decimal
    unit: Slug  # "eight" | "bar" | "rep" | "second" | "minute" | ...


class MetricGrid(_Base):
    """How the domain unit relates to wall-clock time, when it does at all.

    Optional by design: a "reps" domain has no grid; a dance routine does —
    and the grid is what drives the metronome and :func:`resolve`.
    """

    unit: Slug  # "eight"
    subdivisions: int = 1  # beats per unit (8 for an 8-count)
    tempo_bpm: Decimal | None = None  # "129.2"
    origin: Decimal | None = None  # seconds into origin_source where unit 0 starts
    origin_source: Slug | None = None


# ── sources & spans ─────────────────────────────────────────────────────────


class Source(_Base):
    """One input the document's spans refer into (a video, a notes doc, ...)."""

    id: Slug
    kind: Literal["video", "audio", "image", "document", "url"]
    uri: str
    asset_id: str | None = None  # content hash of a local copy, if any
    duration_s: Decimal | None = None
    title: str | None = None
    attribution: str | None = None
    rights: str | None = None  # rights are content in this domain (docs/07 §3)
    attrs: dict[str, Any] = Field(default_factory=dict)


class SourceSpan(_Base):
    """ONE step's presence in ONE source, in ONE role. A step has a LIST of
    these — several roles is the norm, not the exception.

    ``end=None`` means "starts here, extent not recorded" (a deep link is a
    point of entry, not an interval; recording an end it does not know would
    be invention, not data).
    """

    source: Slug
    role: Slug = "performance"  # open vocab: performance|instruction|closeup|...
    start: Decimal
    end: Decimal | None = None
    excerpt: tuple[Decimal, Decimal] | None = None  # loopable sub-window
    label: str | None = None
    caption: str | None = None  # prose about THIS span, not the step
    confidence: float | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)


# ── derived artifacts ───────────────────────────────────────────────────────


class ArtifactRef(_Base):
    """WHAT a derived file is, never HOW it was made — the recipe lives in the
    evidence layer, keyed by ``asset_id``."""

    role: Slug  # clip | gif | poster | thumbnail | waveform | audio
    uri: str  # relative to the document — deploy-portable
    asset_id: str | None = None  # 64-hex SHA-256, the durable identity
    mime: str | None = None
    width: int | None = None
    height: int | None = None
    duration_s: Decimal | None = None
    derived_from: Slug | None = None  # which SourceSpan.role it came from
    attrs: dict[str, Any] = Field(default_factory=dict)


# ── cues: their own track, anchored by step id ──────────────────────────────


class Anchor(_Base):
    """Where a cue attaches: a step, plus an optional relative offset in the
    domain unit. NEVER an absolute time."""

    step: Slug
    offset: Measure | None = None


class Cue(_Base):
    """A landmark the learner can hear or watch for (a lyric, a count, ...)."""

    id: Slug
    kind: Slug  # lyric | count | audio-landmark | caption | warning
    text: str
    anchor: Anchor
    duration: Measure | None = None
    source: Slug | None = None
    at_s: Decimal | None = None  # optional resolved time in that source
    attrs: dict[str, Any] = Field(default_factory=dict)


# ── provenance & edit protection ────────────────────────────────────────────


class Lock(_Base):
    """A human (or approved-AI) decision that regeneration MUST NOT overwrite."""

    path: str  # JSON pointer relative to the node: "/name", "/spans/1/caption"
    by: str  # "user:thor" | "agent:<model>@<hash>"
    at: str  # ISO-8601 UTC, second resolution
    was: Any | None = None  # the pre-edit value — makes the edit reversible
    reason: str | None = None


class Origin(_Base):
    """Back-reference into the evidence layer: why this node says what it says,
    and what a regeneration may replace."""

    annotation_id: str | None = None
    value_digest: str | None = None
    generated_by: str | None = None  # "segmenter:grid-placed" | "user:thor"
    confidence: float | None = None


class OpenQuestion(_Base):
    """The POC's ``note`` fields, promoted: uncertainty and its resolution are
    first-class content, not scratch."""

    id: Slug
    text: str
    status: Literal["open", "settled", "dropped"] = "open"
    resolution: str | None = None
    evidence: list[SourceSpan] = Field(default_factory=list)


# ── the step ────────────────────────────────────────────────────────────────


class Step(_Base):
    """One named piece of the routine — the unit a learner practises.

    A step is a step: sub-steps are ``Step``s in ``steps``. ``repeat`` says the
    children cycle N times (the POC's block 9 is ``repeat=4`` over two
    sub-steps — structure, where the original hand-wrote a display override).
    """

    id: Slug  # stable across re-runs, human-meaningful ("b4")
    name: str
    duration: Measure
    description: str = ""
    spans: list[SourceSpan] = Field(default_factory=list)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    steps: list["Step"] = Field(default_factory=list)
    repeat: int = 1
    optional: bool = False
    variant_of: Slug | None = None
    tags: list[Slug] = Field(default_factory=list)
    questions: list[OpenQuestion] = Field(default_factory=list)
    origin: Origin | None = None
    locks: list[Lock] = Field(default_factory=list)
    attrs: dict[str, Any] = Field(default_factory=dict)


# ── the document ────────────────────────────────────────────────────────────


class StepDocument(_Base):
    """The committed, hand-editable, git-diffable step document — the AST."""

    kind: Literal["StepDocument"] = "StepDocument"
    schema_version: str = SCHEMA_VERSION
    id: Slug
    title: str
    lang: str = "en"  # BCP-47
    domain: Slug = "generic"  # "dance" | "recipe" | "workout" | ...
    metric: MetricGrid | None = None
    sources: list[Source] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)  # ORDER IS SEMANTIC
    cues: list[Cue] = Field(default_factory=list)
    questions: list[OpenQuestion] = Field(default_factory=list)
    credits: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)


# ── serialisation (the git rules of docs/07 §6.5) ───────────────────────────


def dumps_document(doc: StepDocument) -> str:
    """Serialise a document to its canonical wire form.

    camelCase keys in declaration order, 2-space indent, UTF-8 readable
    (``ensure_ascii=False`` equivalent), trailing newline.
    """
    import json

    payload = doc.model_dump(mode="json", by_alias=True, exclude_none=True)
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def loads_document(text: str) -> StepDocument:
    """Parse a document from its wire form (accepts camelCase or snake_case)."""
    return StepDocument.model_validate_json(text)


# ── resolution: absolute positions are computed, never stored ───────────────


def seconds_per_unit(grid: MetricGrid) -> float | None:
    """Seconds one domain unit lasts under *grid*, or None without a tempo.

    >>> seconds_per_unit(MetricGrid(unit='eight', subdivisions=8, tempo_bpm='129.2'))
    3.7151702786377707
    """
    if grid.tempo_bpm is None:
        return None
    return float(grid.subdivisions * 60 / Fraction(grid.tempo_bpm))


def resolve(doc: StepDocument) -> dict:
    """Compute absolute metric offsets (and wall-clock times, when the grid
    allows) for every step. Pure; the analogue of walkthru's
    ``resolve_timeline``.

    Returns a JSON-able dict: ``{"unit", "seconds_per_unit", "origin_s",
    "total_units", "steps": [{"id", "name", "offset", "duration", "start_s",
    "end_s", "repeat", "children": [...]}, ...]}``. Times are floats — this is
    a computed view, not the stored document.
    """
    grid = doc.metric
    spu = seconds_per_unit(grid) if grid is not None else None
    origin = float(Fraction(grid.origin)) if grid and grid.origin else None

    def _wall(offset_units: float) -> float | None:
        if spu is None or origin is None:
            return None
        return origin + offset_units * spu

    def _resolve_steps(steps: list[Step], at: float) -> tuple[list[dict], float]:
        rows = []
        for step in steps:
            dur = float(Fraction(step.duration.value))
            children, _ = _resolve_steps(step.steps, at)
            rows.append(
                {
                    "id": step.id,
                    "name": step.name,
                    "offset": at,
                    "duration": dur,
                    "start_s": _wall(at),
                    "end_s": _wall(at + dur),
                    "repeat": step.repeat,
                    "children": children,
                }
            )
            at += dur
        return rows, at

    rows, total = _resolve_steps(doc.steps, 0.0)
    return {
        "unit": grid.unit if grid else None,
        "seconds_per_unit": spu,
        "origin_s": origin,
        "total_units": total,
        "steps": rows,
    }


def validate_document(doc: StepDocument) -> list[str]:
    """Semantic checks beyond the schema. Returns human-readable issues
    (empty list = clean); never raises.

    Checks: children durations account for the parent's (``repeat`` included),
    span sources exist, cue anchors point at real steps.
    """
    issues: list[str] = []
    source_ids = {s.id for s in doc.sources}
    step_ids: set[str] = set()

    def _walk(step: Step, path: str) -> None:
        step_ids.add(step.id)
        for i, span in enumerate(step.spans):
            if span.source not in source_ids:
                issues.append(f"{path}/spans/{i}: unknown source {span.source!r}")
        if step.steps:
            child_sum = sum(Fraction(c.duration.value) for c in step.steps)
            expected = Fraction(step.duration.value)
            optional_present = any(c.optional or c.variant_of for c in step.steps)
            if step.repeat * child_sum != expected and not optional_present:
                issues.append(
                    f"{path}: children sum to {step.repeat} x {child_sum} "
                    f"!= duration {expected}"
                )
        for child in step.steps:
            _walk(child, f"{path}/steps/{child.id}")

    for step in doc.steps:
        _walk(step, f"/steps/{step.id}")
    for cue in doc.cues:
        if cue.anchor.step not in step_ids:
            issues.append(f"/cues/{cue.id}: anchor step {cue.anchor.step!r} not found")
    return issues
