"""edge-tts voice (Microsoft neural voices; first choice for Chinese, reads other languages too):
    python core/tts/tts_zh.py lines.json out_dir [--voice zh-CN-XiaoxiaoNeural] [--rate +0%] [--pitch +0Hz]
    python core/tts/tts_zh.py --list-presets
    python core/tts/tts_zh.py --preview all --out-dir voice-library
    python core/tts/tts_zh.py lines.json out_dir --preset zh-warm-female [--cast cast.json] [--dry-run]
lines.json = [{"id":..., "text":..., "voice":"zh-CN-YunxiNeural", "rate":"+10%", "pitch":"-2Hz", "say":"..."}, ...]
  "say" (optional) = the text actually sent to be spoken, default "text" (for numbers and abbreviations written out as read; subtitles still use text).
  Also takes tts.py's "speed" (a multiplier, 1.1 → +10%). Voice list: python -m edge_tts --list-voices
Output is the same as tts.py: out_dir/<id>.wav (24 kHz mono, leading/trailing silence trimmed) and out_dir/dur.json.
  The mp3s are cached in out_dir/.cache/; unchanged text/voice/rate is not fetched again (written to .part, then renamed, so Ctrl-C never
  leaves half a file that the next run takes as good; a damaged mp3 in the cache is deleted and fetched again).

Needs the internet: this is Microsoft's online speech service, not a local model. Check Microsoft's terms yourself before using the voices commercially.
Exits with an error when the network is down or blocked (exit code 2; bad input or configuration is 1). Offline alternative: tts.py with
"lang":"cmn" (Kokoro, plain timbre; check it with asr_check.py).
"""
import argparse
import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from voice_library import load_catalog, preview_lines, resolve_lines, write_gallery

SR = 24000


async def synth(text, voice, rate, pitch, path):
    """Download to path: write path.part first and rename only on success, so if path exists it is always complete (no interruption, Ctrl-C included, leaves half a file)"""
    import edge_tts
    fd, part = tempfile.mkstemp(dir=Path(path).parent, suffix='.part')
    os.close(fd)
    last = None
    try:
        for attempt in range(3):   # retry twice on occasional network hiccups
            try:
                await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(part)
                if os.path.getsize(part) == 0: raise OSError('the service returned an empty file')
                os.replace(part, path); return
            except Exception as e:
                last = e
                if type(e).__name__ == 'NoAudioReceived': break   # wrong voice name/text; retrying won't help
                await asyncio.sleep(1.5 * (attempt + 1))
        raise last
    finally:
        if os.path.exists(part): os.remove(part)   # clean up on failure and on Ctrl-C


def to_wav(mp3):
    """Decode to 24 kHz mono; returns None if the file is damaged (the caller deletes the cache entry and downloads again)"""
    try:
        r = subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', mp3, '-ar', str(SR), '-ac', '1', '-f', 'wav', '-'], capture_output=True, check=True)
    except FileNotFoundError: sys.exit('tts_zh.py: ffmpeg is needed to decode the audio (install it and make sure it is on PATH)')
    except subprocess.CalledProcessError: return None
    import soundfile as sf
    try: a, sr = sf.read(io.BytesIO(r.stdout), dtype='float32')
    except Exception: return None
    return (a, sr) if len(a) else None


def plausible(decoded):
    """A cached mp3 must decode to something like a sentence: at least 0.15 s and not silent (a half file often "decodes successfully" but leaves only a short stretch of silence)"""
    if decoded is None: return False
    a, sr = decoded; return len(a) >= 0.15 * sr and float(abs(a).max()) > 1e-3


def render(lines, directory, stage):
    try:
        import edge_tts
        import numpy as np
        import soundfile as sf
    except ImportError as e:
        sys.exit(f'tts_zh.py: {e}. Install the voice tier: sh plugin/skills/lemo-opuscar/scripts/setup.sh deps voice')
    cache = directory / '.cache'
    cache.mkdir(exist_ok=True)
    durations = {}
    for L in lines:
        voice, rate, pitch, say = (L[k] for k in ('voice', 'rate', 'pitch', 'say'))
        key = hashlib.sha1(json.dumps([voice, rate, pitch, say], ensure_ascii=False).encode('utf-8')).hexdigest()[:16]
        mp3 = cache / (key + '.mp3')
        decoded = to_wav(mp3) if os.path.exists(mp3) else None
        if not plausible(decoded): decoded = None
        if decoded is None and os.path.exists(mp3): print(f"tts_zh.py: cached audio for line '{L['id']}' was damaged; fetching it again", file=sys.stderr)
        if decoded is None:
            try: asyncio.run(synth(say, voice, rate, pitch, mp3))
            except Exception as e:
                if type(e).__name__ == 'NoAudioReceived':
                    sys.exit(f"tts_zh.py: no audio came back for line '{L['id']}'. Is the voice name '{voice}' valid (python -m edge_tts --list-voices) and the text speakable?")
                if isinstance(e, ValueError):   # the arguments themselves are wrong (e.g. the voice name doesn't exist); no request was ever sent
                    sys.exit(f"tts_zh.py: line '{L['id']}': {e}  (voices: python -m edge_tts --list-voices)")
                print(f"tts_zh.py: could not reach Microsoft's speech service for line '{L['id']}': {type(e).__name__}: {str(e)[:200]}\n"
                      "  edge-tts needs a network connection (and can be blocked by a firewall/proxy). Offline alternative: tts.py with \"lang\": \"cmn\".", file=sys.stderr)
                sys.exit(2)   # exit code 2 = network problem; 1 = bad input/configuration
            decoded = to_wav(mp3)
            if not plausible(decoded): sys.exit(f"tts_zh.py: the audio Microsoft returned for line '{L['id']}' could not be decoded (ffmpeg); try again")
        y, sr = decoded
        nz = np.where(np.abs(y) > (np.abs(y).max() if len(y) else 0) * .02)[0]
        if len(nz): y = y[max(0, nz[0] - int(.03 * sr)): nz[-1] + int(.10 * sr)]   # trim leading/trailing silence; leave a slightly longer tail so the sentence's last ring isn't cut off
        else: print('warning: line', L['id'], 'is silent', file=sys.stderr)
        filename = f"{L['id']}.wav"
        sf.write(stage / filename, y, sr)
        duration = round(len(y) / sr, 3)
        L.update(file=filename, duration=duration)
        durations[L['id']] = duration
        print(L['id'], duration, L['text'], flush=True)
    return durations


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--list-presets', action='store_true', help='list the bundled voice presets offline')
    mode.add_argument('--preview', metavar='ID|all', help='synthesize catalog samples and a local audition page')
    ap.add_argument('lines', nargs='?', help='JSON script')
    ap.add_argument('out_dir', nargs='?', help='output directory for narration')
    ap.add_argument('--out-dir', dest='preview_dir', help='output directory for the preview')
    ap.add_argument('--json', action='store_true', help='print the catalog as JSON with --list-presets')
    ap.add_argument('--dry-run', action='store_true', help='print resolved settings without writing or connecting')
    ap.add_argument('--cast', metavar='FILE', help='JSON mapping role names to presets or settings')
    ap.add_argument('--preset', help='default preset for the script')
    for field in ('voice', 'rate', 'pitch'):
        ap.add_argument('--' + field, help='override the default ' + field)
    a = ap.parse_args()
    overrides = any(x is not None for x in (a.cast, a.preset, a.voice, a.rate, a.pitch))
    if a.json and not a.list_presets:
        ap.error('--json requires --list-presets')
    if a.list_presets:
        if any((a.lines, a.out_dir, a.preview_dir, overrides, a.dry_run)):
            ap.error('use --list-presets alone or with --json')
        catalog = load_catalog()
        if a.json:
            print(json.dumps(catalog, ensure_ascii=False, indent=2))
        else:
            for p in catalog['presets']:
                print(f"{p['id']:24} {p['name']}  ({p['locale']}, {p['rate']}, {p['pitch']})")
        return
    if a.preview is not None:
        if a.lines or a.out_dir or overrides or (not a.preview_dir and not a.dry_run):
            ap.error('use --preview ID|all --out-dir DIRECTORY [--dry-run]')
        lines = resolve_lines(preview_lines(a.preview))
        directory = a.preview_dir
    else:
        if not a.lines or not a.out_dir or a.preview_dir:
            ap.error('provide lines.json and an output directory')
        cast = read_json(a.cast) if a.cast else {}
        if not isinstance(cast, dict):
            raise ValueError('cast must be a JSON object')
        lines = resolve_lines(read_json(a.lines), preset=a.preset, voice=a.voice,
                              rate=a.rate, pitch=a.pitch, cast=cast)
        directory = a.out_dir
    manifest = {'backend': 'edge', 'sample_rate': SR, 'lines': lines}
    if a.dry_run:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    # Keep the previous completed batch usable if a later line fails.
    with tempfile.TemporaryDirectory(dir=directory, prefix='.tts-') as tmp:
        stage = Path(tmp)
        durations = render(lines, directory, stage)
        write_json(stage / 'dur.json', durations)
        write_json(stage / 'manifest.json', manifest)
        if a.preview is not None:
            write_gallery(stage, manifest)
        for file in stage.iterdir():
            file.replace(directory / file.name)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as e:
        sys.exit(f'tts_zh.py: {e}')
