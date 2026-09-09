"""Shared conventions for every paces body schema.

One base class and one type alias, so the three rules that make a body
round-trippable are stated once rather than re-typed per module: frozen,
``extra="forbid"`` (lacing non-negotiable #3), and decimal strings where the
document would refuse a float.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

#: Exact decimal number as a string ("231.3") — the document's wire form for
#: any quantity, mirrored here so a body never carries a float the document
#: itself would reject (``docs/07 §6.5``).
Decimal = Annotated[str, Field(pattern=r"^-?\d+(\.\d+)?$")]


class BodyBase(BaseModel):
    """Frozen, closed-world body model — lacing validates against it by URI."""

    model_config = {"frozen": True, "extra": "forbid"}
