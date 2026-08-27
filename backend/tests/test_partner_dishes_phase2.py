import uuid
from datetime import datetime

import pytest

from app.main import app
from app.models.dish import Dish
from app.models.user import User
from app.repositories.ranking import RankingRepository
from app.services.data_core.dish_profiles import get_dish_embedding_service
from tests.factories import restaurant


class FakeEmbeddingService:
    def __init__(self):
        self.calls = 0

    def generate(self, profile):
        self.calls += 1
        return [float(self.calls)] * 384


@pytest.fixture
def embedding_service():
    service = FakeEmbeddingService()
    app.dependency_overrides[get_dish_embedding_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_dish_embedding_service, None)


def _user(role="restaurant_partner"):
    user_id = uuid.uuid4()
    return User(
        id=user_id,
        name=f"{role} user",
        email=f"{user_id}@example.test",
        role=role,
    )


def _payload(restaurant_id, **overrides):
    values = {
        "restaurant_id": str(restaurant_id),
        "name": "Partner Karahi",
        "description": "Tomato-forward chicken karahi",
        "cuisine": "Pakistani",
        "price": 1250,
        "availability": True,
        "ingredients": ["chicken", "tomato", "ginger"],
        "allergens": ["dairy"],
        "dietary_tags": ["high-protein"],
        "preparation_style": "stovetop",
        "image_path": "/static/images/neutral-food-fallback.webp",
        "spice_level": 4,
        "sweetness": 1,
        "sourness": 2,
        "saltiness": 3,
        "oiliness": 3,
        "richness": 4,
        "smokiness": 1,
        "texture_tags": ["tender", "saucy"],
    }
    values.update(overrides)
    return values


def _setup(session):
    owner = _user()
    other = _user()
    customer = _user("customer")
    owned = restaurant(owner_id=owner.id, available=True)
    foreign = restaurant(owner_id=other.id, name="Other Kitchen", available=True)
    session.add_all([owner, other, customer, owned, foreign])
    session.commit()
    return owner, other, customer, owned, foreign


def _headers(user, key=None):
    values = {"X-Chaska-User-ID": str(user.id)}
    if key:
        values["X-Idempotency-Key"] = key
    return values


def test_owned_menu_create_and_idempotent_vector(client, session, embedding_service):
    owner, _, _, owned, _ = _setup(session)
    key = "create-dish-key-00000001"
    created = client.post(
        "/partner/dishes",
        headers=_headers(owner, key),
        json=_payload(owned.id),
    )
    repeated = client.post(
        "/partner/dishes",
        headers=_headers(owner, key),
        json=_payload(owned.id),
    )
    assert created.status_code == 201
    assert repeated.json()["id"] == created.json()["id"]
    assert embedding_service.calls == 1
    dish = session.get(Dish, uuid.UUID(created.json()["id"]))
    assert len(dish.embedding) == 384
    assert dish.embedding_updated_at is not None
    listing = client.get(f"/partner/restaurants/{owned.id}/dishes", headers=_headers(owner))
    assert [item["name"] for item in listing.json()] == ["Partner Karahi"]


def test_update_refreshes_vector_and_preserves_profile_lists(client, session, embedding_service):
    owner, _, _, owned, _ = _setup(session)
    created = client.post(
        "/partner/dishes",
        headers=_headers(owner, "create-dish-key-00000002"),
        json=_payload(owned.id),
    ).json()
    dish_id = created["id"]
    before = created["embedding_updated_at"]
    updated_payload = _payload(
        owned.id,
        name="Updated Karahi",
        ingredients=["chicken", "tomato"],
        allergens=["dairy", "nuts"],
        dietary_tags=["high-protein", "low-carb"],
        texture_tags=["tender"],
        spice_level=5,
    )
    updated_payload.pop("restaurant_id")
    updated = client.put(
        f"/partner/dishes/{dish_id}",
        headers=_headers(owner),
        json=updated_payload,
    )
    assert updated.status_code == 200
    assert updated.json()["ingredients"] == ["chicken", "tomato"]
    assert updated.json()["allergens"] == ["dairy", "nuts"]
    assert updated.json()["dietary_tags"] == ["high-protein", "low-carb"]
    assert embedding_service.calls == 2
    assert updated.json()["embedding_updated_at"] >= before


@pytest.mark.parametrize("field,value", [("spice_level", 6), ("sweetness", -1)])
def test_taste_profile_bounds(client, session, embedding_service, field, value):
    owner, _, _, owned, _ = _setup(session)
    response = client.post(
        "/partner/dishes",
        headers=_headers(owner, f"invalid-profile-{field}"),
        json=_payload(owned.id, **{field: value}),
    )
    assert response.status_code == 422
    assert embedding_service.calls == 0


def test_browser_supplied_vector_is_rejected(client, session, embedding_service):
    owner, _, _, owned, _ = _setup(session)
    response = client.post(
        "/partner/dishes",
        headers=_headers(owner, "browser-vector-key-00001"),
        json=_payload(owned.id, embedding=[9.0] * 384),
    )
    assert response.status_code == 422
    assert embedding_service.calls == 0


def test_customer_foreign_restaurant_and_dish_access_denied(client, session, embedding_service):
    owner, other, customer, owned, foreign = _setup(session)
    assert (
        client.post(
            "/partner/dishes",
            headers=_headers(owner, "foreign-dish-key-000001"),
            json=_payload(foreign.id),
        ).status_code
        == 403
    )
    created = client.post(
        "/partner/dishes",
        headers=_headers(owner, "owned-dish-key-0000001"),
        json=_payload(owned.id),
    ).json()
    assert (
        client.get(f"/partner/dishes/{created['id']}", headers=_headers(other)).status_code == 403
    )
    assert (
        client.get(f"/partner/dishes/{created['id']}", headers=_headers(customer)).status_code
        == 403
    )


def test_eligible_availability_and_archive_candidate_exclusion(client, session, embedding_service):
    owner, _, _, owned, _ = _setup(session)
    created = client.post(
        "/partner/dishes",
        headers=_headers(owner, "candidate-dish-key-00001"),
        json=_payload(owned.id),
    ).json()
    dish_id = created["id"]
    assert [str(item.dish.id) for item in RankingRepository(session).list_candidates()] == [dish_id]
    client.post(
        f"/partner/dishes/{dish_id}/availability?available=false",
        headers=_headers(owner),
    )
    assert RankingRepository(session).list_candidates() == []
    client.post(
        f"/partner/dishes/{dish_id}/availability?available=true",
        headers=_headers(owner),
    )
    archived = client.post(f"/partner/dishes/{dish_id}/archive", headers=_headers(owner))
    assert archived.status_code == 200
    assert archived.json()["availability"] is False
    assert datetime.fromisoformat(archived.json()["archived_at"])
    assert RankingRepository(session).list_candidates() == []
