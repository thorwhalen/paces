# 05 — Sequence alignment algorithms: exploiting ORDER

**Question this file answers:** the artifacts occur *in sequence*. Which algorithm turns a
pile of noisy per-artifact evidence into one globally consistent placement, and how do I pick
it without reading a textbook?

This is the math layer under every other method family. Beats, ASR, motion energy and LLM
judgement all produce the same thing — **numbers on a shared clock**. Everything in this file
consumes that and produces **boundaries**. Nothing here touches audio or video.

Verification legend: **[verified]** = I ran it in the p12 env and pasted the real output;
**[from docs]** = read from a docstring/source I did not execute; **[inferred]** = my
judgement, argue with it. Every timing below is measured on this Mac (M-series, single core,
p12 env) unless marked otherwise. The verification scripts were scratch and are gone; **every
algorithm they exercised is inlined below in full**, so the next agent can re-run any claim by
pasting the snippet and the synthetic setup described beside it.

---

## 0. The decision table

Read the two questions in the header row against your problem; the cell is your algorithm.

| | **Artifacts are ordered & non-overlapping** | **Order unknown / artifacts may recur** |
|---|---|---|
| **Every artifact has a span; spans tile the media** | **Ordered segmentation DP** (§3) — ~40 lines, exact, 0.13 s for 9 artifacts × 33 min | Hungarian on a chunked media (§8) — and expect nonsense |
| **Some artifacts have no span; some media has no artifact** | **Needleman–Wunsch / Smith–Waterman with gaps** (§5), or Viterbi with a skip transition (§6) | Hungarian with a dummy row/column (§8) |
| **You want boundaries but not labels, and you know how many** | `ruptures.KernelCPD(...).predict(n_bkps=K-1)` (§7) — 0.19 s at n=4800 | same |
| **One short artifact, find it inside a long stream** | **Subsequence DTW** (§4) — `librosa.sequence.dtw(subseq=True)` | same |
| **Artifact and media are two versions of the same continuous thing** | **Plain DTW** (§4) | — |
| **The artifacts are tokens and the media has a frame-level acoustic model** | **CTC segmentation / forced alignment** (§6) | — |
| **The domain has a regular unit (bars, 8-counts, reps)** | **Grid fitting** (§9) *first*, then any of the above with the grid as a boundary constraint | — |

**The single most important line in this file:** the order prior is not a tie-breaker, it is
the thing that makes the problem solvable. In a synthetic 6-artifact / 200 s test where one
artifact had *no signal at all*, the ordered DP still placed all six boundaries correctly,
because the artifact's span was pinned by its neighbours **[verified]**. Argmax-per-artifact
put two artifacts on the same chunk; Hungarian invented a match for the absent one and broke
monotonicity (§5, §8). Order buys you error correction for free.

---

## 1. The one abstraction: a score matrix on a shared clock

Every algorithm below is a function of one of two objects, and *nothing else*:

```python
Span = tuple[float, float]  # seconds, half-open, as in lacing
Clock = tuple[float, float]  # (t0, hop) — frame f is at t0 + f*hop seconds

# (A) an EMISSION matrix: how well artifact k explains frame t
S: np.ndarray  # shape (K, T), higher is better, may contain -inf for "forbidden"

# (B) a BOUNDARY score: how much frame t looks like a cut, independent of artifacts
b: np.ndarray  # shape (T+1,), higher is better; b[0] = b[T] = 0 by convention
```

Everything else — beats, sub-bass ratio, ASR word hits, motion novelty, LLM votes — is a
*producer* of `S` or `b`. This is exactly the `ScoreTensor` shape that already exists at
`/Users/thorwhalen/Dropbox/py/proj/t/muvid/muvid/footage/scoring/grid.py` **[from docs, per
`00-existing-in-fleet.md` §1]**; do not invent a second one.

Choosing the hop is a real decision, not a detail:

| hop | frames per minute | frames for the POC's 10:51 | use for |
|---|---|---|---|
| 0.010 s | 6 000 | 65 100 | word-level / CTC alignment only |
| 0.023 s (librosa default 512/22050) | 2 580 | 28 000 | onsets, beats, spectral novelty |
| **0.5 s** | **120** | **1 302** | **the default for artifact→span work** |
| 1.0 s | 60 | 651 | the POC's sub-bass ratio; too coarse for beat snapping |

**Recommendation [inferred]:** run the solvers at 0.5 s, keep the producers at their native
hop, and resample into the solver clock with an explicit coverage mask. `resample_to_grid` in
`muvid/footage/scoring/grid.py` already does this. Boundary *reporting* precision better than
the solver hop is a lie unless you refine (§3.4).

---

## 2. What the order prior actually asserts

Be precise, because the four assertions have different strengths and different algorithms:

| # | assertion | who needs it | breaks when |
|---|---|---|---|
| **O1** | artifacts are **totally ordered**, and the media respects that order | everything in §3–§6 | the video demonstrates steps out of the document's order; a recap; a montage |
| **O2** | spans are **non-overlapping** | §3 DP, §6 Viterbi | two artifacts describe the same moment from different angles |
| **O3** | spans **tile** the media (no gaps) | §3 DP as written | intro chatter, outro, ads, dead air |
| **O4** | **every** artifact has exactly one span | §3, §4 | "a step described but not demonstrated" |

O1 is the load-bearing one and the only one that is expensive to relax. **O3 and O4 are
cheap to relax** and you should relax them by default:

- Relax **O3** by adding a `K+1`-th "background" artifact whose emission row is a constant,
  and letting it appear between any two real artifacts. Or use §5's gap model.
- Relax **O4** by allowing a skip in the transition (§6) or a gap in the query (§5).

**Do not relax O1 by switching to Hungarian.** Relax it by *segmenting into ordered runs* —
find the recap boundary first, then run an ordered solver inside each run. Order violations
are almost always block-structured, not per-artifact **[inferred, but this is what a recap,
a montage and a chapter reorder all look like]**.

---

## 3. Ordered segmentation DP — the kernel

**This is the default. Write it, own it, and put everything else behind it.**

### 3.1 The recurrence

Segments are `[b_0=0, b_1), [b_1, b_2), …, [b_{K-1}, b_K=T)`. Maximise

```
sum_k  segment_reward(k, b_k, b_{k+1})   +   sum_{k=1..K-1}  boundary_bonus[b_k]
```

subject to `min_len <= b_{k+1} - b_k <= max_len`. When `segment_reward` is an integral of a
per-frame emission — `sum_{t in [i,j)} S[k, t]` — a prefix sum makes it O(1) per query and
the whole DP is **O(K · T · L)** where `L = max_len - min_len + 1`.

```python
import numpy as np


def ordered_segmentation(
    S, boundary_bonus=None, *, min_len=1, max_len=None, allowed=None, soft=False
):
    """Cut a length-T clock into exactly K ordered, contiguous, non-overlapping segments,
    segment k assigned to artifact k.

    S             : (K, T) emission, higher is better. -inf forbids.
    boundary_bonus: (T+1,) score added for an INTERNAL boundary at frame t. b[0]=b[T]=0.
    allowed       : (T+1,) bool mask of legal internal boundary frames (e.g. beat frames).
    soft          : log-sum-exp instead of max -> V[K,T] is log Z, for §11 confidence.

    Returns (V, B). Boundaries: backtrack(B, K, T).
    """
    K, T = S.shape
    P = np.concatenate([np.zeros((K, 1)), np.cumsum(S, axis=1)], axis=1)  # (K, T+1)
    bonus = np.zeros(T + 1) if boundary_bonus is None else boundary_bonus
    max_len = T if max_len is None else max_len
    V = np.full((K + 1, T + 1), -np.inf)
    V[0, 0] = 0.0
    B = np.zeros((K + 1, T + 1), dtype=np.int64)
    for k in range(1, K + 1):
        for t in range(1, T + 1):
            lo, hi = max(0, t - max_len), t - min_len
            if hi < lo:
                continue
            s = np.arange(lo, hi + 1)
            cand = V[k - 1, s] + (P[k - 1, t] - P[k - 1, s])
            if k >= 2:  # b_0 = 0 pays no bonus
                cand = cand + bonus[s]
                if allowed is not None:
                    cand = np.where(allowed[s], cand, -np.inf)
            if soft:
                m = cand.max()
                V[k, t] = (
                    (m + np.log(np.exp(cand - m).sum())) if np.isfinite(m) else -np.inf
                )
            else:
                j = int(np.argmax(cand))
                V[k, t] = cand[j]
                B[k, t] = s[j]
    return V, B


def backtrack(B, K, T):
    b, t = [T], T
    for k in range(K, 0, -1):
        t = B[k, t]
        b.append(t)
    return np.array(b[::-1])
```

That is the whole thing. **No dependency beyond numpy.**

### 3.2 Measured cost **[verified]**

| K (artifacts) | T (frames) | media at 0.5 s/frame | time |
|---|---|---|---|
| 9 | 650 | 5 min | **0.01 s** |
| 9 | 4 000 | 33 min | 0.13 s |
| 30 | 4 000 | 33 min | 0.49 s |
| 9 | 20 000 | 2 h 47 | 1.92 s |
| 100 | 20 000 | 2 h 47 | 23.0 s |

Pure numpy, single core, no numba. The POC's problem (9 blocks, 10:51) is **10 ms**. You will
never need to optimise this; if you think you do, you have chosen too fine a hop.

### 3.3 What it gets you that argmax does not **[verified]**

Synthetic: 5 artifacts, 600 frames, per-frame emission = signal + N(0, 0.6).

- Boundary MAE **0 frames**, exact recovery.
- Repeat with artifact 2's emission row **replaced by pure noise** (it has no evidence at
  all): boundaries still **exactly** recovered. The order prior reconstructs a signal-free
  artifact's span from its neighbours' spans. This is the property that makes the whole
  approach worth building.

### 3.4 Failure modes

| failure | symptom | fix |
|---|---|---|
| **`min_len` too small** | boundaries collapse; an artifact gets 1 frame | set `min_len` from a duration prior; the POC had 8-counts, so `min_len = 1 × 8-count` |
| **`max_len` hard** | infeasible → all `-inf` → garbage backtrack | make `max_len` **soft**: allow it, penalise overrun linearly. `muvid.footage.select_score` already does exactly this (`l_max_overrun_penalty`) |
| **emission rows on different scales** | one loud artifact eats the timeline | robust-z each row (median / IQR) **before** the DP; see §10.1 |
| **hard boundary snapping** | *worse* than a soft bonus | measured: soft beat bonus MAE **2.93 s**, hard snap-to-beat MAE **6.07 s** on the same data **[verified]**. Snap as a *bonus*, not a *constraint*, unless the grid is certified |
| **boundary precision = hop** | boundaries land on frame edges | after the DP, refine each `b_k` by a local argmax of `boundary_bonus` at the *native* hop, inside `±1` solver frame |
| **infeasible, silently** | `V[K,T] == -inf` | **check it.** Raise with a classification: coverage gap vs dwell-infeasible, then retry with `min_len→0`. Copy the ladder from `muvid.footage.select_score` |

### 3.5 The relationship to everything else

- `ruptures.Dynp(n_bkps=K-1)` is **this DP with the emission dropped** — it scores a segment
  by its internal homogeneity instead of by which artifact it matches (§7).
- Viterbi with a strict left-to-right no-skip transition is **this DP with a geometric length
  prior instead of a hard `[min_len, max_len]`** (§6). Same answer on the same data
  **[verified: both recovered `[0,90,230,300,470,600]` exactly]**.
- Needleman–Wunsch is **this DP plus gaps in both sequences** (§5).

So: **implement §3, and get §6 and §7 by changing the arguments.** That is the argument for
writing it rather than importing it.

---

## 4. Dynamic Time Warping

### 4.1 When DTW is the right tool

DTW answers *"what is the monotone, continuous correspondence between these two sequences?"*
It is right when **the artifact side is itself a time series**: a reference performance, a
previous cut of the same video, a MIDI score, a second camera angle, a pose trajectory. It is
**wrong** when the artifact side is a list of discrete labels — that is §3, and using DTW
there means inventing a fake time series to warp against.

### 4.2 What is installed

| library | present in p12? | API | licence |
|---|---|---|---|
| `librosa.sequence.dtw` | **yes**, 0.11.0 | `dtw(X, Y, *, C, metric, step_sizes_sigma, weights_add, weights_mul, subseq, backtrack, global_constraints, band_rad, return_steps)` **[verified: signature]** | ISC |
| `dtaidistance` | **yes**, 2.4.0 | `dtw`, `dtw_ndim`, `subsequence.dtw.subsequence_alignment`, `local_concurrences` **[verified]** | Apache-2.0 **[verified: PyPI `license_expression`]** |
| `tslearn` | no | `tslearn.metrics.dtw_path`, soft-DTW | BSD-2-Clause |
| `fastdtw` | no | approximate, O(n) | MIT |
| `stumpy` | no | matrix profile (motif/discord, not DTW) | BSD-3-Clause |

**You need no new DTW dependency.** `librosa` and `dtaidistance` are both here, and
`dtaidistance` is already the fleet's DTW (`kodokan.compare`).

### 4.3 Subsequence DTW — find a short artifact inside a long stream

The single most useful DTW variant for this package.

```python
import librosa, numpy as np

# X: (d, n) query features. Y: (d, m) stream features. FEATURE-MAJOR.
D, wp = librosa.sequence.dtw(X=query, Y=stream, subseq=True, metric="cosine")
# wp is returned LAST-STEP-FIRST. The match span in the stream is:
start, end = wp[-1, 1], wp[0, 1]
cost = D[-1, wp[0, 1]]  # comparable across candidate ends
```

**[verified]** — embedded a 2× time-stretched copy of a 40-frame query at stream frames
120–175 in 300 frames of noise; recovered `121 → 182`. `int(np.argmin(D[-1]))` gives the same
end frame, so you can rank *k* candidate endpoints from the last row without backtracking.

`dtaidistance` gives the same thing with a friendlier surface and k-best out of the box:

```python
from dtaidistance.subsequence.dtw import subsequence_alignment

sa = subsequence_alignment(query_1d, series_1d)  # 1-D; use dtw_ndim for multivariate
m = sa.best_match()
m.segment  # -> [158, 196]
[mm.segment for mm in sa.kbest_matches(k=3)]  # -> [[158,196],[119,127],[29,38]]
```
**[verified]** — planted a 60-sample sine at 150–210 in 400 samples of noise; `best_match`
returned `[158, 196]`. Note it under-covers the true span at both ends: subsequence DTW's
endpoints are biased *inward* because the free end-point costs nothing to shorten. **Pad the
returned span, or use the k-best spread as your uncertainty.**

### 4.4 Constraints

- **`global_constraints=True, band_rad=0.25`** is a Sakoe–Chiba band as a *fraction* of the
  shorter sequence. It caps the warp and cuts cost to O(n·band). **[verified: runs, and runs
  together with `subseq=True` without complaint]** — though "banded subsequence DTW" is a
  semantically odd combination; the band is relative to a match whose location you do not yet
  know. **[inferred: don't]**
- **`step_sizes_sigma`** defaults to `[[1,1],[0,1],[1,0]]` with zero additive and unit
  multiplicative weights **[verified: read from source]**. The symmetric-degenerate default
  allows unbounded horizontal and vertical runs — i.e. **it will happily map 30 query frames
  onto 1 stream frame**. If you want a bounded slope use `[[1,1],[1,2],[2,1]]` (Itakura-ish).
- **`C=`** takes a precomputed cost matrix. This is the seam: build `C` from *anything*
  (text similarity, LLM scores, chroma) and DTW is just the solver. `dtw(C=C, subseq=True)`
  **[verified]**.

### 4.5 Cost **[verified]**

`librosa.sequence.dtw(C=…)` on a precomputed cost matrix, warm (numba compiled):

| C shape | time |
|---|---|
| 50 × 300 | 0.3 ms |
| 50 × 1 000 | 0.8 ms |
| 50 × 3 000 | 2.3 ms |

The **first** call in a process pays a numba JIT cost of roughly 1–4 s. Budget for it in a
CLI; it is invisible in a long-running service. Computing `C` from raw features with
`metric='cosine'` dominates everything: 40 × 300 × 12-dim took 2.06 s cold, almost all of it
`cdist` + JIT.

### 4.6 Where DTW is *fatally* wrong — measured **[verified]**

Query = blocks `A B C D`. Stream = the same blocks in the order `A C B D` (a recap, a
reordered demo, a montage). Plain DTW:

```
query block A -> stream frames   0- 29     (correct home  0- 30)
query block B -> stream frames  29- 29     (correct home 60- 90)   <-- collapsed to ONE frame
query block C -> stream frames  30- 59     (correct home 30- 60)   <-- given B's home
query block D -> stream frames  60-119     (correct home 90-120)
```

DTW returns a **plausible-looking, monotone, silently wrong** answer. It cannot report "these
are out of order"; that information is destroyed by the model. The same data through
`scipy.optimize.linear_sum_assignment` on block-mean distances gave `A→0, B→2, C→1, D→3`,
exactly right **[verified]**.

**Detection rule [inferred]:** after any monotone alignment, check for **collapsed segments**
(an artifact assigned < 2 frames) and **path degeneracy** (a long horizontal or vertical run
in `wp`). Either one is the signature of an order violation, not of a bad feature. Report it
as a `order_violation` diagnostic rather than shipping the span.

---

## 5. Needleman–Wunsch / Smith–Waterman — when things are missing

Use when **O4 fails** (an artifact is described but never demonstrated) or **O3 fails** (the
media has intro chatter, an outro, an ad). NW keeps monotonicity but allows *gaps on both
sides*, which is exactly the two failure modes.

### 5.1 The 25-line implementation

```python
import numpy as np


def nw_align(S, *, gap_query=-0.5, gap_ref=-0.5, local=False):
    """Needleman-Wunsch (local=False) / Smith-Waterman (local=True) over a similarity
    matrix S[i, j] = score of matching artifact i to media chunk j.
    Returns matched (i, j) pairs; unmatched i or j are gaps."""
    n, m = S.shape
    H = np.zeros((n + 1, m + 1))
    ptr = np.zeros((n + 1, m + 1), dtype=np.int8)
    if not local:  # global: edges cost gaps
        H[1:, 0] = np.arange(1, n + 1) * gap_ref
        ptr[1:, 0] = 2
        H[0, 1:] = np.arange(1, m + 1) * gap_query
        ptr[0, 1:] = 3
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            c = (
                H[i - 1, j - 1] + S[i - 1, j - 1],
                H[i - 1, j] + gap_ref,
                H[i, j - 1] + gap_query,
            )
            k = int(np.argmax(c))
            best = c[k]
            if local and best < 0:
                best, k = 0.0, -1
            H[i, j] = best
            ptr[i, j] = k + 1  # 0 stop, 1 diag, 2 skip artifact, 3 skip chunk
    i, j = np.unravel_index(np.argmax(H), H.shape) if local else (n, m)
    pairs = []
    while i > 0 and j > 0 and ptr[i, j] != 0:
        p = ptr[i, j]
        if p == 1:
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif p == 2:
            i -= 1
        else:
            j -= 1
    return pairs[::-1], H
```

O(n·m), and n·m here is (artifacts × media chunks), so it is tiny — 7 × 10 is instant, and
even 200 × 5 000 is a second in pure Python.

### 5.2 The measured comparison **[verified]**

7 artifacts, 10 media chunks. Ground truth: artifact **3 is never demonstrated**; chunks
0, 1, 7, 9 have no artifact.

| method | result | verdict |
|---|---|---|
| **NW (`gap = -0.3`)** | `[(0,2),(1,3),(2,4),(4,5),(5,6),(6,8)]` | **exactly right — artifact 3 correctly left unmatched** |
| SW (local) | identical pairs | same; differs only at the ends |
| per-artifact `argmax` | `…(2,4),(3,4)…` | **artifact 3 duplicated onto chunk 4** — this is the POC's real bug, "two blocks assigned the same move" |
| Hungarian | `…(3,7)…`, monotone = **False** | invented a match for the absent artifact and reordered |

That table is the argument for this whole file in four rows.

### 5.3 Choosing the gap penalty

There is no principled default; it trades false gaps against false matches. **[inferred]**
Set it as a *quantile of the similarity distribution*: `gap = np.quantile(S, 0.3)` starts
sane and scales with your features. Then expose it as a keyword, and report the number of
gaps taken as a diagnostic — a run with 6 gaps out of 9 artifacts is telling you the features
are dead, not that 6 steps are missing.

**Affine gaps** (open cost ≠ extend cost) matter when the missing region is *contiguous* —
one 90-second intro rather than nine scattered skips. Cheap to add: carry a second DP layer
for "currently in a gap".

### 5.4 `librosa.sequence.rqa` — affine-gap local alignment, already installed

`librosa.sequence.rqa(sim, *, gap_onset=1, gap_extend=1, knight_moves=True, backtrack=True)`
**[verified: signature and run]** implements Serrà–Serrà–Andrzejak RQA — method `Q` is
Smith–Waterman with affine gaps over a **similarity** (not distance) matrix. **[from docs:
its docstring, quoted]** *"unlike dynamic time warping, alignment paths here are maximized,
not minimized."*

- **[verified]** On a 40 × 200 similarity matrix with a planted diagonal at offset 100, it
  returned the path `[0,100] → [39,139]` with max score 47.33. Cold call 4.48 s — that is
  numba JIT, not the algorithm.
- `knight_moves=True` allows `(-2,-1)` and `(-1,-2)` steps in addition to the diagonal, i.e.
  **a bounded slope of 2**, which is a *feature*: it cannot collapse a block to one frame the
  way §4.6 did.
- **Difference from §5.1 that matters:** `rqa` is near-diagonal by construction; it aligns
  two sequences of *comparable* length. §5.1's NW allows arbitrary-length gaps and is the
  right shape for "9 artifacts vs 400 chunks". Use `rqa` for stream-vs-stream, `nw_align` for
  artifacts-vs-stream. **[inferred, from reading the step set]**

---

## 6. HMM / Viterbi, and CTC segmentation

### 6.1 Viterbi as the probabilistic twin of §3

Model: hidden state at frame `t` = which artifact is current. Transition matrix encodes the
order prior. Emission = your normalised evidence as a per-frame likelihood.

```python
import numpy as np, librosa


def left_to_right(K, *, p_stay=0.99, max_skip=0):
    """Order prior as a transition matrix. max_skip=0 -> every artifact must be visited;
    max_skip=1 -> an artifact may be skipped entirely (relaxes O4)."""
    A = np.zeros((K, K))
    for k in range(K):
        A[k, k] = p_stay
        adv = [k + d for d in range(1, max_skip + 2) if k + d < K]
        for j in adv:
            A[k, j] = (1 - p_stay) / len(adv)
        if not adv:
            A[k, k] = 1.0
        A[k] /= A[k].sum()
    return A


p_init = np.zeros(K)
p_init[0] = 1.0
states = librosa.sequence.viterbi(
    prob, left_to_right(K, p_stay=1 - K / T), p_init=p_init
)
```

`prob` is `(n_states, n_steps)` and **librosa expects it column-normalised** (a distribution
over states per frame). `librosa.sequence.viterbi(prob, transition, *, p_init, return_logp)`
**[verified: signature]**.

**Measured [verified]:** K=5, T=600, same synthetic data as §3.3. Viterbi with
`p_stay = 1 - K/T` recovered `[0, 90, 230, 300, 470, 600]` — identical to the DP. Cold call
1.05 s (numba JIT); warm it is sub-millisecond.

**The skip case [verified]:** K=6 where artifact 2 has *zero* true duration.

```
max_skip=0: states visited [0,1,2,3,4,5]  first frame per state [0, 60, 139, 140, 250, 330]
max_skip=1: states visited [0,1,  3,4,5]  first frame per state [0, 60, None, 140, 250, 330]
```

With `max_skip=0` the model is forced to give artifact 2 a single frame (139) — a lie.
With `max_skip=1` it correctly reports the artifact as **absent**. This is the HMM's version
of an NW gap and it is one keyword.

**Viterbi vs the DP — when to prefer which [inferred]:**

| | ordered DP (§3) | Viterbi (§6) |
|---|---|---|
| length prior | **hard `[min_len, max_len]`, or any shape you write** | geometric only (a self-loop probability), unless you go semi-Markov |
| boundary bonus | first-class term | must be smuggled into the emission |
| exactly-K guarantee | **yes, structural** | only via a no-skip transition, and a state can still get 1 frame |
| skipping an artifact | needs a gap model | **one keyword** |
| posterior confidence | log-sum-exp variant (§11) | forward–backward, standard |
| dependency | numpy | librosa (or 30 lines) |

**Default to the DP**; reach for Viterbi when you want skips or when you already have
calibrated per-frame probabilities.

`librosa.sequence.transition_loop(K, p)` and `transition_cycle(K, p)` build the two common
matrices; `transition_loop(5, 0.99)` row 0 is `[0.99, 0.0025, 0.0025, 0.0025, 0.0025]` — note
it allows **backwards** transitions, so it is *not* an order prior. Use `left_to_right` above
**[verified]**.

### 6.2 CTC segmentation — the principled version for token sequences

When your artifacts are *words* and you have a frame-level acoustic posterior, CTC forced
alignment is the correct algorithm: a constrained Viterbi over the CTC lattice of the token
sequence, which is exactly "assign a monotonic labelling with blanks allowed".

**`torchaudio.functional.forced_align` — present, and DEPRECATED.** **[verified]**

```python
import torch, torchaudio.functional as F

labels, scores = F.forced_align(log_probs, targets, blank=0)  # log_probs (B, T, V)
spans = F.merge_tokens(labels[0], scores[0])  # -> TokenSpan(token, start, end, score)
```

It works and it is fast — **0.4 ms for T=400** — and `merge_tokens` correctly emits two
separate spans for a repeated token **[verified]**. But it prints:

> `torchaudio.functional._alignment.forced_align has been deprecated. This deprecation is
> part of a large refactoring effort to transition TorchAudio into a maintenance phase …
> It will be removed from the 2.9 release.`

**[verified: the literal warning text on torchaudio 2.9.0]** — it is still present in 2.9.0
despite the message, which means the next torch bump can remove it. `00-existing-in-fleet.md`
recommends this API as the cheap route to CTC alignment; **that recommendation now needs a
caveat.** Options, in my order of preference **[inferred]**:

| option | licence | verdict |
|---|---|---|
| **vendor the CTC alignment DP** (~60 lines: expand targets with blanks, Viterbi over the 2N+1 lattice) | yours | **best.** It is a small, stable, well-specified algorithm. Pin it and stop tracking torchaudio's roadmap |
| `ctc-segmentation` (lumaku) | **Apache-2.0** **[verified: GitHub API]** | good; last pushed 2024-05, 348 stars. Cython, builds on Apple Silicon. Designed for exactly this (long-audio ↔ text) |
| `torchaudio.functional.forced_align` | BSD-2 | works today, deprecated. Fine as a *seam default* if you also ship the vendored fallback |
| `ctc-forced-aligner` (MahmoudAshraf97) | **no licence declared** **[verified: GitHub API returns `None`]** | **do not depend on it.** No licence = all rights reserved |
| `aeneas` | **AGPL-3.0** **[verified: PyPI]** | **licence landmine**, same class as the `madmom` exclusion already made in `mixing.audio.beats` |

---

## 7. Change-point detection — `ruptures`

### 7.1 What it is for, and the one thing it cannot do

`ruptures` finds **boundaries in a signal**, from the signal's own statistics. It does *not*
know about artifacts. Confirmed by reading the interface **[verified]**:

```python
class BaseCost:
    @abc.abstractmethod
    def error(self, start, end): ...  # <-- no segment INDEX argument
```

`error(start, end)` cannot express "segment 3 is cheap when artifact 3 occupies it". So:

> **`ruptures` gives you `b`, never `S`.** Use it to *propose boundaries* that you then feed
> to §3 as `allowed` or `boundary_bonus`. Never use it as the aligner.

Which is a genuinely valuable role: the POC's sub-bass split, and any "cut this into N
sections" step, is exactly this.

### 7.2 The known-K special case

`Dynp` with `n_bkps=K-1` is *"cut this signal into exactly K segments optimally"*. That is
frequently what you want, because the number of artifacts is known.

```python
import ruptures as rpt

algo = rpt.KernelCPD(kernel="rbf", min_size=20).fit(signal)  # signal: (n, d) float
bkps = algo.predict(n_bkps=K - 1)  # [b1, …, b_{K-1}, n]
```

**[verified]** On a 600 × 3 synthetic with true breaks `[90, 230, 300, 470, 600]`, **all six
algorithms recovered them exactly**:

| algorithm | call | result | time |
|---|---|---|---|
| `Dynp(l2, min_size=20, jump=1)` | `.predict(n_bkps=4)` | exact | 2.209 s |
| `Binseg(l2, jump=1)` | `.predict(n_bkps=4)` | exact | 0.043 s |
| `Pelt(l2, jump=1)` | `.predict(pen=30)` | exact | 0.346 s |
| `Window(width=50, l2)` | `.predict(n_bkps=4)` | exact | 0.013 s |
| `KernelCPD(rbf, min_size=20)` | `.predict(n_bkps=4)` | exact | 0.007 s |
| `KernelCPD(linear, min_size=20)` | `.predict(n_bkps=4)` | exact | **0.002 s** |

### 7.3 Scaling — **use `KernelCPD`, not `Dynp`** **[verified]**

`n_bkps=8`, 3-dim signal, `min_size=20`:

| n | `Dynp` jump=1 | `Dynp` jump=5 | `Binseg` jump=1 | `KernelCPD` |
|---|---|---|---|---|
| 600 | 2.55 s | 0.11 s | 0.04 s | **0.002 s** |
| 1 200 | 17.4 s | 0.73 s | 0.14 s | 0.010 s |
| 2 400 | **124.8 s** | 4.61 s | 0.48 s | 0.043 s |
| 4 800 | >120 s (abandoned) | 31.5 s | 3.04 s | **0.188 s** |

`Dynp` is the textbook O(K·n²) DP in Python-level loops; `KernelCPD` is the same optimal DP
in C with a kernel trick. **~660× faster at n=2400, same optimal answer.** `jump=5` (the
library default!) is a 5-frame quantisation of every boundary — silently, and it is what you
get if you don't pass `jump`.

**Practical rule [inferred]:** `KernelCPD(kernel="linear")` for mean shifts, `"rbf"` for
distributional change, `Pelt` when you do *not* know K and are willing to tune `pen`, `Window`
when you want a cheap novelty *curve* rather than a decision (its `.score` is a fine
`boundary_bonus` source).

### 7.4 Cost, licence, verdict

- **New dependency**: `ruptures` is **not** in p12 **[verified]**. BSD-2-Clause, 2 077 stars,
  last pushed 2026-07 **[verified: GitHub API]**. Wheels install cleanly on Apple Silicon
  **[verified: `pip install ruptures` in a fresh 3.12 venv, v1.1.10]**.
- **[inferred]** Worth it *only if* the package ships change-point detection as a first-class
  method. If §3's DP plus `mixing.audio.segmentation`'s Foote novelty covers the cases, skip
  it — the fleet already has `self_similarity` and `energy_novelty` strategies.

---

## 8. Constrained assignment — Hungarian, and why to avoid it

`scipy.optimize.linear_sum_assignment(C)` solves min-cost bipartite matching in O(n³).
**[verified]** 1 000×1 000 in 0.049 s, 3 000×3 000 in 0.663 s — never the bottleneck.

```python
from scipy.optimize import linear_sum_assignment

rows, cols = linear_sum_assignment(-S)  # negate: LSA minimises
```

**Use it only when O1 genuinely fails** — an unordered bag of artifacts (chapter thumbnails,
a mood board, tagged photos to place in a montage).

Three things to know:

1. **It has no monotonicity constraint and will break order** — measured in §5.2: it produced
   `(3,7)` for an artifact with no true match, and `np.diff(cols) > 0` was `False`.
2. **It matches everything.** With a square cost matrix, every artifact gets a chunk. To allow
   non-matches, pad with **dummy rows/columns at a constant "non-match cost"** — that constant
   is the same knob as NW's gap penalty.
3. **`inf` in the cost matrix**: `linear_sum_assignment` accepted a matrix containing `inf`
   in my test and returned the same answer as substituting `1e9` **[verified]**, but scipy
   raises `ValueError: cost matrix is infeasible` when the finite entries admit no perfect
   matching. **[inferred]** Substitute a large finite number and check the result rather than
   relying on the exception.

**When Hungarian is the right answer, it is decisively right:** §4.6's out-of-order blocks
were recovered exactly (`A→0, B→2, C→1, D→3`) where DTW silently failed. So the design should
expose both, and make `ordered: bool` an explicit input rather than an assumption.

**The middle ground worth building [inferred]:** *ordered assignment with gaps* — that is
just §5's NW. Order-free is a genuinely different regime; there is no continuum between them.

---

## 9. Grid fitting — `(offset, period)` from observations

The POC did this by hand: beat tracking gave the *spacing* (129.2 bpm → 3.715 s per 8-count),
a visible landmark gave the *phase*. Both halves should be functions. All four below are
verified against a synthetic with `P_true = 3.715`, `t0_true = 12.34`, 44 events, 3 dropped
detections and 3 spurious ones.

### 9.1 Known integer indices → plain least squares

```python
def fit_grid_ls(times, indices):
    A = np.vstack([np.ones_like(indices, float), indices.astype(float)]).T
    (t0, period), *_ = np.linalg.lstsq(A, times, rcond=None)
    return t0, period
```
Two unknowns, closed form. Use when you know *which* 8-count each observation is — e.g. after
a §3 alignment. **[verified: exact recovery on clean data]**

### 9.2 Period known, phase unknown → circular mean

The right way to estimate phase, and it comes with a free confidence.

```python
def estimate_phase(times, period):
    z = np.exp(2j * np.pi * np.asarray(times) / period)
    m = z.mean()
    t0 = (np.angle(m) / (2 * np.pi)) * period % period
    return t0, abs(m)  # abs(m) in [0,1] = concentration = CONFIDENCE
```
**[verified]** With 3 outliers present: `t0 = 1.215` vs true `12.34 mod 3.715 = 1.195`
(19 ms error), concentration `R = 0.911`. `R` near 1 = the events really are on a grid;
`R < ~0.4` = there is no grid and you should say so.

### 9.3 Both unknown → maximise concentration over a period grid

```python
def fit_grid_phase(times, period_lo, period_hi, *, n_grid=4000):
    Ps = np.linspace(period_lo, period_hi, n_grid)
    z = np.array([np.exp(2j * np.pi * np.asarray(times) / P).mean() for P in Ps])
    k = int(np.argmax(np.abs(z)))
    P = Ps[k]
    return P, (np.angle(z[k]) / (2 * np.pi)) * P % P, abs(z[k])
```
**[verified]** Searching 3.4–4.0 s in 4 000 steps: `P = 3.7166` (true 3.715), `t0 = 1.175`,
`R = 0.912`, in **0.019 s**. This is the automated version of the POC's manual phase anchor.

Guard the search range from the beat tracker's tempo, and **search the octave neighbourhood
too** (`P/2`, `P`, `2P`) — beat trackers octave-error routinely, and `R` will usually pick the
right one because the wrong octave halves the concentration.

### 9.4 Outliers → RANSAC on `(offset, period)`

```python
def fit_grid_ransac(times, *, period_lo, period_hi, tol=0.15, iters=2000, seed=0):
    rng = np.random.default_rng(seed)
    t = np.sort(np.asarray(times, float))
    best = (-1, None)
    for _ in range(iters):
        i, j = rng.choice(len(t), 2, replace=False)
        if t[j] == t[i]:
            continue
        for k in range(1, 60):  # how many periods apart i and j are
            P = abs(t[j] - t[i]) / k
            if not (period_lo <= P <= period_hi):
                continue
            resid = t - (t[i] + np.round((t - t[i]) / P) * P)
            inl = np.abs(resid) < tol
            if inl.sum() > best[0]:
                best = (int(inl.sum()), (P, inl))
    _, (P, inl) = best
    return fit_grid_ls(t[inl], np.round((t[inl] - t[inl][0]) / P)) + (
        int(inl.sum()),
        len(t),
    )
```
**[verified]** `P = 3.7160`, `t0 mod P = 1.172`, **41/44 inliers** (it found all three planted
outliers), in **0.07 s**. `tol` is the only real knob — set it to the beat tracker's own
jitter, ~0.05 P.

### 9.5 The duration sanity check — the highest-value five lines in the POC

```python
def tempo_consistency(n_units, unit_beats, bpm_claimed, span_s, *, tol=0.05):
    predicted = n_units * unit_beats * 60 / bpm_claimed
    return predicted, span_s, abs(predicted - span_s) / span_s <= tol
```
**[verified]** — reproduces the POC's finding exactly:

```
100.0 bpm -> 211.2 s vs music span 170.0 s   consistent=False   <-- the document was wrong
129.2 bpm -> 163.5 s vs music span 170.0 s   consistent=True
```

**Generalise it [inferred]:** any time an artifact set carries a *claimed* total (n bars,
n reps, a stated duration), cross-check it against the measured media span **before** running
any solver, and surface a `SourceDocumentInconsistency` rather than silently fitting garbage.
This check costs nothing and it caught a real error in a hand-written source document.

---

## 10. Fusing several weak aligners

### 10.1 Normalise, then add — the shape

Three rules, all learned from the measured ablation below:

1. **Robust-z every emission row independently** before weighting. Median and IQR, not mean
   and std — one loud outlier frame otherwise sets the scale for the whole row.
   `muvid.footage.scoring.grid.compute_norm` already implements exactly this (robust
   median/IQR, percentile-clipped, per-metric-global) **[from docs, per `00-existing-in-fleet.md`]**.
2. **Keep boundary evidence in `b`, not in `S`.** Beat grids, motion novelty and shot cuts say
   *"a cut is likely here"*, which is a property of a **time**, not of an artifact-time pair.
   Adding them to `S` smears them across every artifact.
3. **Weights are a small dict, and the model is linear.** `weights: dict[str, float]` plus one
   `lambda_switch`, as `WeightedSelectionConfig` already does. Resist anything learned until
   you have labelled data — you do not.

```python
def robust_z(x, axis=None):
    med = np.median(x, axis=axis, keepdims=True)
    iqr = np.subtract(*np.percentile(x, [75, 25], axis=axis, keepdims=True)) + 1e-9
    return (x - med) / iqr


S = sum(w[name] * robust_z(curve, axis=1) for name, curve in emissions.items())
b = sum(w[name] * robust_z(curve) for name, curve in boundary_curves.items())
b[beat_frames] += w["beat_snap"]
```

### 10.2 The measured ablation **[verified]**

6 artifacts, 400 frames at 0.5 s (200 s of media). Evidence: a sparse noisy **text**
similarity (artifact 2 deliberately has **no** text evidence at all), a **motion** novelty
curve with 8 spurious peaks, and a **beat** grid at 3.715 s.

| configuration | boundaries | MAE | max err |
|---|---|---|---|
| text only | `[0, 24, 118, 148, 255, 368, 400]` | 6.36 s | 19.0 s |
| **text + motion bonus + beat bonus** | `[0, 53, 119, 161, 245, 367, 400]` | **2.93 s** | 18.5 s |
| text, boundaries **hard-snapped** to beat | `[0, 22, 119, 149, 253, 364, 400]` | 6.07 s | 17.0 s |
| + `max_len` = 70 s | identical to row 2 | 2.93 s | 18.5 s |
| ground truth | `[0, 52, 118, 160, 244, 330, 400]` | — | — |

Three things fall out of that table:

- **Fusion halved the error.** Weak boundary evidence added to strong-but-sparse identity
  evidence is worth more than either alone.
- **Hard snapping was worse than no snapping at all** (6.07 vs 6.36 for text-only, and much
  worse than the 2.93 soft version). A grid you are not certain of is a *prior*, never a
  constraint. This directly contradicts the intuition the POC's manual method suggests.
- **Four of five boundaries landed within 1 frame (0.5 s); one was 18.5 s wrong.** The mean
  hides everything. **Always report the max, and always report per-boundary confidence.**

### 10.3 Rank fusion, when scales are hopeless

When two producers cannot be put on a comparable scale (an LLM's 1–5 rating and a cosine
similarity), fuse **ranks** instead of scores. Reciprocal rank fusion is one line and has no
tuning:

```python
def rrf(score_lists, *, k=60):
    """score_lists: sequence of (K, T) arrays. Returns (K, T) fused rank score."""
    out = 0.0
    for S in score_lists:
        r = (
            (-S).argsort(axis=1).argsort(axis=1)
        )  # rank of each t within each artifact row
        out = out + 1.0 / (k + r)
    return out
```
**[inferred — standard IR technique, not measured here.]** Lower variance than weighted sums
when one producer is occasionally catastrophic, at the cost of throwing away magnitude. Use
it for the *identity* term; keep the boundary term as raw scores.

### 10.4 The producer contract

For fusion to be a table lookup rather than glue code, every producer returns the same thing:

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class Evidence:
    name: str  # 'asr_text', 'beat_grid', 'motion_novelty', 'llm_sheet'
    kind: Literal["emission", "boundary"]
    clock: Clock  # (t0, hop) — the solver resamples, the producer does not
    values: np.ndarray  # (K, T) for emission, (T+1,) for boundary
    mask: np.ndarray | None = None  # where the producer had coverage; NaN-safe fusion
    scale: Literal["score", "logprob", "rank"] = "score"
```

`mask` is the field people forget and then regret: "no evidence here" and "evidence says no"
must not be the same number. Under fusion, a masked-out region contributes 0 after
normalisation, and its absence is reported in the diagnostics.

---

## 11. Confidence — computing it, and not believing it

### 11.1 Forward–backward over the ordered DP

Run §3's DP twice with `soft=True` (log-sum-exp instead of max): once forward, once on the
**reversed reward and reversed bonus**. Then the posterior over boundary `k`'s position is

```python
Vf, _ = ordered_segmentation(S, bonus, min_len=…, max_len=…, soft=True)
Vb, _ = ordered_segmentation(S[::-1, ::-1].copy(), bonus[::-1].copy(),
                             min_len=…, max_len=…, soft=True)     # BOTH axes reversed
logZ = Vf[K, T]
for k in range(1, K):
    lp = Vf[k, :] + Vb[K - k, ::-1] - logZ          # boundary k at frame t
    p = np.exp(lp - lp.max()); p /= p.sum()
    ts = np.arange(T + 1)
    mean = (ts * p).sum()
    sd = np.sqrt((((ts - mean) ** 2) * p).sum())
```

**The correctness test is one line:** `Vf[K, T]` must equal `Vb[K, T]`. **[verified]** — mine
printed `logZ fwd=133.256  bwd=133.256`. Reversing only one axis (the mistake I made first)
silently produces plausible garbage; this check catches it immediately. Cost: exactly 2× the
DP, so still 0.26 s for 9 artifacts × 33 min.

### 11.2 The measured result, including the part that should worry you **[verified]**

Same fusion setup as §10.2. MAP / true / posterior mean are **frames** at 0.5 s per frame;
sd and the probability are in seconds.

| boundary | MAP | true | post. mean | post. sd | P(err ≤ 3 s) | honest? |
|---|---|---|---|---|---|---|
| 1 | 53 | 52 | 38.5 | 6.6 s | 0.31 | yes |
| 2 | 119 | 118 | 125.6 | 4.8 s | 0.56 | yes |
| 3 | 161 | 160 | 165.9 | **14.8 s** | 0.13 | **yes — this is the boundary next to the evidence-free artifact, and the model says so** |
| 4 | 245 | 244 | 256.7 | 2.9 s | 0.11 | yes — but see below |
| 5 | 367 | **330** | 368.7 | **1.0 s** | **1.00** | **NO — confidently wrong by 18.5 s** |

Boundary 4 shows a third, subtler pattern: the MAP is right (245 vs 244) but the posterior
*mean* sits 12 frames away, so `P(err ≤ 3 s)` reads a misleading 0.11. **Report the MAP and
the sd; do not report the posterior mean as the answer**, and be aware that a
tolerance-window probability read off a skewed posterior can disagree with a correct MAP.

- **Boundary 3 is the win**: the artifact with no evidence produced a *wide* posterior. The
  model correctly reports that it does not know. That is exactly the signal an agent needs to
  decide "escalate this one to the LLM/contact-sheet method".
- **Boundary 5 is the warning**: `sd = 1.0 s`, `p = 1.00`, and wrong by 18.5 s. The posterior
  is a statement about *the model*, not about *the world*. When the emission is confidently
  misleading, the posterior is confidently misleading.

**[inferred] Rule:** ship posterior width as `Placement.confidence`, and *also* ship at least
one **model-external** check — the §9.5 duration consistency test, a monotonicity test, and
agreement between two independent producers. Never let a single posterior be the only quality
signal.

### 11.3 Cheaper confidence signals, worth having anyway

| signal | cost | what it catches |
|---|---|---|
| **DP margin**: rerun with boundary `k` forbidden, take `logZ_full − logZ_constrained` | K × one DP | how much the alignment *needs* this boundary |
| **k-best paths** (`dtaidistance.kbest_matches`, or a k-best DP) | ~k × one DP | multi-modality — two equally good placements |
| **producer agreement**: pairwise boundary MAE between single-producer alignments | free, you have them | a producer that is lying |
| **collapsed-segment count** (§4.6) | free | order violations, hard-constraint infeasibility |
| **gap count** (§5.3) | free | dead features masquerading as missing artifacts |
| **grid concentration `R`** (§9.2) | free | "there is no grid here" |

---

## 12. Evaluation — how to test any of this at all

### 12.1 `mir_eval` is installed and is the right tool **[verified: 0.8.2]**

Its `segment` module is the MIREX structural-segmentation standard and maps onto this problem
without adaptation.

```python
import numpy as np, mir_eval.segment as seg

ref_i = np.stack([ref_b[:-1], ref_b[1:]], axis=1)  # (n, 2) intervals in SECONDS
est_i = np.stack([est_b[:-1], est_b[1:]], axis=1)
P, R, F = seg.detection(ref_i, est_i, window=0.5, trim=False)  # boundary hit rate
d_re, d_er = seg.deviation(ref_i, est_i)  # median boundary deviation
seg.pairwise(ref_i, ref_lab, est_i, est_lab)  # frame-pair P/R/F on LABELS
seg.nce(ref_i, ref_lab, est_i, est_lab)  # over/under-segmentation
```

**[verified]** on `ref = [0,90,230,300,470,600]`, `est = [0,88,235,299,466,600]`:

| metric | value |
|---|---|
| `detection(window=0.5)` | P=0.33 R=0.33 F=0.33 |
| `detection(window=3.0)` | P=0.67 R=0.67 F=0.67 |
| `detection(window=15.0)` | P=1.00 R=1.00 F=1.00 |
| `deviation` | (1.5, 1.5) |
| `pairwise` | (0.958, 0.969, 0.963) |
| `nce` | (0.946, 0.942, 0.944) |

**The tolerance is the whole story.** MIREX reports `0.5 s` and `3 s`; those are right for
music structure. **[inferred]** For artifact→span work the honest windows are domain-set:

| domain | boundary tolerance | rationale |
|---|---|---|
| a dance 8-count | **± half an 8-count (≈1.9 s)** | landing on the wrong 8-count is a real error; ±1 beat is not |
| a recipe step | ± 2 s | steps are tens of seconds |
| a lecture chapter | ± 5 s | nobody notices |
| a word (ASR/CTC) | ± 0.05–0.2 s | the standard forced-alignment window |

**Report the whole curve, not one number.** `F(window)` for `window ∈ {0.25, 0.5, 1, 2, 5}`
is one line of code and tells you whether your errors are "slightly off" or "on the wrong
block" — a distinction the F-score at a single tolerance cannot express.

`mir_eval.alignment` also exists (`absolute_error`, `percentage_correct`,
`percentage_correct_segments`, `karaoke_perceptual_metric`) for the **timestamp-list** case
(lyrics/words, not intervals) **[verified]**, and `mir_eval.util.match_events(ref, est,
window)` is the greedy tolerance-window matcher you would otherwise write **[verified]**.

### 12.2 `lacing.quality` is already the fleet's answer for intervals **[verified]**

```python
from lacing.quality import boundary_iou, interval_iou, cohen_kappa, krippendorff_alpha
boundary_iou(a: Iterable[TimeInterval], b: Iterable[TimeInterval]) -> float
interval_iou(a: TimeInterval, b: TimeInterval) -> float
```
Signatures verified by import. **[inferred]** Use `lacing.quality` for the segment-IoU and
inter-annotator numbers, `mir_eval.segment` for the boundary numbers; they answer different
questions and both belong in the report.

### 12.3 The metric set to actually report

Six numbers, in this order **[inferred]**:

1. **Boundary MAE** and **max boundary error**, in seconds. The max is the one that matters.
2. **`F(window)` curve** at 5 tolerances (§12.1).
3. **Mean segment IoU** over artifacts (`lacing.quality.interval_iou`).
4. **Coverage**: fraction of media covered by *some* artifact, and fraction of artifacts with
   a span at all. Catches "it placed 4 of 9 and the metrics still look fine".
5. **Order violations**: count of `b_{k+1} < b_k` or collapsed segments. Should be 0 by
   construction; if it isn't, the solver is broken.
6. **Confidence calibration**: bucket placements by predicted confidence, report actual error
   per bucket. This is the number that tells the *agent* whether to trust the *method*, and it
   is the whole point of having an agent choose methods.

### 12.4 What to test against

There is no public benchmark for "hand-written document → dance video". **[inferred]** Build
the harness from three tiers:

| tier | source | cost | what it tests |
|---|---|---|---|
| **synthetic** | generate `S`/`b` with known boundaries and injected pathologies (dead artifact, spurious peaks, reordered block) | free, milliseconds | the *algorithms*. Every claim in this file was verified this way |
| **semi-synthetic** | take a real video with real chapter marks / real subtitles, hide them, re-derive | cheap | the *producers* |
| **the POC** | the choreography video + its 9 blocks, hand-corrected | one afternoon of labelling | the *whole pipeline*, once |

Tier 1 is where the regression tests live. It is fast, deterministic, and it caught my own
forward–backward bug (§11.1) in one line.

---

## 13. The facade shape

`00-existing-in-fleet.md` §5 fixes the outer API (`Artifact`, `Placement`, `align`, the
`Method` protocol). This file adds the layer *below* it. Keep them separate: a **Method**
produces evidence and calls a **Solver**; a **Solver** knows no media.

```python
# ---- what a solver consumes ------------------------------------------------
Clock = tuple[float, float]  # (t0_seconds, hop_seconds)


@dataclass(frozen=True, slots=True, kw_only=True)
class Prior:
    """Structural knowledge about the artifact SET. Nothing here mentions media."""

    ordered: bool = True  # O1
    non_overlapping: bool = True  # O2
    covers: bool = True  # O3 — spans tile the media
    exhaustive: bool = True  # O4 — every artifact has a span
    min_len_s: float | Sequence[float] = 0.0  # scalar or per-artifact
    max_len_s: float | Sequence[float] | None = None
    anchors: Mapping[str, Span] = field(
        default_factory=dict
    )  # artifact_id -> pinned span
    grid: tuple[float, float] | None = None  # (offset_s, period_s), from §9


@dataclass(frozen=True, slots=True, kw_only=True)
class Evidence:  # see §10.4
    name: str
    kind: Literal["emission", "boundary"]
    clock: Clock
    values: np.ndarray
    mask: np.ndarray | None = None
    scale: Literal["score", "logprob", "rank"] = "score"


# ---- the one solver verb ---------------------------------------------------
@runtime_checkable
class Solver(Protocol):
    name: str
    handles: frozenset[str]  # {'ordered','gaps','skips','unordered','grid'}
    requires: tuple[str, ...] = ()  # importable modules; () means numpy only
    licence: str = "MIT"
    complexity: str = "O(K*T*L)"  # a STRING, for the agent to read

    def __call__(
        self,
        evidence: Sequence[Evidence],
        n_artifacts: int,
        *,
        prior: Prior,
        weights: Mapping[str, float] | None = None,
        **kw,
    ) -> "Alignment": ...


@dataclass(frozen=True, slots=True, kw_only=True)
class Alignment:
    boundaries: np.ndarray  # (n_artifacts + 1,) SECONDS, or NaN for absent
    assignment: np.ndarray  # (n_artifacts,) index into boundaries, -1 = absent
    confidence: np.ndarray  # (n_artifacts,) 0..1
    posterior: np.ndarray | None = None  # (n_artifacts - 1, T + 1), from §11.1
    score: float = float("nan")  # the objective value, comparable within a solver
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
```

**Five design notes, each traceable to something measured above.**

1. **`Prior` is one object, not five keyword arguments**, because O1–O4 are properties of the
   *artifact set* and travel together through every call. `anchors` is a **pruning** of the
   solver's search, never a separate code path — §3's `allowed` mask is exactly the
   mechanism, and `muvid.footage.select_score`'s `allowed(i, j)` hook is the precedent.
2. **`handles` is the dispatch key, and it is a set not a string.** The agent's job in
   `method="auto"` is to intersect what `Prior` asserts with what each solver `handles`, and
   pick the cheapest survivor. That is a five-line rule-based function, not an LLM call — and
   it is why `complexity` is a readable string rather than a number.
3. **The solver takes `n_artifacts: int`, not `artifacts`.** It must not be able to look at
   the artifacts; that is what keeps it testable with synthetic matrices, which is how every
   claim in this file was verified.
4. **`boundaries` in seconds, and `posterior` on the solver clock.** Boundaries are the
   contract; the posterior is a debugging/confidence artifact, and shipping it in frames with
   its clock in `diagnostics` is honest about its resolution.
5. **`diagnostics` is mandatory, not optional.** Minimum keys, all cheap: `collapsed_segments`,
   `gaps_taken`, `order_violations`, `infeasible`, `logZ`, `grid_concentration`,
   `duration_check`. §11.3 shows each of these catching a failure that the score alone hides.

**The solver registry, mirroring `muvid.align`'s `_ALIGNERS` shape:**

| `name` | `handles` | `requires` | complexity | file section |
|---|---|---|---|---|
| `"ordered_dp"` | ordered, grid | — | `O(K·T·L)` | §3 — **the default** |
| `"ordered_dp_gaps"` | ordered, gaps, skips | — | `O(K·T·L)` | §3 + a background row |
| `"needleman_wunsch"` | ordered, gaps, skips | — | `O(K·M)` | §5 |
| `"viterbi"` | ordered, skips | librosa | `O(K²·T)` | §6.1 |
| `"ctc"` | ordered (tokens) | torchaudio *or* vendored | `O(N·T)` | §6.2 |
| `"subsequence_dtw"` | one artifact at a time | librosa *or* dtaidistance | `O(n·m)` | §4.3 |
| `"changepoint"` | boundaries only, no labels | **ruptures** | `O(K·n)` C | §7 |
| `"hungarian"` | unordered | scipy | `O(n³)` | §8 |
| `"grid_fit"` | grid | — | `O(iters·n)` | §9 |

Six of nine are **numpy-only**. Two use libraries already in p12. **One (`ruptures`) is the
only new dependency this whole layer would add** — and it is the one that produces boundaries
without labels, which is the least central capability.

---

## 14. Dependency and licence summary

| library | in p12? | licence | verified how | verdict |
|---|---|---|---|---|
| numpy 2.2.6 / scipy 1.16.3 | **yes** | BSD | import | required |
| librosa 0.11.0 | **yes** | ISC | import + `pypi.org` | `dtw`, `rqa`, `viterbi`, `transition_*` — all three solver families for free |
| dtaidistance 2.4.0 | **yes** | **Apache-2.0** | PyPI `license_expression` | subsequence DTW with k-best; already used by `kodokan.compare` |
| torch/torchaudio 2.9.0 | **yes** | BSD-2 | import | `forced_align` **deprecated**, see §6.2 |
| mir_eval 0.8.2 | **yes** | MIT | import + PyPI | evaluation, §12 |
| lacing 0.0.34 | **yes** | fleet | import | `quality.boundary_iou`, `interval_iou` |
| **ruptures 1.1.10** | **no** | **BSD-2-Clause** | PyPI + GitHub API | the only proposed new dep; installs clean on Apple Silicon |
| ctc-segmentation 1.7.4 | no | **Apache-2.0** | GitHub API | good fallback for §6.2 |
| tslearn 0.9.0 | no | BSD-2-Clause | PyPI | soft-DTW; not needed |
| stumpy 1.14.1 | no | BSD-3-Clause | PyPI | matrix profile; a *different* problem (motif discovery) |
| fastdtw 0.3.4 | no | MIT | PyPI | approximate DTW; librosa is fast enough |
| hmmlearn 0.3.3 | no | BSD | PyPI | `librosa.sequence.viterbi` covers it |
| **aeneas 1.7.3** | no | **AGPL-3.0** | PyPI | **do not use.** Same class as the `madmom` exclusion in `mixing.audio.beats` |
| **ctc-forced-aligner** | no | **none declared** | GitHub API returns `None` | **do not use.** No licence = all rights reserved |

Everything in §3, §5, §9, §10, §11 runs on **numpy alone**, offline, on Apple Silicon, with no
model weights and no network. That is roughly 250 lines of code and it is the majority of the
value in this file.

---

## 15. Open questions

1. **Extract `muvid.footage.select_score._viterbi`, or write §3 fresh?** §3's DP is ~40 lines
   and I verified it end to end; `select_score`'s is ~200 lines, reviewed, with an
   infeasibility taxonomy and a relaxation ladder I did *not* reimplement. The two solve
   structurally identical problems with different emission semantics (which clip is on air vs
   which artifact is current). Extracting forces a `muvid` change in the same PR and gives the
   error handling for free; writing fresh gives a solver that takes no `ScoreTensor`. **My
   lean [inferred]: write §3 fresh as the numpy kernel, then port `select_score`'s
   infeasibility classification onto it, then have `muvid` call it.** But that is a three-way
   trade and the user should make it.

2. **Is `ruptures` worth a dependency?** It is the only new one this layer needs, it is
   BSD-2, and `KernelCPD` is 660× faster than anything I would write. But its `BaseCost` API
   provably cannot express artifact identity (§7.1), so it can only ever be a *boundary
   proposer* — and `mixing.audio.segmentation` already ships Foote self-similarity and energy
   novelty for that. Concretely: does any planned method need optimal `n_bkps` segmentation
   that Foote novelty + §3's DP cannot deliver?

3. **What replaces `torchaudio.functional.forced_align`?** It is deprecated *in the version
   installed* (§6.2) with a message saying it would be removed in the release it is still in.
   Vendoring the CTC lattice DP (~60 lines) removes the question permanently. Is that in scope
   for v1, or does word-level alignment get deferred behind a `scribed`-style seam?

4. **What is `Placement.confidence` actually made of?** §11.2 shows a posterior that is
   correctly humble about a signal-free artifact *and* confidently wrong about another one.
   Shipping a single float invites callers to trust it. Options: (a) posterior width only,
   (b) posterior width × an agreement term across producers, (c) a struct with the six
   diagnostics of §11.3 and no scalar at all. **[inferred] (b), with (c) in `evidence`.**

5. **Does the solver own the hop, or does the caller?** §1 argues for a fixed 0.5 s solver
   clock with producers resampled in. That makes boundaries quantised to 0.5 s unless the
   refinement step of §3.4 is mandatory. Is sub-hop refinement part of the solver contract, or
   a separate `refine_boundaries(alignment, evidence)` call?

6. **How is an order violation reported?** §4.6 shows monotone solvers failing *silently and
   plausibly* on reordered media. `diagnostics['collapsed_segments']` detects it, but then
   what — abstain, fall back to Hungarian, or split into ordered runs and recurse? The last is
   the right answer **[inferred]** and it is a real algorithm nobody has written here.

7. **Are the tolerances domain config or method config?** §12.1's table says a dance
   8-count and an ASR word need windows two orders of magnitude apart. If tolerance lives in
   the evaluation call, every caller re-derives it; if it lives on the artifact set, it is one
   more thing `Prior` carries. **[inferred]** `Prior` — it is a property of the artifacts, the
   same way `min_len_s` is.

8. **Should the synthetic-evidence generator ship?** Every number in this file came from one,
   including the bug it caught. As a public `alignment.testing.synthetic(...)` it would let
   downstream callers regression-test their own producers against a known answer. That is a
   fourth surface nobody asked for — but it is 60 lines and it is how this layer stays honest.
