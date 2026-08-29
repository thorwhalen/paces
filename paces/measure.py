"""Measure a :class:`~paces.model.MetricGrid` from the media itself.

Roadmap issue #2: when no grid is supplied, the media can often supply its
own — the fleet's ``mixing`` package owns the primitives (speech/music
segmentation, beat tracking) and this module composes them, in the cost order
the POC proved out (``docs/01-what-was-built.md §3.1``):

1. **Macro-structure** — ``find_segments(strategy="speech_music")`` splits
   talk from music; the longest music region is where a routine lives.
2. **Tempo** — ``beat_grid`` on that region (librosa under the hood).
3. **Origin** — the weak link, stated honestly: tempo alone cannot give the
   phase. v1 anchors on the first detected beat of the music region, reports
   LOW confidence, and flags the estimate for confirmation — per ADR-0003, a
   default chosen automatically must be reported with its confidence and
   overridable by one keyword (``grid=``).

The ``grid-measured`` capability wires this into :func:`~paces.segmenters.
segment`: media + a step list with durations, no grid → measure, then place
exactly as ``grid-placed`` would. A *partial* ``grid=`` (unit/subdivisions,
no tempo/origin) is honoured as "what the caller knows"; measurement fills
the rest.

Everything heavy is imported lazily — ``import paces`` never pulls librosa —
and the capability preflights ``mixing``/``librosa`` (the ``[audio]`` extra).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paces.model import MetricGrid, seconds_per_unit
from paces.segmenters import (
    Capability,
    Segmentation,
    _segment_grid_placed,
    register,
)

DFLT_UNIT = "eight"
DFLT_SUBDIVISIONS = 8
DFLT_SAMPLE_RATE = 22050

#: The origin estimate is the honest weak link: "first beat of the music
#: region" is right when the routine starts on bar one, and wrong by an intro.
DFLT_MEASURED_CONFIDENCE = 0.5
#: Earned when the declared routine length fits inside the music region.
FIT_BONUS = 0.2
FIT_TOLERANCE = 1.15  # the routine may overrun the region by 15% before we flag
NO_MUSIC_CONFIDENCE = 0.2


def _dec(value: float, *, places: int = 2) -> str:
    text = f"{float(value):.{places}f}".rstrip("0").rstrip(".")
    return text or "0"


@dataclass(frozen=True, slots=True, kw_only=True)
class GridMeasurement:
    """A measured grid, how much to trust it, and the evidence why."""

    grid: MetricGrid
    confidence: float
    flags: tuple[str, ...] = ()
    evidence: Mapping[str, Any] = field(default_factory=dict)


def measure_grid(
    media: str,
    *,
    unit: str = DFLT_UNIT,
    subdivisions: int = DFLT_SUBDIVISIONS,
    total_units: float | None = None,
    sample_rate: int = DFLT_SAMPLE_RATE,
) -> GridMeasurement:
    """Measure tempo, macro-structure and (estimated) origin from *media*.

    *media* is a local audio (or audio-bearing) file. *total_units*, when
    known (the sum of a step list's durations), buys a sanity check: a
    routine that cannot fit inside the detected music region is flagged —
    the POC's "the doc said 100 bpm, the video says 129" lesson.

    Returns a :class:`GridMeasurement`; when no music region is found the
    grid carries tempo only and ``origin`` stays honestly ``None``.
    """
    try:
        import librosa
        from mixing.audio import beat_grid, find_segments
    except ImportError as error:
        raise ImportError(
            "measure_grid needs the [audio] extra — pip install 'paces[audio]'"
        ) from error

    path = Path(media)
    if not path.exists():
        raise FileNotFoundError(
            f"measure_grid needs a local media file; {media!r} does not exist "
            "(download first — e.g. with yb — or supply grid= yourself)"
        )

    segments = find_segments(str(path), strategy="speech_music")
    evidence: dict[str, Any] = {
        "segments": [
            [round(s.start, 2), round(s.end, 2), s.label or ""] for s in segments
        ]
    }
    music = [s for s in segments if s.label == "music"]
    if not music:
        grid_bg = beat_grid(str(path), sample_rate=sample_rate)
        evidence["tempo_bpm"] = float(grid_bg.tempo_bpm)
        return GridMeasurement(
            grid=MetricGrid(
                unit=unit,
                subdivisions=subdivisions,
                tempo_bpm=_dec(grid_bg.tempo_bpm, places=1),
            ),
            confidence=NO_MUSIC_CONFIDENCE,
            flags=(
                "no-music-region",
                "origin-unknown: pass grid= with an origin, or boundaries=",
            ),
            evidence=evidence,
        )

    region = max(music, key=lambda s: s.end - s.start)
    samples, rate = librosa.load(str(path), sr=sample_rate)
    region_samples = samples[int(region.start * rate) : int(region.end * rate)]
    grid_bg = beat_grid(region_samples, sample_rate=rate)
    first_beat = float(grid_bg.beat_times[0]) if len(grid_bg.beat_times) else 0.0
    origin = region.start + first_beat
    grid = MetricGrid(
        unit=unit,
        subdivisions=subdivisions,
        tempo_bpm=_dec(grid_bg.tempo_bpm, places=1),
        origin=_dec(origin),
    )
    evidence.update(
        tempo_bpm=float(grid_bg.tempo_bpm),
        music_span=[round(region.start, 2), round(region.end, 2)],
        beat_count=len(grid_bg.beat_times),
    )
    flags = (
        f"origin-estimated: first beat of the music region ({_dec(origin)} s) "
        "— override with grid= if the routine starts later",
    )
    confidence = DFLT_MEASURED_CONFIDENCE
    spu = seconds_per_unit(grid)
    if total_units is not None and spu:
        routine_s = total_units * spu
        region_s = region.end - origin
        evidence.update(routine_s=round(routine_s, 2), region_s=round(region_s, 2))
        if routine_s > region_s * FIT_TOLERANCE:
            flags += (
                f"duration-mismatch: {_dec(total_units)} × {unit} = "
                f"{routine_s:.1f} s but the music region holds {region_s:.1f} s "
                "— the step list or the tempo may be wrong",
            )
        else:
            confidence += FIT_BONUS
    return GridMeasurement(
        grid=grid, confidence=confidence, flags=flags, evidence=evidence
    )


def _segment_grid_measured(inputs: Mapping[str, Any]) -> Segmentation:
    """Measure the grid from the media, then place like ``grid-placed``.

    A partial ``grid=`` (unit/subdivisions without tempo+origin) supplies
    what the caller knows; with none at all the dance default is assumed —
    and flagged, because an assumed unit is a guess, not a measurement.
    """
    partial: MetricGrid | None = inputs["grid"]
    unit = partial.unit if partial is not None else DFLT_UNIT
    subdivisions = partial.subdivisions if partial is not None else DFLT_SUBDIVISIONS
    total_units = sum(row["duration"] for row in inputs["steps"])
    measurement = measure_grid(
        inputs["media"], unit=unit, subdivisions=subdivisions, total_units=total_units
    )
    flags = measurement.flags
    if partial is None:
        flags += (
            f"assumed-unit: {DFLT_UNIT} ({DFLT_SUBDIVISIONS} beats) — pass "
            "grid={'unit': ..., 'subdivisions': ...} to change",
        )
    grid = measurement.grid
    if grid.tempo_bpm is None or grid.origin is None:
        return Segmentation(grid=grid, confidence=measurement.confidence, flags=flags)
    placed = _segment_grid_placed({**inputs, "grid": grid})
    return Segmentation(
        steps=placed.steps,
        boundaries=placed.boundaries,
        unit=placed.unit,
        grid=grid,
        confidence=min(placed.confidence, measurement.confidence),
        flags=placed.flags + flags,
    )


GRID_MEASURED = register(
    Capability(
        name="grid-measured",
        gives="segmentation",
        summary=(
            "Measure the metric grid from the media itself (speech/music "
            "split + beat tracking, via mixing), then place the step list "
            "on it. Origin is estimated and flagged for confirmation."
        ),
        target="paces.measure:_segment_grid_measured",
        needs=frozenset({"media.local", "steps", "steps.durations"}),
        requires=("mixing", "librosa"),
        # Explicit information outranks inference: a full grid (1.2) and
        # author chapters (0.75) both beat a measured guess.
        base=0.7,
        s_per_min=2.0,
        resolution_s=0.5,
    )
)
