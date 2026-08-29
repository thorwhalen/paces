"""Grid measurement (issue #2): tempo + macro-structure measured, origin
estimated and flagged — on synthesized audio with known ground truth.

These tests exercise the REAL mixing/librosa path (no mocks); the audio is
deterministic, generated at test time, and never leaves tmp_path. They fail —
not skip — when the [audio]/dev deps are missing: a silently skipped suite
proves nothing.
"""

from __future__ import annotations

import pytest
import soundfile as sf

from audio_synth import SAMPLE_RATE, practice_audio, speech_only_audio
from paces.measure import measure_grid
from paces.segmenters import segment

BPM = 129.2
MUSIC_START = 9.5  # 8 s speech + 1.5 s silence


@pytest.fixture(scope="module")
def practice_wav(tmp_path_factory) -> str:
    samples, _ = practice_audio(bpm=BPM)
    path = tmp_path_factory.mktemp("audio") / "practice.wav"
    sf.write(str(path), samples, SAMPLE_RATE)
    return str(path)


@pytest.fixture(scope="module")
def speech_wav(tmp_path_factory) -> str:
    path = tmp_path_factory.mktemp("audio") / "speech.wav"
    sf.write(str(path), speech_only_audio(), SAMPLE_RATE)
    return str(path)


def test_measure_finds_tempo_structure_and_estimated_origin(practice_wav):
    measurement = measure_grid(practice_wav)
    grid = measurement.grid
    assert grid.unit == "eight" and grid.subdivisions == 8
    assert float(grid.tempo_bpm) == pytest.approx(BPM, abs=0.5)
    # origin: first beat of the music region — near, at or after music start
    assert float(grid.origin) == pytest.approx(MUSIC_START, abs=1.0)
    start, end = measurement.evidence["music_span"]
    assert start == pytest.approx(MUSIC_START, abs=0.5)
    assert any(flag.startswith("origin-estimated") for flag in measurement.flags)
    assert 0 < measurement.confidence < 0.9  # an estimate, never certainty


def test_fitting_routine_length_raises_confidence(practice_wav):
    # 7 eights ≈ 26 s fits the ~30 s music region; 40 eights ≈ 148 s cannot
    fits = measure_grid(practice_wav, total_units=7)
    overruns = measure_grid(practice_wav, total_units=40)
    assert fits.confidence > overruns.confidence
    assert not any("duration-mismatch" in flag for flag in fits.flags)
    assert any("duration-mismatch" in flag for flag in overruns.flags)


def test_speech_only_media_is_honest_about_the_origin(speech_wav):
    measurement = measure_grid(speech_wav)
    assert measurement.grid.origin is None
    assert "no-music-region" in measurement.flags
    assert measurement.confidence <= 0.2


def test_missing_file_names_the_fix():
    with pytest.raises(FileNotFoundError, match="grid="):
        measure_grid("nope-not-here.wav")


# ── the grid-measured capability, end to end ────────────────────────────────


def test_segment_measures_when_no_grid_is_given(practice_wav):
    seg = segment(practice_wav, steps=[("intro", 2), ("chorus", 2), ("outro", 3)])
    assert seg.method == "grid-measured"
    assert seg.unit == "eight"
    assert seg.grid is not None
    assert float(seg.grid.tempo_bpm) == pytest.approx(BPM, abs=0.5)
    # placement happened on the measured grid
    assert len(seg.steps) == 3
    assert seg.steps[0].spans[0][0] == pytest.approx(float(seg.grid.origin))
    spu = 8 * 60 / float(seg.grid.tempo_bpm)
    assert seg.steps[1].spans[0][0] == pytest.approx(
        float(seg.grid.origin) + 2 * spu, abs=0.05
    )
    # honesty: the estimate and the assumed unit are both flagged
    assert any(flag.startswith("origin-estimated") for flag in seg.flags)
    assert any(flag.startswith("assumed-unit") for flag in seg.flags)
    assert seg.confidence <= 0.7


def test_partial_grid_supplies_the_unit_and_suppresses_the_assumption(practice_wav):
    seg = segment(
        practice_wav,
        steps=[("a", 4), ("b", 4)],
        grid={"unit": "bar", "subdivisions": 4},
    )
    assert seg.method == "grid-measured"
    assert seg.unit == "bar" and seg.grid.subdivisions == 4
    assert not any(flag.startswith("assumed-unit") for flag in seg.flags)


def test_explicit_grid_still_outranks_measurement(practice_wav):
    seg = segment(
        practice_wav,
        steps=[("a", 4), ("b", 4)],
        grid={"unit": "eight", "subdivisions": 8, "tempoBpm": "120", "origin": "3"},
    )
    assert seg.method == "grid-placed"


def test_remote_media_cannot_select_measurement():
    seg = segment("https://example.com/video.mp4", steps=[("a", 2), ("b", 2)])
    assert "no-signal" in seg.flags  # media.local is the gate


def test_speech_only_segmentation_reports_what_it_still_needs(speech_wav):
    seg = segment(speech_wav, steps=[("a", 2), ("b", 2)])
    assert seg.method == "grid-measured"
    assert seg.steps == ()  # no invented placement
    assert seg.grid is not None and seg.grid.origin is None
    assert "no-music-region" in seg.flags
    assert any("origin-unknown" in flag for flag in seg.flags)


def test_measure_grid_tool_is_json_ready(practice_wav):
    import json

    from paces.tools import measure_grid as measure_tool

    payload = measure_tool(practice_wav, total_units=7)
    json.dumps(payload)
    assert payload["grid"]["tempoBpm"]
    assert payload["evidence"]["music_span"]
