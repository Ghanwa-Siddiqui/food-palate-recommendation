from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

DISH_1 = "d0000000-0000-4000-8000-000000000001"
DISH_2 = "d0000000-0000-4000-8000-000000000002"


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_onboarding_form_renders():
    r = client.get("/onboarding")
    assert r.status_code == 200
    assert "Tell us what you like" in r.text


def test_onboarding_submit_and_taste_vector_roundtrip():
    r = client.post(
        "/onboarding",
        data={
            "cuisines": ["Pakistani", "Italian"],
            "favourite_dishes": "biryani, pasta",
            "dietary": ["halal"],
            "spice_preference": 3,
            "budget_min": 500,
            "budget_max": 1500,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    user_id = r.headers["location"].split("user_id=")[1]

    v = client.get(f"/api/user/{user_id}/taste-vector").json()
    assert v["user_id"] == user_id
    assert len(v["taste_vector"]) == 384
    assert v["budget_min"] == 500
    assert v["budget_max"] == 1500
    assert v["dietary_requirements"] == ["halal"]
    assert v["preferred_cuisines"] == ["Pakistani", "Italian"]
    assert v["favourite_dishes"] == ["biryani", "pasta"]
    assert v["spice_preference"] == 3


def test_interaction_flow_updates_vector():
    onboard = client.post(
        "/onboarding",
        data={"cuisines": ["Pakistani"], "favourite_dishes": "karahi",
              "dietary": [], "spice_preference": 3, "budget_min": 0, "budget_max": 1000},
        follow_redirects=False,
    )
    user_id = onboard.headers["location"].split("user_id=")[1]

    before = client.get(f"/api/user/{user_id}/taste-vector").json()["taste_vector"]
    ack = client.post(
        f"/api/user/{user_id}/interaction",
        json={"dish_id": DISH_2, "action": "order"},
    ).json()
    assert ack["ok"] is True
    assert ack["vector_updated"] is True

    after = client.get(f"/api/user/{user_id}/taste-vector").json()["taste_vector"]
    assert before != after

    interactions = client.get(f"/api/user/{user_id}/interaction").json()
    assert len(interactions) == 1
    assert interactions[0]["dish_id"] == DISH_2


def test_similar_users_endpoint():
    # Identical answers -> identical vectors -> similarity 1.0. That's the
    # only signal stable enough to assert on for a bag-of-terms mock embedding.
    same = {"cuisines": ["Pakistani"], "favourite_dishes": "biryani, karahi",
            "dietary": ["halal"], "spice_preference": 3, "budget_min": 0, "budget_max": 1000}
    different = {"cuisines": ["Japanese"], "favourite_dishes": "sushi, ramen",
                 "dietary": [], "spice_preference": 1, "budget_min": 0, "budget_max": 2000}
    ids = []
    for payload in (same, same, different):
        r = client.post("/onboarding", data=payload, follow_redirects=False)
        ids.append(r.headers["location"].split("user_id=")[1])

    similar = client.get(f"/api/user/{ids[0]}/similar?k=2").json()
    assert len(similar) == 2
    assert similar[0]["user_id"] == ids[1]
    assert similar[0]["score"] > similar[1]["score"]


def test_context_endpoint_unknown_user_404():
    assert client.get("/api/user/u_nope/context").status_code == 404


def test_context_endpoint_returns_signal():
    r = client.post(
        "/onboarding",
        data={"cuisines": ["Pakistani"], "favourite_dishes": "karahi",
              "dietary": [], "spice_preference": 2, "budget_min": 0, "budget_max": 1000},
        follow_redirects=False,
    )
    user_id = r.headers["location"].split("user_id=")[1]

    sig = client.get(f"/api/user/{user_id}/context").json()
    assert sig["user_id"] == user_id
    assert sig["period_weights"] == {}
    assert sig["preferred_period"] is None
    assert sig["current_period"] in {"breakfast", "lunch", "dinner", "late_night"}


def test_popularity_endpoints():
    onboard = client.post(
        "/onboarding",
        data={"cuisines": ["Pakistani"], "favourite_dishes": "karahi",
              "dietary": [], "spice_preference": 2, "budget_min": 0, "budget_max": 1000},
        follow_redirects=False,
    )
    user_id = onboard.headers["location"].split("user_id=")[1]

    client.post(f"/api/user/{user_id}/interaction", json={"dish_id": DISH_1, "action": "order"})
    client.post(f"/api/user/{user_id}/interaction", json={"dish_id": DISH_2, "action": "click"})

    all_scores = client.get("/api/popularity").json()
    assert all_scores[0]["dish_id"] == DISH_1
    assert all_scores[0]["score"] == 1.0

    single = client.get(f"/api/popularity/{DISH_2}").json()
    assert single["score"] < 1.0

    unseen = client.get("/api/popularity/d_999").json()
    assert unseen["score"] == 0.0
