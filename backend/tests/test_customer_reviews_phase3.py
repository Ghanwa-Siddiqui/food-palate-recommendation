import uuid

import pytest

from app.main import app
from app.models.user import User
from app.repositories.ranking import RankingRepository
from app.services.data_core.review_processing import ProcessedReview, get_review_processor
from tests.factories import dish, restaurant


class FakeProcessor:
    def process(self, text, rating):
        return ProcessedReview(
            sentiment={1: 0.1, 2: 0.25, 3: 0.5, 4: 0.75, 5: 0.9}[rating],
            spice=0.75 if "spicy" in text else 0.0,
            oiliness=0.5 if "oily" in text else 0.0,
            tags=[word for word in ("spicy", "oily", "crispy") if word in text],
            embedding=[float(rating)] * 384,
        )


@pytest.fixture(autouse=True)
def processor():
    app.dependency_overrides[get_review_processor] = FakeProcessor
    yield
    app.dependency_overrides.pop(get_review_processor, None)


def setup_catalog(session, *, available=True, archived_at=None):
    customer = User(
        id=uuid.uuid4(), name="Public Diner", email="private@example.test", role="customer"
    )
    other = User(id=uuid.uuid4(), name="Other", email="other@example.test", role="customer")
    partner = User(
        id=uuid.uuid4(), name="Partner", email="partner@example.test", role="restaurant_partner"
    )
    place = restaurant(owner_id=partner.id, available=True)
    session.add_all([customer, other, partner, place])
    session.flush()
    menu_item = dish(place.id, availability=available, archived_at=archived_at)
    session.add(menu_item)
    session.commit()
    return customer, other, partner, menu_item


def headers(user):
    return {"X-Chaska-User-ID": str(user.id)}


def tried(client, user, menu_item, key="tried-event-0001"):
    return client.post(
        f"/users/{user.id}/interactions",
        headers=headers(user),
        json={"dish_id": str(menu_item.id), "action": "tried", "client_event_id": key},
    )


def payload(menu_item, **changes):
    value = {
        "dish_id": str(menu_item.id),
        "rating": 5,
        "text": "Delicious spicy and crispy dish.",
        "tried_confirmation": True,
        "show_display_name": False,
        "submission_key": "review-submit-0001",
    }
    value.update(changes)
    return value


def test_tried_and_review_creation_are_idempotent_and_private(client, session):
    customer, _, _, menu_item = setup_catalog(session)
    assert tried(client, customer, menu_item).status_code == 200
    assert tried(client, customer, menu_item).json()["duplicate"] is True
    created = client.post("/reviews", headers=headers(customer), json=payload(menu_item))
    assert created.status_code == 200
    assert created.json()["processing_status"] == "complete"
    repeated = client.post("/reviews", headers=headers(customer), json=payload(menu_item))
    assert repeated.json()["id"] == created.json()["id"]
    public = client.get(f"/reviews/{menu_item.id}").json()[0]
    assert public["reviewer_name"] == "Anonymous Chaska diner"
    assert not ({"user_id", "email", "review_embedding", "taste_vector"} & public.keys())


def test_review_requires_tried_and_enforces_validation_and_one_active(client, session):
    customer, _, _, menu_item = setup_catalog(session)
    assert (
        client.post("/reviews", headers=headers(customer), json=payload(menu_item)).status_code
        == 422
    )
    tried(client, customer, menu_item)
    assert (
        client.post(
            "/reviews", headers=headers(customer), json=payload(menu_item, rating=6)
        ).status_code
        == 422
    )
    assert (
        client.post("/reviews", headers=headers(customer), json=payload(menu_item)).status_code
        == 200
    )
    assert (
        client.post(
            "/reviews",
            headers=headers(customer),
            json=payload(menu_item, submission_key="another-review-key"),
        ).status_code
        == 409
    )


def test_own_edit_recomputes_and_cross_user_partner_denied(client, session):
    customer, other, partner, menu_item = setup_catalog(session)
    tried(client, customer, menu_item)
    review = client.post(
        "/reviews", headers=headers(customer), json=payload(menu_item, show_display_name=True)
    ).json()
    edited = client.put(
        f"/reviews/{review['id']}",
        headers=headers(customer),
        json={"rating": 1, "text": "Too oily and disappointing dish.", "show_display_name": True},
    )
    assert edited.status_code == 200
    summary = client.get(f"/reviews/{menu_item.id}/summary").json()
    assert summary["average_rating"] == 1 and summary["avg_sentiment"] == pytest.approx(0.1)
    assert (
        client.put(
            f"/reviews/{review['id']}",
            headers=headers(other),
            json={"rating": 4, "text": "A long enough review.", "show_display_name": False},
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"/reviews/{review['id']}",
            headers=headers(partner),
            json={"rating": 4, "text": "A long enough review.", "show_display_name": False},
        ).status_code
        == 403
    )
    assert client.get(f"/reviews/{menu_item.id}").json()[0]["reviewer_name"] == "Public Diner"


def test_unavailable_rejects_new_review_and_negative_does_not_boost(client, session):
    customer, _, _, menu_item = setup_catalog(session, available=False)
    tried(client, customer, menu_item)
    assert (
        client.post("/reviews", headers=headers(customer), json=payload(menu_item)).status_code
        == 409
    )
    menu_item.availability = True
    menu_item.review_average = 1
    menu_item.review_sentiment = 0.1
    session.commit()
    candidate = RankingRepository(session).list_candidates(customer.id)[0]
    assert candidate.review_sentiment == pytest.approx(0.1)
