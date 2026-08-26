import os
import pytest


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    """Point the app's DATA_DIR at a per-test temp dir and reset caches."""
    monkeypatch.setattr("app.config.DATA_DIR", tmp_path)
    monkeypatch.setenv("STORAGE_BACKEND", "json")

    # Reset module-level caches that snapshotted DATA_DIR at import time.
    from app import dish_store
    dish_store.invalidate_cache()

    # Seed a minimal mock_dishes.json so dish_store returns something.
    import json
    from app.embedding import embed_dish
    dishes = [
        {"id": "d0000000-0000-4000-8000-000000000001", "restaurant_id": "r0000000-0000-4000-8000-000000000001",
         "name": "Chicken Karahi", "cuisine": "Pakistani", "ingredients": ["chicken", "tomato"],
         "price": 1000, "vector": embed_dish("Chicken Karahi", "Pakistani", ["chicken", "tomato"]),
         "lat": 24.8, "lng": 67.0},
        {"id": "d0000000-0000-4000-8000-000000000002", "restaurant_id": "r0000000-0000-4000-8000-000000000002",
         "name": "Salmon Sushi", "cuisine": "Japanese", "ingredients": ["salmon", "rice"],
         "price": 1800, "vector": embed_dish("Salmon Sushi", "Japanese", ["salmon", "rice"]),
         "lat": 24.8, "lng": 67.0},
    ]
    (tmp_path / "mock_dishes.json").write_text(json.dumps(dishes), encoding="utf-8")
    yield
    dish_store.invalidate_cache()
