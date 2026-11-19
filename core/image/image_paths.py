"""Shared local naming and framing rules for generated film images."""
import math
from pathlib import Path
import re


OUTPUT_DIRS = {"illustration": Path("assets/illustrations"), "storyboard": Path("storyboard/images")}


def validate_name(name):
    if not re.fullmatch(r"[\w-]+", name) or name in {"-", "_"} or len(name.encode()) > 220:
        raise ValueError("name must be a filename stem using letters, numbers, underscores or hyphens")
    if re.fullmatch(r"(CON|AUX|NUL|PRN|COM[1-9]|LPT[1-9])", name, re.I):
        raise ValueError("name is a reserved device name")
    return name


def parse_aspect(text):
    try:
        width, height = map(float, text.split(":"))
        ratio = width / height
        if width > 0 and height > 0 and math.isfinite(ratio) and ratio > 0:
            return ratio
    except (ValueError, ZeroDivisionError):
        pass
    raise ValueError("aspect must be a positive width:height, e.g. 16:9")
