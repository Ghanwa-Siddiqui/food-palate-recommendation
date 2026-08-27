"""Deterministic, local-only food imagery for the Jinja application."""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

IMAGE_DIR = Path(__file__).parent / "static" / "images"
MANIFEST_PATH = IMAGE_DIR / "image-manifest.json"
STATIC_PREFIX = "/static/images/"


def normalize_image_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


@lru_cache(maxsize=1)
def _manifest() -> dict[str, Any]:
    with MANIFEST_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _asset(filename: str) -> dict[str, Any]:
    assets = _manifest()["assets"]
    selected = assets.get(filename) or assets[_manifest()["fallback"]]
    return {
        "src": f"{STATIC_PREFIX}{selected['local_filename']}",
        "alt": selected["alt"],
        "width": selected["width"],
        "height": selected["height"],
    }


def valid_local_image(value: str | None) -> bool:
    """Accept only known, present local image paths; never remote or traversed paths."""
    if not value or not value.startswith(STATIC_PREFIX):
        return False
    filename = value.removeprefix(STATIC_PREFIX)
    if "/" in filename or "\\" in filename or filename not in _manifest()["assets"]:
        return False
    return (IMAGE_DIR / filename).is_file()


def dish_image(
    name: str | None,
    cuisine: str | None = None,
    persisted_image: str | None = None,
) -> dict[str, Any]:
    """Resolve persisted local metadata, exact dish, alias, cuisine, then neutral."""
    if valid_local_image(persisted_image):
        return _asset(persisted_image.removeprefix(STATIC_PREFIX))
    manifest = _manifest()
    key = normalize_image_key(name)
    filename = manifest["dish_exact"].get(key)
    if filename is None:
        filename = manifest["dish_aliases"].get(key)
    if filename is None:
        filename = manifest["cuisine_fallbacks"].get(normalize_image_key(cuisine))
    return _asset(filename or manifest["fallback"])


def cuisine_image(cuisine: str | None) -> dict[str, Any]:
    manifest = _manifest()
    filename = manifest["cuisine_fallbacks"].get(normalize_image_key(cuisine))
    return _asset(filename or manifest["fallback"])


def restaurant_image(
    identity: object | None, persisted_image: str | None = None
) -> dict[str, Any]:
    if valid_local_image(persisted_image):
        return _asset(persisted_image.removeprefix(STATIC_PREFIX))
    choices = _manifest()["restaurant_fallbacks"]
    digest = hashlib.sha256(str(identity or "restaurant").encode()).digest()
    return _asset(choices[digest[0] % len(choices)])


def context_image(context: str) -> dict[str, Any]:
    manifest = _manifest()
    return _asset(
        manifest["contexts"].get(normalize_image_key(context), manifest["fallback"])
    )


def fallback_image() -> dict[str, Any]:
    return _asset(_manifest()["fallback"])
