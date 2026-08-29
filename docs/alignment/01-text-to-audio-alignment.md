# 01 — Aligning TEXT to AUDIO

**Question this file answers:** given a script, transcript, lyric sheet, subtitle file, or a
list of hand-written step descriptions, how do we find *where in the audio* each piece is
spoken or sung — offline, on an Apple-Silicon Mac, in French as well as English?

**Verification legend.** **[verified]** = I ran it in the p12 env on this machine and the
numbers below are my measurements. **[from docs]** = read from official docs/source, not
executed here. **[inferred]** = my judgement; argue with it.

Everything marked [verified] was measured against a 7.2 s French utterance synthesized with
macOS `say -v Thomas`, transcript
*"Ensuite vous revenez face. Et là c'est genou dedans. Donc là c'est la roue vers l'intérieur.
C'est l'avant-bras qui mouline vers soi."* — sentences lifted verbatim from the POC's real
transcript (`02-technical-recipes.md` §5). Scratch scripts:
`/private/tmp/claude-501/-Users-thorwhalen-Downloads/0f75703c-6761-4aa0-b796-aafe02c94155/scratchpad/`.

---

## 0. The one thing to get right: these are THREE different problems

The single most expensive mistake available here is to treat them as one. They need different
tools, and the tool for one silently produces garbage on another.

| # | Problem | You have | You want | Right tool | Wrong tool bites how |
|---|---|---|---|---|---|
| **P1** | **Quote alignment** | Text that *is* what was said, verbatim | Word times | **Forced alignment** (CTC) | — |
| **P2** | **Transcript alignment** | Nothing but audio | Text **+** word times | **ASR with word timestamps** | — |
| **P3** | **Paraphrase alignment** | Text that *describes* what was said | Spans | **Embeddings + order prior** | Forced alignment returns a **confident-looking, meaningless** answer |

**P3 is the common reelee case and the hard one.** A step is written *"main sur le genou"*;
the teacher says *"et là c'est genou dedans"*. Those share one content word. §3 is the long
section because P3 is where the value is.

**The decisive measurement [verified].** I forced-aligned five different texts against the
same French audio using `VOXPOPULI_ASR_BASE_10K_FR`, and looked at whether the per-word
confidences reveal that the text is wrong:

| Text supplied to the aligner | mean word conf | median | **frac(conf < 0.5)** |
|---|---|---|---|
| Exact ground truth | 0.823 | 0.873 | **0.07** |
| Ground truth + 2 ASR-style errors (`genou`→`genoux`) | 0.815 | 0.873 | **0.07** |
| **Paraphrase** (`"main sur le genou. la roue avec l'avant-bras…"`) | 0.463 | 0.463 | **0.65** |
| Entirely unrelated French sentence | 0.450 | 0.472 | **0.67** |
| Wrong language (English) | 0.378 | 0.332 | **0.69** |

Two conclusions, both load-bearing for the design:

1. **`frac(word_conf < 0.5)` is a clean text-matches-audio detector.** 0.07 vs 0.65+ is not a
   marginal separation; a threshold anywhere in 0.15–0.5 works. **Every forced-alignment
   method in this package must return this number and the facade must check it.** Without it
   the method cannot tell the caller it was handed the wrong kind of input.
2. **Paraphrase scores the same as completely unrelated text.** Forced alignment does not
   degrade gracefully into fuzzy matching — it degrades into *confident nonsense*. It will
   place a word that was never spoken, at a precise timestamp, with a plausible-looking span.
   This is the failure mode that will bite hardest, because the output *looks* fine.

---

## 1. ASR with word timestamps (problem P2)

### 1.1 What each engine actually gives you

| Engine | In env? | Word times? | How it derives them | Licence |
|---|---|---|---|---|
| **mlx-whisper** 0.4.3 | **yes** | yes, `word_timestamps=True` | cross-attention DTW | MIT (Apple MLX) |
| **faster-whisper** 1.2.0 | **yes** | yes, `word_timestamps=True` | cross-attention DTW | MIT |
| **openai-whisper** 20250625 | **yes** | yes | cross-attention DTW | MIT |
| **WhisperX** 3.8.6 | no | yes, **re-derived by wav2vec2 forced alignment** | CTC on a phoneme model | BSD-4 ⚠ |
| **stable-ts** 2.19.1 | no | yes, refined | DTW + silence suppression regrouping | MIT |

**All Whisper word timestamps come from the same trick** [from docs]: Whisper is a
seq2seq model with no native time output, so the timestamps are recovered by running DTW over
the decoder's cross-attention weights against the audio frames. They are an *estimate derived
from attention*, not a measurement. That is why they drift, and why WhisperX exists.

### 1.2 Measured agreement [verified]

All three transcribed the French correctly (modulo `genou`→`genoux` on faster-whisper `small`).
I compared their word **start** times against the CTC forced alignment (§2), treating the
latter as reference, over 18 shared words:

| Comparison | mean signed | MAE | max | within 50 ms | within 100 ms |
|---|---|---|---|---|---|
| mlx large-v3-turbo vs CTC | **−0.071 s** | 0.080 s | 0.140 s | 28 % | 61 % |
| faster-whisper small vs CTC | **−0.059 s** | 0.068 s | 0.160 s | 44 % | 72 % |
| mlx large-v3-turbo vs faster-whisper small | −0.012 s | 0.026 s | 0.120 s | 89 % | 89 % |

Read this carefully, because it is the useful part:

- **The two Whisper engines agree with each other far better than either agrees with CTC**
  (MAE 0.026 s vs 0.068–0.080 s). They share a *method*, so they share a *bias*. Cross-checking
  two Whisper models tells you almost nothing about absolute accuracy.
- **The bias is signed and consistent: Whisper starts words ~60–70 ms EARLY.** It attends to
  the onset region before the phone begins. If you cut clips on raw Whisper word starts you
  will systematically include a sliver of the preceding silence — usually harmless, sometimes
  audible as a click on a tight cut.
- **Whisper word times are good to ~±100 ms, not ~±20 ms.** Fine for "which sentence", fine
  for subtitles, marginal for a beat-accurate cut at 129 bpm where one 8-count is 3.715 s and
  a beat is 464 ms.

### 1.3 Cost [verified]

| Engine / model | Load | Transcribe 7.2 s | RTF | **per minute of audio** |
|---|---|---|---|---|
| mlx-whisper `large-v3-turbo`, `word_timestamps=True` | cached | 2.1 s | 0.29 | **~17 s** |
| faster-whisper `small` int8 CPU, `vad_filter=True` | 0.8 s | 5.0 s | 0.70 | **~42 s** |

mlx-whisper runs on the Apple GPU via MLX and is the clear default on this machine — a
*large* model beating a *small* CPU model by 2.4× is not a close call. The POC measured 45 s
for 651 s of audio (RTF 0.07) with `word_timestamps=False`; **turning word timestamps on cost
roughly 4× there.** Budget for it.

### 1.4 The failure modes that will bite

- **Hallucination over music.** Established in the POC and not re-tested here: over a 170 s
  music run-through Whisper emitted hundreds of near-empty segments and invented counting
  numbers. **Gate ASR to speech spans (§4) rather than cleaning up afterwards.** This is the
  single most important operational rule in this file.
- **Apostrophe subword splitting [verified].** Whisper tokenizes French elisions as separate
  word units: `c'est` comes back as `' c'` + `"'est"`, `l'avant-bras` as `' l'` + `"'avant"` +
  `'-bras'`. Any code that assumes `word` is a whitespace token is wrong for French. Re-join
  on a leading apostrophe before matching.
- **`condition_on_previous_text=True` (the default) propagates a hallucination forward.**
  Once it starts looping it keeps looping. Set `False` for long or noisy media [from docs].
- **Autodetect on bilingual media is a coin flip.** POC finding, worth repeating: the
  choreography video had French speech over a Spanish song. Always pass `language=`.

### 1.5 Snippets

```python
# mlx-whisper — the default on Apple Silicon.  [verified]
import mlx_whisper
r = mlx_whisper.transcribe(
    "audio16k.wav",
    path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
    language="fr", word_timestamps=True, verbose=False,
)
# r["segments"][i]["words"] -> [{"word": " genou", "start": 2.24, "end": 2.54,
#                               "probability": 0.87}, ...]
```

```python
# faster-whisper — when you need VAD, clip gating, or a non-Mac fallback.  [verified]
from faster_whisper import WhisperModel
m = WhisperModel("small", device="cpu", compute_type="int8")
segs, info = m.transcribe("audio16k.wav", language="fr",
                          word_timestamps=True, vad_filter=True)
for s in segs:
    for w in s.words:          # w.word, w.start, w.end, w.probability
        ...
```

### 1.6 WhisperX and stable-ts — worth adding?

**WhisperX** [from docs]: `pip install whisperx` (3.8.6). Pipeline = faster-whisper →
wav2vec2 **CTC forced alignment** of the ASR output → optional pyannote diarization. Its
alignment stage is the interesting part and its default French model is
`VOXPOPULI_ASR_BASE_10K_FR` — **exactly the torchaudio bundle already available here**
(`whisperx/alignment.py:DEFAULT_ALIGN_MODELS_TORCH`). So:

> **Do not add WhisperX for the alignment.** §2 reproduces its French path in ~30 lines with
> zero new dependencies. Add WhisperX only if you want its diarization plumbing, and note it
> pins `pyannote.audio`, `ctranslate2`, `pandas` and `nltk` and is **BSD-4-clause** — the
> advertising-clause variant, which is not a clean fit next to `mixing`'s madmom exclusion.

**stable-ts** [from docs]: `pip install stable-ts` (2.19.1, MIT). Value is *regrouping* and
silence-suppression heuristics over Whisper's own timestamps — nicer subtitle segmentation,
not fundamentally better times. **[inferred]** Not worth a dependency for this package; its
job (turn word times into well-shaped lines) belongs to `lacing`'s `SubtitleBuilder`.

---

## 2. Forced alignment proper (problem P1)

You already have the text. You want times. This is the accurate, cheap, deterministic path —
**and it is available here with no new dependency.**

### 2.1 The headline: torchaudio 2.9.0 does this today

```python
from torchaudio.functional import forced_align, merge_tokens
```

Three verified facts, each a trap:

1. **`forced_align` emits a deprecation warning saying "It will be removed from the 2.9
   release" — and this is torchaudio 2.9.0, and it still works.** [verified] The warning is
   stale. It is nonetheless a real signal: torchaudio is in maintenance
   ([pytorch/audio#3902](https://github.com/pytorch/audio/issues/3902)). **Treat the CTC
   Viterbi as ~40 lines of numpy you may have to vendor**, not as a stable upstream API. Pin
   torchaudio, and put this behind the `Method` seam so replacing it is one file.
2. **`torchaudio.load` is broken here** [verified]: it now dispatches to
   `load_with_torchcodec` and raises `ImportError: TorchCodec is required`. Use `soundfile`:
   ```python
   import soundfile as sf, torch
   d, sr = sf.read(path, dtype="float32"); wav = torch.from_numpy(d)[None, :]
   ```
3. **`merge_tokens(tokens, scores, blank=0)` wants *probabilities*, not log-probs**
   [verified]. Pass `scores.exp()`. `TokenSpan.score` then lands in [0,1] and §0's table
   works. Pass log-probs and you get scores like `−1.36` and every downstream threshold is
   silently wrong.

### 2.2 Which acoustic model — and French matters

| Bundle | Size | Languages | Accents | RTF (CPU) | per min |
|---|---|---|---|---|---|
| **`VOXPOPULI_ASR_BASE_10K_FR`** | **360 MB** | fr only | **native `àéèêçùôîâœûïëüæ`** | **0.045** | **2.7 s** |
| `MMS_FA` | 1.18 GB | ~1100, romanized | **none — raises `KeyError`** | 0.072 | 4.3 s |

Both [verified] end-to-end on the French clip. Sibling bundles exist for `EN`, `DE`, `ES`,
`IT` — the same five WhisperX ships.

**`MMS_FA` raises `KeyError: 'à'` on unromanized French** [verified]. Its label set is
`('-','a','i','e','n','o','u','t','s','r','m','k','l','d','g','h','y','b','p','w','c','v','j','z','f',"'",'q','x','*')`
— ASCII only. You must romanize first, properly with `pip install uroman` (1.3.1.1, the
official companion). An NFKD accent-strip is a workable stand-in for French specifically
[verified — I used one and got a correct alignment], but it is not a general romanizer.

**A silent corruption in the `MMS_FA` path** [verified]: `-` is the *blank* token at index 0,
and it is also an ordinary hyphen in text. `tokenizer(["l'avant-bras"])` happily returns
`[12, 25, 1, 21, 1, 4, 7, **0**, 17, 9, 1, 8]` — a blank embedded mid-word. No error, wrong
alignment. **Strip or split on hyphens before tokenizing.**

**Use `VOXPOPULI_*` when the language is one of the five.** Smaller, faster, more accurate,
no romanization step, and the confidences are directly interpretable. Fall back to `MMS_FA`
+ `uroman` for anything else.

### 2.3 Working French forced aligner, no new dependencies [verified]

```python
"""French word-level forced alignment. torchaudio + soundfile only."""
import re, torch, soundfile as sf
import torchaudio.functional as F
from torchaudio.pipelines import VOXPOPULI_ASR_BASE_10K_FR as B

_model = B.get_model()                      # 360 MB, cached in ~/.cache/torch/hub
_D = {c: i for i, c in enumerate(B.get_labels())}
BLANK = 0

def _prep(text):
    """French text -> (token_ids, [(tok_start, tok_end, word)]).
    The label set has NO apostrophe and NO hyphen, so both split words."""
    t = text.lower().replace("’", "'")
    parts = [p for w in re.split(r"[^a-zà-ÿœæ']+", t) if w for p in w.split("'") if p]
    ids, bounds = [], []
    for w in parts:
        cs = [_D[c] for c in w if c in _D]
        if cs:
            bounds.append((len(ids), len(ids) + len(cs), w)); ids += cs
    return ids, bounds

def align_words(wav_path, text):
    d, sr = sf.read(wav_path, dtype="float32")
    wav = torch.from_numpy(d)[None, :]
    ids, bounds = _prep(text)
    with torch.inference_mode():
        emission, _ = _model(wav)
        logp = torch.log_softmax(emission, dim=-1)
        toks, sc = F.forced_align(logp, torch.tensor([ids], dtype=torch.int32), blank=BLANK)
        spans = F.merge_tokens(toks[0], sc[0].exp(), blank=BLANK)   # .exp() is REQUIRED
    ratio = wav.shape[-1] / emission.shape[1] / sr                  # 0.020 s per frame
    out = []
    for a, b, w in bounds:
        sub = spans[a:b]
        if not sub:
            continue
        n = max(1, sum(s.end - s.start for s in sub))
        conf = sum(s.score * (s.end - s.start) for s in sub) / n
        out.append((w, ratio * sub[0].start, ratio * sub[-1].end, conf))
    return out
```

Real output on the test clip [verified]: `('genou', 2.30, 2.52, 0.78)`,
`('intérieur', 4.42, 4.88, 0.99)`, `('mouline', 6.35, 6.65, 0.92)`. **20 ms resolution**,
0.33 s of compute for 7.2 s of audio.

### 2.4 Limits and the other options

- **Memory is quadratic-ish in utterance length.** The emission tensor is `T × C` at 50 fps,
  and the Viterbi backtrace is `T × L`. **[inferred]** Chunk on VAD boundaries (§4) at ~30 s
  and offset the results; do not hand it a 10-minute file.
- **`forced_align` supports `batch_size == 1` only** [from docs, stated in the docstring].
- **It cannot skip.** Every supplied token *must* be consumed. If your text has a sentence
  the speaker skipped, the aligner distributes it across whatever audio is there and corrupts
  the neighbours too. Guard with §0's confidence check.

| Alternative | Install | Verdict |
|---|---|---|
| **`ctc-segmentation`** 1.7.4 | `pip install ctc-segmentation` | Cython, Apache-2.0. Designed for exactly this and returns per-segment confidence natively. Its advantage over §2.3 is a **skip-tolerant** variant. **[inferred] the one worth benchmarking** if §2.3's rigidity hurts. |
| **Montreal Forced Aligner** 3.x | `conda install -c conda-forge montreal-forced-aligner` | Kaldi-based, phoneme-level, needs a pronunciation dictionary + acoustic model per language (French exists). **Conda-only — will not go into the pip/uv p12 env.** Gold standard for phonetics research; wrong shape for a pip-installable package. |
| **aeneas** 1.7.3.0 | `pip install aeneas` | DTW over MFCCs vs **espeak-synthesized** reference audio. Needs `espeak` + `numpy` headers at build time; **Python 3.12 install is reported broken**, last release 2017. **Do not.** |
| **gentle** | Docker | Kaldi + English only. Not applicable to French. |
| **pyfoal** | `pip install pyfoal` | English only (CMUdict/P2FA lineage). Not applicable. |

---

## 3. Fuzzy text-to-transcript matching (problem P3) — the hard and important one

The artifact is a *paraphrase*, not a quote. §0 proved forced alignment answers confidently
and wrongly here. What actually works is a three-stage pipeline:

> **(a) get a timed transcript (§1) → (b) score every artifact against every transcript line
> → (c) resolve the assignment under the order prior.**

Stage (b) is a similarity matrix. Stage (c) is where most of the accuracy comes from.

### 3.1 Benchmark

Five hand-written French step descriptions against eight timed transcript lines, all wording
taken from or modelled on the POC's real transcript. Ground truth assigned by hand.

| Method | Correct | Cost | Notes |
|---|---|---|---|
| `rapidfuzz.fuzz.token_set_ratio` | **2/5** | 1.4 µs/pair | [verified] |
| `paraphrase-multilingual-MiniLM-L12-v2` (384d) | **4/5** | 13.7 s load, 0.25 s/13 sents | [verified] **already cached in `~/.cache/huggingface`** |
| `paraphrase-multilingual-mpnet-base-v2` (768d) | **5/5** | 31.8 s load | [verified] |
| `intfloat/multilingual-e5-base` (768d) | **5/5** | 23.1 s load, 0.26 s/13 sents | [verified] needs `query:`/`passage:` prefixes |

### 3.2 String matching: use it, but not for this

`rapidfuzz` (MIT, **installed**, 3.14.5) is superb at what it does, and what it does is
surface overlap. Measured on four real artifact/transcript pairs [verified]:

| Artifact → transcript line | `ratio` | `token_set` | `partial_token_set` |
|---|---|---|---|
| `main sur le genou` → `et là c'est genoux dedans` | 43 | 33 | 54 |
| `la roue avec l'avant-bras` → `c'est l'avant-bras qui mouline` | 51 | 65 | **100** |
| `les bras en l'air` → `les deux bras bien haut` | 65 | 65 | **100** |
| `retour face public` → `ensuite vous revenez face` | 47 | 56 | **100** |

**The paraphrase rows score no higher than the noise rows.** And note `partial_token_set_ratio`
saturating at 100 on three unrelated pairs — it is nearly useless as a discriminator here
because it rewards any shared token.

**Where `rapidfuzz` genuinely earns its place** [inferred, but well-founded]:

- **ASR-error tolerance on a near-quote.** `genou`/`genoux` is a 1-edit difference the
  embedding also survives, but on proper nouns and jargon (`"kizomba"`, `"l'avant-bras"`)
  edit distance beats embeddings, which have no vocabulary for them.
- **As a cheap prefilter.** 1.4 µs/pair means a 10 000 × 500 matrix costs ~7 s. Use it to cut
  candidates before paying for embeddings only if you are at that scale — **at reelee scale
  (tens of artifacts, hundreds of lines) just embed everything; it is 0.26 s.**
- **`rapidfuzz.distance.Indel` / `Levenshtein` on normalized text** as one *evidence channel*
  fused with the embedding score, not as the primary signal.

### 3.3 Embeddings: which model, and the gotchas

**Recommended default [inferred, from the benchmark]:
`sentence-transformers/paraphrase-multilingual-mpnet-base-v2`** — 5/5, no prefix ritual,
50+ languages, Apache-2.0, works offline once cached, `sentence-transformers` **is already
installed**.

`multilingual-e5-base` scored identically and encodes faster, but:

- **It requires asymmetric prefixes** — `"query: "` on one side, `"passage: "` on the other
  [from docs, and I used them]. Omit them and quality drops with no error.
- **Its similarities are compressed into a narrow band** [verified]: on my second benchmark
  every value sat in **0.75–0.87**, including obviously-unrelated pairs.
  **Consequence: an absolute similarity threshold is meaningless for e5.** Only within-row
  ranking, or a z-score against the row's own distribution, carries information. This is a
  real trap — a naive `if sim > 0.7: accept` accepts everything.

**The already-cached MiniLM (384d) is the tempting default and it is the wrong one.** It got
4/5, missing `"retour face public"` → `"Ensuite vous revenez face."` by 0.56 vs 0.52 — a
40 ms-of-thought margin in the wrong direction. It is ~4× smaller and ~3× faster; **[inferred]**
offer it as `model="fast"` but do not default to it.

**Gotchas [inferred/from docs]:** first `SentenceTransformer(...)` call downloads from HF, so
a "local" method needs a network on first run — preload in `check_requirements` and fail
loudly offline; set `normalize_embeddings=True` so the dot product *is* cosine; and encode
**whole transcript lines**, not words — these models are trained on sentences.

### 3.4 The order prior — where the accuracy actually comes from

*"The 9 blocks occur in order and do not overlap"* is the strongest information in the whole
problem, and it costs nothing. It turns N independent argmaxes into one constrained
assignment.

```python
"""Monotonic assignment of ordered artifacts to ordered candidate spans."""
import numpy as np

def monotonic_assign(S, *, strict=True):
    """S: (n_artifacts, n_candidates), rows in artifact order, cols in TIME order.
    strict=True  -> distinct, strictly increasing candidates (non-overlapping).
    strict=False -> non-decreasing (several artifacts may share a candidate).
    Returns (col_index_per_artifact, total_score).  O(n*m)."""
    n, m = S.shape
    NEG = -1e18
    dp = np.full((n, m), NEG); bk = np.full((n, m), -1, dtype=int)
    dp[0] = S[0]
    for i in range(1, n):
        best = np.full(m, NEG); arg = np.full(m, -1, dtype=int)
        run_v, run_a = NEG, -1
        for j in range(m):
            jp = j - 1 if strict else j
            if jp >= 0 and dp[i - 1, jp] > run_v:
                run_v, run_a = dp[i - 1, jp], jp
            best[j], arg[j] = run_v, run_a
        dp[i] = S[i] + best; bk[i] = arg
        dp[i][best <= NEG / 2] = NEG
    j = int(np.argmax(dp[n - 1])); out = [j]
    for i in range(n - 1, 0, -1):
        j = int(bk[i, j]); out.append(j)
    return out[::-1], float(dp[n - 1].max())
```

**How much does it buy?** [verified] A synthetic sweep — N ordered artifacts among M=60
candidates, true cell boosted by `margin`, plus two plausible decoys per artifact (the
repeated-vocabulary hazard: the teacher says *"genou"* five times), Gaussian noise on every
cell, 400 trials per row:

| noise | argmax acc | **DP acc** | gain | argmax was monotonic |
|---|---|---|---|---|
| 0.05 | 0.586 | **0.892** | +0.307 | 3 % |
| 0.10 | 0.381 | **0.648** | +0.267 | 0 % |
| 0.15 | 0.242 | **0.429** | +0.186 | 0 % |
| 0.20 | 0.159 | **0.292** | +0.133 | 0 % |
| 0.25 | 0.104 | **0.191** | +0.087 | 0 % |
| 0.40 | 0.059 | **0.119** | +0.060 | 0 % |

and the gain **grows with the number of artifacts** (noise 0.25):

| N artifacts | argmax | **DP** | gain |
|---|---|---|---|
| 3 | 0.118 | 0.141 | +0.022 |
| 5 | 0.118 | 0.165 | +0.047 |
| 9 | 0.110 | **0.215** | +0.105 |
| 15 | 0.111 | **0.271** | +0.160 |
| 25 | 0.111 | **0.384** | +0.274 |

Three things to take from this:

1. **The order prior roughly doubles accuracy across the whole noise range.** It is not a
   tie-breaker, it is the main event.
2. **More artifacts make it stronger, not weaker.** Each additional ordered artifact is another
   constraint. The POC's 9 blocks sit right where it starts paying (+0.105); a 25-step
   walkthrough gets 3.5×.
3. **Raw argmax is essentially never monotonic (0–3 %).** So the DP is not optional polish —
   **without it you do not have a valid answer at all**, you have N independent guesses that
   contradict the known structure. Any honest implementation must run it.

Cost is nothing: **50 artifacts × 4000 candidates in 0.041 s** [verified].

**Caveat on my benchmark honesty:** on the small real 5-step French benchmark the DP changed
nothing, because argmax happened to already be monotonic there. The gain above is measured on
synthetic data where I control the noise. **[inferred]** The real-world regime — repeated
vocabulary, paraphrase-level similarity, ASR noise — sits at noise ≈ 0.15–0.25, where the
table says the prior matters a lot. Validate on real data before believing the exact numbers.

### 3.5 Extensions worth designing for, not building yet

- **`strict=False` for 1:N.** An artifact that recurs (a chorus, a move repeated in the
  breakdown) needs the non-decreasing variant, or a proper semi-Markov DP with durations —
  which **`muvid.footage.select_score._viterbi` already implements** with `[L_min, L_max]`
  constraints, beat snapping and infeasibility classification. Per `00-existing-in-fleet.md`
  §3.3 that is the extraction candidate. Do not write a third DP.
- **Skips and abstention.** Add a per-artifact `null` column at a fixed cost so an artifact
  that is genuinely absent gets `span=None` rather than being forced somewhere. This is what
  makes `Placement.span: Span | None` honest rather than decorative.
- **Word-level refinement.** The DP places an artifact on a *line*. To tighten to the exact
  words, forced-align (§2) *the transcript of that line* — a true quote alignment, P1, where
  §2 is valid — and take the sub-span of the best-matching words. **This is the composition
  that gets you both robustness and 20 ms precision**, and neither method alone gets it.

---

## 4. VAD / speech segmentation (preprocessing)

**This is where the POC's biggest operational rule lives: gate ASR to speech.**

### 4.1 You already have Silero VAD and probably don't know it

**[verified]** `faster-whisper` 1.2.0 **bundles Silero VAD v5 as ONNX weights**:

```
site-packages/faster_whisper/assets/silero_encoder_v5.onnx
site-packages/faster_whisper/assets/silero_decoder_v5.onnx
```

usable standalone, offline, with **no new dependency and no download**:

```python
from faster_whisper.vad import get_speech_timestamps, VadOptions
import soundfile as sf
audio, sr = sf.read("audio16k.wav", dtype="float32")     # must be 16 kHz mono
ts = get_speech_timestamps(audio, VadOptions(
        threshold=0.5, min_silence_duration_ms=300, speech_pad_ms=100))
# -> [{'start': 30720, 'end': 149120}, ...]   SAMPLE indices; divide by sr
```

`VadOptions` defaults [verified]: `threshold=0.5, neg_threshold=None,
min_speech_duration_ms=0, max_speech_duration_s=inf, min_silence_duration_ms=2000,
speech_pad_ms=400`. The 2000 ms default silence and 400 ms padding are tuned for *not cutting
Whisper's context*, not for tight boundaries — **lower both when you want segmentation rather
than ASR preprocessing.**

**Measured** [verified] on a 24.4 s construction (2 s silence | 7.2 s French speech | 2 s
silence | 4 s synthetic bass-heavy "music" | 2 s silence | 7.2 s speech):

- Found exactly the two speech spans: `1.92–9.32` and `17.18–24.41` (true: 2.0–9.2, 17.2–24.4).
  **Boundaries within ~0.1 s.**
- **Correctly rejected the bass-music block.**
- **0.15 s of CPU for 24.4 s of audio — RTF 0.0059, i.e. 0.36 s per minute.** This is free.
  Run it always.

### 4.2 Options compared

| Tool | In env? | Install | Licence | Cost/min | Verdict |
|---|---|---|---|---|---|
| **Silero v5 via `faster_whisper.vad`** | **yes, bundled** | — | MIT | **0.36 s** | **The default. No new dependency.** |
| `silero-vad` 6.2.1 standalone | no | `pip install silero-vad` | MIT | ~same | Only if you drop faster-whisper. Cleaner API, newer weights. |
| `webrtcvad` 2.0.10 | no | `pip install webrtcvad` | BSD-3 | ~0.02 s | Pure energy/GMM. **Fooled by music and noise** — the exact case that matters here. Only for ultra-low-power. |
| `pyannote.audio` VAD | no | see §5 | MIT + gated | ~6–20 s | Better on overlapping/noisy speech; not worth the gate for VAD alone. |

### 4.3 Gating ASR to spans — built in, and the offsets are already right

**[verified]** `faster-whisper` takes `clip_timestamps` directly, and **returns times in the
ORIGINAL media clock** — no offset arithmetic, which is the thing that usually goes wrong:

```python
segs, _ = m.transcribe("mixed.wav", language="fr",
                       clip_timestamps=[2.0, 9.3, 17.2, 24.4])   # [s0,e0,s1,e1,...]
# -> [2.00-9.24] "...", [17.20-24.48] "..."   <- absolute, already correct
```

`mlx_whisper` has **no `clip_timestamps`** [verified — not in its signature]. To gate it you
must slice the audio yourself and add the offset back. **[inferred]** That asymmetry is worth
hiding behind the facade: `transcribe(media, *, within: list[Span])`.

### 4.4 Speech vs music — VAD is not enough

Silero rejected my *synthetic* pure-tone bass block, but **[inferred]** real music with vocals
is a different matter and Silero will mark sung vocals as speech — which is correct behaviour
and wrong for the POC's use case. The POC's **sub-bass energy ratio** (30–140 Hz / total,
~10× for music vs speech, five lines of numpy) is the discriminator that actually worked, and
per `00-existing-in-fleet.md` §2 it should land as a fifth strategy in
`mixing.audio.segmentation`. **Compose: sub-bass ratio for music/speech macro-structure, then
Silero VAD inside the speech regions, then ASR inside those.**

---

## 5. Diarization (several speakers)

**Only needed when "who spoke" disambiguates "which artifact".** The POC had one teacher and
needed none. A two-instructor video, an interview, or a partner dance changes that.

**`pyannote.audio` 4.0.7** is the only serious offline option.

```bash
pip install pyannote.audio            # pulls torch, torch-audiomentations, speechbrain, lightning
```
```python
from pyannote.audio import Pipeline
pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1",
                                use_auth_token=HF_TOKEN)          # token REQUIRED
diar = pipe("audio16k.wav")
for turn, _, spk in diar.itertracks(yield_label=True):
    print(f"{turn.start:.2f}-{turn.end:.2f} {spk}")
```

**The real costs** [from docs / web, **not run here** — it is gated and I did not accept terms
on the user's account]:

| Dimension | Reality |
|---|---|
| **Licence** | Code and models **MIT**. Genuinely open, commercial use permitted. |
| **Gate** | Model repos are **gated on HF**: accept user conditions (company/university + website) and supply a token. Free, but a **human must click it once**, and a machine with no token fails at load. My own probe of `pyannote/speaker-diarization-community-1` returned `HF_FS_ACCESS_DENIED` [verified]. |
| **Offline** | Yes **after** first download; weights cache normally. Pre-seed the cache for air-gapped runs. |
| **Cost** | ~10–30× realtime on CPU, much faster on GPU. **[inferred]** MPS support is partial; expect CPU on this Mac. Budget **tens of seconds per minute**. |
| **Accuracy** | Strong (DER ~10 % on standard benchmarks). Weakest on overlapping speech and on knowing *how many* speakers — pass `num_speakers=` when you know it. |

**When NOT to use it:** one speaker (most reelee media) — it costs 20× more than VAD and adds
a token, a gate, and four heavy dependencies to answer a question you already knew. **[inferred]
Make it an explicitly opt-in method (`consumes=('audio',)`, `cost='gpu'`, `requires=('pyannote.audio',)`),
never part of `"auto"`'s default ladder, and file the HF-token acceptance as a `manual-task`
the first time a build needs it.**

---

## 6. The facade shape

Slots directly into the `Method` protocol in `00-existing-in-fleet.md` §5. Nothing new is
invented here; these are the *text-to-audio* fillings of that contract.

### 6.1 One extra noun: timed text

Every method in this file either produces or consumes "text with times". Name it once.

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class TimedText:
    """Text on a media clock. The universal intermediate of §1-§3."""
    text: str
    span: tuple[float, float]              # seconds, half-open, media clock
    confidence: float = 1.0                # word conf, ASR prob, or similarity
    speaker: str | None = None             # from §5; None when undiarized
    children: tuple["TimedText", ...] = () # words under a line, lines under a section
```

One recursive type covers word / line / section, so a method declares its granularity by what
it fills in rather than by having three result classes. It maps onto `lacing`'s
`(sections, lines, words)` trio without being married to it — which is exactly the
generalization `muvid.align` needs (§3.1 of the sibling doc: *"the tier set is fixed at a
text-shaped hierarchy"*).

### 6.2 Two verbs under the seam

```python
def transcribe(media, *, language=None, within=None, words=True, **kw) -> list[TimedText]:
    """Audio -> timed text (problem P2).  `within` gates to spans (the music-gate rule);
    implementations that lack native clipping slice and re-offset internally."""

def force_align(media, text, *, language, within=None, **kw) -> list[TimedText]:
    """Known-verbatim text -> word times (problem P1).
    MUST populate `confidence` per word so callers can apply the §0 guard."""
```

Problem P3 needs no third verb — it is `transcribe` then the existing `align(artifacts,
media, method="embed-order")`, whose method body is §3.3 + §3.4.

### 6.3 The registry entries this file justifies

| `name` | `consumes` | `requires` | `cost` | licence | solves |
|---|---|---|---|---|---|
| `asr-mlx` | `('audio',)` | `('mlx_whisper',)` | `cheap` (GPU) | MIT | P2 |
| `asr-faster-whisper` | `('audio',)` | `('faster_whisper',)` | `cheap` | MIT | P2, portable fallback |
| `forced-align-ctc` | `('audio','text')` | `('torchaudio','soundfile')` | `cheap` | BSD-2 | P1 |
| `embed-order` | `('transcript','text','order')` | `('sentence_transformers',)` | `cheap` | Apache-2.0 | **P3 — the default** |
| `fuzzy-order` | `('transcript','text','order')` | `('rapidfuzz',)` | `cheap` | MIT | P3 when offline / no model |
| `vad-silero` | `('audio',)` | `('faster_whisper',)` | `cheap` | MIT | preprocessing |
| `diarize-pyannote` | `('audio',)` | `('pyannote.audio',)` | `gpu`+`network` | MIT (gated) | §5, opt-in |

**Every one of these except `diarize-pyannote` runs offline on Apple Silicon with zero new
dependencies.** That is the headline of this file.

### 6.4 One non-negotiable guard

```python
def alignment_is_trustworthy(words: list[TimedText], *, max_low_frac=0.35, low=0.5) -> bool:
    """§0's detector. Below `low` confidence for more than `max_low_frac` of words means the
    text was not spoken in this audio -- return span=None, do not return a confident lie."""
    if not words:
        return False
    return sum(w.confidence < low for w in words) / len(words) <= max_low_frac
```

Measured separation is 0.07 (good text) vs 0.65–0.69 (paraphrase / wrong / wrong-language)
[verified], so 0.35 sits in a wide valley. **`force_align` must call this and abstain**;
otherwise the P1/P3 confusion in §0 becomes silent data corruption.

---

## 7. Recipes

**R1 — Timed transcript of a long noisy video (the POC's step 5, generalized).**
sub-bass ratio → music/speech macro-spans → Silero VAD inside speech → `clip_timestamps` →
mlx-whisper `word_timestamps=True`. Cost ≈ **17 s/min**, dominated by ASR. Zero new deps.

**R2 — A script you know is verbatim (subtitles, lyrics, a read-aloud).**
VAD → chunk at ~30 s → `force_align` per chunk → guard (§6.4) → merge. Cost ≈ **3 s/min**.
**~5× cheaper than R1 and ~3× more accurate in time.** If you have the text, never run ASR.

**R3 — Paraphrased artifacts (the reelee case).**
R1 → embed artifacts and lines with `paraphrase-multilingual-mpnet-base-v2` → similarity
matrix → `monotonic_assign(strict=True)` → **then** R2 on each assigned line to tighten to
words. Cost ≈ R1 + ~1 s. **This is the pipeline the package exists to make one call.**

**R4 — Sanity check, always.** The POC's duration arithmetic caught an error in the *source
document* (44×8 counts @ 100 bpm = 211 s vs a 170 s music span). Generalized: **compare the
total implied by the artifacts against the media duration and warn on disagreement.** Five
lines, no dependencies, and it is the only method in this file that can tell you the *input*
is wrong rather than the output.

---

## 8. Environment: installed vs new dependency

**Present in p12 and sufficient for everything except diarization** [verified by import probe]:
`torch 2.9.0` · `torchaudio 2.9.0` · `transformers 4.57.1` · `sentence-transformers 5.5.1` ·
`mlx-whisper 0.4.3` · `faster-whisper 1.2.0` (**+ bundled Silero VAD v5 ONNX**) ·
`openai-whisper 20250625` · `rapidfuzz 3.14.5` · `librosa 0.11.0` · `soundfile 0.13.1` ·
`onnxruntime 1.23.1` · `numpy 2.2.6` · `scipy 1.16.3` · `scikit-learn 1.7.2` · `nltk 3.9.2` ·
`jiwer` · `demucs 4.1.0`. `torch.backends.mps.is_available() == True`.

**Model weights already cached** [verified]: `mlx-community/whisper-large-v3-turbo`,
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. **Downloaded during this
research** (now cached): `MMS_FA` (1.18 GB), `VOXPOPULI_ASR_BASE_10K_FR` (360 MB),
`paraphrase-multilingual-mpnet-base-v2`, `multilingual-e5-base`.

**Absent, with a recommendation:**

| Package | Install | Add it? |
|---|---|---|
| `uroman` 1.3.1.1 | `pip install uroman` | **Only if** you need `MMS_FA` for a non-Latin language. Not for French. |
| `ctc-segmentation` 1.7.4 | `pip install ctc-segmentation` | **Maybe** — the skip-tolerant alternative to §2.3. Benchmark first. |
| `pyannote.audio` 4.0.7 | `pip install pyannote.audio` | **Only when** multi-speaker media appears. Drags 4 heavy deps + an HF gate. |
| `whisperx` 3.8.6 | `pip install whisperx` | **No.** Its French aligner is already here (§2.2); BSD-4-clause. |
| `stable-ts` 2.19.1 | `pip install stable-ts` | **No.** Regrouping belongs to `lacing`. |
| `silero-vad` 6.2.1 | `pip install silero-vad` | **No.** Bundled in faster-whisper. |
| `webrtcvad`, `aeneas`, MFA, gentle, pyfoal | — | **No.** §4.2, §2.4. |

**Two environment hazards** [verified]: `torchaudio.load` raises `ImportError` without
`torchcodec` — use `soundfile` (§2.1); and `torchaudio.functional.forced_align` warns it will
be removed in 2.9 while working fine in 2.9.0 — pin, and keep it behind the seam.

---

## 9. Open questions

1. **Do we vendor the CTC Viterbi?** torchaudio is in maintenance and `forced_align` already
   carries a (wrong, but pointed) removal notice. It is ~40 lines of numpy. Vendoring removes
   a decaying dependency from the package's most valuable method; not vendoring keeps a C++
   kernel that is much faster. **[inferred]** Vendor a pure-numpy reference as the fallback
   and prefer torchaudio when importable — the same pattern as `mixing`'s lazy librosa.

2. **Where does the acoustic model choice live?** `VOXPOPULI_*` for {en,fr,de,es,it} and
   `MMS_FA`+uroman otherwise is a language→model table. Does the package own that table, or
   does the caller pass `align_model=`? A table makes `language="fr"` sufficient (progressive
   disclosure); it also means the package ships opinions about 1100 languages it has tested
   for one.

3. **Is the 0.35 low-confidence threshold stable across languages and models?** Measured on
   one 7.2 s French clip with one model. The 0.07-vs-0.65 gap is wide enough to be believable,
   but the *absolute* confidences from `MMS_FA` (romanized, 1100-language) will differ from a
   monolingual VoxPopuli model. **Needs a second measurement before it becomes a default.**

4. **Which transcript granularity feeds §3?** I scored artifacts against **transcript lines**
   (Whisper segments). Whisper's segmentation is arbitrary — it splits on its own punctuation
   and 30 s windows, so a "line" is not a semantic unit. Options: fixed-duration windows,
   VAD-delimited utterances, or sentence-split text re-timed from word times. **[inferred]**
   VAD utterances are the most principled and the least tested; this choice probably matters
   more to end-to-end accuracy than the embedding model does.

5. **1:1, or does the DP need durations from day one?** §3.4's `monotonic_assign` assumes each
   artifact takes one candidate. The POC's real structure was "9 blocks covering a contiguous
   170 s span with known 8-count lengths" — that is a *segmentation*, not an assignment, and
   it wants `muvid.footage.select_score._viterbi`. Committing to the simple DP in v1 is honest
   and cheap; committing to the semi-Markov one forces the `muvid` extraction immediately.
   This is open question #3/#4 of `00-existing-in-fleet.md` restated where it bites.

6. **Does the paraphrase benchmark survive contact with real data?** Five steps, eight lines,
   ground truth assigned by me, wording modelled on one POC transcript. mpnet got 5/5 and
   MiniLM 4/5 — **on a sample far too small to separate them.** Before defaulting to a 1 GB
   model over an already-cached 400 MB one, run both over the POC's real 9 blocks and its
   actual breakdown transcript. That data exists.

7. **Should `"auto"` ever pick forced alignment?** Given §0, choosing between P1 and P3
   requires knowing whether the artifact text is a quote or a paraphrase — which the agent
   cannot reliably infer from the text alone. **[inferred]** The safe default is: always run
   the P3 path, and *offer* to tighten with forced alignment, applying the §6.4 guard and
   silently falling back when it trips. That makes the guard load-bearing rather than advisory
   and means a wrong guess costs precision, never correctness.
