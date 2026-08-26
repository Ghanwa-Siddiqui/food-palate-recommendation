from decimal import Decimal

from app.models.dish import Dish
from app.models.restaurant import Restaurant


def restaurant(**overrides) -> Restaurant:
    values = {
        "name": "Sample Kitchen",
        "description": "Synthetic test restaurant",
        "cuisine_types": ["Pakistani"],
        "address": "Test Block",
        "city": "Karachi",
        "latitude": Decimal("24.8607"),
        "longitude": Decimal("67.0011"),
        "price_range": "moderate",
        "halal_status": "claimed",
    }
    values.update(overrides)
    return Restaurant(**values)


def dish(restaurant_id, **overrides) -> Dish:
    values = {
        "restaurant_id": restaurant_id,
        "name": "Chicken Karahi",
        "description": "Tomato-forward sample curry",
        "cuisine": "Pakistani",
        "ingredients": ["chicken", "tomato", "ginger"],
        "price": Decimal("950.00"),
        "spice_level": 4,
        "oiliness": 3,
        "sweetness": 0,
        "sourness": 1,
        "saltiness": 3,
        "smokiness": 2,
        "richness": 4,
        "texture_tags": ["tender"],
        "dietary_tags": ["halal"],
        "allergens": [],
        "preparation_style": "stovetop",
        "availability": True,
        "embedding": [0.25] * 384,
    }
    values.update(overrides)
    return Dish(**values)
