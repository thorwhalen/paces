# 08 — Naming candidates (PyPI-verified)

**What this file is for.** You are about to build a library that ingests instructional media
(a video of someone teaching something + optional notes + a steering prompt), segments it into
named **steps**, builds a structured intermediate representation of those steps ("like an AST"),
and renders that IR into learning materials (interactive practice page, printable guide, …).
`stepped` is a placeholder nobody loves. This file is the naming work already done for you: **684
candidate names were checked against PyPI on 2026-08-28, 466 came back available**, organised into
six families with a one-line rationale each, plus a shortlist of 10 with real arguments, a single
recommended favourite, and a separate recommendation for what to call the axis the brief calls
"SUBJECT" (the *kind of thing being taught*). Do not re-run the availability sweep; do re-verify
the two or three names you actually intend to claim, since PyPI moves.

---

## 0. READ THIS FIRST — the brief was corrected after §3–§5 were written

The user reviewed this file and narrowed the criteria. Their words:

> *"astep is great but the AST idea wasn't for the name, but the architecture. I'd rather the
> name be reminiscent of **what the tool does for the user, not how**. Also, I do like **short
> and punchy, and memorable**."*

They also said the 684-name sweep was *"a bit overkill, but thanks, now we have a lot of
choices to pick from"* — so **do not run another sweep.** §3's tables remain a good pool; just
read them through the corrected filter.

That filter rules out the whole "parsing / structure" family, including **`astep`** (§5) —
it encodes the architecture, which is exactly what the user does not want in the name. It also
demotes the domain-technical names (`kineme`, `spartito`, `korvai`, `adavu`, `laban`): they
describe the material or the mechanism, not the user's gain.

What the tool does *for the user*, in one line: **it takes a video of someone teaching
something and hands you back a thing you can practise with, step by step, at your own pace.**

### The re-focused shortlist (all re-verified free on PyPI, 2026-08-28)

| name | len | the argument |
|---|---|---|
| **`paces`** | 5 | *Put it through its paces* = drill it until you own it — the user's gain. And **the tool literally paces you**: the POC's whole interface is a metronome walking you through the steps at a tempo you set. One word carrying both the benefit and the signature feature, with no reference to how any of it works. Short, plain English, easy to say and spell, no collision with a common programming term. |
| **`marking`** | 7 | In dance, **marking** is walking a routine through at low intensity to learn and remember it — the exact thing the page lets you do. The `-ing` gerund is the same shape as the fleet's `lacing`. Insiders will smile; outsiders still read something sensible. Cost: a very common English word (poor SEO, ambiguous in a file that also does markup), and npm is taken if a JS companion ever ships. |
| **`woodshed`** | 8 | Jazz slang: to *woodshed* is to go off alone and drill the hard passage until it is yours. The warmest and most memorable name on the list, and the only one that names the **experience** rather than the artefact. Cost: longest of the three, and "shed" invites the obvious joke. |
| **`byheart`** | 7 | The plainest possible statement of the goal — you end up knowing it *by heart*. Instantly understood, zero jargon, memorable. Cost: reads as two words jammed together, and slightly twee for a library. |
| **`countin`** | 7 | The **count-in** — "5, 6, 7, 8" — is what a teacher gives you right before you dance. Evocative and punchy. Cost: the most dance-specific of the five, at the moment you are generalising away from dance. |

**Recommendation: `paces`.** It is the only candidate that is short, plain, memorable, *and*
says both halves of the user's promise — you practise it, and the tool sets the pace. It ages
well across subgenres: you put a recipe, a kata or a guitar solo through its paces too.

Runner-up `marking` if the user wants the dance-insider register and accepts the common-word
cost; `woodshed` if charm matters more than length.

Other free names in this register, from a focused re-check on 2026-08-28, if none of the five
land: `spotting`, `shadowing`, `phrasing`, `cadence`, `runthru`, `getgood`, `walkit`, `aceit`,
`nailed`, `coachable`, `themoves`, `loopit`, `shedding`, `drillo`, `practica`, `eightcounts`,
`countoff`, `cuecards`, `katas`, `learnable`.

*(§4's shortlist and §5's `astep` recommendation below are kept for the record and for their
arguments, but they answer the older, broader brief.)*

---

## 1. Method, and exactly what "available" means here (VERIFIED)

Every name below was checked with:

```bash
curl -s -o /dev/null -w "%{http_code}" https://pypi.org/pypi/<name>/json
# 404 = no project with that (normalised) name exists  → available
# 200 = taken
```

Run in parallel batches; raw results are reproducible with the same one-liner.

**Normalisation — I probed this rather than assuming it, and the brief's assumption needs one
correction:**

| probe | result | conclusion |
|---|---|---|
| `scikit-learn` / `scikit_learn` | `200` / `200` | `-`, `_`, `.` **do** collapse to the same project |
| `scikitlearn` | `404` | run-together spelling is a **different, separate** project |
| `stepwise` | `200` | taken (a wetlab-protocol library, last release 2022-08-01) |
| `step-wise` / `step_wise` | `404` / `404` | **free** — and identical to each other |

So `step-wise` *is* actually claimable even though `stepwise` is not. Treat that as a real option,
not a loophole: PEP 503 normalisation makes `step-wise` and `step_wise` one name, and `pip install
step-wise` would not collide with `stepwise`. It would, however, collide *in a human's head* with
the existing `stepwise`, so I have not shortlisted it.

**What "available" does NOT cover.** I verified PyPI only, except for the shortlist (see §4), where
I also checked npm and GitHub handles. I did **not** check trademarks, RTD subdomains, or
conda-forge.

---

## 2. The user's own four tries — all still free (VERIFIED)

| name | PyPI | note |
|---|---|---|
| `stepped` | **404 — free** | still claimable; the objection is taste, not availability |
| `tutorize` | **404 — free** | " |
| `drilled` | **404 — free** | " |
| `routined` | **404 — free** | " |

Adjacent forms, also verified free: `steppee`, `steplee`, `stepee`, `stepla`, `steppa`, `steppi`,
`steppo`, `stepster`, `stepsy`, `drills`, `drillee`, `drillery`, `drilly`, `routiner`, `routinize`,
`routinal`, `routinery`, `routino`.
Adjacent forms **taken**: `stepper`, `stepping`, `steppy`, `stepz`, `stepio`, `stepcast`,
`stepcraft`, `steptree`, `stepguide`, `stepwise`, `drill`, `routina`, `routinely`.

---

## 3. Candidates by family (every one below is verified `404` on PyPI)

### 3.1 Steps / sequence

| name | one-line rationale |
|---|---|
| `stepped` | the placeholder; past participle reads as "already broken into steps" |
| `steplet` | a step is the leaf node; `-let` says "small named unit" |
| `stepline` | the routine as a line of steps, and it hints at a timeline |
| `stepform` | a step plus its shape/notation; also the martial-arts sense of "form" |
| `stepscore` | steps written as a score — the two central metaphors welded together |
| `stepset` | the enumerated set of steps a routine is made of |
| `stepbook` | the printed-guide output in the name |
| `stepkit` | steps + toolkit, plain and unmysterious |
| `stepwork` | what you do in the studio; also "the work is the steps" |
| `stepful` | adjective in the house style of `artful` |
| `steplike` | "shaped like steps" — the IR's claim about any input |
| `stepdoc` | steps → document, the render half of the pipeline |
| `stepify` | verb: turn media into steps |
| `stepster` | agentive and playful; someone/something that steps |
| `step-wise` | claimable *because* `stepwise` is a different name (see §1) — but confusable |
| `pasos` | Spanish "steps"; native to the Latin-dance first use case |
| `pasito` / `pasitos` | Spanish "little step(s)"; warm, diminutive, salsa-flavoured |
| `passo` | Italian/Portuguese "step"; single syllable, clean |
| `pasly` | invented from *paso* in the fleet's `-ly`/`-ee` register |
| `secuencia` / `secuenc` | Spanish "sequence"; the whole routine as one ordered object |
| `enfilade` | a line of connected rooms you pass through in order — the routine as architecture |
| `phrasing` | how a performer groups steps into phrases; gerund matches `lacing` |
| `phraser` | the thing that cuts continuous motion into phrases |
| `eightcount` / `eightcounts` | the POC's actual unit of time; instantly legible to any dancer |
| `countoff` | the "5-6-7-8" that starts every run — the transport in one word |
| `segmentum` | Latinate for "the segment"; sounds like an IR node type |

### 3.2 Learning / practice / rehearsal

| name | one-line rationale |
|---|---|
| `woodshed` | jazz slang for going away alone to drill the hard part — the library *is* the woodshed |
| `woodshedding` / `shedding` | gerund forms of the same, matching `lacing` |
| `rehearsy` | rehearsal made small and friendly, house style |
| `practicum` | a supervised practical course — exactly what the output page is |
| `practify` | verb: turn material into practice |
| `praxie` / `praxly` / `praxio` | invented from *praxis* (practice as embodied doing) since `praxis` is taken |
| `etudely` / `etudify` / `etudee` | an étude is a study written to drill one skill; `etude` itself is taken |
| `riyaz` / `riyaaz` | Hindustani music's word for daily disciplined practice |
| `sadhana` | Sanskrit: sustained practice toward mastery |
| `abhyasa` | Sanskrit: repetition as the mechanism of learning — the loop the page enforces |
| `shuhari` | 守破離, the three stages of mastery (follow / break / transcend) — a learning arc in one word |
| `renshu` | 練習, Japanese "practice"; short, hard consonants, unclaimed |
| `suburi` | solo repetition drill in kendo — one movement, many reps |
| `uchikomi` | judo's repetition-entry drill; the canonical "do the entry 100 times" |
| `randori` | free practice after the drills — the "now perform it" half |
| `embu` | a prearranged demonstration form — literally "a routine performed to be seen" |
| `katas` | `kata` is taken (abandoned 2018 TDD tool); the plural is free and is what you ship |
| `waza` | 技, "technique" — the named thing a step teaches |
| `ubung` / `uebung` | German *Übung*, "exercise"; ASCII-safe transliteration |
| `exercitium` / `exercice` | Latin / French "exercise" |
| `tamrin` | Arabic تمرين, "exercise / drill" |
| `repper` / `repetita` | reps; *repetita iuvant* — "repeated things help" |
| `byheart` | the goal state, said the way a person says it |
| `rotely` | learning by rote, adverbialised |
| `noviciate` | the period of structured apprenticeship |
| `teachable` / `teachably` | the property the library confers on raw video |
| `followalong` / `stepalong` / `playalong` / `singalong` | the genre of artefact being produced |
| `watchlearn` / `dolearn` / `learndo` | watch → do, the whole pedagogy in a compound |
| `drilled` / `drills` / `drilly` / `drillery` / `drillcraft` / `drillbook` | drill family; bare `drill` is taken |
| `lehrgang` / `lehrbuch` | German "course of instruction" / "textbook" |
| `lecon` / `lecons` / `lezione` / `clase` / `clases` / `klasse` / `metodo` / `methode` | lesson/class/method in FR/IT/ES/DE |
| `syllabus` / `syllabary` | the ordered list of what will be taught |

### 3.3 Parsing / structure (the AST metaphor)

| name | one-line rationale |
|---|---|
| `astep` | **AST + step in five letters** — the architecture is in the name; reads "a-step" |
| `asteps` / `astepper` / `asteppy` | variants of the same pun if the bare form is wanted elsewhere |
| `kineme` | real term from kinesics: the smallest distinctive unit of body motion — the *phoneme of movement*, i.e. your AST's leaf node already has a name |
| `kinemes` / `kinesic` / `kinesics` | the field and the plural |
| `choreme` / `choremes` | the analogous coined unit for a unit of choreography |
| `praxeme` / `gesteme` / `moveme` / `movemes` / `stepeme` / `actme` | the same `-eme` morphology, invented, if you want the coinage to be yours |
| `morpheme` | the smallest meaning-bearing unit; the borrowed word, unclaimed on PyPI |
| `syntagma` / `syntagm` | linguistics: an ordered sequence of units that combine into a structure — the definition of your IR |
| `constituency` | the parse-tree relation itself (routine ⊃ block ⊃ count) |
| `partonomy` | a part-of hierarchy — the precise formal name for routine→block→step |
| `mereology` | the logic of parts and wholes; scholarly and unusual |
| `interpretant` | Peirce: what a sign *becomes* when interpreted — phase 2 named exactly |
| `signifier` | the annotation layer as sign, the media as referent |
| `articulation` / `articul` | doubly apt: joints moving, *and* the separation of continuous flow into discrete units |
| `declension` | the systematic inflected forms of one root — a step and its variations |
| `grammatic` | the grammar of the discipline, adjectivised |
| `tokenize` | the phase-1 verb, unclaimed as a package name |
| `lexon` | invented: a lexical atom |
| `corpuslet` | a small corpus — the per-routine bundle of source + annotations |
| `transduce` / `unfolder` | media in, structure out; the render as an unfold |
| `notatio` | Latin "a marking down" |
| `stepast` / `choreast` / `kinast` / `danceast` / `movast` | explicit `<domain>+AST` portmanteaus |
| `parsestep` / `parsemove` / `parselearn` / `steppar` / `movesyntax` | verb-first parser names |
| `movetree` / `movegraph` | the IR as a data structure, said plainly |
| `stepgram` / `stepogram` / `chorogram` / `choregram` / `kinogram` / `kinegram` / `scoregram` | `-gram` = "a thing written down"; the artifact side of the IR |
| `kinemat` / `kinemata` / `kinema` / `kinemas` | Greek κίνημα, "a movement"; the plural `kinemata` reads as a collection of motion units |

### 3.4 Guide / map / score

A musical **score** is the strongest metaphor available: a written notation of a timed performance
that a human executes. `score`, `scored`, `scorer`, `notation`, `notate`, `partitura`, `partition`,
`tablature`, `neume`, `solfege`, `leadsheet` are all **taken**. These are free:

| name | one-line rationale |
|---|---|
| `spartito` | Italian for a musical score — the metaphor, in a word nobody has claimed |
| `partita` | a suite of linked movements performed in order; contains "part" |
| `scorelet` / `scoreful` / `scorely` / `scorelike` / `scorecraft` / `scoreast` / `scorecast` | score-family derivatives |
| `notated` / `notatr` / `notatee` | "the notated thing"; the output artefact |
| `neumes` / `neumatic` | the earliest Western notation marks — one glyph per gesture |
| `solfa` / `solfeggio` | the syllabic system for *singing* a score — a spoken breakdown of a timed performance, which is exactly the POC's source material |
| `tabulature` | archaic spelling of tablature (which is taken); tab = notation of *what the body does*, not what sound results — the single closest musical analogue to your IR |
| `laban` | Labanotation: **the** canonical prior art for writing down human movement |
| `labanote` / `labanish` / `labanly` | derivatives if the bare surname feels presumptuous |
| `kinetography` | the European name for Labanotation; long but unambiguous |
| `benesh` | Benesh Movement Notation — the other major dance-notation system |
| `eshkol` | Eshkol-Wachman Movement Notation — the third, and the most formally algebraic |
| `choreology` | the *study and notation* of dance; the discipline your library automates |
| `choreograph` | the verb, free even though `choreo` is taken |
| `choreographia` | the Latinised noun, if a longer distinct name is fine |
| `vademecum` / `vade` | "go with me" — the handbook you carry into the studio |
| `guidebook` / `guidely` / `handbuch` / `manualis` / `primerly` | guide-family, plain |
| `baedeker` | the archetypal guidebook brand-turned-common-noun |
| `itinerarium` | a Roman route-list: ordered waypoints with distances — a routine, essentially |
| `songlines` | Aboriginal navigational songs that encode a route through country: a *timed performance that is also a map* — the deepest version of the score metaphor |
| `wayfind` / `keymap` | navigation framing |

### 3.5 Invented / portmanteau, in the house style

The fleet's register: `reelee`, `lacing`, `muvid`, `artful`, `falaw`, `braidio`, `walkthru`,
`burns`, `dol`, `i2`, `qh`, `acture`, `zodal` — mostly 4–7 letters, two syllables, either an
`-ee`/`-ly` diminutive, an `-ing` gerund, or a clipped compound.

| name | one-line rationale |
|---|---|
| `steplee` | direct rhyme with `reelee`; the fleet's own suffix applied to the core noun |
| `clavee` / `clavio` / `klavio` / `clavey` | *clave* run through the same suffixes |
| `katee` / `katalee` / `katio` | *kata* likewise, since the bare word is taken |
| `korio` / `kinio` / `kinlee` / `kinoo` | from Greek *kine-*, movement |
| `movio` / `movly` / `moovly` / `movelee` | from "move", `braidio`-style and `-ly`-style |
| `choro` | clipped *choreo* (which is taken); also a Brazilian musical genre, which is a bonus not a clash |
| `chordio` / `cuedio` / `movidio` | `braidio`-pattern compounds |
| `danceture` / `choreture` / `movture` / `stepture` / `learnture` / `cuture` | `acture`-pattern: verb + `-ture` |
| `gestur` | clipped "gesture" (the full word is taken) |
| `paslee` / `runlee` / `walklee` / `showlee` / `teachlee` | more `reelee`-rhymes on domain verbs |
| `drillee` / `tutee` / `tutelee` / `mentee` / `learnee` / `lernee` / `teachee` / `showee` / `guidee` | the `-ee` patient suffix: the *one being taught* |
| `tutela` / `tutelage` | Latin "guardianship/instruction"; softer than `tutorize` |
| `docenta` / `docente` / `maestra` | the teacher, in Spanish/Italian (`maestro`, `guru`, `sensei` all taken) |
| `demoform` / `demoscore` / `demotree` | "demonstration" + the IR |
| `runthru` / `runthrough` | **direct sibling of the existing `walkthru`** — the run-through is the artefact |
| `stepomat` / `stepomatic` | if you want it to sound like a machine that produces routines |

### 3.6 Dance / music / drill / kata / choreography vocabulary

| name | one-line rationale |
|---|---|
| `clave` | the two-bar key pattern every Afro-Cuban musician and dancer locks to — *and* Spanish for "key/code"; the timing spine and the decoding key in one word |
| `tumbao` | the repeating conga/bass pattern under a whole song — the loop the practice page runs |
| `montuno` | the vamp section where the named moves actually happen |
| `guaguanco` | a rumba style; a whole named form |
| `falseta` | flamenco: a self-contained melodic phrase inserted between verses — a *block* (note `compas`, the rhythmic cycle, is taken) |
| `remate` / `cierre` | flamenco: the closing flourish / the figure that ends a section |
| `escobilla` / `zapateado` | flamenco: the pure-footwork section; the footwork itself |
| `jaleo` | the shouted encouragement that cues the dancer — the spoken layer over the danced one |
| `duende` | the thing the recording has that the transcript loses; ambitious, evocative, free |
| `buleria` / `solea` | flamenco *palos* (forms) |
| `enchainement` / `enchaine` / `enchain` | ballet: the linked sequence of steps a teacher sets in class — **the exact object this library produces** |
| `battement` / `tendu` / `plie` / `releve` / `chasse` | named ballet steps; `chasse` in particular is a step that literally chases the previous one |
| `epaulement` | the carriage of the shoulders — the detail a video teaches and text cannot |
| `reverence` | the bow that closes a ballet class; the end of the run-through |
| `marking` | **the dance verb for walking a routine at reduced intensity to fix it in memory** — and simultaneously "marking up" the source media |
| `spotting` | the head technique that keeps a turner oriented; also "spotting" as picking out |
| `adavu` / `adavus` | Bharatanatyam's enumerated, named basic step-units — the domain's own word for the segmented leaves |
| `korvai` | a Carnatic/Bharatanatyam composition assembled from named rhythmic units into a whole that resolves — a routine as a *structured* sequence |
| `jathi` | a rhythmic syllable pattern |
| `sollukattu` | the *spoken* rhythmic syllables recited to teach an adavu — the POC's "spoken move-by-move breakdown", named |
| `theka` | the basic repeating pattern of a tala |
| `tihai` | a phrase repeated three times to land exactly on the downbeat — structured resolution |
| `laya` | tempo/pace; the transport's parameter |
| `nritta` / `abhinaya` | pure movement vs. expressive movement — two annotation layers |
| `toque` | capoeira/Latin: the rhythm that *calls* which game is played — a rhythm that selects a mode |
| `berimbau` | the instrument that dictates the toque |
| `esquiva` | capoeira evasion; a named move |
| `ostinato` | a short pattern repeated obstinately — the loop |
| `anacrusis` | the pickup before beat one; the "and-a-one" the whole POC hangs on |
| `cadenza` | the unmeasured solo passage inside a measured piece |
| `codetta` | a small closing passage |
| `ritornello` | the section that returns each time — the block you drill |
| `concertino` / `ripieno` / `sostenuto` / `tacet` | further score-marking vocabulary, all unclaimed |
| `backbeat` | the emphasis that makes people move |
| `callsheet` | production term: the ordered sheet of what happens when |
| `figuras` / `vuelta` / `vueltas` / `giros` / `salida` / `paseo` / `ocho` / `ochos` / `pasada` | named Latin/tango figures — `salida` ("the exit/opening") and `ocho` ("figure-eight") are the most name-like |

---

## 4. Shortlist of 10 — with the argument, not just the vibe

Re-verified individually on 2026-08-28 (PyPI, npm, and the `github.com/<name>` user handle).

| # | name | PyPI | npm | gh handle | the argument |
|---|---|---|---|---|---|
| 1 | **`astep`** | 404 | 404 | taken | **AST + step in five letters.** The brief says the central design idea is that this is *parsing*: phase 1 emits an AST, phase 2 renders it, the AST is the contract. A name that carries both halves of that teaches the architecture every time someone types it. `astep.parse(video, notes, prompt) -> Routine` and `astep.render(routine, "practice-page")` read as English. Zero collision with an existing English word, so it greps clean. Risk: dry, and a reader may see "asleep" or "a step" before they see "AST". |
| 2 | **`marking`** | 404 | **taken** | taken | The only candidate that names *both phases with one word*: in dance, **marking** is walking a routine through at reduced intensity to learn and remember it (phase 2, the practice page); in text processing, **marking up** is annotating a source (phase 1, the AST). The `-ing` gerund is the exact shape of `lacing`. Risk: a very common English word — bad SEO, and `import marking` is ambiguous in a file that also does markup; npm is taken, which matters if a JS companion ships. |
| 3 | **`clave`** | 404 | 404 | taken | The clave is the two-bar rhythmic key that every part of an Afro-Cuban arrangement locks to — the metronome-transport of the POC is literally clave-relative — **and** `clave` is Spanish for "key" and "code". A library that decodes performance into structure, named after the pattern that makes the performance decodable. Five letters, two syllables, exactly the fleet's register. Risk: it ties the library's identity to Latin music at the moment you are generalising away from dance. |
| 4 | **`kineme`** | 404 | 404 | taken | In kinesics, a **kineme** is the smallest distinctive unit of body motion — the phoneme of movement. If your IR is an AST, its leaf node already has a real, cited academic name, and the name of the package should be the name of its atom (cf. `dol`'s atom being the mapping). Gives you honest vocabulary for free: kineme → phrase → block → routine. Risk: obscure; you will explain it every time. |
| 5 | **`spartito`** | 404 | 404 | taken | Italian for a musical **score** — a written notation of a timed performance that a human executes, which is the best one-line description of your IR that exists. `score`, `partitura`, `partition`, `notation` are all taken; `spartito` is the same idea with an unclaimed word and a good mouthfeel. Risk: eight letters, non-obvious to non-Italian speakers, and "spar" reads martial. |
| 6 | **`enchaine`** | 404 | 404 | — | An *enchaînement* is ballet's word for the linked sequence of steps a teacher sets and the class then performs — precisely the object this library extracts and re-serves. Stripped to `enchaine` it is also the French verb "chains together", so it doubles as the render-phase action: `enchaine.render(...)` = "chain these steps up". Risk: accent-loss makes it look misspelled to francophones. |
| 7 | **`korvai`** | 404 | 404 | taken | A korvai is a Carnatic/Bharatanatyam composition **assembled from named rhythmic units into a structured whole that resolves on the downbeat** — a compositional grammar, taught by naming its parts, which is your entire phase-1 output. Short, unusual, no English collision, and it comes from a tradition that already thinks of routines as parseable. Risk: unknown outside South Indian music; nothing about the name suggests software. |
| 8 | **`adavu`** | 404 | 404 | taken | The adavus are Bharatanatyam's **enumerated, individually named basic step-units** — a tradition that already did the work of segmenting continuous dance into a closed vocabulary of named steps and then teaching them by spoken syllables. Five letters, vowel-heavy, easy to say. Risk: same cultural-specificity objection as `clave` and `korvai`, pointed at a different tradition. |
| 9 | **`laban`** | 404 | 404 | taken | Labanotation is **the** prior art for writing human movement down as a structured, timed, machine-readable score. Naming the library `laban` says "this is Labanotation for the age of video models" to anyone in dance, and says nothing embarrassing to anyone else. Five letters, hard consonants. Risk: it is a real person's surname (Rudolf Laban), which carries both a small trademark question and a biography question you may not want attached. |
| 10 | **`woodshed`** | 404 | 404 | taken | Jazz slang: to *woodshed* is to go off alone and drill the hard passage until it is yours. The library is the woodshed — it takes the performance and hands you the place to grind it. Warm, English, memorable, two syllables, and it names the **user's experience** rather than the implementation, which none of the other nine do. Risk: says nothing about parsing, steps, or structure; and "shed" invites bad jokes about where code goes to die. |

Honourable mentions that just missed: `runthru` (the cleanest sibling to the existing `walkthru`,
but confusable with it), `syntagma` (perfect semantics, heavy mouth), `partita`, `sollukattu`,
`ostinato`, `vademecum`, `songlines`, `steplee`.

---

## 5. My single favourite: `astep` — SUPERSEDED, see §0

> **Superseded.** The user has since ruled this out explicitly: the AST idea belongs in the
> architecture, not the name. Kept for its argument, which is still a good argument for the
> *architecture*. The live recommendation is §0.


The user has already declared what the library *is*: "this is like PARSING. Phase 1 … produces an
AST. Phase 2 renders that AST. The AST is the contract; many renderers can consume it." A name
should encode the thing the architecture must not drift away from, and `astep` encodes exactly
that — **AST** and **step**, superimposed, in five characters, with no leftovers.

Concretely, in its favour:

- **It keeps the contract visible.** Every future contributor who types `import astep` is reminded
  that the middle of this system is a tree, not a pile of files. That is the failure mode this
  library is most likely to have (renderers reaching back into the video instead of consuming the
  IR), and the name argues against it for free.
- **The API sentences are already good.** `astep.parse(video, notes=…, prompt=…) -> Routine`;
  `astep.render(routine, to="practice-page")`; `astep.grammars["salsa"]`. Nothing is strained.
- **It generalises.** `clave`, `adavu`, `korvai` and `laban` all say "dance" — three of them say
  "*this* dance tradition". The brief says the general case is any step-by-step instructional
  content: knife skills, a guitar solo, a yoga sequence, a machine calibration. `astep` survives
  every one of those; `clave` does not survive knife skills.
- **It fits the fleet.** Five letters, two syllables, invented-looking, ASCII, unambiguous to type
  — the same shape as `acture`, `zodal`, `muvid`, `falaw`. And it is free on PyPI **and** npm,
  which matters because a frontend is on the roadmap.
- **It greps clean.** No English word collides, unlike `marking`, `score`, `drill`.

The honest case against, so you can weigh it: `astep` is *architectural*, not *evocative*. It
tells an engineer what the middle looks like; it tells a dancer nothing. If the user wants the name
to feel the way `reelee` and `lacing` feel — playful, human, domain-flavoured — then take
**`marking`** instead, which is the single best domain word available (both phases in one word),
and accept the common-noun tax. If the user wants warmth and doesn't need the name to argue for
the architecture, **`woodshed`**.

---

## 6. What to call the axis the brief calls "SUBJECT"

The axis: *the kind of thing being taught* — a salsa routine, knife skills, a guitar solo, a yoga
sequence, a surgical procedure. It is the thing that determines what counts as a step, what steps
are called, how they nest, which segmentation heuristics fire, which prompt pack loads, and which
renderer defaults apply. Reelee's analogous axis is called `genre`.

| candidate | one line |
|---|---|
| **`discipline`** | dance, cooking, surgery, guitar are all *disciplines*; the word already implies repeated practice, which is precisely the pedagogy this library serves — and it is the word a human would use unprompted |
| **`craft`** | a body of learned practical skill; warm, four letters, sits well next to the fleet's `artful`; slightly twee, and blurs with "handicraft" |
| **`grammar`** | the parsing-native answer: what you plug in is literally the thing that tells the parser what a step *is* in this domain and how steps combine — keeps the AST metaphor coherent end to end |
| **`idiom`** | musically exact: salsa and ballet are idioms *of* dance, bebop is an idiom *of* jazz; correctly sits one level below `discipline`, but laypeople won't parse it |
| **`domain`** | engineering-standard and instantly understood; bland, and already means five other things (DDD, DNS, math) |
| **`genre`** | consistent with reelee, which is a real argument for fleet coherence; but `genre` classifies *media*, not *skill*, and a job may legitimately need both at once — see the warning below |
| **`modality`** | "the mode of the taught activity"; clinical, and it will collide head-on with ML's *modality* (video/audio/text), which this codebase absolutely will use |
| **`form`** | the kata sense — "teaching a form"; collides with HTML forms and with `form` as data-shape |
| **`art`** | "the art being taught" (martial art, culinary art); evocative and echoes `artful`, but reads as fine art |
| **`skill`** | the plainest, most literally true word — **and the one to avoid**, because in this user's ecosystem "skill" already means an Anthropic `SKILL.md`, a live daily collision |
| *(runner-up)* `repertoire` | the *collection* of routines someone knows — a genuinely useful concept, but it names the corpus, not the kind |
| *(runner-up)* `metier` | trade/craft; the accent and the obscurity kill it |

**Recommendation — use two words at two layers, because they are two things:**

1. **`discipline`** for the user-facing axis noun. `parse(video, discipline="salsa")` reads
   correctly to a non-programmer, covers dance and surgery and knife skills without strain, and
   carries the practice connotation the library is built on. If the user prefers warmth over
   precision, `craft` is the runner-up and loses nothing structural.
2. **`grammar`** for the *pluggable artifact* that encodes a discipline — the step vocabulary,
   segmentation heuristics, prompt pack and renderer defaults. `astep.grammars["salsa"]`,
   `Grammar.load(...)`. This is not decoration: if phase 1 is parsing, the per-discipline knowledge
   pack *is* a grammar, and calling it that makes the whole system explainable in one sentence —
   *a grammar tells the parser what counts as a step in this discipline; the parse yields an AST;
   renderers consume the AST.*

**Explicitly do not reuse `genre` here.** Reelee's `genre` selects a *media/output style*. This axis
selects a *skill domain*. A single job will plausibly want both at once (`discipline="salsa"`,
reelee `genre="cartoon-loop"` for the per-block clips — which is exactly what the POC did). Giving
them the same word guarantees a confusing argument-name collision at the fleet boundary within a
month.

---

## 7. Open questions for the next agent

1. **`bunkai` is taken and it was the best semantic fit in the whole sweep.** In karate, *bunkai*
   means the analytical breakdown of a kata into its component applications — i.e. exactly phase 1.
   PyPI's `bunkai` is, ironically, a Japanese **sentence boundary disambiguation** tool (v1.5.7,
   last release 2023-02-09) — a real, plausibly-still-used package. I did not investigate whether
   it is abandoned. Probably unreclaimable; noted because if it ever frees up it beats several
   shortlist entries.
2. **Other high-value taken names I did not check for liveness/squat status**: `kata` (v1.1.0, last
   release **2018-12-01**, a TDD scaffold — looks abandoned), `ledger` (v1.0.1, 2022, summary
   literally "Geektrust ledger problem" — squat-grade), `llamada` (v0.0.1, 2023). PEP 541 name
   transfer is theoretically available for abandoned projects; I judged it not worth the latency
   for a v1, but flagging it since `kata` is a genuinely great name.
3. **GitHub handles**: `github.com/<name>` is a taken user/org for every shortlist name (normal for
   short words). The repo would be `thorwhalen/<name>` — I verified `thorwhalen/astep` returns 404
   (free) but did not check the other nine.
4. **npm**: only `marking` and `partita` are taken on npm among the names I checked. This matters
   only if a JS companion package is planned — the roadmap says a frontend is, so confirm whether
   it will be published to npm under the same name before committing to `marking`.
5. **Trademark / person-name risk unchecked** on `laban` (Rudolf Laban), `benesh` (Benesh), `eshkol`
   (Eshkol-Wachman), `baedeker`. Low practical risk for a small OSS library, but not zero.
6. **The cultural-specificity question is a decision, not a fact.** `clave`, `adavu`, `korvai`,
   `falseta` are all excellent *and* all carry a specific tradition. Is a "born in salsa" origin
   story a feature (memorable, honest about the POC) or a liability (misleads about the general
   case)? Only the user can call it.
7. **`step-wise` vs `stepwise`.** `step-wise` is genuinely claimable and would install as
   `pip install step-wise`. I ruled it out on human-confusability grounds, not availability. If the
   user actually likes `stepwise`, this is the loophole and it is legitimate.
8. **Re-verify before claiming.** All results are from 2026-08-28. Re-run the one-liner in §1 on
   the final two or three candidates immediately before registering.
9. **Full raw data** (466 free names, 218 taken, all 684 checked) was produced by the batch files in
   the session scratchpad and is not committed anywhere; the §3 tables carry every free name worth
   proposing, but if you want the long tail, re-running §1's loop over a candidate list is cheap.
