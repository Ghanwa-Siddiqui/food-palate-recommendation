from dataclasses import dataclass

from app.core.constants import EMBEDDING_DIMENSION
from app.schemas.ranking import FeedPreferences, SignalScores
from app.services.ranking.generator import RankingCandidate, calculate_haversine_distance

NEUTRAL_SCORE = 50.0
WEIGHTS = {
    "taste": 0.45,
    "review": 0.15,
    "popularity": 0.10,
    "distance": 0.10,
    "price": 0.10,
    "context": 0.05,
    "collaborative": 0.05,
}


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


def score_candidate(
    candidate: RankingCandidate,
    preferences: FeedPreferences,
    *,
    maximum_interactions: int,
) -> ScoredCandidate:
    neutral = {"context", "collaborative"}
    dish = candidate.dish
    embedding = list(dish.embedding) if dish.embedding is not None else None
    if preferences.taste_vector is not None and embedding is not None:
        taste = max(0.0, calculate_cosine_similarity(preferences.taste_vector, embedding)) * 100
    else:
        taste = NEUTRAL_SCORE
        neutral.add("taste")
    if candidate.review_average is None:
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
        review=review,
        popularity=popularity,
        distance=distance,
        price=price,
        context=NEUTRAL_SCORE,
        collaborative=NEUTRAL_SCORE,
    )
    total = sum(WEIGHTS[name] * getattr(scores, name) for name in WEIGHTS)
    return ScoredCandidate(
        candidate=candidate,
        total_score=total,
        distance_km=round(distance_km, 1) if distance_km is not None else None,
        signals=scores,
        neutral_signals=frozenset(neutral),
    )
