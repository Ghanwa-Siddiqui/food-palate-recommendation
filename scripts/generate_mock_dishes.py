"""Generate mock dish fixtures with deterministic vectors.

Output shape matches Ganva's docs/contracts/v1/dish-vector.schema.json:
    { id: uuid, restaurant_id: uuid, vector: float[384] }
plus convenience fields (name, cuisine, ingredients, price, lat, lng) this
module's own dev/testing uses but the contract doesn't require.

Run:  python scripts/generate_mock_dishes.py
Writes data/mock_dishes.json (~40 dishes across ~12 restaurants, mixed cuisines).

These are placeholders for Day 1 so the personalization engine has something
real-shaped to work against. Ganva's seeded dish data (data/real_catalog/ on
their branch, 90 real dishes) replaces this once integrated.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DATA_DIR
from app.embedding import embed_dish

# Deterministic uuid5s so re-running this script reproduces the same ids —
# same spirit as Ganva's real_catalog ids, just generated from readable slugs.
_ID_NAMESPACE = uuid.UUID("f7e6d5c4-b3a2-4190-8f7e-6d5c4b3a2190")


def _stable_uuid(slug: str) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, slug))

# Karachi-ish coordinates so the distance calc has something meaningful to chew on.
RESTAURANTS = [
    ("r_01", "Kolachi",              24.7960, 66.9670),
    ("r_02", "BBQ Tonight",          24.8127, 67.0349),
    ("r_03", "Ginsoy",               24.8261, 67.0332),
    ("r_04", "Cafe Aylanto",         24.8115, 67.0296),
    ("r_05", "Xander's",             24.8156, 67.0311),
    ("r_06", "Kababjees",            24.8607, 67.0011),
    ("r_07", "OPTP",                 24.8280, 67.0644),
    ("r_08", "Hanabi",               24.8231, 67.0300),
    ("r_09", "Pompei",               24.8090, 67.0300),
    ("r_10", "Chatkharay",           24.8850, 67.0770),
    ("r_11", "Roasters",             24.8410, 67.0620),
    ("r_12", "Del Frio",             24.8130, 67.0290),
]

# (restaurant_id, name, cuisine, ingredients, price_pkr)
DISHES = [
    ("r_01", "Seekh Kebab Platter",     "Pakistani",  ["beef", "spices", "onion", "coriander"],        1450),
    ("r_01", "Chicken Malai Boti",      "Pakistani",  ["chicken", "cream", "yogurt", "cardamom"],      1350),
    ("r_01", "Sindhi Biryani",          "Pakistani",  ["basmati", "beef", "potato", "plum", "spices"], 1200),
    ("r_02", "Mutton Karahi",           "Pakistani",  ["mutton", "tomato", "green chili", "ginger"],   2400),
    ("r_02", "Chicken Tikka",           "Pakistani",  ["chicken", "yogurt", "chili", "lemon"],         1100),
    ("r_02", "Beef Nihari",             "Pakistani",  ["beef shank", "flour", "ghee", "spices"],       1300),
    ("r_03", "Chicken Manchurian",      "Chinese",    ["chicken", "soy", "garlic", "cornflour"],       1250),
    ("r_03", "Prawn Fried Rice",        "Chinese",    ["prawn", "rice", "egg", "soy", "spring onion"], 1450),
    ("r_03", "Kung Pao Chicken",        "Chinese",    ["chicken", "peanut", "dry chili", "capsicum"],  1350),
    ("r_04", "Truffle Mushroom Pasta",  "Italian",    ["fettuccine", "mushroom", "truffle", "cream"],  1950),
    ("r_04", "Grilled Salmon",          "Continental",["salmon", "butter", "lemon", "asparagus"],      2600),
    ("r_04", "Caesar Salad",            "Continental",["romaine", "parmesan", "anchovy", "crouton"],    950),
    ("r_05", "Wagyu Burger",            "American",   ["wagyu", "bun", "cheddar", "onion"],            2200),
    ("r_05", "BBQ Ribs",                "American",   ["pork ribs", "bbq sauce", "smoke"],             2800),
    ("r_05", "Loaded Fries",            "American",   ["potato", "cheese", "bacon", "jalapeno"],        750),
    ("r_06", "Chicken Handi",           "Pakistani",  ["chicken", "tomato", "yogurt", "spices"],       1400),
    ("r_06", "Mutton Pulao",            "Pakistani",  ["basmati", "mutton", "cumin", "onion"],         1550),
    ("r_06", "Gola Kebab",              "Pakistani",  ["beef", "papaya", "spices", "coal"],            1650),
    ("r_07", "Bun Kebab",               "Street",     ["bun", "lentil", "chutney", "onion"],            250),
    ("r_07", "Chicken Roll",            "Street",     ["chicken", "paratha", "chutney", "salad"],       350),
    ("r_07", "Fries",                   "Street",     ["potato", "salt", "ketchup"],                    200),
    ("r_08", "Salmon Sushi",            "Japanese",   ["salmon", "rice", "nori", "wasabi"],            1850),
    ("r_08", "Chicken Ramen",           "Japanese",   ["noodle", "chicken", "miso", "egg"],            1600),
    ("r_08", "Vegetable Tempura",       "Japanese",   ["vegetable", "batter", "soy"],                  1100),
    ("r_09", "Margherita Pizza",        "Italian",    ["dough", "tomato", "mozzarella", "basil"],      1350),
    ("r_09", "Pesto Chicken Pasta",     "Italian",    ["penne", "chicken", "pesto", "parmesan"],       1550),
    ("r_09", "Tiramisu",                "Italian",    ["mascarpone", "coffee", "cocoa"],                850),
    ("r_10", "Aloo Tikki Chaat",        "Street",     ["potato", "chickpea", "yogurt", "chutney"],      400),
    ("r_10", "Chana Chaat",             "Street",     ["chickpea", "onion", "chutney", "tomato"],       300),
    ("r_10", "Gol Gappay",              "Street",     ["semolina puri", "tamarind", "mint"],            250),
    ("r_11", "Cold Brew",               "Cafe",       ["coffee"],                                       450),
    ("r_11", "Avocado Toast",           "Cafe",       ["sourdough", "avocado", "chili flakes"],         850),
    ("r_11", "Blueberry Pancakes",      "Cafe",       ["flour", "blueberry", "butter", "maple"],        950),
    ("r_12", "Chicken Enchiladas",      "Mexican",    ["tortilla", "chicken", "salsa", "cheese"],      1250),
    ("r_12", "Beef Fajitas",            "Mexican",    ["beef", "capsicum", "tortilla", "sour cream"],  1650),
    ("r_12", "Guacamole & Nachos",      "Mexican",    ["avocado", "lime", "corn chips"],                750),
    ("r_08", "Veggie Sushi Roll",       "Japanese",   ["cucumber", "avocado", "rice", "nori"],         1250),
    ("r_04", "Lentil Soup",             "Continental",["lentil", "carrot", "onion", "herbs"],           550),
    ("r_02", "Dal Makhani",             "Pakistani",  ["black lentil", "butter", "cream", "tomato"],    850),
    ("r_06", "Palak Paneer",            "Pakistani",  ["spinach", "paneer", "garlic", "cream"],         950),
]


def build_dishes() -> list[dict]:
    lookup = {rid: (name, lat, lng) for rid, name, lat, lng in RESTAURANTS}
    out = []
    for idx, (rid, name, cuisine, ingredients, price) in enumerate(DISHES, start=1):
        _, lat, lng = lookup[rid]
        out.append({
            "id": _stable_uuid(f"dish:{rid}:{name}"),
            "restaurant_id": _stable_uuid(f"restaurant:{rid}"),
            "name": name,
            "cuisine": cuisine,
            "ingredients": ingredients,
            "price": price,
            "vector": embed_dish(name, cuisine, ingredients),
            "lat": lat,
            "lng": lng,
        })
    return out


def build_restaurants() -> list[dict]:
    return [
        {"id": _stable_uuid(f"restaurant:{rid}"), "name": name, "lat": lat, "lng": lng}
        for rid, name, lat, lng in RESTAURANTS
    ]


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dishes = build_dishes()
    restaurants = build_restaurants()

    dishes_path = DATA_DIR / "mock_dishes.json"
    restaurants_path = DATA_DIR / "mock_restaurants.json"

    dishes_path.write_text(json.dumps(dishes, indent=2), encoding="utf-8")
    restaurants_path.write_text(json.dumps(restaurants, indent=2), encoding="utf-8")

    print(f"Wrote {len(dishes)} dishes -> {dishes_path.relative_to(DATA_DIR.parent)}")
    print(f"Wrote {len(restaurants)} restaurants -> {restaurants_path.relative_to(DATA_DIR.parent)}")


if __name__ == "__main__":
    main()
