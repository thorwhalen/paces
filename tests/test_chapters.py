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
