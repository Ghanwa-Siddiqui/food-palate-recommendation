from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.deal import Deal
from tests.contract_validation import validate_contract
from tests.factories import dish, restaurant


@pytest.fixture
def catalog_data(session):
    pakistani = restaurant(
        name="Pakistani Kitchen",
        city="Karachi",
        cuisine_types=["Pakistani"],
        halal_status="claimed",
    )
    exact_short = restaurant(
        name="Pak Kitchen",
        city="Lahore",
        cuisine_types=["Pak"],
        halal_status="verified",
    )
    session.add_all([pakistani, exact_short])
    session.flush()
    chicken = dish(
        pakistani.id,
        name="Chicken Karahi",
        cuisine="Pakistani",
        price=Decimal("900"),
    )
    beef = dish(
        pakistani.id,
        name="Beef Karahi",
        cuisine="Pakistani",
        price=Decimal("1200"),
    )
    noodles = dish(
        exact_short.id,
        name="Vegetable Noodles",
        cuisine="Chinese",
        price=Decimal("700"),
    )
    session.add_all([chicken, beef, noodles])
    session.flush()
    now = datetime.now(UTC)
    active = Deal(
        restaurant_id=pakistani.id,
        title="Active Deal",
        description="Current sample",
        discount_percentage=Decimal("15"),
        starts_at=now - timedelta(days=1),
        ends_at=now + timedelta(days=1),
        is_active=True,
    )
    inactive = Deal(
        restaurant_id=exact_short.id,
        title="Inactive Deal",
        description="Inactive sample",
        discount_percentage=Decimal("10"),
        starts_at=now - timedelta(days=3),
        ends_at=now - timedelta(days=2),
        is_active=False,
    )
    session.add_all([active, inactive])
    session.commit()
    return {
        "restaurants": (pakistani, exact_short),
        "dishes": (chicken, beef, noodles),
        "deals": (active, inactive),
    }


def test_positive_restaurant_endpoints_match_contracts(client, catalog_data):
    restaurant_item = catalog_data["restaurants"][0]

    listing = client.get("/restaurants")
    detail = client.get(f"/restaurants/{restaurant_item.id}")
    menu = client.get(f"/restaurants/{restaurant_item.id}/dishes")

    assert listing.status_code == detail.status_code == menu.status_code == 200
    validate_contract("paginated-restaurants.schema.json", listing.json())
    validate_contract("restaurant.schema.json", detail.json())
    validate_contract("paginated-dishes.schema.json", menu.json())
    assert menu.json()["total"] == 2


def test_positive_dish_and_vector_endpoints_match_contracts(client, catalog_data):
    dish_item = catalog_data["dishes"][0]

    listing = client.get("/dishes")
    detail = client.get(f"/dishes/{dish_item.id}")
    vector = client.get(f"/dishes/{dish_item.id}/vector")

    assert listing.status_code == detail.status_code == vector.status_code == 200
    validate_contract("paginated-dishes.schema.json", listing.json())
    validate_contract("dish.schema.json", detail.json())
    validate_contract("dish-vector.schema.json", vector.json())


def test_positive_deal_endpoints_match_contract(client, catalog_data):
    deal = catalog_data["deals"][0]

    listing = client.get("/deals?active_only=false")
    detail = client.get(f"/deals/{deal.id}")

    assert listing.status_code == detail.status_code == 200
    assert listing.json()["total"] == 2
    for item in listing.json()["items"]:
        validate_contract("deal.schema.json", item)
    validate_contract("deal.schema.json", detail.json())


def test_restaurant_filters_are_exact_and_case_insensitive(client, catalog_data):
    city = client.get("/restaurants?city=karachi").json()
    cuisine = client.get("/restaurants?cuisine=pak").json()
    halal = client.get("/restaurants?halal_status=verified").json()

    assert [item["name"] for item in city["items"]] == ["Pakistani Kitchen"]
    assert [item["name"] for item in cuisine["items"]] == ["Pak Kitchen"]
    assert [item["name"] for item in halal["items"]] == ["Pak Kitchen"]


def test_dish_filters_cover_restaurant_cuisine_name_and_prices(client, catalog_data):
    restaurant_item = catalog_data["restaurants"][0]
    response = client.get(
        f"/dishes?restaurant={restaurant_item.id}&cuisine=pakistani&name=chicken"
        "&min_price=800&max_price=1000"
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["name"] == "Chicken Karahi"


def test_pagination_is_stable_for_all_list_endpoints(client, catalog_data):
    first_restaurant = client.get("/restaurants?limit=1&offset=0").json()
    second_restaurant = client.get("/restaurants?limit=1&offset=1").json()
    first_dish = client.get("/dishes?limit=1&offset=0").json()
    second_dish = client.get("/dishes?limit=1&offset=1").json()
    first_deal = client.get("/deals?active_only=false&limit=1&offset=0").json()
    second_deal = client.get("/deals?active_only=false&limit=1&offset=1").json()

    for first, second, total in (
        (first_restaurant, second_restaurant, 2),
        (first_dish, second_dish, 3),
        (first_deal, second_deal, 2),
    ):
        assert first["total"] == second["total"] == total
        assert len(first["items"]) == len(second["items"]) == 1
        assert first["items"][0]["id"] != second["items"][0]["id"]


def test_deal_filters_cover_active_state_and_restaurant(client, catalog_data):
    restaurant_item = catalog_data["restaurants"][0]

    active = client.get("/deals").json()
    by_restaurant = client.get(f"/deals?active_only=false&restaurant={restaurant_item.id}").json()

    assert active["total"] == 1
    assert active["items"][0]["title"] == "Active Deal"
    assert by_restaurant["total"] == 1
    assert by_restaurant["items"][0]["restaurant_id"] == str(restaurant_item.id)
