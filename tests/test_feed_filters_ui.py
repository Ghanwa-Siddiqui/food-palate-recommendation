import re
from pathlib import Path

from app.backend_client import FeedResult


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
    }
    assert not {"max_distance_km", "user_lat", "user_lng"} & {
        name for name, _ in captured
    }
    assert "5 active" in response.text
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
    response = web_client.get("/app/feed?budget_min=2000&budget_max=500")

    assert response.status_code == 200 and calls == 0
    assert "Minimum budget cannot exceed maximum budget" in response.text
    assert "Filters need attention" in response.text

    non_finite = web_client.get("/app/feed?budget_min=nan")
    assert non_finite.status_code == 200 and calls == 0
    assert "Minimum budget must be a finite number" in non_finite.text


def test_feed_success_empty_error_and_complete_cards(web_client, backend_client):
    _login(web_client, backend_client)
    success = web_client.get("/app/feed")
    for text in (
        "Chicken Karahi",
        "Real Restaurant",
        "PKR 1250",
        "92% match",
        "Food profile match",
        "Save dish",
        "Open dish",
        "Order interest",
    ):
        assert text in success.text
    assert "fx-signal-review" not in success.text

    backend_client.empty = True
    assert "No dishes match these filters" in web_client.get("/app/feed").text
    backend_client.empty = False
    backend_client.fail = True
    failed = web_client.get("/app/feed?search=karahi")
    assert "Recommendations are unavailable" in failed.text
    assert 'value="karahi"' in failed.text


def test_feed_renders_only_safe_persisted_twin_review_previews(
    web_client, backend_client, monkeypatch
):
    _login(web_client, backend_client)
    original = backend_client.get_feed

    def with_twin_reviews(user_id, params):
        payload = original(user_id, params).model_dump(mode="json")
        payload["items"][0].update(
            taste_twin_review_count=3,
            taste_twin_reviews=[
                {
                    "reviewer_name": "Maham",
                    "rating": 5,
                    "excerpt": "Spicy, aromatic and not too oily.",
                    "similarity_percent": 89,
                },
                {
                    "reviewer_name": "Anonymous Chaska diner",
                    "rating": 4,
                    "excerpt": "Rich flavour with tender chicken.",
                    "similarity_percent": 84,
                },
            ],
        )
        return FeedResult.model_validate(payload)

    monkeypatch.setattr(backend_client, "get_feed", with_twin_reviews)
    response = web_client.get("/app/feed")

    assert "89% taste twin match" in response.text
    assert "3 taste twins tried this" in response.text
    assert "+1 more" in response.text
    assert "Maham" in response.text and "Anonymous Chaska diner" in response.text
    assert "View all twin reviews" in response.text
    assert "@example" not in response.text and "taste_vector" not in response.text
    card_start = response.text.index('class="feed-card"')
    assert card_start < response.text.index("Food profile match")
    assert response.text.index("Food profile match") < response.text.index(
        "89% taste twin match"
    )
    assert response.text.index("89% taste twin match") < response.text.index(
        "feed-card-actions"
    )


def test_feed_hides_twin_section_without_evidence(web_client, backend_client):
    _login(web_client, backend_client)
    response = web_client.get("/app/feed")

    assert "fx-signal-twin" not in response.text
    assert "taste twin match" not in response.text


def test_feed_drawer_reset_and_responsive_contracts():
    template = Path("app/templates/namak/feed.html").read_text(encoding="utf-8")
    css = Path("app/static/feed.css").read_text(encoding="utf-8")

    assert 'aria-controls="feed-filters"' in template
    assert "aria-expanded','false" in template
    assert "event.key==='Escape'" in template
    assert "Maximum distance" not in template
    assert "Use my coordinates" not in template
    assert "navigator.geolocation" not in template
    assert "user_lat" not in template and "user_lng" not in template
    assert "swap('/app/feed',true)" in template
    assert "data-remove-filter" in template
    # Filters are an on-demand panel at every width now, not a sidebar that's
    # permanently docked open past some desktop breakpoint.
    assert "@media (min-width:981px)" not in css
    assert "position:fixed;z-index:51;top:0;bottom:0;left:0;" in css
    assert "grid-template-columns:288px" not in css
    assert "@media (max-width:560px)" in css
    assert ".feed-card-grid{grid-template-columns:minmax(0,1fr);}" in css
