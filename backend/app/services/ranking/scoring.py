from dataclasses import dataclass
from typing import Protocol

from app.core.constants import EMBEDDING_DIMENSION
from app.schemas.ranking import FeedPreferences, SignalScores
from app.services.ranking.generator import RankingCandidate, calculate_haversine_distance

NEUTRAL_SCORE = 50.0
WEIGHTS = {
    "taste": 0.45,
    "food_profile": 0.20,
    "review": 0.10,
    "distance": 0.10,
    "price": 0.10,
    "popularity": 0.05,
}


class UserProfileLike(Protocol):
    onboarding_complete: bool
    preferred_cuisines: list[str]
    favourite_dishes: list[str]
    spice_preference: int
    sweetness_preference: int
    sourness_preference: int
    saltiness_preference: int
    oiliness_preference: int
    richness_preference: int
    preferred_textures: list[str]


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: RankingCandidate
    total_score: float
    distance_km: float | None
    signals: SignalScores
    neutral_signals: frozenset[str]


def calculate_cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    if len(vector_a) != EMBEDDING_DIMENSION or len(vector_b) != EMBEDDING_DIMENSION:
        raise ValueError(f"vectors must contain exactly {EMBEDDING_DIMENSION} values")
    dot_product = sum(a * b for a, b in zip(vector_a, vector_b, strict=True))
    norm_a = sum(value * value for value in vector_a) ** 0.5
    norm_b = sum(value * value for value in vector_b) ** 0.5
    if not norm_a or not norm_b:
        return 0.0
    return max(-1.0, min(1.0, dot_product / (norm_a * norm_b)))


def _food_profile_score(candidate: RankingCandidate, user: UserProfileLike | None) -> float | None:
    if user is None or not user.onboarding_complete:
        return None
    dish = candidate.dish
    parts: list[tuple[float, float]] = []
    cuisines = {item.casefold() for item in user.preferred_cuisines}
    favourites = {item.casefold() for item in user.favourite_dishes}
    if cuisines or favourites:
        cuisine_match = dish.cuisine.casefold() in cuisines
        favourite_match = any(name in dish.name.casefold() for name in favourites)
        parts.append((100.0 if cuisine_match or favourite_match else 0.0, 0.4))
    pairs = (
        (dish.spice_level, user.spice_preference),
        (dish.oiliness, user.oiliness_preference),
        (dish.sweetness, user.sweetness_preference),
        (dish.sourness, user.sourness_preference),
        (dish.saltiness, user.saltiness_preference),
        (dish.richness, user.richness_preference),
    )
    taste_levels = sum(100 * (1 - abs(actual - preferred) / 5) for actual, preferred in pairs) / 6
    parts.append((taste_levels, 0.4))
    preferred_textures = {item.casefold() for item in user.preferred_textures}
    if preferred_textures:
        dish_textures = {item.casefold() for item in dish.texture_tags}
        parts.append((100 * len(preferred_textures & dish_textures) / len(preferred_textures), 0.2))
    weight = sum(part_weight for _score, part_weight in parts)
    return sum(score * part_weight for score, part_weight in parts) / weight if weight else None


def score_candidate(
    candidate: RankingCandidate,
    preferences: FeedPreferences,
    user: UserProfileLike | None = None,
    *,
    maximum_interactions: int,
) -> ScoredCandidate:
    neutral: set[str] = set()
    dish = candidate.dish
    embedding = list(dish.embedding) if dish.embedding is not None else None
    if preferences.taste_vector is not None and embedding is not None:
        taste = max(0.0, calculate_cosine_similarity(preferences.taste_vector, embedding)) * 100
    else:
        taste = NEUTRAL_SCORE
        neutral.add("taste")
    profile_score = _food_profile_score(candidate, user)
    if profile_score is None and candidate.collaborative_score is None:
        food_profile = NEUTRAL_SCORE
        neutral.add("food_profile")
    elif candidate.collaborative_score is not None:
        # Internal 20% food/profile calculation: 70% content profile + 30% collaborative.
        # A missing content profile stays neutral; collaborative evidence never becomes
        # a seventh top-level ranking signal.
        food_profile = (
            0.7 * (profile_score if profile_score is not None else NEUTRAL_SCORE)
            + 0.3 * candidate.collaborative_score
        )
    else:
        food_profile = profile_score
    if candidate.review_sentiment is not None:
        # Review Intelligence uses 0..1; only genuinely positive sentiment boosts neutral.
        review = max(0.0, min(100.0, candidate.review_sentiment * 100))
    elif candidate.review_average is None:
        review = NEUTRAL_SCORE
        neutral.add("review")
    else:
        review = max(0.0, min(100.0, candidate.review_average / 5 * 100))
    if maximum_interactions > 0:
        popularity = candidate.interaction_count / maximum_interactions * 100
    else:
        popularity = NEUTRAL_SCORE
        neutral.add("popularity")
    distance_km = None
    restaurant = dish.restaurant
    if (
        preferences.user_lat is not None
        and preferences.user_lng is not None
        and restaurant.location_verified
        and restaurant.latitude is not None
        and restaurant.longitude is not None
    ):
        distance_km = calculate_haversine_distance(
            preferences.user_lat,
            preferences.user_lng,
            float(restaurant.latitude),
            float(restaurant.longitude),
        )
        horizon = preferences.max_distance_km or 25.0
        distance = max(0.0, 100 * (1 - distance_km / horizon))
    else:
        distance = NEUTRAL_SCORE
        neutral.add("distance")
    if preferences.budget_max is not None:
        lower = preferences.budget_min or 0.0
        span = max(preferences.budget_max - lower, 1.0)
        price = max(0.0, min(100.0, 100 * (preferences.budget_max - float(dish.price)) / span))
    else:
        price = NEUTRAL_SCORE
        neutral.add("price")
    scores = SignalScores(
        taste=taste,
        food_profile=food_profile,
        review=review,
        popularity=popularity,
        distance=distance,
        price=price,
    )
    total = sum(WEIGHTS[name] * getattr(scores, name) for name in WEIGHTS)
    return ScoredCandidate(
        candidate=candidate,
        total_score=total,
        distance_km=round(distance_km, 1) if distance_km is not None else None,
        signals=scores,
        neutral_signals=frozenset(neutral),
    )
