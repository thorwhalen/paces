"""Re-express the POC (que_calor_dance) as a paces ``StepDocument``.

This is the schema's acceptance test made concrete (kickoff step 2): the POC's
two hand-maintained layers — ``ROUTINE`` (the step structure, 9 blocks in
domain 8-counts) and ``clips.json`` (the span table, 15 rows) — are mapped
into ONE document. If the dance case does not round-trip, the schema is wrong.

Mapping decisions (each argued in ``docs/07-annotation-model.md §1.2``):

- ``src: RT|BD`` becomes ``SourceSpan.role`` (performance / instruction).
- Every clips row carries deep links into BOTH passes (``yt_run`` +
  ``yt_expl``); each becomes a span whose ``start`` is the link and whose
  ``end`` is honestly ``None``. The pass the extract was cut from carries the
  ``excerpt`` window, the caption, and the tab label.
- ``kind: alt`` is NOT uniformly a sub-step: b4b/b5b are sub-steps, b6b/b7b
  are optional add-on variants (new optional children), b8b is a second
  moment of the same step (extra spans), b9b is a close-up (role override).
- Block 9's hand-written 8 subs + ``shownSubs`` collapse to ``repeat=4`` over
  the two-sub cycle — structure where the POC had a display override.
- ``fig``/``figs``/``hideSubs`` are presentation → ``attrs["render.web"]``.
"""

from __future__ import annotations

import json
from pathlib import Path

from paces.model import (
    Anchor,
    ArtifactRef,
    Cue,
    Measure,
    MetricGrid,
    OpenQuestion,
    Source,
    SourceSpan,
    Step,
    StepDocument,
)

TESTS_DIR = Path(__file__).parent
REPO_DIR = TESTS_DIR.parent
CLIPS_PATH = REPO_DIR / "docs" / "poc-reference" / "artifacts" / "clips.json"
ROUTINE_PATH = TESTS_DIR / "data" / "routine.json"

SOURCE_ID = "celine-yt"
NOTES_ID = "choregraphie-doc"

#: clip id → (block step id, target child id or None = the block step itself)
CLIP_TARGET = {
    "b1": ("b1", None),
    "b2": ("b2", None),
    "b3": ("b3", None),
    "b4a": ("b4", "b4-1"),
    "b4b": ("b4", "b4-2"),
    "b5": ("b5", "b5-1"),
    "b5b": ("b5", "b5-2"),
    "b6": ("b6", None),
    "b6b": ("b6", "b6-chaleur"),
    "b7": ("b7", None),
    "b7b": ("b7", "b7-lacher"),
    "b8": ("b8", None),
    "b8b": ("b8", None),
    "b9": ("b9", None),
    "b9b": ("b9", None),
}

#: alt rows that are optional add-on variants → a NEW optional child
ADDON_CHILDREN = {
    "b6b": ("b6-chaleur", "La chaleur", "4"),
    "b7b": ("b7-lacher", "« j'ai chaud »", "4"),
}

#: alt rows that are another camera angle on the same move → role override
CLOSEUP_CLIPS = {"b9b"}

ROLE_OF_SRC = {"RT": "performance", "BD": "instruction"}


def dec(value) -> str:
    """A clean decimal string from a number ('72.6', never '72.60000000001')."""
    text = f"{float(value):.3f}".rstrip("0").rstrip(".")
    return text or "0"


def _eights(value) -> Measure:
    return Measure(value=dec(value), unit="eight")


def _steps_from_routine(routine: dict) -> tuple[list[Step], list[Cue]]:
    steps, cues = [], []
    for block in routine["blocks"]:
        block_id = f"b{block['n']}"
        render_attrs = {"figs": block["figs"]}
        if block.get("hideSubs"):
            render_attrs["hideSubs"] = True
        children = [
            Step(
                id=f"{block_id}-{i + 1}",
                name=sub["label"],
                duration=_eights(sub["eights"]),
            )
            for i, sub in enumerate(block.get("subs") or block.get("cycle") or [])
        ]
        step = Step(
            id=block_id,
            name=block["title"],
            duration=_eights(block["eights"]),
            steps=children,
            repeat=block.get("repeat", 1),
            attrs={"render.web": render_attrs},
        )
        steps.append(step)
        if block.get("cue"):
            cues.append(
                Cue(
                    id=f"cue-{block_id}",
                    kind="lyric",
                    text=block["cue"],
                    anchor=Anchor(step=block_id),
                    source=SOURCE_ID,
                )
            )
        for i, sub in enumerate(block.get("subs") or block.get("cycle") or []):
            if sub.get("cue"):
                cues.append(
                    Cue(
                        id=f"cue-{block_id}-{i + 1}",
                        kind="lyric",
                        text=sub["cue"],
                        anchor=Anchor(step=f"{block_id}-{i + 1}"),
                        source=SOURCE_ID,
                    )
                )
    return steps, cues


def _find_step(steps: list[Step], step_id: str) -> Step:
    for step in steps:
        if step.id == step_id:
            return step
        found = _find_step(step.steps, step_id)
        if found is not None:
            return found
    return None


def _apply_clip(steps: list[Step], clip: dict) -> None:
    block_id, child_id = CLIP_TARGET[clip["id"]]
    block = _find_step(steps, block_id)
    if clip["id"] in ADDON_CHILDREN:
        child_id, name, eights = ADDON_CHILDREN[clip["id"]]
        target = Step(id=child_id, name=name, duration=_eights(eights), optional=True)
        block.steps.append(target)
    else:
        target = _find_step(steps, child_id) if child_id else block

    carrying_role = ROLE_OF_SRC[clip["src"]]
    link_of_role = {"performance": clip["yt_run"], "instruction": clip["yt_expl"]}
    if clip["id"] in CLOSEUP_CLIPS:
        # The pass-side link belongs to the close-up span, not to a second
        # ordinary span of that pass.
        link_of_role.pop(ROLE_OF_SRC[clip["src"]])
        carrying_role = "closeup"
        link_of_role[carrying_role] = clip[
            "yt_expl" if clip["src"] == "BD" else "yt_run"
        ]

    existing = {(span.role, span.start) for span in target.spans}
    for role, link_s in link_of_role.items():
        start = dec(link_s)
        if (role, start) in existing:
            continue
        span = SourceSpan(source=SOURCE_ID, role=role, start=start)
        if role == carrying_role:
            span = span.model_copy(
                update={
                    "excerpt": (dec(clip["start"]), dec(clip["start"] + clip["dur"])),
                    "caption": clip["cap"],
                    "label": clip["tab"],
                    "attrs": {
                        "clip_id": clip["id"],
                        "render.web": {"fig": clip["fig"]},
                    },
                }
            )
        target.spans.append(span)

    for role, extension in (("clip", "mp4"), ("gif", "gif"), ("poster", "jpg")):
        target.artifacts.append(
            ArtifactRef(
                role=role,
                uri=f"media/{clip['id']}.{extension}",
                derived_from=carrying_role,
                attrs={"clip_id": clip["id"]},
            )
        )


def poc_document() -> StepDocument:
    """Build the full POC as a ``StepDocument``."""
    routine = json.loads(ROUTINE_PATH.read_text(encoding="utf-8"))
    clips = json.loads(CLIPS_PATH.read_text(encoding="utf-8"))
    steps, cues = _steps_from_routine(routine)
    for clip in clips:
        _apply_clip(steps, clip)

    attribution = "Chorégraphie, danse et vidéo : Céline Pradeu"
    return StepDocument(
        id="que-calor-dance",
        title="Chorégraphie Que Calor",
        lang="fr",
        domain="dance",
        metric=MetricGrid(
            unit="eight",
            subdivisions=8,
            tempo_bpm=routine["tempo_bpm"],
            origin=routine["origin_s"],
            origin_source=SOURCE_ID,
        ),
        sources=[
            Source(
                id=SOURCE_ID,
                kind="video",
                uri="https://youtu.be/q_TUyxUhoEw",
                title="Chorégraphie Que Calor",
                duration_s="651",
                attribution=attribution,
                rights=(
                    "Source video is unlisted and shows an identifiable "
                    "private person; derived clips were restyled before "
                    "redistribution."
                ),
            ),
            Source(
                id=NOTES_ID,
                kind="document",
                uri="choregraphie.html",
                attrs={"role": "notes"},
            ),
        ],
        steps=steps,
        cues=cues,
        questions=[
            OpenQuestion(
                id="q-b3-soleil",
                text="À remplacer par les 1ers déhanchés ?",
                status="settled",
            )
        ],
        credits=attribution,
    )
