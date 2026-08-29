"""The schema's acceptance test: the POC round-trips through the IR.

Kickoff step 2: re-express the POC's own ``clips.json`` (+ the page's
``ROUTINE``) in the ``StepDocument`` schema. If the dance case does not
round-trip — every value preserved, multi-span steps expressed, domain
durations kept, grid math reproducing the POC's measured boundaries — the
schema is wrong.
"""

from __future__ import annotations

import json
from fractions import Fraction

import pytest

from paces.model import (
    Step,
    StepDocument,
    dumps_document,
    loads_document,
    resolve,
    seconds_per_unit,
    validate_document,
)
from poc_fixture import CLIPS_PATH, dec, poc_document

#: Documented ground truth from the POC session (docs/01-what-was-built.md):
#: block 4's four 8-count boundaries, independently re-derived in-session.
BLOCK4_EIGHT_BOUNDARIES = (95.8, 99.5, 103.3, 107.0)
GRID_TOLERANCE_S = 0.15
#: yt_run deep links were hand-picked near block starts, not measured on them.
DEEP_LINK_TOLERANCE_S = 3.5


@pytest.fixture(scope="module")
def doc() -> StepDocument:
    return poc_document()


@pytest.fixture(scope="module")
def clips() -> list[dict]:
    return json.loads(CLIPS_PATH.read_text(encoding="utf-8"))


def _walk(steps) -> list[Step]:
    out = []
    for step in steps:
        out.append(step)
        out.extend(_walk(step.steps))
    return out


def test_document_is_semantically_valid(doc):
    assert validate_document(doc) == []


def test_wire_roundtrip_is_lossless(doc):
    text = dumps_document(doc)
    assert loads_document(text) == doc


def test_no_floats_on_the_wire(doc):
    def _no_floats(text: str):
        pytest.fail(f"float literal on the wire: {text}")

    json.loads(dumps_document(doc), parse_float=_no_floats)


def test_wire_is_camel_case_and_readable(doc):
    text = dumps_document(doc)
    assert '"schemaVersion"' in text
    assert '"tempoBpm"' in text
    assert "Céline" in text  # ensure_ascii=False: accents readable in a diff
    assert text.endswith("\n")


def test_durations_are_domain_units(doc):
    total = sum(Fraction(step.duration.value) for step in doc.steps)
    assert total == 44  # "44 × 8 temps" — the page's own count
    assert all(step.duration.unit == "eight" for step in doc.steps)


def test_every_block_has_both_passes(doc):
    """A step has SEVERAL source spans: the run-through and the breakdown of
    the same step both survive (the load-bearing multi-span requirement)."""
    for block in doc.steps:
        roles = {span.role for step in _walk([block]) for span in step.spans}
        assert "performance" in roles, f"{block.id} lost its run-through link"
        assert {"instruction", "closeup"} & roles, f"{block.id} lost its breakdown link"


def test_alt_clips_kept_their_three_different_meanings(doc):
    by_id = {step.id: step for step in _walk(doc.steps)}
    # b5b: a sub-step
    assert by_id["b5-2"].name == "De l'autre côté"
    assert any(span.excerpt for span in by_id["b5-2"].spans)
    # b6b: an optional add-on variant
    assert by_id["b6-chaleur"].optional
    # b9b: a close-up on the same move, not a new step
    assert "b9-closeup" not in by_id
    assert any(span.role == "closeup" for span in by_id["b9"].spans)


def test_block9_repeat_replaces_the_display_override(doc):
    block9 = next(step for step in doc.steps if step.id == "b9")
    assert block9.repeat == 4
    assert len(block9.steps) == 2
    child_sum = sum(Fraction(c.duration.value) for c in block9.steps)
    assert block9.repeat * child_sum == Fraction(block9.duration.value)


def test_every_clip_value_survives(doc, clips):
    """Zero data loss: every field of all 15 clips rows lands, typed."""
    text = dumps_document(doc)
    all_steps = _walk(doc.steps)
    starts = {span.start for step in all_steps for span in step.spans}
    excerpts = {
        span.excerpt for step in all_steps for span in step.spans if span.excerpt
    }
    captions = {
        span.caption for step in all_steps for span in step.spans if span.caption
    }
    labels = {span.label for step in all_steps for span in step.spans if span.label}
    artifact_uris = {artifact.uri for step in all_steps for artifact in step.artifacts}
    for clip in clips:
        assert dec(clip["yt_run"]) in starts, clip["id"]
        assert dec(clip["yt_expl"]) in starts, clip["id"]
        assert (dec(clip["start"]), dec(clip["start"] + clip["dur"])) in excerpts, clip[
            "id"
        ]
        assert clip["cap"] in captions, clip["id"]
        assert clip["tab"] in labels, clip["id"]
        assert f"media/{clip['id']}.mp4" in artifact_uris, clip["id"]
        assert clip["fig"] in text, clip["id"]


def test_routine_values_survive(doc):
    text = dumps_document(doc)
    for fragment in (
        "Mise en place",
        "Pas pointe et ronde — « marche, pose, marche, ramène »",
        "Déhanchés en bougeant les bras et les mains (étoiles)",
        "se hace difícil respirar",
        "qué calor",
        "À remplacer par les 1ers déhanchés ?",
    ):
        assert fragment in text


def test_grid_reproduces_the_pocs_measured_boundaries(doc):
    """The resolved grid lands on the boundaries the POC measured and an
    independent agent re-derived (block 4's four eights)."""
    resolved = resolve(doc)
    assert resolved["unit"] == "eight"
    spu = resolved["seconds_per_unit"]
    assert spu == pytest.approx(3.715, abs=0.001)

    block4 = next(row for row in resolved["steps"] if row["id"] == "b4")
    for k, expected in enumerate(BLOCK4_EIGHT_BOUNDARIES):
        assert block4["start_s"] + k * spu == pytest.approx(
            expected, abs=GRID_TOLERANCE_S
        )


def test_grid_agrees_with_the_deep_links(doc, clips):
    """Every block's computed start lands near its hand-picked run-through
    deep link — the grid and the human agree about where the blocks are."""
    resolved = resolve(doc)
    yt_run_of_block = {
        f"b{clip['block']}": clip["yt_run"] for clip in clips if clip["kind"] == "main"
    }
    for row in resolved["steps"]:
        assert row["start_s"] == pytest.approx(
            yt_run_of_block[row["id"]], abs=DEEP_LINK_TOLERANCE_S
        ), row["id"]


def test_rights_and_attribution_are_content(doc):
    source = doc.sources[0]
    assert source.attribution and "Céline Pradeu" in source.attribution
    assert source.rights  # the restyling obligation travels with the document
