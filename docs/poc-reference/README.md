# POC reference code and artifacts

*What this is: the actual scripts and data from the session that produced
<https://thorwhalen.com/que_calor_dance/>. **This is not a library and must not be treated as
one** — it is a pile of session tooling, written to be thrown away, kept because the
parameters in it were expensive to find. Read it for the recipes, not the structure.
`../02-technical-recipes.md` explains every one of them.*

Everything ran under `~/.pyenv/versions/3.12.12/envs/p12/bin/python`, from a working directory
containing `source.mp4`.

## `tools/` — the pipeline

| file | what it does | worth keeping? |
|---|---|---|
| `sheet.py` | Labelled contact sheet over a time window — `sheet.py START END STEP OUT.jpg [COLS]`. Every tile stamped with its absolute timestamp. | **Yes.** This is how an LLM looks at video. The timestamps are the whole point. |
| `zsheet.py`, `sheet_crop.py` | Same, cropped to the subject. Written by subagents mid-session to judge a wide shot. | Merge into one tool. |
| `mkclip.py` | Cut + auto-crop + encode one clip as gif/mp4/webp. Holds `crop_box()`: YOLO person boxes → robust percentile envelope → forced aspect → clamp. | **Yes** — `crop_box()` especially. |
| `track.py` | Whole-video person tracking at 5 fps into `boxes.npz`. | **No.** Abandoned: far too slow (>45 min on CPU). Kept as a record of the dead end. |
| `bg.py` | Empty-room plate as an 88th-percentile-per-pixel composite. | Only for *compositing*. Do not use it to *find* the subject — see `../02-technical-recipes.md §7`. |
| `stylize.py` | The anonymisation pipeline, adapted from kodokan and made streaming. Contains the narrowed head-band fix. | **Yes**, with the licensing caveat. |
| `build_media.py` / `build_media_styl.py` / `restyle_clips.py` | Batch drivers: manifest → mp4 + gif + poster for every clip. Three generations of the same script. | As a spec for what the render stage does. |
| `build_page.py` | Renderer. Splices a `MEDIA` map into the source document's own JS and patches its HTML by string surgery. | **Read it, then do the opposite.** It is the clearest possible argument for a real template contract. |
| `shot.py` | Playwright screenshot + console/HTTP error capture. | **Yes.** Verification, and image generation from the page's own CSS. |
| `ship.sh` | Rebuild page → refresh the deploy app dir. | Trivial, illustrative. |

## `artifacts/` — the intermediate representation

| file | what it is |
|---|---|
| `clips.json` | **The POC's entire AST.** 15 entries. `src: "RT" \| "BD"` is run-through vs breakdown — the two-passes-over-the-same-material idea in its crudest form. Analysed in `../07-annotation-model.md`. |
| `crops.json` | `{clip_id: [x, y, w, h]}` — a derived cache, correctly kept out of the semantic model. |
| `transcript.json` | mlx-whisper output for the whole 651 s. Note how it degrades over the music section (hundreds of near-empty segments, invented numbers) and is excellent over the spoken breakdown. |
| `source-video-metadata.json` | Trimmed `yt-dlp --write-info-json`. `availability: "unlisted"` drove a real publishing decision. |

## `render/` — the output side

| file | what it is |
|---|---|
| `rendered-page.html` | The deployed page, self-contained apart from `media/`. The transport/metronome, the per-card clip tabs, and the IntersectionObserver playback are all in here. |
| `og.html`, `icon.html` | Social image and favicon, as HTML screenshotted at DSF 2 by Playwright — so the type and gradient match the page exactly, for free. |
| `howto.html` | The annotated-card infographic. Generated: it takes a screenshot of a real card, reads the real bounding boxes of the annotated elements out of the DOM, and lays the connectors onto those measured anchors. |
| `annotated-card.jpg` | The rendered result of `howto.html`. |

The media itself (mp4/gif/jpg, ~17 MB) is not copied here; it lives in
`~/Dropbox/py/proj/tt/tw_platform/apps/que_calor_dance/frontend/media/`.
