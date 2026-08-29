"""The segmenter seam: selection, the two v1 segmenters, honesty states."""

from __future__ import annotations

import json

import pytest

from paces.model import MetricGrid
from paces.projection import to_document
from paces.segmenters import Capability, capabilities, register, segment

GRID = {"unit": "eight", "subdivisions": 8, "tempoBpm": "129.2", "origin": "51.2"}
#: The POC routine as (name, eights) pairs — kickoff's "common real case".
ROUTINE_STEPS = [
    ("Mise en place", 2),
    ("Pas pieds pointe et ronde", 6),
    ("Soleil avec les bras", 4),
    ("Déhanchés", 8),
    ("Moulinets de bras", 4),
    ("Genou vers le bas", 4),
    ("Pas pieds pointe, bras alternés", 4),
    ("Taper dans les mains du voisin", 4),
    ("Avancer / reculer sur le refrain", 8),
]


def test_grid_placed_selected_and_placed():
    seg = segment("video.mp4", steps=ROUTINE_STEPS, grid=GRID)
    assert seg.method == "grid-placed"
    assert seg.unit == "eight"
    assert len(seg.steps) == 9
    assert seg.boundaries[0] == pytest.approx(51.2)
    # block 4 starts 12 eights in: 51.2 + 12 * 3.715 ≈ 95.78 (POC: 95.8)
    block4 = seg.steps[3]
    assert block4.spans[0][0] == pytest.approx(95.78, abs=0.05)
    assert block4.name == "Déhanchés"
    # ids are readable slugs, accents folded
    assert block4.id == "dehanches"


def test_grid_placed_places_children_within_the_parent():
    steps = [
        {"name": "Déhanchés", "duration": 8, "children": [("tête", 4), ("étoiles", 4)]},
    ]
    seg = segment("video.mp4", steps=steps, grid=GRID)
    parent = seg.steps[0]
    assert len(parent.children) == 2
    assert parent.children[0].spans[0][0] == pytest.approx(parent.spans[0][0])
    assert parent.children[1].spans[0][0] == pytest.approx(
        parent.spans[0][0] + 4 * 3.71517, abs=0.01
    )


def test_explicit_boundaries_with_names():
    seg = segment(boundaries=[0, 10, 20], steps=["intro", "verse"])
    assert seg.method == "explicit"
    assert [step.name for step in seg.steps] == ["intro", "verse"]
    assert seg.steps[0].spans == ((0.0, 10.0),)
    assert seg.flags == ()


def test_explicit_boundaries_abstain_from_naming():
    """Found-unnamed is a valid, honest state — names are never invented."""
    seg = segment(boundaries=[0, 10, 20, 30])
    assert seg.boundaries == (0.0, 10.0, 20.0, 30.0)
    assert all(step.name == "" for step in seg.steps)
    assert "naming-abstained" in seg.flags


def test_refusal_is_a_result_not_an_exception():
    seg = segment("video.mp4")
    assert seg.steps == () and seg.boundaries == ()
    assert seg.confidence == 0.0
    assert "no-signal" in seg.flags
    assert any(flag.startswith("try:") for flag in seg.flags)


def test_named_segmenter_overrides_selection():
    seg = segment(
        boundaries=[0, 5], steps=[("all of it", 4)], grid=GRID, segmenter="explicit"
    )
    assert seg.method == "explicit"


def test_named_segmenter_with_missing_inputs_says_what_is_missing():
    with pytest.raises(ValueError, match="grid"):
        segment("video.mp4", segmenter="grid-placed", steps=ROUTINE_STEPS)


def test_unknown_segmenter_lists_the_registry():
    with pytest.raises(ValueError, match="explicit"):
        segment("video.mp4", segmenter="does-not-exist")


def test_registering_a_capability_is_additive():
    """ADR-0003 §1: adding a segmenter edits nothing that exists."""
    before = set(capabilities())
    register(
        Capability(
            name="test-noop",
            gives="segmentation",
            summary="test",
            target="paces.segmenters:_segment_explicit",
            needs=frozenset({"boundaries"}),
        )
    )
    try:
        assert set(capabilities()) == before | {"test-noop"}
        seg = segment(boundaries=[0, 1], segmenter="test-noop")
        assert seg.method == "test-noop"
    finally:
        from paces import segmenters as segment_module

        segment_module._CAPABILITIES.pop("test-noop")


def test_to_document_carries_units_grid_and_decimal_strings():
    seg = segment("video.mp4", steps=ROUTINE_STEPS, grid=GRID)
    doc = to_document(
        seg,
        doc_id="que-calor",
        title="Que Calor",
        source="https://youtu.be/q_TUyxUhoEw",
    )
    assert doc.metric is not None and doc.metric.tempo_bpm == "129.2"
    assert doc.steps[0].duration.model_dump() == {"value": "2", "unit": "eight"}
    span = doc.steps[0].spans[0]
    assert span.start == "51.2"
    if "." in span.end:
        assert len(span.end.split(".")[1]) <= 3  # clean decimals, no float drift
    assert doc.sources[0].uri == "https://youtu.be/q_TUyxUhoEw"
    # provenance: which segmenter said so
    assert doc.steps[0].origin.generated_by == "segmenter:grid-placed"


def test_tools_segment_accepts_json_strings():
    from paces.tools import segment as segment_tool

    payload = segment_tool(
        "video.mp4",
        steps=json.dumps([["intro", 2], ["outro", 2]]),
        grid=json.dumps(GRID),
    )
    assert payload["method"] == "grid-placed"
    assert payload["steps"][0]["name"] == "intro"
    json.dumps(payload)  # JSON-ready throughout
