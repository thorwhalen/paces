# ADR-0005 — Media derivation: where media lands, how CI encodes, what the locator seam is

Status: **Accepted** (2026-08-30). Settles the three design calls named by
issue #1 and the 2026-08-29 handoff, each adversarially reviewed before code.
Amends the media-location bullets of docs/06 §8 and docs/07 §6.5 (see §1.4).

## 1. Where derived media lands: next to the document, through a store seam

**Decision.** Derived media (`media/*.mp4|.gif|.jpg`) is written to a
`media/` directory **next to the document** by default. Code addresses the
bytes through an injected `Mapping[str, bytes]`-shaped store whose **key IS
the document-relative uri** (`media/b4-1.mp4`, POSIX `/` on every platform);
the default store is a ~10-line stdlib pathlib mapping rooted at the
document's directory — **not** dol, keeping ADR-0004's pydantic-only core
intact. A dol/s3dol store is injectable by callers.

**Why doc-adjacent.** `ArtifactRef.uri` is *specified* document-relative
("relative to the document — deploy-portable", model.py) and `edits.py` uses
the uri as an artifact's merge identity; the rendered practice page is
written next to the document and references clips relatively (file://
portability is the acceptance criterion of #1/#3); the POC shipped page+media
as one content unit; and the strongest fleet precedent (`an`'s project mall)
roots derived artifacts in the user's project dir. The app-data-lifecycle
rule ("an app directory contains only code + build output") targets
*deploy-managed app trees*; a user-owned document directory is not one.

**The consequences we accept, stated honestly:**

- The store seam is a one-liner **for writes**. Pointing the root away from
  the doc dir (S3, a data dir) forfeits file:// pages by construction —
  adjacency then becomes a serve/deploy concern (a `media/*` mapping).
- **Server-side clause**: when documents live inside a deploy-managed tree
  (the future HTTP surface, issue #8), deployments must inject a non-doc
  store root plus a serve mapping. *That* is the scenario where docs/06 §8's
  `~/.local/share` recommendation is correct.
- Artifact filenames come from **span identity, never position or hash** —
  the uri is merge identity and must be stable across regenerations;
  `asset_id` records content change. A single-excerpt step gets the bare
  step id (`media/b4.mp4`); a multi-excerpt step suffixes each span's
  identity (`media/b8--instruction--0.2.mp4`). Ordinals were rejected by
  adversarial review: inserting or deleting a span reassigned neighbours'
  uris and — combined with byte reuse — served one span another span's
  media. The one accepted rename (a step growing from one excerpt to
  several re-stems the first) is flagged via `stale-artifact`. Derive
  refuses, before any encode, a document where two spans would claim one
  uri or share a `(source, role, start)` identity (`validate_document`
  reports the latter too).
- A document that arrives as a dict/JSON string has no directory: `derive`
  then **requires** an explicit media root (and recipes path) and refuses
  loudly — never a silent default to cwd. An unwritable doc dir raises an
  informative error naming the path and the override; never silent
  relocation.
- `render` warns when its output directory differs from the document's and
  the document carries relative-uri artifacts (the page would show dead
  clips).

**1.4 Reconciliation.** docs/06 §8's location sketch and seam-table row, and
docs/07 §6.5's trailing sentence, said `~/.local/share/stepped/…` for media;
they now defer to this ADR for the *default* (they remain right for the
server-side clause). Issue #1's design bullet is amended by comment. The
`ArtifactRef` docstring's "recipe … keyed by asset_id" describes the
evidence-layer END state (#4); the interim sidecar of §3 diverges in location
and key deliberately, and #4's migration re-keys entries into the store.

## 2. ffmpeg in CI: nothing to install — the exercised paths are pip-only

**Decision.** No `[tool.wads.ops.ffmpeg]` block. Every path `derive` v1
exercises runs without a system ffmpeg:

- mp4 cut/crop: mixing `crop_video` → moviepy → the **pip-bundled
  imageio-ffmpeg binary** (a moviepy dependency; ships static builds for
  linux/macos/win64).
- poster: mixing `save_frame` → cv2 (no ffmpeg at all).
- gif: mixing `make_gif` → the same bundled binary as a subprocess, running
  the POC's palettegen/paletteuse two-pass (single-pass imageio/pillow gifs
  are why moviepy's `write_gif` is not used — palette quality is where the
  POC's small, unbanded loops came from).

Tests run the real mixing path on **synthetic moviepy-built video** (the
mixing-conftest pattern), with media deps imported at module top and the
`[media]` extra mirrored into `[dev]`, so a missing capability **fails, never
skips** (the test_measure.py posture; a silently skipped suite proves
nothing).

**Scope of the guarantee, stated precisely:** fail-not-skip gates publish on
the Linux 3.10/3.12 legs. The Windows leg is `continue-on-error` and absent
from publish's `needs`, so a red Windows job blocks nothing — check it at JOB
level on the PR. And the Windows evidence chain has one unproven link: no
fleet CI run has exercised moviepy-on-Windows with system ffmpeg *absent*
(mixing's leg installs choco ffmpeg, a silent fallback if the bundled exe
were ever invalid); paces' first Windows run of the media tests is the proof
point.

**Triggers for adding the ops block later** (copy mixing's 6-line
`[tool.wads.ops.ffmpeg]`): first use of `make_thumbnail`/subtitles or any
system-ffmpeg subprocess path; a test that feeds pydub a non-wav file (the
`measure_grid`-on-mp4 production path already needs system ffmpeg — pydub
knows nothing of the bundled binary — which is why the preflight below
reports two channels); or a Windows-leg failure of the bundled path.

`paces.derivation.check_media_requirements()` is that preflight: channel 1 =
the bundled binary resolves (the derive paths), channel 2 = `which ffmpeg`
(the pydub/non-wav measure path), reported distinctly — a bundled-only check
would report healthy on a machine where `measure_grid("video.mp4")` fails.

## 3. The `subject_locator=` seam and the crop-recipes sidecar

**Contract (Shape B — locator observes, core decides).**
`subject_locator: Callable[[LocateQuery], SubjectObservation | None]`.
The query carries the local media path, the excerpt window (float seconds —
a computed view, per the `resolve()` precedent), the source frame size, and
the step id/tags as read-only hints. The observation is timed raw evidence:
`samples = ((t_s, (box, box, …)), …)` — one region list per probed instant
(one for a dancer, two for judo, hands+workpiece for cooking; the seam is
deliberately not person-shaped). **`None` means "no crop"** and is the
default locator's honest answer (`full_frame` — a real implementation of the
contract, not a stub) as well as the zero-detections fallback.

The **core** owns the one policy pipeline, written once and locator-agnostic
(the POC measured that per-locator policy is exactly where crops go wrong):
union regions per sample → robust percentile envelope (lo=4 / hi=96) → pad
(0.16) → force aspect (0.8 w/h) → clamp → **one static box per excerpt
window**. The POC's production values are the defaults; named constants, and
recorded per-entry. The one-static-box ruling was measured on **2.5–6 s
loops** ("pans are jittery at these durations") — a long-excerpt subgenre
reopens it deliberately, as a new recipe kind (via `burns`), never by
widening this seam. A `None` observation gets **no policy** — no crop means
genuinely uncropped, not letterboxed.

**Sidecar: `<document-stem>.recipes.json`, next to the document.** Committed
and git-diffable (that is what "hand-overridable, survives re-runs, travels
with a clone" requires; a media-store copy dies with a cache clear). One
entry per excerpt-bearing span, keyed by the span address
**`{step_id}/{source}/{role}/{start}`** — start included because
`(step, source, role)` collides on the repo's own fixture (step b8 carries
two `instruction` excerpts on one source), and `(source, role, start)` is
exactly `edits.py`'s span identity triple. Entry fields: `box`
(`[x, y, w, h]` ints, or null = full frame — a recorded decision), `window`,
`frameWidth`/`frameHeight`, `sourceAssetId` (null = **identity unverified**,
and the drift report says so — `None == None` must never count as a match),
`locator` (name of what produced the box), `params` (lo/hi/pad/aspect as
decimal strings — the sidecar is committed, so the no-floats wire rule
applies), `locked`.

**Re-run semantics (lock precedence stated, not implied):**

- entry exists, not locked, inputs match (window, frame size, and asset id
  when both known) AND the policy matches (`locator` identity and `params`
  — the fingerprint has a reader: a locator upgrade or an aspect/pad change
  re-locates) → reuse `box`, skip the locator entirely. A matching entry
  with no recorded asset id adopts the now-verified hash
  (`recipe-identity-recorded:`), so the unverified state retires instead of
  nagging forever.
- inputs or policy drifted, not locked → re-locate, overwrite, flag
  `recipe-refreshed:`.
- **The byte-reuse gate is the recipe's `media_digest`** — a stamp of what
  the stored media was actually cut with (box + window + source hash),
  written at encode time. Media is reused only when the uris exist AND the
  digest still matches; uri existence alone proves nothing about WHICH
  bytes the store holds, which is how the review's measured blocker served
  a hand-locked crop stale forever (crops.json's failure, reborn once —
  never again).
- drifted **and locked** → keep the box, flag `recipe-drift-locked:` —
  acknowledged ≠ approved.
- **A locked box is used verbatim** — never re-padded, re-aspected, or
  clamped; the stored box is the *final post-policy crop* and `params` are an
  input fingerprint for drift detection only. Accepted consequence:
  hand-locked boxes are exempt from aspect uniformity.
- An entry whose address matches no current excerpt-bearing span is flagged
  `recipe-orphaned:` by name, never silently dropped — a step-id rename
  (which `edits.py` supports) must surface, not discard, a hand-locked box.
- A span skipped this run (missing media, invalid excerpt) keeps its whole
  artifact-name family out of the `stale-artifact` sweep — a false honesty
  flag is the failure mode, since a reader would regenerate healthy media.
- The sidecar serializes `box: null` and `sourceAssetId: null` explicitly
  (no `exclude_none`): they are recorded decisions a hand-editor must be
  able to see and override.
- Hand-override = edit `box`, set `locked: true`. Sidecar locks are
  deliberately weaker than document `Lock`s (no by/at/was) until #4 re-keys
  them into the lacing evidence layer; git history carries reversibility
  until then.

**Licensing.** The pointable replacement is rtmlib/kodokan pose boxes
(rtmlib is Apache-2.0; deps numpy/opencv/onnxruntime, all permissive; its
bundled RTMDet detector means person boxes need no YOLO even for detection).
**A YOLO/ultralytics dependency is barred — AGPL-3.0** (three distributions:
ultralytics, ultralytics-thop, ultralytics-platform); the POC used it as
throwaway session tooling only, which a library cannot. The rtmlib locator is
a follow-up issue; the seam's contract is pinned now by fake-locator tests.

## 4. What mixing grew for this (its first customer is #1)

`make_gif` (two-pass palette, bundled-binary subprocess) and
`crop_box=(x, y, w, h)` on `crop_video`/`Video.save` (spatial crop in the
same encode pass, validated + even-rounded — libx264 rejects odd dims), plus
`ffmpeg_exe()` (bundled-first resolution). Landed in mixing before this ADR's
implementation; paces floors `mixing` accordingly and calls mixing only —
never moviepy/ffmpeg directly (mixing absorbed the moviepy 2.x rename storm;
paces stays insulated). `loop_video` is deliberately unused: looping is the
renderer's `<video loop>` attribute, not a bigger file.
