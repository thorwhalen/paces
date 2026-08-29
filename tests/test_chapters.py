"""The chapters segmenter: author-supplied names and times for ~0 cost."""

from __future__ import annotations

import pytest

from paces.segmenters import segment

YTDLP_METADATA = {
    "id": "abc123",
    "duration": 300,
    "chapters": [
        {"start_time": 0.0, "end_time": 45.0, "title": "Intro"},
        {"start_time": 45.0, "end_time": 180.0, "title": "The basic step"},
        {"start_time": 180.0, "end_time": 300.0, "title": "Putting it together"},
    ],
}

FFPROBE_METADATA = {
    "chapters": [
        {
            "id": 0,
            "time_base": "1/1000",
            "start": 0,
            "start_time": "0.000000",
            "end": 45000,
            "end_time": "45.000000",
            "tags": {"title": "Intro"},
        },
        {
            "id": 1,
            "time_base": "1/1000",
            "start": 45000,
            "start_time": "45.000000",
            "end": 300000,
            "end_time": "300.000000",
            "tags": {"title": "The rest"},
        },
    ]
}


def test_ytdlp_chapters_become_a_named_segmentation():
    seg = segment("video.mp4", metadata=YTDLP_METADATA)
    assert seg.method == "chapters"
    assert [step.name for step in seg.steps] == [
        "Intro",
        "The basic step",
        "Putting it together",
    ]
    assert seg.steps[1].spans == ((45.0, 180.0),)
    assert seg.boundaries == (0.0, 45.0, 180.0, 300.0)
    assert seg.flags == ()
    assert seg.steps[0].id == "intro"


def test_ffprobe_chapters_are_understood():
    seg = segment("video.mp4", metadata=FFPROBE_METADATA)
    assert seg.method == "chapters"
    assert [step.name for step in seg.steps] == ["Intro", "The rest"]
    assert seg.steps[0].spans == ((0.0, 45.0),)


def test_bare_chapter_list_works_too():
    seg = segment(metadata=[{"start": 0, "end": 10, "title": "One"}])
    assert seg.method == "chapters"
    assert seg.steps[0].name == "One"


def test_untitled_chapters_abstain_from_naming():
    seg = segment(metadata=[{"start": 0, "end": 10}, {"start": 10, "end": 20}])
    assert all(step.name == "" for step in seg.steps)
    assert "naming-abstained" in seg.flags
    assert seg.steps[0].id == "chapter-1"


def test_duplicate_titles_get_unique_ids():
    seg = segment(
        metadata=[
            {"start": 0, "end": 10, "title": "Chorus"},
            {"start": 10, "end": 20, "title": "Chorus"},
        ]
    )
    assert [step.id for step in seg.steps] == ["chorus", "chorus-2"]


def test_users_steps_and_grid_outrank_chapters():
    """A caller who spelled out steps + grid meant them; chapters are the
    fallback richness, not the override."""
    seg = segment(
        "video.mp4",
        steps=[("a", 2), ("b", 2)],
        grid={"unit": "eight", "subdivisions": 8, "tempoBpm": "120", "origin": "0"},
        metadata=YTDLP_METADATA,
    )
    assert seg.method == "grid-placed"


def test_chapters_outrank_bare_boundaries():
    seg = segment(boundaries=[0, 10, 20], metadata=YTDLP_METADATA)
    assert seg.method == "chapters"


def test_empty_or_null_chapters_are_no_fact():
    seg = segment("video.mp4", metadata={"id": "x", "chapters": None})
    assert "no-signal" in seg.flags
    seg = segment("video.mp4", metadata={"chapters": []})
    assert "no-signal" in seg.flags


def test_malformed_chapter_says_what_is_wrong():
    with pytest.raises(ValueError, match="start_time"):
        segment(metadata=[{"title": "no times"}])


# ── adversarial-review regressions (PR #11) ────────────────────────────────


def test_unsorted_chapters_are_sorted_and_no_boundary_is_lost():
    seg = segment(
        metadata=[
            {"start": 30, "end": 40, "title": "Late"},
            {"start": 0, "end": 10, "title": "Early"},
        ]
    )
    assert [s.name for s in seg.steps] == ["Early", "Late"]
    assert seg.boundaries == (0.0, 10.0, 30.0, 40.0)  # 40 must not vanish


def test_gapped_chapters_keep_the_gap_visible():
    seg = segment(
        metadata=[
            {"start": 0, "end": 10, "title": "A"},
            {"start": 20, "end": 30, "title": "B"},
        ]
    )
    assert seg.boundaries == (0.0, 10.0, 20.0, 30.0)


def test_degenerate_chapters_are_refused_with_the_defect_named():
    with pytest.raises(ValueError, match="must be after start"):
        segment(metadata=[{"start": 10, "end": 5, "title": "backwards"}])
    with pytest.raises(ValueError, match="must be a number"):
        segment(metadata=[{"start": 0, "end": True, "title": "bool"}])
    with pytest.raises(ValueError, match="negative"):
        segment(metadata=[{"start": -5, "end": 10, "title": "neg"}])
    with pytest.raises(ValueError, match="unreadable"):
        segment(metadata=[{"start": "abc", "end": 10, "title": "junk"}])


def test_whitespace_titles_count_as_unnamed():
    seg = segment(metadata=[{"start": 0, "end": 10, "title": "   "}])
    assert seg.steps[0].name == ""
    assert "naming-abstained" in seg.flags


def test_matching_user_step_names_override_chapter_titles():
    """The human's explicit input outranks the author's metadata."""
    seg = segment(steps=["My intro", "My verse", "My outro"], metadata=YTDLP_METADATA)
    assert seg.method == "chapters"
    assert [s.name for s in seg.steps] == ["My intro", "My verse", "My outro"]
    assert seg.steps[0].evidence["chapter_title"] == "Intro"
    assert not any(flag.startswith("ignored") for flag in seg.flags)


def test_mismatched_user_step_count_is_flagged_not_silent():
    seg = segment(steps=["only", "two"], metadata=YTDLP_METADATA)
    assert [s.name for s in seg.steps] == [
        "Intro",
        "The basic step",
        "Putting it together",
    ]
    assert any("step-count-mismatch" in flag for flag in seg.flags)


def test_discarded_explicit_inputs_are_flagged():
    """Finding 6: chapters winning over caller-typed boundaries must say so."""
    seg = segment(boundaries=[0, 10, 20], metadata=YTDLP_METADATA)
    assert seg.method == "chapters"
    assert any(flag == "ignored: boundaries" for flag in seg.flags)


def test_boundaries_plus_steps_outrank_chapters():
    """A human supplying boundaries AND names gave the full explicit picture
    — e.g. to correct bad chapters — and wins."""
    seg = segment(
        boundaries=[0, 10, 20],
        steps=["fixed intro", "fixed verse"],
        metadata=YTDLP_METADATA,
    )
    assert seg.method == "explicit"
    assert [s.name for s in seg.steps] == ["fixed intro", "fixed verse"]


def test_a_grid_rides_along_even_when_placement_did_not_use_it():
    seg = segment(
        metadata=YTDLP_METADATA,
        grid={"unit": "eight", "subdivisions": 8, "tempoBpm": "120", "origin": "0"},
    )
    assert seg.method == "chapters"
    assert seg.grid is not None and seg.unit == "eight"


def test_non_finite_times_are_refused():
    with pytest.raises(ValueError, match="non-finite"):
        segment(metadata=[{"start": "nan", "end": "nan", "title": "x"}])
    with pytest.raises(ValueError, match="non-finite"):
        segment(metadata=[{"start": 0, "end": "inf", "title": "x"}])
