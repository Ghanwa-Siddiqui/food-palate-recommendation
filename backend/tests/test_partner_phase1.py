import uuid

from app.models.user import User


def _user(role: str) -> User:
    user_id = uuid.uuid4()
    return User(
        id=user_id,
        name=f"{role} user",
        email=f"{user_id}@example.test",
        role=role,
    )


def _payload(**overrides):
    values = {
        "name": "Partner Kitchen",
        "description": "Partner-managed restaurant profile",
        "address": "Main Boulevard, Lahore",
        "city": "Lahore",
        "cuisine_types": ["Pakistani"],
        "contact_phone": "+92 300 1234567",
        "halal_status": "claimed",
        "halal_verification_status": "pending",
        "lat": 31.5204,
        "lng": 74.3587,
        "opening_information": "Daily 12:00–23:00",
        "available": True,
        "image_path": "/static/images/restaurant-warm-interior.webp",
        "price_range": "moderate",
    }
    values.update(overrides)
    return values


def test_user_sync_defaults_customer_and_accepts_partner_role(client):
    customer_id = uuid.uuid4()
    partner_id = uuid.uuid4()
    customer = client.post(
        "/users/sync",
        json={
            "id": str(customer_id),
            "name": "Customer",
            "email": "customer@example.test",
        },
    )
    partner = client.post(
        "/users/sync",
        json={
            "id": str(partner_id),
            "name": "Partner",
            "email": "partner@example.test",
            "role": "restaurant_partner",
        },
    )
    assert customer.json()["role"] == "customer"
    assert partner.json()["role"] == "restaurant_partner"


def test_partner_create_list_and_update(client, session):
    partner = _user("restaurant_partner")
    session.add(partner)
    session.commit()
    headers = {"X-Chaska-User-ID": str(partner.id)}
    created = client.post("/partner/restaurants", headers=headers, json=_payload())
    assert created.status_code == 201
    assert created.json()["owner_id"] == str(partner.id)
    assert created.json()["location_verified"] is False
    restaurant_id = created.json()["id"]
    listing = client.get("/partner/restaurants", headers=headers)
    assert [item["id"] for item in listing.json()] == [restaurant_id]
    updated = client.put(
        f"/partner/restaurants/{restaurant_id}",
        headers=headers,
        json=_payload(name="Updated Kitchen", available=False),
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Kitchen"
    assert updated.json()["available"] is False


def test_partner_ownership_and_customer_authorization(client, session):
    owner = _user("restaurant_partner")
    other = _user("restaurant_partner")
    customer = _user("customer")
    session.add_all([owner, other, customer])
    session.commit()
    created = client.post(
        "/partner/restaurants",
        headers={"X-Chaska-User-ID": str(owner.id)},
        json=_payload(),
    )
    restaurant_id = created.json()["id"]
    denied = client.put(
        f"/partner/restaurants/{restaurant_id}",
        headers={"X-Chaska-User-ID": str(other.id)},
        json=_payload(name="Stolen profile"),
    )
    assert denied.status_code == 403
    assert (
        client.get(
            "/partner/restaurants",
            headers={"X-Chaska-User-ID": str(customer.id)},
        ).status_code
        == 403
    )


def test_partner_validation_rejects_partial_coordinates_and_external_image(client, session):
    partner = _user("restaurant_partner")
    session.add(partner)
    session.commit()
    headers = {"X-Chaska-User-ID": str(partner.id)}
    partial = client.post("/partner/restaurants", headers=headers, json=_payload(lng=None))
    external = client.post(
        "/partner/restaurants",
        headers=headers,
        json=_payload(image_path="https://example.test/image.jpg"),
    )
    assert partial.status_code == 422
    assert external.status_code == 422
