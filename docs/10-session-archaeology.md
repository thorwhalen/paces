# 10 — Session archaeology

*What this file is for: these docs are a summary, and summaries lose things. The full
transcript of the session that produced the POC is on disk. If you hit a question these docs
don't answer — an exact parameter, why an approach was abandoned, what an intermediate output
looked like — interrogate the transcript before re-deriving it.*

---

## The transcript

```
~/.claude-iq/projects/-Users-thorwhalen-Downloads/0f75703c-6761-4aa0-b796-aafe02c94155.jsonl
```

**27.7 MB, JSONL, one JSON object per line.** Session id `0f75703c-6761-4aa0-b796-aafe02c94155`,
2026-08-27/28, cwd `~/Downloads`.

Do **not** `cat` it into an agent's context. Query it.

### Shape

Each line has a `type` (`user`, `assistant`, `system`, …) and a `message` with `role` and
`content`. Content is a list of blocks: `{"type": "text"|"tool_use"|"tool_result", …}`.
Confirm the exact keys before writing a big query — the schema varies by client version:

```bash
head -1 <file> | python3 -m json.tool | head -40
python3 -c "
import json,collections
c=collections.Counter(json.loads(l).get('type') for l in open(PATH))
print(c)"
```

### Useful queries

```python
import json

PATH = "~/.claude-iq/projects/-Users-thorwhalen-Downloads/0f75703c-6761-4aa0-b796-aafe02c94155.jsonl"


def blocks(kinds=("text",)):
    """Yield (line_no, role, block) for the block types you care about."""
    for i, line in enumerate(open(PATH)):
        try:
            d = json.loads(line)
        except Exception:
            continue
        m = d.get("message") or {}
        for b in m.get("content") or []:
            if isinstance(b, dict) and b.get("type") in kinds:
                yield i, m.get("role"), b


# every bash command that was run, in order — the real recipe log
for i, role, b in blocks(("tool_use",)):
    if b.get("name") == "Bash":
        print(i, b["input"].get("description"), "::", b["input"]["command"][:160])

# what the user actually asked for, in their own words
for i, role, b in blocks(("text",)):
    if role == "user":
        print(f"--- line {i} ---\n{b['text'][:2000]}")

# find a parameter you half-remember
import re

pat = re.compile(r"sigma_r|det_thresh|ANIME_EVERY|129", re.I)
for i, role, b in blocks(("text", "tool_use")):
    s = json.dumps(b)
    if pat.search(s):
        print(i, s[:300])
```

### The best way to use it

Spawn a **subagent** whose whole job is to answer one question from this file, and have it
return the answer, not the excerpts. The file is 27 MB; a targeted grep-then-read pattern
keeps it out of your context entirely.

## Subagent transcripts from that session

The window-picking and research agents each have their own transcript, with full reasoning
about *why* a particular video window was chosen or rejected:

```
~/.claude-iq/projects/-Users-thorwhalen-Downloads/0f75703c-6761-4aa0-b796-aafe02c94155/subagents/workflows/
    wf_3d11a5f2-2b3/     # clip picking (10 agents) + the thorwhalen.com deploy recipe
    wf_da66bd26-6ba/     # the research behind docs 04–09 in this folder
```

Each has a `journal.jsonl` with one `{"type":"result", …}` line per completed agent — read
**that** first, not the per-agent `agent-*.jsonl` files.

The clip-picking agents' returned notes are unusually good raw material: each explains in
French what is visible in its window, what it rejected and why, and where the block actually
starts and ends. That is a worked example of the kind of judgement the library will need to
either automate or elicit.

## Related work referenced during the session

| what | where |
|---|---|
| The judo stylization pipeline this borrowed from | `~/Dropbox/py/proj/t/kodokan/examples/generate_stylized_clips.py` |
| Its face-privacy rationale (read this before changing anonymisation) | `~/Dropbox/py/proj/t/kodokan/misc/docs/adr-video-face-privacy.md` |
| Its regeneration procedure | `~/Dropbox/py/proj/t/kodokan/misc/docs/regenerate-data.md` |
| The deployed page | `~/Dropbox/py/proj/tt/tw_platform/apps/que_calor_dance/` |
| The deploy PRs, with reasoning in the bodies | `thorwhalen/tw_platform` #128, #129, #130, #131 |

Those four PR descriptions are a compact narrative of the POC's evolution and are worth
reading in order (`gh pr view 128 --repo thorwhalen/tw_platform`).

## What is gone

The working directory was a session scratchpad and has been cleaned up. Lost: `source.mp4`
(200 MB), the extracted audio, the contact sheets, the background plate, the per-frame
feature arrays. All regenerable; `02-technical-recipes.md §1` has the download command,
including the flag without which yt-dlp fails on current YouTube.

The source video is **unlisted** and **copyright Céline Pradeu**. It was used to build a
personal aide-mémoire, and the published extracts are stylized and face-anonymised for that
reason. If this library ships as a product, that constraint is a design input, not a footnote.
