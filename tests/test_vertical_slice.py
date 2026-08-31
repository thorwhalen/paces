"""Issue #3: the vertical slice — raw audio-bearing video in, practice page
with a real loop clip at the grid-computed boundaries out.

This is the integration test of the whole pipeline — grid measurement (#2) →
grid-placed segmentation → excerpt suggestion → media derivation (#1) →
render — run through the SAME tool surface the CLI dispatches, on synthetic
media whose ground truth is known (``audio_synth.practice_audio`` muxed onto
the rect video). Deliberately NO new architecture: everything here is the
shipped verbs composed. Fail — never skip — when deps are missing.

``measure_grid`` on an .mp4 needs a SYSTEM ffmpeg (pydub/librosa read the
audio track via PATH ffmpeg — the bundled moviepy binary cannot serve them),
which is why paces now declares ``[tool.wads.ops.ffmpeg]`` (ADR-0005 §2's
fired trigger). Everything derive does still runs bundled-only.
"""

from __future__ import annotations

import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import librosa  # noqa: F401 — fail loudly, never skip
import mixing  # noqa: F401
import moviepy  # noqa: F401
import pytest

from video_synth import FRAME_SIZE, practice_av

#: The synthetic routine: 8 eights of music at the POC's tempo. The last
#: block is the "Déhanchés" analog — the one whose card must carry a clip.
BPM = 129.2
STEPS = [["Intro", 2], ["Bras", 2], ["Déhanchés", 4]]
TOTAL_UNITS = 8
SPU_TRUTH = 8 * 60 / BPM  # ≈ 3.715 s per eight

#: Measurement tolerances, from test_measure's proven bounds: tempo ±0.5 bpm
#: and origin ≈ the music start. The block boundary inherits origin error
#: plus 4 units of tempo drift — ±1.0 s is generous against those and still
#: fails on a half-unit (1.86 s) placement error.
BOUNDARY_TOLERANCE_S = 1.0

SOURCE = {"id": "rt", "kind": "video", "uri": "https://example.com/run-through"}


@pytest.fixture(scope="module")
def av(tmp_path_factory):
    path, truth = practice_av(
        tmp_path_factory.mktemp("slice") / "run_through.mp4",
        bpm=BPM,
        music_s=32.0,  # 8 units ≈ 29.7 s + headroom for measurement drift
    )
    return path, truth


def test_the_slice_end_to_end(tmp_path, av):
    from paces import tools

    video, truth = av

    # 1. segment: measures the grid from the media, places the step list
    seg = tools.segment(str(video), steps=STEPS)
    grid = seg["grid"]
    assert grid is not None, seg["flags"]
    assert float(Fraction(grid["tempoBpm"])) == pytest.approx(BPM, abs=0.5)
    assert float(Fraction(grid["origin"])) == pytest.approx(
        truth["music_start_s"], abs=0.6
    )

    # 2. project into the committed document
    doc_path = tmp_path / "document.json"
    tools.to_document(
        seg, doc_id="routine", title="Routine", source=SOURCE, output=str(doc_path)
    )

    # 3. suggest excerpts: each block's clip window IS its grid window —
    # EVERY block, not just the asserted one
    payload = tools.suggest_excerpts(str(doc_path), output=str(doc_path))
    assert payload["suggested"] == ["intro", "bras", "dehanches"]
    doc = json.loads(doc_path.read_text())
    block = next(s for s in doc["steps"] if s["id"] == "dehanches")
    excerpt = block["spans"][0]["excerpt"]
    start_s, end_s = (float(Fraction(v)) for v in excerpt)

    # the excerpt sits on the measured grid: block 3 spans units 4..8
    origin = float(Fraction(grid["origin"]))
    spu = 8 * 60 / float(Fraction(grid["tempoBpm"]))
    assert start_s == pytest.approx(origin + 4 * spu, abs=0.01)
    assert end_s == pytest.approx(origin + 8 * spu, abs=0.01)
    # ...and on the TRUTH the media was synthesized with
    assert start_s == pytest.approx(
        truth["music_start_s"] + 4 * SPU_TRUTH, abs=BOUNDARY_TOLERANCE_S
    )
    assert end_s == pytest.approx(
        truth["music_start_s"] + 8 * SPU_TRUTH, abs=BOUNDARY_TOLERANCE_S
    )

    # 4. derive: a real clip is cut at those boundaries
    derived = tools.derive(str(doc_path), media=str(video))
    assert not any(f.startswith("stale-artifact") for f in derived["flags"])
    clip_path = tmp_path / "media" / "dehanches.mp4"
    assert clip_path.is_file()
    probed_w, probed_h = mixing.get_video_dimensions(str(clip_path))
    assert (probed_w, probed_h) == FRAME_SIZE  # no-crop default: full frame
    doc = json.loads(doc_path.read_text())
    block = next(s for s in doc["steps"] if s["id"] == "dehanches")
    clip_ref = next(a for a in block["artifacts"] if a["role"] == "clip")
    assert clip_ref["uri"] == "media/dehanches.mp4"
    assert float(Fraction(clip_ref["durationS"])) == pytest.approx(4 * spu, abs=0.05)

    # 5. render: the card shows the looping clip
    page_path = tmp_path / "page.html"
    tools.render(str(doc_path), output=str(page_path))
    page = page_path.read_text()
    assert '<source src="media/dehanches.mp4"' in page
    assert "<video controls loop muted playsinline" in page
    assert 'poster="media/dehanches.jpg"' in page
    assert "Déhanchés" in page

    # 6. the caption is editorial content and arrives as a hand EDIT (which
    # writes a Lock) — the POC card's caption path, exercised the house way
    caption = "Jambes tendues, le bassin pulse"
    tools.edit(
        str(doc_path),
        [
            {
                "op": "set",
                "path": "/steps/dehanches/spans/0/caption",
                "value": caption,
            }
        ],
        by="user:test",
        output=str(doc_path),
    )

    # 7. the crop is hand-tuned via the recipes sidecar (ADR-0005 §3's
    # documented flow: edit box, set locked) — and the digest gate re-cuts
    from paces.derivation import load_recipes, save_recipes

    sidecar = tmp_path / "document.recipes.json"
    recipes = load_recipes(sidecar)
    span_start = block["spans"][0]["start"]
    key = f"dehanches/rt/performance/{span_start}"
    recipes.entries[key].box = (60, 40, 100, 80)
    recipes.entries[key].locked = True
    save_recipes(recipes, sidecar)
    tools.derive(str(doc_path), media=str(video))
    assert tuple(mixing.get_video_dimensions(str(clip_path))) == (100, 80), (
        "the locked hand box must re-cut the existing clip"
    )

    tools.render(str(doc_path), output=str(page_path))
    page = page_path.read_text()
    assert caption in page  # the card carries the caption
    assert '<source src="media/dehanches.mp4"' in page  # and still the clip


def test_the_slice_via_the_cli(tmp_path, av):
    """The kickoff's step 4 as literal shell commands — every seam on its
    default, through ``python -m paces`` exactly as a user would type it."""
    video, _truth = av
    (tmp_path / "steps.json").write_text(
        json.dumps(STEPS, ensure_ascii=False), encoding="utf-8"
    )

    def run(*args: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "paces", *args],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    run("segment", str(video), "--steps", "steps.json", "--output", "seg.json")
    run(
        "to-document",
        "seg.json",
        "--source",
        json.dumps(SOURCE),
        "--doc-id",
        "routine",
        "--title",
        "Routine",
        "--output",
        "document.json",
    )
    run("suggest-excerpts", "document.json", "--output", "document.json")
    run("derive", "document.json", "--media", str(video))
    run("render", "document.json", "--output", "page.html")

    assert (tmp_path / "media" / "dehanches.mp4").is_file()
    assert (tmp_path / "media" / "dehanches.gif").is_file()
    assert (tmp_path / "document.recipes.json").is_file()
    page = (tmp_path / "page.html").read_text()
    assert '<source src="media/dehanches.mp4"' in page


def test_measure_decodes_mp4_without_librosas_deprecated_fallback(av, monkeypatch):
    """CI regression: librosa reads only soundfile formats and silently leans
    on its deprecated audioread fallback when that package happens to be
    installed (dev machines) — and raises where it is not (CI). Simulate the
    CI condition and prove the pydub decode path carries the mp4."""
    import librosa

    from paces import measure

    video, truth = av
    real_load = librosa.load

    def no_fallback_load(path, **kwargs):
        if str(path).endswith(".mp4"):
            raise RuntimeError("simulated: soundfile cannot open mp4")
        return real_load(path, **kwargs)

    monkeypatch.setattr(librosa, "load", no_fallback_load)
    samples, rate = measure._load_audio(video, sample_rate=22050)
    assert rate == 22050 and samples.size > 20 * 22050  # ~41 s of audio
    # and the full measurement still lands on the truth through this path
    measurement = measure.measure_grid(str(video))
    assert measurement.grid.tempo_bpm is not None
    assert float(measurement.grid.tempo_bpm) == pytest.approx(truth["bpm"], abs=0.5)
