# Kickoff prompt

*Paste the block below into a fresh Claude Code session started in `~/Dropbox/py/proj/t/paces`.
It is written to be self-contained for an agent with no prior context.*

---

```
We're starting `paces`. Everything you need to not start from scratch is in ./docs — a full
handoff written from a working proof-of-concept, plus research already done. Read before you
build; a lot of what you might otherwise write already exists in the fleet.

WHAT PACES IS

Take instructional media — a video of someone teaching something — plus optionally notes and a
steering prompt. Segment it into named steps, build a structured intermediate representation of
those steps, and render that into learning material: an interactive practice page today, other
guides later. First subgenre is dance; the general case is any step-by-step instruction that
can be segmented out of a video.

The proof-of-concept is live at https://thorwhalen.com/que_calor_dance/ — look at it, it's the
clearest statement of what we're generalising.

READ IN THIS ORDER

  docs/README.md            index, reading order, and the findings that change your starting
                            position — read this first, it will redirect you
  docs/adr/                 the settled decisions. 0003 (video + segmenter) is the one that
                            most shapes the design; 0001 (alignment engine) tells you what
                            already exists so you don't rebuild it
  docs/01-what-was-built.md  the POC, including an incident list where every failure is a
                            requirement in disguise
  docs/03-design-brief.md    the parse -> AST -> render framing, in the user's own words
  docs/07-annotation-model.md  the proposed shape of the AST
  docs/alignment/           the analysis-side research, one file per method family

Two things are deliberately NOT settled and are yours to work out with me: the integration
shape with reelee (a focused package below it? something else?) and what a "segmentation"
actually is as a return type.

WHAT IS ALREADY DECIDED — don't relitigate these without a reason

  * The name is `paces` (adr/0002). Docs written before that say "stepped"; read `paces`.
  * Analysis and rendering are separate phases with a serialisable intermediate representation
    between them — like a parser emitting an AST and a backend interpreting it. Renderers
    depend on the IR, never on the analyser. (adr/0003 context, docs/03 section 1)
  * Segmentation is a SEAM, not a stage: `video + segmenter=`, kept open-closed by a strategy
    pattern. Segmenters draw on intrinsic media features, externally-supplied coordinates,
    information derived from surrounding annotations, or a mix — mixed being the normal case.
    A large family of intrinsic segmenters share one shape (featurize -> reduce -> threshold ->
    regularize) and we should ship that as composable stages. "Ask the user" is a first-class
    implementation, not a fallback. (adr/0003 — read it, it has the user's own words)
  * The steering prompt is a first-class, persisted input — not a CLI flag consumed once.
    (docs/03 section 3)

HOW I WANT THIS BUILT

Follow my usual conventions — read ~/.claude/CLAUDE.md and the skills it points at. In
particular ~/.claude/skills/architecture-first/SKILL.md governs turn 1: decide the seams before
the first commit, each seam one keyword argument defaulting to the strongest implementation
that needs no new dependency. docs/06-surfaces-and-conventions.md has the house style distilled
for this project specifically.

Backend in Python first. Then AI artifacts, web services (qh), MCP (py2mcp), and a frontend —
in that order, and only when asked. In v1 ask only "would this surface need the core to
change?", then build the one surface I asked for.

WHERE TO START

Don't write code first. Do this:

  1. Read docs/README.md and the three ADRs, then tell me — briefly — what you think the
     package boundary is, and whether you agree with the research's hypothesis that paces is a
     focused package below reelee (registering an `nw` genre) rather than a fork or a plugin.
     That decision is expensive to move later, so we settle it before anything else.

  2. Propose the IR schema, and validate it the cheap way: re-express the POC's own
     docs/poc-reference/artifacts/clips.json in it. If the dance case doesn't round-trip, the
     schema is wrong. Watch for the two things a naive model gets wrong — a step has SEVERAL
     source spans (the at-tempo run-through and the slow explanation are the same step seen
     twice), and duration is domain-specific (8-counts here, not seconds).

  3. Propose the `Segmenter` protocol per adr/0003 — the registry, and the featurize/reduce/
     detect/regularize stages for the intrinsic family. Note that `kodokan.segment` and
     `mixing.audio.find_segments` already implement much of that family but NOT as composable
     stages; factoring those two into the shape, rather than writing a third, is the concrete
     first task. If a default is selected automatically, reuse the `Capability(needs, gives)`
     record from docs/alignment/06 rather than inventing a parallel declaration format.

  4. Then, with those agreed, the smallest end-to-end vertical slice that reproduces one block
     of the POC from its inputs.

Flag disagreements with the docs — they were written fast and some of it is inference, marked
as such. I'd rather you argue than comply.
```

---

## Notes for whoever pastes this

- The session that produced the handoff is queryable if the docs fall short —
  `docs/10-session-archaeology.md` has the path and how to interrogate it without blowing up
  a context window.
- `docs/09-subgenre-candidates.md` is deliberately *not* in the reading list. It's roadmap
  material, not v1 material, and pointing a fresh agent at it invites premature generality.
- If the agent proposes building the video-only segmenter first, push back: `adr/0003` argues
  for the que-calor segmenter and the ask-the-user segmenter first, precisely because they are
  maximally different and so the seam that fits both is less likely to be shaped around one.
