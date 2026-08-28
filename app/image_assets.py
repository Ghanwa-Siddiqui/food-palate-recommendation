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


# Keyword fallbacks, tried after the exact/alias tables and before the
# per-cuisine fallback. Without this step a menu of "Egg Fried Rice",
# "Chicken Chow Mein" and "Beef Chilli Dry" collapses onto one Chinese
# photograph, because only ~17 dish names are mapped exactly while a live
# menu carries hundreds.
#
# Order is significant: the first tuple containing a matching substring wins,
# so specific dishes are listed before generic ingredients. Each target was
# chosen against the actual photograph, not its filename — e.g.
# sour-citrus-dish is a lemon-dressed fish fillet, and
# continental-grilled-chicken is a plate of red grilled wings.
_DISH_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    # Named South Asian dishes
    (("biryani",), "chicken-biryani.webp"),
    (("nihari",), "nihari.webp"),
    (("haleem",), "haleem.webp"),
    (("karahi", "handi", "makhni", "makhani"), "chicken-karahi.webp"),
    (("pulao", "pilaf", "polao"), "chicken-biryani.webp"),
    (("daal", "dal ", "lentil"), "daal-with-naan.webp"),
    (("naan", "roti", "paratha", "garlic bread"), "daal-with-naan.webp"),
    (("tikka",), "chicken-tikka.webp"),
    (("shawarma", "doner", "donair"), "turkish-kebab.webp"),
    (("seekh", "kabab", "kebab", "shami", "boti"), "seekh-kebab.webp"),
    (("bbq", "barbecue", "tandoori"), "pakistani-bbq-platter.webp"),
    # Far Eastern
    (("sushi", "sashimi", "maki"), "sushi-platter.webp"),
    (("chow mein", "chowmein", "noodle", "ramen", "hakka"), "chinese-noodles.webp"),
    (("fried rice",), "chinese-fried-rice.webp"),
    (("spring roll", "dumpling", "dim sum", "momo", "gyoza"), "crunchy-snacks.webp"),
    # Ahead of the sauce keywords below: "Spicy Honey Chicken Wings" and
    # "Gochu Wings" should show wings, not a breaded cutlet.
    (("wing",), "continental-grilled-chicken.webp"),
    (
        ("manchurian", "dynamite", "honey chicken", "chilli", "chili",
         "teriyaki", "gochu", "szechuan", "schezwan"),
        "crispy-food.webp",
    ),
    (("curry", "thai"), "thai-curry.webp"),
    (("soup", "broth"), "thai-curry.webp"),
    # Italian / western staples
    (("pizza",), "italian-pizza.webp"),
    (
        ("pasta", "spaghetti", "fettuccine", "alfredo", "penne", "lasagn",
         "bolognese", "macaroni", "mac and cheese"),
        "creamy-pasta.webp",
    ),
    (("burger", "patty", "slider", "bun"), "burger.webp"),
    (("fries", "hashbrown", "hash brown"), "burger.webp"),
    (("croissant", "muffin"), "sweet-dessert.webp"),
    (("sandwich", "wrap", "tortilla", "burrito", "taco", "sub ", "club", "bagel"),
     "burger.webp"),
    (
        ("crispy", "krunch", "crunch", "popcorn", "nugget", "strip", "broast",
         "fried chicken", "tempura", "pakora"),
        "crispy-food.webp",
    ),
    # Seafood
    (("prawn", "shrimp", "fish", "salmon", "seafood"), "sour-citrus-dish.webp"),
    # Sweet
    (
        ("cake", "pastry", "pie", "waffle", "pancake", "cheesecake", "brownie",
         "kheer", "dessert", "sundae", "molten", "tiramisu", "ice cream",
         "custard", "fudge", "donut", "doughnut", "french toast"),
        "sweet-dessert.webp",
    ),
    # Generic proteins, last so specific dishes above always win
    (("steak", "grilled"), "continental-grilled-chicken.webp"),
    (("mutton", "lamb", "beef"), "mutton-karahi.webp"),
)


# Interchangeable photographs of the same dish. A menu carries the same dish
# at many restaurants, and one photo repeated down the grid reads as a
# rendering fault. The choice is keyed off the restaurant so a given
# restaurant's dish always looks the same, while neighbouring cards differ.
#
# These are all generic stock photographs; per the manifest's usage note none
# of them depicts a named restaurant's actual food, so rotating between them
# claims nothing that showing a single one did not already claim.
_DISH_VARIANTS: dict[str, tuple[str, ...]] = {
    "italian-pizza.webp": (
        "italian-pizza.webp",
        "pizza-margherita-classic.webp",
        "pizza-neapolitan-peel.webp",
        "pizza-margherita-plate.webp",
        "pizza-quattro-stagioni.webp",
        "pizza-capricciosa.webp",
        "pizza-sliced-board.webp",
        "pizza-margherita-basil.webp",
    ),
    "burger.webp": (
        "burger.webp",
        "burger-classic-cheeseburger.webp",
        "burger-bacon-cheeseburger.webp",
        "burger-stacked-arugula.webp",
        "burger-with-fries-plate.webp",
        "burger-chicken-sliders.webp",
        "burger-restaurant-plate.webp",
        "burger-fries-box.webp",
    ),
    "sweet-dessert.webp": (
        "sweet-dessert.webp",
        "dessert-cheesecake-berries.webp",
        "dessert-cheesecake-slice.webp",
        "dessert-croissants.webp",
        "dessert-apple-crumb-pie.webp",
        "dessert-ice-cream-cone.webp",
        "dessert-waffle.webp",
        "dessert-carrot-cake.webp",
    ),
}


def _pick_variant(filename: str, variant_key: str | None) -> str:
    options = _DISH_VARIANTS.get(filename)
    if not options or not variant_key:
        return filename
    digest = hashlib.sha256(str(variant_key).encode()).digest()
    return options[int.from_bytes(digest[:4], "big") % len(options)]


def _keyword_image(name: str | None) -> str | None:
    key = normalize_image_key(name)
    if not key:
        return None
    padded = f" {key} "
    for keywords, filename in _DISH_KEYWORDS:
        if any(word in padded for word in keywords):
            return filename
    return None


def _resolve_base(
    name: str | None, cuisine: str | None, persisted_image: str | None
) -> str | None:
    """The photograph for a dish before variant spreading. None => persisted."""
    if valid_local_image(persisted_image):
        return None
    manifest = _manifest()
    key = normalize_image_key(name)
    filename = manifest["dish_exact"].get(key)
    if filename is None:
        filename = manifest["dish_aliases"].get(key)
    if filename is None:
        filename = _keyword_image(name)
    if filename is None:
        filename = manifest["cuisine_fallbacks"].get(normalize_image_key(cuisine))
    return filename or manifest["fallback"]


def feed_images(items: Any) -> list[dict[str, Any]]:
    """Resolve one photograph per feed row, cycling through a dish's variants.

    Hashing each row independently re-uses photos by pure chance - with eight
    pizzas and three pizza rows the odds of a repeat are about one in three,
    which is what put two identical cards side by side. Walking the variants
    in order instead guarantees that duplicates of a dish on the same page
    never repeat until every alternative has been used.
    """
    resolved: list[dict[str, Any]] = []
    used: dict[str, int] = {}
    for item in items or []:
        get = item.get if isinstance(item, dict) else lambda k: getattr(item, k, None)
        persisted = get("image_url")
        base = _resolve_base(get("dish_name"), get("cuisine"), persisted)
        if base is None:
            resolved.append(_asset(persisted.removeprefix(STATIC_PREFIX)))
            continue
        options = _DISH_VARIANTS.get(base, (base,))
        index = used.get(base, 0)
        used[base] = index + 1
        resolved.append(_asset(options[index % len(options)]))
    return resolved


def dish_image(
    name: str | None,
    cuisine: str | None = None,
    persisted_image: str | None = None,
    variant_key: str | None = None,
) -> dict[str, Any]:
    """Resolve persisted local metadata, exact dish, alias, keyword, cuisine, neutral.

    `variant_key` (the restaurant id in the feed) spreads dishes that have
    several interchangeable photographs across them; a real persisted image
    always wins and is never rotated.
    """
    if valid_local_image(persisted_image):
        return _asset(persisted_image.removeprefix(STATIC_PREFIX))
    manifest = _manifest()
    key = normalize_image_key(name)
    filename = manifest["dish_exact"].get(key)
    if filename is None:
        filename = manifest["dish_aliases"].get(key)
    if filename is None:
        filename = _keyword_image(name)
    if filename is None:
        filename = manifest["cuisine_fallbacks"].get(normalize_image_key(cuisine))
    return _asset(_pick_variant(filename or manifest["fallback"], variant_key))


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


# Licences that oblige us to name the photographer and the licence in a place
# a viewer can reach. CC0/public-domain and the generated assets do not, but
# they are still listed so the page is a complete record of what ships.
_ATTRIBUTION_REQUIRED = ("CC BY",)


def image_attributions() -> list[dict[str, Any]]:
    """Every shipped photograph with its creator, licence and source page."""
    rows = []
    for filename, meta in sorted(_manifest()["assets"].items()):
        licence = meta.get("licence_or_usage_basis") or "Unspecified"
        rows.append(
            {
                "src": f"{STATIC_PREFIX}{filename}",
                "alt": meta.get("alt", ""),
                "creator": meta.get("creator") or "Unattributed",
                "platform": meta.get("source_platform") or "",
                "licence": licence,
                "page": meta.get("original_source_page") or "",
                "required": any(m in licence for m in _ATTRIBUTION_REQUIRED),
            }
        )
    rows.sort(key=lambda row: (not row["required"], row["licence"], row["src"]))
    return rows
