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


# ── adversarial-review regressions (PR #13) ────────────────────────────────


@pytest.fixture(scope="module")
def silence_wav(tmp_path_factory) -> str:
    import numpy as np

    path = tmp_path_factory.mktemp("audio") / "silence.wav"
    sf.write(str(path), np.zeros(int(10 * SAMPLE_RATE), dtype="float32"), SAMPLE_RATE)
    return str(path)


def test_silence_never_crashes_and_never_claims_a_tempo(silence_wav):
    """F1: beatless media used to reach ZeroDivisionError via tempo '0'."""
    measurement = measure_grid(silence_wav)
    assert measurement.grid.tempo_bpm is None  # never '0'
    assert any("tempo-unmeasured" in flag for flag in measurement.flags)
    seg = segment(silence_wav, steps=[("a", 2), ("b", 2)])  # the facade contract
    assert seg.method == "grid-measured"
    assert seg.steps == ()  # no invented placement
    assert seg.confidence <= 0.2


def test_tiny_and_empty_files_return_honest_results(tmp_path):
    import numpy as np

    tiny = tmp_path / "tiny.wav"
    sf.write(str(tiny), np.zeros(int(0.05 * SAMPLE_RATE), dtype="float32"), SAMPLE_RATE)
    seg = segment(str(tiny), steps=[("a", 2)])
    assert seg.steps == () and seg.confidence <= 0.2

    empty = tmp_path / "empty.wav"
    sf.write(str(empty), np.zeros(0, dtype="float32"), SAMPLE_RATE)
    seg = segment(str(empty), steps=[("a", 2)])  # must not raise
    assert seg.steps == ()


def test_metric_grid_refuses_zero_tempo_and_zero_subdivisions():
    from paces.model import MetricGrid

    with pytest.raises(Exception, match="positive"):
        MetricGrid(unit="eight", tempo_bpm="0")
    with pytest.raises(Exception, match="positive"):
        MetricGrid(unit="eight", tempo_bpm="-5")
    with pytest.raises(Exception):
        MetricGrid(unit="eight", subdivisions=0)


def test_partial_grid_tempo_wins_and_disagreement_is_flagged(practice_wav):
    """F2: the caller's tempo is used, and the media's disagreement named."""
    seg = segment(
        practice_wav,
        steps=[("a", 2), ("b", 2)],
        grid={"unit": "eight", "subdivisions": 8, "tempoBpm": "200"},
    )
    assert seg.method == "grid-measured"
    assert seg.grid.tempo_bpm == "200"
    assert any(flag.startswith("tempo-disagreement") for flag in seg.flags)


def test_partial_grid_origin_wins_and_is_not_estimated(practice_wav):
    seg = segment(
        practice_wav,
        steps=[("a", 2), ("b", 2)],
        grid={"unit": "eight", "subdivisions": 8, "origin": "12.5"},
    )
    assert seg.method == "grid-measured"
    assert seg.grid.origin == "12.5"
    assert not any(flag.startswith("origin-estimated") for flag in seg.flags)
    assert seg.steps[0].spans[0][0] == pytest.approx(12.5)
    assert seg.confidence >= 0.7  # the weak link was supplied, not guessed


def test_directory_media_is_not_measurable(tmp_path):
    """F3: a directory passes exists() but is not media."""
    seg = segment(str(tmp_path), steps=[("a", 2), ("b", 2)])
    assert "no-signal" in seg.flags
    with pytest.raises(FileNotFoundError, match="not one"):
        measure_grid(str(tmp_path))


def test_non_audio_file_gets_an_informative_error(tmp_path):
    from paces.measure import MediaDecodeError

    junk = tmp_path / "not-audio.json"
    junk.write_text('{"hello": "world"}', encoding="utf-8")
    with pytest.raises(MediaDecodeError, match="as audio"):
        measure_grid(str(junk))


def test_zero_total_units_earns_no_fit_bonus(practice_wav):
    from paces.measure import DFLT_MEASURED_CONFIDENCE

    measurement = measure_grid(practice_wav, total_units=0)
    assert measurement.confidence == DFLT_MEASURED_CONFIDENCE
    assert "routine_s" not in measurement.evidence


def test_known_values_round_trip_verbatim(practice_wav):
    """Round 2 F1: an explicitly supplied string is never reformatted."""
    measurement = measure_grid(practice_wav, tempo_bpm="129.25", origin="12.345")
    assert measurement.grid.tempo_bpm == "129.25"
    assert measurement.grid.origin == "12.345"


def test_known_origin_on_no_music_media_stays_low_confidence(speech_wav):
    """Round 2 F2: a speech-rhythm tempo must not earn origin-level trust."""
    measurement = measure_grid(speech_wav, origin="3.0")
    assert measurement.grid.origin == "3.0"
    assert measurement.confidence <= 0.2
    if measurement.grid.tempo_bpm is not None:
        assert "no-music-region" in measurement.flags


def test_tempo_unmeasured_wording_acknowledges_a_caller_tempo(silence_wav):
    measurement = measure_grid(silence_wav, tempo_bpm="120")
    assert measurement.grid.tempo_bpm == "120"
    assert any(
        "tempo-unmeasured" in flag and "using your tempoBpm" in flag
        for flag in measurement.flags
    )
