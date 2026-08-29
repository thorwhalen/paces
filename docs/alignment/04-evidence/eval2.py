"""Does normalisation / person-cropping rescue frame-wise VLM matching?"""
import glob, time, numpy as np, torch
from PIL import Image
from transformers import AutoModel, AutoProcessor
exec(open('/private/tmp/claude-501/-Users-thorwhalen-Downloads/0f75703c-6761-4aa0-b796-aafe02c94155/scratchpad/eval_vlm.py').read().split("FRAMES = sorted")[0])
SP='/private/tmp/claude-501/-Users-thorwhalen-Downloads/0f75703c-6761-4aa0-b796-aafe02c94155/scratchpad'
FRAMES=sorted(glob.glob(f'{SP}/frames/*.jpg')); T=np.arange(len(FRAMES))+0.5
def block_of(t):
    for i,(a,b) in enumerate(GT):
        if a<=t<b: return i
    return 8
def hits(S, name):
    h=[block_of(T[int(S[i].argmax())])==i for i in range(9)]
    print(f"    {name:34s} {sum(h)}/9   peaks={[round(float(T[int(S[i].argmax())]),0) for i in range(9)]}")
    return sum(h)

def smooth(S,k):
    if k<=1: return S
    ker=np.ones(k)/k
    return np.stack([np.convolve(S[i],ker,mode='same') for i in range(S.shape[0])])

for tag in ('FR','EN'):
    S=np.load(f'{SP}/S_siglip2-base-patch16-224_{tag}.npy')
    print(f"\nSigLIP2-base, {tag} queries, full 854x480 frame:")
    hits(S,'raw cosine')
    Zq=(S-S.mean(1,keepdims=True))/S.std(1,keepdims=True)          # per-query z  (row)
    hits(Zq,'row z-score (per query)')
    Zf=S-S.mean(0,keepdims=True)                                    # per-frame centering (column)
    hits(Zf,'column-centred (per frame)')
    Zb=(Zf-Zf.mean(1,keepdims=True))/Zf.std(1,keepdims=True)
    hits(Zb,'double-normalised')
    hits(smooth(Zb,5),'double-norm + 5 s box smooth')
    hits(smooth(Zb,11),'double-norm + 11 s box smooth')
    P=np.exp(S*100); P=P/P.sum(0,keepdims=True)                     # softmax over queries per frame
    hits(P,'softmax over queries (tau=0.01)')
