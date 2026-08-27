import re
from pathlib import Path


def _csrf(response) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match
    return match.group(1)


def _login(client, backend) -> None:
    backend.profile = backend.profile.model_copy(update={"onboarding_complete": True})
    page = client.get("/login")
    response = client.post(
        "/login",
        data={
            "csrf_token": _csrf(page),
            "email": "test@example.com",
            "password": "password123",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_every_feed_filter_reaches_ranking_and_state_is_visible(
    web_client, backend_client, monkeypatch
):
    _login(web_client, backend_client)
    captured = []
    original = backend_client.get_feed

    def capture(user_id, params):
        captured.extend(params)
        return original(user_id, params)

    monkeypatch.setattr(backend_client, "get_feed", capture)
    query = (
        "search=Pakistani&budget_min=400&budget_max=1800&require_halal=true&"
        "dietary_restrictions=vegetarian&max_distance_km=12.5&"
        "user_lat=31.5204&user_lng=74.3587"
    )
    response = web_client.get(f"/app/feed?{query}")

    assert response.status_code == 200
    assert set(captured) >= {
        ("search", "Pakistani"),
        ("budget_min", "400"),
        ("budget_max", "1800"),
        ("require_halal", "true"),
        ("dietary_restrictions", "vegetarian"),
        ("max_distance_km", "12.5"),
        ("user_lat", "31.5204"),
        ("user_lng", "74.3587"),
    }
    assert "6 active" in response.text
    assert 'value="Pakistani"' in response.text
    assert "Search: Pakistani" in response.text


def test_feed_filter_validation_blocks_bad_queries(
    web_client, backend_client, monkeypatch
):
    _login(web_client, backend_client)
    calls = 0

    def unexpected(*_args):
        nonlocal calls
        calls += 1

    monkeypatch.setattr(backend_client, "get_feed", unexpected)
    response = web_client.get(
        "/app/feed?budget_min=2000&budget_max=500&max_distance_km=10&user_lat=91"
    )

    assert response.status_code == 200 and calls == 0
    assert "Minimum budget cannot exceed maximum budget" in response.text
    assert "Latitude and longitude must be supplied together" in response.text
    assert "Maximum distance requires valid coordinates" in response.text
    assert "Filters need attention" in response.text


def test_feed_success_empty_error_and_complete_cards(web_client, backend_client):
    _login(web_client, backend_client)
    success = web_client.get("/app/feed")
    for text in (
        "Chicken Karahi",
        "Real Restaurant",
        "PKR 1250",
        "92% match",
        "Taste match",
        "Review insight",
        "Save dish",
        "Open dish",
        "Order interest",
    ):
        assert text in success.text

    backend_client.empty = True
    assert "No dishes match these filters" in web_client.get("/app/feed").text
    backend_client.empty = False
    backend_client.fail = True
    failed = web_client.get("/app/feed?search=karahi")
    assert "Recommendations are unavailable" in failed.text
    assert 'value="karahi"' in failed.text


def test_feed_drawer_geolocation_reset_and_responsive_contracts():
    template = Path("app/templates/namak/feed.html").read_text(encoding="utf-8")
    css = Path("app/static/namak.css").read_text(encoding="utf-8")

    assert 'aria-controls="feed-filters"' in template
    assert "aria-expanded','false" in template
    assert "event.key==='Escape'" in template
    assert "Requesting your location" in template
    assert "Coordinates ready" in template
    assert "Location permission was denied" in template
    assert "location is unavailable" in template
    assert "window.location.assign('/app/feed')" in template
    assert "data-remove-filter" in template
    assert ".feed-shell{box-sizing:border-box;width:min(1360px,100%)" in css
    assert "grid-template-columns:280px minmax(0,1fr)" in css
    assert "@media(max-width:980px)" in css
    assert "@media(max-width:700px)" in css
    assert ".feed-card-grid{grid-template-columns:1fr}" in css
