import uuid

from app.main import app
from app.models.dish import Dish
from app.models.user import User
from app.services.data_core.dish_profiles import get_dish_embedding_service
from app.services.data_core.review_processing import ProcessedReview, get_review_processor
from tests.factories import restaurant

VECTOR = [1.0] + [0.0] * 383


class FakeDishEmbedding:
    def generate(self, _profile):
        return VECTOR


class FakeReviewProcessor:
    def process(self, text, rating):
        return ProcessedReview(0.9, 0.7, 0.2, ["spicy", "rich"], VECTOR)


def dish_payload(restaurant_id, name):
    return {
        "restaurant_id": str(restaurant_id),
        "name": name,
        "description": f"A complete {name} profile",
        "cuisine": "Pakistani",
        "price": 900,
        "availability": True,
        "ingredients": ["rice", "chicken"],
        "allergens": [],
        "dietary_tags": ["halal"],
        "preparation_style": "stovetop",
        "spice_level": 4,
        "sweetness": 1,
        "sourness": 1,
        "saltiness": 3,
        "oiliness": 2,
        "richness": 4,
        "smokiness": 1,
        "texture_tags": ["tender"],
    }


def headers(user):
    return {"X-Chaska-User-ID": str(user.id)}


def interact(client, user, dish_id, action):
    return client.post(
        f"/users/{user.id}/interactions",
        headers=headers(user),
        json={
            "dish_id": dish_id,
            "action": action,
            "client_event_id": f"{action}-{uuid.uuid4()}",
        },
    )


def test_customer_partner_review_intelligence_and_taste_twin_journey(client, session):
    app.dependency_overrides[get_dish_embedding_service] = FakeDishEmbedding
    app.dependency_overrides[get_review_processor] = FakeReviewProcessor
    partner = User(name="Partner", email="partner-journey@example.test", role="restaurant_partner")
    customer = User(
        name="Customer",
        email="customer-journey@example.test",
        role="customer",
        onboarding_complete=True,
        taste_vector=VECTOR,
    )
    twin = User(
        name="Maham",
        email="twin-journey@example.test",
        role="customer",
        onboarding_complete=True,
        taste_vector=VECTOR,
        show_review_display_name=True,
    )
    session.add_all([partner, customer, twin])
    session.flush()
    owned = restaurant(owner_id=partner.id, name="Partner Kitchen", available=True)
    session.add(owned)
    session.commit()

    shared = client.post(
        "/partner/dishes",
        headers={**headers(partner), "X-Idempotency-Key": "journey-shared-dish"},
        json=dish_payload(owned.id, "Chicken Biryani"),
    )
    discovery = client.post(
        "/partner/dishes",
        headers={**headers(partner), "X-Idempotency-Key": "journey-discovery-dish"},
        json=dish_payload(owned.id, "Mutton Pulao"),
    )
    assert shared.status_code == discovery.status_code == 201
    shared_id, discovery_id = shared.json()["id"], discovery.json()["id"]
    assert len(session.get(Dish, uuid.UUID(shared_id)).embedding) == 384
    assert client.get(f"/ranking/feed/{customer.id}").json()["total_candidates"] == 2

    assert interact(client, customer, shared_id, "tried").status_code == 200
    assert interact(client, customer, shared_id, "like").status_code == 200
    customer_review = client.post(
        "/reviews",
        headers=headers(customer),
        json={
            "dish_id": shared_id,
            "rating": 5,
            "text": "Spicy rich biryani that I loved.",
            "tried_confirmation": True,
            "show_display_name": False,
            "submission_key": "journey-customer-review",
        },
    )
    assert customer_review.json()["processing_status"] == "complete"

    interact(client, twin, shared_id, "like")
    interact(client, twin, discovery_id, "tried")
    twin_review = client.post(
        "/reviews",
        headers=headers(twin),
        json={
            "dish_id": discovery_id,
            "rating": 5,
            "text": "Excellent rich pulao with balanced spice.",
            "tried_confirmation": True,
            "show_display_name": True,
            "submission_key": "journey-twin-review",
        },
    )
    assert twin_review.status_code == 200
    feed = client.get(f"/ranking/feed/{customer.id}").json()
    recommended = next(item for item in feed["items"] if item["dish_id"] == discovery_id)
    assert feed["collaborative_available"] is True
    assert recommended["collaborative_reviewer_name"] == "Maham"
    assert "Excellent rich pulao" in recommended["collaborative_review_excerpt"]
