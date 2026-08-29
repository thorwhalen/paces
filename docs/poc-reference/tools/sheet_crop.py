#!/usr/bin/env python
"""Contact sheet with a crop: sheet_crop.py START END STEP OUT.jpg COLS CX CY CW CH"""
import subprocess, sys, tempfile, os, glob
from PIL import Image, ImageDraw, ImageFont
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'source.mp4')
start, end, step, out = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
cols = int(sys.argv[5]); cx,cy,cw,ch = (int(v) for v in sys.argv[6:10])
tmp = tempfile.mkdtemp()
subprocess.run(['ffmpeg','-y','-ss',str(start),'-to',str(end),'-i',SRC,
                '-vf',f'crop={cw}:{ch}:{cx}:{cy},fps={1/step},scale=340:-1','-q:v','3',
                os.path.join(tmp,'f_%03d.jpg'),'-loglevel','error'], check=True)
files = sorted(glob.glob(os.path.join(tmp,'f_*.jpg')))
font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf', 22)
W,H = Image.open(files[0]).size
rows = (len(files)+cols-1)//cols
sheet = Image.new('RGB',(cols*W, rows*H),'black'); d = ImageDraw.Draw(sheet)
for i,f in enumerate(files):
    t = start + i*step
    im = Image.open(f); x,y = (i%cols)*W, (i//cols)*H
    sheet.paste(im,(x,y)); d.rectangle([x+2,y+2,x+94,y+30], fill='black')
    d.text((x+6,y+4), f'{t:.1f}', fill='yellow', font=font)
sheet.save(out, quality=88)
print(f'{out} {sheet.size} {len(files)} tiles')
