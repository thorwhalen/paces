"""The rtmlib pose subject_locator (issue #15), and the licence perimeter it sits in.

Offline by construction. Nothing here installs rtmlib, downloads a weight, or
reaches the network: the locator's contract is exercised with a fake pose
estimator injected through ``pose_estimator=``, reading real frames out of the
same synthetic video the derivation tests use. The one test that would run a
real model is opt-in behind ``PACES_TEST_MODELS`` and skipped everywhere else,
CI included — which is why ``[pose]`` is deliberately NOT mirrored into ``[dev]``.

The rest is packaging. ``[pose]`` is the only extra that reaches a model
runtime, and no behaviour in this suite would notice AGPL being slipped into it
— these tests are what notice.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import mixing  # noqa: F401 — the frame reader is real; fail loudly, never skip
import pytest

from paces import pose
from paces.derivation import (
    LocateQuery,
    SubjectObservation,
    derive_document,
    load_recipes,
    resolve_crop_box,
)
from paces.model import Measure, Source, SourceSpan, Step, StepDocument
from paces.pose import (
    DFLT_MIN_KEYPOINTS,
    POSE_EXTRA_MISSING,
    TEST_MODELS_ENVVAR,
    RtmlibPoseLocator,
    check_pose_requirements,
    person_boxes,
    probe_times,
    rtmlib_pose,
)
from video_synth import FRAME_SIZE, practice_video

#: A version to stand in for an installed rtmlib, so the naming contract can be
#: asserted on a machine that has no rtmlib at all (every CI machine).
FAKE_RTMLIB_VERSION = "0.0.16"

#: Distributions carrying AGPL terms that must never reach ANY paces extra.
#: ultralytics pulls the other two itself, and a licence check matches per
#: distribution name — so all three are named (ADR-0005 §3).
FORBIDDEN_DISTRIBUTIONS = frozenset(
    {"ultralytics", "ultralytics-thop", "ultralytics-platform"}
)

_PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


@pytest.fixture(scope="module")
def pyproject():
    return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def video(tmp_path_factory):
    """The derivation suite's fixture clip: a green rect on blue, 2 s at 24 fps."""
    return practice_video(tmp_path_factory.mktemp("pose") / "practice.mp4")


def _people(*boxes, score=0.9):
    """rtmlib-shaped ``(keypoints, scores)`` for people occupying ``boxes``.

    Four corner keypoints each, which is exactly ``DFLT_MIN_KEYPOINTS``.
    """
    keypoints = [
        [(x, y), (x + w, y), (x, y + h), (x + w, y + h)] for x, y, w, h in boxes
    ]
    return keypoints, [(score,) * 4 for _ in boxes]


def _query(video, *, start_s=0.0, end_s=2.0):
    return LocateQuery(
        media_path=str(video),
        start_s=start_s,
        end_s=end_s,
        frame_width=FRAME_SIZE[0],
        frame_height=FRAME_SIZE[1],
        step_id="b4",
        tags=("performance",),
    )


# ── probe_times (pure) ──────────────────────────────────────────────────────


def test_probe_times_spreads_the_asked_rate_inside_the_window():
    times = probe_times(10.0, 13.0, probe_fps=5.0)
    assert len(times) == 15  # 3 s at 5 fps
    assert all(10.0 < t < 13.0 for t in times)
    assert times == tuple(sorted(times))


def test_probe_times_gives_a_short_window_its_middle():
    # shorter than one probe interval: one look, and not on either edge (a probe
    # on the closing edge reads the next shot)
    assert probe_times(4.0, 4.1, probe_fps=5.0) == (4.05,)


def test_probe_times_refuses_an_empty_window_and_a_dead_rate():
    with pytest.raises(ValueError, match="non-empty"):
        probe_times(2.0, 2.0)
    with pytest.raises(ValueError, match="probe_fps"):
        probe_times(0.0, 1.0, probe_fps=0.0)


# ── person_boxes (pure) ─────────────────────────────────────────────────────


def test_person_boxes_spans_the_confident_keypoints():
    keypoints, scores = _people((60, 40, 100, 80))
    assert person_boxes(keypoints, scores, frame_size=FRAME_SIZE) == (
        (60, 40, 100, 80),
    )


def test_person_boxes_keeps_every_person():
    # the judo case: two people, two regions, no identity claim and no choosing
    keypoints, scores = _people((10, 10, 40, 90), (200, 20, 50, 80))
    assert person_boxes(keypoints, scores, frame_size=FRAME_SIZE) == (
        (10, 10, 40, 90),
        (200, 20, 50, 80),
    )


def test_person_boxes_ignores_keypoints_below_the_confidence():
    keypoints = [[(60, 40), (160, 40), (60, 120), (160, 120), (5, 5)]]
    scores = [(0.9, 0.9, 0.9, 0.9, 0.05)]  # the stray point is noise
    assert person_boxes(keypoints, scores, frame_size=FRAME_SIZE) == (
        (60, 40, 100, 80),
    )


def test_person_boxes_drops_a_person_with_too_little_evidence():
    keypoints, scores = _people((60, 40, 100, 80))
    assert (
        person_boxes(
            keypoints,
            scores,
            frame_size=FRAME_SIZE,
            min_keypoints=DFLT_MIN_KEYPOINTS + 1,
        )
        == ()
    )


def test_person_boxes_clamps_into_the_frame():
    keypoints, scores = _people((-20, -30, 400, 400))
    assert person_boxes(keypoints, scores, frame_size=FRAME_SIZE) == (
        (0, 0, FRAME_SIZE[0], FRAME_SIZE[1]),
    )


def test_person_boxes_reports_zero_detections_as_evidence_not_error():
    assert person_boxes([], [], frame_size=FRAME_SIZE) == ()
    assert person_boxes(None, None, frame_size=FRAME_SIZE) == ()


# ── the locator, against real frames and a fake model ───────────────────────


def test_locator_observes_every_probe_and_every_person(video):
    seen_shapes = []

    def estimator(frame):
        seen_shapes.append(frame.shape)
        return _people((60, 40, 100, 80), (200, 40, 60, 120))

    locator = RtmlibPoseLocator(probe_fps=5.0, pose_estimator=estimator)
    query = _query(video)
    observation = locator(query)

    assert isinstance(observation, SubjectObservation)
    assert len(observation.samples) == 10  # 2 s at 5 fps
    assert len(seen_shapes) == 10, "every probe must reach the estimator"
    # real frames, read through mixing: cv2's (height, width, BGR) layout
    assert set(seen_shapes) == {(FRAME_SIZE[1], FRAME_SIZE[0], 3)}
    assert all(query.start_s < t < query.end_s for t, _boxes in observation.samples)
    assert all(
        boxes == ((60, 40, 100, 80), (200, 40, 60, 120))
        for _t, boxes in observation.samples
    )


def test_locator_hands_the_core_something_the_policy_can_resolve(video):
    locator = RtmlibPoseLocator(
        probe_fps=5.0,
        pose_estimator=lambda frame: _people((10, 10, 40, 90), (200, 20, 50, 80)),
    )
    observation = locator(_query(video))
    box = resolve_crop_box(observation, frame_size=FRAME_SIZE, pad=0.0, aspect=1.0)
    assert box is not None
    x, y, w, h = box
    # the core unioned both people and kept them inside the frame
    assert x <= 10 and y <= 10 and x + w >= 250 and x + w <= FRAME_SIZE[0]
    assert y + h <= FRAME_SIZE[1]


def test_locator_answers_none_when_it_sees_nobody(video):
    locator = RtmlibPoseLocator(probe_fps=5.0, pose_estimator=lambda frame: _people())
    # ADR-0005 §3: None is the zero-detections fallback, and no crop means
    # genuinely uncropped rather than letterboxed
    assert locator(_query(video)) is None


def test_locator_raises_rather_than_calling_unreadable_media_uncropped():
    locator = RtmlibPoseLocator(pose_estimator=lambda frame: _people())
    query = _query("no-such-file.mp4")
    with pytest.raises((RuntimeError, ValueError)):
        locator(query)


# ── the recorded identity ───────────────────────────────────────────────────


def test_locator_name_carries_the_rtmlib_version(monkeypatch):
    # the recipe fingerprint reads this: an rtmlib upgrade must re-locate rather
    # than reuse a box a different model measured (ADR-0005 §3)
    monkeypatch.setattr(pose, "_rtmlib_version", lambda: FAKE_RTMLIB_VERSION)
    assert rtmlib_pose.locator_name == (
        f"rtmlib-pose@{FAKE_RTMLIB_VERSION};mode=balanced;fps=5;conf=0.3;minkp=4"
    )


@pytest.mark.parametrize(
    "changed",
    [
        {"mode": "performance"},
        {"probe_fps": 10.0},
        {"keypoint_confidence": 0.5},
        {"min_keypoints": 6},
    ],
)
def test_every_input_that_moves_a_box_moves_the_locator_name(monkeypatch, changed):
    # derive gates recipe reuse on this name (derivation.py's _reconcile_recipe),
    # so anything left out of it silently reuses a box measured under different
    # settings — precisely what ADR-0005 §3's fingerprint exists to prevent
    monkeypatch.setattr(pose, "_rtmlib_version", lambda: FAKE_RTMLIB_VERSION)
    assert RtmlibPoseLocator(**changed).locator_name != rtmlib_pose.locator_name


def test_an_injected_estimator_names_itself_instead_of_claiming_rtmlib(monkeypatch):
    # claiming rtmlib's version for a box rtmlib did not measure would be the
    # same false identity in the other direction
    def boom():
        raise AssertionError("an injected estimator must not read rtmlib's version")

    monkeypatch.setattr(pose, "_rtmlib_version", boom)

    def my_estimator(frame):
        return _people()

    name = RtmlibPoseLocator(pose_estimator=my_estimator).locator_name
    assert name.startswith("rtmlib-pose@custom:")
    assert "my_estimator" in name
    assert "mode=" not in name  # a Body argument; meaningless to another estimator
    assert ";fps=5;conf=0.3;minkp=4" in name


def test_an_estimator_may_version_itself(monkeypatch):
    monkeypatch.setattr(pose, "_rtmlib_version", lambda: FAKE_RTMLIB_VERSION)

    def versioned(frame):
        return _people()

    versioned.locator_name = "my-model@2.1"
    name = RtmlibPoseLocator(pose_estimator=versioned).locator_name
    assert name.startswith("rtmlib-pose@custom:my-model@2.1;")


def test_naming_the_locator_without_the_extra_names_the_extra(monkeypatch):
    import importlib.metadata
    import importlib.util

    def not_installed(distribution, *args, **kwargs):
        if distribution == "rtmlib":
            raise importlib.metadata.PackageNotFoundError(distribution)
        return FAKE_RTMLIB_VERSION

    monkeypatch.setattr(importlib.metadata, "version", not_installed)
    # patched too, so this describes an absent rtmlib rather than whatever the
    # developer's machine happens to have installed
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    with pytest.raises(ImportError) as excinfo:
        rtmlib_pose.locator_name
    message = str(excinfo.value)
    assert "paces[pose]" in message
    assert "rtmlib" in message
    assert "full_frame" in message, (
        "the message must name the answer that needs nothing"
    )


def test_running_the_locator_without_the_extra_names_the_extra(monkeypatch):
    # the calling path, not just the naming one: every rtmlib import goes
    # through _import_body precisely so this message is written once
    import builtins

    real_import = builtins.__import__

    def no_rtmlib(name, *args, **kwargs):
        if name == "rtmlib" or name.startswith("rtmlib."):
            raise ImportError("No module named 'rtmlib'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_rtmlib)
    pose._body_estimator.cache_clear()
    with pytest.raises(ImportError) as excinfo:
        pose._import_body()
    assert "paces[pose]" in str(excinfo.value)


def test_a_vendored_rtmlib_is_told_apart_from_a_missing_one(monkeypatch):
    # importable but no dist-info (a vendored copy, or a source tree on
    # PYTHONPATH): "pip install paces[pose]" is the wrong advice there
    import importlib.metadata
    import importlib.util

    def no_metadata(distribution, *args, **kwargs):
        raise importlib.metadata.PackageNotFoundError(distribution)

    monkeypatch.setattr(importlib.metadata, "version", no_metadata)
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    with pytest.raises(ImportError) as excinfo:
        rtmlib_pose.locator_name
    message = str(excinfo.value)
    assert "no distribution metadata" in message
    assert "pose_estimator" in message, "the message must name the way out"


def test_the_missing_extra_message_states_the_licence_boundary():
    assert "Apache-2.0" in POSE_EXTRA_MISSING
    assert "AGPL" in POSE_EXTRA_MISSING


# ── the seam, end to end through derive ─────────────────────────────────────


def test_derive_records_the_pose_locator_in_the_recipe(tmp_path, video, monkeypatch):
    monkeypatch.setattr(pose, "_rtmlib_version", lambda: FAKE_RTMLIB_VERSION)
    document = StepDocument(
        id="routine",
        title="Routine",
        sources=[Source(id="perf", kind="video", uri="https://example.com/v")],
        steps=[
            Step(
                id="b4",
                name="Step",
                duration=Measure(value="4", unit="eight"),
                spans=[
                    SourceSpan(
                        source="perf",
                        role="performance",
                        start="0.4",
                        excerpt=("0.4", "1.2"),
                    )
                ],
            )
        ],
    )
    doc_path = tmp_path / "routine.json"
    doc_path.write_text("{}", encoding="utf-8")

    def one_dancer(frame):
        return _people((60, 40, 100, 80))

    locator = RtmlibPoseLocator(probe_fps=5.0, pose_estimator=one_dancer)
    result = derive_document(
        document,
        media={"perf": str(video)},
        doc_path=doc_path,
        subject_locator=locator,
        pad=0.0,
        aspect=1.0,
        roles=("poster",),
    )
    recipes = load_recipes(tmp_path / "routine.recipes.json")
    entry = recipes.entries["b4/perf/performance/0.4"]
    # the whole policy identity lands in the sidecar, not just a model version
    assert entry.locator.startswith("rtmlib-pose@custom:")
    assert "one_dancer" in entry.locator
    assert entry.locator.endswith(";fps=5;conf=0.3;minkp=4")
    assert entry.box is not None
    x, y, w, h = entry.box
    # the rect (60, 40, 100, 80) squared to aspect 1.0 about its own centre
    assert (x, y, w, h) == (60, 30, 100, 100)
    assert result.document.steps[0].artifacts


# ── the extra is genuinely lazy ─────────────────────────────────────────────


def test_importing_paces_never_pulls_the_pose_stack():
    # the guarantee is structural, so assert it structurally: rtmlib and
    # onnxruntime are heavy, and `import paces` is not where anyone opted in
    repo_root = Path(pose.__file__).resolve().parents[1]  # holds the `paces` package
    env = dict(os.environ, PYTHONPATH=str(repo_root))
    script = (
        "import sys\n"
        "import paces\n"
        "import paces.pose\n"
        "leaked = {'rtmlib', 'onnxruntime'} & set(sys.modules)\n"
        "assert not leaked, leaked\n"
        "print('clean')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo_root),
    )
    assert completed.returncode == 0, completed.stderr
    assert "clean" in completed.stdout


def test_check_pose_requirements_reports_channels_without_downloading():
    report = check_pose_requirements()
    assert set(report) == {"ok", "rtmlib", "onnxruntime", "cv2_providers", "notes"}
    assert report["ok"] is (
        report["rtmlib"] is not None and report["onnxruntime"] is not None
    )
    if not report["ok"]:
        assert any("paces[pose]" in note for note in report["notes"])


def test_check_pose_requirements_names_the_repair_when_both_cv2_providers_present(
    monkeypatch,
):
    # issue #20: rtmlib declares both opencv-python and opencv-contrib-python.
    # Naming the collision isn't enough — a reader who hits it needs the
    # repair command, not just the two package names, since neither package's
    # uninstall is safe once both are present (each claims the other's files).
    import importlib.metadata

    installed = {
        "rtmlib": "0.0.16",
        "onnxruntime": "1.2.3",
        "opencv-python": "4.12.0.88",
        "opencv-contrib-python": "4.13.0.92",
    }

    def fake_version(distribution, *args, **kwargs):
        try:
            return installed[distribution]
        except KeyError:
            raise importlib.metadata.PackageNotFoundError(distribution)

    monkeypatch.setattr(importlib.metadata, "version", fake_version)
    report = check_pose_requirements()
    assert report["cv2_providers"] == ["opencv-python", "opencv-contrib-python"]
    assert any(
        "pip install --force-reinstall" in note for note in report["notes"]
    )


# ── the licence perimeter (packaging facts, guarded because nothing else is) ─


def _distribution_names(requirements):
    """Bare distribution names out of PEP 508 requirement strings."""
    for requirement in requirements:
        head = requirement.split(";")[0].split("[")[0]
        for separator in ("==", ">=", "<=", "~=", "!=", ">", "<", " ", "@"):
            head = head.split(separator)[0]
        yield head.strip().lower().replace("_", "-")


def test_core_dependencies_stay_copyleft_free(pyproject):
    core = set(_distribution_names(pyproject["project"]["dependencies"]))
    assert core == {"pydantic"}


def test_no_extra_reaches_agpl(pyproject):
    # putting ultralytics into `pose` is the regression this exists to catch:
    # it is how a user who asked for pose boxes would silently inherit the AGPL.
    # Scope, stated so nobody reads more into a green run than is there: this
    # reads paces' OWN pyproject, i.e. what paces declares. It says nothing
    # about transitive closures, and nothing about what a dependency's wheels
    # actually ship — opencv's GPL-on-macOS FFmpeg is exactly that gap, which
    # is why it was measured off the binaries and written down instead.
    for extra, requirements in pyproject["project"]["optional-dependencies"].items():
        found = set(_distribution_names(requirements)) & FORBIDDEN_DISTRIBUTIONS
        assert not found, f"AGPL {sorted(found)} reached the `{extra}` extra"


def test_pose_is_the_extra_that_declares_rtmlib(pyproject):
    requirements = pyproject["project"]["optional-dependencies"]["pose"]
    assert set(_distribution_names(requirements)) == {"rtmlib", "onnxruntime"}
    # the licence audit was done against one rtmlib version, and 0.0.x promises
    # no stability: a floor with no ceiling would let an unaudited wheel in
    (rtmlib_requirement,) = [r for r in requirements if r.startswith("rtmlib")]
    assert "<" in rtmlib_requirement, (
        f"rtmlib must carry an upper bound, got {rtmlib_requirement!r}"
    )


def test_the_licence_table_looks_where_the_exposure_is(pyproject):
    # wads' LicencePolicy rejects unknown keys deliberately, so a typo here is a
    # hard error rather than a silent fallback to defaults — keep it parseable.
    known = {
        "enabled",
        "allowed",
        "forbidden",
        "exceptions",
        "include-extras",
        "unknown-is-failure",
        "unclassified-is-failure",
    }
    table = pyproject["tool"]["wads"]["licence"]
    assert set(table) <= known, f"unknown keys: {sorted(set(table) - known)}"
    # every extra is inside the perimeter — a new one must be adjudicated, not
    # quietly excluded from the check
    declared = set(pyproject["project"]["optional-dependencies"]) - {"dev", "docs"}
    assert declared <= set(table["include-extras"])
    # paces adjudicates nothing: an exceptions table appearing here would mean
    # the perimeter moved, and that is a decision, not a diff
    assert "exceptions" not in table


# ── the real model: opt-in, never CI ────────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get(TEST_MODELS_ENVVAR) is None,
    reason=f"set {TEST_MODELS_ENVVAR}=1 to download rtmlib weights and run a real pass",
)
def test_real_rtmlib_pass_smoke(video):
    # not an accuracy claim: the fixture is a green rectangle and RTMPose is
    # entitled to see nobody in it. What this proves is the wiring — Body
    # constructs, weights resolve, inference runs, and its output is the shape
    # person_boxes reads.
    observation = rtmlib_pose(_query(video))
    assert observation is None or isinstance(observation, SubjectObservation)
    assert rtmlib_pose.locator_name.startswith("rtmlib-pose@")
