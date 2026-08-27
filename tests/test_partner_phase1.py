import re
from uuid import uuid4


def _csrf(response) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match
    return match.group(1)


def _login(client, backend, *, role="restaurant_partner"):
    backend.profile = backend.profile.model_copy(
        update={"role": role, "onboarding_complete": role == "customer"}
    )
    page = client.get("/login")
    return client.post(
        "/login",
        data={
            "csrf_token": _csrf(page),
            "email": "test@example.com",
            "password": "password123",
        },
        follow_redirects=False,
    )


def _restaurant_form(csrf: str, **overrides):
    values = {
        "csrf_token": csrf,
        "name": "Partner Kitchen",
        "description": "A real partner-managed profile.",
        "address": "Main Boulevard, Lahore",
        "city": "Lahore",
        "cuisine_types": "Pakistani, Continental",
        "contact_phone": "+92 300 1234567",
        "halal_status": "claimed",
        "halal_verification_status": "pending",
        "lat": "31.5204",
        "lng": "74.3587",
        "opening_information": "Daily 12:00–23:00",
        "available": "true",
        "price_range": "moderate",
    }
    values.update(overrides)
    return values


def test_partner_signup_and_onboarding_redirect(web_client, backend_client):
    page = web_client.get("/signup")
    assert "I represent a restaurant" in page.text
    response = web_client.post(
        "/signup",
        data={
            "csrf_token": _csrf(page),
            "name": "Restaurant Owner",
            "email": "owner@example.test",
            "password": "password123",
            "account_type": "restaurant_partner",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/partner/onboarding"
    assert backend_client.profile.role == "restaurant_partner"
    onboarding = web_client.get("/partner/onboarding")
    assert onboarding.status_code == 200
    assert "Tell us about your restaurant" in onboarding.text


def test_partner_create_update_and_dashboard(web_client, backend_client):
    _login(web_client, backend_client)
    form_page = web_client.get("/partner/onboarding")
    created = web_client.post(
        "/partner/restaurants",
        data=_restaurant_form(_csrf(form_page)),
        follow_redirects=False,
    )
    assert created.status_code == 303
    assert created.headers["location"] == "/partner/dashboard?created=1"
    dashboard = web_client.get("/partner/dashboard")
    assert dashboard.status_code == 200
    assert "Partner Kitchen" in dashboard.text
    edit = web_client.get(f"/partner/restaurants/{backend_client.restaurant.id}/edit")
    updated = web_client.post(
        f"/partner/restaurants/{backend_client.restaurant.id}",
        data=_restaurant_form(_csrf(edit), name="Updated Partner Kitchen"),
        follow_redirects=False,
    )
    assert updated.status_code == 303
    assert backend_client.restaurant.name == "Updated Partner Kitchen"


def test_customer_and_cross_partner_access_denied(web_client, backend_client):
    _login(web_client, backend_client, role="customer")
    assert web_client.get("/partner/dashboard").status_code == 403

    web_client.post("/logout", data={"csrf_token": _csrf(web_client.get("/login"))})
    _login(web_client, backend_client)
    backend_client.restaurant = backend_client.restaurant.model_copy(
        update={"owner_id": uuid4()}
    )
    response = web_client.get(
        f"/partner/restaurants/{backend_client.restaurant.id}/edit"
    )
    assert response.status_code == 403


def test_partner_csrf_and_validation(web_client, backend_client):
    _login(web_client, backend_client)
    assert web_client.post("/partner/restaurants", data={}).status_code == 403
    page = web_client.get("/partner/onboarding")
    invalid = web_client.post(
        "/partner/restaurants",
        data=_restaurant_form(_csrf(page), cuisine_types="", lat="", lng=""),
    )
    assert invalid.status_code == 422
    assert "Add at least one cuisine" in invalid.text
