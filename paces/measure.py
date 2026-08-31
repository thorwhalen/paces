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

Honesty under failure (adversarial review, PR #13): media with no beat
structure — silence, ambience, an empty file — yields a grid whose tempo is
honestly ``None`` (never ``"0"``: :class:`~paces.model.MetricGrid` refuses
non-positive tempi) plus a ``tempo-unmeasured`` flag, and the ``segment()``
facade keeps its returns-a-Segmentation-always contract.

The ``grid-measured`` capability wires this into :func:`~paces.segmenters.
segment`: media + a step list with durations, no full grid → measure, then
place exactly as ``grid-placed`` would. A *partial* ``grid=`` is honoured as
"what the caller knows" — unit and subdivisions always, and a caller-supplied
tempo or origin **wins over the measured value** (explicit beats inferred),
with a ``tempo-disagreement`` flag when the media measurably disagrees — the
POC's doc-said-100-video-says-129 lesson, surfaced as a diff instead of
silently resolved either way.

Everything heavy is imported lazily — ``import paces`` never pulls librosa —
and the capability preflights ``mixing``/``librosa`` (the ``[audio]`` extra).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

from paces.model import MetricGrid, decimal_str, seconds_per_unit
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
#: A caller-supplied origin removes the weak link; the tempo half is reliable.
KNOWN_ORIGIN_CONFIDENCE = 0.75
#: Earned when the declared routine length fits inside the music region.
FIT_BONUS = 0.2
FIT_TOLERANCE = 1.15  # the routine may overrun the region by 15% before we flag
UNMEASURED_CONFIDENCE = 0.2
#: A caller tempo further than this (relative) from the measured one is flagged.
TEMPO_DISAGREEMENT_RTOL = 0.02


class MediaDecodeError(ValueError):
    """The file exists but could not be read as audio."""


def _dec(value: float, *, places: int = 2) -> str:
    return decimal_str(value, places=places)


@dataclass(frozen=True, slots=True, kw_only=True)
class GridMeasurement:
    """A measured grid, how much to trust it, and the evidence why."""

    grid: MetricGrid
    confidence: float
    flags: tuple[str, ...] = ()
    evidence: Mapping[str, Any] = field(default_factory=dict)


def _load_audio(path, *, sample_rate):
    """Decode *path* to ``(samples, rate)`` — wav-family natively, anything
    else through pydub's ffmpeg decode to a temp wav.

    librosa reads only what soundfile can open (wav/flac/ogg); for an .mp4
    or .mp3 it silently falls back to its DEPRECATED audioread path when
    that package happens to be installed, and raises when it is not — which
    is exactly how this worked on a dev machine and failed on CI. Routing
    non-wav through pydub gives one decode path (the same ffmpeg pydub
    already uses for ``find_segments`` on the same file) that survives
    librosa 1.0.
    """
    import librosa

    try:
        return librosa.load(str(path), sr=sample_rate)
    except Exception:
        import tempfile

        from pydub import AudioSegment

        audio = AudioSegment.from_file(str(path))
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = Path(tmp) / "decoded.wav"
            audio.export(str(wav_path), format="wav")
            return librosa.load(str(wav_path), sr=sample_rate)


def _measured_tempo(beat_grid_result) -> tuple[str | None, float | None]:
    """The tempo as a wire decimal, or None when there is no beat structure.

    mixing's ``beat_grid`` reports ``tempo_bpm = 0.0`` when librosa finds no
    tempo; zero is 'unmeasured', never a value (a zero tempo is
    unrepresentable in :class:`MetricGrid`, deliberately).
    """
    tempo = float(beat_grid_result.tempo_bpm)
    if tempo <= 0 or not len(beat_grid_result.beat_times):
        return None, None
    return _dec(tempo, places=1), tempo


def measure_grid(
    media: str,
    *,
    unit: str = DFLT_UNIT,
    subdivisions: int = DFLT_SUBDIVISIONS,
    tempo_bpm: str | float | None = None,
    origin: str | float | None = None,
    total_units: float | None = None,
    sample_rate: int = DFLT_SAMPLE_RATE,
) -> GridMeasurement:
    """Measure tempo, macro-structure and (estimated) origin from *media*.

    *media* is a local audio (or audio-bearing) file. *tempo_bpm* and
    *origin*, when given, are what the caller already knows: they WIN over
    the measured values (a disagreement is flagged, never silently resolved).
    *total_units* (the sum of a step list's durations) buys a sanity check: a
    routine that cannot fit inside the detected music region is flagged.

    Returns a :class:`GridMeasurement`; whatever could not be measured stays
    honestly ``None`` on the grid, with a flag naming it.
    """
    try:
        import librosa
        from mixing.audio import beat_grid, find_segments
    except ImportError as error:
        raise ImportError(
            "measure_grid needs the [audio] extra — pip install 'paces[audio]'"
        ) from error

    path = Path(media)
    if not path.is_file():
        raise FileNotFoundError(
            f"measure_grid needs a local media file; {media!r} is not one "
            "(download first — e.g. with yb — or supply grid= yourself)"
        )
    # A caller-supplied string is already a valid wire decimal: pass it
    # through untouched so the declared value round-trips verbatim; only
    # numbers get formatted.
    known_tempo = (
        tempo_bpm
        if isinstance(tempo_bpm, str)
        else None
        if tempo_bpm is None
        else _dec(float(tempo_bpm), places=1)
    )
    known_origin = (
        origin
        if isinstance(origin, str)
        else None
        if origin is None
        else _dec(float(origin))
    )

    try:
        segments = find_segments(str(path), strategy="speech_music")
    except Exception as error:
        raise MediaDecodeError(
            f"could not read {media!r} as audio ({type(error).__name__}) — "
            "is it an audio/video file? Non-wav formats need ffmpeg installed."
        ) from error
    evidence: dict[str, Any] = {
        "segments": [
            [round(s.start, 2), round(s.end, 2), s.label or ""] for s in segments
        ]
    }
    music = [s for s in segments if s.label == "music"]
    flags: tuple[str, ...] = ()

    if music:
        region = max(music, key=lambda s: s.end - s.start)
        try:
            samples, rate = _load_audio(path, sample_rate=sample_rate)
        except Exception as error:
            raise MediaDecodeError(
                f"could not decode {media!r} as audio ({type(error).__name__})"
            ) from error
        region_samples = samples[int(region.start * rate) : int(region.end * rate)]
        bg = beat_grid(region_samples, sample_rate=rate)
        measured_tempo, tempo_value = _measured_tempo(bg)
        evidence.update(
            music_span=[round(region.start, 2), round(region.end, 2)],
            beat_count=len(bg.beat_times),
        )
        if measured_tempo is not None:
            evidence["tempo_bpm"] = tempo_value
            measured_origin = _dec(region.start + float(bg.beat_times[0]))
            tempo_unmeasured_note = None
        else:
            tempo_unmeasured_note = "no beat structure in the music region"
            measured_origin = None
    else:
        region = None
        bg = beat_grid(str(path), sample_rate=sample_rate)
        measured_tempo, tempo_value = _measured_tempo(bg)
        measured_origin = None
        if measured_tempo is not None:
            evidence["tempo_bpm"] = tempo_value
            tempo_unmeasured_note = None
        else:
            tempo_unmeasured_note = "no beat structure found"
        flags += ("no-music-region",)
    if tempo_unmeasured_note is not None:
        suffix = " — using your tempoBpm" if known_tempo is not None else ""
        flags += (f"tempo-unmeasured: {tempo_unmeasured_note}{suffix}",)

    # Explicit beats inferred — but a disagreement is a finding, not a secret.
    final_tempo = known_tempo or measured_tempo
    if (
        known_tempo is not None
        and measured_tempo is not None
        and abs(float(known_tempo) - float(measured_tempo))
        > float(measured_tempo) * TEMPO_DISAGREEMENT_RTOL
    ):
        flags += (
            f"tempo-disagreement: you said {known_tempo} bpm, the media "
            f"measures {measured_tempo} — using yours; drop tempoBpm from "
            "grid= to use the measured value",
        )
    final_origin = known_origin or measured_origin
    if known_origin is None and measured_origin is not None:
        flags += (
            f"origin-estimated: first beat of the music region "
            f"({measured_origin} s) — override with grid= if the routine "
            "starts later",
        )

    grid = MetricGrid(
        unit=unit,
        subdivisions=subdivisions,
        tempo_bpm=final_tempo,
        origin=final_origin,
    )
    if final_origin is None:
        flags += ("origin-unknown: pass grid= with an origin, or boundaries=",)
        confidence = UNMEASURED_CONFIDENCE
    elif region is None:
        # The grid is only complete because the caller supplied the origin,
        # and any tempo here was measured from a no-music recording (speech
        # rhythm) — a placement can proceed, but not with real confidence.
        confidence = UNMEASURED_CONFIDENCE
    else:
        confidence = (
            KNOWN_ORIGIN_CONFIDENCE if known_origin else DFLT_MEASURED_CONFIDENCE
        )

    spu = seconds_per_unit(grid)
    if total_units and total_units > 0 and spu and final_origin and region:
        routine_s = total_units * spu
        region_s = region.end - float(Fraction(final_origin))
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
        grid=grid, confidence=min(confidence, 0.95), flags=flags, evidence=evidence
    )


def _segment_grid_measured(inputs: Mapping[str, Any]) -> Segmentation:
    """Measure what the caller's partial ``grid=`` left unknown, then place
    like ``grid-placed``.

    With no grid at all the dance default is assumed — and flagged, because
    an assumed unit is a guess, not a measurement. Whatever still cannot be
    known (a beatless recording's origin) yields the honest partial result,
    never an exception and never an invented placement.
    """
    partial: MetricGrid | None = inputs["grid"]
    unit = partial.unit if partial is not None else DFLT_UNIT
    subdivisions = partial.subdivisions if partial is not None else DFLT_SUBDIVISIONS
    total_units = sum(row["duration"] for row in inputs["steps"])
    measurement = measure_grid(
        inputs["media"],
        unit=unit,
        subdivisions=subdivisions,
        tempo_bpm=partial.tempo_bpm if partial is not None else None,
        origin=partial.origin if partial is not None else None,
        total_units=total_units,
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
