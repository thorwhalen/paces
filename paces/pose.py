"""The pointable ``subject_locator``: person boxes from rtmlib pose keypoints.

ADR-0005 §3 shipped the ``subject_locator=`` seam with :func:`paces.derivation.full_frame`
as its default — a real implementation whose honest answer is "no crop" — and pinned
the contract with fake locators. This module is the pointable replacement: probe the
excerpt window at ~5 fps, run RTMPose over each probed frame, and hand the core one
region list per instant, every person seen. It **observes only**; the core still owns
the one policy pipeline (union → percentile envelope → pad → aspect → clamp → one
static box per window), which is exactly where the POC measured that crops go wrong.

**Licence perimeter.** rtmlib is Apache-2.0 and its runtime closure
(numpy / opencv / onnxruntime / tqdm) is permissive throughout; its bundled RTMDet
detector means person boxes need no YOLO even for detection. A YOLO/ultralytics
dependency is barred here — AGPL-3.0, whose §13 network clause reaches users you
serve rather than only people you hand a copy to (ADR-0005 §3).
``tests/test_pose.py`` guards that perimeter as the packaging fact it is. kodokan's
``pose``/``track`` split is the fleet's worked example of the same quarantine.

**Nothing here is imported until it is used.** ``import paces`` never touches this
module, and importing *this* module never touches rtmlib: every rtmlib access goes
through :func:`_import_body` or :func:`_rtmlib_version`, both of which raise an
``ImportError`` naming the extra. Model weights download on first inference, so CI
covers the seam's contract through fake locators and never runs a model.

Usage — the shell, then the library::

    paces derive doc.json --media routine.mp4 --subject-locator paces.pose:rtmlib_pose

    from paces.derivation import derive_document
    from paces.pose import RtmlibPoseLocator, rtmlib_pose

    derive_document(doc, media=..., doc_path=..., subject_locator=rtmlib_pose)
    derive_document(..., subject_locator=RtmlibPoseLocator(probe_fps=10.0))
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Sequence

from paces.derivation import Box, LocateQuery, SubjectObservation

#: Probe rate across an excerpt window, in samples per second — the POC's rate.
#: Excerpts are 2.5–6 s loops, so ~5 fps is 13–30 looks: enough for the 4/96
#: envelope to shrug off a stray frame, cheap enough to run on CPU.
DFLT_PROBE_FPS = 5.0

#: rtmlib ``Body`` accuracy/latency trade-off: "lightweight" | "balanced" | "performance".
DFLT_MODE = "balanced"

#: onnxruntime execution device. "cpu" is the portable answer and the only one
#: CI would ever have; "cuda"/"mps" are a caller's choice, not a default.
DFLT_DEVICE = "cpu"

#: A keypoint below this score is noise, not evidence, and never widens a box.
DFLT_KEYPOINT_CONFIDENCE = 0.3

#: Fewer confident keypoints than this is not a person — it is a hallucinated
#: limb or two, and boxing it would hand the core a region with no subject in it.
DFLT_MIN_KEYPOINTS = 4

#: The extra that carries this locator, and the stem of its recorded identity.
POSE_EXTRA = "pose"
LOCATOR_STEM = "rtmlib-pose"

#: Opt-in for the real-model smoke test. Unset (CI, always) = no weights, no
#: inference — the contract is covered by fake locators instead.
TEST_MODELS_ENVVAR = "PACES_TEST_MODELS"

POSE_EXTRA_MISSING = (
    "rtmlib is required for the pose subject_locator. Install it with:\n"
    f"    pip install 'paces[{POSE_EXTRA}]'\n"
    "That extra is rtmlib (Apache-2.0) + onnxruntime (MIT); its runtime closure\n"
    "(numpy, opencv, onnxruntime, tqdm) is permissive throughout. rtmlib's\n"
    "bundled RTMDet detector means person boxes need no YOLO, and a\n"
    "YOLO/ultralytics dependency is barred here — AGPL-3.0 (ADR-0005 §3).\n"
    "Model weights download on first inference, not on install.\n"
    "The default locator (paces.derivation.full_frame) needs none of this: it\n"
    "answers 'no crop', which is a real answer rather than a failure."
)

MEDIA_EXTRA_MISSING = (
    "the pose locator reads frames through mixing, the same media path derive\n"
    "itself runs on. Install it with:\n"
    "    pip install 'paces[media]'"
)


# ── rtmlib, reached from exactly two places ─────────────────────────────────


def _import_body():
    """rtmlib's ``Body`` solution (RTMDet detector + RTMPose, COCO-17).

    Every rtmlib *import* goes through here so the missing-extra message is
    written once, the way kodokan routes ultralytics through one importer.
    """
    try:
        from rtmlib import Body
    except ImportError as error:
        raise ImportError(POSE_EXTRA_MISSING) from error
    return Body


def _rtmlib_version() -> str:
    """rtmlib's version, from distribution metadata — no import, no model load.

    ``derive`` reads ``locator_name`` *before* it decides whether a recipe may
    be reused (ADR-0005 §3's re-run semantics), so naming the locator must stay
    this cheap. An absent distribution is the same failure as an absent import,
    reported the same way — and reported before any encode work is spent.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("rtmlib")
    except PackageNotFoundError as error:
        raise ImportError(POSE_EXTRA_MISSING) from error


@lru_cache(maxsize=None)
def _body_estimator(mode: str, device: str):
    """One loaded ``Body`` per (mode, device), for the life of the process.

    The first call downloads the ONNX weights; every excerpt window after it
    reuses the loaded session rather than paying that again.
    """
    Body = _import_body()
    return Body(mode=mode, backend="onnxruntime", device=device)


def _frame_reader(media_path: str) -> Callable[[float], Any]:
    """A ``t_seconds -> frame`` reader over one media file, through ``mixing``.

    All media I/O goes through mixing, never moviepy/cv2 directly (ADR-0005).
    ``mixing.Video`` indexes by time and hands back cv2's native BGR, which is
    the layout rtmlib expects.
    """
    try:
        from mixing import Video
    except ImportError as error:  # pragma: no cover - needs [media] absent
        raise ImportError(MEDIA_EXTRA_MISSING) from error
    video = Video(media_path)
    return lambda t_s: video[t_s]


# ── the two pure pieces (no media, no model, no numpy) ──────────────────────


def probe_times(
    start_s: float, end_s: float, *, probe_fps: float = DFLT_PROBE_FPS
) -> tuple[float, ...]:
    """The instants to look at: ~``probe_fps`` samples spread inside the window.

    Samples sit at the midpoints of ``n`` equal slices, so each one is strictly
    inside ``[start_s, end_s)`` — a probe on the closing edge would read the
    next shot — and a window shorter than one probe interval still gets exactly
    one look, at its middle.

    >>> tuple(round(t, 3) for t in probe_times(0.0, 1.0, probe_fps=5.0))
    (0.1, 0.3, 0.5, 0.7, 0.9)
    >>> tuple(round(t, 3) for t in probe_times(10.0, 10.05))
    (10.025,)
    """
    if not end_s > start_s:
        raise ValueError(
            f"an excerpt window must be non-empty; got [{start_s}, {end_s})"
        )
    if not probe_fps > 0:
        raise ValueError(f"probe_fps must be positive; got {probe_fps}")
    count = max(1, round((end_s - start_s) * probe_fps))
    step = (end_s - start_s) / count
    return tuple(start_s + (index + 0.5) * step for index in range(count))


def person_boxes(
    keypoints: Sequence[Sequence[Sequence[float]]] | None,
    scores: Sequence[Sequence[float]] | None,
    *,
    frame_size: tuple[int, int],
    keypoint_confidence: float = DFLT_KEYPOINT_CONFIDENCE,
    min_keypoints: int = DFLT_MIN_KEYPOINTS,
) -> tuple[Box, ...]:
    """One box per person, spanning that person's *confident* keypoints.

    ``keypoints`` is ``(n_persons, n_keypoints, 2)`` and ``scores`` is
    ``(n_persons, n_keypoints)`` — rtmlib's output shape, read here as plain
    nested sequences, so this stays a pure function and numpy remains the
    extra's business rather than this module's. A person carrying fewer than
    ``min_keypoints`` confident points is dropped rather than boxed from noise;
    boxes are clamped into the frame, and a degenerate one is dropped too.
    Zero detections is ``()`` — evidence that nobody was there, not an error.

    Order is rtmlib's and means nothing: the seam is a *set* of regions per
    instant (the core unions them), so no person-identity claim is made here.

    >>> person_boxes(
    ...     [[(10, 20), (30, 60)]], [(0.9, 0.9)],
    ...     frame_size=(100, 100), min_keypoints=2,
    ... )
    ((10, 20, 20, 40),)
    """
    if keypoints is None or scores is None:
        return ()
    frame_width, frame_height = frame_size
    boxes: list[Box] = []
    for person, person_scores in zip(keypoints, scores):
        confident = [
            (float(point[0]), float(point[1]))
            for point, score in zip(person, person_scores)
            if float(score) >= keypoint_confidence
        ]
        if len(confident) < min_keypoints:
            continue
        xs = [x for x, _y in confident]
        ys = [y for _x, y in confident]
        left = max(0, int(math.floor(min(xs))))
        top = max(0, int(math.floor(min(ys))))
        right = min(frame_width, int(math.ceil(max(xs))))
        bottom = min(frame_height, int(math.ceil(max(ys))))
        if right - left < 1 or bottom - top < 1:
            continue
        boxes.append((left, top, right - left, bottom - top))
    return tuple(boxes)


# ── the locator ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, kw_only=True)
class RtmlibPoseLocator:
    """The pointable ``subject_locator``: rtmlib pose boxes over a probed window.

    Callable per the ADR-0005 §3 contract — a :class:`~paces.derivation.LocateQuery`
    in, a :class:`~paces.derivation.SubjectObservation` out, or ``None``, the
    honest "no crop", when the window showed nobody. It never resolves a box:
    that is the core's :func:`~paces.derivation.resolve_crop_box`.

    ``pose_estimator`` is the seam inside the seam: any
    ``callable(frame) -> (keypoints, scores)``. The default is rtmlib's ``Body``
    (RTMDet + RTMPose, COCO-17); the replacements are already pointable —
    rtmlib's ``Wholebody``, ``Hand`` and ``Animal`` solutions have exactly this
    shape, and the ADR's "hands + workpiece for cooking" case is one of them.
    Tests inject a fake through it, which is how the contract is exercised with
    no weights downloaded and no network reached.

    All fields are keyword-only, and the defaults are the shipped policy.
    """

    probe_fps: float = DFLT_PROBE_FPS
    mode: str = DFLT_MODE
    device: str = DFLT_DEVICE
    keypoint_confidence: float = DFLT_KEYPOINT_CONFIDENCE
    min_keypoints: int = DFLT_MIN_KEYPOINTS
    pose_estimator: Callable[[Any], tuple[Any, Any]] | None = None

    @property
    def locator_name(self) -> str:
        """``rtmlib-pose@<version>`` — the policy identity the crop recipe
        records, so that an rtmlib upgrade re-locates rather than reusing a box
        that a different model measured (ADR-0005 §3)."""
        return f"{LOCATOR_STEM}@{_rtmlib_version()}"

    def __call__(self, query: LocateQuery) -> SubjectObservation | None:
        estimate = self.pose_estimator or _body_estimator(self.mode, self.device)
        read_frame = _frame_reader(query.media_path)
        frame_size = (query.frame_width, query.frame_height)
        samples: list[tuple[float, tuple[Box, ...]]] = []
        unreadable: list[float] = []
        for t_s in probe_times(query.start_s, query.end_s, probe_fps=self.probe_fps):
            try:
                frame = read_frame(t_s)
            except (ValueError, OSError):
                # one unreadable probe is a damaged frame, not a verdict on the
                # window; only losing every probe is a fault worth raising
                unreadable.append(t_s)
                continue
            keypoints, scores = estimate(frame)
            samples.append(
                (
                    t_s,
                    person_boxes(
                        keypoints,
                        scores,
                        frame_size=frame_size,
                        keypoint_confidence=self.keypoint_confidence,
                        min_keypoints=self.min_keypoints,
                    ),
                )
            )
        if not samples:
            raise RuntimeError(
                f"read no frame of {query.media_path} in "
                f"[{query.start_s}, {query.end_s}) — {len(unreadable)} probes "
                "all failed; the media is unreadable there, which is a fault, "
                "not a 'no crop' answer"
            )
        if not any(boxes for _t, boxes in samples):
            # ADR-0005 §3: None is the zero-detections fallback, and no crop
            # means genuinely uncropped — never letterboxed
            return None
        return SubjectObservation(samples=tuple(samples))


#: The ready-made locator: no configuration, and the target a CLI
#: ``--subject-locator paces.pose:rtmlib_pose`` reference resolves to.
rtmlib_pose = RtmlibPoseLocator()


def check_pose_requirements() -> dict:
    """Preflight for the ``[pose]`` extra, per channel and never silently.

    - ``rtmlib`` / ``onnxruntime`` — the locator and its inference backend.
    - ``cv2_providers`` — rtmlib declares BOTH ``opencv-python`` and
      ``opencv-contrib-python``, while the fleet standardises on the contrib
      superset (mixing's single cv2 provider). An install can therefore end up
      with two distributions owning one ``cv2`` package. Reported, not fatal:
      it works until one of them is uninstalled, and a reader deserves to know.

    Downloads nothing: weights arrive on first inference, not on this check.
    """
    from importlib.metadata import PackageNotFoundError, version

    def _version(distribution: str) -> str | None:
        try:
            return version(distribution)
        except PackageNotFoundError:
            return None

    notes: list[str] = []
    rtmlib_version = _version("rtmlib")
    onnxruntime_version = _version("onnxruntime")
    if rtmlib_version is None or onnxruntime_version is None:
        missing = [
            name
            for name, found in (
                ("rtmlib", rtmlib_version),
                ("onnxruntime", onnxruntime_version),
            )
            if found is None
        ]
        notes.append(
            f"{', '.join(missing)} not installed — install the pose extra: "
            f"pip install 'paces[{POSE_EXTRA}]'"
        )
    cv2_providers = [
        name
        for name in ("opencv-python", "opencv-contrib-python")
        if _version(name) is not None
    ]
    if len(cv2_providers) > 1:
        notes.append(
            "two distributions provide cv2 "
            f"({', '.join(cv2_providers)}) — rtmlib declares both; uninstalling "
            "either can leave the other's cv2 broken"
        )
    return {
        "ok": rtmlib_version is not None and onnxruntime_version is not None,
        "rtmlib": rtmlib_version,
        "onnxruntime": onnxruntime_version,
        "cv2_providers": cv2_providers,
        "notes": notes,
    }
