"""Body schemas for steps, sub-steps, and cues.

- ``annot://schema/guide-step/v1`` — one annotation per **(step, span)**
  (``docs/07 §6.3``), on tier ``step`` for top-level steps and tier
  ``step.sub`` (``INCLUDED_IN`` ``step``) for sub-steps. A step that appears
  in three places is three annotations sharing one ``step_id``;
  ``parent_step_id``, ``ordinal`` and ``span_index`` are what put the tree
  and its order back together.
- ``annot://schema/guide-cue/v1`` — one per cue, tier ``cue``
  (``INCLUDED_IN`` ``step``).

The span's ``start`` and ``end`` are **not** fields here: they are the
annotation's reference interval. What stays in the body is everything about
the span that is not a time — which source, which role, the label and the
caption a human will edit.

A step with no spans still gets exactly one annotation, with
``span_index=None`` and a point interval at tick 0. "This step exists, its
extent is not recorded" is a state the segmenters can legitimately return
(``paces/segmenters.py``'s honesty rules), so it is a state the store has to
be able to hold.
"""

from __future__ import annotations

from typing import Any

from lacing.schema import register_body_schema
from pydantic import Field

from paces.bodies._base import BodyBase, Decimal

STEP_TIER = "step"
SUB_STEP_TIER = "step.sub"
STEP_BODY_SCHEMA_URI = "annot://schema/guide-step/v1"

CUE_TIER = "cue"
CUE_BODY_SCHEMA_URI = "annot://schema/guide-cue/v1"


class GuideStepBodyV1(BodyBase):
    """One step's presence in one span (or its absence from every span)."""

    doc_id: str = Field(..., description="Which guide this step belongs to.")
    step_id: str = Field(
        ...,
        description=(
            "Stable id within the guide ('b4'). Distinct from the annotation "
            "id — document ids are slugs, store ids are UUIDs, and the two "
            "are related by this field, never conflated."
        ),
    )
    parent_step_id: str | None = Field(
        None, description="Enclosing step's id; None for a top-level step."
    )
    ordinal: int = Field(
        ..., description="Position among siblings, 0-based. Order is semantic."
    )
    name: str = Field(
        "",
        description="The step's name. Empty means found-but-not-named, a valid state.",
    )
    description: str = Field("", description="Prose about the step.")
    duration_value: Decimal = Field(
        ..., description="Duration in the domain's own unit, as a decimal string."
    )
    duration_unit: str = Field(
        ..., description="The domain unit: eight | rep | second."
    )
    repeat: int = Field(1, description="How many times the children cycle.")
    optional: bool = Field(False, description="'Facultatif — si tu le sens'.")
    variant_of: str | None = Field(
        None, description="Another angle on that step, not a new step."
    )
    tags: list[str] = Field(default_factory=list, description="Open tag vocabulary.")
    attrs: dict[str, Any] = Field(
        default_factory=dict, description="Namespaced open bag, as on the step."
    )

    span_index: int | None = Field(
        None,
        description=(
            "Which of the step's spans this annotation is, 0-based. None "
            "means the step has no spans at all and this is its only row."
        ),
    )
    span_count: int = Field(
        0, description="How many spans the step has, so a reader can tell rows apart."
    )
    span_source: str | None = Field(
        None, description="Slug of the source the span refers into."
    )
    span_role: str | None = Field(
        None, description="performance | instruction | closeup | ... (open vocab)."
    )
    span_open_ended: bool = Field(
        False,
        description=(
            "The span recorded a start but no end — a deep link, not an "
            "interval. The reference interval is then a point at the start, "
            "and this flag is what keeps that distinct from a zero-length span."
        ),
    )
    span_label: str | None = Field(None, description="Short label for this span.")
    span_caption: str | None = Field(
        None, description="Prose about THIS span, not about the step."
    )
    span_confidence: float | None = Field(
        None, ge=0.0, le=1.0, description="Confidence in this span specifically."
    )
    span_attrs: dict[str, Any] = Field(
        default_factory=dict, description="Open bag on the span."
    )


class GuideCueBodyV1(BodyBase):
    """A landmark the learner can hear or watch for, anchored to a step."""

    doc_id: str = Field(..., description="Which guide this cue belongs to.")
    ordinal: int = Field(
        ..., description="Position in the document's cue list, 0-based."
    )
    cue_id: str = Field(..., description="Stable id within the guide.")
    kind: str = Field(..., description="lyric | count | audio-landmark | caption | ...")
    text: str = Field(..., description="What the learner hears or reads.")
    step_id: str = Field(..., description="The step this cue is anchored to.")
    offset_value: Decimal | None = Field(
        None,
        description=(
            "Offset into the step, in the domain unit. RELATIVE, always — an "
            "absolute cue time is computed by ``resolve()``, never stored."
        ),
    )
    offset_unit: str | None = Field(None, description="Unit of ``offset_value``.")
    duration_value: Decimal | None = Field(
        None, description="How long the cue lasts, in the domain unit."
    )
    duration_unit: str | None = Field(None, description="Unit of ``duration_value``.")
    source: str | None = Field(
        None, description="Which source the cue was heard in, when known."
    )
    at_resolved: bool = Field(
        False,
        description=(
            "True when the cue's wall-clock position in that source is known, "
            "in which case the reference is a point at it. False means the "
            "annotation sits at tick 0 because there is nothing better — the "
            "one bit that keeps 'at second zero' distinct from 'unknown'."
        ),
    )
    attrs: dict[str, Any] = Field(default_factory=dict, description="Open bag.")


register_body_schema(STEP_BODY_SCHEMA_URI, GuideStepBodyV1)
register_body_schema(CUE_BODY_SCHEMA_URI, GuideCueBodyV1)
