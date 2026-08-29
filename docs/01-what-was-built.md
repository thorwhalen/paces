# 01 — What was actually built (the POC)

*What this file is for: a factual account of the working proof-of-concept this library
generalises. Read it before designing anything, because several of the design constraints
in `03-design-brief.md` are not arbitrary — they were forced by things that went wrong
here. Everything below was verified in one session; the live result is
<https://thorwhalen.com/que_calor_dance/>.*

---

## 1. The task, as it was given

The user had:

- **A YouTube video** — `https://youtu.be/q_TUyxUhoEw`, 10:51, 1280×720, 30 fps, *unlisted*,
  "Chorégraphie Que Calor", by **Céline Pradeu**, made for a wedding. One person, static
  camera, an attic room.
- **A hand-written HTML document** — `choregraphie.html`, a self-contained "aide-mémoire"
  someone (an earlier Claude session) had already written *from* that video: nine numbered
  blocks of the routine, each with a count in 8s, sub-steps, animated SVG stick figures, and
  a metronome/transport that walks the whole routine.
- **A prompt** carrying the things a document cannot say:
  > *"first the person on the video talks, then she goes through the whole phases, while music
  > is playing, then she breaks them down and explains… Also, know that it may not be exactly
  > as described in the phases — I think she changed a few things."*

The ask: extract a few frames per phase, make a GIF each, put them in the artifact, publish
it at `thorwhalen.com/que_calor_dance`.

**That prompt is the single most important input to preserve in the generalisation.** It
contained the video's macro-structure (talk / run-through / breakdown) and an explicit
warning that the doc and the video disagree. No amount of analysis would have recovered the
first cheaply, and nothing would have recovered the second at all. See
`03-design-brief.md §"The steering prompt is a first-class input"`.

## 2. What was produced

A deployed page with, per block:

- a short **looping video extract**, auto-cropped to the dancer, cartoon-stylized and
  face-anonymised;
- for six of the nine blocks, **two extracts behind a tab** — the move at tempo inside the
  run-through, and the isolated slow demo from the breakdown;
- a **French caption** describing what is visible (not what the doc says should be visible);
- **deep links back into the source video** at both timestamps;
- a **GIF download** of the loop.

Plus, page-wide: the full 2:46 run-through with its music, an 8-count transport running at
the routine's *measured* tempo (129 bpm — the original document guessed 100), a generated
wordmark used as favicon / og:image / launcher tile, and an annotated "how to read a card"
infographic generated from the live DOM.

## 3. The pipeline that produced it

```
                    ┌──────────────────────────────────────────────┐
   video ──────────►│ ANALYSIS                                     │
   doc  ──────────► │  audio features → macro-structure            │
   prompt ────────► │  ASR → what she says, when                   │──► clips.json
                    │  beat tracking → the count grid              │    crops.json
                    │  frame inspection → which window shows what  │    (the "AST")
                    └──────────────────────────────────────────────┘
                                        │
                    ┌───────────────────▼──────────────────────────┐
                    │ RENDERING                                    │
                    │  crop + stylize + encode  → mp4 / gif / jpg  │──► index.html
                    │  template + AST           → page             │    + media/
                    └──────────────────────────────────────────────┘
```

The two halves really were separable in practice: the media was re-rendered **three times**
(plain → stylized → stylized with a narrower privacy mask) without touching `clips.json`,
and the page was rebuilt perhaps a dozen times from the same manifests. That is the
empirical case for the AST split, not a theory.

### 3.1 Analysis — finding the structure

**Macro-structure from audio, in seconds.** A 1-second-frame RMS + sub-bass-ratio profile
over the whole 651 s separated the video instantly:

| span | what it is | how it showed up |
|---|---|---|
| 0–43 s | she talks to camera | speech RMS, bass ratio ~0.02 |
| 44–48 s | silence | RMS ~0.001 |
| **49–219 s** | **the run-through, with music** | steady RMS ~0.05, bass ratio 0.15–0.30 |
| 220–650 s | the spoken breakdown | speech again |

The bass ratio (energy in 30–140 Hz over total) is what makes this trivial: music with a
kick drum has an order of magnitude more sub-bass than speech. This is a five-line feature
and it did more work than anything else in the session.

**Beat grid.** `librosa.beat.beat_track` on the music span returned **129.2 bpm** → one
8-count = 3.715 s.

**Phase origin.** Rather than trusting the count, the origin was solved from a *visual
landmark*: in the refrain the dancer throws both arms overhead once per 2×8, and those
throws are visible in a 2-second-per-frame contact sheet at ≈196, 204, 212 s. Working
backwards through 36 eights gave `t0 = 51.2 s`. Every block boundary then falls out of
`t0 + cumulative_eights × 3.715`, and each boundary was checked against the contact sheets.
An independent subagent later re-derived the same grid (95.8 / 99.5 / 103.3 / 107.0 for
block 4's four eights) from scratch, which is the only reason to trust it.

**ASR.** `mlx_whisper` with `mlx-community/whisper-large-v3-turbo`, `language='fr'`,
45 s for the whole 651 s on an M-series Mac. The transcript of the *breakdown* is what named
the moves — she says "et là c'est genou dedans", "c'est la roue vers l'intérieur, c'est
l'avant-bras qui mouline", "on reprend le marquage sur place du pied". Those phrases became
the captions. During the *music* section Whisper produces garbage (it hallucinates counting
numbers over the beat) — worth knowing, and harmless if you only use the breakdown half.

**Window selection.** Ten subagents, one per block, were each given a run-through window and
a breakdown window, told to generate contact sheets at 0.5 s steps with `tools/sheet.py`,
**look at the images**, and return the best 2.5–6 s sub-window plus a French description of
what is actually visible. This is the part that most resists automation and it is where the
LLM earned its place: an agent rejected the run-through window for block 1 because *"elle est
minuscule au fond à droite et souvent de dos"*, and another noticed the breakdown demo of
block 5 shows only one side, flagging where the second clip should come from. A verification
agent then cross-checked all ten picks for overlap and ordering and caught that blocks 1 and 2
had been assigned the same move.

### 3.2 Rendering

Per clip: locate the dancer (YOLO11s person boxes over the window, robust percentile
envelope, forced 4:5 aspect, padded) → crop from the *source* at that box → stylize →
encode mp4 + gif + poster. Then a Python template splices a `MEDIA` map into the original
document's own JavaScript and writes `index.html`.

Notably the *renderer reused the input document as its template*. The original
`choregraphie.html` was split into head/body/script and patched by string surgery. That was
right for a POC and is exactly the thing to replace with a real template contract.

## 4. What went wrong, and what each failure teaches

These are the expensive lessons. Each one is a requirement in disguise.

| what happened | what it teaches |
|---|---|
| First background-subtraction crop put the dancer at the frame edge — the empty-room plate differed from the live frames on the right side (exposure drift), so the largest connected component was a wall, not a person. Replaced by YOLO person boxes. | **Don't infer the subject from the background.** Use a real detector. The background plate is still useful for *compositing*, not for *finding*. |
| `cv2.stylization` + a full-width head-band blur (inherited from the judo pipeline) smeared the raised arm in blocks 3, 7 and 9 — precisely the arms those clips exist to show. | **A privacy transform can destroy the content.** The anonymisation mask must be aware of what the step is *about*. Fixed by narrowing the band to a window above the shoulder columns. |
| The `<video>` element was in the card-click exclusion list next to `a, button`. It had no controls, so the biggest element on every card silently swallowed clicks. | Found only by writing the annotated-card infographic. **Documenting the UI is a UI test.** |
| A blanket `<meta name="robots" content="noindex">` silently killed every chat-app link preview — WhatsApp/Signal/iMessage scrape through `facebookexternalhit`, which refuses noindex pages. | **"Unlisted" is not one setting.** Scoping noindex to named search engines keeps it out of results while letting a chat render the card. |
| The page shipped with **two** `<meta name="description">` tags. | Generated HTML needs a uniqueness check on singleton head tags. |
| GIFs at 300 px / 10 fps came to 24.6 MB for 15 clips. After stylization (flat backgrounds) the same 15 came to 9.7 MB. | **GIF cost is dominated by background entropy.** mp4 was 20× smaller than gif throughout; the page ships mp4 and offers gif as a download. |
| The document's default tempo was 100 bpm; the routine is 129. At 100 the routine would take 3:31 against an actual 2:46. | **The doc is a hypothesis, not ground truth.** Measure and correct it; record the disagreement. |
| Three of the document's own open questions ("soleil des bras, ou les premiers déhanchés ?") were answered outright by the video. | The analysis should be able to **resolve** input-document uncertainty, not just illustrate it. |

## 5. The shape of the intermediate representation, as it actually was

`clips.json` — 15 entries. This is the POC's whole AST and it is worth reading
(`poc-reference/artifacts/clips.json`):

```json
{
 "id": "b4a", "block": 4, "kind": "main", "src": "RT",
 "start": 103.3, "dur": 5.2,
 "cap": "Jambes tendues bien écartées, le bassin pulse sur place, bras relâchés — et le regard change à chaque 8 (ici : de côté, face, puis vers le haut).",
 "yt_expl": 305, "yt_run": 96,
 "tab": "hanches + regard", "fig": "tete"
}
```

What that flat shape got right, and what it got wrong, is analysed in
`07-annotation-model.md`. In short: `src: "RT" | "BD"` (run-through vs breakdown) encodes
the *two source passes*, which turned out to be the single most load-bearing idea; but the
step identity is smeared across `id`, `block` and `kind` instead of being one thing with
several spans.

`crops.json` — `{clip_id: [x, y, w, h]}`, a pure derived cache. Regenerable, and correctly
kept out of the semantic model.

## 6. Where everything is

| thing | path |
|---|---|
| Reference code | `poc-reference/tools/` (see its README) |
| The AST as it was | `poc-reference/artifacts/clips.json`, `crops.json` |
| ASR output | `poc-reference/artifacts/transcript.json` |
| Rendered page | `poc-reference/render/rendered-page.html` |
| Image generators | `poc-reference/render/{og,icon,howto}.html` |
| The deployed app | `~/Dropbox/py/proj/tt/tw_platform/apps/que_calor_dance/` |
| The full session transcript | see `10-session-archaeology.md` |

The source video and the ~200 MB of intermediates were in a session scratchpad and are
**gone**. The video is re-downloadable (`10-session-archaeology.md` has the exact yt-dlp
invocation, including the flag without which it fails).

---

## Open questions for the next agent

- The nine blocks came from the *input document*, not from analysis. Nothing in this session
  segmented a video into steps without a prior list of steps to align against. **Segmenting
  cold is an unsolved and much harder problem** — decide early whether v1 requires a doc.
- The at-tempo/slow-demo pass structure was given in the prompt. Detecting it automatically
  (music-vs-speech gives a strong signal, as §3.1 shows) is plausible but untested.
- Ten agents looking at contact sheets is accurate and slow: that workflow ran 12 agents
  (the ten pickers, a verifier, and an unrelated deploy-research agent) in ~11 minutes wall
  clock for ~880k subagent tokens total. What is the cheaper 80 % — and is it good enough?
