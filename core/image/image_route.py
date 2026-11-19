#!/usr/bin/env python3
"""Choose image providers per film, plan host tool calls and remember submitted OpenArt jobs."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from character_refs import identity_prompt, list_characters, load_character, register
from image_paths import OUTPUT_DIRS, parse_aspect, validate_name


KINDS = tuple(OUTPUT_DIRS)
NATIVE_AUTO = {"provider": "native", "model": "auto"}
DEFAULT = {**NATIVE_AUTO, "preferred_model": "GPT Image 2.6 Sunburst"}


def project_path(project, relative):
    path = project / relative
    if path.is_symlink() or not path.resolve().is_relative_to(project):
        raise ValueError(f"unexpected project path: {relative}")
    return path


def read(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def write(path, data, *, replace=False):
    """Publish a complete file. Concurrent identical immutable records can be reused."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", delete=False) as f:
        tmp = Path(f.name)
        try:
            json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")
        except BaseException:
            f.close()
            tmp.unlink(missing_ok=True)
            raise
    try:
        if replace:
            tmp.replace(path)
        else:
            try:
                os.link(tmp, path)
            except FileExistsError:
                if read(path) != data:
                    raise ValueError(f"{path.name} already records a different request; use a new asset name") from None
    finally:
        tmp.unlink(missing_ok=True)


def selection(provider, model, preferred_model=None):
    if preferred_model is not None:
        if provider != "native" or not isinstance(preferred_model, str) or not preferred_model.strip():
            raise ValueError("a native model preference must be a non-empty name")
    if provider == "native" and model in (None, "auto"):
        choice = NATIVE_AUTO.copy()
        if preferred_model is not None:
            choice["preferred_model"] = preferred_model.strip()
        return choice
    if provider == "openart" and isinstance(model, str) and model.strip() and model.strip().lower() != "auto":
        return {"provider": provider, "model": model.strip()}
    if provider == "native":
        raise ValueError("ChatGPT native cannot select or confirm a specific model. Use --prefer-model to record a preference, or --model auto for host selection.")
    raise ValueError("OpenArt needs a specific image model from the live catalog")


def settings(path):
    config = {"version": 1, **{kind: DEFAULT.copy() for kind in KINDS}}
    if path.exists():
        saved = read(path)
        if not isinstance(saved, dict) or saved.get("version") != 1 or saved.keys() - config.keys():
            raise ValueError("invalid image-providers.json")
        for kind in KINDS:
            if kind in saved:
                item = saved[kind]
                if not isinstance(item, dict) or item.keys() - {"provider", "model", "preferred_model"}:
                    raise ValueError(f"invalid {kind} provider settings")
                config[kind] = selection(item.get("provider"), item.get("model"), item.get("preferred_model"))
    return config


@contextmanager
def config_lock(project):
    lock = project_path(project, ".image-providers.lock")
    try:
        lock.touch(exist_ok=False)
    except FileExistsError:
        raise ValueError("image configuration is being edited; retry after the active configure command exits") from None
    try:
        yield
    finally:
        lock.unlink()


def make_plan(a, project, choice):
    name = validate_name(a.name)
    if a.prompt_file:
        prompt = Path(a.prompt_file).read_text(encoding="utf-8")
    else:
        prompt = a.prompt
    if not prompt.strip():
        raise ValueError("prompt must contain text")
    if a.aspect:
        parse_aspect(a.aspect)
    plan = {"version": 1, **choice, "kind": a.kind, "name": name, "prompt": prompt,
            "aspect": a.aspect, "destination": (OUTPUT_DIRS[a.kind] / (name + ".png")).as_posix()}
    project_path(project, plan["destination"])
    if a.character:
        if choice["provider"] != "native":
            raise ValueError("--character binds local master images on the native route; OpenArt needs host-bound references")
        if a.recent_images is not None:
            raise ValueError("use local --ref files for other images when including a --character master")
        if len(set(a.character)) != len(a.character):
            raise ValueError("include each --character ID only once per shot")
        plan["characters"] = [load_character(project, identifier) for identifier in a.character]
    if choice["provider"] == "native":
        if a.reference_count is not None:
            raise ValueError("for native references use --ref or --recent-images")
        if a.recent_images is not None and not 1 <= a.recent_images <= 5:
            raise ValueError("--recent-images must be between 1 and 5")
        args = {"prompt": (f"Frame the image at {a.aspect} (width:height).\n" if a.aspect else "") + prompt}
        characters = plan.get("characters", [])
        paths = [(project / character["reference"]).resolve(strict=True) for character in characters]
        if characters:
            args["prompt"] += "\n\n" + identity_prompt(characters)
        if a.ref or paths:
            paths.extend((project / f).resolve(strict=True) for f in a.ref or [])
            if not all(p.is_file() for p in paths):
                raise ValueError("reference inputs must be image files")
            args["referenced_image_paths"] = [str(p) for p in paths]
        if a.recent_images:
            args["num_last_images_to_include"] = a.recent_images
        count = len(paths) or a.recent_images or 0
        # Without an explicit edit preference the host preserves reference transparency.
        if not count or a.transparent_background is not None:
            args["transparent_background"] = bool(a.transparent_background)
        plan["call"] = {"toolName": "image_gen.imagegen", "arguments": args}
    else:
        if a.ref or a.recent_images or a.transparent_background is not None:
            raise ValueError("OpenArt uses host-bound references (--reference-count) and its live form settings")
        count = a.reference_count or 0
        if count < 0:
            raise ValueError("--reference-count must not be negative")
        plan["call"] = {"toolName": "openart_model_list", "arguments": {}}
    plan["reference_count"] = count
    plan["mode"] = "image2image" if count else "text2image"
    return plan


def job_files(project, a):
    base = Path(".image-jobs") / a.kind / validate_name(a.name)
    return tuple(project_path(project, base / (n + ".json")) for n in ("plan", "submission"))


def job_status(project, plan, submission):
    """Only a matching receipt and its verified image are a completed asset."""
    submitted = read(submission) if submission.exists() else None
    png = project_path(project, plan["destination"])
    receipt = project_path(project, Path(plan["destination"]).with_suffix(".json"))
    result = {"plan": plan, "submission": submitted, "receipt": None,
              "status": "submitted" if submitted else "planned"}
    if receipt.exists():
        meta = read(receipt)
        if (meta.get("kind") != plan["kind"] or meta.get("provider") != plan["provider"]
                or meta.get("path") != png.relative_to(project).as_posix()):
            raise ValueError("existing receipt belongs to a different asset")
        if plan["provider"] == "openart" and (not submitted or submitted["model"] != meta.get("model")
                                             or submitted["historyId"] != meta.get("history_id")):
            raise ValueError("existing receipt does not match this OpenArt submission")
        if png.is_file():
            with png.open("rb") as source:
                if hashlib.file_digest(source, "sha256").hexdigest() != meta.get("sha256"):
                    raise ValueError("the saved asset differs from its receipt")
            result.update(status="saved", receipt=meta)
    elif png.exists():
        raise ValueError("destination exists without a receipt; choose a fresh asset name")
    if result["status"] == "planned" and plan.get("characters"):
        characters = plan["characters"]
        if any(load_character(project, c["id"]) != c for c in characters):
            raise ValueError("character identity record differs from this saved shot plan")
        # A copied film uses its own masters when a pending native job is resumed.
        paths = plan["call"]["arguments"]["referenced_image_paths"]
        paths[:len(characters)] = [str((project / c["reference"]).resolve(strict=True)) for c in characters]
    return result


def handle(a):
    project = Path(a.project).resolve(strict=True)
    if not project.is_dir():
        raise ValueError("project must be an existing film directory")
    config = project_path(project, "image-providers.json")
    if a.cmd == "configure":
        choice = selection(a.provider, a.model, a.prefer_model)
        if a.provider == "native" and a.model is None and a.prefer_model is None:
            choice = DEFAULT.copy()
        with config_lock(project):
            current = settings(config)
            for kind in KINDS if a.kind == "both" else (a.kind,):
                current[kind] = choice
            write(config, current, replace=True)
        return current
    if a.cmd == "show":
        return settings(config)
    if a.cmd == "character":
        return register(project, a.id, a.description, a.ref)
    if a.cmd == "characters":
        return list_characters(project)
    plan_file, submission = job_files(project, a)
    if a.cmd == "plan":
        plan = make_plan(a, project, settings(config)[a.kind])
        if a.save:
            dest = project_path(project, plan["destination"])
            if not plan_file.exists() and (dest.exists() or dest.with_suffix(".json").exists()):
                raise ValueError("asset name already in use; choose a fresh name")
            if plan_file.exists() and "preferred_model" in plan:
                # Older native plans carried no preference. Preserve their original
                # provenance when the actual host request is otherwise identical.
                previous = read(plan_file)
                if previous == {k: v for k, v in plan.items() if k != "preferred_model"}:
                    return previous
            write(plan_file, plan)
        return plan
    plan = read(plan_file)
    if a.cmd == "submitted":
        if (plan["provider"] != "openart" or not re.fullmatch(r"[\w:-]+", a.history_id)
                or not re.fullmatch(r"[\w.-]+", a.model)):
            raise ValueError("record a real OpenArt history ID and the resolved model ID")
        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", plan["model"]) and plan["model"] != a.model:
            raise ValueError("submitted model ID differs from the chosen model")
        write(submission, {"model": a.model, "historyId": a.history_id})
    return job_status(project, plan, submission)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    cmds = parser.add_subparsers(dest="cmd", required=True)
    for cmd in ("configure", "show", "character", "characters", "plan", "submitted", "status"):
        sub = cmds.add_parser(cmd)
        sub.add_argument("project")
        if cmd in ("show", "characters"):
            continue
        if cmd == "character":
            sub.add_argument("--id", required=True, help="stable character ID shared by this film's shots")
            sub.add_argument("--description", required=True, help="recognizable features to preserve across shots")
            sub.add_argument("--ref", required=True, help="master image file (absolute or relative to PROJECT)")
            continue
        sub.add_argument("--kind", choices=KINDS + (("both",) if cmd == "configure" else ()), required=True)
        if cmd == "configure":
            sub.add_argument("--provider", choices=["native", "openart"], required=True)
            sub.add_argument("--model")
            sub.add_argument("--prefer-model", help="native model preference for the brief; the host selects the actual model")
            continue
        sub.add_argument("--name", required=True)
        if cmd == "submitted":
            sub.add_argument("--model", required=True)
            sub.add_argument("--history-id", required=True)
        if cmd == "plan":
            group = sub.add_mutually_exclusive_group(required=True)
            group.add_argument("--prompt")
            group.add_argument("--prompt-file")
            sub.add_argument("--aspect")
            sub.add_argument("--character", action="append", help="native: repeat once for each registered character in the shot")
            refs = sub.add_mutually_exclusive_group()
            refs.add_argument("--ref", action="append", help="native reference file (absolute or relative to PROJECT)")
            refs.add_argument("--recent-images", type=int, help="native: recent conversation images to include")
            refs.add_argument("--reference-count", type=int, help="OpenArt: number of references to bind through the host")
            sub.add_argument("--transparent-background", action=argparse.BooleanOptionalAction, default=None)
            sub.add_argument("--save", action="store_true", help="retain the plan under .image-jobs for recovery")
    try:
        result = handle(parser.parse_args())
    except (OSError, ValueError) as e:
        parser.exit(1, f"image_route: {e}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
