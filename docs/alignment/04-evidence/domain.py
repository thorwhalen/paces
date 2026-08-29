import glob, numpy as np, torch
from PIL import Image
from transformers import AutoModel, AutoProcessor
SP='/private/tmp/claude-501/-Users-thorwhalen-Downloads/0f75703c-6761-4aa0-b796-aafe02c94155/scratchpad'
imgs=[Image.open(p).convert('RGB') for p in sorted(glob.glob(f'{SP}/frames/*.jpg'))]
mid='google/siglip2-base-patch16-224'
proc=AutoProcessor.from_pretrained(mid); model=AutoModel.from_pretrained(mid,dtype=torch.float32).to('mps').eval()
with torch.no_grad():
    F=[]
    for k in range(0,len(imgs),32):
        i=proc(images=imgs[k:k+32],return_tensors='pt').to('mps')
        F.append(model.get_image_features(**i).float().cpu())
    F=torch.cat(F); F=F/F.norm(dim=-1,keepdim=True)
    Q=["a cartoon illustration of a person","a photograph of a person",
       "a person dancing","a person standing still talking to the camera",
       "a wide shot of a person in a room","a close-up of a person's face",
       "a slide with text on it"]
    i=proc(text=Q,return_tensors='pt',padding='max_length',max_length=64,truncation=True).to('mps')
    T=model.get_text_features(**i).float().cpu(); T=T/T.norm(dim=-1,keepdim=True)
S=(T@F.T).numpy()
for q,row in zip(Q,S): print(f"  {row.mean():+.4f} mean  {row.max():+.4f} max   {q}")
print(f"\n  cartoon minus photograph, mean over 166 frames: {S[0].mean()-S[1].mean():+.4f}"
      f"  (cartoon wins on {(S[0]>S[1]).mean()*100:.0f}% of frames)")
print(f"  'dancing' minus 'standing still talking': {S[2].mean()-S[3].mean():+.4f}"
      f"  (dancing wins on {(S[2]>S[3]).mean()*100:.0f}% of frames)")
