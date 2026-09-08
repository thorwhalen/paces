"""The evidence layer's acceptance tests (issue #4).

Offline and synthetic throughout: every store is a dict-backed
``lacing.MemoryStore``, never a file, never the user data dir.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

lacing = pytest.importorskip("lacing")

from lacing import (  # noqa: E402
    DEFAULT_RATE,
    LossyTimeConversionError,
    MemoryStore,
    RationalTime,
    TierStereotype,
    annotation_value_digest,
)
from lacing.schema import validate as validate_body  # noqa: E402

from paces import SegStep, Segmentation, segment  # noqa: E402
from paces.bodies import (  # noqa: E402
    BEAT_TIER,
    CUE_TIER,
    DOC_TIER,
    GRID_TIER,
    PASS_TIER,
    RECIPE_TIER,
    SOURCE_TIER,
    STEP_TIER,
    SUB_STEP_TIER,
    WORD_TIER,
)
from paces.evidence import (  # noqa: E402
    TIERS,
    AmbiguousDocument,
    CollidingEvidenceKey,
    DocumentNotInStore,
    from_store,
    recipes_from_store,
    to_store,
)
from paces.model import Cue, dumps_document  # noqa: E402
from paces.projection import to_document  # noqa: E402

ASSET = "a" * 64  # a bare 64-hex asset id, so lineage edges are representable
GRID = {"unit": "eight", "subdivisions": 8, "tempoBpm": "129.2", "origin": "51.2"}
STEPS = [
    {"name": "Mise en place", "duration": 2},
    {
        "name": "Déhanchés",
        "duration": 8,
        "children": [
            {"name": "sur place", "duration": 4},
            {"name": "en avançant", "duration": 4},
        ],
    },
    {"name": "Soleil avec les bras", "duration": 4},
]

# The speech/music split's own shape: measure_grid puts exactly these triples
# in GridMeasurement.evidence["segments"].
PASSES = [(0.0, 51.2, "speech"), (51.2, 400.0, "music")]
BEATS = ["51.2", "51.664", "52.128"]
TRANSCRIPT = [
    {"start": "60.0", "end": "60.4", "text": "se", "speaker": "singer"},
    {"start": "60.4", "end": "61.0", "text": "hace", "speaker": "singer"},
]
RECIPES = {
    "dehanches/source/performance/58.63": {
        "box": ["120", "40", "480", "640"],
        "window": ["58.63", "88.36"],
        "frameWidth": 1280,
        "frameHeight": 720,
        "sourceAssetId": ASSET,
        "locator": "full_frame",
        "params": {"aspect": "0.75", "pad": "0.12"},
        "locked": False,
        "mediaDigest": "d" * 64,
    }
}


def a_segmentation(steps=STEPS):
    return segment(None, steps=steps, grid=GRID)


def a_write(store=None, *, seg=None, **kwargs):
    kwargs.setdefault("doc_id", "que-calor")
    kwargs.setdefault("title", "Que Calor")
    kwargs.setdefault("source", "https://youtu.be/q_TUyxUhoEw")
    kwargs.setdefault("domain", "dance")
    return to_store(
        seg or a_segmentation(),
        store=store if store is not None else MemoryStore(),
        asset_id=ASSET,
        **kwargs,
    )


# ── the acceptance test ─────────────────────────────────────────────────────


def test_roundtrip_reproduces_the_document_byte_for_byte():
    store = MemoryStore()
    write = a_write(store)
    assert dumps_document(from_store(store, asset_id=ASSET)) == dumps_document(
        write.document
    )


def test_roundtrip_with_every_tier_present():
    store = MemoryStore()
    write = a_write(
        store,
        cues=[
            Cue(
                id="calor",
                kind="lyric",
                text="se hace difícil respirar",
                anchor={"step": "dehanches", "offset": {"value": "2", "unit": "eight"}},
                at_s="60.5",
            )
        ],
        passes=PASSES,
        beats=BEATS,
        transcript=TRANSCRIPT,
        recipes=RECIPES,
        detector="mixing.find_segments:speech_music",
    )
    assert dumps_document(from_store(store, asset_id=ASSET)) == dumps_document(
        write.document
    )


def test_the_projection_only_gains_its_evidence_backreferences():
    """``to_store``'s document is ``to_document``'s, plus the ``Origin`` refs."""
    seg = a_segmentation()
    write = a_write(seg=seg)
    plain = to_document(
        seg,
        doc_id="que-calor",
        title="Que Calor",
        source="https://youtu.be/q_TUyxUhoEw",
        domain="dance",
    )
    assert [s.name for s in write.document.steps] == [s.name for s in plain.steps]
    for enriched, bare in zip(write.document.steps, plain.steps):
        assert enriched.origin.generated_by == bare.origin.generated_by
        assert enriched.origin.confidence == bare.origin.confidence
        assert bare.origin.annotation_id is None
        assert enriched.origin.annotation_id is not None
        assert enriched.origin.value_digest is not None


# ── idempotence and identity ────────────────────────────────────────────────


def test_a_second_to_store_writes_nothing():
    store = MemoryStore()
    first = a_write(store)
    before = len(list(store.all()))
    second = a_write(store)
    assert (second.written, second.updated) == (0, 0)
    assert second.unchanged == first.total
    assert len(list(store.all())) == before


def test_ids_are_deterministic_across_fresh_stores():
    one, two = a_write(), a_write()
    assert one.annotation_ids == two.annotation_ids
    assert dumps_document(one.document) == dumps_document(two.document)


def test_a_changed_step_updates_in_place_keeping_its_id():
    """A change that keeps the step id rewrites that row, id and all."""
    store = MemoryStore()
    base = a_write(store)
    longer = [dict(STEPS[0], duration=3), *STEPS[1:]]
    changed = a_write(store, seg=a_segmentation(longer))
    annotation_id = base.document.steps[0].origin.annotation_id
    assert annotation_id in changed.annotation_ids  # same id
    assert changed.updated >= 1  # new value
    assert (
        changed.document.steps[0].origin.value_digest
        != base.document.steps[0].origin.value_digest
    )


def test_a_step_that_no_longer_exists_is_pruned_not_resurrected():
    store = MemoryStore()
    a_write(store)
    shorter = a_write(store, seg=a_segmentation(STEPS[:2]))
    assert shorter.removed == 1  # "Soleil avec les bras" is gone
    back = from_store(store, asset_id=ASSET)
    assert [step.id for step in back.steps] == [
        step.id for step in shorter.document.steps
    ]
    assert dumps_document(back) == dumps_document(shorter.document)


def test_prune_false_accumulates_instead():
    store = MemoryStore()
    a_write(store)
    shorter = a_write(store, seg=a_segmentation(STEPS[:2]), prune=False)
    assert shorter.removed == 0
    assert len([a for a in store.all() if a.tier == STEP_TIER]) == 3


def test_pruning_only_touches_tiers_this_call_wrote_to():
    """Omitting ``passes=`` leaves an earlier speech/music split standing."""
    store = MemoryStore()
    a_write(store, passes=PASSES)
    a_write(store)  # same guide, no passes supplied
    assert len([a for a in store.all() if a.tier == PASS_TIER]) == len(PASSES)


def test_pruning_leaves_another_guide_on_the_same_asset_alone():
    store = MemoryStore()
    a_write(store, doc_id="one")
    a_write(store, doc_id="two", seg=a_segmentation(STEPS[:1]))
    assert len(from_store(store, asset_id=ASSET, doc_id="one").steps) == 3
    assert len(from_store(store, asset_id=ASSET, doc_id="two").steps) == 1


def test_origin_backreferences_resolve_to_real_annotations():
    store = MemoryStore()
    write = a_write(store)
    by_id = {str(a.id): a for a in store.all()}
    for step in write.document.steps:
        annotation = by_id[step.origin.annotation_id]
        assert annotation.tier == STEP_TIER
        assert annotation.body["step_id"] == step.id
        assert step.origin.value_digest == annotation_value_digest(annotation)


# ── the tier table ──────────────────────────────────────────────────────────


def test_tiers_land_as_the_table_says():
    store = MemoryStore()
    a_write(
        store,
        cues=[
            Cue(
                id="calor",
                kind="lyric",
                text="se hace difícil respirar",
                anchor={"step": "dehanches"},
            )
        ],
        passes=PASSES,
        beats=BEATS,
        transcript=TRANSCRIPT,
        recipes=RECIPES,
    )
    counts: dict[str, int] = {}
    for annotation in store.all():
        counts[annotation.tier] = counts.get(annotation.tier, 0) + 1
    assert counts == {
        DOC_TIER: 1,
        SOURCE_TIER: 1,
        PASS_TIER: len(PASSES),
        GRID_TIER: 1,
        BEAT_TIER: len(BEATS),
        WORD_TIER: len(TRANSCRIPT),
        STEP_TIER: 3,  # one per (step, span); three top-level steps, one span each
        SUB_STEP_TIER: 2,
        CUE_TIER: 1,
        RECIPE_TIER: 1,
    }


def test_declared_stereotypes_match_docs_07_section_6_3():
    by_name = {tier.name: tier for tier in TIERS}
    assert by_name[SUB_STEP_TIER].stereotype is TierStereotype.INCLUDED_IN
    assert by_name[SUB_STEP_TIER].parent == STEP_TIER
    assert by_name[CUE_TIER].stereotype is TierStereotype.INCLUDED_IN
    assert by_name[CUE_TIER].parent == STEP_TIER
    assert by_name[RECIPE_TIER].stereotype is TierStereotype.SYMBOLIC_ASSOCIATION
    assert by_name[RECIPE_TIER].parent == STEP_TIER
    assert by_name[STEP_TIER].stereotype is TierStereotype.NONE


def test_every_body_validates_against_its_registered_schema():
    store = MemoryStore()
    a_write(store, passes=PASSES, beats=BEATS, transcript=TRANSCRIPT, recipes=RECIPES)
    for annotation in store.all():
        validate_body(annotation.body, annotation.body_schema_uri)


# ── provenance / lineage ────────────────────────────────────────────────────


def _one(store, tier):
    rows = [a for a in store.all() if a.tier == tier]
    assert len(rows) == 1, f"{tier}: expected one row, got {len(rows)}"
    return rows[0]


def test_lineage_edges_make_freshness_work():
    store = MemoryStore()
    a_write(store, passes=PASSES, beats=BEATS, recipes=RECIPES)
    grid = _one(store, GRID_TIER)
    passes = {a.id for a in store.all() if a.tier == PASS_TIER}
    steps = [a for a in store.all() if a.tier == STEP_TIER]
    subs = [a for a in store.all() if a.tier == SUB_STEP_TIER]
    beats = [a for a in store.all() if a.tier == BEAT_TIER]
    recipe = _one(store, RECIPE_TIER)

    assert passes <= set(grid.provenance.was_derived_from)
    assert ASSET in grid.provenance.was_derived_from
    for step in steps:
        assert grid.id in step.provenance.was_derived_from
    step_ids = {a.id for a in steps}
    for sub in subs:
        assert step_ids & set(sub.provenance.was_derived_from)
    for beat in beats:
        assert grid.id in beat.provenance.was_derived_from
    assert step_ids & set(recipe.provenance.was_derived_from)


def test_a_step_is_derived_from_the_pass_that_frames_it():
    store = MemoryStore()
    a_write(store, passes=PASSES)
    music = next(
        a for a in store.all() if a.tier == PASS_TIER and a.body["label"] == "music"
    )
    speech = next(
        a for a in store.all() if a.tier == PASS_TIER and a.body["label"] == "speech"
    )
    steps = [a for a in store.all() if a.tier == STEP_TIER]
    assert steps  # the routine starts at the grid origin, inside the music pass
    for step in steps:
        assert music.id in step.provenance.was_derived_from
        assert speech.id not in step.provenance.was_derived_from


def test_a_non_hex_asset_id_still_works_and_simply_carries_no_edge():
    store = MemoryStore()
    to_store(a_segmentation(), store=store, asset_id="local-video", doc_id="g")
    doc = _one(store, DOC_TIER)
    assert doc.provenance.was_derived_from == []
    assert from_store(store, asset_id="local-video").id == "g"


# ── the no-floats boundary ──────────────────────────────────────────────────


def _leaf_values(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaf_values(value, f"{path}/{key}")
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            yield from _leaf_values(value, f"{path}/{index}")
    else:
        yield path, node


def test_no_float_reaches_a_body():
    store = MemoryStore()
    a_write(store, passes=PASSES, beats=BEATS, transcript=TRANSCRIPT, recipes=RECIPES)
    offenders = [
        (annotation.tier, path, value)
        for annotation in store.all()
        for path, value in _leaf_values(annotation.body)
        if isinstance(value, float) and not path.endswith("confidence")
    ]
    assert offenders == []


def test_every_interval_is_rational_ticks():
    store = MemoryStore()
    a_write(store, passes=PASSES, beats=BEATS)
    for annotation in store.all():
        interval = annotation.reference.interval
        assert isinstance(interval.start, RationalTime)
        assert isinstance(interval.start.value, int)
        assert interval.start.rate == DEFAULT_RATE


def test_a_time_the_rate_cannot_hold_raises_rather_than_rounding():
    # 1/7 s is not representable at any decimal-friendly rate.
    with pytest.raises(LossyTimeConversionError):
        to_store(
            a_segmentation(),
            store=MemoryStore(),
            asset_id=ASSET,
            passes=[("0.0", "0.14285714", "music")],
        )


def test_a_non_canonical_decimal_comes_back_normalised():
    """The store speaks ticks, so ``"60.50"`` reads back as ``"60.5"``.

    Documented in ``paces/evidence.py``: a projection is always canonical, so
    this only shows up on a hand-written value, and it is a normalisation
    rather than a loss.
    """
    store = MemoryStore()
    a_write(
        store,
        cues=[
            Cue(
                id="c",
                kind="lyric",
                text="x",
                anchor={"step": "dehanches"},
                at_s="60.50",
            )
        ],
    )
    assert from_store(store, asset_id=ASSET).cues[0].at_s == "60.5"


def test_a_finer_rate_is_a_keyword_not_a_rewrite():
    store = MemoryStore()
    to_store(
        a_segmentation(),
        store=store,
        asset_id=ASSET,
        doc_id="g",
        passes=[("0.0", "1.00048", "music")],
        rate=1_000_000,
    )
    assert any(a.tier == PASS_TIER for a in store.all())


# ── shapes the segmenters are allowed to return ─────────────────────────────


def test_a_step_with_no_spans_is_one_row_not_zero():
    store = MemoryStore()
    spanless = Segmentation(
        steps=(
            SegStep(id="intro", name="Intro", confidence=0.4),
            SegStep(id="verse", name="Verse", confidence=0.4),
        ),
        unit="seconds",
        method="explicit",
        flags=("extent-unrecorded",),
    )
    write = to_store(spanless, store=store, asset_id=ASSET, doc_id="g")
    rows = [a for a in store.all() if a.tier == STEP_TIER]
    assert len(rows) == 2
    assert all(row.body["span_index"] is None for row in rows)
    assert all(row.body["span_count"] == 0 for row in rows)
    assert dumps_document(from_store(store, asset_id=ASSET)) == dumps_document(
        write.document
    )


def test_cues_and_recipes_come_back_out():
    store = MemoryStore()
    cue = Cue(
        id="calor",
        kind="lyric",
        text="se hace difícil respirar",
        anchor={"step": "dehanches", "offset": {"value": "2", "unit": "eight"}},
        source="source",
        at_s="60.5",
    )
    a_write(store, cues=[cue], recipes=RECIPES)
    back = from_store(store, asset_id=ASSET)
    assert back.cues == [cue]
    assert recipes_from_store(store, asset_id=ASSET) == RECIPES


# ── errors that name the fix ────────────────────────────────────────────────


def test_two_spans_at_one_address_are_refused_not_merged():
    """Derived ids make a duplicate span address a silent overwrite."""
    doubled = Segmentation(
        steps=(SegStep(id="b1", name="One", spans=((0.0, 10.0), (0.0, 20.0))),),
        unit="seconds",
        method="explicit",
    )
    with pytest.raises(CollidingEvidenceKey):
        to_store(doubled, store=MemoryStore(), asset_id=ASSET, doc_id="g")


def test_reading_an_asset_with_nothing_in_it_says_so():
    with pytest.raises(DocumentNotInStore):
        from_store(MemoryStore(), asset_id=ASSET)


def test_two_guides_on_one_asset_need_a_doc_id():
    store = MemoryStore()
    a_write(store, doc_id="one")
    a_write(store, doc_id="two")
    with pytest.raises(AmbiguousDocument):
        from_store(store, asset_id=ASSET)
    assert from_store(store, asset_id=ASSET, doc_id="two").id == "two"


# ── the core stays pydantic-only (ADR-0004) ─────────────────────────────────


def test_importing_paces_does_not_import_lacing():
    code = "import sys, paces; print('lacing' in sys.modules)"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "False"


def test_to_store_is_reachable_from_the_package_root():
    import paces

    assert paces.to_store is to_store
    assert "to_store" in dir(paces)
    with pytest.raises(AttributeError):
        paces.no_such_thing


# ── the README's example, run ───────────────────────────────────────────────


def test_the_readme_example_actually_works():
    """The block under README's "The evidence layer", executed.

    Also checks the README still contains the lines this mirrors, so the two
    cannot drift apart silently.
    """
    asset_sha256 = ASSET
    seg = segment(None, steps=[("Mise en place", 2), ("Déhanchés", 8)], grid=GRID)

    store = MemoryStore()
    write = to_store(
        seg,
        store=store,
        asset_id=asset_sha256,
        doc_id="que-calor",
        title="Que Calor",
        domain="dance",
        source="https://youtu.be/q_TUyxUhoEw",
    )

    assert dumps_document(from_store(store, asset_id=asset_sha256)) == dumps_document(
        write.document
    )
    assert (
        to_store(
            seg,
            store=store,
            asset_id=asset_sha256,
            doc_id="que-calor",
            title="Que Calor",
            domain="dance",
            source="https://youtu.be/q_TUyxUhoEw",
        ).written
        == 0
    )

    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(
        encoding="utf-8"
    )
    for line in (
        "from lacing import MemoryStore",
        "write = to_store(seg, store=store, asset_id=asset_sha256,",
        "dumps_document(from_store(store, asset_id=asset_sha256))",
    ):
        assert line in readme, f"README no longer shows: {line}"
