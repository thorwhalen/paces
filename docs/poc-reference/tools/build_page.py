"""Assemble the deployable index.html from the original aide-memoire + the video clips.

Reads page/_head.html (doctype + CSS), page/_body.html, page/_script.js (the original
artifact, split by tools/split), plus clips.json, and writes site/index.html.
"""

import json, os, re

SITE = "https://thorwhalen.com/que_calor_dance/"
CLIPS = json.load(open("clips.json"))
head = open("page/_head.html").read()
body = open("page/_body.html").read()
script = open("page/_script.js").read()

# ── head ───────────────────────────────────────────────────────────────────
head = head.replace(
    "<title>La choré — aide-mémoire</title>",
    "<title>Que Calor — la choré, bloc par bloc</title>\n"
    # Targeted rather than blanket: a bare `robots` noindex also stops the link-preview
    # crawlers (WhatsApp/Signal/iMessage all go through facebookexternalhit, which
    # refuses to scrape a noindex page), so pasting the URL in a chat showed nothing.
    # Naming the search engines keeps the page out of results while letting a chat
    # render the card.
    '<meta name="googlebot" content="noindex, nofollow">\n'
    '<meta name="bingbot" content="noindex, nofollow">\n'
    '<meta name="duckduckbot" content="noindex, nofollow">\n'
    '<meta name="slurp" content="noindex, nofollow">\n'
    '<meta name="yandex" content="noindex, nofollow">\n'
    '<meta name="applebot" content="noindex, nofollow">\n'
    '<meta name="ia_archiver" content="noindex, nofollow">\n'
    '<meta name="theme-color" content="#170D20">\n'
    '<link rel="icon" type="image/png" sizes="192x192" href="media/icon-192.png">\n'
    '<link rel="icon" type="image/png" sizes="64x64" href="media/favicon-64.png">\n'
    '<link rel="apple-touch-icon" href="media/apple-touch-icon.png">\n'
    '<meta property="og:type" content="website">\n'
    '<meta property="og:site_name" content="thorwhalen.com">\n'
    '<meta property="og:locale" content="fr_FR">\n'
    '<meta property="og:url" content="' + SITE + '">\n'
    '<meta property="og:title" content="Que Calor \u2014 la chor\u00e9, bloc par bloc">\n'
    '<meta property="og:description" content="Neuf blocs, 44 \u00d7 8 temps. Le compte au tempo '
    'et un extrait vid\u00e9o par mouvement. Chor\u00e9graphie de C\u00e9line Pradeu.">\n'
    # JPEG first, and small: WhatsApp/iMessage scrape on the SENDING DEVICE with a
    # simpler fetcher than a server-side crawler, and a 60 KB jpeg is the shape they
    # handle most reliably. secure_url / image_src / itemprop are the legacy keys
    # older Android scrapers still read. The png stays as a second og:image.
    '<meta property="og:image" content="' + SITE + 'media/og.jpg">\n'
    '<meta property="og:image:secure_url" content="' + SITE + 'media/og.jpg">\n'
    '<meta property="og:image:width" content="1200">\n'
    '<meta property="og:image:height" content="630">\n'
    '<meta property="og:image:type" content="image/jpeg">\n'
    '<meta property="og:image:alt" content="Que Calor, bloc par bloc">\n'
    '<meta property="og:image" content="' + SITE + 'media/og-square.jpg">\n'
    '<meta property="og:image:width" content="600">\n'
    '<meta property="og:image:height" content="600">\n'
    '<meta property="og:image:type" content="image/jpeg">\n'
    '<link rel="image_src" href="' + SITE + 'media/og.jpg">\n'
    '<meta itemprop="name" content="Que Calor \u2014 la chor\u00e9, bloc par bloc">\n'
    '<meta itemprop="description" content="Neuf blocs, 44 \u00d7 8 temps. Le compte au tempo '
    'et un extrait vid\u00e9o par mouvement. Chor\u00e9graphie de C\u00e9line Pradeu.">\n'
    '<meta itemprop="image" content="' + SITE + 'media/og.jpg">\n'
    '<meta name="twitter:card" content="summary_large_image">\n'
    '<meta name="twitter:title" content="Que Calor \u2014 la chor\u00e9, bloc par bloc">\n'
    '<meta name="twitter:description" content="Neuf blocs, 44 \u00d7 8 temps. Le compte au tempo '
    'et un extrait vid\u00e9o par mouvement.">\n'
    '<meta name="twitter:image" content="' + SITE + 'media/og.jpg">\n'
    '<meta name="description" content="Neuf blocs, 44 \u00d7 8 temps. Le compte au tempo '
    'et un extrait vid\u00e9o par mouvement. Chor\u00e9graphie de C\u00e9line Pradeu.">',
)

EXTRA_CSS = """
/* ═══════════════════════════════════════════════
   Les extraits vidéo — un mouvement par carte
   ═══════════════════════════════════════════════ */
.clip{
  position:relative;aspect-ratio:4/5;border-radius:12px;overflow:hidden;
  background:#100819;border:1px solid var(--ink-3);margin-bottom:.5rem;
}
.clip video{
  position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block;
  opacity:0;transition:opacity .18s;
}
.clip video.on{opacity:1;position:relative}
.clip .badge{
  position:absolute;left:.4rem;top:.4rem;z-index:2;
  font-family:var(--mono);font-size:.6rem;letter-spacing:.14em;text-transform:uppercase;
  background:rgba(16,8,25,.72);color:var(--haze);padding:.16rem .45rem;border-radius:999px;
  backdrop-filter:blur(4px);
}
.clip .fig-inset{
  position:absolute;right:.35rem;bottom:.35rem;z-index:2;
  width:54px;height:68px;padding:3px;border-radius:9px;
  background:rgba(16,8,25,.6);backdrop-filter:blur(5px);
  display:flex;align-items:flex-end;justify-content:center;
}
.clip .fig-inset svg.fig{height:100%;width:auto;opacity:0;position:absolute;bottom:3px}
.clip .fig-inset svg.fig.on{opacity:.95;position:relative}
.tabs{display:flex;gap:.3rem;margin:0 0 .5rem;flex-wrap:wrap}
.tab{
  border:1px solid var(--ink-3);background:transparent;border-radius:999px;
  padding:.2rem .6rem;font-size:.72rem;font-family:var(--mono);color:var(--haze);
}
.tab.on{background:var(--c-soft);border-color:var(--c-mid);color:var(--paper)}
.seen{
  font-size:.86rem;line-height:1.4;color:#EBD9EF;margin:0 0 .7rem;
  border-left:2px solid var(--c-mid);padding-left:.6rem;
}
.jump{display:flex;flex-wrap:wrap;gap:.3rem;margin-top:.75rem}
.jump a{
  font-family:var(--mono);font-size:.68rem;text-decoration:none;color:var(--haze);
  border:1px solid var(--ink-3);border-radius:999px;padding:.18rem .5rem;white-space:nowrap;
}
.jump a:hover{color:var(--paper);border-color:var(--c-mid);background:var(--c-soft)}
.jump a.gif{color:var(--c);border-color:var(--c-mid)}

/* le filage complet, sous le compteur */
.filage{
  margin-top:1.2rem;border:1px solid var(--ink-3);border-radius:16px;overflow:hidden;
  background:linear-gradient(180deg,var(--ink-2),#1d1129);
}
.filage summary{
  cursor:pointer;list-style:none;padding:.85rem 1.1rem;display:flex;align-items:center;gap:.7rem;
  font-weight:700;
}
.filage summary::-webkit-details-marker{display:none}
.filage summary::before{content:"▶";color:var(--sun);font-size:.8rem}
.filage[open] summary::before{content:"▼"}
.filage summary .hint-txt{font-family:var(--mono);font-size:.7rem;color:var(--haze);
  letter-spacing:.1em;text-transform:uppercase;margin-left:auto}
.filage video{display:block;width:100%;background:#000}
.howto img{display:block;width:100%;height:auto;background:var(--ink)}
.howto-note{padding:.7rem 1.1rem 1rem;font-size:.82rem;color:var(--haze)}
.howto-note a{color:var(--sun)}
.credit{
  margin-top:1.4rem;font-size:.82rem;color:var(--haze);
  border-top:1px solid var(--ink-3);padding-top:.9rem;
}
.credit a{color:var(--haze)}\n.credit .yt{font-family:var(--mono);font-size:.78em;opacity:.8}
.grid{grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}
@media (max-width:640px){
  .clip .fig-inset{width:44px;height:56px}
}

/* ═══════════════════════════════════════════════
   Mode lecture : le bandeau se réduit pour ne pas
   manger la carte vers laquelle on vient de sauter
   ═══════════════════════════════════════════════ */
body.playing .transport{padding:.5rem .75rem}
body.playing #reset,
body.playing #sound,
body.playing .tempo,
body.playing .now .label,
body.playing .now .next{display:none}
body.playing .btn-play{min-width:5.2rem;padding:.4rem .85rem;font-size:.84rem}
body.playing .count{font-size:2.1rem}
body.playing .transport-row{gap:.45rem .8rem;flex-wrap:nowrap}
body.playing .now{flex:1 1 auto;min-width:0}
body.playing .now .title{
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:.92rem;
}
body.playing .ribbon-wrap{margin-top:.5rem;padding-top:.45rem}
@media (max-width:640px){
  body.playing .pips{display:none}
}

/* la carte visée se pose SOUS le bandeau collant, jamais dessous */
.card{scroll-margin-top:calc(var(--th, 7rem) + 14px)}

.byline{
  margin:.65rem 0 0;font-size:.85rem;color:var(--haze);
}
.byline b{color:var(--paper);font-weight:700}
.byline a{color:var(--sun);text-decoration:none;border-bottom:1px solid rgba(255,192,46,.35)}
.byline a:hover{border-bottom-color:var(--sun)}
"""
head = head + EXTRA_CSS  # _head.html ends INSIDE the <style> block

# ── body ───────────────────────────────────────────────────────────────────
body = body.replace(
    "<h1>La choré,<br>bloc par bloc</h1>", "<h1>Que Calor,<br>bloc par bloc</h1>"
)
body = body.replace(
    "Neuf blocs, 44 × 8 temps. Lance le compte : les figurines dansent au tempo que tu règles, "
    "et le ruban montre où tu en es.",
    "Neuf blocs, 44 × 8 temps, ~129 bpm. Lance le compte : le ruban montre où tu en es, et chaque "
    "carte rejoue le mouvement en boucle, découpé depuis la vidéo de Céline.",
)
body = body.replace('value="100"', 'value="129"')


body = body.replace(
    "</header>",
    '    <p class="byline">Chorégraphie, danse et vidéo&nbsp;: <b>Céline Pradeu</b> · '
    '<a href="https://youtu.be/q_TUyxUhoEw" target="_blank" rel="noopener">'
    "voir la vidéo d'origine&nbsp;↗</a></p>\n  </header>",
)

FILAGE = """
    <details class="filage">
      <summary>Le filage complet <span class="hint-txt">2 min 46 · avec la musique</span></summary>
      <video src="media/filage.mp4" poster="media/filage.jpg" controls preload="none" playsinline></video>
    </details>

    <details class="filage howto">
      <summary>Comment lire une carte <span class="hint-txt">ce qui se clique</span></summary>
      <img src="media/howto.jpg" loading="lazy" decoding="async"
           alt="Une carte annotée : le badge dit si l'extrait vient du filage ou de
                l'explication, les onglets basculent entre les deux extraits du bloc, la
                légende décrit ce qu'on voit, le découpage donne le nombre de 8 par
                intention, et « filage » et « explication » sont des liens qui ouvrent la
                vidéo d'origine à cet instant.">
      <p class="howto-note">Version pleine résolution&nbsp;:
        <a href="media/howto.png" target="_blank" rel="noopener">l'image seule</a>.</p>
    </details>
"""
body = body.replace(
    '  <main class="grid" id="grid"></main>',
    FILAGE + '\n  <main class="grid" id="grid"></main>',
)

OPEN_LIST = """    <ul class="open">
      <li><b>Bloc&nbsp;3</b> — tranché&nbsp;: c'est bien un mouvement de bras, pas les déhanchés.
          Céline dit «&nbsp;faire des droites avec les bras, très net, un peu continu, pour casser
          le côté rebondi&nbsp;» — sa petite signature.</li>
      <li><b>Bloc&nbsp;9</b> — tranché&nbsp;: le cycle de 2&nbsp;×&nbsp;8 (avancer, puis bras en
          l'air et reculer) est bien répété 4&nbsp;fois pour remplir les 8&nbsp;×&nbsp;8.</li>
      <li><b>Bloc&nbsp;6</b> — le passage genou&nbsp;→&nbsp;front suit les paroles
          («&nbsp;se hace difícil respirar&nbsp;») et reste facultatif&nbsp;: «&nbsp;si vous le
          sentez, vous le faites&nbsp;».</li>
      <li><b>Blocs&nbsp;1 et 2</b> — dans la vidéo l'entrée se fait en diagonale depuis le fond,
          bras ouverts en seconde sur la 2<sup>e</sup> moitié. Le pas isolé (bloc&nbsp;1) est montré
          face caméra, ce n'est pas l'orientation de scène.</li>
    </ul>"""
body = re.sub(r'    <ul class="open">.*?</ul>', OPEN_LIST, body, flags=re.S)
body = body.replace("<h3>À trancher</h3>", "<h3>Ce que la vidéo tranche</h3>")

CREDIT = """
    <p class="credit">
      Chorégraphie, danse et vidéo&nbsp;: <b>Céline&nbsp;Pradeu</b> — pour le mariage d'Emmanuelle
      et&nbsp;Olivier. Les extraits de cette page sont découpés de
      <a href="https://youtu.be/q_TUyxUhoEw" target="_blank" rel="noopener">sa vidéo</a>
      (<span class="yt">youtu.be/q_TUyxUhoEw</span>) et servent uniquement d'aide-mémoire
      personnelle&nbsp;; page non&nbsp;référencée par les moteurs de recherche. Ils sont <b>stylisés</b> — rendu dessin animé,
      décor aplati et visage anonymisé — pour ne pas rediffuser son image&nbsp;; la vidéo
      d'origine reste la référence. Musique&nbsp;: <i>Que Calor</i>. Les timings en&nbsp;secondes
      renvoient à la vidéo d'origine.
    </p>"""
body = body.replace("  </footer>", CREDIT + "\n  </footer>")

# ── script ─────────────────────────────────────────────────────────────────
by_block = {}
for c in CLIPS:
    by_block.setdefault(c["block"], []).append(
        {
            k: c[k]
            for k in (
                "id",
                "src",
                "start",
                "dur",
                "cap",
                "tab",
                "fig",
                "yt_expl",
                "yt_run",
            )
        }
    )
MEDIA = "const MEDIA = " + json.dumps(by_block, ensure_ascii=False, indent=1) + ";\n\n"
MEDIA += 'const YT = "https://youtu.be/q_TUyxUhoEw?t=";\n'
MEDIA += 'const mmss = s => `${Math.floor(s/60)}:${String(Math.round(s)%60).padStart(2,"0")}`;\n\n'
script = MEDIA + script


# ── la vidéo tranche : on corrige le texte des blocs 2, 3 et 9 ──────────────
script = script.replace(
    '{eights:5, label:"Pas pointe et ronde"}',
    '{eights:5, label:"Pas pointe et ronde — « marche, pose, marche, ramène »"}',
)
script = script.replace(
    '{eights:4, label:"Grand cercle des deux bras"}',
    '{eights:4, label:"Grandes droites des deux bras — « très net, un peu continu »"}',
)
script = script.replace('    note:"À remplacer par les 1ers déhanchés ?" },', "  },")
script = script.replace('    note:"Cycle de 2 × 8 à répéter 4 fois ?" }', "  }")


# ── le bandeau collant ne doit plus recouvrir la carte visée ────────────────
script = script.replace(
    """function scrollToCard(si){
  const el = cards()[si];
  const r = el.getBoundingClientRect();
  if (r.top < 150 || r.bottom > window.innerHeight - 20) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}""",
    """const transportEl = $('.transport');

/* --th = hauteur réelle du bandeau ; sert de marge de défilement aux cartes */
function measure(){
  document.documentElement.style.setProperty('--th', transportEl.offsetHeight + 'px');
}
addEventListener('resize', measure);
if (window.ResizeObserver) new ResizeObserver(measure).observe(transportEl);
measure();

function scrollToCard(si){
  const el = cards()[si];
  const top = el.getBoundingClientRect().top;
  const th = transportEl.offsetHeight + 14;
  if (top < th || top > window.innerHeight * 0.55) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}""",
)

script = script.replace(
    """  $('#play').textContent = 'Pause';
  loop();""",
    """  $('#play').textContent = 'Pause';
  document.body.classList.add('playing');
  measure();
  loop();""",
)
script = script.replace(
    """  clearTimeout(timer);
  $('#play').textContent = 'Lancer';""",
    """  clearTimeout(timer);
  $('#play').textContent = 'Lancer';
  document.body.classList.remove('playing');
  measure();""",
)

OLD_STAGE = """  const list = sec.shownSubs || sec.subs;
  const pair = sec.figs.length > 1;
  const duo  = pair && sec.figs[0].k.indexOf('clap') === 0;

  const stage = `<div class="stage${pair ? ' pair' : ''}${duo ? ' duo' : ''}">`
    + sec.figs.map(f => `<div class="fig-box">${figSvg(f.k)}${f.l ? `<span class="fig-label">${f.l}</span>` : ''}</div>`).join('')
    + `</div>`;

  card.innerHTML = stage
    + `<div class="card-head"><span class="num">${sec.n}</span>`"""
NEW_STAGE = """  const list = sec.shownSubs || sec.subs;
  const clips = MEDIA[sec.n] || [];

  const stage = `<div class="clip">`
    + `<span class="badge">${clips[0] ? (clips[0].src === 'RT' ? 'filage' : 'explication') : ''}</span>`
    + clips.map((c, i) => `<video data-i="${i}" class="${i ? '' : 'on'}" src="media/${c.id}.mp4"`
        + ` poster="media/${c.id}.jpg" muted loop playsinline preload="none"`
        + ` aria-label="${c.cap.replace(/"/g, '&quot;')}"></video>`).join('')
    + `<span class="fig-inset">`
    + clips.map((c, i) => figSvg(c.fig, i ? '' : 'on')).join('')
    + `</span></div>`
    + (clips.length > 1
        ? `<div class="tabs">` + clips.map((c, i) =>
            `<button class="tab${i ? '' : ' on'}" data-i="${i}">${c.tab}</button>`).join('') + `</div>`
        : '')
    + (clips[0] ? `<p class="seen">${clips[0].cap}</p>` : '');

  card.innerHTML = stage
    + `<div class="card-head"><span class="num">${sec.n}</span>`"""
assert OLD_STAGE in script
script = script.replace(OLD_STAGE, NEW_STAGE)

OLD_TAIL = """    + (sec.note ? `<p class="note">${sec.note}</p>` : '');

  card.addEventListener('click', () => goTo(startBeatOf(si), true));"""
NEW_TAIL = """    + (sec.note ? `<p class="note">${sec.note}</p>` : '')
    + (clips[0]
        ? `<div class="jump">`
          + `<a href="${YT}${Math.max(0, Math.round(clips[0].yt_run) - 1)}" target="_blank" rel="noopener">filage ${mmss(clips[0].yt_run)}</a>`
          + `<a href="${YT}${Math.max(0, Math.round(clips[0].yt_expl) - 1)}" target="_blank" rel="noopener">explication ${mmss(clips[0].yt_expl)}</a>`
          + `<a class="gif" href="media/${clips[0].id}.gif" download>gif ↓</a>`
          + `</div>`
        : '');

  // onglets : bascule entre les extraits d'une même carte
  card.querySelectorAll('.tab').forEach(t => t.addEventListener('click', e => {
    e.stopPropagation();
    const i = +t.dataset.i;
    card.querySelectorAll('.tab').forEach(x => x.classList.toggle('on', x === t));
    card.querySelectorAll('.clip video').forEach(v => {
      const on = +v.dataset.i === i;
      v.classList.toggle('on', on);
      if (on) { v.play().catch(() => {}); } else { v.pause(); }
    });
    card.querySelectorAll('.fig-inset svg.fig').forEach((f, k) => f.classList.toggle('on', k === i));
    const c = clips[i];
    card.querySelector('.seen').textContent = c.cap;
    card.querySelector('.badge').textContent = c.src === 'RT' ? 'filage' : 'explication';
    const j = card.querySelectorAll('.jump a');
    j[0].href = YT + Math.max(0, Math.round(c.yt_run) - 1);
    j[0].textContent = 'filage ' + mmss(c.yt_run);
    j[1].href = YT + Math.max(0, Math.round(c.yt_expl) - 1);
    j[1].textContent = 'explication ' + mmss(c.yt_expl);
    j[2].href = 'media/' + c.id + '.gif';
  }));

  card.addEventListener('click', e => {
    if (e.target.closest('a, button')) return;  // la vignette aussi saute au bloc
    goTo(startBeatOf(si), true);
  });"""
assert OLD_TAIL in script
script = script.replace(OLD_TAIL, NEW_TAIL)

script = script.replace(
    'function figSvg(key){\n  return `<svg class="fig m-${key}" viewBox="0 0 160 200" role="img" aria-hidden="true">`',
    'function figSvg(key, cls){\n  return `<svg class="fig m-${key} ${cls || \'\'}" viewBox="0 0 160 200" role="img" aria-hidden="true">`',
)
script = script.replace(
    '+ `<line class="floor" x1="14" y1="188" x2="146" y2="188"/></svg>`', "+ `</svg>`"
)
script = script.replace("setTempo(100);", "setTempo(129);")
script = script.replace(
    "let beat = 0, playing = false, bpm = 100,",
    "let beat = 0, playing = false, bpm = 129,",
)

OBSERVER = """

/* ═══════════════════════════════════════════════
   Les vidéos ne tournent que quand on les voit
   ═══════════════════════════════════════════════ */
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
if (!reduce) {
  const io = new IntersectionObserver(entries => {
    entries.forEach(e => {
      const v = e.target;
      if (e.isIntersecting && v.classList.contains('on')) v.play().catch(() => {});
      else v.pause();
    });
  }, { rootMargin: '80px 0px', threshold: 0.25 });
  document.querySelectorAll('.clip video').forEach(v => io.observe(v));
}
"""
script += OBSERVER

os.makedirs("site", exist_ok=True)
open("site/index.html", "w").write(
    head + body + "<script>" + script + "</script>\n</body>\n</html>\n"
)
print("site/index.html", os.path.getsize("site/index.html"), "bytes")
