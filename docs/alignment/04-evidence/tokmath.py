import math
def count_image_tokens(w,h): return math.ceil(w/28)*math.ceil(h/28)
def resized_size(width,height,max_edge=1568,max_tokens=1568):
    def fits(w,h):
        return (math.ceil(w/28)*28<=max_edge and math.ceil(h/28)*28<=max_edge
                and count_image_tokens(w,h)<=max_tokens)
    if fits(width,height): return (width,height)
    if height>width:
        rh,rw=resized_size(height,width,max_edge,max_tokens); return (rw,rh)
    ar=width/height; lo,hi=1,width
    while lo+1<hi:
        mid=(lo+hi)//2
        if fits(mid,max(round(mid/ar),1)): lo=mid
        else: hi=mid
    return (lo,max(round(lo/ar),1))
assert resized_size(1075,1520)==(924,1307)   # doc's worked example
HI=dict(max_edge=2576,max_tokens=4784); ST=dict(max_edge=1568,max_tokens=1568)

print(f"{'sheet':<24}{'tiles':>6}{'px':>12} | {'hi-res tok':>10}{'tok/tile':>9}{'px/tile(hi)':>13} | {'std tok':>8}{'tok/tile':>9}")
CASES=[('1 frame 400x225',1,400,225),('1 frame 854x480',1,854,480),
       ('6x2 = 12 @400px',12,2400,510),('6x4 = 24 @400px',24,2400,1020),
       ('6x6 = 36 @400px',36,2400,1500),('6x6 = 36 @560px',36,3360,2106),
       ('4x3 = 12 @560px',12,2240,1020),('8x5 = 40 @300px',40,2400,940),
       ('6x8 = 48 @400px',48,2400,2000)]
for name,n,w,h in CASES:
    wh,hh=resized_size(w,h,**HI); th=count_image_tokens(wh,hh)
    ws,hs=resized_size(w,h,**ST); ts=count_image_tokens(ws,hs)
    print(f"{name:<24}{n:>6}{f'{w}x{h}':>12} | {th:>10}{th/n:>9.0f}{f'{wh//int(w/ (w//n if False else 1))}':>0}"
          f"{f'{int(wh*hh/n)**0.5:.0f}²':>13} | {ts:>8}{ts/n:>9.0f}")
print()
# dollars
PR={'claude-opus-5':5.0,'claude-sonnet-5':2.0,'claude-haiku-4-5':1.0}
for name,n,w,h in [('6x6 = 36 @400px',36,2400,1500),('6x4 = 24 @400px',24,2400,1020)]:
    wh,hh=resized_size(w,h,**HI); th=count_image_tokens(wh,hh)
    ws,hs=resized_size(w,h,**ST); ts=count_image_tokens(ws,hs)
    print(f"{name}: hi-res {th} tok, standard {ts} tok")
    for m,p in PR.items():
        t = ts if m=='claude-haiku-4-5' else th
        print(f"   {m:<18} ${t*p/1e6:.5f}/sheet   1 h of video @ 1 sheet/{n*2}s "
              f"= {math.ceil(3600/(n*2))} sheets = ${math.ceil(3600/(n*2))*t*p/1e6:.2f} (image tokens only)")
