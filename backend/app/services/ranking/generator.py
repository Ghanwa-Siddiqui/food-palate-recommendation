import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.schemas.ranking import FeedPreferences


class RestaurantLike(Protocol):
    id: UUID
    name: str
    halal_status: str
    latitude: Decimal | None
    longitude: Decimal | None
    location_verified: bool


class DishLike(Protocol):
    id: UUID
    restaurant_id: UUID
    name: str
    cuisine: str
    price: Decimal
    ingredients: list[str]
    dietary_tags: list[str]
    allergens: list[str]
    spice_level: int
    oiliness: int
    sweetness: int
    sourness: int
    saltiness: int
    richness: int
    texture_tags: list[str]
    availability: bool
    embedding: list[float] | None
    restaurant: RestaurantLike


@dataclass(frozen=True)
class TasteTwinReviewEvidence:
    reviewer_name: str
    rating: float
    excerpt: str
    similarity_percent: int


@dataclass(frozen=True)
class RankingCandidate:
    dish: DishLike
    review_average: float | None = None
    review_sentiment: float | None = None
    interaction_count: int = 0
    saved: bool = False
    collaborative_score: float | None = None
    similar_user_count: int = 0
    collaborative_explanation: str | None = None
    collaborative_reviewer_name: str | None = None
    collaborative_review_excerpt: str | None = None
    collaborative_review_rating: float | None = None
    taste_twin_review_count: int = 0
    taste_twin_reviews: tuple[TasteTwinReviewEvidence, ...] = ()


def _normalized(values: list[str]) -> set[str]:
    return {value.strip().casefold() for value in values if value.strip()}


def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(delta_lon / 2) ** 2
    )
    return radius_km * (2 * math.atan2(math.sqrt(value), math.sqrt(1 - value)))


def filter_candidates(
    candidates: list[RankingCandidate], preferences: FeedPreferences
) -> list[RankingCandidate]:
    required_dietary = _normalized(preferences.dietary_restrictions) - {"halal"}
    allergies = _normalized(preferences.allergies)
    disliked = _normalized(preferences.disliked_ingredients)
    filtered: list[RankingCandidate] = []
    for candidate in candidates:
        dish = candidate.dish
        if (
            preferences.restaurant_id is not None
            and dish.restaurant_id != preferences.restaurant_id
        ):
            continue
        if preferences.search:
            needle = preferences.search.casefold()
            searchable = f"{dish.name} {dish.cuisine}".casefold()
            if needle not in searchable:
                continue
        if not dish.availability:
            continue
        price = float(dish.price)
        if preferences.budget_min is not None and price < preferences.budget_min:
            continue
        if preferences.budget_max is not None and price > preferences.budget_max:
            continue
        if not required_dietary <= _normalized(dish.dietary_tags):
            continue
        if allergies & _normalized(dish.allergens):
            continue
        if disliked & _normalized(dish.ingredients):
            continue
        if preferences.require_halal and dish.restaurant.halal_status not in {
            "verified",
            "claimed",
        }:
            continue
        if (
            preferences.max_distance_km is not None
            and preferences.user_lat is not None
            and preferences.user_lng is not None
            and dish.restaurant.location_verified
            and dish.restaurant.latitude is not None
            and dish.restaurant.longitude is not None
            and calculate_haversine_distance(
                preferences.user_lat,
                preferences.user_lng,
                float(dish.restaurant.latitude),
                float(dish.restaurant.longitude),
            )
            > preferences.max_distance_km
        ):
            continue
        filtered.append(candidate)
    return filtered
