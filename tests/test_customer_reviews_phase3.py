import re
from pathlib import Path
from uuid import UUID

DISH_ID = UUID("22222222-2222-4222-8222-222222222222")


def csrf(response):
    return re.search(r'name="csrf_token" value="([^"]+)"', response.text).group(1)


def login(client):
    page = client.get("/login")
    return client.post(
        "/login",
        data={
            "csrf_token": csrf(page),
            "email": "test@example.com",
            "password": "password123",
        },
    )


def test_dish_review_form_success_edit_and_safe_public_render(
    web_client, backend_client
):
    login(web_client)
    page = web_client.get(f"/app/dishes/{DISH_ID}")
    assert (
        "I tried this dish" in page.text and "No reviews are available yet" in page.text
    )
    token = csrf(page)
    event = re.search(r'name="submission_key" value="([^"]+)"', page.text).group(1)
    tried_event = re.search(r'name="tried_event_id" value="([^"]+)"', page.text).group(
        1
    )
    response = web_client.post(
        f"/app/dishes/{DISH_ID}/reviews",
        data={
            "csrf_token": token,
            "submission_key": event,
            "tried_event_id": tried_event,
            "tried_confirmation": "on",
            "rating": "5",
            "text": "Wonderful spicy karahi.",
            "show_display_name": "on",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303 and len(backend_client.reviews) == 1
    rendered = web_client.get(f"/app/dishes/{DISH_ID}")
    assert "Test Eater" in rendered.text and "Wonderful spicy karahi." in rendered.text
    assert "test@example.com" not in rendered.text


def test_review_csrf_and_validation_failure(web_client, backend_client):
    login(web_client)
    assert web_client.post(f"/app/dishes/{DISH_ID}/reviews", data={}).status_code == 403
    page = web_client.get(f"/app/dishes/{DISH_ID}")
    response = web_client.post(
        f"/app/dishes/{DISH_ID}/reviews",
        data={"csrf_token": csrf(page), "rating": "bad"},
        follow_redirects=False,
    )
    assert (
        response.status_code == 303
        and "review_error=validation" in response.headers["location"]
    )


def test_dish_detail_has_responsive_premium_structure(web_client):
    login(web_client)
    page = web_client.get(f"/app/dishes/{DISH_ID}")

    assert page.status_code == 200
    assert 'class="dish-hero"' in page.text
    assert 'class="dish-media"' in page.text
    assert 'class="dish-copy"' in page.text
    assert 'class="dish-match"' in page.text
    assert 'class="dish-facts"' in page.text
    assert 'class="review-composer"' in page.text
    assert 'class="review-list"' in page.text
    assert 'rows="7"' in page.text
    assert "data-character-count" in page.text
    assert "Share your experience" in page.text
    assert "minimum 10" in page.text
    assert page.text.count('action="/app/interactions"') == 5


def test_review_validation_preserves_entered_values(web_client):
    login(web_client)
    page = web_client.get(f"/app/dishes/{DISH_ID}")
    response = web_client.post(
        f"/app/dishes/{DISH_ID}/reviews",
        data={
            "csrf_token": csrf(page),
            "rating": "bad",
            "text": "Keep this useful review draft.",
            "tried_confirmation": "on",
            "show_display_name": "on",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Keep this useful review draft." in response.text
    assert 'name="tried_confirmation" required checked' in response.text
    assert 'name="show_display_name" checked' in response.text
    assert "Your entries have been preserved" in response.text


def test_dish_css_has_mobile_tablet_and_desktop_layout_contract():
    css = Path("app/static/namak.css").read_text(encoding="utf-8")

    assert ".dish-hero{display:grid" in css
    assert "grid-template-columns:minmax(0,1fr) minmax(0,1.04fr)" in css
    assert "@media(max-width:820px)" in css
    assert "@media(max-width:520px)" in css
    assert ".dish-hero{grid-template-columns:1fr" in css
    assert ".dish-actions form:first-child{width:100%}" in css
    assert ".dish-page{box-sizing:border-box" in css
