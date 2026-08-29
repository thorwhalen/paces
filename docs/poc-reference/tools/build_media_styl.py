"""Re-render every clip through the anime/cartoon stylizer, then rebuild posters + gifs."""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('BLUR_ANIME_FACES', '1')
import stylize as S

OUT = 'media'
crops = json.load(open('crops.json'))
clips = json.load(open('clips.json'))
models = S.load_models()
t0 = time.time()

for c in clips:
    cid = c['id']
    cx, cy, cw, ch = crops[cid]
    out = f'{OUT}/{cid}.mp4'
    tmp = out + '.src.mp4'
    S._cut('source.mp4', c['start'], c['dur'],
           f'crop={cw}:{ch}:{cx}:{cy},fps=25,scale=560:-2', tmp)
    n = S.stylize(models, tmp, out, flat_bg=True, crf='26')
    os.remove(tmp)
    print(f'{out} {n}f {os.path.getsize(out)/1024:.0f}KB  [{time.time()-t0:.0f}s]', flush=True)
    # poster + gif from the stylized clip
    subprocess.run(['ffmpeg', '-y', '-ss', str(c['dur'] / 2), '-i', out, '-frames:v', '1',
                    '-vf', 'scale=360:-1', '-q:v', '5', f'{OUT}/{cid}.jpg', '-loglevel', 'error'],
                   check=True)
    pal = f'{OUT}/{cid}.pal.png'
    vf = 'fps=10,scale=300:-1:flags=lanczos'
    subprocess.run(['ffmpeg', '-y', '-i', out, '-vf', vf + ',palettegen=max_colors=128:stats_mode=diff',
                    pal, '-loglevel', 'error'], check=True)
    subprocess.run(['ffmpeg', '-y', '-i', out, '-i', pal, '-lavfi',
                    vf + '[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle',
                    '-loop', '0', f'{OUT}/{cid}.gif', '-loglevel', 'error'], check=True)
    os.remove(pal)

# the full run-through, with its music
out = f'{OUT}/filage.mp4'
tmp = out + '.src.mp4'
S._cut('source.mp4', 50.6, 166, 'scale=854:480', tmp, crf='20')
subprocess.run(['ffmpeg', '-y', '-ss', '50.6', '-t', '166', '-i', 'source.mp4', '-vn',
                '-c:a', 'aac', '-b:a', '96k', out + '.aac.m4a', '-loglevel', 'error'], check=True)
n = S.stylize(models, tmp, out, flat_bg=True, audio_from=out + '.aac.m4a', crf='28')
os.remove(tmp); os.remove(out + '.aac.m4a')
subprocess.run(['ffmpeg', '-y', '-ss', '70', '-i', out, '-frames:v', '1', '-vf', 'scale=854:-1',
                '-q:v', '5', f'{OUT}/filage.jpg', '-loglevel', 'error'], check=True)
print(f'{out} {n}f {os.path.getsize(out)/1e6:.2f}MB  [{time.time()-t0:.0f}s]', flush=True)

mp4 = sum(os.path.getsize(f'{OUT}/{f}') for f in os.listdir(OUT) if f.endswith(('.mp4', '.jpg')))
gif = sum(os.path.getsize(f'{OUT}/{f}') for f in os.listdir(OUT) if f.endswith('.gif'))
print(f'DONE  page media {mp4/1e6:.2f} MB · gifs {gif/1e6:.2f} MB  [{time.time()-t0:.0f}s]')
