"""Media derivation (issue #1, ADR-0005): real clips/gifs/posters from spans.

These tests exercise the REAL mixing path on synthetic video. They fail —
not skip — when the [media]/dev deps are missing: a silently skipped suite
proves nothing (the same posture as ``test_measure.py``). Only the
pip-bundled imageio-ffmpeg binary is needed; no system ffmpeg (ADR-0005 §2).
"""

from __future__ import annotations

import hashlib
import json
from fractions import Fraction
from pathlib import Path

import mixing  # noqa: F401 — fail loudly, never skip
import moviepy  # noqa: F401
import pytest

from paces import derivation
from paces.derivation import (
    CropRecipe,
    DirStore,
    LocateQuery,
    RecipesFile,
    SubjectObservation,
    check_media_requirements,
    derive_document,
    load_recipes,
    resolve_crop_box,
    save_recipes,
)
from paces.model import (
    ArtifactRef,
    Lock,
    Measure,
    Source,
    SourceSpan,
    Step,
    StepDocument,
    dumps_document,
)
from video_synth import FRAME_SIZE, RECT_XYWH, practice_video


def _fail_on_float(value):  # the no-floats-on-the-wire gate
    raise AssertionError(f"float on the wire: {value}")


def _span(*, start="0.4", excerpt=("0.4", "1.2"), role="performance", source="perf"):
    return SourceSpan(source=source, role=role, start=start, excerpt=excerpt)


def _doc(steps, *, sources=None):
    return StepDocument(
        id="routine",
        title="Routine",
        sources=sources
        or [Source(id="perf", kind="video", uri="https://example.com/v")],
        steps=steps,
    )


def _step(step_id="b4", spans=None, **kwargs):
    return Step(
        id=step_id,
        name="Step",
        duration=Measure(value="4", unit="eight"),
        spans=spans if spans is not None else [_span()],
        **kwargs,
    )


@pytest.fixture(scope="module")
def video(tmp_path_factory):
    return practice_video(tmp_path_factory.mktemp("media") / "src.mp4")


@pytest.fixture
def doc_dir(tmp_path, video):
    """A user project dir holding document.json; media beside the doc."""
    doc = _doc([_step()])
    doc_path = tmp_path / "document.json"
    doc_path.write_text(dumps_document(doc), encoding="utf-8")
    return tmp_path


def _derive(doc, doc_path, video, **kwargs):
    return derive_document(doc, media=str(video), doc_path=doc_path, **kwargs)


# ── the headline path ───────────────────────────────────────────────────────


def test_derive_fills_artifacts_and_writes_media(tmp_path, video):
    doc = _doc([_step()])
    doc_path = tmp_path / "document.json"
    result = _derive(doc, doc_path, video)

    (step,) = result.document.steps
    by_role = {a.role: a for a in step.artifacts}
    assert set(by_role) == {"clip", "gif", "poster"}
    assert by_role["clip"].uri == "media/b4.mp4"
    assert by_role["gif"].uri == "media/b4.gif"
    assert by_role["poster"].uri == "media/b4.jpg"
    for artifact in step.artifacts:
        path = tmp_path / artifact.uri
        assert path.is_file(), artifact.uri
        assert artifact.asset_id == hashlib.sha256(path.read_bytes()).hexdigest()
        assert artifact.derived_from == "performance"
    assert by_role["clip"].mime == "video/mp4"
    assert by_role["clip"].duration_s == "0.8"  # the excerpt window, exact
    assert (by_role["clip"].width, by_role["clip"].height) == FRAME_SIZE  # no crop
    assert by_role["gif"].duration_s == "0.8"
    assert by_role["poster"].duration_s is None

    # the document stays float-free on the wire
    json.loads(dumps_document(result.document), parse_float=_fail_on_float)

    # media identity was recorded onto the (previously hashless) source
    assert result.document.sources[0].asset_id is not None
    assert any(f.startswith("media-identity-recorded:") for f in result.flags)

    # a recipe was written: full-frame is a recorded decision (box null)
    recipes = load_recipes(tmp_path / "document.recipes.json")
    (key,) = recipes.entries
    assert key == "b4/perf/performance/0.4"
    entry = recipes.entries[key]
    assert entry.box is None and entry.locator == "full-frame"
    assert entry.window == ("0.4", "1.2")
    assert (entry.frame_width, entry.frame_height) == FRAME_SIZE
    assert entry.source_asset_id == result.document.sources[0].asset_id
    # the sidecar itself is float-free
    json.loads(
        (tmp_path / "document.recipes.json").read_text(), parse_float=_fail_on_float
    )


def test_rerun_reuses_bytes_and_skips_the_locator(tmp_path, video):
    doc = _doc([_step()])
    doc_path = tmp_path / "document.json"
    first = _derive(doc, doc_path, video)

    calls = []

    def counting_locator(query: LocateQuery):
        calls.append(query)
        return None

    counting_locator.locator_name = "full-frame"  # same identity as run 1

    second = _derive(first.document, doc_path, video, subject_locator=counting_locator)
    assert not calls, "a matching recipe must skip the locator entirely"
    assert any(f == "reused-media:b4" for f in second.flags)
    firsts = {a.role: a.asset_id for a in first.document.steps[0].artifacts}
    seconds = {a.role: a.asset_id for a in second.document.steps[0].artifacts}
    assert firsts == seconds, "re-runs must be byte-stable (no re-encode churn)"
    # dims survive the reuse path too
    clip = next(a for a in second.document.steps[0].artifacts if a.role == "clip")
    assert (clip.width, clip.height) == FRAME_SIZE


def test_two_same_role_spans_in_one_step(tmp_path, video):
    """The design-review blocker: (step, source, role) collides on the POC's
    step b8 — two instruction excerpts on one source. Keys carry start."""
    step = _step(
        "b8",
        spans=[
            _span(start="0.2", excerpt=("0.2", "0.7"), role="instruction"),
            _span(start="0.9", excerpt=("0.9", "1.5"), role="instruction"),
        ],
    )
    doc = _doc([step])
    doc_path = tmp_path / "document.json"
    result = _derive(doc, doc_path, video)

    uris = sorted(a.uri for a in result.document.steps[0].artifacts)
    assert uris == [
        "media/b8.1.gif",
        "media/b8.1.jpg",
        "media/b8.1.mp4",
        "media/b8.2.gif",
        "media/b8.2.jpg",
        "media/b8.2.mp4",
    ]
    recipes = load_recipes(tmp_path / "document.recipes.json")
    assert set(recipes.entries) == {
        "b8/perf/instruction/0.2",
        "b8/perf/instruction/0.9",
    }
    # and a re-run is stable: no refresh ping-pong between the two spans
    second = _derive(result.document, doc_path, video)
    assert not any(f.startswith("recipe-refreshed:") for f in second.flags)


# ── the crop policy (pure — no media involved) ──────────────────────────────


def test_resolve_crop_box_none_means_no_crop():
    assert resolve_crop_box(None, frame_size=(320, 240)) is None
    empty = SubjectObservation(samples=((0.0, ()), (0.5, ())))
    assert resolve_crop_box(empty, frame_size=(320, 240)) is None


def test_resolve_crop_box_identity_when_no_pad_no_aspect_change():
    obs = SubjectObservation(samples=((0.0, ((40, 40, 20, 40),)),))
    assert resolve_crop_box(obs, frame_size=(200, 200), pad=0.0, aspect=0.5) == (
        40,
        40,
        20,
        40,
    )


def test_resolve_crop_box_unions_regions_per_sample():
    # two boxes in one sample (the judo case) union before the envelope
    obs = SubjectObservation(samples=((0.0, ((10, 10, 20, 80), (70, 10, 20, 80))),))
    box = resolve_crop_box(obs, frame_size=(200, 100), pad=0.0, aspect=1.0)
    # union spans (10,10)-(90,90): both judoka in frame, aspect already 1.0
    assert box == (10, 10, 80, 80)


def test_resolve_crop_box_percentile_envelope_rejects_outliers():
    # 25 tight samples + one wild box: the 4/96 envelope shrugs it off
    tight = tuple((float(i), ((100, 100, 50, 50),)) for i in range(25))
    wild = ((99.0, ((0, 0, 300, 200),)),)
    obs = SubjectObservation(samples=tight + wild)
    box = resolve_crop_box(obs, frame_size=(320, 240), pad=0.0, aspect=1.0)
    assert box is not None
    x, y, w, h = box
    assert w < 100 and h < 100, f"outlier dominated the envelope: {box}"


def test_resolve_crop_box_pads_and_forces_aspect():
    obs = SubjectObservation(samples=((0.0, ((100, 100, 100, 50),)),))
    box = resolve_crop_box(obs, frame_size=(1000, 1000), pad=0.1, aspect=0.8)
    assert box is not None
    x, y, w, h = box
    assert w == 120  # 100 padded by 10% each side
    assert h == 150  # forced to w/h = 0.8
    assert x == 90 and y == 50  # centered on the padded box


def test_resolve_crop_box_clamps_into_frame():
    obs = SubjectObservation(samples=((0.0, ((0, 0, 300, 100),)),))
    box = resolve_crop_box(obs, frame_size=(320, 240), pad=0.0, aspect=2.0)
    assert box is not None
    x, y, w, h = box
    assert 0 <= x and 0 <= y and x + w <= 320 and y + h <= 240
    assert abs(w / h - 2.0) < 0.05  # clamped aspect-true


# ── the locator seam, end to end ────────────────────────────────────────────


def test_locator_observation_drives_the_cut(tmp_path, video):
    x, y, w, h = RECT_XYWH

    def rect_locator(query: LocateQuery):
        assert query.frame_width, "the query carries the probed frame size"
        return SubjectObservation(samples=((query.start_s, ((x, y, w, h),)),))

    rect_locator.locator_name = "test-rect"

    doc = _doc([_step()])
    doc_path = tmp_path / "document.json"
    result = _derive(doc, doc_path, video, subject_locator=rect_locator, pad=0.0)

    expected = resolve_crop_box(
        SubjectObservation(samples=((0.0, ((x, y, w, h),)),)),
        frame_size=FRAME_SIZE,
        pad=0.0,
    )
    clip = next(a for a in result.document.steps[0].artifacts if a.role == "clip")
    # mixing even-floors the box; width/height come from the encoded file
    assert (clip.width, clip.height) == (
        expected[2] - expected[2] % 2,
        expected[3] - expected[3] % 2,
    )
    entry = load_recipes(tmp_path / "document.recipes.json").entries[
        "b4/perf/performance/0.4"
    ]
    assert entry.box == expected and entry.locator == "test-rect"


def test_locked_recipe_box_is_used_verbatim(tmp_path, video):
    doc = _doc([_step()])
    doc_path = tmp_path / "document.json"
    recipes = RecipesFile(
        entries={
            "b4/perf/performance/0.4": CropRecipe(
                box=(60, 40, 100, 80),
                window=("0.4", "1.2"),
                frame_width=FRAME_SIZE[0],
                frame_height=FRAME_SIZE[1],
                locator="user:thor",
                locked=True,
            )
        }
    )
    save_recipes(recipes, tmp_path / "document.recipes.json")

    def exploding_locator(query):  # locked must never re-locate
        raise AssertionError("locator ran despite a locked recipe")

    result = _derive(doc, doc_path, video, subject_locator=exploding_locator)
    clip = next(a for a in result.document.steps[0].artifacts if a.role == "clip")
    assert (clip.width, clip.height) == (100, 80)
    # identity was unverified (hand-written entry has no asset id) — said so
    assert any(f.startswith("recipe-identity-unverified:") for f in result.flags)


def test_locked_recipe_survives_drift_with_a_loud_flag(tmp_path, video):
    doc = _doc([_step()])
    doc_path = tmp_path / "document.json"
    recipes = RecipesFile(
        entries={
            "b4/perf/performance/0.4": CropRecipe(
                box=(60, 40, 100, 80),
                window=("9.0", "9.5"),  # drifted: doc says (0.4, 1.2)
                frame_width=64,  # and the frame changed
                frame_height=48,
                source_asset_id="0" * 64,
                locator="user:thor",
                locked=True,
            )
        }
    )
    save_recipes(recipes, tmp_path / "document.recipes.json")
    result = _derive(doc, doc_path, video)
    assert any(f == "recipe-drift-locked:b4/perf/performance/0.4" for f in result.flags)
    clip = next(a for a in result.document.steps[0].artifacts if a.role == "clip")
    assert (clip.width, clip.height) == (100, 80)  # the human's box, kept


def test_unlocked_recipe_refreshes_on_drift(tmp_path, video):
    doc = _doc([_step()])
    doc_path = tmp_path / "document.json"
    recipes = RecipesFile(
        entries={
            "b4/perf/performance/0.4": CropRecipe(
                box=(0, 0, 10, 10),
                window=("9.0", "9.5"),
                frame_width=64,
                frame_height=48,
                source_asset_id="0" * 64,
                locator="stale",
            )
        }
    )
    save_recipes(recipes, tmp_path / "document.recipes.json")
    result = _derive(doc, doc_path, video)
    assert any(f == "recipe-refreshed:b4/perf/performance/0.4" for f in result.flags)
    entry = load_recipes(tmp_path / "document.recipes.json").entries[
        "b4/perf/performance/0.4"
    ]
    assert entry.box is None and entry.locator == "full-frame"  # re-located


def test_orphaned_recipe_is_flagged_and_kept(tmp_path, video):
    doc = _doc([_step()])
    doc_path = tmp_path / "document.json"
    recipes = RecipesFile(
        entries={
            "gone/perf/performance/3.0": CropRecipe(
                box=(0, 0, 50, 50),
                window=("3.0", "4.0"),
                frame_width=FRAME_SIZE[0],
                frame_height=FRAME_SIZE[1],
                locator="user:thor",
                locked=True,
            )
        }
    )
    save_recipes(recipes, tmp_path / "document.recipes.json")
    result = _derive(doc, doc_path, video)
    assert any(f == "recipe-orphaned:gone/perf/performance/3.0" for f in result.flags)
    assert (
        "gone/perf/performance/3.0"
        in load_recipes(tmp_path / "document.recipes.json").entries
    ), "an orphaned (possibly hand-locked) recipe must never be dropped"


# ── honesty: identity, locks, staleness, refusals ───────────────────────────


def test_media_hash_mismatch_refuses(tmp_path, video):
    doc = _doc(
        [_step()],
        sources=[Source(id="perf", kind="video", uri="https://x", asset_id="0" * 64)],
    )
    doc_path = tmp_path / "document.json"
    with pytest.raises(ValueError, match="different bytes"):
        _derive(doc, doc_path, video)


def test_derive_requires_an_anchor(video):
    with pytest.raises(ValueError, match="anchor"):
        derive_document(_doc([_step()]), media=str(video))


def test_single_path_with_two_sources_errors(tmp_path, video):
    doc = _doc(
        [
            _step("b1", spans=[_span()]),
            _step("b2", spans=[_span(source="other")]),
        ],
        sources=[
            Source(id="perf", kind="video", uri="https://x"),
            Source(id="other", kind="video", uri="https://y"),
        ],
    )
    with pytest.raises(ValueError, match="several sources"):
        _derive(doc, tmp_path / "document.json", video)


def test_partial_media_mapping_flags_the_uncovered_source(tmp_path, video):
    doc = _doc(
        [
            _step("b1", spans=[_span()]),
            _step("b2", spans=[_span(source="other")]),
        ],
        sources=[
            Source(id="perf", kind="video", uri="https://x"),
            Source(id="other", kind="video", uri="https://y"),
        ],
    )
    result = derive_document(
        doc, media={"perf": str(video)}, doc_path=tmp_path / "document.json"
    )
    assert any(f == "no-media:b2/other" for f in result.flags)
    assert result.document.steps[1].artifacts == []  # nothing invented
    # ...and the uncovered span's (absent) recipe is NOT reported orphaned
    assert not any(f.startswith("recipe-orphaned:") for f in result.flags)


def test_locked_artifact_entry_is_kept(tmp_path, video):
    step = _step()
    step.artifacts.append(
        ArtifactRef(role="clip", uri="media/b4.mp4", attrs={"note": "hand-swapped"})
    )
    step.locks.append(
        Lock(path="/artifacts/0/uri", by="user:thor", at="2026-08-30T00:00:00Z")
    )
    doc = _doc([step])
    result = _derive(doc, tmp_path / "document.json", video)
    assert any(f == "locked-artifact-kept:b4:media/b4.mp4" for f in result.flags)
    kept = result.document.steps[0].artifacts[0]
    assert kept.asset_id is None and kept.attrs == {"note": "hand-swapped"}


def test_stale_derived_artifact_is_flagged_never_removed(tmp_path, video):
    step = _step()
    step.artifacts.append(
        ArtifactRef(role="clip", uri="media/b4.9.mp4", derived_from="performance")
    )
    step.artifacts.append(  # different name family: not derive's to flag
        ArtifactRef(role="clip", uri="media/b4x.mp4", derived_from="performance")
    )
    doc = _doc([step])
    result = _derive(doc, tmp_path / "document.json", video)
    assert any(f == "stale-artifact:b4:media/b4.9.mp4" for f in result.flags)
    assert not any("b4x" in f for f in result.flags)
    uris = [a.uri for a in result.document.steps[0].artifacts]
    assert "media/b4.9.mp4" in uris and "media/b4x.mp4" in uris


def test_invalid_excerpt_is_flagged(tmp_path, video):
    doc = _doc([_step(spans=[_span(excerpt=("1.2", "0.4"))])])
    result = _derive(doc, tmp_path / "document.json", video)
    assert any(f.startswith("invalid-excerpt:") for f in result.flags)
    assert result.document.steps[0].artifacts == []


def test_roles_filter(tmp_path, video):
    doc = _doc([_step()])
    result = _derive(doc, tmp_path / "document.json", video, roles=("clip",))
    assert [a.role for a in result.document.steps[0].artifacts] == ["clip"]
    assert not (tmp_path / "media" / "b4.gif").exists()
    with pytest.raises(ValueError, match="unknown roles"):
        _derive(doc, tmp_path / "document.json", video, roles=("clip", "webm"))


def test_child_step_spans_are_derived(tmp_path, video):
    child = _step("b4-1")
    parent = _step("b4", spans=[])
    parent.steps.append(child)
    doc = _doc([parent])
    result = _derive(doc, tmp_path / "document.json", video)
    (got_parent,) = result.document.steps
    assert got_parent.artifacts == []
    assert {a.uri for a in got_parent.steps[0].artifacts} == {
        "media/b4-1.mp4",
        "media/b4-1.gif",
        "media/b4-1.jpg",
    }


# ── the store seam ──────────────────────────────────────────────────────────


def test_dirstore_rejects_traversal(tmp_path):
    store = DirStore(tmp_path)
    with pytest.raises(ValueError, match="relative POSIX"):
        store["../escape.bin"] = b"x"
    with pytest.raises(ValueError, match="relative POSIX"):
        store["/absolute.bin"] = b"x"
    store["media/x.bin"] = b"data"
    assert store["media/x.bin"] == b"data"
    assert "media/x.bin" in store and list(store) == ["media/x.bin"]


def test_injected_store_receives_the_bytes(tmp_path, video):
    doc = _doc([_step()])
    store: dict[str, bytes] = {}
    result = derive_document(
        doc,
        media=str(video),
        media_store=store,
        recipes_path=tmp_path / "r.json",
    )
    assert set(store) == {"media/b4.mp4", "media/b4.gif", "media/b4.jpg"}
    clip = next(a for a in result.document.steps[0].artifacts if a.role == "clip")
    assert clip.asset_id == hashlib.sha256(store["media/b4.mp4"]).hexdigest()


# ── preflight & tools surface ───────────────────────────────────────────────


def test_check_media_requirements_reports_two_channels():
    report = check_media_requirements()
    assert report["ok"] is True
    assert report["bundled_ffmpeg"]
    assert "system_ffmpeg" in report  # present either way — reported distinctly


def test_tools_derive_writes_back_and_reports(tmp_path, video):
    from paces import tools

    doc_path = tmp_path / "document.json"
    doc_path.write_text(dumps_document(_doc([_step()])), encoding="utf-8")
    payload = tools.derive(str(doc_path), media=str(video))
    assert "flags" in payload and "derived" in payload
    on_disk = json.loads(doc_path.read_text(), parse_float=_fail_on_float)
    uris = {a["uri"] for a in on_disk["steps"][0]["artifacts"]}
    assert uris == {"media/b4.mp4", "media/b4.gif", "media/b4.jpg"}


def test_tools_derive_refuses_a_non_path_document(video):
    from paces import tools

    with pytest.raises(ValueError, match="file path"):
        tools.derive({"id": "x"}, media=str(video))


def test_duration_decimal_is_exact(tmp_path, video):
    # 1.2 - 0.4 in floats is 0.7999...; the wire value must be the exact "0.8"
    assert Fraction("1.2") - Fraction("0.4") == Fraction("0.8")
    doc = _doc([_step()])
    result = _derive(doc, tmp_path / "document.json", video, roles=("clip",))
    clip = result.document.steps[0].artifacts[0]
    assert clip.duration_s == "0.8"
