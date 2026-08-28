"""Guards for the dish-name -> photograph keyword fallback.

_asset() silently substitutes the neutral plate when a filename is missing
from the manifest, so a typo or an unregistered image degrades quietly
instead of failing. These tests make that loud.
"""

import json
from pathlib import Path

from app.image_assets import (
    feed_images,
    IMAGE_DIR,
    MANIFEST_PATH,
    _DISH_KEYWORDS,
    _DISH_VARIANTS,
    dish_image,
)


def _manifest() -> dict:
    with MANIFEST_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_every_keyword_target_is_registered_and_present_on_disk():
    assets = _manifest()["assets"]
    for keywords, filename in _DISH_KEYWORDS:
        assert filename in assets, (
            f"{filename} (for {keywords[0]!r}) is not in the image manifest, so it "
            "would silently fall back to the neutral plate"
        )
        assert (IMAGE_DIR / filename).is_file(), f"{filename} is missing from disk"


def test_keyword_matching_separates_dishes_that_share_a_cuisine():
    """The bug this fixes: every Chinese dish resolved to one fried-rice photo."""
    chinese = ["Egg Fried Rice", "Chicken Chow Mein", "Beef Chilli Dry"]
    resolved = {dish_image(name, "Chinese")["src"] for name in chinese}
    assert len(resolved) == 3, f"expected three distinct photos, got {resolved}"


def test_exact_manifest_entries_still_win_over_keywords():
    assert dish_image("Chicken Biryani", "Pakistani")["src"].endswith(
        "chicken-biryani.webp"
    )
    # "Margherita Pizza" is an exact entry; "Crown Pizza" only matches by keyword.
    assert dish_image("Crown Pizza", "Italian")["src"].endswith("italian-pizza.webp")


def test_every_variant_is_registered_and_present_on_disk():
    assets = _manifest()["assets"]
    for base, options in _DISH_VARIANTS.items():
        assert base in options, f"{base} should be among its own variants"
        for filename in options:
            assert filename in assets, f"variant {filename} is not in the manifest"
            assert (IMAGE_DIR / filename).is_file(), f"{filename} missing from disk"


def test_repeated_dish_on_one_page_never_repeats_a_photo():
    """The reported bug: three Margherita Pizza cards all showed one photo."""
    variants = len(_DISH_VARIANTS["italian-pizza.webp"])
    items = [
        {"dish_name": "Margherita Pizza", "cuisine": "Italian", "image_url": None}
        for _ in range(variants)
    ]
    srcs = [image["src"] for image in feed_images(items)]
    assert len(set(srcs)) == variants, f"photos repeated within one page: {srcs}"


def test_variants_wrap_around_once_exhausted():
    items = [
        {"dish_name": "Margherita Pizza", "cuisine": "Italian", "image_url": None}
        for _ in range(10)
    ]
    srcs = [image["src"] for image in feed_images(items)]
    assert srcs[0] == srcs[8], "the cycle should restart after every variant is used"


def test_feed_images_keeps_a_persisted_image_and_aligns_with_rows():
    items = [
        {"dish_name": "Margherita Pizza", "cuisine": "Italian", "image_url": None},
        {
            "dish_name": "Margherita Pizza",
            "cuisine": "Italian",
            "image_url": "/static/images/sushi-platter.webp",
        },
        {"dish_name": "Chicken Biryani", "cuisine": "Pakistani", "image_url": None},
    ]
    srcs = [image["src"] for image in feed_images(items)]
    assert len(srcs) == len(items)
    assert srcs[1] == "/static/images/sushi-platter.webp"
    assert srcs[2].endswith("chicken-biryani.webp")


def test_variant_choice_is_stable_for_a_given_restaurant():
    first = dish_image("Margherita Pizza", "Italian", None, "rest-a")["src"]
    for _ in range(5):
        assert dish_image("Margherita Pizza", "Italian", None, "rest-a")["src"] == first


def test_variants_are_not_applied_without_a_key():
    assert dish_image("Margherita Pizza", "Italian")["src"].endswith("italian-pizza.webp")


def test_persisted_image_is_never_rotated():
    persisted = "/static/images/sushi-platter.webp"
    for restaurant in ("a", "b", "c"):
        assert (
            dish_image("Margherita Pizza", "Italian", persisted, restaurant)["src"]
            == persisted
        )


def test_persisted_image_overrides_keyword_matching():
    persisted = "/static/images/sushi-platter.webp"
    assert dish_image("Chicken Biryani", "Pakistani", persisted)["src"] == persisted


def test_unmatched_dish_falls_back_to_cuisine_then_neutral():
    assert dish_image("Zzz Unknown", "Italian")["src"].endswith("italian-pizza.webp")
    assert dish_image("Zzz Unknown", "Klingon")["src"].endswith(
        _manifest()["fallback"]
    )
