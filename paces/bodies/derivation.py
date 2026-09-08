"""Body schema for derivation recipes — the POC's ``crops.json``, promoted.

``annot://schema/guide-recipe/v1``, tier ``derivation``
(``SYMBOLIC_ASSOCIATION`` under ``step``): the *parameters* a derived file
was made with, so a re-run is stable and a human override survives it.
``docs/07 §6.2``'s split, stated once: the document's
:class:`~paces.model.ArtifactRef` says **what** a file is; this says **how**
it was made.

The recipe's ``window`` is not a field — it is the annotation's reference
interval, which is exactly what a window is. Everything else is
:class:`paces.derivation.CropRecipe` as it already exists on disk, with the
box's coordinates crossing as decimal strings; the sidecar is committed, so
it has always been float-free and the store keeps it that way.
"""

from __future__ import annotations

from lacing.schema import register_body_schema
from pydantic import Field

from paces.bodies._base import BodyBase, Decimal

RECIPE_TIER = "derivation"
RECIPE_BODY_SCHEMA_URI = "annot://schema/guide-recipe/v1"


class GuideRecipeBodyV1(BodyBase):
    """One span's derivation parameters, keyed by the span address."""

    doc_id: str = Field(..., description="Which guide this recipe belongs to.")
    span_key: str = Field(
        ...,
        description=(
            "The span address ``{step_id}/{source}/{role}/{start}`` — the same "
            "key ``paces.derivation`` writes into the committed sidecar, so "
            "the two layers join without a translation table."
        ),
    )
    step_id: str = Field(..., description="The step this recipe derives media for.")
    box: list[Decimal] | None = Field(
        None,
        description=(
            "The resolved crop box (x, y, w, h) in pixels, as decimal "
            "strings. None means full frame — a recorded decision, not a gap."
        ),
    )
    frame_width: int = Field(..., description="Source frame width the box is in.")
    frame_height: int = Field(..., description="Source frame height the box is in.")
    source_asset_id: str | None = Field(
        None, description="Hash of the media cut from. None = identity unverified."
    )
    locator: str = Field(
        ..., description="Which subject locator resolved the box ('full_frame', ...)."
    )
    params: dict[str, Decimal] = Field(
        default_factory=dict,
        description=(
            "Policy parameters the box was resolved under (aspect, pad). A "
            "change here re-locates an unlocked entry."
        ),
    )
    locked: bool = Field(
        False, description="A human set this box; reconcile must not re-derive it."
    )
    media_digest: str | None = Field(
        None,
        description=(
            "What the stored media was actually cut with (box + window + "
            "source hash). A hand-edited box or a re-timed window changes it "
            "and forces a re-encode instead of serving stale bytes."
        ),
    )


register_body_schema(RECIPE_BODY_SCHEMA_URI, GuideRecipeBodyV1)
