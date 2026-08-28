import re
from pathlib import Path

import pytest

from app.image_assets import dish_image
from tests.test_web_integration import _csrf, _login

PICKS = {
    "Pakistani": [
        "Biryani",
        "Karahi",
        "Nihari",
        "Haleem",
        "Chicken Tikka",
        "Seekh Kebab",
    ],
    "Chinese": [
        "Chow Mein",
        "Fried Rice",
        "Manchurian",
        "Dumplings",
        "Hot and Sour Soup",
    ],
    "Italian": ["Pizza", "Pasta", "Lasagna", "Risotto", "Garlic Bread"],
    "Turkish": ["Adana Kebab", "Doner Kebab", "Pide", "Lahmacun", "Turkish Kofta"],
    "Japanese": ["Sushi", "Ramen", "Tempura", "Teriyaki Chicken"],
    "Thai": ["Pad Thai", "Thai Curry", "Tom Yum", "Thai Fried Rice"],
    "Continental": ["Grilled Chicken", "Steak", "Soup", "Salad", "Roast Chicken"],
    "Fast Food": ["Burger", "Fried Chicken", "Loaded Fries", "Sandwich", "Shawarma"],
}


def _select_cuisines(client, cuisines):
    first = client.get("/onboarding/1")
    response = client.post(
        "/onboarding/1",
        data={
            "csrf_token": _csrf(first),
            "city": "Lahore",
            "preferred_cuisines": cuisines,
        },
        follow_redirects=False,
    )
    assert response.headers["location"] == "/onboarding/2"
    return client.get("/onboarding/2")


def _rendered_picks(response):
    return re.findall(r'data-favourite-suggestion="([^"]+)"', response.text)


@pytest.mark.parametrize(("cuisine", "expected"), PICKS.items())
def test_individual_cuisine_has_only_its_quick_picks(
    web_client, backend_client, cuisine, expected
):
    _login(web_client, backend_client, onboarded=False)
    response = _select_cuisines(web_client, [cuisine])

    assert _rendered_picks(response) == expected
    if cuisine == "Chinese":
        assert "Biryani" not in _rendered_picks(response)
    for dish in expected:
        assert dish_image(dish, cuisine)["src"] in response.text


def test_multiple_cuisines_are_balanced_unique_and_capped(web_client, backend_client):
    _login(web_client, backend_client, onboarded=False)
    response = _select_cuisines(web_client, ["Chinese", "Italian", "Thai"])
    picks = _rendered_picks(response)

    assert picks == [
        "Chow Mein",
        "Pizza",
        "Pad Thai",
        "Fried Rice",
        "Pasta",
        "Thai Curry",
        "Manchurian",
        "Lasagna",
        "Tom Yum",
        "Dumplings",
    ]
    assert len(picks) == len(set(map(str.casefold, picks))) == 10


def test_turkish_thai_mix_stays_balanced_and_compatible(web_client, backend_client):
    _login(web_client, backend_client, onboarded=False)
    response = _select_cuisines(web_client, ["Turkish", "Thai"])

    assert _rendered_picks(response) == [
        "Adana Kebab",
        "Pad Thai",
        "Doner Kebab",
        "Thai Curry",
        "Pide",
        "Tom Yum",
        "Lahmacun",
        "Thai Fried Rice",
        "Turkish Kofta",
    ]
    for dish, cuisine in zip(
        _rendered_picks(response), ["Turkish", "Thai"] * 4 + ["Turkish"]
    ):
        assert dish_image(dish, cuisine)["src"] in response.text


def test_no_selection_uses_varied_neutral_fallback(web_client, backend_client):
    _login(web_client, backend_client, onboarded=False)
    picks = _rendered_picks(web_client.get("/onboarding/2"))

    assert picks == [
        "Biryani",
        "Chow Mein",
        "Pizza",
        "Adana Kebab",
        "Sushi",
        "Pad Thai",
        "Grilled Chicken",
        "Burger",
    ]


def test_back_continue_and_validation_preserve_cuisines_and_dishes(
    web_client, backend_client
):
    _login(web_client, backend_client, onboarded=False)
    second = _select_cuisines(web_client, ["Chinese"])
    back = web_client.post(
        "/onboarding/2",
        data={
            "csrf_token": _csrf(second),
            "direction": "back",
            "favourite_dishes": ["Chow Mein", "Custom Noodle Bowl"],
        },
        follow_redirects=False,
    )
    assert back.headers["location"] == "/onboarding/1"
    first = web_client.get("/onboarding/1")
    assert 'value="Chinese" checked' in first.text
    second = _select_cuisines(web_client, ["Chinese"])
    assert "Custom Noodle Bowl" in second.text

    invalid = web_client.post(
        "/onboarding/2",
        data={
            "csrf_token": _csrf(second),
            "favourite_dishes": ["Chow Mein", "Custom Noodle Bowl"],
        },
    )
    assert invalid.status_code == 422
    assert "Chow Mein" in invalid.text and "Custom Noodle Bowl" in invalid.text
    assert _rendered_picks(invalid) == PICKS["Chinese"]


def test_quick_pick_progressive_enhancement_adds_tags_without_duplicates():
    script = Path("app/static/preferences.js").read_text(encoding="utf-8")

    assert "[data-favourite-suggestion]" in script
    assert 'checkbox.addEventListener("change"' in script
    assert (
        'querySelectorAll("[data-favourite-suggestion]").forEach((button) => '
        'button.addEventListener("click"'
    ) not in script
    assert 'data-tag-editor][data-name="favourite_dishes"]' in script
    assert "!tags.some" in script
    assert "Remove ${tag}" in script
    assert "matchingPick.checked = false" in script
    assert "data-favourite-count" in script
    assert "continueButton.disabled = tags.length < 3" in script


def test_step_two_uses_single_border_cards_and_accessible_selection_status(
    web_client, backend_client
):
    _login(web_client, backend_client, onboarded=False)
    response = _select_cuisines(web_client, ["Chinese"])

    assert 'class="favourite-pick-grid"' in response.text
    assert 'class="quick-pick-card"' in response.text
    assert 'type="checkbox" name="favourite_dishes"' in response.text
    assert '<button class="favourite-pick' not in response.text
    assert "choice visual-choice favourite" not in response.text
    assert "aria-pressed" not in response.text
    assert 'data-favourite-count aria-live="polite"' in response.text
    assert "Choose at least three or add your own." in response.text
    assert "data-favourite-continue" in response.text


def test_step_two_css_has_responsive_grid_and_touch_targets():
    stylesheet = Path("app/static/namak.css").read_text(encoding="utf-8")

    assert "grid-template-columns:repeat(3,minmax(0,1fr))" in stylesheet
    assert (
        "@media(max-width:980px){.favourite-pick-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}"
        in stylesheet
    )
    assert "@media(max-width:520px)" in stylesheet
    assert ".quick-pick-card{" in stylesheet
    assert ".quick-pick-card:has(input:checked)" in stylesheet
    assert ".quick-pick-card:has(input:checked) .quick-pick-indicator" in stylesheet
    assert "min-height:44px" in stylesheet
