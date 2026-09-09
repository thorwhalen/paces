"""The evidence layer: persist analysis into a ``lacing`` store, project it back.

Two layers, one direction of flow (``docs/07 §6.0``). The committed
:class:`~paces.model.StepDocument` is the contract renderers read; the
machine evidence — the speech/music split, the metric grid, the beats, the
transcript, the step candidates, the derivation recipes and the lineage
between them — lives in a ``lacing`` store, and the document is a
*projection* of it. **The document is derivable from the store; the store is
not derivable from the document.**

Three functions::

    seg = segment(...)                                   # analysis
    write = to_store(seg, store=store, asset_id=asset)   # evidence  ← here
    doc = from_store(store, asset_id=asset)              # projection ← here
    dumps_document(doc) == dumps_document(write.document)

What crosses into the store, and what deliberately does not:

============================  ==========================================
crosses                       stays on the document
============================  ==========================================
sources, passes, the grid,    ``locks``, ``questions``, ``artifacts``,
beats, transcript words,      span ``excerpt`` windows
steps + their spans, cues,
derivation recipes
============================  ==========================================

The right column is not an omission. Those four are *document-layer*
records — a human edit, an open question, a built file, a hand-picked loop —
and ``docs/07 §6.0`` is explicit that nothing flows document → store.
:func:`from_store` therefore returns them empty, which is exactly what
:func:`paces.projection.to_document` emits, so the round trip is exact.

Three properties this module is built to hold, each with a test:

- **Deterministic identity.** An annotation's id is
  ``uuid5(PACES_NAMESPACE, f"{tier}\\n{evidence_key}")``, not a fresh
  ``uuid4`` plus a procedural adoption pass. ``docs/07 §6.4`` steps 1–3 then
  hold by construction: a re-derivation of the same evidence *is* the same
  id, so ``was_derived_from`` edges keep resolving and ``to_store`` is
  reproducible from a fresh store.
- **Idempotence, digest-gated.** A row whose
  :func:`lacing.annotation_value_digest` is unchanged is left *completely*
  alone — provenance included — so ``generated_at_time`` does not churn and
  freshness does not fire. A second :func:`to_store` of the same input
  writes nothing. The one exception is lineage: the value digest excludes
  provenance by design, so a row whose answer held but whose
  ``was_derived_from`` moved is rewritten (``StoreWrite.relinked``) with its
  ``generated_at_time`` preserved — otherwise a re-measured pass would leave
  the grid and its steps pointing at the previous run's inputs.
- **Re-derivation, not accumulation — for the guide's own rows.** A
  doc-scoped row this run superseded (a step that no longer exists, a cue
  that was dropped) is removed: `reelee`'s *"the graph is a set of nodes
  whose values are re-derivable, not an append-only log"*, and a stale one
  left behind would come back out of :func:`from_store` as a step nobody
  analysed. :data:`ASSET_SCOPED_TIERS` — the speech/music split, the beats,
  the transcript — are **never** pruned: they describe the asset, are shared
  by every guide over it, and deleting one out from under a sibling guide's
  ``was_derived_from`` would leave that guide pointing at nothing.
  ``prune=False`` opts out of the rest.
- **No floats across the boundary.** Every time crosses as
  ``RationalTime`` ticks at ``rate=`` (lacing non-negotiable #1);
  :meth:`RationalTime.from_seconds` raises rather than rounding, so a
  document carrying finer time than the rate can hold is a loud error with
  ``rate=`` as the answer. Reading back yields the canonical minimal decimal,
  so a hand-written ``"231.30"`` normalises to ``"231.3"``.

Intervals live on ``Annotation.reference`` and never in a body: these are
standoff annotations, and a body that carried its own times would be a
second, unindexed interval store.

Requires the ``[lacing]`` extra. ``import paces`` does not import this
module — the core stays pydantic-only (ADR-0004); ``paces.to_store`` and
``paces.from_store`` resolve it on first attribute access.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

try:  # pragma: no cover - the message is the point, not the branch
    from lacing import (
        DEFAULT_RATE,
        Annotation,
        MediaRef,
        Provenance,
        RationalTime,
        Tier,
        TierStereotype,
        TimeInterval,
        annotation_value_digest,
    )
except ImportError as error:  # pragma: no cover
    raise ImportError(
        "paces' evidence layer needs lacing: `pip install 'paces[lacing]'`. "
        "The rest of paces does not — the core is pydantic-only (ADR-0004)."
    ) from error

from paces.bodies import (
    BEAT_BODY_SCHEMA_URI,
    BEAT_TIER,
    CUE_BODY_SCHEMA_URI,
    CUE_TIER,
    DOC_BODY_SCHEMA_URI,
    DOC_TIER,
    GRID_BODY_SCHEMA_URI,
    GRID_TIER,
    PASS_BODY_SCHEMA_URI,
    PASS_TIER,
    RECIPE_BODY_SCHEMA_URI,
    RECIPE_TIER,
    SOURCE_BODY_SCHEMA_URI,
    SOURCE_TIER,
    STEP_BODY_SCHEMA_URI,
    STEP_TIER,
    SUB_STEP_TIER,
    WORD_BODY_SCHEMA_URI,
    WORD_TIER,
    GuideBeatBodyV1,
    GuideCueBodyV1,
    GuideDocBodyV1,
    GuideGridBodyV1,
    GuidePassBodyV1,
    GuideRecipeBodyV1,
    GuideSourceBodyV1,
    GuideStepBodyV1,
)
from paces.model import (
    SCHEMA_VERSION,
    Anchor,
    Cue,
    Measure,
    MetricGrid,
    Origin,
    Source,
    SourceSpan,
    Step,
    StepDocument,
)
from paces.projection import to_document
from paces.segmenters import Segmentation

#: The namespace every paces annotation id is derived under. Derived from the
#: repository URL rather than typed as a literal, so it is reproducible from
#: something a reader can check.
PACES_NAMESPACE = uuid5(NAMESPACE_URL, "https://github.com/thorwhalen/paces")

#: Default ``provenance.was_generated_by`` for rows that are not a step's own
#: (a step's carries its ``Origin.generated_by`` instead).
DFLT_GENERATED_BY = "processor:paces.to_store"

#: Default ``provenance.was_attributed_to``.
DFLT_ATTRIBUTED_TO = "paces"

#: The tiers this module writes, with the ELAN stereotypes of ``docs/07 §6.3``.
#: Registered on the store by :func:`register_tiers`, which :func:`to_store`
#: calls — a store that cannot hold tiers (the Protocol makes them optional)
#: is used without them rather than refused.
TIERS: tuple[Tier, ...] = (
    Tier(DOC_TIER),
    Tier(SOURCE_TIER),
    Tier(PASS_TIER),
    Tier(GRID_TIER),
    Tier(BEAT_TIER),
    Tier(WORD_TIER),
    Tier(STEP_TIER),
    Tier(SUB_STEP_TIER, stereotype=TierStereotype.INCLUDED_IN, parent=STEP_TIER),
    Tier(CUE_TIER, stereotype=TierStereotype.INCLUDED_IN, parent=STEP_TIER),
    Tier(
        RECIPE_TIER,
        stereotype=TierStereotype.SYMBOLIC_ASSOCIATION,
        parent=STEP_TIER,
    ),
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


# ── time at the boundary ────────────────────────────────────────────────────


def _ticks(value: str, *, rate: int) -> RationalTime:
    """A decimal-string second count as exact ticks. Lossy input raises."""
    return RationalTime.from_seconds(value, rate)


def _decimal(time: RationalTime) -> str:
    """The canonical minimal decimal string for *time*.

    Exact: the tick rate's denominator is factored into 2s and 5s and the
    numerator scaled by the larger power of ten, so nothing is rounded. A
    rate whose denominator survives that (a third of a second) has no finite
    decimal and says so rather than rounding into the document.

    >>> _decimal(RationalTime.from_seconds('51.2', 24000))
    '51.2'
    >>> _decimal(RationalTime.from_seconds('72', 24000))
    '72'
    """
    fraction = time.to_fraction()
    numerator, denominator = fraction.numerator, fraction.denominator
    rest, twos, fives = denominator, 0, 0
    while rest % 2 == 0:
        rest //= 2
        twos += 1
    while rest % 5 == 0:
        rest //= 5
        fives += 1
    if rest != 1:
        raise ValueError(
            f"{time!r} is {fraction} seconds, which has no finite decimal form; "
            "the document's wire is decimal strings, so this tick rate cannot "
            "be projected without rounding"
        )
    places = max(twos, fives)
    scaled = numerator * 10**places // denominator
    sign = "-" if scaled < 0 else ""
    digits = str(abs(scaled)).rjust(places + 1, "0")
    if places == 0:
        return sign + digits
    return sign + f"{digits[:-places]}.{digits[-places:]}".rstrip("0").rstrip(".")


def _interval(start: str, end: str | None, *, rate: int) -> TimeInterval:
    """The half-open span for a document span. ``end=None`` → a point."""
    begin = _ticks(start, rate=rate)
    return TimeInterval(begin, begin if end is None else _ticks(end, rate=rate))


def _point(seconds: str | None, *, rate: int) -> TimeInterval:
    """A point interval, at *seconds* or at tick 0 when there is nothing better."""
    at = RationalTime.zero(rate) if seconds is None else _ticks(seconds, rate=rate)
    return TimeInterval.point(at)


def _asset_lineage(asset_id: str) -> list[str]:
    """The asset as a ``was_derived_from`` ref, when it is one.

    ``Provenance`` accepts only a bare 64-hex SHA-256 as an artifact ref
    (``lacing.model.AssetId``). A ``MediaRef.asset_id`` is free-form, so a
    project keyed by a readable name still works — it just contributes no
    lineage edge, rather than raising.
    """
    return [asset_id] if _HEX64.match(asset_id) else []


# ── writing ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class StoreWrite:
    """What :func:`to_store` did, and the document it projects to.

    ``document`` is the projection with its evidence back-references filled
    in: every :class:`~paces.model.Origin` carries the ``annotation_id`` and
    ``value_digest`` of the row it came from. That is the document
    :func:`from_store` reproduces byte for byte.
    """

    document: StepDocument
    written: int  # rows that did not exist
    updated: int  # rows whose value digest changed
    unchanged: int  # rows left completely alone — the idempotence count
    relinked: int  # rows whose value held but whose upstream moved
    removed: int  # rows this re-derivation superseded and dropped
    annotation_ids: tuple[str, ...]  # every row touched, in write order

    @property
    def total(self) -> int:
        return self.written + self.updated + self.unchanged + self.relinked


class CollidingEvidenceKey(ValueError):
    """Two rows in one run would derive the same annotation id."""


#: The provenance fields that say where a row came *from*. Compared on every
#: digest-gated skip, because ``annotation_value_digest`` deliberately excludes
#: provenance entirely (``lacing/digest.py``'s ``VALUE_FIELDS``): a row can keep
#: its exact value while the thing it was derived from moves underneath it.
_LINEAGE_FIELDS = (
    "was_generated_by",
    "was_attributed_to",
    "was_derived_from",
    "activity",
)


def _same_lineage(one: Provenance, other: Provenance) -> bool:
    """Do these two provenances agree on everything except *when*?"""
    return all(getattr(one, f) == getattr(other, f) for f in _LINEAGE_FIELDS)


class _Writer:
    """Digest-gated upsert over one store. Not part of the public surface."""

    def __init__(self, store, *, attributed_to: str, generated_at: RationalTime):
        self._store = store
        self._attributed_to = attributed_to
        self._generated_at = generated_at
        self._index: dict[UUID, Annotation] = {a.id: a for a in store.all()}
        self.written = 0
        self.updated = 0
        self.unchanged = 0
        self.relinked = 0
        self.removed = 0
        self.ids: list[str] = []
        self.touched: set[UUID] = set()

    def put(
        self,
        *,
        tier: str,
        key: str,
        interval: TimeInterval,
        asset_id: str,
        body: Mapping[str, Any],
        schema_uri: str,
        generated_by: str = DFLT_GENERATED_BY,
        derived_from: Iterable[Any] = (),
        confidence: float | None = None,
    ) -> tuple[UUID, str]:
        """Upsert one annotation; return its ``(id, value_digest)``."""
        annotation_id = uuid5(PACES_NAMESPACE, f"{tier}\n{key}")
        if annotation_id in self.touched:
            raise CollidingEvidenceKey(
                f"two {tier!r} rows in one run share the evidence key {key!r}. "
                "Derived ids make that a silent overwrite, so it is refused "
                "here instead. Two spans with the same (source, role, start) "
                "are the usual cause — `validate_document` reports the same "
                "collision on the document side."
            )
        candidate = Annotation(
            id=annotation_id,
            tier=tier,
            reference=MediaRef(asset_id=asset_id, interval=interval),
            body=dict(body),
            body_schema_uri=schema_uri,
            provenance=Provenance(
                was_generated_by=generated_by,
                was_attributed_to=self._attributed_to,
                was_derived_from=list(derived_from),
                generated_at_time=self._generated_at,
                activity="derive",
            ),
            confidence=confidence,
        )
        digest = annotation_value_digest(candidate)
        existing = self._index.get(annotation_id)
        if existing is not None:
            if annotation_value_digest(existing) == digest:
                if _same_lineage(existing.provenance, candidate.provenance):
                    self.unchanged += 1
                    self._record(annotation_id)
                    return annotation_id, digest
                # Same answer, different upstream. The value digest cannot see
                # this — provenance is excluded from it by design — so the
                # gate alone would leave the row pointing at the previous
                # run's inputs, which is the one thing the edge exists to
                # answer. Rewrite it, but keep ``generated_at_time``: the
                # value did not change, so freshness has no business firing.
                candidate = candidate.model_copy(
                    update={
                        "provenance": candidate.provenance.model_copy(
                            update={
                                "generated_at_time": (
                                    existing.provenance.generated_at_time
                                )
                            }
                        )
                    }
                )
                self._store.remove(annotation_id)
                self.relinked += 1
            else:
                self._store.remove(annotation_id)
                self.updated += 1
        else:
            self.written += 1
        self._store.add(candidate)
        self._index[annotation_id] = candidate
        self._record(annotation_id)
        return annotation_id, digest

    def _record(self, annotation_id: UUID) -> None:
        self.ids.append(str(annotation_id))
        self.touched.add(annotation_id)

    def prune(self, *, asset_id: str, doc_id: str, tiers: set[str]) -> None:
        """Drop rows on *tiers* this run superseded — a re-derivation, not a merge.

        Scoped three ways so it can only ever remove what this call is
        authoritative for: the asset it was given, the guide it was given,
        and the tiers this call actually wrote to. The ``doc_id`` test is a
        strict match on the body's own field, so a row that does not carry
        one is never pruned — see :data:`ASSET_SCOPED_TIERS` for why that
        matters.
        """
        for annotation in list(self._store.all()):
            if annotation.tier not in tiers or annotation.id in self.touched:
                continue
            if getattr(annotation.reference, "asset_id", None) != asset_id:
                continue
            if annotation.body.get("doc_id") != doc_id:
                continue
            self._store.remove(annotation.id)
            self._index.pop(annotation.id, None)
            self.removed += 1


def register_tiers(store) -> None:
    """Declare :data:`TIERS` on *store*, if it keeps tiers at all.

    ``IntervalAnnotationStore`` is a Protocol: a dict-shaped store that
    conforms structurally may not implement ``add_tier``. Tier metadata is
    descriptive, so its absence is not a reason to refuse the store.
    """
    add_tier = getattr(store, "add_tier", None)
    if add_tier is None:
        return
    for tier in TIERS:
        add_tier(tier)


def to_store(
    seg: Segmentation,
    *,
    store,
    asset_id: str,
    doc_id: str = "guide",
    title: str = "",
    source=None,
    domain: str = "generic",
    lang: str = "en",
    cues: Sequence[Cue | Mapping[str, Any]] = (),
    passes: Sequence[Sequence[Any]] = (),
    beats: Sequence[float | str] = (),
    transcript: Sequence[Mapping[str, Any] | Sequence[Any]] = (),
    recipes: Mapping[str, Any] | Any = None,
    detector: str = "",
    attributed_to: str = DFLT_ATTRIBUTED_TO,
    generated_at: RationalTime | None = None,
    prune: bool = True,
    rate: int = DEFAULT_RATE,
) -> StoreWrite:
    """Persist an analysis result into *store* as standoff annotations.

    *seg* is the analysis result; the projection arguments (*doc_id*,
    *title*, *source*, *domain*, *lang*) are :func:`paces.to_document`'s,
    unchanged. Everything else is evidence a segmenter does not carry on
    :class:`~paces.segmenters.Segmentation` but a pipeline may have:

    Args:
        store: Any ``lacing.IntervalAnnotationStore`` — ``MemoryStore()`` for
            tests, ``SqliteStore`` for a project sidecar, or a ``dol`` store
            that conforms. Injected, never constructed here: nothing in paces
            decides where a user's evidence lives.
        asset_id: Identity of the media every reference points into. A bare
            64-hex SHA-256 also becomes a lineage edge; any other string is
            a usable key that simply contributes no edge.
        cues: :class:`~paces.model.Cue` records (or their wire mappings).
            Cue detection is analysis (``docs/07 §6.3``), and a
            ``Segmentation`` has nowhere to carry it, so it arrives here.
        passes: ``(start_s, end_s, label)`` triples — exactly the shape of
            ``paces.measure.GridMeasurement.evidence['segments']``.
        beats: Measured beat times in seconds. Written **only** when given;
            beats are never synthesised from the grid (see the module
            docstring of ``paces/bodies/signal.py``).
        transcript: ``(start_s, end_s, text)`` triples or
            ``{'start', 'end', 'text', 'speaker'}`` mappings, landing on
            lacing's own ``word/v1``.
        recipes: A ``paces.derivation.RecipesFile``, or its ``entries``
            mapping of span address → recipe.
        detector: What produced *passes*, recorded on each pass row.
        generated_at: ``provenance.generated_at_time``; defaults to now.
            Unchanged rows keep the timestamp they already had, so this only
            stamps rows that actually changed.
        prune: Drop this guide's rows that this run superseded — a step that
            no longer exists, a cue that was dropped. On by default, because
            ``to_store`` is a **re-derivation** of the guide, not a merge
            into it: a stale row left behind would be resurrected by
            :func:`from_store` as a step nobody analysed. Scoped to this
            asset, this ``doc_id``, and the doc-scoped tiers this call
            actually wrote to; :data:`ASSET_SCOPED_TIERS` are never pruned.
            Pass ``False`` to accumulate instead.

    Note:
        ``doc_id`` names the guide, so changing it writes a **second** guide
        rather than renaming the first — the old one is still there, and a
        later ``from_store(store, asset_id=...)`` without a ``doc_id`` will
        say so by raising :class:`AmbiguousDocument`. Renaming a guide means
        writing the new one and dropping the old rows deliberately.

    Concurrency:
        Not safe against another writer on the same store. The digest index
        is snapshotted at entry and pruning reads-then-removes, both without
        a lock, so two concurrent ``to_store`` calls on one asset can delete
        each other's rows. Serialise them, or give each its own store.
        rate: Ticks per second for every interval. Raises rather than
            rounding if a time cannot be represented exactly.

    Returns:
        A :class:`StoreWrite` whose ``document`` is the projection with real
        ``Origin`` back-references.
    """
    document = to_document(
        seg, doc_id=doc_id, title=title, source=source, domain=domain, lang=lang
    )
    if cues:
        document = document.model_copy(
            update={"cues": [_as_cue(cue, rate=rate) for cue in cues]}
        )

    register_tiers(store)
    writer = _Writer(
        store,
        attributed_to=attributed_to,
        generated_at=generated_at or RationalTime.now(),
    )
    base = _asset_lineage(asset_id)
    put = _bind_put(writer, asset_id=asset_id)

    put(
        tier=DOC_TIER,
        key=f"doc:{doc_id}",
        interval=_point(None, rate=rate),
        body=GuideDocBodyV1(
            doc_id=document.id,
            title=document.title,
            lang=document.lang,
            domain=document.domain,
            schema_version=document.schema_version,
            credits=document.credits,
            method=seg.method,
            flags=list(seg.flags),
            attrs=dict(document.attrs),
        ).model_dump(mode="json"),
        schema_uri=DOC_BODY_SCHEMA_URI,
        derived_from=base,
    )

    for ordinal, src in enumerate(document.sources):
        put(
            tier=SOURCE_TIER,
            key=f"source:{doc_id}/{src.id}",
            interval=_point(None, rate=rate),
            body=GuideSourceBodyV1(
                doc_id=doc_id,
                ordinal=ordinal,
                source_id=src.id,
                kind=src.kind,
                uri=src.uri,
                asset_id=src.asset_id,
                duration_s=src.duration_s,
                title=src.title,
                attribution=src.attribution,
                rights=src.rights,
                attrs=dict(src.attrs),
            ).model_dump(mode="json"),
            schema_uri=SOURCE_BODY_SCHEMA_URI,
            derived_from=base,
        )

    written_passes = _write_passes(put, passes, detector=detector, base=base, rate=rate)
    grid_id = _write_grid(
        put,
        document.metric,
        doc_id=doc_id,
        method=seg.method,
        beat_count=len(beats) or None,
        span=_document_span(document),
        base=[*base, *(annotation_id for annotation_id, _, _ in written_passes)],
        rate=rate,
    )
    _write_beats(put, beats, base=[grid_id, *base] if grid_id else base, rate=rate)
    _write_transcript(put, transcript, base=base, rate=rate)

    step_base = [grid_id, *base] if grid_id else list(base)
    step_rows: dict[str, tuple[UUID, str]] = {}
    span_rows: dict[str, tuple[UUID, str]] = {}
    steps = _write_steps(
        put,
        document.steps,
        doc_id=doc_id,
        parent_id=None,
        parent_ann=None,
        base=step_base,
        passes=written_passes,
        rate=rate,
        step_rows=step_rows,
        span_rows=span_rows,
    )
    _write_cues(put, document.cues, doc_id=doc_id, step_rows=step_rows, rate=rate)
    _write_recipes(
        put, recipes, doc_id=doc_id, span_rows=span_rows, base=base, rate=rate
    )

    if prune:
        writer.prune(
            asset_id=asset_id,
            doc_id=doc_id,
            tiers=_prunable_tiers(cues=document.cues, recipes=recipes),
        )

    return StoreWrite(
        document=document.model_copy(update={"steps": steps}),
        written=writer.written,
        updated=writer.updated,
        unchanged=writer.unchanged,
        relinked=writer.relinked,
        removed=writer.removed,
        annotation_ids=tuple(writer.ids),
    )


#: Tiers whose rows describe **the asset**, not one guide over it: the
#: speech/music split of a video, its beat times, its transcript. Their bodies
#: carry no ``doc_id`` on purpose — two guides over the same video share one
#: transcript rather than duplicating it — and that is exactly why they are
#: never pruned. Pruning is per-guide, and a guide has no authority to delete
#: evidence another guide's annotations were derived from; deleting a pass row
#: out from under a sibling guide's ``was_derived_from`` would leave it
#: pointing at nothing. A re-measure that moves a boundary therefore *adds* a
#: row under a new content-derived key and leaves the old one standing, where
#: provenance still says which run used which.
ASSET_SCOPED_TIERS = frozenset({PASS_TIER, BEAT_TIER, WORD_TIER})

#: Tiers whose rows belong to exactly one guide (every body carries a
#: ``doc_id``) and which a re-derivation of that guide is therefore
#: authoritative over.
DOC_SCOPED_TIERS = frozenset(
    {DOC_TIER, SOURCE_TIER, GRID_TIER, STEP_TIER, SUB_STEP_TIER, CUE_TIER, RECIPE_TIER}
)

#: The doc-scoped tiers every ``to_store`` writes, because they are projected
#: from the ``Segmentation`` itself.
_ALWAYS_WRITTEN_TIERS = frozenset(
    {DOC_TIER, SOURCE_TIER, GRID_TIER, STEP_TIER, SUB_STEP_TIER}
)


def _prunable_tiers(*, cues, recipes) -> set[str]:
    """Which tiers this call may prune: the ones it is authoritative over.

    Doc-scoped only (:data:`ASSET_SCOPED_TIERS` explains the exclusion), and
    within those, a tier fed by a keyword is prunable only when that keyword
    was supplied: "a re-derivation replaces what it re-derives", and it
    re-derives what it was given.
    """
    tiers = set(_ALWAYS_WRITTEN_TIERS)
    for supplied, tier in ((cues, CUE_TIER), (recipes, RECIPE_TIER)):
        if supplied:
            tiers.add(tier)
    assert tiers <= DOC_SCOPED_TIERS  # the invariant this function exists for
    return tiers


def _bind_put(writer: _Writer, *, asset_id: str):
    """``writer.put`` with the asset pinned — every reference names one asset."""

    def put(**kwargs) -> tuple[UUID, str]:
        return writer.put(asset_id=asset_id, **kwargs)

    return put


def _as_cue(cue: Cue | Mapping[str, Any], *, rate: int) -> Cue:
    """A cue in the store's own spelling of its time.

    ``at_s`` is the one caller-supplied *time* that reaches the returned
    document — spans arrive already canonical from
    :func:`~paces.projection.to_document`. Passing it through the tick round
    trip here is what keeps ``StoreWrite.document`` and :func:`from_store`
    literally identical rather than merely equivalent: a hand-written
    ``"60.50"`` becomes ``"60.5"`` on the way in, not on the way back out.
    """
    cue = cue if isinstance(cue, Cue) else Cue.model_validate(dict(cue))
    if cue.at_s is None:
        return cue
    return cue.model_copy(update={"at_s": _decimal(_ticks(cue.at_s, rate=rate))})


def _document_span(document: StepDocument) -> tuple[str, str] | None:
    """The outermost ``(start, end)`` any span in *document* covers."""
    starts, ends = [], []
    for step in _walk(document.steps):
        for span in step.spans:
            starts.append(Fraction(span.start))
            ends.append(Fraction(span.end if span.end is not None else span.start))
    if not starts:
        return None
    return _fraction_decimal(min(starts)), _fraction_decimal(max(ends))


def _fraction_decimal(value: Fraction) -> str:
    """A ``Fraction`` of seconds back as a decimal string, exactly."""
    return _decimal(RationalTime(value.numerator, value.denominator))


def _walk(steps: Sequence[Step]) -> Iterator[Step]:
    for step in steps:
        yield step
        yield from _walk(step.steps)


def _write_passes(
    put, passes, *, detector: str, base, rate: int
) -> list[tuple[UUID, TimeInterval, str]]:
    written = []
    for row in passes:
        start, end, label = _pass_row(row)
        interval = _interval(start, end, rate=rate)
        annotation_id, _ = put(
            tier=PASS_TIER,
            key=f"pass:{label}/{start}/{end}",
            interval=interval,
            body=GuidePassBodyV1(label=label, detector=detector).model_dump(
                mode="json"
            ),
            schema_uri=PASS_BODY_SCHEMA_URI,
            derived_from=base,
        )
        written.append((annotation_id, interval, label))
    return written


def _pass_row(row) -> tuple[str, str, str]:
    if isinstance(row, Mapping):
        start, end, label = row["start"], row["end"], row.get("label", "")
    else:
        start, end, label = (list(row) + [""])[:3]
    return _seconds(start), _seconds(end), str(label or "")


def _seconds(value) -> str:
    """A time as a decimal string, whatever the caller had it as.

    Floats are accepted *here* and only here — they are what the analysis
    libraries return — and are converted through ``repr`` so no precision is
    invented, then re-normalised by the tick round trip.
    """
    if isinstance(value, str):
        return value
    return _fraction_decimal(Fraction(str(value)))


def _write_grid(
    put,
    grid: MetricGrid | None,
    *,
    doc_id: str,
    method: str,
    beat_count: int | None,
    span: tuple[str, str] | None,
    base,
    rate: int,
) -> UUID | None:
    if grid is None:
        return None
    interval = (
        _point(None, rate=rate)
        if span is None
        else _interval(span[0], span[1], rate=rate)
    )
    annotation_id, _ = put(
        tier=GRID_TIER,
        key=f"grid:{doc_id}",
        interval=interval,
        body=GuideGridBodyV1(
            doc_id=doc_id,
            unit=grid.unit,
            subdivisions=grid.subdivisions,
            tempo_bpm=grid.tempo_bpm,
            origin=grid.origin,
            origin_source=grid.origin_source,
            beat_count=beat_count,
            method=method,
        ).model_dump(mode="json"),
        schema_uri=GRID_BODY_SCHEMA_URI,
        derived_from=base,
    )
    return annotation_id


def _write_beats(put, beats, *, base, rate: int) -> None:
    for index, at in enumerate(beats):
        seconds = _seconds(at)
        put(
            tier=BEAT_TIER,
            key=f"beat:{seconds}",
            interval=_point(seconds, rate=rate),
            body=GuideBeatBodyV1(index=index).model_dump(mode="json"),
            schema_uri=BEAT_BODY_SCHEMA_URI,
            derived_from=base,
        )


def _write_transcript(put, transcript, *, base, rate: int) -> None:
    for index, row in enumerate(transcript):
        if isinstance(row, Mapping):
            start, end = _seconds(row["start"]), _seconds(row["end"])
            text, speaker = row["text"], row.get("speaker")
        else:
            start, end, text = (list(row) + [None])[:3]
            start, end, speaker = _seconds(start), _seconds(end), None
        put(
            tier=WORD_TIER,
            key=f"word:{start}/{end}/{index}",
            interval=_interval(start, end, rate=rate),
            body={"text": text, "speaker": speaker},
            schema_uri=WORD_BODY_SCHEMA_URI,
            derived_from=base,
        )


def _write_steps(
    put,
    steps: Sequence[Step],
    *,
    doc_id: str,
    parent_id: str | None,
    parent_ann: UUID | None,
    base,
    passes: Sequence[tuple[UUID, TimeInterval, str]],
    rate: int,
    step_rows: dict[str, tuple[UUID, str]],
    span_rows: dict[str, tuple[UUID, str]],
) -> list[Step]:
    """Write one sibling level, recurse, and return the steps with back-refs."""
    tier = STEP_TIER if parent_id is None else SUB_STEP_TIER
    out: list[Step] = []
    for ordinal, step in enumerate(steps):
        generated_by = (
            step.origin.generated_by
            if step.origin and step.origin.generated_by
            else DFLT_GENERATED_BY
        )
        confidence = step.origin.confidence if step.origin else None
        lineage = [*base] if parent_ann is None else [parent_ann, *base]
        rows: list[tuple[UUID, str]] = []
        for span_index, span in _spans_of(step):
            key = _span_key(doc_id, step.id, span)
            interval = (
                _point(None, rate=rate)
                if span is None
                else _interval(span.start, span.end, rate=rate)
            )
            annotation_id, digest = put(
                tier=tier,
                key=key,
                interval=interval,
                body=_step_body(
                    step,
                    doc_id=doc_id,
                    parent_id=parent_id,
                    ordinal=ordinal,
                    span_index=span_index,
                    span=span,
                ),
                schema_uri=STEP_BODY_SCHEMA_URI,
                generated_by=generated_by,
                derived_from=[*lineage, *_covering(passes, interval)],
                confidence=confidence,
            )
            rows.append((annotation_id, digest))
            if span is not None:
                span_rows[_span_address(step.id, span)] = (annotation_id, digest)
        head = rows[0]
        step_rows[step.id] = head
        children = _write_steps(
            put,
            step.steps,
            doc_id=doc_id,
            parent_id=step.id,
            parent_ann=head[0],
            base=base,
            passes=passes,
            rate=rate,
            step_rows=step_rows,
            span_rows=span_rows,
        )
        out.append(
            step.model_copy(
                update={
                    "steps": children,
                    "origin": _with_backref(
                        step.origin, head, generated_by=generated_by
                    ),
                }
            )
        )
    return out


def _spans_of(step: Step) -> list[tuple[int | None, SourceSpan | None]]:
    """``(span_index, span)`` pairs — one ``(None, None)`` row when spanless.

    A step with no spans is still a step: it gets exactly one annotation, so
    the store can hold "found, extent not recorded" rather than dropping it.
    """
    if not step.spans:
        return [(None, None)]
    return list(enumerate(step.spans))


def _span_address(step_id: str, span: SourceSpan) -> str:
    """``{step_id}/{source}/{role}/{start}`` — ``paces.derivation``'s key."""
    return f"{step_id}/{span.source}/{span.role}/{span.start}"


def _span_key(doc_id: str, step_id: str, span: SourceSpan | None) -> str:
    """The evidence key one ``(step, span)`` row is identified by.

    The step id is in it even when the span is not: a spanless step is still
    its own row, and keying every spanless step on the same string would
    collapse them all onto one annotation id.
    """
    address = f"{step_id}/-" if span is None else _span_address(step_id, span)
    return f"step:{doc_id}/{address}"


def _step_body(
    step: Step,
    *,
    doc_id: str,
    parent_id: str | None,
    ordinal: int,
    span_index: int | None,
    span: SourceSpan | None,
) -> dict:
    return GuideStepBodyV1(
        doc_id=doc_id,
        step_id=step.id,
        parent_step_id=parent_id,
        ordinal=ordinal,
        name=step.name,
        description=step.description,
        duration_value=step.duration.value,
        duration_unit=step.duration.unit,
        repeat=step.repeat,
        optional=step.optional,
        variant_of=step.variant_of,
        tags=list(step.tags),
        attrs=dict(step.attrs),
        span_index=span_index,
        span_count=len(step.spans),
        span_source=None if span is None else span.source,
        span_role=None if span is None else span.role,
        span_open_ended=span is not None and span.end is None,
        span_label=None if span is None else span.label,
        span_caption=None if span is None else span.caption,
        span_confidence=None if span is None else span.confidence,
        span_attrs={} if span is None else dict(span.attrs),
    ).model_dump(mode="json")


def _covering(passes: Sequence[tuple[UUID, TimeInterval, str]], interval) -> list[UUID]:
    """The pass rows a span sits inside.

    Lineage, not decoration: this is the edge that makes a re-run of the
    speech/music split mark the steps it framed stale
    (``nw.freshness.stale_after`` walks ``was_derived_from``). Containment is
    tested on the interval's own endpoints — an exact test through
    ``lacing.allen`` would need the span strictly inside, and a step that
    starts exactly where the music does is still framed by it.
    """
    return [
        annotation_id
        for annotation_id, span, _ in passes
        if span.start <= interval.start and interval.end <= span.end
    ]


def _with_backref(
    origin: Origin | None, row: tuple[UUID, str], *, generated_by: str
) -> Origin:
    """The step's ``Origin`` with its evidence back-reference filled in.

    A step that arrived without an ``Origin`` leaves with one: the store now
    knows where it came from, and saying so is the point of the field.
    """
    annotation_id, digest = row
    fields = {} if origin is None else origin.model_dump()
    return Origin(
        **{
            **fields,
            "generated_by": generated_by,
            "annotation_id": str(annotation_id),
            "value_digest": digest,
        }
    )


def _write_cues(put, cues: Sequence[Cue], *, doc_id: str, step_rows, rate: int) -> None:
    for ordinal, cue in enumerate(cues):
        parent = step_rows.get(cue.anchor.step)
        put(
            tier=CUE_TIER,
            key=f"cue:{doc_id}/{cue.id}",
            interval=_point(cue.at_s, rate=rate),
            body=GuideCueBodyV1(
                doc_id=doc_id,
                ordinal=ordinal,
                cue_id=cue.id,
                kind=cue.kind,
                text=cue.text,
                step_id=cue.anchor.step,
                offset_value=None
                if cue.anchor.offset is None
                else cue.anchor.offset.value,
                offset_unit=None
                if cue.anchor.offset is None
                else cue.anchor.offset.unit,
                duration_value=None if cue.duration is None else cue.duration.value,
                duration_unit=None if cue.duration is None else cue.duration.unit,
                source=cue.source,
                at_resolved=cue.at_s is not None,
                attrs=dict(cue.attrs),
            ).model_dump(mode="json"),
            schema_uri=CUE_BODY_SCHEMA_URI,
            derived_from=[] if parent is None else [parent[0]],
        )


def _write_recipes(put, recipes, *, doc_id: str, span_rows, base, rate: int) -> None:
    for address, recipe in _recipe_entries(recipes):
        entry = (
            recipe if isinstance(recipe, Mapping) else recipe.model_dump(mode="json")
        )
        window = entry["window"]
        parent = span_rows.get(address)
        put(
            tier=RECIPE_TIER,
            key=f"derivation:{doc_id}/{address}",
            interval=_interval(window[0], window[1], rate=rate),
            body=GuideRecipeBodyV1(
                doc_id=doc_id,
                span_key=address,
                step_id=address.split("/", 1)[0],
                box=None if entry.get("box") is None else list(entry["box"]),
                frame_width=entry["frameWidth"]
                if "frameWidth" in entry
                else entry["frame_width"],
                frame_height=entry["frameHeight"]
                if "frameHeight" in entry
                else entry["frame_height"],
                source_asset_id=entry.get(
                    "sourceAssetId", entry.get("source_asset_id")
                ),
                locator=entry["locator"],
                params=dict(entry.get("params", {})),
                locked=bool(entry.get("locked", False)),
                media_digest=entry.get("mediaDigest", entry.get("media_digest")),
            ).model_dump(mode="json"),
            schema_uri=RECIPE_BODY_SCHEMA_URI,
            derived_from=[*([] if parent is None else [parent[0]]), *base],
        )


def _recipe_entries(recipes) -> Iterator[tuple[str, Any]]:
    if recipes is None:
        return
    entries = getattr(recipes, "entries", None)
    if entries is None and isinstance(recipes, Mapping):
        entries = recipes.get("entries", recipes)
    yield from (entries or {}).items()


# ── reading back ────────────────────────────────────────────────────────────


class DocumentNotInStore(KeyError):
    """No guide in this store matches the asset (and doc id) asked for."""


class AmbiguousDocument(ValueError):
    """Several guides share the asset and no ``doc_id`` said which."""


def from_store(store, *, asset_id: str, doc_id: str | None = None) -> StepDocument:
    """Project the guide held in *store* back into a :class:`StepDocument`.

    The inverse of :func:`to_store`: given the same store, it reproduces
    ``StoreWrite.document`` byte for byte under
    :func:`paces.model.dumps_document`. Document-layer records (``locks``,
    ``questions``, ``artifacts``, span ``excerpt`` windows) come back empty,
    because they never went in — see the module docstring.

    Args:
        store: The ``lacing`` store written by :func:`to_store`.
        asset_id: Which media's annotations to read.
        doc_id: Which guide, when the store holds more than one for that
            asset. Optional when there is exactly one.

    Raises:
        DocumentNotInStore: nothing matches.
        AmbiguousDocument: several guides match and none was named.
    """
    rows = [
        annotation
        for annotation in store.all()
        if getattr(annotation.reference, "asset_id", None) == asset_id
    ]
    envelope = _envelope(rows, asset_id=asset_id, doc_id=doc_id)
    guide_id = envelope.body["doc_id"]

    def mine(tier: str) -> list[Annotation]:
        return [
            row
            for row in rows
            if row.tier == tier and row.body.get("doc_id") == guide_id
        ]

    sources = [
        Source(
            id=row.body["source_id"],
            kind=row.body["kind"],
            uri=row.body["uri"],
            asset_id=row.body["asset_id"],
            duration_s=row.body["duration_s"],
            title=row.body["title"],
            attribution=row.body["attribution"],
            rights=row.body["rights"],
            attrs=dict(row.body["attrs"]),
        )
        for row in sorted(mine(SOURCE_TIER), key=lambda r: r.body["ordinal"])
    ]
    grids = mine(GRID_TIER)
    metric = _metric(grids[0]) if grids else None
    step_rows = mine(STEP_TIER) + mine(SUB_STEP_TIER)
    cues = [
        _cue(row) for row in sorted(mine(CUE_TIER), key=lambda r: r.body["ordinal"])
    ]
    return StepDocument(
        id=guide_id,
        schema_version=envelope.body.get("schema_version", SCHEMA_VERSION),
        title=envelope.body["title"],
        lang=envelope.body["lang"],
        domain=envelope.body["domain"],
        credits=envelope.body["credits"],
        metric=metric,
        sources=sources,
        steps=_steps(step_rows, parent_id=None),
        cues=cues,
        attrs=dict(envelope.body["attrs"]),
    )


def _envelope(rows, *, asset_id: str, doc_id: str | None) -> Annotation:
    envelopes = [row for row in rows if row.tier == DOC_TIER]
    if doc_id is not None:
        envelopes = [row for row in envelopes if row.body["doc_id"] == doc_id]
    if not envelopes:
        raise DocumentNotInStore(
            f"no guide for asset {asset_id!r}"
            + ("" if doc_id is None else f" with doc_id {doc_id!r}")
        )
    if len(envelopes) > 1:
        found = sorted(row.body["doc_id"] for row in envelopes)
        raise AmbiguousDocument(
            f"asset {asset_id!r} holds {len(envelopes)} guides ({found}); "
            "pass doc_id= to say which"
        )
    return envelopes[0]


def _metric(row: Annotation) -> MetricGrid:
    body = row.body
    return MetricGrid(
        unit=body["unit"],
        subdivisions=body["subdivisions"],
        tempo_bpm=body["tempo_bpm"],
        origin=body["origin"],
        origin_source=body["origin_source"],
    )


def _cue(row: Annotation) -> Cue:
    body = row.body
    offset = (
        None
        if body["offset_value"] is None
        else Measure(value=body["offset_value"], unit=body["offset_unit"])
    )
    duration = (
        None
        if body["duration_value"] is None
        else Measure(value=body["duration_value"], unit=body["duration_unit"])
    )
    return Cue(
        id=body["cue_id"],
        kind=body["kind"],
        text=body["text"],
        anchor=Anchor(step=body["step_id"], offset=offset),
        duration=duration,
        source=body["source"],
        at_s=_decimal(row.reference.interval.start) if body["at_resolved"] else None,
        attrs=dict(body["attrs"]),
    )


def _steps(rows: Sequence[Annotation], *, parent_id: str | None) -> list[Step]:
    """Rebuild one sibling level from its annotation rows, then recurse."""
    level = [row for row in rows if row.body["parent_step_id"] == parent_id]
    by_step: dict[str, list[Annotation]] = {}
    for row in level:
        by_step.setdefault(row.body["step_id"], []).append(row)
    ordered = sorted(by_step.items(), key=lambda kv: kv[1][0].body["ordinal"])
    return [
        _step(step_id, sorted(step_rows, key=_span_order), rows=rows)
        for step_id, step_rows in ordered
    ]


def _span_order(row: Annotation) -> int:
    index = row.body["span_index"]
    return -1 if index is None else index


def _step(step_id: str, step_rows: Sequence[Annotation], *, rows) -> Step:
    head = step_rows[0]
    body = head.body
    return Step(
        id=step_id,
        name=body["name"],
        duration=Measure(value=body["duration_value"], unit=body["duration_unit"]),
        description=body["description"],
        spans=[_span(row) for row in step_rows if row.body["span_index"] is not None],
        steps=_steps(rows, parent_id=step_id),
        repeat=body["repeat"],
        optional=body["optional"],
        variant_of=body["variant_of"],
        tags=list(body["tags"]),
        origin=Origin(
            annotation_id=str(head.id),
            value_digest=annotation_value_digest(head),
            generated_by=head.provenance.was_generated_by,
            confidence=head.confidence,
        ),
        attrs=dict(body["attrs"]),
    )


def _span(row: Annotation) -> SourceSpan:
    body = row.body
    interval = row.reference.interval
    return SourceSpan(
        source=body["span_source"],
        role=body["span_role"],
        start=_decimal(interval.start),
        end=None if body["span_open_ended"] else _decimal(interval.end),
        label=body["span_label"],
        caption=body["span_caption"],
        confidence=body["span_confidence"],
        attrs=dict(body["span_attrs"]),
    )


def recipes_from_store(store, *, asset_id: str, doc_id: str | None = None) -> dict:
    """The derivation recipes held for one guide, as the sidecar's shape.

    ``{span address: recipe dict}`` — the same keys
    ``paces.derivation.RecipesFile.entries`` uses, so a store round trip and
    the committed sidecar are directly comparable.
    """
    rows = [
        row
        for row in store.all()
        if row.tier == RECIPE_TIER
        and getattr(row.reference, "asset_id", None) == asset_id
        and (doc_id is None or row.body["doc_id"] == doc_id)
    ]
    return {
        row.body["span_key"]: {
            "box": row.body["box"],
            "window": [
                _decimal(row.reference.interval.start),
                _decimal(row.reference.interval.end),
            ],
            "frameWidth": row.body["frame_width"],
            "frameHeight": row.body["frame_height"],
            "sourceAssetId": row.body["source_asset_id"],
            "locator": row.body["locator"],
            "params": dict(row.body["params"]),
            "locked": row.body["locked"],
            "mediaDigest": row.body["media_digest"],
        }
        for row in rows
    }
