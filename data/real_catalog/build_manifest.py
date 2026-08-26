"""Build and validate the researched real-catalog manifest.

This is deliberately local-only: it does not import the application or connect to a database.
"""

import json
import re
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent
STAMP = "2026-08-26T00:00:00+05:00"
NS = uuid.UUID("c82d2361-4f51-4d14-8b2d-f89579ff4c43")


def uid(kind, value):
    return str(uuid.uuid5(NS, f"{kind}:{value}"))


# brand, display name, branch, city, address, cuisines, price range, verification, source
RESTAURANTS = [
    ("Howdy", "Howdy - MM Alam Road", "MM Alam Road", "Lahore", "Rooftop, 9C Building, MM Alam Road, Gulberg III, Lahore", ["Fast Food", "Continental"], "$$", "exact", "https://www.foodpanda.pk/restaurant/kcnc/howdy-mm-alam-road"),
    ("Yum Chinese", "Yum Chinese - MM Alam", "MM Alam", "Lahore", "MM Alam Road, Gulberg III, Lahore", ["Chinese", "Thai"], "$$$", "area_verified", "https://www.foodpanda.pk/restaurant/w6ce/yum-chinese-mm-alam-odr"),
    ("Layers", "Layers - M.M Alam", "M.M Alam", "Lahore", "Shop 1, KD Plaza, 100 MM Alam Road, Block B2, Gulberg III, Lahore", ["Continental"], "$$", "exact", "https://www.foodpanda.pk/restaurant/p5xl/layers-m-m-alam"),
    ("P.F. Chang's", "P.F. Chang's - Gulberg", "Gulberg", "Lahore", "17-C1 MM Alam Road, Block C1, Gulberg III, Lahore", ["Chinese"], "$$$", "exact", "https://www.foodpanda.pk/restaurant/o5ip/p-f-changs-gulberg"),
    ("California Pizza", "California Pizza - MM Alam Road", "MM Alam Road", "Lahore", "MM Alam Road, Gulberg III, Lahore", ["Italian", "Fast Food"], "$$", "area_verified", "https://www.foodpanda.pk/restaurant/s4vv/california-pizza-mm-alam-road"),
    ("Kitchen Cuisine", "Kitchen Cuisine - M.M Alam", "M.M Alam", "Lahore", "118-119 P Block, MM Alam Road, Gulberg II, Lahore", ["Continental"], "$$", "exact", "https://www.foodpanda.pk/restaurant/qpig/kitchen-cuisine-m-m-alam"),
    ("Spice Bazaar", "Spice Bazaar - T-Block", "T-Block", "Lahore", "T-Block, Gulberg II, Lahore", ["Pakistani"], "$$$", "area_verified", "https://www.foodpanda.pk/restaurant/t2yo/spice-bazaar"),
    ("Arcadian Cafe", "Arcadian Cafe - MM Tower", "MM Tower", "Lahore", "MM Tower, Gulberg, Lahore", ["Continental", "Chinese", "Italian"], "$$", "area_verified", "https://www.foodpanda.pk/restaurant/w5hk/arcadian-cafe-odr"),
    ("Johnny & Jugnu", "Johnny & Jugnu - Emporium", "Emporium", "Lahore", "Emporium Mall, Johar Town, Lahore", ["Fast Food"], "$$", "area_verified", "https://www.foodpanda.pk/restaurant/pb0c/johnny-and-jugnu-emporium"),
    ("OD", "OD - MM Alam", "MM Alam", "Lahore", "MM Alam Road, Gulberg III, Lahore", ["Continental", "Fast Food"], "$$", "area_verified", "https://www.foodpanda.pk/restaurant/d1v9/od-mm-alam-d1v9"),

    ("Xander's", "Xander's - Clifton", "Clifton", "Karachi", "C-32, E-Street, off 26th Street, Block 4, Clifton, Karachi", ["Continental", "Italian"], "$$$", "exact", "https://www.foodpanda.pk/restaurant/s2gf/xanders"),
    ("Burger Lab", "Burger Lab - Badar", "Badar Commercial", "Karachi", "Plot 13/C, Shop 1, Street 10, Badar Commercial, DHA Phase 5, Karachi", ["Fast Food"], "$$", "exact", "https://www.foodpanda.pk/restaurant/v3bp/burger-lab-badar-odr"),
    ("Ginsoy", "Ginsoy - SMCHS", "SMCHS", "Karachi", "Plot 122-A, Malik Heights, SMCHS, Karachi", ["Chinese", "Thai"], "$$", "exact", "https://www.foodpanda.pk/restaurant/s7gg/ginsoy-smchs"),
    ("Broadway Pizza", "Broadway Pizza - Rashid Minhas Road", "Rashid Minhas Road", "Karachi", "Rashid Minhas Road, Karachi", ["Italian", "Fast Food"], "$$", "area_verified", "https://www.foodpanda.pk/restaurant/s0nz/broadway-pizza-rashid-minhas-road"),
    ("Kababjees", "Kababjees - Shaheed-e-Millat", "Shaheed-e-Millat", "Karachi", "No. 3, Karachi Memon Society, Shaheed-e-Millat Road, Karachi", ["Pakistani", "Continental"], "$$$", "exact", "https://www.foodpanda.pk/chain/cv5bv/kababjees-restaurant-cv5bv"),
    ("Del Frio", "Del Frio - SMCHS", "SMCHS", "Karachi", "103-A Zaibi Arcade, SMCHS, Karachi", ["Continental", "Italian"], "$$", "exact", "https://www.foodpanda.pk/restaurant/w0hh/del-frio-smchs-odr"),
    ("Cocochan", "Cocochan - Clifton", "Clifton", "Karachi", "Clifton, Karachi", ["Chinese", "Japanese", "Thai", "Korean"], "$$$", "area_verified", "https://www.foodpanda.pk/restaurant/t0iv/cocochan"),
    ("KFC", "KFC - I.I. Chundrigar Road", "I.I. Chundrigar Road", "Karachi", "I.I. Chundrigar Road, Karachi", ["Fast Food"], "$$", "area_verified", "https://www.foodpanda.pk/restaurant/s3tj/kfc-i-i-chundrigar-road"),
    ("McDonald's", "McDonald's - Stadium Road", "Stadium Road", "Karachi", "Opposite National Stadium, Plot SB-9, KDA Scheme 1 Extension, Karachi", ["Fast Food"], "$$", "exact", "https://www.foodpanda.pk/restaurant/s4wz/mcdonalds-stadium-road"),
    ("Papa Johns", "Papa Johns - Bukhari", "Bukhari Commercial", "Karachi", "42C/2, Bukhari Commercial Lane 8, DHA Phase 6, Karachi", ["Italian", "Fast Food"], "$$", "exact", "https://www.foodpanda.pk/restaurant/yoz5/papa-johns-bukhari"),

    ("Asian Wok", "Asian Wok - F-11", "F-11", "Islamabad", "F-11 Markaz, Islamabad", ["Chinese", "Thai"], "$$$", "area_verified", "https://www.foodpanda.pk/restaurant/wy4q/asian-wok-f-11"),
    ("Burning Brownie", "Burning Brownie - F-11", "F-11", "Islamabad", "Ground Floor, Olympus Mall, F-11 Markaz, Islamabad", ["Continental"], "$$", "exact", "https://www.foodpanda.pk/restaurant/d0q9/burning-brownie-f-11"),
    ("Savour Foods", "Savour Foods - Rawalpindi Stadium", "Rawalpindi Stadium", "Rawalpindi", "Food Street, Double Road, Shamsabad, Rawalpindi", ["Pakistani", "Fast Food"], "$$", "exact", "https://www.foodpanda.pk/restaurant/v2iw/savour-foods-rawalpindi-stadium"),
    ("Ranchers", "Ranchers - I-8", "I-8", "Islamabad", "Time Square Plaza, I-8, Islamabad", ["Fast Food"], "$$", "exact", "https://www.foodpanda.pk/restaurant/s0ty/ranchers"),
    ("Loafology", "Loafology - Blue Area", "Blue Area", "Islamabad", "108-W Jinnah Avenue, G-7/2, Blue Area, Islamabad 44000", ["Continental"], "$$", "exact", "https://www.foodpanda.pk/restaurant/eqms/loafology-blue-area"),
    ("Tuscany Courtyard", "Tuscany Courtyard - Kohsar Market", "Kohsar Market", "Islamabad", "Kohsar Market, F-6/3, Islamabad", ["Italian", "Continental", "Thai"], "$$$", "area_verified", "https://www.foodpanda.pk/restaurant/bjtm/tuscany-courtyard-bjtm"),
    ("Wild Wings", "Wild Wings - I-8 Markaz", "I-8 Markaz", "Islamabad", "Hall 04, 1st Floor, Pakland Vista, I-8 Markaz, Islamabad", ["Fast Food", "Continental"], "$$", "exact", "https://www.foodpanda.pk/restaurant/wzqt/wild-wings-i-8-markaz"),
    ("Tandoori Restaurant", "Tandoori Restaurant - F-10", "F-10", "Islamabad", "Khursheed Market, Street 30, F-10/1, Islamabad", ["Pakistani", "Chinese"], "$", "exact", "https://www.foodpanda.pk/restaurant/w9ms/tandoori-restaurant-f10-odr-w9ms"),
    ("NOM NOM WOK", "NOM NOM WOK - DHA Phase II", "DHA Phase II", "Islamabad", "7-B, Central Park, DHA Phase II, Islamabad", ["Chinese", "Thai"], "$$", "exact", "https://www.foodpanda.pk/restaurant/jnpp/nom-nom-wok-by-tuscany-courtyard-jnpp"),
    ("Chaaye Khana", "Chaaye Khana - F-11", "F-11", "Islamabad", "Plot 37, Crown Plaza, F-11 Markaz, Islamabad", ["Pakistani", "Continental"], "$$", "exact", "https://www.foodpanda.pk/restaurant/w0xx/chaaye-khana-f-11-odr"),
]


# brand -> [(published name, regular PKR price, cuisine, preparation style, description-or-null)]
DISHES = {
    "Howdy": [("Son Of A Bun", 1249, "Fast Food", "charcoal-grilled", None), ("Yay Cheese", 1099, "Fast Food", "fried", None), ("Chock-A-Block", 1149, "Fast Food", "charcoal-grilled", None)],
    "Yum Chinese": [("Spicy Honey Chicken Wings", 775, "Chinese", "fried", "Spicy fried chicken wings glazed with honey and chillies."), ("Chinese Spring Roll", 725, "Chinese", "fried", "Wok stir-fried vegetables, chicken and Chinese spices."), ("Prawns Tempura", 1495, "Japanese", "fried", "Deep-fried prawns dipped in YUM's batter.")],
    "Layers": [("Three Milk Cake", 2400, "Continental", "baked", None), ("Milky Malt Cake", 1900, "Continental", "baked", None), ("Three Milk Sundae", 500, "Continental", "chilled", None)],
    "P.F. Chang's": [("The Original Dynamite Shrimp", 2450, "Chinese", "fried", None), ("Dumplings", 1390, "Chinese", "steamed", "Hand-wrapped dumplings."), ("Mongolian Beef", 2850, "Chinese", "stir-fried", "Sweet soy glazed flank steak with garlic and green onion.")],
    "California Pizza": [("Sriracha Sizzle", 549, "Italian", "baked", "Sriracha sauce with fajita meat, capsicum, onion, mushrooms, jalapeno and cheese."), ("Ranchy Madness", 549, "Italian", "baked", "Ranch sauce with tikka meat, capsicum, onion, jalapeno and cheese."), ("Peri Peri Punch", 549, "Italian", "baked", "Peri peri sauce with malai boti, capsicum, onion, jalapeno and cheese.")],
    "Kitchen Cuisine": [("Chicken Mushroom Crepe Roll", 340, "Continental", "baked", None), ("Fudge Delight Pastry", 390, "Continental", "baked", None), ("Cold Cheesecake Strawberry 1lb", 1500, "Continental", "chilled", None)],
    "Spice Bazaar": [("Chicken Seekh Kabab", 1895, "Pakistani", "charcoal-grilled", None), ("Sindhi Matka Biryani", 2095, "Pakistani", "slow-cooked", None), ("Chicken Tikka", 1095, "Pakistani", "charcoal-grilled", None)],
    "Arcadian Cafe": [("Cream of Chicken Soup", 445, "Continental", "simmered", None), ("Chicken Manchurian", 925, "Chinese", "stir-fried", "Served with egg fried rice."), ("Crispy Honey Chicken", 945, "Chinese", "fried", "Served with egg fried rice.")],
    "Johnny & Jugnu": [("WEHSHI", 890, "Fast Food", "fried", "Crispy chicken burger."), ("TORTILLA WRAP", 1100, "Fast Food", "wrapped", "Four chicken tenderloin strips in a wrap."), ("Gochu Wings", 810, "Korean", "fried", None)],
    "OD": [("Chicken Honey Mustard", 1490, "Continental", "grilled", None), ("Classic Pancake", 1090, "Continental", "griddled", None), ("Breakfast Wrap", 1490, "Continental", "wrapped", "Scrambled eggs, smoked chicken and hash browns in a tortilla with mushroom sauce.")],

    "Xander's": [("Babar Pasta", 1860, "Italian", "boiled", None), ("The Xanders Club", 1810, "Continental", "toasted", "Club sandwich with grilled chicken, turkey bacon, omelette, tomatoes, cheddar and cucumber."), ("Loaded Sriracha Fries", 1450, "Continental", "fried", "Fries with sriracha mayo, jalapenos, salsa verde, tomatoes, parmesan and truffle oil.")],
    "Burger Lab": [("Animal Fries", 800, "Fast Food", "fried", None), ("Habibi Injected Burger Double", 690, "Fast Food", "fried", None), ("All American", 850, "Fast Food", "griddled", None)],
    "Ginsoy": [("Hot and Sour Soup (Red)", 290, "Chinese", "simmered", "Chillies, ginger and vinegar."), ("Dynamite Chicken", 560, "Chinese", "fried", None), ("Basket of Fries", 410, "Fast Food", "fried", None)],
    "Broadway Pizza": [("Value Pasta", 399, "Italian", "boiled", "Garlic pasta."), ("Pizza Roll", 399, "Italian", "baked", "Chicken Mughlai, garlic ranch sauce, mozzarella, onions, capsicum, tomatoes and jalapenos."), ("Garlic Bread", 399, "Italian", "baked", "Six pieces.")],
    "Kababjees": [("Chicken Madabee", 1990, "Middle Eastern", "roasted", None), ("Chicken Makhni Handi", 2590, "Pakistani", "slow-cooked", None), ("Chicken Alfredo", 1690, "Italian", "boiled", None)],
    "Del Frio": [("French Toast", 395, "Continental", "griddled", None), ("Ferrero Rocher Waffles", 650, "Continental", "griddled", "Served with a scoop of ice cream."), ("Portuguese Baked Eggs", 640, "Continental", "baked", "Eggs with bell peppers, onions, jalapenos, tomatoes, basil, garlic, oregano and cream cheese.")],
    "Cocochan": [("dynamite chicken", 1460, "Chinese", "fried", "Batter-fried crispy dynamite chicken."), ("korean popcorn shrimp", 1440, "Korean", "fried", "Korean popcorn shrimp with truffle mayo."), ("crispy thai chicken", 1140, "Thai", "fried", "Crispy Thai chicken with chilli lime sauce and garlic.")],
    "KFC": [("Krunch Burger", 310, "Fast Food", "fried", "Crispy chicken fillet in a bun with sauce and lettuce."), ("Rice & Spice", 420, "Fast Food", "fried", None), ("Mexinger Burger", 660, "Fast Food", "fried", "Chicken burger with salsa, cheese, jalapenos and chipotle mayo.")],
    "McDonald's": [("Egg N Hashbrowns Wrap", 582.61, "Fast Food", "wrapped", None), ("Chicken Sausage McMuffin with Egg", 521.74, "Fast Food", "toasted", None), ("Chicken Sausage McMuffin", 434.79, "Fast Food", "toasted", None)],
    "Papa Johns": [("Kids 6'' Cheese Pizza", 650, "Italian", "baked", "Cheese and pizza sauce base."), ("Spicy Chicken Rolls", 600, "Italian", "baked", "Fresh dough rolled with spicy chicken, jalapenos, ranch sauce and mozzarella."), ("Chicken Alfredo", 1000, "Italian", "baked", "Penne pasta with Alfredo sauce, grilled chicken, mushrooms and oregano.")],

    "Asian Wok": [("Prawn Tempura (6 Pcs)", 4595, "Japanese", "fried", "Prawns in special batter, deep-fried and served with wonton sauce."), ("Chinese Spring Rolls (6 Pcs)", 2195, "Chinese", "fried", "Vegetables and chicken with Chinese spices in a crispy wrapper."), ("Steamed Chicken Dumplings (8 Pcs)", 2275, "Chinese", "steamed", "Steamed dumplings filled with chicken mince.")],
    "Burning Brownie": [("Grilled Chicken Sandwich", 1100, "Continental", "grilled", None), ("Deli Chicken", 1000, "Continental", "toasted", None), ("Baked Cheese Cake Slice", 581, "Continental", "baked", None)],
    "Savour Foods": [("Chicken Pulao Single", 724, "Pakistani", "steamed", "Rice with a chicken piece, two shami kabab, salad and raita."), ("Pulao Kabab", 490, "Pakistani", "steamed", "Rice with two shami kabab, salad and raita."), ("Shami Kabab", 68, "Pakistani", "fried", None)],
    "Ranchers": [("Krunch Burger", 299, "Fast Food", "fried", None), ("Gun Smoked Fries", 775, "Fast Food", "fried", "Fries with grilled chicken, tangy sauce, Mughlai sauce, tandoori sauce and jalapeno."), ("Crown Pizza", 1599, "Italian", "baked", None)],
    "Loafology": [("Plain Croissant", 669, "Continental", "baked", "Traditional flaky croissant made with French butter."), ("Ultimate Salmon Bagel", 2799, "Continental", "toasted", "Bagel with smoked salmon, capers, onion and cream cheese."), ("French Toast", 1545, "Continental", "griddled", "Brioche with maple syrup, seasonal fruit and icing sugar.")],
    "Tuscany Courtyard": [("Spaghetti Bolognese Pasta", 1895, "Italian", "boiled", "Spaghetti with minced chicken, tomato sauce, cheese and parsley."), ("Fettuccine Alfredo Pasta", 1975, "Italian", "boiled", "Pasta with grilled chicken, shallots, cream sauce and basil."), ("Chicken Strips with French Fries", 1595, "Continental", "fried", "Fried chicken strips with fries and sauce.")],
    "Wild Wings": [("Louisiana Chicken Pasta", 1590, "Continental", "boiled", "Bow-tie pasta with creamy sauce, fried chicken bites and mushroom."), ("Mushroom Chicken Steak", 2145, "Continental", "charcoal-grilled", "Chicken with mashed potatoes or fries, vegetables and mushroom sauce."), ("Classic American Burger", 1690, "Fast Food", "griddled", "Double beef patty with cheddar, onions, gherkins and burger sauce.")],
    "Tandoori Restaurant": [("Fresh Green Salad", 130, "Pakistani", "raw", "Seasonal vegetables."), ("Roghani Naan", 70, "Pakistani", "tandoor-baked", None), ("Kheer", 100, "Pakistani", "simmered", None)],
    "NOM NOM WOK": [("Chicken Spring Rolls", 749, "Chinese", "fried", "Spring rolls with vegetables and chicken, served with sweet chilli sauce."), ("Dynamite Prawns", 1499, "Chinese", "fried", "Crispy prawns tossed in dynamite sauce."), ("Dynamite Chicken", 1199, "Chinese", "fried", "Crispy chicken cubes tossed in dynamite sauce.")],
    "Chaaye Khana": [("Carrot Cake Slice", 280, "Continental", "baked", None), ("Apple Pie", 245, "Continental", "baked", None), ("Chocolate Molten Cake", 385, "Continental", "baked", None)],
}


def taste(name, cuisine, prep):
    """Conservative editorial estimates; never presented as published facts."""
    n = name.lower()
    sweet = 4 if any(x in n for x in ("cake", "pie", "sundae", "waffle", "pancake", "french toast", "pastry")) else 1
    spice = 4 if any(x in n for x in ("spicy", "sriracha", "dynamite", "gochu", "chilli", "tikka")) else (2 if cuisine in ("Pakistani", "Thai", "Korean") else 1)
    oil = 4 if prep == "fried" else (2 if prep in ("griddled", "stir-fried", "charcoal-grilled") else 1)
    smoke = 3 if prep == "charcoal-grilled" or "smoked" in n else 0
    rich = 4 if any(x in n for x in ("cheese", "alfredo", "mushroom", "fudge", "milk", "molten")) else (3 if sweet >= 4 else 2)
    sour = 2 if any(x in n for x in ("sour", "lime", "lemon", "sriracha")) else 0
    salt = 2 if sweet >= 4 else 3
    texture = []
    if prep in ("fried", "baked", "toasted", "tandoor-baked"): texture.append("crispy")
    if prep in ("simmered", "slow-cooked", "steamed"): texture.append("soft")
    return dict(spice_level=spice, oiliness=oil, sweetness=sweet, sourness=sour,
                saltiness=salt, smokiness=smoke, richness=rich, texture_tags=texture)


def build():
    restaurants, dishes, sources = [], [], {"metadata": {
        "catalog_version": "2026-08-26",
        "price_currency": "PKR",
        "price_verified_at": "2026-08-26",
        "deals_count": 0,
        "taste_profile_provenance": "editorial_estimate",
        "taste_profile_note": "Numeric taste fields and texture tags are conservative editorial estimates for recommendation bootstrapping. They are not restaurant-published facts. Names, regular prices, descriptions, and ingredient statements require the cited menu source.",
    }, "restaurants": [], "dishes": [], "failed_candidates": [
        {"candidate": "Cheezious", "region": "Islamabad/Rawalpindi", "reason": "Search results mixed the official brand with similarly named independent pizzerias; replaced to avoid misattribution."},
        {"candidate": "Tehzeeb Bakers", "region": "Islamabad/Rawalpindi", "reason": "No current branch menu with three unambiguous fixed prices was found in the reviewed results."},
        {"candidate": "Nando's", "region": "Karachi", "reason": "No usable current branch listing with three fixed prices appeared in the reviewed results."},
        {"candidate": "Hot & Grill", "region": "Rawalpindi", "reason": "Menu was dominated by temporary discounts and did not meet the preferred regular-price evidence rule."}
    ]}

    for brand, name, branch, city, address, cuisines, price_range, status, url in RESTAURANTS:
        rid = uid("restaurant", brand)
        restaurants.append({
            "id": rid, "name": name, "description": None, "cuisine_types": cuisines,
            "address": address, "city": city, "lat": None, "lng": None,
            "location_verified": False, "coordinates_source_url": None,
            "coordinates_verified_at": None, "price_range": price_range,
            "halal_status": "unknown", "created_at": STAMP, "updated_at": STAMP,
        })
        sources["restaurants"].append({
            "restaurant_id": rid, "brand_name": brand, "branch_name": branch,
            "restaurant_source_url": url, "address_source_url": url,
            "menu_source_url": url, "address_verification_status": status,
            "price_verified_at": STAMP,
            "notes": "Current Foodpanda branch listing. Halal status not asserted; coordinates intentionally unverified.",
        })
        for name_, price, cuisine, prep, description in DISHES[brand]:
            did = uid("dish", f"{brand}:{name_}")
            values = taste(name_, cuisine, prep)
            dishes.append({
                "id": did, "restaurant_id": rid, "name": name_, "description": description,
                "cuisine": cuisine, "ingredients": [], "price": price, **values,
                "dietary_tags": [], "allergens": [], "preparation_style": prep,
                "availability": True, "lat": None, "lng": None,
                "created_at": STAMP, "updated_at": STAMP,
            })
            sources["dishes"].append({
                "dish_id": did, "restaurant_id": rid, "menu_source_url": url,
                "price_verified_at": STAMP, "price_type": "regular",
                "notes": "Fixed visible price, or original regular price where the listing displayed a platform discount. Taste fields are editorial estimates.",
            })
    return restaurants, dishes, sources


def validate(restaurants, dishes, sources):
    errors = []
    rids = {r["id"] for r in restaurants}
    counts = Counter(d["restaurant_id"] for d in dishes)
    brands = [s["brand_name"] for s in sources["restaurants"]]
    normalized = [re.sub(r"[^a-z0-9]", "", b.lower()) for b in brands]
    city_groups = Counter("Islamabad/Rawalpindi" if r["city"] in {"Islamabad", "Rawalpindi"} else r["city"] for r in restaurants)
    errors += [] if len(restaurants) == 30 else ["restaurant count must be 30"]
    errors += [] if len(dishes) == 90 else ["dish count must be 90"]
    errors += [] if all(counts[rid] == 3 for rid in rids) else ["every restaurant must have 3 dishes"]
    errors += [] if len(set(normalized)) == 30 else ["normalized brands must be unique"]
    errors += [] if city_groups == {"Lahore": 10, "Karachi": 10, "Islamabad/Rawalpindi": 10} else [f"bad city split: {city_groups}"]
    errors += [] if all(d["restaurant_id"] in rids for d in dishes) else ["orphan dish"]
    errors += [] if all(isinstance(d["price"], (int, float)) and d["price"] > 0 for d in dishes) else ["invalid price"]
    errors += [] if all((r["lat"] is None) == (r["lng"] is None) for r in restaurants) else ["coordinate pair"]
    errors += [] if all(not r["location_verified"] for r in restaurants if r["lat"] is None) else ["null coordinates marked verified"]
    errors += [] if all(r["halal_status"] == "unknown" for r in restaurants) else ["unsupported halal claim"]
    bad_cuisine = {"BBQ", "Grill", "Steak", "Seafood", "Café", "Cafe", "Bakery"}
    errors += [] if all(not (set(r["cuisine_types"]) & bad_cuisine) for r in restaurants) and all(d["cuisine"] not in bad_cuisine for d in dishes) else ["invalid regional cuisine taxonomy"]
    errors += [] if all(s.get("address_source_url") and s.get("menu_source_url") for s in sources["restaurants"]) else ["missing restaurant source"]
    errors += [] if all(s.get("menu_source_url") for s in sources["dishes"]) else ["missing dish source"]
    errors += [] if not any("sample" in (r["name"] + " " + r["address"]).lower() for r in restaurants) else ["sample data found"]
    if errors:
        raise ValueError("; ".join(errors))
    return {"restaurants": len(restaurants), "dishes": len(dishes), "brands": len(set(normalized)), "city_groups": dict(city_groups), "deals": 0}


if __name__ == "__main__":
    restaurant_rows, dish_rows, source_rows = build()
    result = validate(restaurant_rows, dish_rows, source_rows)
    for filename, payload in (("restaurants.json", restaurant_rows), ("dishes.json", dish_rows), ("sources.json", source_rows)):
        (ROOT / filename).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        json.loads((ROOT / filename).read_text(encoding="utf-8"))
    print(json.dumps(result, indent=2))
