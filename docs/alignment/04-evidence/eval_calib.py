"""Is a CLIP/SigLIP peak evidence? Compare true queries against decoy queries
that describe things that are definitely NOT in the video."""
import glob, numpy as np, torch
from PIL import Image
from transformers import AutoModel, AutoProcessor
SP='/private/tmp/claude-501/-Users-thorwhalen-Downloads/0f75703c-6761-4aa0-b796-aafe02c94155/scratchpad'
exec(open(f'{SP}/eval_vlm.py').read().split("FRAMES = sorted")[0])
DECOY=["une personne qui fait frire des oignons dans une poêle",
       "un chien qui court sur une plage",
       "une voiture rouge garée devant une maison",
       "deux personnes qui jouent aux échecs",
       "un graphique en barres sur un écran d'ordinateur",
       "une personne qui joue de la guitare assise",
       "un plat de pâtes sur une table en bois",
       "un avion qui décolle au coucher du soleil",
       "une personne qui nage dans une piscine",
       "un chat endormi sur un canapé",
       "une foule dans un stade de football",
       "une personne qui écrit sur un tableau blanc"]
imgs=[Image.open(p).convert('RGB') for p in sorted(glob.glob(f'{SP}/frames/*.jpg'))]
mid='google/siglip2-base-patch16-224'
proc=AutoProcessor.from_pretrained(mid); model=AutoModel.from_pretrained(mid,dtype=torch.float32).to('mps').eval()
with torch.no_grad():
    F=[]
    for k in range(0,len(imgs),32):
        i=proc(images=imgs[k:k+32],return_tensors='pt').to('mps')
        F.append(model.get_image_features(**i).float().cpu())
    F=torch.cat(F); F=F/F.norm(dim=-1,keepdim=True)
    def enc(ts):
        i=proc(text=ts,return_tensors='pt',padding='max_length',max_length=64,truncation=True).to('mps')
        f=model.get_text_features(**i).float().cpu(); return f/f.norm(dim=-1,keepdim=True)
    St=(enc(FR)@F.T).numpy(); Sd=(enc(DECOY)@F.T).numpy()
def stats(S,name):
    peak=S.max(1); mean=S.mean(1); std=S.std(1); z=(peak-mean)/std
    print(f"{name:8s} n={len(S):2d}  peak-cos {peak.min():.3f}..{peak.max():.3f} (mu {peak.mean():.3f})"
          f"  peak-z {z.min():.2f}..{z.max():.2f} (mu {z.mean():.2f})")
    return peak,z
pt,zt=stats(St,'TRUE'); pd_,zd=stats(Sd,'DECOY')
print(f"\n  separation on raw peak cosine : AUC = {np.mean([ (a>b)+0.5*(a==b) for a in pt for b in pd_]):.2f}")
print(f"  separation on peak z-score    : AUC = {np.mean([ (a>b)+0.5*(a==b) for a in zt for b in zd]):.2f}")
# margin against the decoy pool -- the usable statistic
allS=np.vstack([St,Sd])
P=allS - allS.mean(0,keepdims=True)
print(f"  after subtracting the decoy-pool mean per frame:")
pt2=P[:9].max(1); pd2=P[9:].max(1)
print(f"    TRUE peak {pt2.min():.3f}..{pt2.max():.3f} | DECOY peak {pd2.min():.3f}..{pd2.max():.3f}"
      f" | AUC={np.mean([(a>b)+0.5*(a==b) for a in pt2 for b in pd2]):.2f}")
