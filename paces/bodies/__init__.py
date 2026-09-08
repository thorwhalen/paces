"""The body schemas paces registers with ``lacing`` — the evidence layer's vocabulary.

Importing this package registers every URI paces owns into
:mod:`lacing.schema`'s registry. That registry is **one flat, fleet-wide
dict**, ``register_body_schema`` is last-write-wins and silent, and
``annot://schema/beat/v1`` is already ``reelee``'s *narrative* beat — so
every URI paces owns is prefixed ``guide-`` (the thing it describes: a step
guide), and the one URI paces does not own, ``annot://schema/word/v1``, is
reused from :mod:`lacing.bodies` unchanged. The reasoning is issue #4's
decision comment and ``docs/07-annotation-model.md §6.3``.

Tier names are *not* prefixed: tiers are store-local, so ``step``,
``step.sub``, ``cue``, ``beat`` cost nothing and stay exactly as
``docs/07 §6.3`` wrote them.

Two rules hold across every body here:

- **No interval in a body.** Annotations are standoff; the interval lives on
  ``Annotation.reference``. A body that wants to say *when* says it by being
  attached somewhere, never by carrying a number.
- **No floats where the document would refuse one.** Times, durations and
  box coordinates cross as decimal strings, matching the document's
  no-floats wire (``docs/07 §6.5``). ``confidence`` is the one exception the
  document itself already makes.
"""

from paces.bodies.derivation import (
    RECIPE_BODY_SCHEMA_URI,
    RECIPE_TIER,
    GuideRecipeBodyV1,
)
from paces.bodies.document import (
    DOC_BODY_SCHEMA_URI,
    DOC_TIER,
    SOURCE_BODY_SCHEMA_URI,
    SOURCE_TIER,
    GuideDocBodyV1,
    GuideSourceBodyV1,
)
from paces.bodies.signal import (
    BEAT_BODY_SCHEMA_URI,
    BEAT_TIER,
    GRID_BODY_SCHEMA_URI,
    GRID_TIER,
    PASS_BODY_SCHEMA_URI,
    PASS_TIER,
    WORD_BODY_SCHEMA_URI,
    WORD_TIER,
    GuideBeatBodyV1,
    GuideGridBodyV1,
    GuidePassBodyV1,
)
from paces.bodies.step import (
    CUE_BODY_SCHEMA_URI,
    CUE_TIER,
    STEP_BODY_SCHEMA_URI,
    STEP_TIER,
    SUB_STEP_TIER,
    GuideCueBodyV1,
    GuideStepBodyV1,
)

#: Every ``body_schema_uri`` paces *owns*. ``word/v1`` is deliberately absent:
#: it is lacing's, reused rather than claimed. Pinned by
#: ``tests/test_evidence_schemas.py`` against a committed JSON Schema snapshot,
#: so a rename or a field change fails the build (issue #4).
PACES_BODY_SCHEMA_URIS = (
    DOC_BODY_SCHEMA_URI,
    SOURCE_BODY_SCHEMA_URI,
    PASS_BODY_SCHEMA_URI,
    STEP_BODY_SCHEMA_URI,
    CUE_BODY_SCHEMA_URI,
    GRID_BODY_SCHEMA_URI,
    BEAT_BODY_SCHEMA_URI,
    RECIPE_BODY_SCHEMA_URI,
)

__all__ = [
    "PACES_BODY_SCHEMA_URIS",
    # document envelope
    "DOC_TIER",
    "DOC_BODY_SCHEMA_URI",
    "GuideDocBodyV1",
    "SOURCE_TIER",
    "SOURCE_BODY_SCHEMA_URI",
    "GuideSourceBodyV1",
    # steps and cues
    "STEP_TIER",
    "SUB_STEP_TIER",
    "STEP_BODY_SCHEMA_URI",
    "GuideStepBodyV1",
    "CUE_TIER",
    "CUE_BODY_SCHEMA_URI",
    "GuideCueBodyV1",
    # measured signal
    "PASS_TIER",
    "PASS_BODY_SCHEMA_URI",
    "GuidePassBodyV1",
    "GRID_TIER",
    "GRID_BODY_SCHEMA_URI",
    "GuideGridBodyV1",
    "BEAT_TIER",
    "BEAT_BODY_SCHEMA_URI",
    "GuideBeatBodyV1",
    "WORD_TIER",
    "WORD_BODY_SCHEMA_URI",
    # derivation
    "RECIPE_TIER",
    "RECIPE_BODY_SCHEMA_URI",
    "GuideRecipeBodyV1",
]
