# Alignment research

*What this folder is for: preparation for a possible dedicated **alignment tool** in the
`video_gen` / reelee fleet — the thing that answers "given some artifacts and some media,
which span of the media does each artifact correspond to?". The decision to build it is
recorded as an intent in `../adr/0001-alignment-engine-as-a-fleet-package.md`; **read that
first**, then come here for the method-by-method detail.*

The user's framing of the problem and of the top surface:

> *"This is a very common task in our reelee work: being able to match and align things. More
> specifically … being able to align annotations/artifacts to segments of audio and/or video."*
>
> *"I'm imagining that the highest surface would be an agent that can study the context, what
> is available, and have a list of possible methods/algorithms/tools it could use. It could use
> beats. It could use the transcribed words (and transcribe if they're not available). It could
> use some knowledge of the order of the artifacts to be matched. It could use gestures."*

## The files

| file | what it covers |
|---|---|
| **`00-existing-in-fleet.md`** | **Start here.** What the fleet already has. Verdict: the capability doesn't exist as a capability, but nearly every part does — `muvid/align.py` is the v0 registry, `muvid.footage.select_score` is the order-prior solver, `mixing.audio` is the signal layer, `kodokan` is a complete but dormant pose front-end, `lacing` is the settled output substrate. Also argues *separate package vs a module in `lacing`* (§4.3) and concludes separate. |
| `01-text-to-audio-alignment.md` | ASR with word timings, true forced alignment (CTC, MFA, aeneas), **fuzzy paraphrase→transcript matching** (the common reelee case, and the hard one), VAD, diarization. |
| `02-music-rhythm-and-structure.md` | Beats, downbeats, tempo and its octave errors, **phase/offset** (tempo gives spacing, not where bar 1 starts), music structure segmentation, music-vs-speech discrimination, audio-to-audio alignment and fingerprinting. |
| `03-visual-signals.md` | Scene cuts, motion energy and optical flow, **pose estimation and pose→segmentation**, repetition/periodicity detection, gesture and action recognition, hand/object interaction, OCR. This is the file that closes the "we never used gestures" gap. |
| `04-semantic-and-llm-matching.md` | CLIP/SigLIP frame–text scoring, CLAP for audio, video-text retrieval, the **LLM-over-timestamped-contact-sheets** pattern written up as a reusable technique, transcript structure extraction, and confidence calibration. |
| `05-sequence-alignment-algorithms.md` | The algorithm layer under everything else: DTW and subsequence DTW, gapped Needleman–Wunsch, CTC segmentation, Viterbi, **change-point detection with a known segment count**, grid fitting for `(offset, period)`, evidence fusion, and how to evaluate an aligner at all. |
| `06-the-planner-surface.md` | The top surface. Proposes collapsing all five sibling method Protocols into one `Capability(needs, gives, …)` record, a measured ~1.4 s/min context probe, and a deterministic ranked graph walk — with the LLM deliberately outside the control loop. |
| **`07-segmenter-strategies.md`** | **The `video + segmenter` seam** the user settled on. A catalogue of ~16 video-only segmentation families plus six richer input tiers (step list, structured document, steering prompt, chapters/subtitles/**re-watch heatmap**, ask-the-user, escalation), organised by *what input is present* because that is what picks the default. Then the `Segmenter` protocol — reusing `06`'s `Capability` with **two** new products and **seven** new facts and no new fields — the generated default-selection table, and the recommendation: three segmenters in v1, `novelty-k` as the video-only default, **and it deliberately does not name the steps**. |
| `04-evidence/` | Real experiment scripts the semantic agent wrote and ran (SigLIP SO400M, CLAP, VLM scoring, calibration, ASR cue extraction). Kept because the numbers in `04-…md` came from them. Scratch quality — read them as evidence, not as library code. |

## How to use this

These files are a **menu with prices**, not a plan. Each method entry states what signal it
needs, what it produces, its cost per minute of media, its licence, and the failure mode that
will bite. The planner file is what turns the menu into a selection procedure.

Two things worth internalising before reading in depth, both from the POC that motivated all of
this (`../01-what-was-built.md`):

- **The cheapest signal did the most work.** A five-line sub-bass energy ratio separated
  talking-head from music-with-dancing and made everything downstream tractable. Any design that
  reaches for pose or a VLM first will be slower *and* worse.
- **No single method was sufficient.** The answer came from combining a cheap audio feature, a
  beat model, ASR, a vision-language judgement, and the order prior. Fusion and confidence are
  not optional extras — they're the point.
