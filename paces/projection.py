"""The projection from analysis result to document: ``to_document``.

A :class:`~paces.segment.Segmentation` is the *analysis result*; a
:class:`~paces.model.StepDocument` is the *artifact* — committed, hand-edited,
rendered. Keeping them separate (one function between) is what lets the
segmenter re-run without touching hand-edited captions
(``docs/alignment/07 §9.1`` decision 6).
"""

from __future__ import annotations

from collections.abc import Mapping

from paces.model import (
    decimal_str,
    Measure,
    Origin,
    Source,
    SourceSpan,
    Step,
    StepDocument,
    seconds_per_unit,
)
from paces.segmenters import SegStep, Segmentation

#: Decimal places kept when converting computed seconds to wire decimals —
#: matches the POC's 0.1 s working resolution with headroom.
DECIMAL_PLACES = 3


def _dec(value: float, *, places: int = DECIMAL_PLACES) -> str:
    return decimal_str(value, places=places)


def _as_source(source, *, default_id: str = "source") -> Source:
    if isinstance(source, Source):
        return source
    if isinstance(source, Mapping):
        return Source.model_validate(dict(source))
    uri = source or ""
    return Source(id=default_id, kind="url", uri=uri)


def to_document(
    seg: Segmentation,
    *,
    doc_id: str = "guide",
    title: str = "",
    source=None,
    domain: str = "generic",
    lang: str = "en",
) -> StepDocument:
    """Project a segmentation into a fresh step document.

    *source* is the media the spans refer into: a URI string, a
    :class:`~paces.model.Source`, or a mapping. Hand edits belong on the
    returned document, never back on the segmentation.
    """
    src = _as_source(source)
    spu = seconds_per_unit(seg.grid) if seg.grid is not None else None

    def _duration_of(step: SegStep) -> Measure:
        units = step.evidence.get("duration_units")
        if units is not None and seg.unit != "seconds":
            return Measure(value=_dec(float(units)), unit=seg.unit)
        length_s = sum(end - start for start, end in step.spans)
        if spu and seg.unit != "seconds":
            return Measure(value=_dec(length_s / spu), unit=seg.unit)
        return Measure(value=_dec(length_s), unit="second")

    def _convert(step: SegStep) -> Step:
        return Step(
            id=step.id,
            name=step.name,
            duration=_duration_of(step),
            spans=[
                SourceSpan(source=src.id, start=_dec(start), end=_dec(end))
                for start, end in step.spans
            ],
            steps=[_convert(child) for child in step.children],
            origin=Origin(
                generated_by=f"segmenter:{seg.method or step.source}",
                confidence=step.confidence,
            ),
        )

    return StepDocument(
        id=doc_id,
        title=title or doc_id,
        lang=lang,
        domain=domain,
        metric=seg.grid,
        sources=[src],
        steps=[_convert(step) for step in seg.steps],
    )
