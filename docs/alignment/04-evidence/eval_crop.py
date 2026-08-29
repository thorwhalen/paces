"""Does cropping to the subject rescue VLM move matching?
6 run-through block clips (already person-cropped, 560x700) x 9 French/English move texts."""

import numpy as np, torch, cv2
from PIL import Image
from transformers import AutoModel, AutoProcessor

SP = "/private/tmp/claude-501/-Users-thorwhalen-Downloads/0f75703c-6761-4aa0-b796-aafe02c94155/scratchpad"
MED = "/Users/thorwhalen/Dropbox/py/proj/tt/tw_platform/apps/que_calor_dance/frontend/media"
exec(open(f"{SP}/eval_vlm.py").read().split("FRAMES = sorted")[0])
CLIPS = [
    ("b2", 1),
    ("b3", 2),
    ("b4a", 3),
    ("b4b", 3),
    ("b7", 6),
    ("b9", 8),
]  # 0-based block index


def frames_of(c, every=5):
    cap = cv2.VideoCapture(f"{MED}/{c}.mp4")
    out = []
    k = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if k % every == 0:
            out.append(Image.fromarray(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)))
        k += 1
    cap.release()
    return out


mid = "google/siglip2-base-patch16-224"
proc = AutoProcessor.from_pretrained(mid)
model = AutoModel.from_pretrained(mid, dtype=torch.float32).to("mps").eval()


def enc_img(ims):
    with torch.no_grad():
        i = proc(images=ims, return_tensors="pt").to("mps")
        f = model.get_image_features(**i).float().cpu()
    return f / f.norm(dim=-1, keepdim=True)


def enc_txt(ts):
    with torch.no_grad():
        i = proc(
            text=ts,
            return_tensors="pt",
            padding="max_length",
            max_length=64,
            truncation=True,
        ).to("mps")
        f = model.get_text_features(**i).float().cpu()
    return f / f.norm(dim=-1, keepdim=True)


for tag, texts in (("FR", FR), ("EN", EN)):
    Tt = enc_txt(texts)
    print(f"\n-- cropped-clip retrieval, {tag} ({len(CLIPS)} clips, 9 candidate texts)")
    top1 = 0
    top3 = 0
    for c, gt in CLIPS:
        F = enc_img(frames_of(c))
        s = (Tt @ F.T).mean(1).numpy()  # mean over the clip's frames
        order = list(np.argsort(-s))
        r = order.index(gt)
        top1 += r == 0
        top3 += r < 3
        print(
            f"   {c:4s} true=blk{gt + 1}  rank={r + 1}  top1=blk{order[0] + 1}  margin={s[order[0]] - s[order[1]]:+.4f}"
        )
    print(
        f"   top-1 {top1}/{len(CLIPS)}   top-3 {top3}/{len(CLIPS)}   (chance top-1 = 0.67/6)"
    )
