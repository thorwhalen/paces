"""Body schemas for the document envelope and its sources.

- ``annot://schema/guide-doc/v1`` (tier ``document``) — the one annotation
  that says *which guide this is*: id, title, language, domain, plus the
  analysis run's own report (``method``, ``flags``). Everything ordered or
  timed hangs off the other tiers.
- ``annot://schema/guide-source/v1`` (tier ``source``) — one per
  :class:`~paces.model.Source`.

Neither body carries an interval; both annotations attach as point
annotations at tick 0, which is lacing's spelling of "about the asset, not
about a region of it".

What is deliberately **not** here: ``locks``, ``questions``, ``artifacts``
and span ``excerpt`` windows. Those are document-layer records — a human
edit, an open question, a built file, a hand-picked loop — and
``docs/07 §6.0`` is explicit that nothing flows document → store. The
evidence layer holds what analysis produced; the document holds what people
did to it.
"""

from __future__ import annotations

from typing import Any

from lacing.schema import register_body_schema
from pydantic import Field

from paces.bodies._base import BodyBase, Decimal

DOC_TIER = "document"
DOC_BODY_SCHEMA_URI = "annot://schema/guide-doc/v1"

SOURCE_TIER = "source"
SOURCE_BODY_SCHEMA_URI = "annot://schema/guide-source/v1"


class GuideDocBodyV1(BodyBase):
    """The guide's envelope: identity, presentation language, and the run."""

    doc_id: str = Field(
        ...,
        description=(
            "Stable slug of the guide within a project. Distinct from the "
            "annotation id, and the field that lets one store hold several "
            "guides over the same asset."
        ),
    )
    title: str = Field(..., description="Human title of the guide.")
    lang: str = Field("en", description="BCP-47 language tag of the guide's prose.")
    domain: str = Field(
        "generic", description="Domain slug: dance | recipe | workout | ..."
    )
    schema_version: str = Field(
        ..., description="Version of the StepDocument schema this was projected at."
    )
    credits: str | None = Field(
        None, description="Attribution line, when there is one."
    )
    method: str = Field(
        "",
        description=(
            "Which segmentation capability produced the steps "
            "(``Segmentation.method``). Empty when unrecorded."
        ),
    )
    flags: list[str] = Field(
        default_factory=list,
        description=(
            "The run's honesty flags (``Segmentation.flags``) — "
            "'naming-abstained', 'origin-estimated: ...', and friends. "
            "Evidence about the run, never projected into the document."
        ),
    )
    attrs: dict[str, Any] = Field(
        default_factory=dict, description="Namespaced open bag, as on the document."
    )


class GuideSourceBodyV1(BodyBase):
    """One input the guide's spans refer into."""

    doc_id: str = Field(
        ...,
        description=(
            "Which guide this source belongs to — one store can hold several "
            "guides over the same asset, and a projection has to read back "
            "only its own."
        ),
    )
    ordinal: int = Field(
        ..., description="Position in the document's source list, 0-based."
    )
    source_id: str = Field(
        ..., description="Slug of the source within the guide. Not the annotation id."
    )
    kind: str = Field(..., description="video | audio | image | document | url.")
    uri: str = Field(..., description="Where the source lives.")
    asset_id: str | None = Field(
        None, description="Content hash of a local copy, if any."
    )
    duration_s: Decimal | None = Field(
        None, description="Source duration in seconds, as a decimal string."
    )
    title: str | None = Field(None, description="Source title.")
    attribution: str | None = Field(None, description="Who made it.")
    rights: str | None = Field(
        None,
        description=(
            "Usage rights. First-class in this domain (``docs/07 §8.7``): a "
            "guide that restyles someone's choreography has to say so."
        ),
    )
    attrs: dict[str, Any] = Field(default_factory=dict, description="Open bag.")


register_body_schema(DOC_BODY_SCHEMA_URI, GuideDocBodyV1)
register_body_schema(SOURCE_BODY_SCHEMA_URI, GuideSourceBodyV1)
