"""Re-render just the 15 short clips (not the filage) + their posters and gifs."""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('BLUR_ANIME_FACES', '1')
os.environ.setdefault('NARROW_HEAD_BAND', '1')
import stylize as S

OUT = 'media'
crops = json.load(open('crops.json'))
clips = json.load(open('clips.json'))
models = S.load_models()
t0 = time.time()
for c in clips:
    cid = c['id']
    cx, cy, cw, ch = crops[cid]
    out, tmp = f'{OUT}/{cid}.mp4', f'{OUT}/{cid}.mp4.src.mp4'
    S._cut('source.mp4', c['start'], c['dur'],
           f'crop={cw}:{ch}:{cx}:{cy},fps=25,scale=560:-2', tmp)
    n = S.stylize(models, tmp, out, flat_bg=True, crf='26')
    os.remove(tmp)
    subprocess.run(['ffmpeg', '-y', '-ss', str(c['dur'] / 2), '-i', out, '-frames:v', '1',
                    '-vf', 'scale=360:-1', '-q:v', '5', f'{OUT}/{cid}.jpg', '-loglevel', 'error'], check=True)
    pal, vf = f'{OUT}/{cid}.pal.png', 'fps=10,scale=300:-1:flags=lanczos'
    subprocess.run(['ffmpeg', '-y', '-i', out, '-vf', vf + ',palettegen=max_colors=128:stats_mode=diff',
                    pal, '-loglevel', 'error'], check=True)
    subprocess.run(['ffmpeg', '-y', '-i', out, '-i', pal, '-lavfi',
                    vf + '[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle',
                    '-loop', '0', f'{OUT}/{cid}.gif', '-loglevel', 'error'], check=True)
    os.remove(pal)
    print(f'{out} {n}f {os.path.getsize(out)/1024:.0f}KB  [{time.time()-t0:.0f}s]', flush=True)
print('DONE')
