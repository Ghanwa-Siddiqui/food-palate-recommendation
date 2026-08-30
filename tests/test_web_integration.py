import re

from app.auth import AuthUnavailableError, InvalidCredentialsError


def _csrf(response) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match
    return match.group(1)


def _login(client, backend, *, onboarded=True):
    backend.profile = backend.profile.model_copy(
        update={"onboarding_complete": onboarded}
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


def test_landing_auth_and_protected_redirect(web_client, backend_client):
    landing = web_client.get("/")
    assert landing.status_code == 200
    assert "Restaurants that" in landing.text
    response = web_client.get("/app/feed", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")
    assert _login(web_client, backend_client).headers["location"] == "/app/feed"


def test_login_validation_and_expired_session(
    web_client, backend_client, auth_provider
):
    page = web_client.get("/login")
    bad = web_client.post(
        "/login",
        data={
            "csrf_token": _csrf(page),
            "email": "bad@example.com",
            "password": "wrong",
        },
    )
    assert bad.status_code == 401
    assert "Email or password is incorrect" in bad.text
    _login(web_client, backend_client)
    auth_provider.valid_tokens.clear()
    auth_provider.refresh = lambda _token: (_ for _ in ()).throw(
        InvalidCredentialsError()
    )
    expired = web_client.get("/app/feed", follow_redirects=False)
    assert expired.status_code == 303
    assert expired.headers["location"].startswith("/login")


def test_signup_validation_duplicate_and_sync(
    web_client, backend_client, auth_provider
):
    page = web_client.get("/signup")
    short = web_client.post(
        "/signup",
        data={
            "csrf_token": _csrf(page),
            "name": "A",
            "email": "new@example.com",
            "password": "short",
        },
    )
    assert short.status_code == 422
    assert "at least 8 characters" in short.text

    page = web_client.get("/signup")
    duplicate = web_client.post(
        "/signup",
        data={
            "csrf_token": _csrf(page),
            "name": "Test Eater",
            "email": auth_provider.user.email,
            "password": "password123",
        },
    )
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.text

    page = web_client.get("/signup")
    created = web_client.post(
        "/signup",
        data={
            "csrf_token": _csrf(page),
            "name": "New Eater",
            "email": "new@example.com",
            "password": "password123",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    assert created.headers["location"] == "/onboarding/1"
    assert backend_client.profile.email == "new@example.com"


def test_successful_auth_failed_sync_is_recoverable_on_login(
    web_client, backend_client
):
    backend_client.fail = True
    page = web_client.get("/signup")
    signup = web_client.post(
        "/signup",
        data={
            "csrf_token": _csrf(page),
            "name": "Recoverable User",
            "email": "recoverable@example.test",
            "password": "password123",
        },
        follow_redirects=False,
    )

    assert signup.status_code == 503
    assert "account was created" in signup.text
    assert "Do not create the account again" in signup.text
    assert backend_client.sync_calls == 1

    backend_client.fail = False
    page = web_client.get("/login")
    login = web_client.post(
        "/login",
        data={
            "csrf_token": _csrf(page),
            "email": "recoverable@example.test",
            "password": "password123",
        },
        follow_redirects=False,
    )

    assert login.status_code == 303
    assert login.headers["location"] == "/onboarding/1"
    assert backend_client.sync_calls == 2
    assert backend_client.profile.email == "recoverable@example.test"


def test_signup_does_not_expose_sensitive_auth_failure(web_client, auth_provider):
    sensitive = "private@example.test private-password access-token api-key"

    def fail_signup(*_args):
        raise AuthUnavailableError() from RuntimeError(sensitive)

    auth_provider.signup = fail_signup
    page = web_client.get("/signup")

    response = web_client.post(
        "/signup",
        data={
            "csrf_token": _csrf(page),
            "name": "Private User",
            "email": "private@example.test",
            "password": "private-password",
        },
    )

    assert response.status_code == 503
    assert "Authentication is temporarily unavailable" in response.text
    for value in sensitive.split():
        assert value not in response.text


def test_feed_success_empty_error_filters_and_images(web_client, backend_client):
    _login(web_client, backend_client)
    success = web_client.get("/app/feed?search=karahi&budget_max=1500")
    assert success.status_code == 200
    assert "Chicken Karahi" in success.text
    assert "92%" in success.text
    assert "/static/images/chicken-karahi.webp" in success.text
    assert 'loading="lazy"' in success.text
    assert "Food profile match" in success.text
    assert "fx-signal-review" not in success.text

    backend_client.empty = True
    empty = web_client.get("/app/feed")
    assert "No dishes match these filters" in empty.text
    backend_client.empty = False
    backend_client.fail = True
    failed = web_client.get("/app/feed")
    assert failed.status_code == 200
    assert "Recommendations are unavailable" in failed.text


def test_onboarding_persists_complete_384_vector(web_client, backend_client):
    _login(web_client, backend_client, onboarded=False)
    page = web_client.get("/onboarding/1")
    response = web_client.post(
        "/onboarding/1",
        data={
            "csrf_token": _csrf(page),
            "city": "Lahore",
            "preferred_cuisines": "Pakistani",
        },
        follow_redirects=False,
    )
    assert response.headers["location"] == "/onboarding/2"
    for step, data in (
        (
            2,
            {
                "favourite_dishes_text": "Karahi, Biryani, karahi, Pizza",
            },
        ),
        (
            3,
            {
                "spice_preference": "4",
                "sweetness_preference": "2",
                "sourness_preference": "2",
                "saltiness_preference": "3",
                "oiliness_preference": "2",
                "richness_preference": "4",
            },
        ),
        (
            4,
            {
                "preferred_textures": ["tender", "crispy"],
                "dietary_requirements": "",
                "allergies_text": "Peanuts, peanuts",
                "disliked_ingredients_text": "Olives",
                "require_halal": "true",
            },
        ),
    ):
        page = web_client.get(f"/onboarding/{step}")
        response = web_client.post(
            f"/onboarding/{step}",
            data={"csrf_token": _csrf(page), **data},
            follow_redirects=False,
        )
    assert response.status_code == 200
    assert "Your food personality is ready" in response.text
    assert backend_client.profile.onboarding_complete
    assert backend_client.profile.preferred_cuisines == ["Pakistani"]
    assert backend_client.profile.favourite_dishes == ["Karahi", "Biryani", "Pizza"]
    assert backend_client.profile.preferred_textures == ["tender", "crispy"]
    assert backend_client.profile.allergies == ["Peanuts"]
    assert backend_client.profile.disliked_ingredients == ["Olives"]
    assert backend_client.profile.require_halal is True
    assert len(backend_client.last_profile_payload["taste_vector"]) == 384


def test_interactions_are_idempotent_and_rerank(web_client, backend_client):
    _login(web_client, backend_client)
    page = web_client.get("/app/feed")
    token = _csrf(page)
    payload = {
        "csrf_token": token,
        "dish_id": str(backend_client.dish.id),
        "action": "click",
        "event_id": "browser-event-1",
        "next": "/app/feed",
    }
    first = web_client.post("/app/interactions", data=payload, follow_redirects=False)
    second = web_client.post("/app/interactions", data=payload, follow_redirects=False)
    assert first.status_code == second.status_code == 303
    assert len(backend_client.actions) == 1
    payload.update(action="save", event_id="browser-event-2")
    web_client.post("/app/interactions", data=payload, follow_redirects=False)
    reranked = web_client.get("/app/feed")
    assert "94%" in reranked.text
    assert "Saved ✓" in reranked.text


def test_restaurant_dish_profile_saved_and_logout(web_client, backend_client):
    _login(web_client, backend_client)
    restaurant = web_client.get(f"/app/restaurants/{backend_client.restaurant.id}")
    assert restaurant.status_code == 200
    assert "Real Restaurant" in restaurant.text
    assert "No reviews yet" in restaurant.text
    dish = web_client.get(f"/app/dishes/{backend_client.dish.id}")
    assert dish.status_code == 200
    assert "Ingredients" in dish.text
    assert "No reviews are available yet" in dish.text
    assert web_client.get("/app/profile").status_code == 200
    assert "Test Eater" in web_client.get("/app/profile").text
    assert "Nothing saved yet" in web_client.get("/app/saved").text
    page = web_client.get("/app/profile")
    logged_out = web_client.post(
        "/logout", data={"csrf_token": _csrf(page)}, follow_redirects=False
    )
    assert logged_out.status_code == 303
    assert logged_out.headers["location"] == "/login?logged_out=1"
