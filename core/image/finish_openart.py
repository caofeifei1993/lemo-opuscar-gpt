#!/usr/bin/env python3
"""Import the original image from a completed, previously submitted OpenArt job."""
import argparse
import json
from pathlib import Path
import sys

from image_paths import OUTPUT_DIRS, parse_aspect
from image_route import job_files, read
from save_asset import check_url, save


def selected_image(raw, submission, resource_id):
    if not isinstance(raw, dict) or raw.get("isError"):
        raise ValueError("expected a successful OpenArt tool result")
    result = raw.get("structuredContent", raw)
    if not isinstance(result, dict) or result.get("status") != "COMPLETED":
        raise ValueError("OpenArt has not reported a completed creation")
    if result.get("warning") or result.get("error"):
        raise ValueError("OpenArt reported an incomplete or failed result; inspect the job in the host")
    if result.get("historyId") != submission["historyId"]:
        raise ValueError("completion historyId differs from the recorded submission")
    # creation_get may expose {modelId}:{capabilityKey}; modelDisplayName is a
    # human-readable label, not the model ID. Submit responses can omit both.
    capability = result.get("capabilityId")
    if capability is not None:
        if not isinstance(capability, str) or not capability.startswith(submission["model"] + ":"):
            raise ValueError("OpenArt capabilityId does not match the submitted model")
    if "model" in result and result["model"] != submission["model"]:
        raise ValueError("OpenArt model does not match the submitted model")

    resources = result.get("resources")
    if not isinstance(resources, list) or not resources or not all(isinstance(r, dict) for r in resources):
        raise ValueError("completion contains no usable resource list")
    if result.get("resourceCount", len(resources)) != len(resources):
        raise ValueError("OpenArt has not returned all expected resource slots")
    if resource_id is None and len(resources) != 1:
        raise ValueError("completion has multiple resources; specify the chosen --resource-id")
    matches = [r for r in resources if resource_id is None or r.get("id") == resource_id]
    if len(matches) != 1:
        raise ValueError("resource ID must identify exactly one image in this completion")
    item = matches[0]
    if item.get("mediaType") != "image" or not isinstance(item.get("id"), str) or not item["id"].strip():
        raise ValueError("selected OpenArt resource is not an identified image")
    status = item.get("status")
    if item.get("error") or (status is not None and str(status).upper() not in
                             {"COMPLETED", "SUCCESS", "SUCCEEDED", "READY", "FINISHED", "DONE"}):
        raise ValueError("OpenArt has not reported a successful selected resource")
    if not isinstance(item.get("url"), str):
        raise ValueError("completed image has no original resource URL")
    check_url(item["url"])
    return item


def finish(args, raw):
    project = args.project.resolve(strict=True)
    plan_path, submit_path = job_files(project, args)
    plan, submission = read(plan_path), read(submit_path)
    if (not isinstance(plan, dict) or plan.get("provider") != "openart"
            or plan.get("kind") != args.kind or plan.get("name") != args.name):
        raise ValueError("expected a saved OpenArt plan for this asset")
    if not isinstance(submission, dict) or not all(isinstance(submission.get(k), str) and submission[k].strip()
                                                  for k in ("model", "historyId")):
        raise ValueError("first record the resolved model and historyId using image_route.py submitted")
    image = selected_image(raw, submission, args.resource_id)
    return save(argparse.Namespace(project=project, kind=args.kind, name=args.name, provider="openart",
                                   model=submission["model"], history_id=submission["historyId"],
                                   resource_id=image["id"], aspect=parse_aspect(plan["aspect"]) if plan.get("aspect") else None,
                                   url=image["url"], stdin=False, file=None))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--kind", required=True, choices=OUTPUT_DIRS)
    parser.add_argument("--name", required=True)
    parser.add_argument("--result", required=True, help="tool result as JSON, or '-' to read from stdin")
    parser.add_argument("--resource-id", help="choose an image when the job returned several")
    args = parser.parse_args()
    try:
        raw = json.load(sys.stdin) if args.result == "-" else read(Path(args.result))
        print(json.dumps(finish(args, raw), ensure_ascii=False))
    except (OSError, ValueError) as error:
        parser.exit(1, f"finish_openart: {error}\n")


if __name__ == "__main__":
    main()
