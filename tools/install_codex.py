#!/usr/bin/env python3
"""Register this local library as a Codex skill without copying or replacing files."""

import argparse
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest", type=Path,
        default=Path.home() / ".agents" / "skills" / "lemo-opuscar",
        help="Full destination skill directory (default: ~/.agents/skills/lemo-opuscar)",
    )
    args = parser.parse_args()
    library = Path(__file__).resolve().parents[1]
    source = library / "plugin" / "skills" / "lemo-opuscar"
    if not (source / "SKILL.md").is_file() or not (library / "core" / "render").is_dir():
        parser.error("Run the installer from an intact lemo-opuscar-gpt checkout.")
    destination = args.dest.expanduser().absolute()
    if destination.is_symlink() and destination.resolve() == source:
        print(f"Already installed: {destination} -> {source}")
        return 0
    if destination.exists() or destination.is_symlink():
        print(f"Refusing to replace existing path: {destination}", file=sys.stderr)
        return 1
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.symlink_to(source, target_is_directory=True)
    except OSError as exc:
        print(f"Could not install the skill: {exc}", file=sys.stderr)
        return 1
    print(f"Installed: {destination} -> {source}")
    print("Open a new Codex chat; select lemo-opuscar or mention $lemo-opuscar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
