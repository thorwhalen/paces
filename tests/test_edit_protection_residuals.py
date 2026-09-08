"""Residuals from PR #11's adversarial review, tracked as issue #12.

Each test below covers one item from the issue. Items declined (documented
instead of fixed, or explicitly deferred) are not tested here — see the issue
for the one-line reasons.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from paces.edits import apply_edits, merge_regenerated
from paces.model import (
    Lock,
    Measure,
    Source,
    SourceSpan,
    Step,
    StepDocument,
    validate_document,
)


def _doc(**overrides) -> StepDocument:
    fields = dict(
        id="guide",
        title="A guide",
        steps=[Step(id="a", name="Step A", duration=Measure(value="2", unit="eight"))],
    )
    fields.update(overrides)
    return StepDocument(**fields)


# ── Lock.by / Lock.at validation ─────────────────────────────────────────────


def test_lock_by_rejects_empty_string():
    with pytest.raises(ValidationError):
        Lock(path="/name", by="", at="2026-08-30T00:00:00Z")


def test_lock_by_rejects_whitespace_only():
    with pytest.raises(ValidationError):
        Lock(path="/name", by="   ", at="2026-08-30T00:00:00Z")


def test_lock_at_rejects_junk_timestamp():
    with pytest.raises(ValidationError):
        Lock(path="/name", by="user:thor", at="not-a-timestamp")


def test_lock_at_rejects_non_utc_offset():
    with pytest.raises(ValidationError):
        Lock(path="/name", by="user:thor", at="2026-08-30T00:00:00+02:00")


def test_lock_at_accepts_the_format_edits_writes():
    Lock(path="/name", by="user:thor", at="2026-08-30T00:00:00Z")


# ── Lock.was float leak (validate_document) ──────────────────────────────────


def test_validate_document_flags_float_leaked_into_lock_was():
    doc = _doc(
        steps=[
            Step(
                id="a",
                name="Step A",
                duration=Measure(value="2", unit="eight"),
                locks=[
                    Lock(
                        path="/name", by="user:thor", at="2026-08-30T00:00:00Z", was=1.5
                    )
                ],
            )
        ]
    )
    issues = validate_document(doc)
    assert any("float" in issue for issue in issues)


def test_validate_document_flags_float_leaked_into_attrs():
    doc = _doc(
        steps=[
            Step(
                id="a",
                name="Step A",
                duration=Measure(value="2", unit="eight"),
                attrs={"render.web": {"hue": 0.5}},
            )
        ]
    )
    issues = validate_document(doc)
    assert any("float" in issue for issue in issues)


def test_validate_document_does_not_flag_the_typed_confidence_float():
    doc = _doc(
        steps=[
            Step(
                id="a",
                name="Step A",
                duration=Measure(value="2", unit="eight"),
                spans=[SourceSpan(source="vid", start="10", confidence=0.8)],
            )
        ]
    )
    issues = validate_document(doc)
    assert not any("float" in issue for issue in issues)


def test_validate_document_does_not_flag_a_lock_was_holding_the_old_confidence():
    # apply_edits itself writes exactly this: a Lock.was carrying the
    # pre-edit value of a schema-typed float field (SourceSpan.confidence).
    doc = _doc(
        steps=[
            Step(
                id="a",
                name="Step A",
                duration=Measure(value="2", unit="eight"),
                spans=[SourceSpan(source="vid", start="10", confidence=0.8)],
            )
        ]
    )
    edited = apply_edits(
        doc,
        [{"op": "set", "path": "/steps/a/spans/0/confidence", "value": 0.9}],
        by="user:thor",
    )
    issues = validate_document(edited)
    assert not any("float" in issue for issue in issues)


def test_validate_document_clean_document_has_no_float_issues():
    assert validate_document(_doc()) == []


# ── rename onto an existing id is refused at edit time ───────────────────────


def _two_step_doc(**overrides) -> StepDocument:
    fields = dict(
        id="guide",
        title="A guide",
        sources=[Source(id="vid", kind="video", uri="https://example.com/v")],
        steps=[
            Step(
                id="a",
                name="Step A",
                duration=Measure(value="2", unit="eight"),
                spans=[SourceSpan(source="vid", start="10")],
            ),
            Step(
                id="b",
                name="Step B",
                duration=Measure(value="2", unit="eight"),
                spans=[SourceSpan(source="vid", start="20")],
            ),
        ],
    )
    fields.update(overrides)
    return StepDocument(**fields)


def test_apply_edits_refuses_rename_onto_an_existing_id():
    with pytest.raises(ValueError, match="already used"):
        apply_edits(
            _two_step_doc(),
            [{"op": "set", "path": "/steps/a/id", "value": "b"}],
            by="user:thor",
        )


def test_apply_edits_allows_rename_onto_a_free_id():
    doc = apply_edits(
        _two_step_doc(),
        [{"op": "set", "path": "/steps/a/id", "value": "a2"}],
        by="user:thor",
    )
    assert [s.id for s in doc.steps] == ["a2", "b"]


def test_apply_edits_allows_renaming_id_to_itself():
    doc = apply_edits(
        _two_step_doc(),
        [{"op": "set", "path": "/steps/a/id", "value": "a"}],
        by="user:thor",
    )
    assert [s.id for s in doc.steps] == ["a", "b"]


def test_apply_edits_refuses_a_nested_rename_onto_a_top_level_id():
    doc = _two_step_doc(
        steps=[
            Step(
                id="a",
                name="Step A",
                duration=Measure(value="2", unit="eight"),
                steps=[
                    Step(id="c", name="Sub", duration=Measure(value="2", unit="eight"))
                ],
            ),
            Step(id="b", name="Step B", duration=Measure(value="2", unit="eight")),
        ]
    )
    # "b" isn't a sibling of "c" (it lives one level up) — the collision must
    # still be caught document-wide, matching validate_document's own scope.
    with pytest.raises(ValueError, match="already used"):
        apply_edits(
            doc,
            [{"op": "set", "path": "/steps/a/steps/c/id", "value": "b"}],
            by="user:thor",
        )


# ── merge after an id rename does not resurrect the old id ──────────────────


def test_merge_regenerated_does_not_resurrect_the_pre_rename_id():
    committed = apply_edits(
        _two_step_doc(),
        [{"op": "set", "path": "/steps/a/id", "value": "a2"}],
        by="user:thor",
    )
    # Analysis re-runs without knowledge of the rename: it still emits "a".
    fresh = _two_step_doc()
    merged = merge_regenerated(committed, fresh)
    assert [s.id for s in merged.steps] == ["a2", "b"]
    assert merged.steps[0].name == "Step A"


def test_merge_regenerated_does_not_double_match_when_fresh_has_both_ids():
    committed = apply_edits(
        _two_step_doc(),
        [{"op": "set", "path": "/steps/a/id", "value": "a2"}],
        by="user:thor",
    )
    # Fresh carries BOTH the old id and the already-renamed id (e.g. analysis
    # caught up and emitted "a2", but a stray "a" is also present) — the
    # renamed committed step must not be matched twice.
    fresh = _two_step_doc(
        steps=[
            Step(id="a", name="Step A", duration=Measure(value="2", unit="eight")),
            Step(id="a2", name="Step A", duration=Measure(value="2", unit="eight")),
            Step(id="b", name="Step B", duration=Measure(value="2", unit="eight")),
        ]
    )
    merged = merge_regenerated(committed, fresh)
    ids = [s.id for s in merged.steps]
    assert ids == ["a", "a2", "b"]
    assert len(ids) == len(set(ids))
    assert validate_document(merged) == []
