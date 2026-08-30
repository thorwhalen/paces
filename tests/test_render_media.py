"""The practice page embeds derived clips (issue #1's render half).

Core-only: builds documents with ``ArtifactRef``s directly — no media deps,
no files. The page must not get worse when derivation has not run (span
deep-links stay), and must show looping clips when it has.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from paces.model import (
    ArtifactRef,
    Measure,
    Source,
    SourceSpan,
    Step,
    StepDocument,
    dumps_document,
)
from paces.render import render_html


def _artifacts(base: str) -> list[ArtifactRef]:
    return [
        ArtifactRef(role="clip", uri=f"media/{base}.mp4", mime="video/mp4"),
        ArtifactRef(role="gif", uri=f"media/{base}.gif", mime="image/gif"),
        ArtifactRef(role="poster", uri=f"media/{base}.jpg", mime="image/jpeg"),
    ]


def _doc(*, step_artifacts=(), child_artifacts=()):
    child = Step(
        id="b4-1",
        name="Child",
        duration=Measure(value="2", unit="eight"),
        spans=[SourceSpan(source="perf", role="performance", start="0.4", end="1.2")],
        artifacts=list(child_artifacts),
    )
    step = Step(
        id="b4",
        name="Step 4",
        duration=Measure(value="4", unit="eight"),
        spans=[SourceSpan(source="perf", role="performance", start="0.4")],
        artifacts=list(step_artifacts),
        steps=[
            child,
            Step(id="b4-2", name="Other", duration=Measure(value="2", unit="eight")),
        ],
    )
    return StepDocument(
        id="routine",
        title="Routine",
        sources=[Source(id="perf", kind="video", uri="https://youtu.be/x")],
        steps=[step],
    )


def test_clip_artifact_becomes_a_looping_video():
    html_page = render_html(_doc(step_artifacts=_artifacts("b4")))
    assert '<video controls loop muted playsinline preload="metadata"' in html_page
    assert 'poster="media/b4.jpg"' in html_page
    assert '<source src="media/b4.mp4" type="video/mp4">' in html_page
    assert 'href="media/b4.gif" download' in html_page


def test_child_step_artifacts_render_inside_the_sub_list():
    html_page = render_html(_doc(child_artifacts=_artifacts("b4-1")))
    subs = html_page.split('<ol class="subs">')[1]
    assert '<source src="media/b4-1.mp4"' in subs


def test_media_free_document_renders_no_video_but_keeps_links():
    html_page = render_html(_doc())
    assert "<video" not in html_page
    assert "youtu.be" in html_page  # the span deep-link fallback stays


def test_deep_links_stay_when_clips_are_embedded():
    html_page = render_html(_doc(step_artifacts=_artifacts("b4")))
    assert "youtu.be" in html_page


def test_unpaired_clip_gets_no_poster_or_gif_chrome():
    clip_only = [ArtifactRef(role="clip", uri="media/b4.mp4", mime="video/mp4")]
    html_page = render_html(_doc(step_artifacts=clip_only))
    assert "<video" in html_page
    assert "poster=" not in html_page
    assert "download" not in html_page


def test_render_warns_when_page_leaves_relative_media_behind(tmp_path):
    from paces import tools

    doc_path = tmp_path / "document.json"
    doc_path.write_text(
        dumps_document(_doc(step_artifacts=_artifacts("b4"))), encoding="utf-8"
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    with pytest.warns(UserWarning, match="relative media uris"):
        tools.render(str(doc_path), output=str(elsewhere / "page.html"))
    # beside the document: no warning
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        tools.render(str(doc_path), output=str(tmp_path / "page.html"))
    assert Path(tmp_path / "page.html").is_file()
