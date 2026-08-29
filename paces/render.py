"""Render a :class:`~paces.model.StepDocument` into learning material.

The renderer depends on the document and :func:`~paces.model.resolve` — never
on the analyser. v1 ships one renderer: a self-contained HTML practice page
(steps, counts, captions, deep links into the sources, and — when the document
has a metric grid — a count-along transport that paces you through the
routine, which is the behaviour the package is named after).
"""

from __future__ import annotations

import html
import json
from fractions import Fraction

from paces.model import Source, SourceSpan, Step, StepDocument, resolve

#: Span roles shown as deep links, in display order.
ROLE_LABELS = {
    "performance": "run-through",
    "instruction": "breakdown",
    "closeup": "close-up",
}


def _mmss(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"


def _deep_link(source: Source, start_s: float) -> str | None:
    uri = source.uri
    if not uri.startswith(("http://", "https://")):
        return None
    if "youtu" in uri:
        joiner = "&" if "?" in uri else "?"
        return f"{uri}{joiner}t={int(start_s)}"
    return uri


def _span_links(spans: list[SourceSpan], sources: dict[str, Source]) -> str:
    parts = []
    for span in spans:
        start_s = float(Fraction(span.start))
        role = ROLE_LABELS.get(span.role, span.role)
        source = sources.get(span.source)
        text = f"{role} {_mmss(start_s)}"
        url = _deep_link(source, start_s) if source else None
        if url:
            parts.append(
                f'<a class="span" href="{html.escape(url)}" target="_blank" '
                f'rel="noopener">{html.escape(text)}</a>'
            )
        else:
            parts.append(f'<span class="span">{html.escape(text)}</span>')
    return " ".join(parts)


def _captions(step: Step) -> str:
    rows = []
    for span in step.spans:
        if span.caption:
            label = f"<b>{html.escape(span.label)}</b> — " if span.label else ""
            rows.append(f'<p class="cap">{label}{html.escape(span.caption)}</p>')
    return "\n".join(rows)


def _step_card(
    step: Step,
    *,
    ordinal: int,
    doc: StepDocument,
    sources: dict[str, Source],
    cues_by_step: dict[str, list],
) -> str:
    unit = step.duration.unit
    badges = []
    if step.optional:
        badges.append('<span class="badge">optional</span>')
    if step.variant_of:
        badges.append(
            f'<span class="badge">variant of {html.escape(step.variant_of)}</span>'
        )
    repeat = f" × {step.repeat}" if step.repeat > 1 else ""
    subs = ""
    if step.steps:
        items = []
        for child in step.steps:
            child_bits = [
                f"<b>{html.escape(child.duration.value)} {html.escape(child.duration.unit)}</b>",
                html.escape(child.name),
            ]
            if child.spans:
                child_bits.append(_span_links(child.spans, sources))
            extra = _captions(child)
            items.append(f"<li>{' — '.join(child_bits)}{extra}</li>")
        subs = f'<ol class="subs">{"".join(items)}</ol>'
    cues = "".join(
        f'<p class="cue">♪ {html.escape(cue.text)}</p>'
        for cue in cues_by_step.get(step.id, [])
    )
    description = (
        f'<p class="desc">{html.escape(step.description)}</p>'
        if step.description
        else ""
    )
    links = _span_links(step.spans, sources)
    links_paragraph = f'<p class="links">{links}</p>' if links else ""
    return f"""
  <section class="card" id="step-{html.escape(step.id)}">
    <header>
      <span class="n">{ordinal}</span>
      <h2>{html.escape(step.name)}</h2>
      <span class="dur">{html.escape(step.duration.value)} {html.escape(unit)}{repeat}</span>
      {" ".join(badges)}
    </header>
    {description}
    {links_paragraph}
    {_captions(step)}
    {subs}
    {cues}
  </section>"""


def _transport(doc: StepDocument) -> str:
    """The count-along transport — only when the grid can pace us."""
    grid = doc.metric
    if grid is None or grid.tempo_bpm is None:
        return ""
    resolved = resolve(doc)
    timeline = [
        {
            "id": row["id"],
            "name": row["name"],
            "offset": row["offset"],
            "duration": row["duration"],
        }
        for row in resolved["steps"]
    ]
    config = {
        "bpm": float(Fraction(grid.tempo_bpm)),
        "subdivisions": grid.subdivisions,
        "unit": grid.unit,
        "totalUnits": resolved["total_units"],
        "steps": timeline,
    }
    return f"""
  <div class="transport">
    <button id="play">▶ count me in</button>
    <span id="pos">–</span>
    <span id="now"></span>
  </div>
  <script>
  const G = {json.dumps(config, ensure_ascii=False)};
  let running = false, startedAt = 0, raf = 0;
  const beatSeconds = 60 / G.bpm;
  const audio = new (window.AudioContext || window.webkitAudioContext)();
  let lastBeat = -1;
  function click(accent) {{
    const osc = audio.createOscillator(), gain = audio.createGain();
    osc.frequency.value = accent ? 1200 : 800;
    gain.gain.setValueAtTime(0.12, audio.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + 0.06);
    osc.connect(gain).connect(audio.destination);
    osc.start(); osc.stop(audio.currentTime + 0.07);
  }}
  function tick() {{
    if (!running) return;
    const elapsed = (performance.now() - startedAt) / 1000;
    const beat = Math.floor(elapsed / beatSeconds);
    const unitPos = elapsed / (beatSeconds * G.subdivisions);
    if (beat !== lastBeat) {{ click(beat % G.subdivisions === 0); lastBeat = beat; }}
    if (unitPos >= G.totalUnits) {{ stop(); return; }}
    const step = G.steps.findLast(s => unitPos >= s.offset) || G.steps[0];
    document.getElementById('pos').textContent =
      `${{G.unit}} ${{Math.floor(unitPos) + 1}} / ${{G.totalUnits}}`;
    document.getElementById('now').textContent = step ? step.name : '';
    document.querySelectorAll('.card').forEach(c => c.classList.remove('live'));
    if (step) {{
      const card = document.getElementById('step-' + step.id);
      if (card) card.classList.add('live');
    }}
    raf = requestAnimationFrame(tick);
  }}
  function stop() {{
    running = false; cancelAnimationFrame(raf); lastBeat = -1;
    document.getElementById('play').textContent = '▶ count me in';
  }}
  document.getElementById('play').addEventListener('click', () => {{
    if (running) {{ stop(); return; }}
    audio.resume(); running = true; startedAt = performance.now();
    document.getElementById('play').textContent = '⏸ stop';
    tick();
  }});
  </script>"""


_CSS = """
  :root { --ink:#1c1a22; --paper:#faf8f4; --accent:#7c3aed; --soft:#e8e2f5; }
  * { box-sizing: border-box; }
  body { margin:0; padding:2rem 1rem 4rem; background:var(--paper); color:var(--ink);
         font:16px/1.55 system-ui, sans-serif; }
  main { max-width: 46rem; margin: 0 auto; }
  h1 { font-size:1.9rem; margin:0 0 .3rem; }
  .meta { color:#666; margin:0 0 1.4rem; }
  .transport { display:flex; gap:1rem; align-items:center; margin:0 0 1.6rem;
               padding:.7rem 1rem; background:var(--soft); border-radius:.7rem; }
  .transport button { font:inherit; padding:.4rem .9rem; border:0; border-radius:.5rem;
                      background:var(--accent); color:#fff; cursor:pointer; }
  #now { font-weight:600; }
  .card { background:#fff; border:1px solid #e5e1d8; border-radius:.8rem;
          padding:1rem 1.2rem; margin:0 0 1rem; }
  .card.live { outline:3px solid var(--accent); }
  .card header { display:flex; gap:.7rem; align-items:baseline; flex-wrap:wrap; }
  .card h2 { font-size:1.15rem; margin:0; }
  .n { background:var(--accent); color:#fff; border-radius:50%; width:1.6rem;
       height:1.6rem; display:inline-flex; align-items:center; justify-content:center;
       font-size:.9rem; flex:none; }
  .dur { color:#666; font-size:.9rem; }
  .badge { background:var(--soft); border-radius:.4rem; padding:.05rem .45rem;
           font-size:.78rem; }
  .links { margin:.4rem 0 .2rem; }
  .span { margin-right:.8rem; font-size:.9rem; }
  .cap, .desc { margin:.3rem 0; }
  .cue { color:var(--accent); font-style:italic; margin:.3rem 0 0; }
  .subs { margin:.5rem 0 0; padding-left:1.3rem; }
  .subs li { margin:.25rem 0; }
  .questions { margin-top:2rem; }
  .questions h2 { font-size:1.1rem; }
  footer { margin-top:2.5rem; color:#666; font-size:.85rem; }
"""


def render_html(doc: StepDocument) -> str:
    """The practice page: steps, counts, deep links, captions, and (with a
    grid) the count-along transport. Self-contained; media-free by design —
    derived clips arrive via ``ArtifactRef`` when the media layer exists."""
    sources = {source.id: source for source in doc.sources}
    cues_by_step: dict[str, list] = {}
    for cue in doc.cues:
        cues_by_step.setdefault(cue.anchor.step, []).append(cue)

    grid = doc.metric
    meta_bits = []
    if grid is not None:
        total = resolve(doc)["total_units"]
        meta_bits.append(f"{int(total)} × {grid.unit}")
        if grid.tempo_bpm:
            meta_bits.append(f"~{grid.tempo_bpm} bpm")
    meta = " · ".join(meta_bits)

    cards = "\n".join(
        _step_card(
            step, ordinal=i + 1, doc=doc, sources=sources, cues_by_step=cues_by_step
        )
        for i, step in enumerate(doc.steps)
    )

    questions = ""
    if doc.questions:
        items = []
        for question in doc.questions:
            status = f" — <i>{question.resolution}</i>" if question.resolution else ""
            items.append(
                f"<li><b>[{question.status}]</b> "
                f"{html.escape(question.text)}{status}</li>"
            )
        questions = (
            f'<div class="questions"><h2>Open questions</h2>'
            f"<ul>{''.join(items)}</ul></div>"
        )

    credits = f"<footer>{html.escape(doc.credits)}</footer>" if doc.credits else ""
    return f"""<!doctype html>
<html lang="{html.escape(doc.lang)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(doc.title)}</title>
<style>{_CSS}</style>
</head>
<body>
<main>
  <h1>{html.escape(doc.title)}</h1>
  <p class="meta">{html.escape(meta)}</p>
{_transport(doc)}
{cards}
{questions}
{credits}
</main>
</body>
</html>
"""
