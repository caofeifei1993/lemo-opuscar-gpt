#!/usr/bin/env python3
"""Render a two-second local diagnostic through the real production tools.

Run from any directory: python3 /path/to/lemo-opuscar-gpt/tools/smoke_codex.py
Requires the core dependencies (setup.sh deps), Node, ffmpeg and ffprobe.
Each run gets a new folder under films/codex-smoke; --out must be empty.
No model, voice service, image generator or media download is used.
"""

import argparse
from array import array
from datetime import datetime
from fractions import Fraction
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import wave


LIB = Path(__file__).resolve().parents[1]
DURATION, FPS, WIDTH, HEIGHT, SAMPLE_RATE = 2, 24, 640, 360, 48000

PAGE = """<!doctype html>
<meta charset="utf-8">
<title>Codex render check</title>
<style>html,body{margin:0;overflow:hidden;background:#111827}canvas{display:block}</style>
<canvas id="stage"></canvas>
<script>
const canvas = document.getElementById('stage');
canvas.width = innerWidth; canvas.height = innerHeight;
const ctx = canvas.getContext('2d');
window.DUR = 2;
window.EV = [{t:0, type:'tone', frequency:440}];
window.render = t => {
  const w = canvas.width, h = canvas.height;
  ctx.fillStyle = '#111827'; ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = '#f9fafb'; ctx.font = 'bold 30px sans-serif';
  ctx.textAlign = 'center'; ctx.fillText('Codex render check', w / 2, h * .25);
  ctx.fillStyle = '#9ca3af'; ctx.font = '16px sans-serif';
  ctx.fillText('Canvas / Chromium / FFmpeg', w / 2, h * .36);
  ctx.strokeStyle = '#374151'; ctx.lineWidth = 3;
  ctx.beginPath(); ctx.moveTo(w * .18, h * .62); ctx.lineTo(w * .82, h * .62); ctx.stroke();
  const x = w * (.18 + .64 * Math.max(0, Math.min(1, t / 2)));
  ctx.fillStyle = '#34d399'; ctx.beginPath(); ctx.arc(x, h * .62, 18, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = '#d1d5db'; ctx.font = '14px monospace';
  ctx.fillText(t.toFixed(2) + ' s  /  2.00 s', w / 2, h * .85);
};
window.READY = true;
window.render(0);
</script>
"""


def run(*args):
    print('+ ' + ' '.join(str(arg) for arg in args), flush=True)
    subprocess.run([str(arg) for arg in args], cwd=LIB, check=True)


def write_audio(path):
    samples = array('h')
    for frame in range(DURATION * SAMPLE_RATE):
        t = frame / SAMPLE_RATE
        envelope = min(1, t / .05, (DURATION - t) / .05)
        sample = round(32767 * .15 * envelope * math.sin(2 * math.pi * 440 * t))
        samples.extend((sample, sample))
    if sys.byteorder != 'little':
        samples.byteswap()
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(samples.tobytes())


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, help='an empty output directory; otherwise a fresh run folder is created')
    args = parser.parse_args()
    for command in ('node', 'ffmpeg', 'ffprobe', 'sh'):
        check(shutil.which(command), f'{command} is missing from PATH')
    check((LIB / 'node_modules/playwright-core').is_dir(), 'Run sh plugin/skills/lemo-opuscar/scripts/setup.sh deps first')
    if args.out:
        project = args.out.expanduser().absolute()
        check(not project.is_symlink(), f'Refusing a symlink output: {project}')
        project.mkdir(parents=True, exist_ok=True)
        check(not any(project.iterdir()), f'Refusing to overwrite a non-empty directory: {project}')
    else:
        root = LIB / 'films/codex-smoke'
        root.mkdir(parents=True, exist_ok=True)
        project = Path(tempfile.mkdtemp(prefix=datetime.now().strftime('%Y%m%d-%H%M%S-'), dir=root))
    (project / 'index.html').write_text(PAGE, encoding='utf-8')
    write_audio(project / 'mix.wav')
    size = f'{WIDTH}x{HEIGHT}'
    run('node', 'core/render/events.mjs', project, '--size', size)
    events = json.loads((project / 'events.json').read_text(encoding='utf-8'))
    check(events == {'dur': DURATION, 'ev': [{'t': 0, 'type': 'tone', 'frequency': 440}]}, 'Timeline export did not match the page')
    run('node', 'core/render/still.mjs', project, '0', '1', '--size', size)
    check((project / 'stills/t_0.jpg').read_bytes() != (project / 'stills/t_1.jpg').read_bytes(), 'The diagnostic animation did not advance')
    video = project / 'out/video.mp4'
    final = project / 'codex-smoke.mp4'
    run('node', 'core/render/video.mjs', project, '--fps', FPS, '--workers', '1', '--size', size, '--out', video)
    run('sh', 'core/render/mux.sh', video, project / 'mix.wav', final, FPS, '0')
    probe = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(final)
    ], text=True))
    videos = [stream for stream in probe['streams'] if stream['codec_type'] == 'video']
    audios = [stream for stream in probe['streams'] if stream['codec_type'] == 'audio']
    check(len(videos) == len(audios) == 1, 'Expected exactly one video stream and one audio stream')
    picture, audio = videos[0], audios[0]
    check(picture['codec_name'] == 'h264' and audio['codec_name'] == 'aac', 'Expected H.264 video and AAC audio')
    check((picture['width'], picture['height']) == (WIDTH, HEIGHT), 'Unexpected video dimensions')
    check(Fraction(picture['avg_frame_rate']) == FPS, 'Unexpected video frame rate')
    check(int(picture['nb_frames']) == DURATION * FPS, 'Unexpected frame count')
    check(int(audio['sample_rate']) == SAMPLE_RATE and audio['channels'] == 2, 'Unexpected audio format')
    for item in (probe['format'], picture, audio):
        check(abs(float(item['duration']) - DURATION) <= .1, 'An audio/video stream has the wrong duration')
    run('ffmpeg', '-v', 'error', '-xerror', '-i', final, '-f', 'null', '-')
    report = {
        'passed': True, 'video': str(final), 'preview': str(project / 'stills/t_1.jpg'),
        'duration_seconds': float(probe['format']['duration']), 'size': size,
        'fps': FPS, 'frames': int(picture['nb_frames']), 'audio': 'AAC stereo 48000 Hz',
        'checks': ['events', 'animated stills', 'video render', 'audio mux', 'ffprobe', 'full decode'],
    }
    (project / 'check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'Codex render check failed: {error}', file=sys.stderr)
        sys.exit(1)
