"""Body schemas for what was measured off the media: passes, the grid, beats.

- ``annot://schema/guide-pass/v1`` (tier ``source.pass``) — *"[45 s, 215 s]
  is a music pass; [220 s, 520 s] is speech"*. The speech/music split
  ``paces.measure`` gets from ``mixing.find_segments``, which is what made
  the POC's dual timestamps possible in the first place.
- ``annot://schema/guide-grid/v1`` (tier ``grid``) — the metric grid, **one**
  annotation over the region it governs.
- ``annot://schema/guide-beat/v1`` (tier ``beat``) — one point annotation per
  *measured* beat.

Why the grid is one annotation and the beats are separate: paces' grid is
closed form (``tempo_bpm`` + ``origin`` + ``subdivisions``), so materialising
N beats *from* it would be a denormalised cache with no invalidation story —
the same argument ``docs/07 §7`` uses to refuse materialising Allen
relations. Beat annotations are therefore written only when a producer hands
over times it actually measured, and they carry a ``was_derived_from`` edge
to the grid so a re-measure invalidates them.

Transcripts reuse lacing's own ``annot://schema/word/v1`` unchanged, on tier
``transcript.word``; the URIs and tier name live here so every evidence tier
is named in one place.
"""

from __future__ import annotations

import lacing.bodies  # noqa: F401  — registers the word/v1 paces reuses
from lacing.schema import register_body_schema
from pydantic import Field

from paces.bodies._base import BodyBase, Decimal

PASS_TIER = "source.pass"
PASS_BODY_SCHEMA_URI = "annot://schema/guide-pass/v1"

GRID_TIER = "grid"
GRID_BODY_SCHEMA_URI = "annot://schema/guide-grid/v1"

BEAT_TIER = "beat"
BEAT_BODY_SCHEMA_URI = "annot://schema/guide-beat/v1"

#: Transcripts are lacing's, not paces'. Named here so the tier table is
#: complete in one file; NOT registered here, and NOT in
#: ``PACES_BODY_SCHEMA_URIS`` — ``lacing.bodies.word`` owns it.
WORD_TIER = "transcript.word"
WORD_BODY_SCHEMA_URI = "annot://schema/word/v1"


class GuidePassBodyV1(BodyBase):
    """A stretch of one source with a single character (music, speech, ...)."""

    label: str = Field(
        ...,
        description=(
            "What this stretch is: 'music' | 'speech' | '' when the detector "
            "found a segment it would not name."
        ),
    )
    detector: str = Field(
        "",
        description=(
            "What produced the split ('mixing.find_segments:speech_music'). "
            "Empty when the caller supplied passes without saying."
        ),
    )


class GuideGridBodyV1(BodyBase):
    """How the domain unit relates to wall-clock time, over the region it governs.

    The document's ``metric`` is projected straight back out of this — one
    grid, one source of truth, no second copy in the document envelope.
    """

    doc_id: str = Field(
        ...,
        description=(
            "Which guide this grid governs. The grid is per-guide, not "
            "per-asset: two guides can count the same video differently."
        ),
    )
    unit: str = Field(..., description="The domain unit counted: eight | bar | rep.")
    subdivisions: int = Field(1, ge=1, description="Beats per unit (8 for an 8-count).")
    tempo_bpm: Decimal | None = Field(
        None,
        description=(
            "Tempo as a decimal string. None spells 'tempo unknown' — never '0'."
        ),
    )
    origin: Decimal | None = Field(
        None, description="Seconds into ``origin_source`` where unit 0 starts."
    )
    origin_source: str | None = Field(
        None, description="Which source ``origin`` is measured in."
    )
    beat_count: int | None = Field(
        None,
        description=(
            "How many beats were actually tracked, when the grid was measured "
            "rather than supplied. None means nobody counted."
        ),
    )
    method: str = Field(
        "",
        description=(
            "Which capability produced the grid ('grid-measured', "
            "'grid-placed'). Empty when the caller supplied it outright."
        ),
    )


class GuideBeatBodyV1(BodyBase):
    """One measured beat. The time is the reference's point interval."""

    index: int = Field(
        ..., description="Position in the measured beat sequence, 0-based."
    )


register_body_schema(PASS_BODY_SCHEMA_URI, GuidePassBodyV1)
register_body_schema(GRID_BODY_SCHEMA_URI, GuideGridBodyV1)
register_body_schema(BEAT_BODY_SCHEMA_URI, GuideBeatBodyV1)
