"""Edit protection: typed patches write Locks; regeneration cannot eat edits.

The scenario throughout is the POC's real failure mode: a human fixes a
caption / a name, analysis re-runs, and the regenerated document must keep the
fix (docs/07-annotation-model.md §1.3).
"""

from __future__ import annotations

import pytest

from paces.edits import apply_edits, merge_regenerated
from paces.model import Measure, Origin, SourceSpan, Step, StepDocument, Source


def _doc(**overrides) -> StepDocument:
    """A small two-step document with spans, the shape a projection makes."""
    fields = dict(
        id="guide",
        title="A guide",
        sources=[Source(id="vid", kind="video", uri="https://example.com/v")],
        steps=[
            Step(
                id="a",
                name="Step A",
                duration=Measure(value="2", unit="eight"),
                spans=[SourceSpan(source="vid", start="10", end="20")],
                origin=Origin(generated_by="segmenter:grid-placed"),
            ),
            Step(
                id="b",
                name="Step B",
                duration=Measure(value="4", unit="eight"),
                spans=[
                    SourceSpan(source="vid", start="20", end="35", caption="machine")
                ],
                origin=Origin(generated_by="segmenter:grid-placed"),
            ),
        ],
    )
    fields.update(overrides)
    return StepDocument(**fields)


# ── apply_edits ─────────────────────────────────────────────────────────────


def test_set_by_step_id_records_a_reversible_lock():
    doc = apply_edits(
        _doc(),
        [{"op": "set", "path": "/steps/b/spans/0/caption", "value": "hand-fixed"}],
        by="user:thor",
    )
    step_b = doc.steps[1]
    assert step_b.spans[0].caption == "hand-fixed"
    (lock,) = step_b.locks
    assert lock.path == "/spans/0/caption"
    assert lock.was == "machine"
    assert lock.by == "user:thor"


def test_set_by_index_and_doc_level_lock():
    doc = apply_edits(
        _doc(),
        [
            {"op": "set", "path": "/steps/0/name", "value": "Renamed"},
            {"op": "set", "path": "/title", "value": "Better title"},
        ],
        by="user:thor",
    )
    assert doc.steps[0].name == "Renamed"
    assert doc.steps[0].locks[0].path == "/name"
    assert doc.title == "Better title"
    assert doc.locks[0].path == "/title"
    assert doc.locks[0].was == "A guide"


def test_editing_a_locked_path_again_replaces_the_lock():
    doc = apply_edits(
        _doc(), [{"op": "set", "path": "/steps/a/name", "value": "v1"}], by="user:t"
    )
    doc = apply_edits(
        doc, [{"op": "set", "path": "/steps/a/name", "value": "v2"}], by="user:t"
    )
    (lock,) = doc.steps[0].locks
    assert lock.was == "v1"  # the last edit stays reversible


def test_bad_paths_and_ops_are_informative_and_atomic():
    original = _doc()
    with pytest.raises(ValueError, match="no item with id 'zz'"):
        apply_edits(
            original,
            [{"op": "set", "path": "/steps/zz/name", "value": "x"}],
            by="user:t",
        )
    with pytest.raises(ValueError, match="unsupported op"):
        apply_edits(
            original,
            [{"op": "append", "path": "/steps", "value": {}}],
            by="user:t",
        )
    with pytest.raises(ValueError, match="no field"):
        apply_edits(
            original,
            [{"op": "set", "path": "/steps/a/nope", "value": "x"}],
            by="user:t",
        )
    assert original == _doc()  # nothing was half-applied


def test_invalid_value_fails_schema_validation():
    with pytest.raises(Exception, match="duration"):
        apply_edits(
            _doc(),
            [{"op": "set", "path": "/steps/a/duration", "value": 3.5}],
            by="user:t",
        )


# ── merge_regenerated ───────────────────────────────────────────────────────


def test_merge_keeps_locked_values_and_takes_fresh_elsewhere():
    committed = apply_edits(
        _doc(),
        [{"op": "set", "path": "/steps/b/spans/0/caption", "value": "hand-fixed"}],
        by="user:thor",
    )
    # regeneration moved a boundary AND regressed the caption
    fresh = _doc()
    fresh.steps[1].spans[0].caption = "machine v2"
    fresh.steps[1].spans[0].start = "21"
    fresh.steps[0].name = "Step A improved"

    merged = merge_regenerated(committed, fresh)
    assert merged.steps[1].spans[0].caption == "hand-fixed"  # lock wins
    assert merged.steps[1].spans[0].start == "21"  # fresh wins unlocked
    assert merged.steps[0].name == "Step A improved"
    assert merged.steps[1].locks == committed.steps[1].locks  # protection travels


def test_merge_keeps_doc_level_locks():
    committed = apply_edits(
        _doc(), [{"op": "set", "path": "/title", "value": "My title"}], by="user:t"
    )
    fresh = _doc(title="Regenerated title")
    merged = merge_regenerated(committed, fresh)
    assert merged.title == "My title"


def test_protected_committed_only_step_survives_where_it_was():
    committed = _doc()
    committed.steps.insert(
        1,
        Step(
            id="human-extra",
            name="A step the human added",
            duration=Measure(value="1", unit="eight"),
            origin=Origin(generated_by="user:thor"),
        ),
    )
    fresh = _doc()  # regeneration knows nothing of the human step
    merged = merge_regenerated(committed, fresh)
    assert [s.id for s in merged.steps] == ["a", "human-extra", "b"]


def test_unprotected_committed_only_step_is_superseded():
    committed = _doc()
    committed.steps.append(
        Step(
            id="stale-analysis",
            name="Old analysis output",
            duration=Measure(value="1", unit="eight"),
            origin=Origin(generated_by="segmenter:grid-placed"),
        )
    )
    merged = merge_regenerated(committed, _doc())
    assert [s.id for s in merged.steps] == ["a", "b"]


def test_fresh_only_steps_are_kept():
    fresh = _doc()
    fresh.steps.append(
        Step(
            id="new-find",
            name="Newly detected",
            duration=Measure(value="1", unit="eight"),
        )
    )
    merged = merge_regenerated(_doc(), fresh)
    assert merged.steps[-1].id == "new-find"


def test_committed_cues_and_questions_survive_a_cueless_regeneration():
    from paces.model import Anchor, Cue, OpenQuestion

    committed = _doc()
    committed.cues.append(
        Cue(id="c1", kind="lyric", text="qué calor", anchor=Anchor(step="a"))
    )
    committed.questions.append(OpenQuestion(id="q1", text="Which side first?"))
    merged = merge_regenerated(committed, _doc())
    assert merged.cues[0].text == "qué calor"
    assert merged.questions[0].id == "q1"


def test_lock_on_a_path_the_fresh_structure_lost_is_kept_as_record():
    committed = apply_edits(
        _doc(),
        [{"op": "set", "path": "/steps/b/spans/0/caption", "value": "kept"}],
        by="user:t",
    )
    fresh = _doc()
    fresh.steps[1].spans = []  # regeneration dropped the span entirely
    merged = merge_regenerated(committed, fresh)
    assert merged.steps[1].spans == []  # structure follows fresh...
    assert merged.steps[1].locks[0].was == "machine"  # ...the record survives


def test_tools_roundtrip_edit_and_merge():
    from paces import tools

    doc_dict = tools.to_document(
        tools.segment(boundaries=[0, 10, 20], steps=["intro", "verse"]),
        doc_id="g",
        title="G",
        source="https://example.com/v",
    )
    edited = tools.edit(
        doc_dict,
        [{"op": "set", "path": "/steps/intro/name", "value": "Intro!"}],
        by="user:thor",
    )
    assert edited["steps"][0]["name"] == "Intro!"
    merged = tools.merge(edited, doc_dict)
    assert merged["steps"][0]["name"] == "Intro!"


# ── adversarial-review regressions (PR #11) ────────────────────────────────


def test_span_lock_follows_the_span_through_a_reorder():
    """Finding 1 (BLOCKER): a fresh doc inserts a new span BEFORE the locked
    one; the locked caption must land on the matched span, not position 0."""
    committed = apply_edits(
        _doc(),
        [{"op": "set", "path": "/steps/b/spans/0/caption", "value": "hand-fixed"}],
        by="user:thor",
    )
    fresh = _doc()
    fresh.steps[1].spans = [
        SourceSpan(source="vid", role="closeup", start="5", end="9"),
        SourceSpan(source="vid", start="20", end="35", caption="machine v2"),
    ]
    merged = merge_regenerated(committed, fresh)
    closeup, performance = merged.steps[1].spans
    assert closeup.caption is None  # the new span is untouched
    assert performance.caption == "hand-fixed"  # the lock followed its span


def test_source_lock_follows_the_source_through_a_reorder():
    committed = _doc()
    committed.sources.append(Source(id="notes", kind="document", uri="notes.html"))
    committed = apply_edits(
        committed,
        [{"op": "set", "path": "/sources/1/uri", "value": "notes-v2.html"}],
        by="user:thor",
    )
    # canonicalised to id-form at record time
    assert committed.locks[0].path == "/sources/notes/uri"
    fresh = _doc()
    fresh.sources = [
        Source(id="notes", kind="document", uri="notes.html"),
        Source(id="vid", kind="video", uri="https://example.com/v"),
    ]
    merged = merge_regenerated(committed, fresh)
    by_id = {s.id: s for s in merged.sources}
    assert by_id["notes"].uri == "notes-v2.html"
    assert by_id["vid"].uri == "https://example.com/v"


def test_digit_step_ids_resolve_id_first():
    """Finding 2: chapters titled '1','2' mint digit ids; /steps/1 must mean
    the step whose id is '1', not position 1."""
    doc = _doc()
    doc.steps[0].id = "1"
    doc.steps[1].id = "0"
    edited = apply_edits(
        doc, [{"op": "set", "path": "/steps/1/name", "value": "hit"}], by="user:t"
    )
    assert edited.steps[0].name == "hit"  # id '1' is at position 0
    assert edited.steps[1].name == "Step B"


def test_step_shaped_attrs_data_does_not_capture_the_lock():
    """Finding 3: user data in attrs that happens to look like a Step must
    not swallow the Lock, and the edit must survive a merge."""
    committed = _doc()
    committed.attrs["things"] = [{"duration": 1, "spans": [], "note": "orig"}]
    committed = apply_edits(
        committed,
        [{"op": "set", "path": "/attrs/things/0/note", "value": "fixed"}],
        by="user:thor",
    )
    assert committed.locks and committed.locks[0].path == "/attrs/things/0/note"
    assert "locks" not in committed.attrs["things"][0]  # user data unpolluted
    assert all(not s.locks for s in committed.steps)
    fresh = _doc()
    fresh.attrs["things"] = [{"duration": 1, "spans": [], "note": "orig"}]
    merged = merge_regenerated(committed, fresh)
    assert merged.attrs["things"][0]["note"] == "fixed"  # committed attrs win


def test_duplicate_step_ids_are_flagged_by_the_validator():
    from paces.model import validate_document

    doc = _doc()
    doc.steps[1].id = "a"
    issues = validate_document(doc)
    assert any("duplicate step id 'a'" in issue for issue in issues)


def test_a_single_bare_edit_mapping_is_accepted():
    doc = apply_edits(
        _doc(), {"op": "set", "path": "/title", "value": "One edit"}, by="user:t"
    )
    assert doc.title == "One edit"


def test_camel_case_paths_are_accepted_and_canonicalised():
    doc = apply_edits(
        _doc(),
        [{"op": "set", "path": "/steps/a/variantOf", "value": "b"}],
        by="user:t",
    )
    assert doc.steps[0].variant_of == "b"
    assert doc.steps[0].locks[0].path == "/variant_of"
