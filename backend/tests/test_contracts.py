import json

from jsonschema import Draft202012Validator

from tests.contract_validation import CONTRACT_DOCUMENTS, CONTRACTS, validate_contract


def test_all_contracts_are_valid_json_and_versioned():
    paths = sorted(CONTRACTS.glob("*.schema.json"))
    assert len(paths) == 9
    for path in paths:
        contract = json.loads(path.read_text(encoding="utf-8"))
        assert contract["$schema"].endswith("2020-12/schema")
        assert "/v1/" in contract["$id"]


def test_all_contracts_pass_draft_2020_12_metaschema_validation():
    for contract in CONTRACT_DOCUMENTS.values():
        Draft202012Validator.check_schema(contract)


def test_relative_refs_resolve_through_contract_registry():
    restaurant = {
        "id": "00000000-0000-0000-0000-000000000001",
        "name": "Sample",
        "description": None,
        "cuisine_types": ["Pakistani"],
        "address": "Sample address",
        "city": "Karachi",
        "lat": 24.86,
        "lng": 67.01,
        "location_verified": True,
        "coordinates_source_url": "https://nominatim.openstreetmap.org/",
        "coordinates_verified_at": "2026-08-26T00:00:00Z",
        "price_range": "moderate",
        "halal_status": "claimed",
        "owner_id": None,
        "contact_phone": None,
        "halal_verification_status": "unverified",
        "opening_information": None,
        "available": True,
        "image_path": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    validate_contract(
        "paginated-restaurants.schema.json",
        {"items": [restaurant], "total": 1, "limit": 20, "offset": 0},
    )

    restaurant.update(
        lat=None,
        lng=None,
        location_verified=False,
        coordinates_source_url=None,
        coordinates_verified_at=None,
    )
    validate_contract("restaurant.schema.json", restaurant)


def test_dish_contract_preserves_compatibility_fields():
    contract = json.loads((CONTRACTS / "dish.schema.json").read_text(encoding="utf-8"))
    fields = contract["properties"]
    required = (
        "id",
        "restaurant_id",
        "name",
        "description",
        "cuisine",
        "ingredients",
        "price",
        "vector",
        "lat",
        "lng",
    )
    assert all(name in fields for name in required)
    assert fields["vector"]["minItems"] == fields["vector"]["maxItems"] == 384
    palate_fields = {
        "smokiness",
        "richness",
        "allergens",
        "preparation_style",
        "availability",
    }
    assert palate_fields <= set(fields)


def test_restaurant_contract_uses_public_coordinate_names():
    contract = json.loads((CONTRACTS / "restaurant.schema.json").read_text(encoding="utf-8"))
    fields = contract["properties"]

    assert {"lat", "lng"} <= set(contract["required"])
    assert "latitude" not in fields
    assert "longitude" not in fields


def test_cross_module_handoff_contracts_preserve_agreed_shapes():
    review = json.loads((CONTRACTS / "review-summary.schema.json").read_text(encoding="utf-8"))
    interaction = json.loads((CONTRACTS / "interaction.schema.json").read_text(encoding="utf-8"))

    assert set(review["required"]) == {
        "dish_id",
        "avg_sentiment",
        "spice_level",
        "oiliness",
        "flavor_tags",
        "review_vector",
    }
    assert interaction["properties"]["action"]["enum"] == [
        "click",
        "save",
        "order",
        "tried",
        "like",
        "dislike",
    ]


def test_user_taste_contract_covers_onboarding_handoff_without_vector_logic():
    contract = json.loads((CONTRACTS / "user-taste.schema.json").read_text(encoding="utf-8"))
    required = {
        "user_id",
        "preferred_cuisines",
        "favourite_dishes",
        "spice_preference",
        "sweetness_preference",
        "sourness_preference",
        "saltiness_preference",
        "oiliness_preference",
        "preferred_textures",
        "budget_min",
        "budget_max",
        "dietary_requirements",
        "allergies",
        "disliked_ingredients",
        "taste_vector",
        "last_updated",
    }

    assert set(contract["required"]) == required
    assert set(contract["properties"]) == required
    assert "minItems" not in contract["properties"]["taste_vector"]
