import numpy as np

from app.config import VECTOR_DIM
from app.embedding import embed_dish, embed_text
from app.models import OnboardingAnswers
from app.personalization import (
    apply_interaction_update,
    build_taste_vector,
    user_from_onboarding,
)
from app.vector_math import cosine_similarity, ema_update


def test_embedding_deterministic():
    assert embed_text("chicken biryani") == embed_text("chicken biryani")
    assert embed_text("Chicken Biryani") == embed_text("chicken biryani")  # normalized


def test_embedding_is_unit_length():
    v = embed_text("something specific")
    assert abs(np.linalg.norm(v) - 1.0) < 1e-5


def test_same_cuisine_more_similar_than_cross_cuisine():
    v_paki_a = embed_dish("Chicken Karahi", "Pakistani", ["chicken", "tomato"])
    v_paki_b = embed_dish("Chicken Biryani", "Pakistani", ["chicken", "rice"])
    v_jap = embed_dish("Salmon Sushi", "Japanese", ["salmon", "rice"])
    assert cosine_similarity(v_paki_a, v_paki_b) > cosine_similarity(v_paki_a, v_jap)


def test_build_taste_vector_returns_unit_vector():
    answers = OnboardingAnswers(
        preferred_cuisines=["Pakistani", "Italian"],
        favourite_dishes=["biryani", "pasta"],
        dietary_requirements=["halal"],
        spice_preference=3,
        budget_min=500,
        budget_max=1500,
    )
    vec = build_taste_vector(answers)
    assert len(vec) == VECTOR_DIM
    assert abs(np.linalg.norm(vec) - 1.0) < 1e-5


def test_ema_moves_vector_toward_signal():
    current = embed_text("pakistani food")
    signal = embed_text("italian food")
    updated = ema_update(current, signal, alpha=0.3)
    assert cosine_similarity(updated, signal) > cosine_similarity(current, signal)


def test_apply_interaction_bumps_user_vector_toward_dish():
    answers = OnboardingAnswers(
        preferred_cuisines=["Pakistani"], favourite_dishes=["biryani"]
    )
    user = user_from_onboarding("11111111-1111-4111-8111-111111111111", answers)
    dish_v = embed_dish("Salmon Sushi", "Japanese", ["salmon", "rice"])
    updated = apply_interaction_update(user, dish_v)
    assert cosine_similarity(updated.taste_vector, dish_v) > cosine_similarity(
        user.taste_vector, dish_v
    )
    assert updated.last_updated >= user.last_updated
