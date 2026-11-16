#!/bin/sh
# Lemo-Opuscar for Codex: locate the library and report its readiness.
#   sh setup.sh [check]             read-only check; does not download or update
#   sh setup.sh install             download a missing library from the configured repository
#   sh setup.sh update              fast-forward a clean main branch from its existing origin
#   sh setup.sh deps [voice] [music] install the core packages and optional package tiers
#   sh setup.sh demo <slug>          add one style's demo source (reference only)
# LEMO_OPUSCAR_HOME overrides library discovery; LEMO_OPUSCAR_REPO is used only for installation.
set -e
REPO=${LEMO_OPUSCAR_REPO:-https://github.com/caoofeifie1993/lemo-opuscar-gpt.git}
usage() { echo "usage: sh setup.sh [check|install|update|deps [voice] [music]|demo <slug>]"; }
action=${1:-check}
case "$action" in
  check|install|update) [ "$#" -le 1 ] || { usage >&2; exit 2; } ;;
  deps) shift; for tier in "$@"; do case "$tier" in voice|music) ;; *) usage >&2; exit 2 ;; esac; done ;;
  demo)
    [ "$#" -eq 2 ] || { usage >&2; exit 2; }
    case "$2" in ''|*[!a-z0-9-]*|-*) echo "invalid style slug: $2" >&2; exit 2 ;; esac ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

# Resolve both directory links (the Codex installer links the skill directory) and file links.
script=$0
while [ -L "$script" ]; do
  script_dir=$(CDPATH= cd -P -- "$(dirname -- "$script")" && pwd)
  target=$(readlink "$script")
  case "$target" in /*) script=$target ;; *) script=$script_dir/$target ;; esac
done
script_dir=$(CDPATH= cd -P -- "$(dirname -- "$script")" && pwd)
skill_lib=$(CDPATH= cd "$script_dir/../../../.." && pwd -P)

# Explicit override > the current library > the library containing this skill > private default.
is_lib() { [ -f "$1/AGENTS.md" ] && [ -d "$1/core/render" ]; }
if [ -n "$LEMO_OPUSCAR_HOME" ]; then LIB=$LEMO_OPUSCAR_HOME
elif top=$(git rev-parse --show-toplevel 2>/dev/null) && is_lib "$top"; then LIB=$top
elif is_lib "$skill_lib"; then LIB=$skill_lib
else LIB=$HOME/lemo-opuscar-gpt
fi
case "$LIB" in /*|[A-Za-z]:[/\\]*) ;; *) LIB=$(pwd)/$LIB ;; esac

# Our clone skips demo sources, the gallery, the README's pictures and big images; what `setup.sh demo` added stays.
# git < 2.35 has no --no-cone: then the whole library is checked out.
# The patterns reach git as written: Git Bash on Windows would turn '/styleboard/' into 'C:/Program Files/Git/styleboard/'.
# It runs from inside $LIB, because a -C /c/… path needs that rewriting.
sparse() { (cd "$LIB" && MSYS_NO_PATHCONV=1 git sparse-checkout "$@"); }
apply_sparse() {
  set -- '/*' '!/styles/*/demo/' '!/styleboard/' '!/docs/readme/' '!/docs/cover.jpg' '!/styles/*/poster.jpg' \
    $(git -C "$LIB" sparse-checkout list 2>/dev/null | grep -E '^/styles/[^/*]+/(demo/|poster\.jpg)$' || true)
  sparse set --no-cone "$@" 2>/dev/null || git -C "$LIB" sparse-checkout disable || true
}

if ! is_lib "$LIB"; then
  if [ "$action" != install ]; then
    echo "✗ no library at $LIB; run this script with 'install', or set LEMO_OPUSCAR_HOME to your clone." >&2
    exit 1
  fi
  if [ -e "$LIB" ] || [ -L "$LIB" ]; then
    [ -d "$LIB" ] && [ -z "$(ls -A "$LIB")" ] || {
      echo "✗ $LIB exists but is not an empty library folder. Choose another LEMO_OPUSCAR_HOME." >&2; exit 1;
    }
  fi
  command -v git >/dev/null || { echo "✗ git is needed to download the library" >&2; exit 1; }
  echo "↓ downloading the style library into $LIB"
  git clone --quiet --depth 1 --filter=blob:none --sparse --branch main "$REPO" "$LIB" || {
    echo "✗ download failed; no existing files were removed. Check the network or LEMO_OPUSCAR_REPO." >&2; exit 1;
  }
  apply_sparse
  is_lib "$LIB" || {
    echo "✗ downloaded repository is not a Lemo-Opuscar library; check LEMO_OPUSCAR_REPO. Files were kept at $LIB." >&2
    exit 1
  }
  git -C "$LIB" config lemo.managed true
fi
LIB=$(CDPATH= cd "$LIB" && pwd -P)

if [ "$action" = update ]; then
  top=$(git -C "$LIB" rev-parse --show-toplevel 2>/dev/null) || {
    echo "✗ update requires a Git clone" >&2; exit 1;
  }
  [ "$top" = "$LIB" ] || { echo "✗ the library must be the Git repository root" >&2; exit 1; }
  [ -z "$(git -C "$LIB" status --porcelain)" ] || {
    echo "✗ local changes found; keep them safe before updating. Nothing was changed." >&2; exit 1;
  }
  [ "$(git -C "$LIB" symbolic-ref --quiet --short HEAD)" = main ] || {
    echo "✗ update only supports the main branch; update other branches manually." >&2; exit 1;
  }
  git -C "$LIB" fetch --quiet origin main
  git -C "$LIB" merge --ff-only FETCH_HEAD
fi

# Installed packages are tracked by content: a marker holds a checksum of the files they came from (and the Python
# version), so a changed package.json or requirements file triggers a reinstall.
sig() { cat "$@" 2>/dev/null | cksum | cut -d' ' -f1; }
pysig() { echo "$(sig "$1")-$("$LIB/.venv/bin/python" -V 2>&1 | cut -d. -f1,2)"; }
req() { [ "$1" = core ] && echo "$LIB/requirements.txt" || echo "$LIB/requirements-$1.txt"; }
node_ok() { [ "$(cat "$LIB/node_modules/.lemo-ok" 2>/dev/null)" = "$(sig "$LIB/package.json" "$LIB/package-lock.json")" ]; }
py_ok() { [ "$(cat "$LIB/.venv/.lemo-$1" 2>/dev/null)" = "$(pysig "$(req "$1")")" ]; }
# a Python 3.11+ for the venv when uv is absent; kokoro-onnx (voice tier) needs < 3.14, so those come first
find_py() {
  for c in python3.12 python3.13 python3.11 python3 python; do
    "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null && { echo "$c"; return 0; }
  done
  return 1
}
# Windows (Git Bash): a venv keeps its Python in Scripts/python.exe. Give it the .venv/bin/python every tool calls,
# a shim that also forces UTF-8 (a Chinese Windows defaults to GBK, which can't print ✓ or read our UTF-8 files).
win_shim() {
  [ -f .venv/Scripts/python.exe ] && [ ! -e .venv/bin/python ] || return 0
  mkdir -p .venv/bin
  printf '#!/bin/sh\nPYTHONUTF8=1 PYTHONIOENCODING=utf-8 exec "$(dirname "$0")/../Scripts/python.exe" "$@"\n' > .venv/bin/python
  chmod +x .venv/bin/python
}
# One deps run per library at a time (#23): two sessions sharing a library would otherwise half-install, or remove,
# each other's packages. A lock folder holds the run's pid; a lock whose run is gone is taken over.
lock_deps() {
  lock=$LIB/.lemo-deps.lock; n=0
  until mkdir "$lock" 2>/dev/null; do
    p=$(cat "$lock/pid" 2>/dev/null || true)
    if [ -n "$p" ] && ! kill -0 "$p" 2>/dev/null; then rm -rf "$lock"; continue; fi
    [ $n -gt 0 ] || echo "… another '$1 deps' is installing into $LIB; waiting for it to finish"
    n=$((n + 1)); [ $n -lt 1800 ] || { echo "✗ $lock is still there after 30 minutes: remove it if no install is running"; exit 1; }
    sleep 1
  done
  echo $$ > "$lock/pid"
  trap 'rm -rf "$lock"' EXIT; trap 'exit 1' INT TERM HUP
}

case "$action" in
  deps)
    tiers=core
    for t in "$@"; do case $t in voice|music) tiers="$tiers $t" ;; *) echo "usage: sh setup.sh deps [voice] [music]"; exit 1 ;; esac; done
    cd "$LIB"; lock_deps "sh setup.sh"
    command -v npm >/dev/null || { echo "✗ npm not found: install Node 20+ first"; exit 1; }
    if ! node_ok; then
      npm install --no-audit --no-fund --loglevel=error
      sig package.json package-lock.json > node_modules/.lemo-ok
    fi
    node node_modules/playwright-core/cli.js install chromium-headless-shell   # the renderer's browser (a no-op when present)
    # a venv whose Python is gone (after a Python upgrade) can't be repaired in place: make it again
    win_shim
    [ ! -e .venv ] || .venv/bin/python -c pass 2>/dev/null || { echo "! $LIB/.venv is broken; making it again"; rm -rf .venv; }
    if [ ! -x .venv/bin/python ]; then
      if command -v uv >/dev/null; then uv venv --quiet --python 3.12 .venv
      else py=$(find_py) || { echo "✗ Python 3.11+ is needed (or install uv, which fetches it)"; exit 1; }; "$py" -m venv .venv; fi
      win_shim
    fi
    # uv is a native program: on Windows it needs the venv's Scripts/python.exe, not a bin/python meant for sh
    upy=.venv/bin/python; [ ! -f .venv/Scripts/python.exe ] || upy=.venv/Scripts/python.exe
    for t in $tiers; do
      py_ok "$t" && continue
      if command -v uv >/dev/null; then uv pip install --quiet --python "$upy" -r "$(req "$t")"
      else .venv/bin/python -m pip install --quiet --disable-pip-version-check -r "$(req "$t")"; fi
      pysig "$(req "$t")" > ".venv/.lemo-$t"
    done
    case " $tiers " in *" voice "*) [ -f core/tts/kokoro-v1.0.onnx ] && [ -f core/tts/voices-v1.0.bin ] || sh tools/fetch.sh voice ;; esac
    ;;
  demo)
    [ -n "$2" ] && [ -f "$LIB/styles/$2/STYLE.md" ] || { echo "usage: sh setup.sh demo <slug>  (slugs: $LIB/styles/README.md)"; exit 1; }
    if git -C "$LIB" sparse-checkout list >/dev/null 2>&1 && ! git -C "$LIB" sparse-checkout list | grep -qx "/styles/$2/demo/"; then
      sparse add "/styles/$2/demo/" "/styles/$2/poster.jpg"
    fi
    echo "demo source: $LIB/styles/$2/demo"
    echo "demo poster: $LIB/styles/$2/poster.jpg"
    ;;
esac

# 2. Tools the pipeline needs (report only; installing them is up to the user)
miss=""
if command -v node >/dev/null; then
  [ "$(node -p 'process.versions.node.split(".")[0]')" -ge 20 ] || miss="$miss node20+(found $(node -v))"
else miss="$miss node20+"; fi
if command -v ffmpeg >/dev/null; then
  ffv=$(ffmpeg -version 2>/dev/null | sed -n '1s/^ffmpeg version n\{0,1\}\([0-9][0-9]*\)\..*/\1/p')
  [ -z "$ffv" ] || [ "$ffv" -ge 7 ] || miss="$miss ffmpeg7+(found $ffv.x)"
else miss="$miss ffmpeg"; fi
command -v uv >/dev/null || find_py >/dev/null || miss="$miss python3.11+(or uv)"
[ -n "$miss" ] && echo "! missing:$miss"
# packages never installed, or installed from a package.json or requirements file that has changed since (a marker is there)
if ! { node_ok && py_ok core; }; then
  if [ -f "$LIB/node_modules/.lemo-ok" ] || [ -f "$LIB/.venv/.lemo-core" ]; then
    echo "! packages changed: run 'sh setup.sh deps' to update them before the next render"
  else echo "! packages not installed yet: run 'sh setup.sh deps' (a few minutes) before the first render"; fi
fi
# Package tiers: core renders; voice (TTS + speech check) and music (pluck.py) are added when a film needs them
mark() { if "$@"; then printf '✓'; else printf '✗'; fi; }
core_ok() { node_ok && py_ok core; }
voice_ok() { py_ok voice && [ -f "$LIB/core/tts/kokoro-v1.0.onnx" ] && [ -f "$LIB/core/tts/voices-v1.0.bin" ]; }
add=""; voice_ok || add="$add voice"; py_ok music || add="$add music"
tline="packages: core $(mark core_ok) · voice $(mark voice_ok) · music $(mark py_ok music)"
core_ok && [ -n "$add" ] && tline="$tline  (when a film needs them: sh setup.sh deps$add)"
echo "$tline"
echo "LIB=$LIB"
