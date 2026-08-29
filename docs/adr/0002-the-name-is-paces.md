# ADR-0002 — The package is called `paces`

- **Status:** **Accepted.** Decided by thorwhalen, 2026-08-29.
- **Supersedes:** the placeholder `stepped`, and the earlier recommendation `astep`
  (`../08-naming-candidates.md §5`, marked superseded there).

---

## Context

The working name was `stepped` — a placeholder nobody liked. A survey of 684 PyPI-checked
candidates (`../08-naming-candidates.md`) initially recommended `astep`, on the grounds that it
encodes AST + step and so keeps the architecture visible.

The user rejected that reasoning and narrowed the criteria:

> *"astep is great but the AST idea wasn't for the name, but the architecture. I'd rather the
> name be reminiscent of **what the tool does for the user, not how**. Also, I do like **short
> and punchy, and memorable**."*

That rules out the whole parsing/structure family and demotes the domain-technical names
(`kineme`, `spartito`, `korvai`, `laban`) — they describe the material or the mechanism, not
the user's gain.

## Decision

**`paces`.** Verified free on PyPI on 2026-08-28.

The argument, in the user's terms:

- **What it does for you.** *Put it through its paces* — drill it until you own it. That is the
  user's gain, stated in ordinary English, with no reference to how any of it works.
- **And it is literally true of the interface.** The tool **paces** you: the POC's signature
  feature is a metronome walking you through the steps at a tempo you set. One word carries
  both the benefit and the product's most distinctive behaviour.
- **Short, punchy, memorable.** Five letters, plain English, unambiguous to spell and say, no
  collision with a common programming term (unlike `marking`, which is also a markup word).
- **It ages across subgenres.** You put a recipe, a kata, a guitar solo or a rehab protocol
  through its paces too. Nothing about the name is dance-specific — which matters, since the
  first subgenre is dance and the point is to generalise past it.

Runners-up, kept on record in case of a late change of heart: `marking` (best dance-insider
register, `-ing` matches `lacing`, but a very common word and npm is taken); `woodshed`
(warmest and most memorable, names the experience, but longest); `byheart`; `countin`.

## Consequences

- Package name, import name and repo name are all `paces`.
- The package lives at `~/Dropbox/py/proj/t/paces` and joins the `video_gen` federation.
- These docs moved from `pocs/stepped/docs/` to `t/paces/docs/`. Any prose still saying
  "stepped" is stale — treat `paces` as authoritative.
- `../08-naming-candidates.md` stays in the repo as the record of how the decision was reached
  and as a name pool for the sub-packages this work may spawn (the alignment engine of
  `0001` has no name yet).
- **Re-verify and claim the PyPI name before the first release.** Availability was checked on
  2026-08-28 and PyPI moves.
