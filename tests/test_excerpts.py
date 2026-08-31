"""Excerpt suggestion (issue #3's v1 heuristic) — pure, no media."""

from __future__ import annotations

import json

import pytest

from paces.excerpts import suggest_excerpts
from paces.model import (
    Lock,
    Measure,
    MetricGrid,
    Source,
    SourceSpan,
    Step,
    StepDocument,
    dumps_document,
)

GRID = MetricGrid(unit="eight", subdivisions=8, tempo_bpm="120", origin="10")
SPU = 4.0  # 8 * 60 / 120


def _doc(steps, *, metric=GRID):
    return StepDocument(
        id="routine",
        title="Routine",
        metric=metric,
        sources=[Source(id="perf", kind="video", uri="https://x")],
        steps=steps,
    )


def _step(step_id="b1", *, spans=None, **kwargs):
    return Step(
        id=step_id,
        name="Step",
        duration=Measure(value="2", unit="eight"),
        spans=spans
        if spans is not None
        else [SourceSpan(source="perf", start="10", end="18")],
        **kwargs,
    )


def test_default_is_the_spans_whole_window():
    result = suggest_excerpts(_doc([_step()]))
    (span,) = result.document.steps[0].spans
    assert span.excerpt == ("10", "18")
    assert result.suggested == ["b1"] and result.flags == []


def test_units_takes_the_first_n_grid_units():
    result = suggest_excerpts(_doc([_step()]), units=1)
    (span,) = result.document.steps[0].spans
    assert span.excerpt == ("10", "14")  # 1 unit at 4 s/unit


def test_units_is_clipped_to_the_spans_end():
    result = suggest_excerpts(_doc([_step()]), units=5)
    (span,) = result.document.steps[0].spans
    assert span.excerpt == ("10", "18")  # 5 x 4 = 20s, clipped at end


def test_units_without_a_grid_flags_and_suggests_nothing():
    result = suggest_excerpts(_doc([_step()], metric=None), units=1)
    assert any(f.startswith("no-grid") for f in result.flags)
    assert result.document.steps[0].spans[0].excerpt is None
    with pytest.raises(ValueError, match="positive"):
        suggest_excerpts(_doc([_step()]), units=0)


def test_deep_link_span_with_units_gets_a_window():
    # end=None ("starts here, extent not recorded") + units: the grid knows
    step = _step(spans=[SourceSpan(source="perf", start="10")])
    result = suggest_excerpts(_doc([step]), units=2)
    assert result.document.steps[0].spans[0].excerpt == ("10", "18")


def test_deep_link_span_without_units_is_flagged_not_invented():
    step = _step(spans=[SourceSpan(source="perf", start="10")])
    result = suggest_excerpts(_doc([step]))
    assert result.document.steps[0].spans[0].excerpt is None
    assert "no-extent:b1" in result.flags


def test_existing_excerpt_is_never_eaten_by_default():
    step = _step(
        spans=[SourceSpan(source="perf", start="10", end="18", excerpt=("11", "13"))]
    )
    result = suggest_excerpts(_doc([step]))
    assert result.document.steps[0].spans[0].excerpt == ("11", "13")
    assert result.suggested == []
    overwritten = suggest_excerpts(_doc([step]), overwrite=True)
    assert overwritten.document.steps[0].spans[0].excerpt == ("10", "18")


def test_locked_excerpt_survives_even_overwrite():
    step = _step(
        spans=[SourceSpan(source="perf", start="10", end="18", excerpt=("11", "13"))],
        locks=[
            Lock(path="/spans/0/excerpt", by="user:thor", at="2026-08-31T00:00:00Z")
        ],
    )
    result = suggest_excerpts(_doc([step]), overwrite=True)
    assert result.document.steps[0].spans[0].excerpt == ("11", "13")
    assert "locked-excerpt-kept:b1" in result.flags


def test_missing_role_is_flagged_and_role_is_selectable():
    step = _step(
        spans=[SourceSpan(source="perf", role="instruction", start="10", end="18")]
    )
    result = suggest_excerpts(_doc([step]))
    assert "no-performance-span:b1" in result.flags
    by_role = suggest_excerpts(_doc([step]), role="instruction")
    assert by_role.document.steps[0].spans[0].excerpt == ("10", "18")


def test_child_steps_are_walked_and_the_original_is_untouched():
    child = _step("b1-1", spans=[SourceSpan(source="perf", start="10", end="14")])
    parent = _step("b1", spans=[])
    parent.steps.append(child)
    doc = _doc([parent])
    result = suggest_excerpts(doc)
    assert result.document.steps[0].steps[0].spans[0].excerpt == ("10", "14")
    assert doc.steps[0].steps[0].spans[0].excerpt is None  # deep copy


def test_wire_stays_float_free():
    def fail(value):
        raise AssertionError(f"float on the wire: {value}")

    grid = MetricGrid(unit="eight", subdivisions=8, tempo_bpm="129.2", origin="51.2")
    step = _step(spans=[SourceSpan(source="perf", start="95.8")])
    result = suggest_excerpts(_doc([step], metric=grid), units=1.4)
    json.loads(dumps_document(result.document), parse_float=fail)
