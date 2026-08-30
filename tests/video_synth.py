"""Deterministic synthetic practice video for derivation tests.

A static green rectangle at a known, asymmetric position (x != y) on a blue
background — spatially non-uniform on purpose: a solid-color clip cannot
distinguish a correct crop origin from an x/y-swapped one. Written with
moviepy, whose writer is the pip-bundled imageio-ffmpeg binary, so building
this fixture needs no system ffmpeg (ADR-0005 §2).
"""

from __future__ import annotations

from pathlib import Path

#: The subject's pixel box (x, y, w, h) and the frame size.
RECT_XYWH = (60, 40, 100, 80)
FRAME_SIZE = (320, 240)


def practice_video(path: str | Path, *, duration_s: float = 2.0, fps: int = 24) -> Path:
    """Write the fixture mp4 to ``path`` and return it."""
    import numpy as np
    from moviepy.video.io.ImageSequenceClip import ImageSequenceClip

    width, height = FRAME_SIZE
    x, y, w, h = RECT_XYWH
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :] = (0, 0, 255)  # blue background (RGB)
    frame[y : y + h, x : x + w] = (0, 255, 0)  # green subject
    clip = ImageSequenceClip([frame] * int(duration_s * fps), fps=fps)
    clip.write_videofile(str(path), codec="libx264", audio=False, logger=None)
    clip.close()
    return Path(path)
