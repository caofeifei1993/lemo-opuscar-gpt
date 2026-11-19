"""Voice casting and preview helpers; listing/planning requires only Python's stdlib."""
import html
import json
import math
from pathlib import Path
import re
import unicodedata

CATALOG = Path(__file__).with_name('voice_presets.json')
DEFAULTS = {'voice': 'zh-CN-XiaoxiaoNeural', 'rate': '+0%', 'pitch': '+0Hz', 'preset': None}
SAFE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]*\Z')


def load_catalog():
    data = json.loads(CATALOG.read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or data.get('backend') != 'edge':
        raise ValueError('unsupported voice catalog schema')
    presets = data.get('presets')
    if not isinstance(presets, list) or not presets:
        raise ValueError('voice catalog must contain presets')
    seen = set()
    for p in presets:
        if not isinstance(p, dict) or not isinstance(p.get('id'), str) or not SAFE_ID.fullmatch(p['id']):
            raise ValueError('invalid preset ID in catalog')
        if p['id'] in seen:
            raise ValueError(f"duplicate preset: {p['id']}")
        seen.add(p['id'])
        for field in ('name', 'voice', 'locale', 'gender', 'rate', 'pitch', 'description', 'sample_text'):
            if not isinstance(p.get(field), str) or not p[field].strip():
                raise ValueError(f"preset {p['id']}: missing {field}")
        if not isinstance(p.get('tags'), list) or not all(isinstance(t, str) for t in p['tags']):
            raise ValueError(f"preset {p['id']}: invalid search tags")
        validate_settings(p)
    if data.get('default') not in seen:
        raise ValueError('unknown default preset in catalog')
    return data


def rate_value(value):
    if isinstance(value, bool):
        raise ValueError('rate/speed must be a percentage string or positive speed multiplier')
    if isinstance(value, (int, float)):
        if not math.isfinite(value) or value <= 0:
            raise ValueError('speed must be finite and greater than zero')
        value = f'{round((value - 1) * 100):+d}%'
    if not isinstance(value, str) or not re.fullmatch(r'[+-]\d+%', value):
        raise ValueError(f"rate must look like '+10%' or '-5%', got {value!r}")
    if int(value[:-1]) <= -100:
        raise ValueError('rate must be greater than -100%')
    return value


def validate_settings(settings):
    voice = settings.get('voice')
    if not isinstance(voice, str) or not voice.strip():
        raise ValueError('voice must be a non-empty voice identifier')
    rate_value(settings.get('rate'))
    pitch = settings.get('pitch')
    if not isinstance(pitch, str) or not re.fullmatch(r'[+-]\d+Hz', pitch):
        raise ValueError(f"pitch must look like '-2Hz' or '+0Hz', got {pitch!r}")


def resolve_lines(lines, *, preset=None, voice=None, rate=None, pitch=None, cast=None):
    """Layer defaults, global settings, role, then line; a preset resets its three settings."""
    presets = {p['id']: p for p in load_catalog()['presets']}

    def apply(base, layer):
        if isinstance(layer, str):
            layer = {'preset': layer}
        if not isinstance(layer, dict):
            raise ValueError('voice settings must be an object or preset ID')
        result = dict(base)
        if layer.get('preset') is not None:
            key = layer['preset']
            if not isinstance(key, str) or key not in presets:
                raise ValueError(f'unknown preset: {key!r}; use --list-presets')
            result.update({k: presets[key][k] for k in ('voice', 'rate', 'pitch')})
            result['preset'] = key
        for key in ('voice', 'pitch'):
            if key in layer and layer[key] is not None:
                result[key] = layer[key]
        if layer.get('rate') is not None:
            result['rate'] = rate_value(layer['rate'])
        elif layer.get('speed') is not None:
            speed = layer['speed']
            if isinstance(speed, bool):
                raise ValueError('speed must be a positive number')
            try:
                speed = float(speed)
            except (TypeError, ValueError):
                raise ValueError('speed must be a positive number') from None
            result['rate'] = rate_value(speed)
        validate_settings(result)
        return result

    if not isinstance(lines, list) or not lines:
        raise ValueError('lines must be a non-empty JSON array')
    if cast is None:
        cast = {}
    if not isinstance(cast, dict):
        raise ValueError('cast must be a JSON object mapping roles to presets/settings')
    base = apply(DEFAULTS, {'preset': preset, 'voice': voice, 'rate': rate, 'pitch': pitch})
    # Validate unused roles too, so typos cannot hide until a later scene.
    roles = {}
    for name, config in cast.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError('role names must be non-empty strings')
        if isinstance(config, dict):
            unknown = config.keys() - {'preset', 'voice', 'rate', 'pitch', 'speed'}
            if unknown:
                raise ValueError(f'role {name}: unknown settings {", ".join(sorted(unknown))}')
        roles[name] = apply(base, config)
    resolved, seen = [], set()
    for line in lines:
        if not isinstance(line, dict):
            raise ValueError('each line must be an object')
        key = line.get('id')
        if isinstance(key, int) and not isinstance(key, bool):
            key = str(key)
        if (not isinstance(key, str) or not key.strip() or key in ('.', '..')
                or re.search(r'[/\\:*?"<>|\x00-\x1f]', key)
                or re.match(r'^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\.|$)', key, re.I)):
            raise ValueError(f'invalid line id: {key!r}; use a filename without path separators')
        filename_key = unicodedata.normalize('NFC', key).casefold()
        if filename_key in seen:
            raise ValueError(f'duplicate line id: {key}')
        seen.add(filename_key)
        for field in ('text', 'say'):
            value = line.get(field, line.get('text'))
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'line {key}: {field} must be non-empty text')
        role = line.get('role')
        if role is not None and (not isinstance(role, str) or role not in roles):
            raise ValueError(f'line {key}: unknown role {role!r}; define it in --cast')
        settings = apply(roles[role] if role is not None else base, line)
        resolved.append({**settings, 'id': key, 'text': line['text'],
                         'say': line.get('say', line['text']), 'role': role})
    return resolved


def preview_lines(selection):
    presets = load_catalog()['presets']
    if selection != 'all':
        presets = [p for p in presets if p['id'] == selection]
        if not presets:
            raise ValueError(f'unknown preset: {selection!r}; use --list-presets')
    return [{'id': p['id'], 'text': p['sample_text'], 'preset': p['id']} for p in presets]


def write_gallery(directory, manifest):
    """Local, network-free player for the WAVs synthesized by the preview command."""
    presets = {p['id']: p for p in load_catalog()['presets']}
    esc = html.escape
    cards = []
    for line in manifest['lines']:
        p = presets[line['preset']]
        cards.append(f'''<article data-search="{esc(' '.join([p['name'], p['id'], p['locale'], p['gender'], *p['tags']]), quote=True)}">
<div class="meta">{esc(p['locale'])} · {'女声' if p['gender']=='Female' else '男声'}</div>
<h2>{esc(p['name'])}</h2><p>{esc(p['description'])}</p>
<blockquote>{esc(line['say'])}</blockquote>
<audio controls preload="none" src="{esc(line['file'], quote=True)}"></audio>
<code>{esc(p['id'])}</code><small>{esc(line['voice'])} · {esc(line['rate'])} · {esc(line['pitch'])} · {line['duration']:.2f}s</small>
</article>''')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Lemo · 语音试听</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f1e9;color:#252d32;font:16px/1.6 Inter,"PingFang SC",system-ui,sans-serif}
header,main,footer{max-width:1200px;margin:auto;padding:28px}header{padding-top:52px}h1{font:500 40px/1.2 "Source Sans 3","PingFang SC",sans-serif;margin:12px 0}
header p{max-width:780px;color:#62686b}input{width:100%;padding:14px 18px;border:1px solid #bbc4c2;border-radius:10px;font:inherit;background:#fff}
main{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:20px;padding-top:0}article{background:#fff;border:1px solid #e2ded4;border-radius:14px;padding:24px}
h2{font-size:22px;margin:8px 0}article p{color:#62686b;min-height:52px}.meta{font-size:12px;letter-spacing:.06em;color:#487268}
blockquote{margin:18px 0;padding-left:12px;border-left:3px solid #ceba8e;min-height:54px}audio{width:100%;margin:8px 0 16px}code{display:block;color:#305b52}small{display:block;color:#798180;font-size:11px;overflow-wrap:anywhere;margin-top:7px}
[hidden]{display:none!important}footer{font-size:13px;color:#717571}@media(max-width:500px){header,main,footer{padding:20px}h1{font-size:32px}}
</style><header><h1>语音包试听</h1>
<p>播放样音，找到合适的声音后，将卡片上的预设 ID 用于旁白或角色。</p>
<label for="search">筛选音色、语言或用途</label><input id="search" type="search" placeholder="例如：讲书、粤语、男声、en-US"></header><main>'''
    page += '\n'.join(cards)
    page += '''</main><footer>样音由 Microsoft Edge 合成。此页可离线播放。</footer>
<script>document.querySelector('#search').addEventListener('input',e=>{const q=e.target.value.trim().toLowerCase();document.querySelectorAll('article').forEach(c=>c.hidden=!c.textContent.toLowerCase().includes(q)&&!c.dataset.search.toLowerCase().includes(q))});document.querySelectorAll('audio').forEach(a=>a.addEventListener('play',()=>document.querySelectorAll('audio').forEach(b=>{if(a!==b)b.pause()})));</script></html>'''
    Path(directory, 'index.html').write_text(page, encoding='utf-8')
