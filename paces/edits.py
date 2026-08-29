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

Path rules (each earned by an adversarial review, PR #11):

- List items are addressed **by id first** (``/steps/b4/name``); an ASCII
  digit segment is an index only when no item carries that id. Ids are
  stabler across regenerations — always prefer them.
- Field segments accept the wire's camelCase or Python's snake_case; recorded
  ``Lock.path``\\ s are canonicalised to snake_case and to id-form where an
  unambiguous id exists.
- On merge, a lock is re-applied by **matching list items structurally**
  (id; a span's exact ``(source, role, start)``, falling back to
  ``(source, role)`` only for singleton groups; an artifact's ``uri``) —
  never by bare position, not even within a group, because regeneration
  reorders lists and a positional write would land on the wrong item. When
  no confident match exists, nothing is written and the lock survives as
  the record. Scalar list items (tags) have no identity besides their
  value, so an edited scalar cannot be re-found after regeneration — the
  edit does not survive; only its lock record does.
- ``attrs`` bags merge committed-over-fresh per key: they are user/renderer
  data that analysis does not produce, so regeneration never wins there.

Not yet recorded anywhere: the fresh values a merge *rejects*
(``Origin.value_digest`` and the op-log arrive with the evidence layer,
issue #4).
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from paces.model import Lock, StepDocument

#: The ops v1 supports. ``append``/``delete`` arrive at the third real need
#: (they require tombstone semantics in the merge — see issue #5).
SUPPORTED_OPS = ("set",)

_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")

#: Structural identity keys for list items that carry no ``id``.
_SPAN_KEYS = frozenset({"source", "role", "start"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _snake(key: str) -> str:
    return _CAMEL_BOUNDARY.sub("_", key).lower()


def _split_path(path: str) -> list[str]:
    if not isinstance(path, str) or not path.startswith("/") or path == "/":
        raise ValueError(
            f"path must be a JSON-pointer-style path like '/steps/b4/name'; "
            f"got {path!r}"
        )
    return path[1:].split("/")


def _is_index(segment: str) -> bool:
    return segment.isascii() and segment.isdigit()


def _index_of(items: list, segment: str, *, at: str) -> int:
    """Resolve a list segment: an item id first; an ASCII digit index second.

    Id-first because ids are the stable address — and because a segmenter can
    legitimately mint all-digit ids (chapters titled "1", "2", ...), which
    index-first would silently misroute.
    """
    for i, item in enumerate(items):
        if isinstance(item, Mapping) and item.get("id") == segment:
            return i
    if _is_index(segment):
        index = int(segment)
        if index < len(items):
            return index
        raise ValueError(f"{at}: index {index} out of range (len {len(items)})")
    ids = [item.get("id") for item in items if isinstance(item, Mapping)]
    raise ValueError(f"{at}: no item with id {segment!r} (have: {ids})")


def _key_of(container: Mapping, segment: str, *, at: str) -> str:
    """Resolve a field segment; accepts wire camelCase, returns snake_case."""
    if segment in container:
        return segment
    snake = _snake(segment)
    if snake in container:
        return snake
    raise ValueError(f"{at}: no field {segment!r} (have: {sorted(container)})")


def _resolve_parent(root: Any, segments: list[str], *, path: str):
    """The parent container of the leaf, and the resolved leaf key."""
    node = root
    for i, segment in enumerate(segments[:-1]):
        at = "/" + "/".join(segments[: i + 1])
        if isinstance(node, list):
            node = node[_index_of(node, segment, at=at)]
        elif isinstance(node, Mapping):
            node = node[_key_of(node, segment, at=at)]
        else:
            raise ValueError(f"{at}: cannot descend into {type(node).__name__}")
    leaf = segments[-1]
    if isinstance(node, list):
        return node, _index_of(node, leaf, at=path)
    if isinstance(node, Mapping):
        return node, _key_of(node, leaf, at=path)
    raise ValueError(f"{path}: cannot set into {type(node).__name__}")


def _canonical_segments(root: Any, segments: list[str], *, path: str) -> list[str]:
    """The stablest spelling of a path: snake_case fields; list items by id
    when one exists unambiguously in that list, by index otherwise."""
    node, out = root, []
    for i, segment in enumerate(segments):
        at = "/" + "/".join(segments[: i + 1])
        if isinstance(node, list):
            index = _index_of(node, segment, at=at)
            item = node[index]
            item_id = item.get("id") if isinstance(item, Mapping) else None
            ids = [x.get("id") for x in node if isinstance(x, Mapping)]
            unambiguous = item_id is not None and ids.count(item_id) == 1
            out.append(str(item_id) if unambiguous else str(index))
            node = item
        elif isinstance(node, Mapping):
            key = _key_of(node, segment, at=at)
            out.append(key)
            node = node[key]
        else:
            raise ValueError(f"{at}: cannot descend into {type(node).__name__}")
    return out


def _lock_site(dump: dict, segments: list[str]) -> tuple[dict, str]:
    """The node that records the lock, and the lock path relative to it.

    Structural, not heuristic: only paths of the form
    ``steps/<item>(/steps/<item>)*/<field>...`` are owned by the innermost
    step; everything else — ``attrs`` contents included, whatever shape the
    user's data takes — locks on the document itself.
    """
    site, node, depth, i = dump, dump, 0, 0
    while i + 2 <= len(segments) - 1 and segments[i] == "steps":
        items = node["steps"]
        at = "/" + "/".join(segments[: i + 2])
        node = items[_index_of(items, segments[i + 1], at=at)]
        site, depth = node, i + 2
        i += 2
    return site, "/" + "/".join(segments[depth:])


def apply_edits(
    doc: StepDocument,
    edits: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    by: str,
    at: str | None = None,
    reason: str | None = None,
) -> StepDocument:
    """Apply typed patches to a document, recording a Lock per edit.

    Each edit is ``{"op": "set", "path": ..., "value": ...}`` (a single edit
    may be passed bare). All edits are validated together — an invalid edit
    means NO edit is applied. Editing an already-locked path replaces the
    lock (``was`` becomes the value this edit overwrote, keeping the last
    edit reversible).

    >>> from paces.model import Measure, Step, StepDocument
    >>> doc = StepDocument(id='g', title='G', steps=[
    ...     Step(id='a', name='old', duration=Measure(value='2', unit='eight'))])
    >>> edited = apply_edits(doc, [{'op': 'set', 'path': '/steps/a/name',
    ...                             'value': 'new'}], by='user:thor')
    >>> edited.steps[0].name, edited.steps[0].locks[0].was
    ('new', 'old')
    """
    if isinstance(edits, Mapping):
        edits = [edits]
    timestamp = at or _now_iso()
    dump = doc.model_dump(mode="python", by_alias=False)
    for i, edit in enumerate(edits):
        if not isinstance(edit, Mapping):
            raise ValueError(
                f"edits[{i}]: expected a mapping like "
                f"{{'op': 'set', 'path': ..., 'value': ...}}; "
                f"got {type(edit).__name__}"
            )
        op = edit.get("op")
        if op not in SUPPORTED_OPS:
            raise ValueError(
                f"edits[{i}]: unsupported op {op!r} (v1 supports: "
                f"{', '.join(SUPPORTED_OPS)})"
            )
        raw_path = edit.get("path", "")
        segments = _canonical_segments(dump, _split_path(raw_path), path=raw_path)
        container, key = _resolve_parent(dump, segments, path=raw_path)
        # The lock site must resolve BEFORE the mutation: an edit may change
        # the very value a segment addresses (renaming a step's id).
        site, relative = _lock_site(dump, segments)
        was = copy.deepcopy(container[key])
        container[key] = copy.deepcopy(edit["value"])
        locks = site.setdefault("locks", [])
        locks[:] = [lock for lock in locks if lock.get("path") != relative]
        locks.append(
            Lock(path=relative, by=by, at=timestamp, was=was, reason=reason).model_dump(
                mode="python"
            )
        )
    return StepDocument.model_validate(dump)


# ── merge: locked values win, matched structurally ──────────────────────────


def _match_index(citems: list, cidx: int, fitems: list) -> int | None:
    """The fresh index corresponding to committed item *cidx* — never bare
    position on a reorderable list. ``None`` means no confident match."""
    citem = citems[cidx]
    if isinstance(citem, Mapping):
        cid = citem.get("id")
        if cid is not None:
            for j, fitem in enumerate(fitems):
                if isinstance(fitem, Mapping) and fitem.get("id") == cid:
                    return j
            return None
        if _SPAN_KEYS <= set(citem):  # a SourceSpan
            # Anchor on the exact (source, role, start) triple first — a
            # reorder keeps starts, so this survives insertion AND intra-group
            # shuffling. Only when that fails, fall back to (source, role),
            # and ONLY when that group is a singleton on both sides: an
            # ordinal within a group is bare position wearing a costume
            # (adversarial re-review of PR #11). Anything else declines.
            def _triple(item):
                return (item.get("source"), item.get("role"), item.get("start"))

            def _pair(item):
                return (item.get("source"), item.get("role"))

            triple_hits = [
                j
                for j, fitem in enumerate(fitems)
                if isinstance(fitem, Mapping) and _triple(fitem) == _triple(citem)
            ]
            if len(triple_hits) == 1:
                return triple_hits[0]
            committed_group = [
                x for x in citems if isinstance(x, Mapping) and _pair(x) == _pair(citem)
            ]
            fresh_group = [
                j
                for j, fitem in enumerate(fitems)
                if isinstance(fitem, Mapping) and _pair(fitem) == _pair(citem)
            ]
            if len(committed_group) == 1 and len(fresh_group) == 1:
                return fresh_group[0]
            return None
        if "uri" in citem:  # an ArtifactRef: the uri is its identity
            for j, fitem in enumerate(fitems):
                if isinstance(fitem, Mapping) and fitem.get("uri") == citem["uri"]:
                    return j
            return None
        return None
    for j, fitem in enumerate(fitems):  # scalar: first equal value
        if fitem == citem:
            return j
    return None


def _apply_lock(fresh: Any, committed: Any, path: str) -> bool:
    """Re-apply the committed value at *path* onto *fresh*.

    Walks both structures in parallel, matching list items structurally.
    Returns False — writing nothing — when the path cannot be confidently
    resolved in the fresh structure; the lock then survives as the record.
    """
    try:
        segments = _split_path(path)
        cnode, fnode = committed, fresh
        for i, segment in enumerate(segments[:-1]):
            at = "/" + "/".join(segments[: i + 1])
            if isinstance(cnode, list):
                if not isinstance(fnode, list):
                    return False
                cidx = _index_of(cnode, segment, at=at)
                fidx = _match_index(cnode, cidx, fnode)
                if fidx is None:
                    return False
                cnode, fnode = cnode[cidx], fnode[fidx]
            elif isinstance(cnode, Mapping):
                key = _key_of(cnode, segment, at=at)
                if not isinstance(fnode, Mapping) or key not in fnode:
                    return False
                cnode, fnode = cnode[key], fnode[key]
            else:
                return False
        leaf = segments[-1]
        if isinstance(cnode, list):
            if not isinstance(fnode, list):
                return False
            cidx = _index_of(cnode, leaf, at=path)
            fidx = _match_index(cnode, cidx, fnode)
            if fidx is None:
                return False
            fnode[fidx] = copy.deepcopy(cnode[cidx])
            return True
        if isinstance(cnode, Mapping):
            key = _key_of(cnode, leaf, at=path)
            if not isinstance(fnode, Mapping) or key not in fnode:
                return False
            fnode[key] = copy.deepcopy(cnode[key])
            return True
        return False
    except ValueError:
        return False


def _value_at(dump: Mapping, path: str) -> Any:
    segments = _split_path(path)
    container, key = _resolve_parent(dict(dump), segments, path=path)
    return copy.deepcopy(container[key])


def _is_protected(step_dump: Mapping) -> bool:
    origin = step_dump.get("origin") or {}
    generated_by = origin.get("generated_by") or ""
    return bool(step_dump.get("locks")) or generated_by.startswith("user:")


def _merged_attrs(committed: Mapping, fresh: Mapping) -> dict:
    """attrs are user/renderer data analysis does not produce: committed wins
    per key, fresh-only keys are kept."""
    return {**copy.deepcopy(dict(fresh)), **copy.deepcopy(dict(committed))}


def _merge_steps(committed: list[dict], fresh: list[dict]) -> list[dict]:
    committed_by_id: dict[str, dict] = {}
    for step in committed:  # first occurrence wins, matching apply_edits
        committed_by_id.setdefault(step["id"], step)
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
        out["attrs"] = _merged_attrs(
            committed_step.get("attrs", {}), fresh_step.get("attrs", {})
        )
        out["locks"] = copy.deepcopy(committed_step.get("locks", []))
        for lock in out["locks"]:
            _apply_lock(out, committed_step, lock["path"])
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
        for earlier in reversed(committed[:position]):
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
       every step matched by id, recursively — re-applied by structural
       match, never by bare position (a reorder must not land a locked value
       on the wrong item).
    2. Everything else takes the fresh value (regeneration is allowed to
       improve what nobody protected) — except ``attrs``, where committed
       wins per key.
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
    out["attrs"] = _merged_attrs(committed_dump.get("attrs", {}), out.get("attrs", {}))
    out["locks"] = copy.deepcopy(committed_dump.get("locks", []))
    for lock in out["locks"]:
        _apply_lock(out, committed_dump, lock["path"])
    return StepDocument.model_validate(out)
