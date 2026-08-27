import re
from html.parser import HTMLParser

from tests.test_web_integration import _csrf, _login


class IdCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []

    def handle_starttag(self, _tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"])


def test_every_onboarding_step_has_progress_accessible_controls_and_no_duplicate_ids(
    web_client, backend_client
):
    _login(web_client, backend_client, onboarded=False)
    for step in range(1, 6):
        response = web_client.get(f"/onboarding/{step}")
        assert response.status_code == 200
        assert f"Step {step} of 5" in response.text
        assert 'aria-current="step"' in response.text
        assert 'class="quiz-layout"' in response.text
        parser = IdCollector()
        parser.feed(response.text)
        assert len(parser.ids) == len(set(parser.ids))
    flavour = web_client.get("/onboarding/3").text
    assert len(re.findall(r'type="range" min="0" max="5"', flavour)) == 6
    assert "data-taste-range" in flavour


def test_onboarding_navigation_validation_and_preserved_choices(
    web_client, backend_client
):
    _login(web_client, backend_client, onboarded=False)
    first = web_client.get("/onboarding/1")
    invalid = web_client.post(
        "/onboarding/1",
        data={"csrf_token": _csrf(first), "city": "Lahore"},
    )
    assert invalid.status_code == 422
    assert 'value="Lahore"' in invalid.text
    valid = web_client.post(
        "/onboarding/1",
        data={
            "csrf_token": _csrf(invalid),
            "city": "Lahore",
            "preferred_cuisines": ["Pakistani", "Chinese"],
        },
        follow_redirects=False,
    )
    assert valid.headers["location"] == "/onboarding/2"
    second = web_client.get("/onboarding/2")
    too_few = web_client.post(
        "/onboarding/2",
        data={"csrf_token": _csrf(second), "favourite_dishes_text": "Biryani, biryani"},
    )
    assert too_few.status_code == 422
    assert "Biryani" in too_few.text
    back = web_client.post(
        "/onboarding/2",
        data={"csrf_token": _csrf(too_few), "direction": "back"},
        follow_redirects=False,
    )
    assert back.headers["location"] == "/onboarding/1"
    revisited = web_client.get("/onboarding/1").text
    assert 'value="Pakistani" checked' in revisited
    assert 'value="Chinese" checked' in revisited


def test_budget_and_slider_validation_preserve_values(web_client, backend_client):
    _login(web_client, backend_client, onboarded=False)
    third = web_client.get("/onboarding/3")
    bad_slider = web_client.post(
        "/onboarding/3",
        data={"csrf_token": _csrf(third), "spice_preference": "9"},
    )
    assert bad_slider.status_code == 422
    fifth = web_client.get("/onboarding/5")
    bad_budget = web_client.post(
        "/onboarding/5",
        data={"csrf_token": _csrf(fifth), "budget_min": "2000", "budget_max": "500"},
    )
    assert bad_budget.status_code == 422
    assert 'value="2000"' in bad_budget.text
    assert 'value="500"' in bad_budget.text


def test_edit_preferences_load_save_error_and_csrf(web_client, backend_client):
    _login(web_client, backend_client)
    backend_client.profile = backend_client.profile.model_copy(
        update={
            "city": "Karachi",
            "preferred_cuisines": ["Pakistani"],
            "favourite_dishes": ["Biryani"],
        }
    )
    page = web_client.get("/app/preferences")
    assert page.status_code == 200
    assert "data-section-navigator" in page.text
    assert 'value="Karachi"' in page.text
    assert 'value="Pakistani" checked' in page.text
    assert web_client.post("/app/preferences", data={}).status_code == 200
    invalid = web_client.post(
        "/app/preferences",
        data={
            "csrf_token": _csrf(page),
            "city": "Islamabad",
            "preferred_cuisines": "Thai",
            "budget_min": "900",
            "budget_max": "200",
        },
    )
    assert invalid.status_code == 422
    assert 'value="Islamabad"' in invalid.text
    saved = web_client.post(
        "/app/preferences",
        data={
            "csrf_token": _csrf(invalid),
            "city": "Islamabad",
            "preferred_cuisines": ["Thai", "Italian"],
            "favourite_dishes_text": "Pizza, pizza, Pasta",
            "preferred_textures": "creamy",
            "dietary_requirements": "vegetarian",
            "allergies_text": "Peanuts",
            "disliked_ingredients_text": "Olives",
            "require_halal": "true",
            "budget_min": "400",
            "budget_max": "1800",
            "spice_preference": "3",
            "sweetness_preference": "2",
            "sourness_preference": "1",
            "saltiness_preference": "2",
            "oiliness_preference": "1",
            "richness_preference": "4",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert saved.headers["location"] == "/app/preferences?saved=1"
    assert backend_client.profile.city == "Islamabad"
    assert backend_client.profile.favourite_dishes == ["Pizza", "Pasta"]
    assert backend_client.profile.require_halal is True
    assert len(backend_client.last_profile_payload["taste_vector"]) == 384
