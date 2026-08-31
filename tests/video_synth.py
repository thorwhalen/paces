"""Deterministic synthetic practice video for derivation and slice tests.

A static green rectangle at a known, asymmetric position (x != y) on a blue
background — spatially non-uniform on purpose: a solid-color clip cannot
distinguish a correct crop origin from an x/y-swapped one. Written with
moviepy, whose writer is the pip-bundled imageio-ffmpeg binary, so building
these fixtures needs no system ffmpeg (ADR-0005 §2) — though READING the
audio back out of :func:`practice_av`'s mp4 (what ``measure_grid`` does) is
the system-ffmpeg channel.
"""

from __future__ import annotations

from pathlib import Path

#: The subject's pixel box (x, y, w, h) and the frame size.
RECT_XYWH = (60, 40, 100, 80)
FRAME_SIZE = (320, 240)


def _rect_frame():
    import numpy as np

    width, height = FRAME_SIZE
    x, y, w, h = RECT_XYWH
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :] = (0, 0, 255)  # blue background (RGB)
    frame[y : y + h, x : x + w] = (0, 255, 0)  # green subject
    return frame


def practice_video(path: str | Path, *, duration_s: float = 2.0, fps: int = 24) -> Path:
    """Write the (silent) fixture mp4 to ``path`` and return it."""
    from moviepy.video.io.ImageSequenceClip import ImageSequenceClip

    clip = ImageSequenceClip([_rect_frame()] * int(duration_s * fps), fps=fps)
    clip.write_videofile(str(path), codec="libx264", audio=False, logger=None)
    clip.close()
    return Path(path)


def practice_av(
    path: str | Path,
    *,
    bpm: float = 129.2,
    speech_s: float = 8.0,
    silence_s: float = 1.5,
    music_s: float = 30.0,
    fps: int = 12,
    seed: int = 0,
) -> tuple[Path, dict]:
    """One audio-bearing practice VIDEO — the vertical slice's raw input.

    The audio track is :func:`audio_synth.practice_audio` (speech, a pause,
    then kick-driven music at *bpm* — the POC's macro-structure), muxed onto
    the rect visual. Returns ``(path, truth)`` with the synthesis ground
    truth (music start/end, bpm).
    """
    import numpy as np
    from moviepy.audio.AudioClip import AudioArrayClip
    from moviepy.video.io.ImageSequenceClip import ImageSequenceClip

    from audio_synth import practice_audio

    samples, truth = practice_audio(
        bpm=bpm, speech_s=speech_s, silence_s=silence_s, music_s=music_s, seed=seed
    )
    total_s = samples.size / truth["sample_rate"]
    clip = ImageSequenceClip([_rect_frame()] * int(total_s * fps), fps=fps)
    stereo = np.column_stack([samples, samples])
    clip = clip.with_audio(AudioArrayClip(stereo, fps=truth["sample_rate"]))
    clip.write_videofile(str(path), codec="libx264", audio_codec="aac", logger=None)
    clip.close()
    return Path(path), truth
