"""Residuals from PR #11's adversarial review, tracked as issue #12.

Each test below covers one item from the issue. Items declined (documented
instead of fixed, or explicitly deferred) are not tested here — see the issue
for the one-line reasons.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from paces.model import Lock


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
