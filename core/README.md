# core/: the shared production tools

Command reference for `core/` and `tools/`. How the pieces fit together is in [`TECHNIQUE.md`](../TECHNIQUE.md). Run commands from the library root (`$LIB` in skill mode); Python is the library's `.venv/bin/python`. `<demo>` is any folder with an `index.html`.

## Install

| Command | What it does |
|---|---|
| `sh plugin/skills/lemo-opuscar/scripts/setup.sh [check]` | locate the library and report readiness without downloading or updating; prints `LIB=<path>` |
| `… setup.sh install` | download this fork when the library is missing; preserve existing libraries |
| `… setup.sh update` | fast-forward a clean main branch from its existing origin; refuse local changes or divergence |
| `… setup.sh deps` | core tier: npm packages, headless browser, `.venv` from `requirements.txt` |
| `… setup.sh deps voice` | adds `requirements-voice.txt` (kokoro-onnx, edge-tts, faster-whisper) and the Kokoro model |
| `… setup.sh deps music` | adds `requirements-music.txt` (numba, for `pluck.py`; `sampler.py` needs only the core) |
| `… setup.sh demo <slug>` | adds one style's demo source and poster (to read, not to render) |
| `sh tools/fetch.sh voice` \| `hdri` \| `instruments <lib>` \| `instruments all` | Kokoro model · HDRIs · a sample library (`freepats`, `karoryfer`, `salamander`, `vcsl`, `vsco2ce`) |

Sizes are in TECHNIQUE.md §1.

## The page contract

| Global | Required | Meaning |
|---|---|---|
| `window.READY = true` | yes | set once fonts and images are loaded |
| `window.render(t)` | yes | draw the frame at second `t`; deterministic |
| `window.DUR` | video, events, readcheck | film length in seconds |
| `window.EV = [{t, type, …}]` | no | sound and cue events, exported by `events.mjs` |
| `window.TEXTS(t)` | readcheck | `[{id, text, x0, y0, x1, y1}]`: every on-screen text visible at `t`, with its box in pixels. Report an element's **full** text from its first visible frame (a typewriter that reports only the typed letters fails the check). Add `pass: true` to text the viewer isn't meant to read in full (a sign passed by, fine-print credits) |

The viewport is 1920×1080 at device scale 1, or `--size WxH`. `--q 'k=v&…'` reaches the page as `location.search`. A page error, or an HTTP error on a script, module or the page, stops the tool (exit 1). Other missing files (fetch, images, fonts) print `optional file missing: <URL>` and the tool carries on. The tools wait up to 180 s for `window.READY`.

## Render

| Command | What it does |
|---|---|
| `node core/render/still.mjs <demo> <t> [<t> …] [--range a:b:step] [--prefix t_] [--out dir]` | review stills as JPEGs (default `<demo>/stills/t_<t>.jpg`) |
| `node core/render/video.mjs <demo> [--fps 24] [--workers 3] [--out <demo>/out/video.mp4]` | every frame to a video; up to 6 workers for a single render. Each parallel version needs its own `--out` |
| `node core/render/events.mjs <demo> [--out <file>]` | export `{dur, ev}` to `<demo>/events.json` |
| `node core/render/readcheck.mjs <demo> [--step 0.04] [--latin-cps 15] [--cjk-cps 4.5] [--pad 1.5] [--min 1.5]` | reading-time check (below) |
| `.venv/bin/python core/render/sheet.py out.jpg img… [--cols 4] [--w 480]` | contact sheet |
| `.venv/bin/python core/render/srt.py cues.json out.srt` | subtitles from `[{t0, t1, text}]` |
| `sh core/render/mux.sh video.mp4 mix.wav out.mp4 [fps=24] [grain=2]` | mux and master (below) |

All four page tools take `--size WxH` (default `1920x1080`, even numbers) and `--q 'k=v'`.

**readcheck** asks the page for `window.TEXTS(t)` at every step. Each text must stay fully in frame, unchanged, for at least CJK characters ÷ 4.5 + other non-space characters ÷ 15 + 1.5 s, and never less than `--min`. A new `text` under the same `id` starts a new piece. Text marked `pass: true` (a shop sign in a fly-through, a label the camera sweeps past, fine-print licence credits on the end card) is listed as passing and not timed; never mark text the film needs read. Subtitles are checked by their `.srt`, not here.

**mux** runs a two-pass `loudnorm` to −14 LUFS / true peak −1.2 dB and a 4× oversampled, delay-compensated limiter for a true peak at or under −1 dBTP (if AAC still pushes a peak over, it encodes the audio again with a lower ceiling, picture copied, up to three times, and warns if the peak is still over), adds film grain (`grain` 0 = none) and prints the measured loudness. Silent audio is left at its level with a warning; short audio is padded, long audio cut at the picture's end; missing, damaged or truncated audio is refused. It never leaves a partial file.

## Audio

| Command | What it does |
|---|---|
| `.venv/bin/python core/tts/tts.py lines.json out_dir` | Kokoro, offline. `lines.json` = `[{id, text, voice?, speed?, lang?}]` (defaults `af_bella`, `0.92`, `en-us`; Chinese: `"lang": "cmn"`, a `zf_*`/`zm_*` voice). Writes `<id>.wav` (24 kHz, trimmed) and `dur.json`. Needs a library path under 160 bytes (espeak-ng); it checks |
| `.venv/bin/python core/tts/tts_zh.py lines.json out_dir [--preset <id>] [--cast cast.json] [--voice <name>] [--rate=+0%] [--pitch=+0Hz] [--dry-run]` | edge-tts (Microsoft), online; same WAV/duration layout as `tts.py`. Per line: `preset`, `role`, `voice`, `rate`, `pitch`, `speed`, `say`. `--dry-run` prints resolved settings as JSON without network or output files. No options preserves Xiaoxiao / +0% / +0Hz. Caches in `out_dir/.cache/` |
| `.venv/bin/python core/tts/tts_zh.py --list-presets [--json]` | list the bundled voice presets without contacting the service; full service voice list: `.venv/bin/python -m edge_tts --list-voices` (online) |
| `.venv/bin/python core/tts/tts_zh.py --preview <id-or-all> --out-dir films/voice-library` | synthesize audition WAVs online; writes `dur.json`, `manifest.json` and an `index.html` player alongside the audio |
| `.venv/bin/python core/tts/asr_check.py lines.json voices_dir [--lang en\|zh\|ja\|ko\|auto] [--threshold 0.92] [--model base]` | speech-to-text check of every `<id>.wav`; writes `words.json` (word timestamps). English must match word for word (0–999 count the same as their words); Chinese, Japanese, Korean compare by character similarity ≥ `--threshold`, each number by its value (十九 = 19, 一万九千 = 1.9万, 三点五 = 3.5, 百分之三十 = 30%); a number heard as a different number fails the line. An `asr` field in a line overrides the expected text (names, and in English decimals and times: write it as Whisper does) |
| `core/audio/sfx.py` | procedural foley and mix helpers: filters, envelopes, `click`, `whoosh`, `thump`, `ding`…, `compress`, `limit`, `add(buf, sound, at, gain, pan)` |
| `core/audio/sampler.py`, `core/audio/pluck.py` | sampled instruments and plucked-string modelling ([`audio/INSTRUMENTS.md`](audio/INSTRUMENTS.md)). The sample libraries a score needs are downloaded when it is rendered, all missing ones at once (`LEMO_FETCH=0`: only name the `fetch.sh instruments <lib>` commands). `.venv/bin/python core/audio/sampler.py --need <mix.py | names>` fetches them up front, before a long render (it also runs from a plain `python3`). `credits(names)` writes the CREDITS lines |

See the [voice pack guide](../docs/VOICES.md) for the catalog and character-casting examples. Settings resolve from defaults → global preset → global explicit options → cast role → line preset → line explicit options. Applying a preset replaces voice, rate and pitch together; explicit `rate` wins over `speed` at the same level. Use `--rate=-15%` and `--pitch=-1Hz` for negative CLI values. Edge supports these prosody adjustments, not custom SSML emotion tags.

## Picture helpers

| File | What it is |
|---|---|
| `core/lib.js` | seeded random `mulberry`, `hash`, `vnoise`, `clamp(x,a,b)`, `lerp(a,b,t)`, `seg(t,a,b)` (0→1 between a and b), easing on 0–1 (`ss(t)`, `eio(t)`, `eo(t)`, `ei(t)`, `back(t,s)`, `spring(t,k,z)`), `monotone`/`track` interpolation, envelope `env` |
| `core/three/post.js` | three.js post: physical depth of field, GTAO, bloom, colour grade, 2× supersampling |
| `core/render/illustrated-sequence.js` | frame opaque illustrated plates around a subject, animate the crop and time cuts or dissolves to the film clock ([camera example](../DIRECTOR.md#camera-moves-for-illustrated-sequences)) |
| `core/post/crt.js` | WebGL2 CRT / VHS pass over a 2D canvas |
| `core/fonts/` | Fredoka, Lilita One, IM Fell English, ZCOOL KuaiLe (OFL, [`fonts/OFL.md`](fonts/OFL.md)) as subsets; ZCOOL holds only ≈ 200 characters |
| `core/assets/polyhaven/` | CC0 HDRIs and models (`SOURCES.md`) |

## Image generation

The ✦ styles use generated characters, props or panels. In a Codex session choose ChatGPT native or an OpenArt model, independently for film illustrations and generated storyboard panels. The route helper prepares the host call. After the host generates the image, the save helper validates and imports it. Instructions and examples are in [Image providers](../docs/IMAGE-PROVIDERS.md).

| Command | What it does |
|---|---|
| `python3 core/image/image_route.py configure PROJECT --kind illustration --provider native` | save the illustration choice for this film. Use `--kind storyboard` for concept panels or `--kind both` to share a choice |
| `python3 core/image/image_route.py configure PROJECT --kind storyboard --provider openart --model MODEL_ID` | use the exact model ID returned by the current OpenArt image catalog |
| `.venv/bin/python core/image/image_route.py character PROJECT --id ID --description "stable features" --ref IMAGE` | register a per-film master reference for later native shots with `plan --character ID` |
| `python3 core/image/image_route.py plan PROJECT --kind storyboard --name shot-01 --prompt "Wide shot of a café at dawn" --aspect 16:9` | resolve the choice and prepare a generation request |
| `python3 core/image/gen_image.py --check` | is the Codex CLI installed and signed in? Exit 0 if so, 4 if not, with a different message for "not installed" and "not signed in". The first real image confirms that the account can generate images |
| `python3 core/image/gen_image.py "<prompt>" --aspect 16:9 --out "<project>/gen" --name <base> [--ref <image> …] [--edit]` | one image through `codex exec` (read-only sandbox, its built-in `image_gen`) → `<project>/gen/<base>_<date-time>.png`, path printed. `--ref` attaches a reference sheet (repeatable); `--edit` changes the first `--ref` and keeps the rest of it. A wrong aspect is retried, then kept as `…_wrongaspect.png`. Exit 2 no image, 3 wrong aspect, 4 setup (no Codex, a missing reference, a bad argument) |

New films record GPT Image 2.6 Sunburst as the native model preference. Native model selection is automatic and the host does not identify the model in the result. OpenArt uses the connected workspace's current image catalog and model-specific form. Check the exact model, generation mode and credits before submitting a job. On a missing provider, unsupported reference, insufficient balance or failure, keep the user's selection and report the available options. The signed-in Codex CLI helper above remains an optional native route. A style can also use suitable drawings supplied by the user. Include the planned images and their number in the brief.

## Environment variables

| Variable | Meaning |
|---|---|
| `LEMO_OPUSCAR_HOME` | explicit library path; otherwise use the current/skill checkout, then `~/lemo-opuscar-gpt` |
| `LEMO_OPUSCAR_REPO` | repository used only for a new library install (default this Codex fork); does not replace an existing origin |
| `PLAYWRIGHT_CHROME` | a Chrome / headless-shell executable instead of Playwright's |
| `LEMO_ANGLE` | WebGL backend (default `metal` on macOS; `default` passes none). A virtualised adapter (most cloud VMs and CI runners) creates the demo's context and then drops it, so WebGL styles draw nothing: `LEMO_ANGLE=swiftshader` asks for software rendering up front and renders them, slowly |
| `RENDER_SLOTS` | optional; limits concurrent full renders across processes |
| `LEMO_FETCH=0` | `sampler.py` doesn't download missing sample libraries; it stops and names the `fetch.sh` commands |
| `LEMO_COLOR=bt709` | `mux.sh` writes limited-range BT.709 instead of the default full-range output |
| `WHISPER_MODEL` | Whisper model name or local folder for `asr_check.py` (same as `--model`; default `base.en` for English, `small` for Chinese, `base` otherwise) |
| `HF_ENDPOINT` | Hugging Face mirror for the Whisper download |

## Exit codes

| Tool | 0 | 1 | 2 |
|---|---|---|---|
| render tools | done | page error, a lost WebGL context (blank frames), missing required file, ffmpeg failure | usage, no `index.html`, `--out` already being written |
| `readcheck.mjs` | all texts long enough | some too short or never fully visible | could not check (no `TEXTS`) |
| `mux.sh` | film written | any failure | – |
| `tts.py`, `srt.py` | done | bad input, missing model, path too long | usage |
| `tts_zh.py` | done | bad input | network unreachable |
| `asr_check.py` | all lines pass | mismatches | model failed to load |
