"""Score 9 French dance-block descriptions against 166 frames of the run-through.
Ground truth: filage.mp4 = source[50.9:216.9]; routine = 44 eights at 3.715 s/eight.
Verified by multi-scale template matching of the 6 run-through block clips."""

import glob, json, time, sys
import numpy as np, torch
from PIL import Image
from transformers import AutoModel, AutoProcessor, AutoTokenizer

SP = "/private/tmp/claude-501/-Users-thorwhalen-Downloads/0f75703c-6761-4aa0-b796-aafe02c94155/scratchpad"
EIGHT = 8 * 60 / 129.2
CUM = np.cumsum([0, 2, 6, 4, 8, 4, 4, 4, 4, 8])  # block starts in eights
GT = [(CUM[i] * EIGHT, CUM[i + 1] * EIGHT) for i in range(9)]

FR = [
    "une personne debout immobile qui se met en place",
    "une personne qui marche en pointant le pied, les bras ouverts sur les côtés",
    "une personne qui balaie l'espace avec les deux bras tendus en grand cercle, comme un soleil",
    "une personne qui bouge les hanches, jambes écartées, en tournant la tête",
    "une personne qui fait tourner son avant-bras comme un moulinet à partir du coude",
    "une personne accroupie en grand plié, les genoux qui rentrent vers l'intérieur",
    "une personne sur place qui lève un bras près de la tête puis l'autre",
    "une personne qui tape dans les mains d'un voisin, bras tendu vers le haut",
    "une personne qui court en avant et lance les deux bras en l'air",
]
EN = [
    "a person standing still getting into position",
    "a person walking and pointing the foot, arms open to the sides",
    "a person sweeping both straight arms through a big circle like a sun",
    "a person moving their hips with legs apart, turning their head",
    "a person rotating a forearm like a windmill from the elbow",
    "a person in a deep squat with knees dropping inward",
    "a person raising one arm near the head then the other, stepping in place",
    "a person clapping hands with a partner, arm stretched up",
    "a person running forward and throwing both arms up in the air",
]

FRAMES = sorted(glob.glob(f"{SP}/frames/*.jpg"))
T = np.arange(len(FRAMES)) + 0.5
imgs = [Image.open(p).convert("RGB") for p in FRAMES]


def block_of(t):
    for i, (a, b) in enumerate(GT):
        if a <= t < b:
            return i
    return 8


def run(model_id, texts, tag, device="mps"):
    proc = AutoProcessor.from_pretrained(model_id)
    model = AutoModel.from_pretrained(model_id, dtype=torch.float32).to(device).eval()
    t0 = time.time()
    with torch.no_grad():
        F = []
        for k in range(0, len(imgs), 32):
            i = proc(images=imgs[k : k + 32], return_tensors="pt").to(device)
            F.append(model.get_image_features(**i).float().cpu())
        F = torch.cat(F)
        F = F / F.norm(dim=-1, keepdim=True)
        kw = (
            dict(padding="max_length", max_length=64)
            if "siglip" in model_id
            else dict(padding=True)
        )
        ti = proc(text=texts, return_tensors="pt", truncation=True, **kw).to(device)
        Tt = model.get_text_features(**ti).float().cpu()
        Tt = Tt / Tt.norm(dim=-1, keepdim=True)
    S = (Tt @ F.T).numpy()  # (9 blocks, 166 frames)
    dt = time.time() - t0
    # -- argmax per block, independently
    hits = 0
    rows = []
    for i in range(9):
        j = int(S[i].argmax())
        t = T[j]
        b = block_of(t)
        ok = b == i
        hits += ok
        rows.append(
            f"  blk{i + 1}: peak@{t:6.1f}s -> block{b + 1} {'HIT ' if ok else 'miss'} "
            f"(gt {GT[i][0]:.0f}-{GT[i][1]:.0f}s) s={S[i, j]:.3f} z={(S[i, j] - S[i].mean()) / S[i].std():.2f}"
        )
    # -- monotone DP: assign each frame to a block, blocks in order, contiguous
    n, m = 9, len(T)
    Z = (S - S.mean(1, keepdims=True)) / S.std(1, keepdims=True)  # per-query z-score
    D = np.full((n, m), -1e9)
    P = np.zeros((n, m), int)
    D[0, 0] = Z[0, 0]
    for j in range(1, m):
        D[0, j] = D[0, j - 1] + Z[0, j]
        P[0, j] = 0
    for i in range(1, n):
        for j in range(i, m):
            stay = D[i, j - 1] if D[i, j - 1] > -1e8 else -1e9
            new = D[i - 1, j - 1]
            if new >= stay:
                D[i, j] = new + Z[i, j]
                P[i, j] = 1
            else:
                D[i, j] = stay + Z[i, j]
                P[i, j] = 0
    # backtrace
    bounds = [m]
    i, j = n - 1, m - 1
    while i > 0:
        while j > 0 and P[i, j] == 0:
            j -= 1
        bounds.append(j)
        i -= 1
        j -= 1
    bounds = [0] + sorted(bounds)
    dp_err = []
    for i in range(9):
        pred = bounds[i] + 0.5
        dp_err.append(abs(pred - GT[i][0]))
    print(f"\n== {tag} :: {model_id.split('/')[-1]}  ({dt:.1f}s)")
    print(f"  independent argmax: {hits}/9 in the right block")
    print("\n".join(rows))
    print(f"  monotone-DP boundaries: {[round(b, 1) for b in bounds[:-1]]}")
    print(f"  ground-truth starts   : {[round(g[0], 1) for g in GT]}")
    print(
        f"  DP boundary abs err (s): median={np.median(dp_err):.1f} mean={np.mean(dp_err):.1f} max={max(dp_err):.1f}"
    )
    return S


if __name__ == "__main__":
    for mid in ["google/siglip2-base-patch16-224", "openai/clip-vit-base-patch32"]:
        for tag, txt in (("FR", FR), ("EN", EN)):
            S = run(mid, txt, tag)
            np.save(f"{SP}/S_{mid.split('/')[-1]}_{tag}.npy", S)
