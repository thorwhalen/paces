"""Media derivation: fill ``ArtifactRef``s with real clips, gifs and posters.

For every excerpt-bearing :class:`~paces.model.SourceSpan`, cut a loopable
mp4, a palette-quality gif and a poster frame from the local media, write
them through a store keyed by document-relative uri, and upsert the
resulting :class:`~paces.model.ArtifactRef`\\ s onto the owning step. The
design — where media lands, why CI needs no system ffmpeg, and the
``subject_locator=`` seam — is ADR-0005 (``docs/adr/0005-media-derivation.md``);
this docstring only summarises the contracts.

**The locator seam (Shape B — locator observes, core decides).** A
``subject_locator`` is a callable receiving a :class:`LocateQuery` and
returning a :class:`SubjectObservation` — timed raw region evidence — or
``None``, which means "no crop" and is both the default locator's honest
answer (:func:`full_frame`) and the zero-detections fallback. The *core*
owns the one policy pipeline (:func:`resolve_crop_box`): union regions per
sample → robust percentile envelope → pad → force aspect → clamp → **one
static box per excerpt window** (measured on 2.5–6 s loops; per-frame crops
are unstable). A ``None`` observation gets no policy: no crop means
genuinely uncropped, not letterboxed.

**Crop recipes** persist in a sidecar (``<document-stem>.recipes.json``,
next to the document, committed and diffable) keyed by the span address
``{step_id}/{source}/{role}/{start}``. A recipe whose inputs still match is
reused (the locator is skipped); a **locked** recipe's box is used verbatim
— never re-padded, re-aspected or clamped — and survives drift with a loud
flag. Hand-override = edit ``box``, set ``locked: true``.

**Honesty flags over silence.** Every skipped span, unverifiable identity,
kept lock, refreshed or orphaned recipe, and stale artifact is a named flag
in the result — never a silent drop.

All media I/O goes through ``mixing`` (behind the ``[media]`` extra) — never
moviepy/ffmpeg directly.
"""

from __future__ import annotations

import hashlib
import math
import re
import tempfile
from collections.abc import Iterator, MutableMapping
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path, PurePosixPath
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from paces.model import (
    ArtifactRef,
    Decimal,
    Step,
    StepDocument,
    decimal_str,
)

#: Crop-policy defaults — the POC's shipped production values
#: (``docs/poc-reference/tools/build_media.py``): 4th/96th percentile robust
#: envelope, 16% padding, 4:5 portrait-ish aspect (width/height).
ENVELOPE_LO = 4
ENVELOPE_HI = 96
DFLT_PAD = 0.16
DFLT_ASPECT = 0.8

#: The artifact roles derive produces, in production order.
DFLT_ROLES = ("clip", "gif", "poster")

#: Uri prefix (and store-key prefix) for derived media — POSIX '/', always.
MEDIA_PREFIX = "media"

_MIME = {"clip": "video/mp4", "gif": "image/gif", "poster": "image/jpeg"}
_EXT = {"clip": ".mp4", "gif": ".gif", "poster": ".jpg"}

RECIPES_SCHEMA_VERSION = "0.1.0"

#: A pixel box: (x, y, w, h) from the frame's top-left.
Box = tuple[int, int, int, int]


# ── the locator seam ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LocateQuery:
    """What a ``subject_locator`` is asked: one excerpt window of one media
    file, with read-only hints. Times are float seconds — a computed view,
    like :func:`paces.model.resolve`'s output, never the stored document."""

    media_path: str
    start_s: float
    end_s: float
    frame_width: int
    frame_height: int
    step_id: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class SubjectObservation:
    """Timed raw region evidence: ``samples[i] = (t_s, (box, box, ...))`` —
    one region tuple per probed instant. Deliberately not person-shaped: one
    box for a dancer, two for judo, hands + workpiece for cooking. Samples
    are transient locator output; only the resolved box is ever persisted."""

    samples: tuple[tuple[float, tuple[Box, ...]], ...]


#: The seam: returns an observation, or ``None`` meaning "no crop".
SubjectLocator = Callable[[LocateQuery], "SubjectObservation | None"]


def full_frame(query: LocateQuery) -> None:
    """The default locator: no crop, ever — a real implementation of the
    contract whose honest answer is ``None`` (docs/09: the seam must be
    "genuinely pluggable and nullable"). Pointable replacement: rtmlib pose
    boxes (Apache-2.0; never YOLO/ultralytics — AGPL, see ADR-0005 §3)."""
    return None


full_frame.locator_name = "full-frame"


def _percentile(values: list[float], q: float) -> float:
    """Linear-interpolated percentile (numpy's default method), pure python."""
    xs = sorted(values)
    k = (len(xs) - 1) * q / 100
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return xs[int(k)]
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def resolve_crop_box(
    observation: SubjectObservation | None,
    *,
    frame_size: tuple[int, int],
    aspect: float = DFLT_ASPECT,
    pad: float = DFLT_PAD,
    lo: float = ENVELOPE_LO,
    hi: float = ENVELOPE_HI,
) -> Box | None:
    """The locator-agnostic crop policy: observation → ONE static box.

    Union regions per sample → robust percentile envelope (``lo``/``hi``) →
    pad → force ``aspect`` (w/h, expanding the deficient dimension) → clamp
    into the frame (shrinking aspect-true when the padded box exceeds it).
    ``None`` in (no observation, or no sample carried a region) → ``None``
    out: full frame, no policy — no crop is genuinely uncropped.

    >>> obs = SubjectObservation(samples=((0.0, ((40, 40, 20, 40),)),))
    >>> resolve_crop_box(obs, frame_size=(200, 200), pad=0.0, aspect=0.5)
    (40, 40, 20, 40)
    """
    if observation is None:
        return None
    unions = []
    for _t, boxes in observation.samples:
        if not boxes:
            continue
        lefts, tops = zip(*((x, y) for x, y, _w, _h in boxes))
        rights = tuple(x + w for x, _y, w, _h in boxes)
        bottoms = tuple(y + h for _x, y, _w, h in boxes)
        unions.append((min(lefts), min(tops), max(rights), max(bottoms)))
    if not unions:
        return None
    left = _percentile([u[0] for u in unions], lo)
    top = _percentile([u[1] for u in unions], lo)
    right = _percentile([u[2] for u in unions], hi)
    bottom = _percentile([u[3] for u in unions], hi)
    w, h = right - left, bottom - top
    left, top = left - w * pad, top - h * pad
    right, bottom = right + w * pad, bottom + h * pad
    w, h = right - left, bottom - top
    cx, cy = (left + right) / 2, (top + bottom) / 2
    if h <= 0 or w <= 0:
        return None
    if w / h > aspect:
        h = w / aspect
    else:
        w = h * aspect
    frame_w, frame_h = frame_size
    if w > frame_w:
        w, h = frame_w, frame_w / aspect
    if h > frame_h:
        h, w = frame_h, frame_h * aspect
    cx = min(max(cx, w / 2), frame_w - w / 2)
    cy = min(max(cy, h / 2), frame_h - h / 2)
    if w < 2 or h < 2:
        return None
    return (
        int(round(cx - w / 2)),
        int(round(cy - h / 2)),
        int(round(w)),
        int(round(h)),
    )


# ── crop recipes (the sidecar) ──────────────────────────────────────────────


class _WireBase(BaseModel):
    """camelCase wire, strict fields — the document's conventions, locally."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid"
    )


class CropRecipe(_WireBase):
    """One span's derivation parameters: the resolved ``box`` (the *final*
    post-policy crop; ``None`` = full frame, a recorded decision) plus the
    input fingerprint that makes drift detectable. ``params`` are decimal
    strings (the sidecar is committed — no floats on the wire) and are a
    fingerprint only: a stored box is never re-run through the policy."""

    box: Box | None = None
    window: tuple[Decimal, Decimal]
    frame_width: int
    frame_height: int
    source_asset_id: str | None = None  # None = media identity unverified
    locator: str
    params: dict[str, Decimal] = Field(default_factory=dict)
    locked: bool = False


class RecipesFile(_WireBase):
    """The sidecar document: span address → :class:`CropRecipe`."""

    kind: Literal["paces.crop-recipes"] = "paces.crop-recipes"
    schema_version: str = RECIPES_SCHEMA_VERSION
    entries: dict[str, CropRecipe] = Field(default_factory=dict)


def load_recipes(path: str | Path) -> RecipesFile:
    """Read the sidecar (missing file → an empty one)."""
    path = Path(path)
    if not path.exists():
        return RecipesFile()
    return RecipesFile.model_validate_json(path.read_text(encoding="utf-8"))


def save_recipes(recipes: RecipesFile, path: str | Path) -> None:
    """Write the sidecar in the document's canonical wire style."""
    import json

    payload = recipes.model_dump(mode="json", by_alias=True, exclude_none=True)
    Path(path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _span_key(step_id: str, span) -> str:
    """The span address — ``{step_id}/{source}/{role}/{start}`` (start is the
    span's exact wire decimal). ``(step, source, role)`` alone collides on
    the POC fixture (step b8 carries two ``instruction`` excerpts on one
    source); adding ``start`` matches ``edits.py``'s span identity triple."""
    return f"{step_id}/{span.source}/{span.role}/{span.start}"


def _decimals_equal(a: str, b: str) -> bool:
    return Fraction(a) == Fraction(b)


# ── the default media store ─────────────────────────────────────────────────


class DirStore(MutableMapping):
    """Minimal ``MutableMapping[str, bytes]`` over files under a root
    directory, keyed by relative POSIX paths (``media/b4.mp4``).

    The default backend of the ADR-0005 store seam — stdlib-only so the
    pydantic-only core stays intact (ADR-0004). Inject a ``dol``/``s3dol``
    store for other backends; the key contract (document-relative POSIX uri)
    is backend-independent.
    """

    def __init__(self, rootdir: str | Path):
        self.rootdir = Path(rootdir)

    def _path(self, key: str) -> Path:
        pure = PurePosixPath(key)
        if pure.is_absolute() or ".." in pure.parts:
            raise ValueError(f"store keys are relative POSIX paths, got {key!r}")
        return self.rootdir.joinpath(*pure.parts)

    def __setitem__(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def __getitem__(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise KeyError(key)
        return path.read_bytes()

    def __delitem__(self, key: str) -> None:
        path = self._path(key)
        if not path.is_file():
            raise KeyError(key)
        path.unlink()

    def __contains__(self, key) -> bool:
        return isinstance(key, str) and self._path(key).is_file()

    def __iter__(self) -> Iterator[str]:
        if not self.rootdir.is_dir():
            return
        for path in sorted(self.rootdir.rglob("*")):
            if path.is_file():
                yield path.relative_to(self.rootdir).as_posix()

    def __len__(self) -> int:
        return sum(1 for _ in self)


# ── preflight ───────────────────────────────────────────────────────────────


def check_media_requirements() -> dict:
    """Two-channel media preflight (ADR-0005 §2), reported distinctly:

    - ``bundled_ffmpeg`` — the pip-bundled imageio-ffmpeg binary, which is
      all `derive` needs (mp4/gif via mixing; posters via cv2).
    - ``system_ffmpeg`` — a PATH ffmpeg, which `derive` does NOT need but
      ``measure_grid`` on non-wav input does (pydub knows nothing of the
      bundled binary). A bundled-only check would report healthy on a
      machine where ``measure_grid("video.mp4")`` fails.
    """
    notes: list[str] = []
    try:
        import mixing  # noqa: F401
    except ImportError:
        return {
            "ok": False,
            "bundled_ffmpeg": None,
            "system_ffmpeg": None,
            "notes": [
                "mixing is not installed — install the media extra: "
                "pip install paces[media]"
            ],
        }
    import shutil

    bundled = None
    try:
        from mixing.util import ffmpeg_exe

        bundled = ffmpeg_exe()
    except Exception as error:
        notes.append(f"no bundled ffmpeg ({error}); derive cannot encode")
    system = shutil.which("ffmpeg")
    if system is None:
        notes.append(
            "no system ffmpeg on PATH: derive is unaffected, but "
            "measure_grid on non-wav media (e.g. an .mp4) will fail — "
            "pydub needs a PATH ffmpeg"
        )
    return {
        "ok": bundled is not None,
        "bundled_ffmpeg": bundled,
        "system_ffmpeg": system,
        "notes": notes,
    }


# ── derivation ──────────────────────────────────────────────────────────────


@dataclass
class DeriveResult:
    """What a derive run did: the updated document, the honesty flags, and
    one row per derived (or byte-stably reused) span."""

    document: StepDocument
    flags: list[str] = field(default_factory=list)
    derived: list[dict] = field(default_factory=list)


def _walk_steps(steps: list[Step]) -> Iterator[Step]:
    for step in steps:
        yield step
        yield from _walk_steps(step.steps)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _excerpt_spans(step: Step) -> list:
    return [span for span in step.spans if span.excerpt is not None]


def _artifact_base(step: Step, ordinal: int, count: int) -> str:
    """Deterministic, step-derived artifact stem: ``b4`` for the common
    single-excerpt step, ``b8.1``/``b8.2`` when a step carries several.
    Step/role-derived — never hash-derived: the uri is the artifact's merge
    identity in ``edits.py`` and must survive regeneration."""
    return step.id if count == 1 else f"{step.id}.{ordinal}"


_ARTIFACT_LOCK = re.compile(r"^/artifacts/(\d+)(/|$)")


def _locked_artifact_indices(step: Step) -> set[int]:
    return {
        int(match.group(1))
        for lock in step.locks
        if (match := _ARTIFACT_LOCK.match(lock.path))
    }


def _upsert_artifact(step: Step, ref: ArtifactRef, flags: list[str]) -> None:
    """Update-by-uri or append; never reorder, never delete — index-form
    artifact locks stay valid, and a locked entry is kept verbatim."""
    locked = _locked_artifact_indices(step)
    for i, existing in enumerate(step.artifacts):
        if existing.uri == ref.uri:
            if i in locked:
                flags.append(f"locked-artifact-kept:{step.id}:{ref.uri}")
            else:
                step.artifacts[i] = ref
            return
    step.artifacts.append(ref)


def _stale_artifact_flags(
    step: Step, produced_uris: set[str], flags: list[str]
) -> None:
    """Flag (never remove) derived-looking artifacts this run no longer
    produces — report, don't repair."""
    family = re.compile(rf"^{MEDIA_PREFIX}/{re.escape(step.id)}(\.\d+)?\.[a-z0-9]+$")
    for artifact in step.artifacts:
        if artifact.uri in produced_uris:
            continue
        if artifact.derived_from and family.match(artifact.uri):
            flags.append(f"stale-artifact:{step.id}:{artifact.uri}")


def _media_paths(doc: StepDocument, media) -> dict[str, Path]:
    """Resolve ``media`` (one path, or ``{source_id: path}``) to the source
    ids that excerpt-bearing spans actually reference."""
    referenced = sorted(
        {
            span.source
            for step in _walk_steps(doc.steps)
            for span in _excerpt_spans(step)
        }
    )
    if not referenced:
        return {}
    if isinstance(media, dict):
        mapping = {str(k): Path(v) for k, v in media.items()}
        unknown = sorted(set(mapping) - {s.id for s in doc.sources})
        if unknown:
            raise ValueError(
                f"media maps unknown source ids {unknown}; "
                f"document sources: {sorted(s.id for s in doc.sources)}"
            )
    else:
        if len(referenced) > 1:
            raise ValueError(
                "one media path was given but excerpt spans reference "
                f"several sources {referenced}; pass media as a mapping "
                '{"<source-id>": "<path>"}'
            )
        mapping = {referenced[0]: Path(media)}
    for source_id, path in mapping.items():
        if not path.is_file():
            raise ValueError(f"media file for source {source_id!r} not found: {path}")
    return mapping


def _verify_media_identity(
    doc: StepDocument, media_paths: dict[str, Path], flags: list[str]
) -> dict[str, str]:
    """SHA-256 each media file; refuse a mismatch with the document's
    recorded ``Source.asset_id`` (the timings were measured on OTHER bytes),
    record the hash when the document has none."""
    hashes: dict[str, str] = {}
    sources = {source.id: source for source in doc.sources}
    for source_id, path in media_paths.items():
        digest = _sha256_file(path)
        hashes[source_id] = digest
        source = sources.get(source_id)
        if source is None:
            continue
        if source.asset_id is None:
            source.asset_id = digest
            flags.append(f"media-identity-recorded:{source_id}")
        elif source.asset_id != digest:
            raise ValueError(
                f"media file {path} has sha256 {digest[:12]}… but the "
                f"document records source {source_id!r} as "
                f"{source.asset_id[:12]}… — the document's timings were "
                "measured on different bytes. Point at the right media, or "
                "clear the source's assetId to accept this file."
            )
    return hashes


def _reconcile_recipe(
    recipes: RecipesFile,
    key: str,
    *,
    window: tuple[str, str],
    frame_size: tuple[int, int],
    media_hash: str,
    locate: Callable[[], Box | None],
    locator_name: str,
    aspect: float,
    pad: float,
    flags: list[str],
) -> Box | None:
    """ADR-0005 §3's re-run semantics. Returns the box to cut with."""
    entry = recipes.entries.get(key)
    if entry is not None:
        identity_known = entry.source_asset_id is not None
        if not identity_known:
            flags.append(f"recipe-identity-unverified:{key}")
        matches = (
            _decimals_equal(entry.window[0], window[0])
            and _decimals_equal(entry.window[1], window[1])
            and (entry.frame_width, entry.frame_height) == frame_size
            and (not identity_known or entry.source_asset_id == media_hash)
        )
        if entry.locked:
            if not matches:
                flags.append(f"recipe-drift-locked:{key}")
            return entry.box  # verbatim — never re-run through the policy
        if matches:
            return entry.box
        flags.append(f"recipe-refreshed:{key}")
    box = locate()
    recipes.entries[key] = CropRecipe(
        box=box,
        window=window,
        frame_width=frame_size[0],
        frame_height=frame_size[1],
        source_asset_id=media_hash,
        locator=locator_name,
        params={
            "lo": decimal_str(ENVELOPE_LO),
            "hi": decimal_str(ENVELOPE_HI),
            "pad": decimal_str(pad),
            "aspect": decimal_str(aspect),
        },
    )
    return box


def derive_document(
    document: StepDocument,
    *,
    media,
    doc_path: str | Path | None = None,
    media_store: MutableMapping | None = None,
    recipes_path: str | Path | None = None,
    subject_locator: SubjectLocator | None = None,
    aspect: float = DFLT_ASPECT,
    pad: float = DFLT_PAD,
    roles: tuple[str, ...] = DFLT_ROLES,
) -> DeriveResult:
    """Derive media for every excerpt-bearing span and return the updated
    document (the caller persists it; media and recipes are written here).

    Args:
        document: the committed document (worked on a deep copy).
        media: local media — one path when exactly one source carries
            excerpts, else ``{source_id: path}``.
        doc_path: the document's file path — the anchor for the default
            media store (``<dir>/media/``) and recipes sidecar
            (``<dir>/<stem>.recipes.json``). Without it, ``media_store``
            AND ``recipes_path`` must be given explicitly: a document that
            arrived as data has no directory, and deriving into cwd
            silently would make every written uri a lie (ADR-0005 §1).
        media_store: ``MutableMapping[str, bytes]`` keyed by
            document-relative POSIX uri. Default: :class:`DirStore` beside
            the document.
        recipes_path: the crop-recipes sidecar path.
        subject_locator: the ADR-0005 §3 seam; default :func:`full_frame`
            (no crop).
        aspect: crop aspect (w/h) the policy forces — only when a locator
            yields regions; never applied to a locked or full-frame box.
        pad: padding fraction around the envelope.
        roles: which artifact roles to produce, of ``("clip", "gif",
            "poster")``.
    """
    unknown_roles = set(roles) - set(DFLT_ROLES)
    if unknown_roles:
        raise ValueError(
            f"unknown roles {sorted(unknown_roles)}; choose from {DFLT_ROLES}"
        )
    if doc_path is not None:
        doc_dir = Path(doc_path).parent
        if media_store is None:
            media_store = DirStore(doc_dir)
        if recipes_path is None:
            recipes_path = doc_dir / f"{Path(doc_path).stem}.recipes.json"
    if media_store is None or recipes_path is None:
        raise ValueError(
            "derive needs an anchor: pass doc_path (a document file path), "
            "or both media_store= and recipes_path= explicitly — a document "
            "given as data has no directory to put media/ next to"
        )
    requirements = check_media_requirements()
    if not requirements["ok"]:
        raise RuntimeError(
            "media requirements not met: " + "; ".join(requirements["notes"])
        )
    import mixing

    locator = subject_locator if subject_locator is not None else full_frame
    locator_name = getattr(locator, "locator_name", None) or getattr(
        locator, "__name__", "custom"
    )

    doc = document.model_copy(deep=True)
    result = DeriveResult(document=doc)
    flags = result.flags

    media_paths = _media_paths(doc, media)
    media_hashes = _verify_media_identity(doc, media_paths, flags)
    frame_sizes: dict[str, tuple[int, int]] = {
        source_id: tuple(mixing.get_video_dimensions(str(path)))
        for source_id, path in media_paths.items()
    }

    recipes = load_recipes(recipes_path)
    current_keys: set[str] = set()

    for step in _walk_steps(doc.steps):
        spans = _excerpt_spans(step)
        produced: set[str] = set()
        for ordinal, span in enumerate(spans, start=1):
            key = _span_key(step.id, span)
            current_keys.add(key)
            if span.source not in media_paths:
                flags.append(f"no-media:{step.id}/{span.source}")
                continue
            start_str, end_str = span.excerpt
            start_s = float(Fraction(start_str))
            end_s = float(Fraction(end_str))
            if end_s <= start_s:
                flags.append(f"invalid-excerpt:{key}")
                continue
            media_path = media_paths[span.source]
            frame_size = frame_sizes[span.source]

            def _locate() -> Box | None:
                observation = locator(
                    LocateQuery(
                        media_path=str(media_path),
                        start_s=start_s,
                        end_s=end_s,
                        frame_width=frame_size[0],
                        frame_height=frame_size[1],
                        step_id=step.id,
                        tags=tuple(step.tags),
                    )
                )
                return resolve_crop_box(
                    observation, frame_size=frame_size, aspect=aspect, pad=pad
                )

            box = _reconcile_recipe(
                recipes,
                key,
                window=(start_str, end_str),
                frame_size=frame_size,
                media_hash=media_hashes[span.source],
                locate=_locate,
                locator_name=locator_name,
                aspect=aspect,
                pad=pad,
                flags=flags,
            )

            base = _artifact_base(step, ordinal, len(spans))
            refs = _derive_span_media(
                media_path,
                start_s=start_s,
                end_s=end_s,
                box=box,
                base=base,
                roles=roles,
                span_role=span.role,
                window=(start_str, end_str),
                store=media_store,
                flags=flags,
            )
            for ref in refs:
                _upsert_artifact(step, ref, flags)
                produced.add(ref.uri)
            result.derived.append(
                {
                    "step": step.id,
                    "span": key,
                    "uris": sorted(ref.uri for ref in refs),
                    "box": list(box) if box else None,
                }
            )
        if produced:
            # only when this run actually derived for the step — a span
            # skipped for missing media must not smear its existing
            # artifacts as stale
            _stale_artifact_flags(step, produced, flags)

    for key in sorted(set(recipes.entries) - current_keys):
        flags.append(f"recipe-orphaned:{key}")

    if recipes.entries or Path(recipes_path).exists():
        save_recipes(recipes, recipes_path)
    return result


def _derive_span_media(
    media_path: Path,
    *,
    start_s: float,
    end_s: float,
    box: Box | None,
    base: str,
    roles: tuple[str, ...],
    span_role: str,
    window: tuple[str, str],
    store: MutableMapping,
    flags: list[str],
) -> list[ArtifactRef]:
    """Cut/encode one span's artifacts through mixing, write bytes through
    the store, and return the refs. Re-encoding is skipped when every
    requested uri already exists in the store (byte-stable re-runs: x264 is
    not deterministic, so re-encoding would churn every ``asset_id``)."""
    import mixing

    uris = {role: f"{MEDIA_PREFIX}/{base}{_EXT[role]}" for role in roles}
    try:
        all_present = all(uri in store for uri in uris.values())
    except (TypeError, NotImplementedError):
        all_present = False  # a write-only store: always encode

    duration = decimal_str(float(Fraction(window[1]) - Fraction(window[0])))
    refs: list[ArtifactRef] = []

    if all_present:
        flags.append(f"reused-media:{base}")
        payloads = {role: store[uri] for role, uri in uris.items()}
        clip_dims = (None, None)
        if "clip" in roles:
            # probe dims from the stored bytes (backend-agnostic), so a
            # byte-stable re-run does not erase width/height from the refs
            with tempfile.TemporaryDirectory() as tmp:
                probe_path = Path(tmp) / f"{base}.mp4"
                probe_path.write_bytes(payloads["clip"])
                clip_dims = tuple(mixing.get_video_dimensions(str(probe_path)))
        dims = {"clip": clip_dims, "poster": clip_dims, "gif": (None, None)}
    else:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            produced: dict[str, Path] = {}
            if "clip" in roles or "poster" in roles:
                clip_path = tmp_dir / f"{base}.mp4"
                mixing.crop_video(
                    str(media_path),
                    start_s,
                    end_s,
                    crop_box=box,
                    output=clip_path,
                    logger=None,
                )
                produced["clip"] = clip_path
            if "poster" in roles:
                poster_path = tmp_dir / f"{base}.jpg"
                mixing.save_frame(
                    str(produced["clip"]),
                    (end_s - start_s) / 2,
                    output=str(poster_path),
                    image_format="jpg",
                )
                produced["poster"] = poster_path
            if "gif" in roles:
                gif_path = tmp_dir / f"{base}.gif"
                mixing.make_gif(
                    str(media_path), start_s, end_s, crop_box=box, output=gif_path
                )
                produced["gif"] = gif_path
            payloads = {role: produced[role].read_bytes() for role in roles}
            clip_dims = (
                tuple(mixing.get_video_dimensions(str(produced["clip"])))
                if "clip" in produced
                else (None, None)
            )
            dims = {
                "clip": clip_dims,
                "poster": clip_dims,  # the poster is a frame OF the clip
                "gif": (None, None),  # scaled by make_gif; honesty over guess
            }
        for role in roles:
            store[uris[role]] = payloads[role]

    for role in roles:
        data = payloads[role]
        width, height = dims.get(role, (None, None))
        refs.append(
            ArtifactRef(
                role=role,
                uri=uris[role],
                asset_id=hashlib.sha256(data).hexdigest(),
                mime=_MIME[role],
                width=width,
                height=height,
                duration_s=duration if role in ("clip", "gif") else None,
                derived_from=span_role,
            )
        )
    return refs
