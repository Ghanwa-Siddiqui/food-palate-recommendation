"""Small, defensive HTTP client for the integrated Ranking API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .config import RANKING_API_BASE_URL, RANKING_API_TIMEOUT_SECONDS


class FeedItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dish_id: UUID
    dish_name: str
    restaurant_id: UUID
    restaurant_name: str
    price: float = Field(gt=0)
    match_percentage: int = Field(ge=0, le=100)
    distance_km: float | None = Field(default=None, ge=0)


class FeedResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_id: UUID
    total_candidates: int = Field(ge=0)
    items: list[FeedItem]
    neutral_signals: list[str] = Field(default_factory=list)


class RankingClientError(Exception):
    """Base class for errors safe to map to a UI state."""


class RankingValidationError(RankingClientError):
    pass


class RankingUserNotFoundError(RankingClientError):
    pass


class RankingUnavailableDataError(RankingClientError):
    pass


class RankingBackendError(RankingClientError):
    pass


class RankingFeedClient:
    def __init__(
        self,
        base_url: str = RANKING_API_BASE_URL,
        timeout_seconds: float = RANKING_API_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get_feed(self, user_id: UUID, params: list[tuple[str, str]]) -> FeedResult:
        try:
            response = httpx.get(
                f"{self.base_url}/ranking/feed/{user_id}",
                params=params,
                timeout=self.timeout_seconds,
                follow_redirects=False,
            )
        except httpx.RequestError as exc:
            raise RankingBackendError from exc

        if response.status_code == 404:
            raise RankingUserNotFoundError
        if response.status_code == 422:
            raise RankingValidationError
        if response.status_code >= 500:
            raise RankingBackendError
        if response.status_code != 200:
            raise RankingBackendError

        try:
            payload: Any = response.json()
            result = FeedResult.model_validate(payload)
        except (ValueError, ValidationError) as exc:
            raise RankingUnavailableDataError from exc
        if result.user_id != user_id:
            raise RankingUnavailableDataError
        return result
