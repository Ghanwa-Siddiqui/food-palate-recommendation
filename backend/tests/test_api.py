from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.deal import Deal
from tests.factories import dish, restaurant


def test_dish_list_filters_paginates_and_hides_vector(client, session):
    owner = restaurant()
    session.add(owner)
    session.flush()
    session.add_all(
        [
            dish(owner.id, name="Chicken Karahi", price=Decimal("900")),
            dish(owner.id, name="Beef Karahi", price=Decimal("1200")),
        ]
    )
    session.commit()
    response = client.get("/dishes?name=chicken&min_price=800&max_price=1000&limit=1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "Chicken Karahi"
    assert isinstance(payload["items"][0]["price"], (int, float))
    assert isinstance(payload["items"][0]["lat"], (int, float))
    assert isinstance(payload["items"][0]["lng"], (int, float))
    assert "vector" not in payload["items"][0]
    assert "embedding" not in payload["items"][0]
    assert "latitude" not in payload["items"][0]
    assert "longitude" not in payload["items"][0]


def test_public_restaurant_and_deal_numbers_match_contracts(client, session):
    owner = restaurant()
    session.add(owner)
    session.flush()
    now = datetime.now(UTC)
    deal = Deal(
        restaurant_id=owner.id,
        title="Sample Deal",
        description="Synthetic test deal",
        discount_percentage=Decimal("12.50"),
        starts_at=now - timedelta(days=1),
        ends_at=now + timedelta(days=1),
        is_active=True,
    )
    session.add(deal)
    session.commit()

    restaurant_response = client.get(f"/restaurants/{owner.id}")
    deal_response = client.get(f"/deals/{deal.id}")

    assert restaurant_response.status_code == 200
    restaurant_payload = restaurant_response.json()
    assert isinstance(restaurant_payload["lat"], (int, float))
    assert isinstance(restaurant_payload["lng"], (int, float))
    assert "latitude" not in restaurant_payload
    assert "longitude" not in restaurant_payload
    assert deal_response.status_code == 200
    assert isinstance(deal_response.json()["discount_percentage"], (int, float))


def test_restaurant_and_dish_serialize_missing_coordinates_as_null(client, session):
    owner = restaurant(latitude=None, longitude=None, location_verified=False)
    session.add(owner)
    session.flush()
    item = dish(owner.id)
    session.add(item)
    session.commit()

    restaurant_payload = client.get(f"/restaurants/{owner.id}").json()
    dish_payload = client.get(f"/dishes/{item.id}").json()

    assert restaurant_payload["lat"] is None
    assert restaurant_payload["lng"] is None
    assert restaurant_payload["location_verified"] is False
    assert dish_payload["lat"] is None
    assert dish_payload["lng"] is None


def test_vector_is_available_only_from_dedicated_endpoint(client, session):
    owner = restaurant()
    session.add(owner)
    session.flush()
    item = dish(owner.id)
    session.add(item)
    session.commit()
    response = client.get(f"/dishes/{item.id}/vector")
    assert response.status_code == 200
    assert len(response.json()["vector"]) == 384


def test_api_returns_consistent_validation_and_not_found_errors(client):
    invalid = client.get("/dishes?limit=0")
    missing = client.get("/restaurants/00000000-0000-0000-0000-000000000000")
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_existing_dish_without_embedding_is_distinct_from_missing_dish(client, session):
    owner = restaurant()
    session.add(owner)
    session.flush()
    item = dish(owner.id, embedding=None)
    session.add(item)
    session.commit()

    unavailable = client.get(f"/dishes/{item.id}/vector")
    missing = client.get("/dishes/00000000-0000-0000-0000-000000000000/vector")

    assert unavailable.status_code == 409
    assert unavailable.json()["error"]["code"] == "embedding_unavailable"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_only_known_request_errors_are_mapped_to_invalid_request(client):
    invalid_prices = client.get("/dishes?min_price=20&max_price=10")
    invalid_halal = client.get("/restaurants?halal_status=halal")

    assert invalid_prices.status_code == 422
    assert invalid_prices.json()["error"]["code"] == "invalid_request"
    assert invalid_halal.status_code == 422
    assert invalid_halal.json()["error"]["code"] == "validation_error"
