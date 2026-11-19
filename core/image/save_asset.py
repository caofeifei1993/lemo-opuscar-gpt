#!/usr/bin/env python3
"""Import one completed image generation into a film as a verified PNG and JSON receipt.

Run with the project's core Python environment (requires Pillow). For OpenArt URLs,
the caller must select the original image resource from the completed host job.
"""
import argparse
import hashlib
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler
import warnings

try:
    from PIL import Image, ImageOps
except ImportError:
    raise SystemExit("save_asset: Pillow is required; use the library's .venv/bin/python after setup.sh deps")

from image_paths import OUTPUT_DIRS, parse_aspect, validate_name


MAX_INPUT_BYTES = 128 * 1024 * 1024


def check_aspect(size, wanted):
    if wanted and abs(size[0] / size[1] / wanted - 1) > 0.0500000001:
        raise ValueError(f"image is {size[0]}x{size[1]}, outside the requested aspect tolerance (5%)")


def check_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("use the HTTPS image resource URL returned for the completed job")


class HTTPSRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def copy_input(stream, dest):
    total = 0
    with dest.open("wb") as output:
        while chunk := stream.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_INPUT_BYTES:
                raise ValueError("image exceeds the 128 MiB input limit")
            output.write(chunk)


def get_source(args, dest):
    if args.url:
        try:
            with build_opener(HTTPSRedirect()).open(args.url, timeout=60) as response:
                copy_input(response, dest)
        except HTTPError as error:
            raise ValueError(f"image download returned HTTP {error.code}; check the completed resource") from None
        except (URLError, HTTPException, OSError, ValueError) as error:
            # The transport exception can contain the entire signed URL.
            raise ValueError(f"image download failed ({type(error).__name__}); check the completed resource") from None
    elif args.stdin:
        copy_input(sys.stdin.buffer, dest)
    else:
        with args.file.open("rb") as source:
            copy_input(source, dest)


def normalize_png(source, output, aspect):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source, formats=("PNG", "JPEG", "WEBP", "GIF")) as probe:
                probe.verify()
            with Image.open(source) as original:
                if getattr(original, "n_frames", 1) != 1:
                    raise ValueError("expected one still image, got an animated image")
                original.load()
                oriented = ImageOps.exif_transpose(original)
                check_aspect(oriented.size, aspect)
                alpha = "A" in oriented.getbands() or "transparency" in oriented.info
                image = oriented.convert("RGBA" if alpha else "RGB")
                image.info.clear()
                image.save(output, format="PNG")
                return image.size
    except (OSError, SyntaxError, EOFError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise ValueError("could not decode a complete PNG, JPEG, WebP or static GIF") from None


def checksum(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def target_paths(project, kind, name):
    validate_name(name)
    if not project.is_dir():
        raise ValueError("film project directory does not exist")
    folder = project / OUTPUT_DIRS[kind]
    if not folder.resolve().is_relative_to(project):
        raise ValueError("output directory points outside the film project")
    folder.mkdir(parents=True, exist_ok=True)
    png, receipt = folder / (name + ".png"), folder / (name + ".json")
    for path in (png, receipt):
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError(f"unexpected entry at {path.name}; choose a fresh name")
    return png, receipt


def read_receipt(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError):
        raise ValueError(f"unreadable receipt {path.name}; original files preserved") from None
    if not isinstance(data, dict):
        raise ValueError(f"invalid receipt {path.name}; original files preserved")
    return data


def publish(png, receipt, temp_png, temp_json, record):
    # Link a complete receipt first as an exclusive claim. A retry with matching
    # provenance can finish the second link after an interruption, even with
    # concurrent writers. Existing files are never replaced.
    try:
        os.link(temp_json, receipt)
    except FileExistsError:
        if receipt.is_symlink() or read_receipt(receipt) != record:
            raise ValueError(f"name already taken: {png.name}; choose a different stem")
    try:
        os.link(temp_png, png)
        return "saved"
    except FileExistsError:
        if png.is_symlink() or checksum(png) != record["sha256"]:
            raise ValueError(f"existing {png.name} differs from the result; files preserved")
        return "reused"


def save(args):
    if args.provider == "openart" and not args.model:
        raise ValueError("specify the OpenArt model ID from the completed generation")
    if args.url is not None:
        check_url(args.url)
        if args.provider != "openart" or not (args.history_id and args.resource_id):
            raise ValueError("--url needs OpenArt's completed --history-id and --resource-id")
    for identifier in (args.model, args.history_id, args.resource_id):
        if identifier is not None and (not re.fullmatch(r"[\w./:-]{1,256}", identifier) or "//" in identifier):
            raise ValueError("expected a model or resource identifier, not a URL")
    project = args.project.resolve()
    png, receipt = target_paths(project, args.kind, args.name)
    identity = {"schema_version": 1, "kind": args.kind, "provider": args.provider,
                "model": args.model or "auto", "path": png.relative_to(project).as_posix()}
    if args.history_id:
        identity["history_id"] = args.history_id
    if args.resource_id:
        identity["resource_id"] = args.resource_id
    if png.exists() and not receipt.exists():
        raise ValueError(f"existing {png.name} has no receipt; choose a different stem")
    if args.url and png.exists() and receipt.exists():
        previous = read_receipt(receipt)
        if any(previous.get(k) != v for k, v in identity.items()):
            raise ValueError(f"name already taken: {png.name}; choose a different stem")
        if checksum(png) != previous.get("sha256"):
            raise ValueError(f"existing {png.name} differs from its receipt; files preserved")
        # A completed OpenArt resource ID identifies one image. Reuse the verified
        # local copy even after its signed URL expires.
        with Image.open(png, formats=("PNG",)) as existing:
            if existing.size != (previous.get("width"), previous.get("height")):
                raise ValueError(f"dimensions disagree with {receipt.name}")
            check_aspect(existing.size, args.aspect)
        return {"status": "reused", "path": str(png), "metadata": str(receipt),
                "width": previous["width"], "height": previous["height"], "sha256": previous["sha256"]}

    with tempfile.TemporaryDirectory(prefix=".import-", dir=png.parent) as work:
        stage = Path(work)
        raw, normalized, staged_receipt = stage / "input", stage / "image.png", stage / "receipt.json"
        get_source(args, raw)
        width, height = normalize_png(raw, normalized, args.aspect)
        record = dict(identity, width=width, height=height, sha256=checksum(normalized))
        staged_receipt.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        status = publish(png, receipt, normalized, staged_receipt, record)
    return {"status": status, "path": str(png), "metadata": str(receipt), "width": width,
            "height": height, "sha256": record["sha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--kind", required=True, choices=OUTPUT_DIRS)
    parser.add_argument("--name", required=True)
    parser.add_argument("--provider", required=True, choices=("native", "openart"))
    parser.add_argument("--model")
    parser.add_argument("--history-id")
    parser.add_argument("--resource-id")
    parser.add_argument("--aspect", type=parse_aspect)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path)
    source.add_argument("--stdin", action="store_true", help="read original image bytes")
    source.add_argument("--url", help="HTTPS original image URL from a completed OpenArt resource")
    args = parser.parse_args()
    try:
        print(json.dumps(save(args), ensure_ascii=False))
    except (ValueError, OSError) as error:
        print(f"save_asset: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
