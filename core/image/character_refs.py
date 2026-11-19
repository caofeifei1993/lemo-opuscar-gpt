"""Register and verify a film's reusable native image references for recurring characters."""
import hashlib
import json
from pathlib import Path
import tempfile

from image_paths import validate_name


DIRECTORY = Path("assets/characters")


def paths(project, identifier):
    validate_name(identifier)
    folder = project / DIRECTORY
    if not folder.resolve().is_relative_to(project):
        raise ValueError("character reference directory points outside the film")
    png = folder / (identifier + ".png")
    record = png.with_suffix(".json")
    for path in (png, record):
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError(f"unexpected character reference entry: {path.name}")
    return png, record


def register(project, identifier, description, source):
    """Publish an independent PNG and its immutable identity record. Matching retries are safe."""
    # Planning and listing use the standard library. Only importing a master needs Pillow.
    from save_asset import checksum, copy_input, normalize_png, publish

    description = description.strip()
    if not description:
        raise ValueError("describe the character's stable appearance")
    png, record = paths(project, identifier)
    if png.exists() and not record.exists():
        raise ValueError(f"{png.name} already exists without a character record; choose a new ID")
    source = project / source
    if not source.is_file():
        raise ValueError(f"character {identifier}: reference image is missing: {source}")
    png.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".register-", dir=png.parent) as tmp:
        raw, image, metadata = (Path(tmp) / n for n in ("source", "master.png", "identity.json"))
        with source.open("rb") as stream:
            copy_input(stream, raw)
        normalize_png(raw, image, None)
        identity = {"id": identifier, "description": description, "reference": png.relative_to(project).as_posix(),
                    "sha256": checksum(image)}
        metadata.write_text(json.dumps(identity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        publish(png, record, image, metadata, identity)
    return identity


def load_character(project, identifier):
    png, record = paths(project, identifier)
    if not record.is_file() or not png.is_file():
        raise ValueError(f"character {identifier}: register the master image first")
    identity = json.loads(record.read_text(encoding="utf-8"))
    if (not isinstance(identity, dict) or identity.get("id") != identifier
            or not isinstance(identity.get("description"), str) or not identity["description"].strip()
            or identity.get("reference") != png.relative_to(project).as_posix()):
        raise ValueError(f"character {identifier}: invalid identity record")
    with png.open("rb") as master:
        if hashlib.file_digest(master, "sha256").hexdigest() != identity.get("sha256"):
            raise ValueError(f"character {identifier}: master image differs from its registered digest")
    return identity


def list_characters(project):
    folder = project / DIRECTORY
    if not folder.resolve().is_relative_to(project):
        raise ValueError("character reference directory points outside the film")
    return [load_character(project, item.stem) for item in sorted(folder.glob("*.json"))]


def identity_prompt(characters):
    lines = ["Use the following reference images to keep each character recognizable across shots.",
             "Keep each character's identity and defining features. Follow the shot prompt for pose, framing and setting."]
    for index, character in enumerate(characters, 1):
        lines.append(f"Reference {index} — {character['id']}: {character['description']}")
    return "\n".join(lines)
