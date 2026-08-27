from app.services.data_core.dish_profiles import DeterministicDishEmbeddingService
from scripts.seed_partner_marketplace_demo import (
    BATCH,
    DISHES,
    PARTNERS,
    RESTAURANTS,
    _dish_profile,
    plan,
)


def test_demo_plan_exact_counts_keys_and_vectors():
    restaurants, dishes = plan()
    assert len(PARTNERS) == 10
    assert len(RESTAURANTS) == len(restaurants) == 20
    assert len(dishes) == 200
    assert all(len(DISHES[cuisine]) == 10 for cuisine in DISHES)
    assert len({row["id"] for row in restaurants}) == 20
    assert len({row["id"] for row in dishes}) == 200
    assert all(
        len(DeterministicDishEmbeddingService().generate(_dish_profile(row))) == 384
        for row in dishes
    )
    assert BATCH == "partner-marketplace-demo-v1"
