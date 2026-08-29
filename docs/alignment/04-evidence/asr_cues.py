"""ASR the synthetic French instruction speech, then extract ordinal/imperative cues
with a pure-regex detector (no spaCy, no LLM)."""
import time, re, json
import mlx_whisper
t0=time.time()
r=mlx_whisper.transcribe('speech.wav', path_or_hf_repo='mlx-community/whisper-large-v3-turbo',
                         language='fr', word_timestamps=True, verbose=False)
dt=time.time()-t0
dur=36.24
print(f"ASR: {dt:.1f}s for {dur:.0f}s audio ({dur/dt:.1f}x realtime, mlx large-v3-turbo)")
segs=[(s['start'],s['end'],s['text'].strip()) for s in r['segments']]
for s in segs: print(f"  [{s[0]:6.1f}-{s[1]:6.1f}] {s[2]}")

# ---- cheap classical cue detector -------------------------------------------
ORDINAL = r"(?:et\s+là|et\s+puis|ensuite|après\s+ça|après\s+quoi|puis|maintenant|d'abord|" \
          r"pour\s+commencer|enfin|pour\s+finir|on\s+enchaîne|on\s+passe\s+à|" \
          r"la\s+prochaine|voilà|d'accord|alors)"
# French 2pl imperative / instructional present: 'vous X-ez', or bare '-ez' at clause start
IMPER   = r"\b(?:vous\s+)?(\w{3,}(?:ez|issez))\b"
CLOSERS = r"(?:voilà|d'accord|ok|c'est\s+tout|ça\s+y\s+est)"
words=[w for s in r['segments'] for w in s.get('words',[])]
def wtime(cidx, text):
    # map a character index in the joined text back to a word time
    acc=0
    for w in words:
        tok=w['word']
        if acc+len(tok) >= cidx: return w['start']
        acc+=len(tok)
    return None
full="".join(w['word'] for w in words)
print("\ncue hits (regex only):")
for name,pat in (('ORDINAL',ORDINAL),('IMPERATIVE',IMPER),('CLOSER',CLOSERS)):
    for m in re.finditer(pat, full, re.I):
        t=wtime(m.start(), full)
        print(f"  {name:11s} t={t if t is None else round(t,1):>6}  '{m.group(0).strip()}'")
