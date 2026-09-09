"""The body-schema URIs paces claims, pinned with their content.

``lacing.schema``'s registry is one flat, fleet-wide dict and
``register_body_schema`` is last-write-wins and silent, so a URI is a claim
on a shared namespace, not a local name. This file is the guard on both
halves of that claim:

- **which URIs** paces owns (a rename, an addition or a drop fails here), and
  that they do not collide with a name another fleet package already owns;
- **what is inside them** — the committed JSON Schema snapshot in
  ``tests/data/body_schemas.json``. New URIs are additive and need no
  migration; a *changed* one is a wire break for every already-written store,
  and this test is what makes that a decision rather than an accident.

Regenerating the snapshot deliberately::

    python -m tests.test_evidence_schemas   # writes tests/data/body_schemas.json
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("lacing")

from lacing.schema import json_schema, registered_uris  # noqa: E402

from paces.bodies import PACES_BODY_SCHEMA_URIS, WORD_BODY_SCHEMA_URI  # noqa: E402

SNAPSHOT = Path(__file__).parent / "data" / "body_schemas.json"

#: Names other fleet packages already own on this shared namespace, checked
#: here so paces never quietly takes one over. ``beat/v1`` is the live
#: example: it is reelee's *narrative* beat, which is why paces' musical one
#: is ``guide-beat/v1``.
FOREIGN_URIS = (
    "annot://schema/beat/v1",  # reelee — a narrative beat
    "annot://schema/step/v1",  # unclaimed, but too generic to take
    "annot://schema/cue/v1",  # unclaimed, but too generic to take
    "annot://schema/section/v1",  # nw
    "annot://schema/shot/v1",  # nw
    "annot://schema/clip/v1",  # reelee
    "annot://schema/source/v1",  # braidio
    "annot://schema/named-entity/v1",  # lacing
)


def _snapshot() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_the_uri_set_is_exactly_what_is_pinned():
    assert sorted(PACES_BODY_SCHEMA_URIS) == sorted(_snapshot())


def test_every_pinned_schema_still_has_its_pinned_content():
    snapshot = _snapshot()
    for uri, expected in snapshot.items():
        assert json_schema(uri) == expected, (
            f"{uri} changed shape. New URIs are additive and free; CHANGING "
            "one breaks every store already written against it. If the change "
            "is intended, bump to /v2 and register a migration — do not "
            "re-snapshot in place."
        )


def test_paces_claims_no_name_another_package_owns():
    assert not set(PACES_BODY_SCHEMA_URIS) & set(FOREIGN_URIS)


def test_importing_the_bodies_registers_them():
    registered = set(registered_uris())
    assert set(PACES_BODY_SCHEMA_URIS) <= registered
    # word/v1 is reused, not claimed: it must be there, and it must be
    # lacing's model, not a paces copy.
    assert WORD_BODY_SCHEMA_URI in registered
    assert WORD_BODY_SCHEMA_URI not in PACES_BODY_SCHEMA_URIS


def _write_snapshot() -> None:
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    payload = {uri: json_schema(uri) for uri in sorted(PACES_BODY_SCHEMA_URIS)}
    SNAPSHOT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    _write_snapshot()
    print(f"wrote {SNAPSHOT}")
