import glob,time,numpy as np,torch,cv2
from PIL import Image
from transformers import AutoModel, AutoProcessor
SP='/private/tmp/claude-501/-Users-thorwhalen-Downloads/0f75703c-6761-4aa0-b796-aafe02c94155/scratchpad'
MED='/Users/thorwhalen/Dropbox/py/proj/tt/tw_platform/apps/que_calor_dance/frontend/media'
exec(open(f'{SP}/eval_vlm.py').read().split("FRAMES = sorted")[0])
mid='google/siglip2-so400m-patch14-384'
proc=AutoProcessor.from_pretrained(mid, use_fast=True); model=AutoModel.from_pretrained(mid,dtype=torch.float16).to('mps').eval()
FR_=sorted(glob.glob(f'{SP}/frames/*.jpg')); T=np.arange(len(FR_))+0.5
imgs=[Image.open(p).convert('RGB') for p in FR_]
def enc_img(ims,bs=16):
    o=[]
    with torch.no_grad():
        for k in range(0,len(ims),bs):
            i=proc(images=ims[k:k+bs],return_tensors='pt').to('mps')
            o.append(model.get_image_features(**i).float().cpu())
    f=torch.cat(o); return f/f.norm(dim=-1,keepdim=True)
def enc_txt(ts):
    with torch.no_grad():
        i=proc(text=ts,return_tensors='pt',padding='max_length',max_length=64,truncation=True).to('mps')
        f=model.get_text_features(**i).float().cpu()
    return f/f.norm(dim=-1,keepdim=True)
def block_of(t):
    for i,(a,b) in enumerate(GT):
        if a<=t<b: return i
    return 8
t0=time.time(); F=enc_img(imgs); torch.mps.synchronize(); dt=time.time()-t0
print(f"so400m-384: {len(imgs)} frames in {dt:.1f}s = {len(imgs)/dt:.1f} fps, dim={F.shape[1]}")
for tag,txt in (('FR',FR),('EN',EN)):
    S=(enc_txt(txt)@F.T).numpy()
    h=[block_of(T[int(S[i].argmax())])==i for i in range(9)]
    print(f"  full-frame argmax {tag}: {sum(h)}/9  peaks={[round(float(T[int(S[i].argmax())]),0) for i in range(9)]}")
# cropped-clip retrieval
def frames_of(c,every=5):
    cap=cv2.VideoCapture(f'{MED}/{c}.mp4');o=[];k=0
    while True:
        ok,fr=cap.read()
        if not ok:break
        if k%every==0:o.append(Image.fromarray(cv2.cvtColor(fr,cv2.COLOR_BGR2RGB)))
        k+=1
    cap.release();return o
CLIPS=[('b2',1),('b3',2),('b4a',3),('b4b',3),('b7',6),('b9',8)]
for tag,txt in (('FR',FR),('EN',EN)):
    Tt=enc_txt(txt); t1=0;t3=0;rows=[]
    for c,gt in CLIPS:
        s=(Tt@enc_img(frames_of(c)).T).mean(1).numpy(); o=list(np.argsort(-s)); r=o.index(gt)
        t1+= r==0; t3+= r<3; rows.append(f"{c}:r{r+1}")
        m=s[o[0]]-s[o[1]]
    print(f"  cropped-clip {tag}: top1 {t1}/6 top3 {t3}/6  ({' '.join(rows)})")
