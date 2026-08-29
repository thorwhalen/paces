"""Synthesize practice-video-shaped audio for the grid-measurement tests.

The shape mirrors the POC's macro-structure (docs/01 §3.1): the teacher talks
(amplitude-modulated noise at a syllabic ~4 Hz), a beat of silence, then the
run-through — music with a sub-bass kick on a known tempo. Everything is
deterministic (seeded) and synthesized at test time: no media files in the
repo, no network, no cost.
"""

from __future__ import annotations

import numpy as np

SAMPLE_RATE = 22050


def practice_audio(
    *,
    bpm: float = 129.2,
    speech_s: float = 8.0,
    silence_s: float = 1.5,
    music_s: float = 30.0,
    sample_rate: int = SAMPLE_RATE,
    seed: int = 0,
) -> tuple[np.ndarray, dict]:
    """Speech, a pause, then kick-driven music at *bpm*.

    Returns ``(samples, truth)`` where ``truth`` carries the ground truth the
    tests assert against (music start/end, bpm).
    """
    rng = np.random.default_rng(seed)

    t_speech = np.arange(int(speech_s * sample_rate)) / sample_rate
    speech = (
        rng.normal(0, 0.15, t_speech.size)
        * (0.55 + 0.45 * np.sin(2 * np.pi * 3.8 * t_speech)) ** 2
    )
    speech *= np.sin(2 * np.pi * 0.4 * t_speech) > -0.6  # breathing pauses

    silence = np.zeros(int(silence_s * sample_rate))

    beat_period = 60 / bpm
    t_music = np.arange(int(music_s * sample_rate)) / sample_rate
    music = 0.05 * rng.normal(0, 1, t_music.size)  # hiss bed
    music += 0.15 * np.sin(2 * np.pi * 110 * t_music)  # sustained tone
    for k in range(int(music_s / beat_period)):
        start = int(k * beat_period * sample_rate)
        end = min(start + int(0.09 * sample_rate), t_music.size)
        n = end - start
        envelope = np.exp(-np.arange(n) / (0.02 * sample_rate))
        music[start:end] += (
            0.9 * np.sin(2 * np.pi * 55 * np.arange(n) / sample_rate) * envelope
        )

    samples = np.concatenate([speech, silence, music]).astype(np.float32)
    truth = {
        "bpm": bpm,
        "music_start_s": speech_s + silence_s,
        "music_end_s": speech_s + silence_s + music_s,
        "sample_rate": sample_rate,
    }
    return samples, truth


def speech_only_audio(
    *, duration_s: float = 12.0, sample_rate: int = SAMPLE_RATE, seed: int = 1
) -> np.ndarray:
    """Talk with no music anywhere — the origin-unknown case."""
    t = np.arange(int(duration_s * sample_rate)) / sample_rate
    rng = np.random.default_rng(seed)
    speech = (
        rng.normal(0, 0.15, t.size) * (0.55 + 0.45 * np.sin(2 * np.pi * 4.1 * t)) ** 2
    )
    return (speech * (np.sin(2 * np.pi * 0.3 * t) > -0.7)).astype(np.float32)
