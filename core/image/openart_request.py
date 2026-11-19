#!/usr/bin/env python3
"""Prepare OpenArt host calls from live model, form and price responses. No network or credentials."""
import argparse
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def object_value(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def call(name, arguments):
    return {"toolName": "openart_" + name, "arguments": arguments}


def resolve(plan, catalog):
    """Use an exact ID or an unambiguous full display name; never guess a paid model."""
    object_value(plan, "plan")
    object_value(catalog, "catalog")
    choice, mode = plan.get("model"), plan.get("mode")
    if plan.get("provider") != "openart" or not isinstance(choice, str) or not choice.strip():
        raise ValueError("select an OpenArt provider and model in the film plan")
    if mode not in ("text2image", "image2image"):
        raise ValueError("expected an image plan with mode text2image or image2image")
    models = catalog.get("models")
    if not isinstance(models, list) or not all(isinstance(m, dict) for m in models):
        raise ValueError("catalog needs the current model_list structuredContent")
    matches = [m for m in models if m.get("id") == choice]
    if not matches:
        matches = [m for m in models if isinstance(m.get("displayName"), str)
                   and m["displayName"].casefold() == choice.casefold()]
    if len(matches) != 1:
        raise ValueError(f"model {choice!r} is missing or ambiguous; choose an exact ID from model_list")
    model = matches[0]
    image_modes = object_value(model.get("modes"), "model modes").get("image", [])
    options = [m for m in image_modes if isinstance(m, dict) and m.get("mode") == mode]
    if len(options) != 1 or not isinstance(model.get("id"), str):
        raise ValueError(f"{choice!r} does not advertise {mode} in its image modes")
    args = {"model": model["id"], "mode": mode}
    return {**args, "default_credits": options[0].get("totalCredits"),
            "default_affordable": options[0].get("affordable"), "form": call("model_form_get", args)}


def references(raw):
    """Accept imported reference records or verified visualReferences/handles from the host."""
    if isinstance(raw, dict):
        results = raw.get("results")
        if not isinstance(results, list) or not all(isinstance(r, dict) and r.get("status") == "SUCCESS"
                                                    for r in results):
            raise ValueError("all attached images must be imported successfully and in order")
        raw = [r.get("visualReference") for r in results]
    if not isinstance(raw, list):
        raise ValueError("--refs needs the upload_import result or an ordered visualReference array")
    clean = []
    for item in raw:
        object_value(item, "reference")
        if item.get("type") != "image":
            raise ValueError("use accepted image references for illustration/storyboard image2image")
        for key in ("id", "label"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError(f"OpenArt reference is missing {key}")
        ref = {k: item[k] for k in ("type", "id", "label")}
        if not re.fullmatch(r"(upload|resource):[A-Za-z0-9_-]+", ref["id"]):
            url = item.get("url")
            parts = urlsplit(url) if isinstance(url, str) else None
            if not parts or parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
                raise ValueError("use an OpenArt handle or the HTTPS visualReference from the host")
            ref["url"] = url
        clean.append(ref)
    return clean


def validate_value(value, field, name):
    """Check the scalar, enum and length/range constraints used by live image forms."""
    types = {"string": (str,), "integer": (int,), "number": (int, float),
             "boolean": (bool,), "array": (list,)}
    kind = field.get("type")
    if kind not in types or type(value) not in types[kind]:
        raise ValueError(f"{name} must match form type {kind}")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if ("enum" in field and value not in field["enum"]) or ("const" in field and value != field["const"]):
        raise ValueError(f"{name} is outside the choices from model_form_get")
    if isinstance(value, (str, list)):
        lower, upper = ("minLength", "maxLength") if isinstance(value, str) else ("minItems", "maxItems")
        if len(value) < field.get(lower, 0) or len(value) > field.get(upper, math.inf):
            raise ValueError(f"{name} length is outside the live form limits")
    if type(value) in (int, float):
        if (value < field.get("minimum", -math.inf) or value > field.get("maximum", math.inf)
                or value <= field.get("exclusiveMinimum", -math.inf) or value >= field.get("exclusiveMaximum", math.inf)):
            raise ValueError(f"{name} is outside the live form limits")


def check_quote(quote, request):
    object_value(quote, "quote")
    items = quote.get("items")
    if quote.get("currency") != "credits" or not isinstance(items, list) or len(items) != 1:
        raise ValueError("get a fresh model_cost quote for this one configuration")
    item = object_value(items[0], "quoted item")
    if any(item.get(k) != request[k] for k in ("model", "mode")) or item.get("mediaType") != "image":
        raise ValueError("cost quote belongs to another model, mode or medium")
    if item.get("quantity") != 1:
        raise ValueError("expected a quote for one output image")
    price = item.get("totalCredits")
    if type(price) not in (float, int) or not math.isfinite(price) or price < 0:
        raise ValueError("cost quote does not contain a valid price")
    if item.get("affordable") is not True:
        balance = quote.get("balance", "unknown")
        raise ValueError(f"OpenArt has not confirmed sufficient credits for this {price}-credit job "
                         f"(balance: {balance}). " + str(quote.get("upgradeUrl", "")))
    # model_cost echoes billable options, not necessarily prompt, references or every form field.
    # Both invocations must use the same plan, form, params and bindings from this transaction.
    config = object_value(item.get("config"), "quoted config")
    if any(config[k] != request["params"][k] for k in config.keys() & request["params"].keys()):
        raise ValueError("configuration changed after pricing; get a fresh quote")
    return price


def prepare(plan, catalog, form, overrides=None, refs=None, quote=None):
    recipe = resolve(plan, catalog)
    resource = {k: recipe[k] for k in ("model", "mode")}
    object_value(form, "form")
    if form.get("media") != "image" or any(resource[k] != form.get(k) for k in resource):
        raise ValueError("form does not match the selected image model and mode")
    schema = object_value(form.get("jsonSchema"), "form jsonSchema")
    fields = object_value(schema.get("properties"), "form properties")
    params = {} if overrides is None else dict(object_value(overrides, "params"))
    if set(params) & {"prompt", "aspectRatio", "visualReferences", "model", "projectId"}:
        raise ValueError("set the prompt, aspect and references through the plan and host bindings")
    if (params.get("imageCount", 1) != 1 or params.get("resultType", "single") != "single"
            or params.get("format") == "vector" or params.get("outputFormat") in ("svg", "gif")):
        raise ValueError("each named film asset needs a single still raster image")
    params["prompt"] = plan.get("prompt")
    if not isinstance(params["prompt"], str) or not params["prompt"].strip():
        raise ValueError("plan needs a prompt")
    if plan.get("aspect") is not None:
        if params.get("lockAspectRatio") is False or {"customWidth", "customHeight"} & params.keys():
            raise ValueError("custom sizing conflicts with the planned aspect; use one sizing method")
        params["aspectRatio"] = plan["aspect"]
    if resource["mode"] == "image2image":
        bound = references(refs)
        if not bound or ("reference_count" in plan and plan["reference_count"] != len(bound)):
            raise ValueError("bind every planned reference image, in order")
        params["visualReferences"] = bound
    elif refs is not None or plan.get("reference_count", 0) != 0:
        raise ValueError("text2image cannot use reference images")
    for key, value in params.items():
        if key not in fields:
            raise ValueError(f"{recipe['model']} {recipe['mode']} does not support {key} in the current form")
        validate_value(value, fields[key], key)
    missing = set(schema.get("required", [])) - params.keys()
    if missing:
        raise ValueError("form requires " + ", ".join(sorted(missing)))
    request = {**resource, "params": params}
    recipe["cost"] = call("model_cost", request)
    if quote is not None:
        recipe["credits"] = check_quote(quote, request)
        recipe["generate"] = call("generate_image", request)
    return recipe


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--catalog", required=True, help="structuredContent from openart_model_list")
    parser.add_argument("--resolve-only", action="store_true")
    parser.add_argument("--form", help="structuredContent from the selected model_form_get")
    parser.add_argument("--refs", help="ordered host-bound references or upload_import structuredContent")
    parser.add_argument("--params", help="additional live form options")
    parser.add_argument("--quote", help="fresh model_cost structuredContent for the exact cost arguments")
    a = parser.parse_args(argv)
    try:
        plan, catalog = read_json(a.plan), read_json(a.catalog)
        if a.resolve_only:
            if any((a.form, a.refs, a.params, a.quote)):
                parser.error("--resolve-only takes --plan and --catalog only")
            result = resolve(plan, catalog)
        else:
            if not a.form:
                parser.error("provide --form or use --resolve-only")
            result = prepare(plan, catalog, read_json(a.form),
                             read_json(a.params) if a.params else None,
                             read_json(a.refs) if a.refs else None,
                             read_json(a.quote) if a.quote else None)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except (OSError, ValueError) as e:
        print(f"openart_request: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
