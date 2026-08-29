"""Document-layer edit protection: typed patches write Locks; regeneration
merges without eating edits.

The POC's single most expensive failure was regeneration destroying hand
edits (``docs/07-annotation-model.md §1.3``). The remedy has two halves, both
here and both store-independent (``docs/07 §6.4`` steps 4–6):

- :func:`apply_edits` — edits are **typed patches**
  (``{"op": "set", "path": "/steps/b4/name", "value": ...}``), validated
  before application, and every edit writes a :class:`~paces.model.Lock` with
  the pre-edit value, so every edit is reversible and every protected path is
  explicit.
- :func:`merge_regenerated` — a fresh analysis projection merged against the
  committed document: locked paths keep the committed value, everything else
  takes the fresh value, and committed-only steps that carry protection
  survive.

Paths address list items by index (``/steps/3/name``) or, for lists whose
items carry an ``id`` (steps, sources, cues, questions), by that id
(``/steps/b4/spans/0/caption``) — ids are stabler across regenerations, so
prefer them.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from paces.model import Lock, StepDocument

#: The ops v1 supports. ``append``/``delete`` arrive at the third real need
#: (they require tombstone semantics in the merge — see issue #5).
SUPPORTED_OPS = ("set",)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _split_path(path: str) -> list[str]:
    if not path.startswith("/") or path == "/":
        raise ValueError(
            f"path must be a JSON-pointer-style path like '/steps/b4/name'; "
            f"got {path!r}"
        )
    return path[1:].split("/")


def _index_of(items: list, segment: str, *, at: str) -> int:
    """Resolve a list segment: a digit is an index, otherwise an item id."""
    if segment.isdigit():
        index = int(segment)
        if index >= len(items):
            raise ValueError(f"{at}: index {index} out of range (len {len(items)})")
        return index
    for i, item in enumerate(items):
        if isinstance(item, Mapping) and item.get("id") == segment:
            return i
    ids = [item.get("id") for item in items if isinstance(item, Mapping)]
    raise ValueError(f"{at}: no item with id {segment!r} (have: {ids})")


def _resolve(root: dict, segments: list[str]) -> tuple[Any, list[str | int]]:
    """Walk *segments* from *root*; return (parent container, resolved keys)."""
    node: Any = root
    resolved: list[str | int] = []
    for i, segment in enumerate(segments[:-1]):
        at = "/" + "/".join(segments[: i + 1])
        if isinstance(node, list):
            key: str | int = _index_of(node, segment, at=at)
        elif isinstance(node, Mapping):
            if segment not in node:
                raise ValueError(f"{at}: no field {segment!r}")
            key = segment
        else:
            raise ValueError(f"{at}: cannot descend into {type(node).__name__}")
        resolved.append(key)
        node = node[key]
    return node, resolved


def _leaf_key(container: Any, segment: str, *, path: str) -> str | int:
    if isinstance(container, list):
        return _index_of(container, segment, at=path)
    if isinstance(container, Mapping):
        if segment not in container:
            raise ValueError(
                f"{path}: no field {segment!r} (have: {sorted(container)})"
            )
        return segment
    raise ValueError(f"{path}: cannot set into {type(container).__name__}")


def _lock_site(dump: dict, segments: list[str]) -> tuple[dict, str]:
    """The node that records the lock, and the lock path relative to it.

    The nearest enclosing step owns the lock (its locks travel with it through
    a merge); anything above the steps list locks on the document itself.
    """
    node: Any = dump
    site, site_depth = dump, 0
    for i, segment in enumerate(segments[:-1]):
        if isinstance(node, list):
            node = node[_index_of(node, segment, at="/" + "/".join(segments[: i + 1]))]
            if (
                isinstance(node, Mapping)
                and "duration" in node
                and "spans" in node  # a Step dump
            ):
                site, site_depth = node, i + 1
        else:
            node = node[segment]
    relative = "/" + "/".join(segments[site_depth:])
    return site, relative


def apply_edits(
    doc: StepDocument,
    edits: Sequence[Mapping[str, Any]],
    *,
    by: str,
    at: str | None = None,
    reason: str | None = None,
) -> StepDocument:
    """Apply typed patches to a document, recording a Lock per edit.

    Each edit is ``{"op": "set", "path": ..., "value": ...}``. All edits are
    validated together — an invalid edit means NO edit is applied. Editing an
    already-locked path replaces the lock (``was`` becomes the value this edit
    overwrote, keeping the last edit reversible).

    >>> from paces.model import Measure, Step, StepDocument
    >>> doc = StepDocument(id='g', title='G', steps=[
    ...     Step(id='a', name='old', duration=Measure(value='2', unit='eight'))])
    >>> edited = apply_edits(doc, [{'op': 'set', 'path': '/steps/a/name',
    ...                             'value': 'new'}], by='user:thor')
    >>> edited.steps[0].name, edited.steps[0].locks[0].was
    ('new', 'old')
    """
    timestamp = at or _now_iso()
    dump = doc.model_dump(mode="python", by_alias=False)
    for i, edit in enumerate(edits):
        op = edit.get("op")
        if op not in SUPPORTED_OPS:
            raise ValueError(
                f"edits[{i}]: unsupported op {op!r} (v1 supports: "
                f"{', '.join(SUPPORTED_OPS)})"
            )
        segments = _split_path(edit["path"])
        container, _ = _resolve(dump, segments)
        key = _leaf_key(container, segments[-1], path=edit["path"])
        was = copy.deepcopy(container[key])
        container[key] = copy.deepcopy(edit["value"])

        site, relative = _lock_site(dump, segments)
        locks = site.setdefault("locks", [])
        locks[:] = [lock for lock in locks if lock.get("path") != relative]
        locks.append(
            Lock(path=relative, by=by, at=timestamp, was=was, reason=reason).model_dump(
                mode="python"
            )
        )
    return StepDocument.model_validate(dump)


def _value_at(dump: Mapping, path: str) -> Any:
    segments = _split_path(path)
    container, _ = _resolve(dict(dump), segments)
    key = _leaf_key(container, segments[-1], path=path)
    return copy.deepcopy(container[key])


def _set_at(dump: dict, path: str, value: Any) -> None:
    segments = _split_path(path)
    container, _ = _resolve(dump, segments)
    key = _leaf_key(container, segments[-1], path=path)
    container[key] = copy.deepcopy(value)


def _is_protected(step_dump: Mapping) -> bool:
    origin = step_dump.get("origin") or {}
    generated_by = origin.get("generated_by") or ""
    return bool(step_dump.get("locks")) or generated_by.startswith("user:")


def _merge_steps(committed: list[dict], fresh: list[dict]) -> list[dict]:
    committed_by_id = {step["id"]: step for step in committed}
    fresh_ids = {step["id"] for step in fresh}
    merged: list[dict] = []
    for fresh_step in fresh:
        committed_step = committed_by_id.get(fresh_step["id"])
        if committed_step is None:
            merged.append(copy.deepcopy(fresh_step))
            continue
        out = copy.deepcopy(fresh_step)
        out["steps"] = _merge_steps(
            committed_step.get("steps", []), fresh_step.get("steps", [])
        )
        out["locks"] = copy.deepcopy(committed_step.get("locks", []))
        for lock in out["locks"]:
            try:
                _set_at(out, lock["path"], _value_at(committed_step, lock["path"]))
            except ValueError:
                # The locked path no longer exists in the fresh structure
                # (e.g. a span index gone). Keep the lock as the record; the
                # value it protected is in lock['was'] and the committed doc.
                continue
        merged.append(out)

    # Committed-only steps survive when they carry protection (locks anywhere
    # in their subtree, or a user origin); analysis leftovers are superseded.
    for position, committed_step in enumerate(committed):
        if committed_step["id"] in fresh_ids:
            continue
        subtree_protected = _is_protected(committed_step) or any(
            _is_protected(child) for child in _walk_dumps(committed_step)
        )
        if not subtree_protected:
            continue
        insert_at = len(merged)
        for j, earlier in enumerate(reversed(committed[:position])):
            index = _find_index(merged, earlier["id"])
            if index is not None:
                insert_at = index + 1
                break
        else:
            insert_at = 0 if position == 0 else len(merged)
        merged.insert(insert_at, copy.deepcopy(committed_step))
    return merged


def _walk_dumps(step_dump: Mapping):
    for child in step_dump.get("steps", []):
        yield child
        yield from _walk_dumps(child)


def _find_index(steps: list[dict], step_id: str) -> int | None:
    for i, step in enumerate(steps):
        if step["id"] == step_id:
            return i
    return None


def _union_by_id(committed: list[dict], fresh: list[dict]) -> list[dict]:
    """Fresh entries win for shared ids; committed-only entries are kept."""
    fresh_ids = {item["id"] for item in fresh}
    return copy.deepcopy(fresh) + [
        copy.deepcopy(item) for item in committed if item["id"] not in fresh_ids
    ]


def merge_regenerated(committed: StepDocument, fresh: StepDocument) -> StepDocument:
    """Merge a fresh analysis projection against the committed document.

    The rules, in order of authority:

    1. **Locked paths keep the committed value** — on the document and on
       every step matched by id, recursively.
    2. Everything else takes the fresh value (regeneration is allowed to
       improve what nobody protected).
    3. Committed-only steps survive when protected (locks in their subtree or
       a ``user:`` origin); unprotected ones are superseded analysis output.
    4. Cues, questions and sources are unioned by id (fresh wins on shared
       ids) — analysis rarely regenerates them, and dropping committed
       content silently is the failure this module exists to prevent.

    Edits made through :func:`apply_edits` are always locked, so "hand edit"
    and "protected" coincide by construction; edits made by hand-editing the
    JSON without locks are, deliberately, not protected.
    """
    committed_dump = committed.model_dump(mode="python", by_alias=False)
    out = fresh.model_dump(mode="python", by_alias=False)
    out["steps"] = _merge_steps(committed_dump["steps"], out["steps"])
    for key in ("cues", "questions", "sources"):
        out[key] = _union_by_id(committed_dump[key], out[key])
    out["locks"] = copy.deepcopy(committed_dump.get("locks", []))
    for lock in out["locks"]:
        try:
            _set_at(out, lock["path"], _value_at(committed_dump, lock["path"]))
        except ValueError:
            continue
    return StepDocument.model_validate(out)
