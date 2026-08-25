from app.models import Interaction
from app.popularity import normalized_dish_popularity, raw_dish_scores
from app.repositories import get_repository


def test_no_interactions_returns_empty():
    assert raw_dish_scores() == {}
    assert normalized_dish_popularity() == {}


def test_weights_and_normalization():
    repo = get_repository()
    repo.add_interaction(Interaction(user_id="u1", dish_id="d_001", action="click"))
    repo.add_interaction(Interaction(user_id="u2", dish_id="d_001", action="order"))  # 1 + 3 = 4
    repo.add_interaction(Interaction(user_id="u1", dish_id="d_002", action="save"))   # 2

    raw = raw_dish_scores()
    assert raw["d_001"] == 4.0
    assert raw["d_002"] == 2.0

    norm = normalized_dish_popularity()
    assert norm["d_001"] == 1.0
    assert norm["d_002"] == 0.5
