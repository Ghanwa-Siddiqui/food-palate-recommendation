from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


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
            "favorite_foods": "biryani, pasta",
            "dietary": ["halal"],
            "spice_pref": 3,
            "budget": 1500,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    user_id = r.headers["location"].split("user_id=")[1]

    v = client.get(f"/api/user/{user_id}/taste-vector").json()
    assert v["user_id"] == user_id
    assert len(v["taste_vector"]) == 128
    assert v["budget"] == 1500
    assert v["dietary"] == ["halal"]


def test_interaction_flow_updates_vector():
    onboard = client.post(
        "/onboarding",
        data={"cuisines": ["Pakistani"], "favorite_foods": "karahi",
              "dietary": [], "spice_pref": 3, "budget": 1000},
        follow_redirects=False,
    )
    user_id = onboard.headers["location"].split("user_id=")[1]

    before = client.get(f"/api/user/{user_id}/taste-vector").json()["taste_vector"]
    ack = client.post(
        f"/api/user/{user_id}/interaction",
        json={"dish_id": "d_002", "action": "order"},
    ).json()
    assert ack["ok"] is True
    assert ack["vector_updated"] is True

    after = client.get(f"/api/user/{user_id}/taste-vector").json()["taste_vector"]
    assert before != after

    interactions = client.get(f"/api/user/{user_id}/interaction").json()
    assert len(interactions) == 1
    assert interactions[0]["dish_id"] == "d_002"


def test_similar_users_endpoint():
    # Identical answers -> identical vectors -> similarity 1.0. That's the
    # only signal stable enough to assert on for a bag-of-terms mock embedding.
    same = {"cuisines": ["Pakistani"], "favorite_foods": "biryani, karahi",
            "dietary": ["halal"], "spice_pref": 3, "budget": 1000}
    different = {"cuisines": ["Japanese"], "favorite_foods": "sushi, ramen",
                 "dietary": [], "spice_pref": 1, "budget": 2000}
    ids = []
    for payload in (same, same, different):
        r = client.post("/onboarding", data=payload, follow_redirects=False)
        ids.append(r.headers["location"].split("user_id=")[1])

    similar = client.get(f"/api/user/{ids[0]}/similar?k=2").json()
    assert len(similar) == 2
    assert similar[0]["user_id"] == ids[1]
    assert similar[0]["score"] > similar[1]["score"]
