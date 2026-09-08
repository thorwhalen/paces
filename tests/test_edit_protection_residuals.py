"""Residuals from PR #11's adversarial review, tracked as issue #12.

Each test below covers one item from the issue. Items declined (documented
instead of fixed, or explicitly deferred) are not tested here — see the issue
for the one-line reasons.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from paces.model import Lock, Measure, SourceSpan, Step, StepDocument, validate_document


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


def test_validate_document_clean_document_has_no_float_issues():
    assert validate_document(_doc()) == []
