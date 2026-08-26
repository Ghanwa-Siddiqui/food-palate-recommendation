import csv

from fastapi.testclient import TestClient

from review_intelligence.api.review_api import create_app


def _features_csv(tmp_path):
    path = tmp_path / "review_features.csv"
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=["review_id", "dish_id", "text", "rating", "timestamp", "sentiment", "spice_level", "oiliness", "flavor_tags", "embedding"])
        writer.writeheader()
        writer.writerow({"review_id": "R1", "dish_id": "D001", "text": "Good", "rating": "5", "timestamp": "2026-08-25", "sentiment": "0.9", "spice_level": "0.8", "oiliness": "0.4", "flavor_tags": "[\"spicy\", \"tender\"]", "embedding": "[1, 3]"})
    return path


def test_existing_dish_summary_matches_shared_contract(tmp_path):
    client = TestClient(create_app(_features_csv(tmp_path)))
    response = client.get("/reviews/D001/summary")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"dish_id", "avg_sentiment", "spice_level", "oiliness", "flavor_tags", "review_vector"}
    assert body["dish_id"] == "D001"
    assert body["review_vector"] == [1.0, 3.0]


def test_unknown_dish_returns_clear_404(tmp_path):
    client = TestClient(create_app(_features_csv(tmp_path)))
    response = client.get("/reviews/UNKNOWN/summary")
    assert response.status_code == 404
    assert "No review summary" in response.json()["detail"]
