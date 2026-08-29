"""CLAP (audio-language) vs the POC's five-line sub-bass ratio, on a
music / speech / silence / music test signal with known boundaries."""

import time, numpy as np, soundfile as sf, torch
from transformers import ClapModel, ClapProcessor

SP = "/private/tmp/claude-501/-Users-thorwhalen-Downloads/0f75703c-6761-4aa0-b796-aafe02c94155/scratchpad"
GT = [
    (0, 40, "music"),
    (40, 76.2, "speech"),
    (76.2, 82.2, "silence"),
    (82.2, 122.2, "music"),
]


def label(t):
    for a, b, l in GT:
        if a <= t < b:
            return l
    return "music"


x, sr = sf.read(f"{SP}/mix.wav")
x = x.astype(np.float32)
print(f"{len(x) / sr:.1f}s @ {sr}Hz")

# ---------- baseline: the POC's sub-bass energy ratio, 1 s frames ----------
t0 = time.time()
n = sr
base = []
for i in range(len(x) // n):
    w = x[i * n : (i + 1) * n]
    X = np.abs(np.fft.rfft(w * np.hanning(len(w)))) + 1e-10
    f = np.fft.rfftfreq(len(w), 1 / sr)
    base.append(
        (
            float(np.sqrt((w**2).mean())),
            float(X[(f >= 30) & (f <= 140)].sum() / X.sum()),
        )
    )
base = np.array(base)
dt_base = time.time() - t0
rms, bass = base[:, 0], base[:, 1]
pred = np.where(rms < 0.005, "silence", np.where(bass > 0.10, "music", "speech"))
truth = np.array([label(i + 0.5) for i in range(len(pred))])
acc = (pred == truth).mean()
print(
    f"\nsub-bass ratio : {dt_base:.3f}s for {len(x) / sr:.0f}s audio "
    f"({(len(x) / sr) / dt_base:.0f}x realtime, pure numpy) frame-accuracy={acc:.3f}"
)
for l in ("music", "speech", "silence"):
    m = truth == l
    print(
        f"   {l:8s} n={m.sum():3d} recall={(pred[m] == l).mean():.2f} "
        f"| rms {rms[m].mean():.4f}  bass {bass[m].mean():.3f}"
    )

# ---------- CLAP ----------
for mid in ["laion/clap-htsat-unfused", "laion/larger_clap_general"]:
    proc = ClapProcessor.from_pretrained(mid)
    model = ClapModel.from_pretrained(mid).eval()
    QS = ["music playing", "a person speaking", "silence"]
    with torch.no_grad():
        ti = proc(text=QS, return_tensors="pt", padding=True)
        Tt = model.get_text_features(**ti)
        Tt = Tt / Tt.norm(dim=-1, keepdim=True)
    # 5 s windows, 1 s hop, resampled to 48k (CLAP wants 48 kHz)
    W, H = 5, 1
    starts = np.arange(0, len(x) / sr - W, H)
    t0 = time.time()
    feats = []
    for k in range(0, len(starts), 16):
        chunk = [x[int(s * sr) : int((s + W) * sr)] for s in starts[k : k + 16]]
        ai = proc(audios=chunk, sampling_rate=sr, return_tensors="pt", padding=True)
        with torch.no_grad():
            f = model.get_audio_features(**ai)
        feats.append(f)
    F = torch.cat(feats)
    F = F / F.norm(dim=-1, keepdim=True)
    dt = time.time() - t0
    S = (Tt @ F.T).numpy()
    pr = np.array([QS[i].split()[0] for i in S.argmax(0)])
    pr = np.array(
        ["music" if p == "music" else ("speech" if p == "a" else "silence") for p in pr]
    )
    tr = np.array([label(s + W / 2) for s in starts])
    print(
        f"\n{mid}: {len(starts)} windows in {dt:.1f}s "
        f"({(len(x) / sr) / dt:.1f}x realtime, CPU) frame-accuracy={(pr == tr).mean():.3f}"
    )
    for l in ("music", "speech", "silence"):
        m = tr == l
        if m.sum():
            print(
                f"   {l:8s} n={m.sum():3d} recall={(pr[m] == l).mean():.2f} "
                f"mean-cos music/speech/silence = {S[:, m].mean(1).round(3)}"
            )
