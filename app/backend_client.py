"""Typed server-to-server client for Chaska's integrated backend API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .config import (
    BACKEND_API_BASE_URL,
    BACKEND_API_TIMEOUT_SECONDS,
    CHASKA_INTERNAL_API_KEY,
)


class BackendError(Exception):
    pass


class BackendNotFound(BackendError):
    pass


class BackendValidationError(BackendError):
    pass


class BackendUnavailable(BackendError):
    pass


class APIModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class UserProfile(APIModel):
    user_id: UUID
    name: str
    email: str
    role: str = "customer"
    onboarding_complete: bool
    city: str | None
    preferred_cuisines: list[str]
    favourite_dishes: list[str]
    spice_preference: int
    sweetness_preference: int
    sourness_preference: int
    saltiness_preference: int
    oiliness_preference: int
    richness_preference: int
    preferred_textures: list[str]
    budget_min: float
    budget_max: float
    dietary_requirements: list[str]
    allergies: list[str]
    disliked_ingredients: list[str]
    require_halal: bool
    taste_updated_at: datetime | None


class RestaurantItem(APIModel):
    id: UUID
    name: str
    description: str | None
    cuisine_types: list[str]
    address: str
    city: str
    lat: float | None
    lng: float | None
    location_verified: bool
    price_range: str
    halal_status: str
    owner_id: UUID | None = None
    contact_phone: str | None = None
    halal_verification_status: str = "unverified"
    opening_information: str | None = None
    available: bool = True
    image_path: str | None = None


class DishItem(APIModel):
    id: UUID
    restaurant_id: UUID
    name: str
    description: str | None
    cuisine: str
    ingredients: list[str]
    price: float
    spice_level: int
    oiliness: int
    sweetness: int
    sourness: int
    saltiness: int
    smokiness: int
    richness: int
    texture_tags: list[str]
    dietary_tags: list[str]
    allergens: list[str]
    preparation_style: str
    availability: bool
    image_path: str | None = None
    archived_at: datetime | None = None
    embedding_updated_at: datetime | None = None


class DealItem(APIModel):
    id: UUID
    restaurant_id: UUID
    title: str
    description: str | None
    discount_percentage: float
    starts_at: datetime
    ends_at: datetime
    is_active: bool


class FeedItem(APIModel):
    dish_id: UUID
    dish_name: str
    restaurant_id: UUID
    restaurant_name: str
    cuisine: str
    description: str | None
    price: float = Field(gt=0)
    match_percentage: int = Field(ge=0, le=100)
    distance_km: float | None
    halal_status: str
    availability: bool
    dietary_tags: list[str]
    texture_tags: list[str]
    taste_explanation: str
    review_insight: str | None
    active_deals: list[str]
    saved: bool
    signals: dict[str, float]
    collaborative_score: float | None = None
    collaborative_explanation: str | None = None
    collaborative_reviewer_name: str | None = None
    collaborative_review_excerpt: str | None = None
    collaborative_review_rating: float | None = None


class FeedResult(APIModel):
    user_id: UUID
    total_candidates: int
    items: list[FeedItem]
    neutral_signals: list[str]
    collaborative_available: bool = False
    similar_user_count: int = 0
    limit: int
    offset: int


class InteractionItem(APIModel):
    id: UUID
    user_id: UUID
    dish_id: UUID
    action: str
    ts: datetime
    client_event_id: str | None
    duplicate: bool = False


class ReviewSummary(APIModel):
    dish_id: UUID
    review_count: int
    average_rating: float | None = None
    avg_sentiment: float | None = None
    spice_level: float | None = None
    oiliness: float | None = None
    flavor_tags: list[str]


class PublicReview(APIModel):
    id: UUID
    dish_id: UUID
    rating: int
    text: str
    reviewer_name: str
    created_at: datetime
    updated_at: datetime
    processing_status: str | None = None


class SimilarUser(APIModel):
    user_id: UUID
    name: str
    score: float


class ChaskaBackendClient:
    def __init__(
        self,
        base_url: str = BACKEND_API_BASE_URL,
        timeout_seconds: float = BACKEND_API_TIMEOUT_SECONDS,
        internal_key: str = CHASKA_INTERNAL_API_KEY,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.internal_key = internal_key

    def _request(
        self,
        method: str,
        path: str,
        *,
        user_id: UUID | None = None,
        params: list[tuple[str, str]] | None = None,
        json: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        headers = {"Accept": "application/json"}
        if self.internal_key:
            headers["X-Chaska-Internal-Key"] = self.internal_key
        if user_id:
            headers["X-Chaska-User-ID"] = str(user_id)
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                params=params,
                json=json,
                headers=headers,
                timeout=self.timeout_seconds,
                follow_redirects=False,
            )
        except httpx.RequestError as exc:
            raise BackendUnavailable("Backend service is unavailable") from exc
        if response.status_code == 404:
            raise BackendNotFound
        if response.status_code in {400, 401, 403, 409, 422}:
            raise BackendValidationError
        if response.status_code >= 500:
            raise BackendUnavailable("Backend service failed")
        if response.status_code == 204:
            return None
        if not 200 <= response.status_code < 300:
            raise BackendUnavailable("Unexpected backend response")
        try:
            return response.json()
        except ValueError as exc:
            raise BackendUnavailable("Backend returned invalid data") from exc

    @staticmethod
    def _parse(model, payload):
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise BackendUnavailable(
                "Backend response did not match its contract"
            ) from exc

    def sync_user(
        self, user_id: UUID, name: str, email: str, role: str | None = None
    ) -> None:
        payload = {"id": str(user_id), "name": name, "email": email}
        if role is not None:
            payload["role"] = role
        self._request(
            "POST",
            "/users/sync",
            json=payload,
        )

    def partner_restaurants(self, user_id: UUID) -> list[RestaurantItem]:
        payload = self._request("GET", "/partner/restaurants", user_id=user_id)
        return [self._parse(RestaurantItem, item) for item in payload]

    def create_partner_restaurant(
        self, user_id: UUID, payload: dict[str, Any]
    ) -> RestaurantItem:
        return self._parse(
            RestaurantItem,
            self._request(
                "POST", "/partner/restaurants", user_id=user_id, json=payload
            ),
        )

    def update_partner_restaurant(
        self, user_id: UUID, restaurant_id: UUID, payload: dict[str, Any]
    ) -> RestaurantItem:
        return self._parse(
            RestaurantItem,
            self._request(
                "PUT",
                f"/partner/restaurants/{restaurant_id}",
                user_id=user_id,
                json=payload,
            ),
        )

    def partner_menu(self, user_id: UUID, restaurant_id: UUID) -> list[DishItem]:
        payload = self._request(
            "GET", f"/partner/restaurants/{restaurant_id}/dishes", user_id=user_id
        )
        return [self._parse(DishItem, item) for item in payload]

    def partner_dish(self, user_id: UUID, dish_id: UUID) -> DishItem:
        return self._parse(
            DishItem,
            self._request("GET", f"/partner/dishes/{dish_id}", user_id=user_id),
        )

    def create_partner_dish(
        self, user_id: UUID, payload: dict[str, Any], idempotency_key: str
    ) -> DishItem:
        return self._parse(
            DishItem,
            self._request(
                "POST",
                "/partner/dishes",
                user_id=user_id,
                json=payload,
                idempotency_key=idempotency_key,
            ),
        )

    def update_partner_dish(
        self, user_id: UUID, dish_id: UUID, payload: dict[str, Any]
    ) -> DishItem:
        return self._parse(
            DishItem,
            self._request(
                "PUT", f"/partner/dishes/{dish_id}", user_id=user_id, json=payload
            ),
        )

    def set_partner_dish_availability(
        self, user_id: UUID, dish_id: UUID, available: bool
    ) -> DishItem:
        return self._parse(
            DishItem,
            self._request(
                "POST",
                f"/partner/dishes/{dish_id}/availability",
                user_id=user_id,
                params=[("available", str(available).lower())],
            ),
        )

    def archive_partner_dish(self, user_id: UUID, dish_id: UUID) -> DishItem:
        return self._parse(
            DishItem,
            self._request(
                "POST", f"/partner/dishes/{dish_id}/archive", user_id=user_id
            ),
        )

    def get_profile(self, user_id: UUID) -> UserProfile:
        return self._parse(
            UserProfile,
            self._request("GET", f"/users/{user_id}/profile", user_id=user_id),
        )

    def update_profile(self, user_id: UUID, payload: dict[str, Any]) -> UserProfile:
        return self._parse(
            UserProfile,
            self._request(
                "PUT", f"/users/{user_id}/profile", user_id=user_id, json=payload
            ),
        )

    def get_feed(self, user_id: UUID, params: list[tuple[str, str]]) -> FeedResult:
        return self._parse(
            FeedResult,
            self._request(
                "GET", f"/ranking/feed/{user_id}", user_id=user_id, params=params
            ),
        )

    def get_restaurant(self, restaurant_id: UUID) -> RestaurantItem:
        return self._parse(
            RestaurantItem, self._request("GET", f"/restaurants/{restaurant_id}")
        )

    def restaurant_dishes(self, restaurant_id: UUID) -> list[DishItem]:
        payload = self._request("GET", f"/restaurants/{restaurant_id}/dishes")
        return [self._parse(DishItem, item) for item in payload["items"]]

    def get_dish(self, dish_id: UUID) -> DishItem:
        return self._parse(DishItem, self._request("GET", f"/dishes/{dish_id}"))

    def restaurant_deals(self, restaurant_id: UUID) -> list[DealItem]:
        payload = self._request(
            "GET",
            "/deals",
            params=[("restaurant_id", str(restaurant_id)), ("active_only", "true")],
        )
        return [self._parse(DealItem, item) for item in payload["items"]]

    def review_summary(self, dish_id: UUID) -> ReviewSummary:
        return self._parse(
            ReviewSummary, self._request("GET", f"/reviews/{dish_id}/summary")
        )

    def dish_reviews(self, dish_id: UUID) -> list[PublicReview]:
        payload = self._request("GET", f"/reviews/{dish_id}")
        return [self._parse(PublicReview, item) for item in payload]

    def my_review(self, user_id: UUID, dish_id: UUID) -> PublicReview | None:
        payload = self._request("GET", f"/reviews/{dish_id}/mine", user_id=user_id)
        return self._parse(PublicReview, payload) if payload else None

    def create_review(self, user_id: UUID, payload: dict[str, Any]) -> PublicReview:
        return self._parse(
            PublicReview,
            self._request("POST", "/reviews", user_id=user_id, json=payload),
        )

    def update_review(
        self, user_id: UUID, review_id: UUID, payload: dict[str, Any]
    ) -> PublicReview:
        return self._parse(
            PublicReview,
            self._request(
                "PUT", f"/reviews/{review_id}", user_id=user_id, json=payload
            ),
        )

    def interactions(self, user_id: UUID) -> list[InteractionItem]:
        payload = self._request(
            "GET", f"/users/{user_id}/interactions", user_id=user_id
        )
        return [self._parse(InteractionItem, item) for item in payload]

    def interact(
        self, user_id: UUID, dish_id: UUID, action: str, client_event_id: str
    ) -> InteractionItem:
        payload = self._request(
            "POST",
            f"/users/{user_id}/interactions",
            user_id=user_id,
            json={
                "dish_id": str(dish_id),
                "action": action,
                "client_event_id": client_event_id,
            },
        )
        return self._parse(InteractionItem, payload)

    def unsave(self, user_id: UUID, dish_id: UUID) -> None:
        self._request("DELETE", f"/users/{user_id}/saved/{dish_id}", user_id=user_id)

    def similar_users(self, user_id: UUID) -> list[SimilarUser]:
        payload = self._request("GET", f"/users/{user_id}/similar", user_id=user_id)
        return [self._parse(SimilarUser, item) for item in payload]


def get_backend_client() -> ChaskaBackendClient:
    return ChaskaBackendClient()
