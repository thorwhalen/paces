"""The one-command test — the definition of v1 (architecture-first).

v1 done when::

    python -m paces segment --steps steps.json --grid grid.json \\
        --output seg.json
    python -m paces to-document seg.json --source <video-url> \\
        --title "..." --output document.json
    python -m paces render document.json --output page.html

produces a practice page you would actually use. This test runs exactly that
path, every seam on its default, and must still pass after every later seam
swap.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

VIDEO_URL = "https://youtu.be/q_TUyxUhoEw"
STEPS = [
    ["Mise en place", 2],
    ["Pas pieds pointe et ronde", 6],
    ["Soleil avec les bras", 4],
    ["Déhanchés", 8],
    ["Moulinets de bras", 4],
    ["Genou vers le bas", 4],
    ["Pas pieds pointe, bras alternés", 4],
    ["Taper dans les mains du voisin", 4],
    ["Avancer / reculer sur le refrain", 8],
]
GRID = {"unit": "eight", "subdivisions": 8, "tempoBpm": "129.2", "origin": "51.2"}


def _run(*args: str, cwd: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "paces", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_the_one_command_path(tmp_path):
    (tmp_path / "steps.json").write_text(json.dumps(STEPS), encoding="utf-8")
    (tmp_path / "grid.json").write_text(json.dumps(GRID), encoding="utf-8")

    _run(
        "segment",
        VIDEO_URL,
        "--steps",
        "steps.json",
        "--grid",
        "grid.json",
        "--output",
        "seg.json",
        cwd=tmp_path,
    )
    seg = json.loads((tmp_path / "seg.json").read_text(encoding="utf-8"))
    assert seg["method"] == "grid-placed" and len(seg["steps"]) == 9

    _run(
        "to-document",
        "seg.json",
        "--doc-id",
        "que-calor",
        "--title",
        "Chorégraphie Que Calor",
        "--source",
        VIDEO_URL,
        "--domain",
        "dance",
        "--lang",
        "fr",
        "--output",
        "document.json",
        cwd=tmp_path,
    )
    doc = json.loads((tmp_path / "document.json").read_text(encoding="utf-8"))
    assert doc["kind"] == "StepDocument" and len(doc["steps"]) == 9

    _run("render", "document.json", "--output", "page.html", cwd=tmp_path)
    page = (tmp_path / "page.html").read_text(encoding="utf-8")

    # a page you would actually use: named steps, counts, deep links back
    # into the video, and the count-along transport
    assert "Déhanchés" in page
    assert "8 eight" in page
    assert f"{VIDEO_URL}?t=95" in page  # block 4's run-through deep link
    assert "count me in" in page  # the transport — the tool paces you


def test_validate_and_resolve_tools(tmp_path):
    from paces import tools

    seg = tools.segment(VIDEO_URL, steps=STEPS, grid=GRID)
    doc = tools.to_document(seg, doc_id="g", title="G", source=VIDEO_URL)
    assert tools.validate(doc) == {"issues": []}
    resolved = tools.resolve(doc)
    assert resolved["total_units"] == 44.0
    assert "grid-placed" in tools.list_segmenters()
