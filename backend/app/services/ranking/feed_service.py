import uuid

from app.models.user import User
from app.repositories.ranking import RankingRepository
from app.schemas.ranking import FeedPreferences, FeedResponse, RankedDishItem
from app.services.data_core.catalog import NotFoundError
from app.services.ranking.generator import filter_candidates
from app.services.ranking.scoring import score_candidate


class RankingFeedService:
    def __init__(self, repository: RankingRepository) -> None:
        self.repository = repository

    def get_ranked_feed(self, user_id: uuid.UUID, preferences: FeedPreferences) -> FeedResponse:
        if self.repository.session.get(User, user_id) is None:
            raise NotFoundError("user", user_id)
        candidates = filter_candidates(self.repository.list_candidates(), preferences)
        maximum_interactions = max(
            (candidate.interaction_count for candidate in candidates), default=0
        )
        scored = [
            score_candidate(candidate, preferences, maximum_interactions=maximum_interactions)
            for candidate in candidates
        ]
        scored.sort(
            key=lambda item: (
                -item.total_score,
                item.candidate.dish.name.casefold(),
                str(item.candidate.dish.id),
            )
        )
        selected = scored[: preferences.limit]
        neutral_signals = sorted(
            set().union(*(item.neutral_signals for item in selected)) if selected else set()
        )
        return FeedResponse(
            user_id=user_id,
            total_candidates=len(candidates),
            neutral_signals=neutral_signals,
            items=[
                RankedDishItem(
                    dish_id=item.candidate.dish.id,
                    dish_name=item.candidate.dish.name,
                    restaurant_id=item.candidate.dish.restaurant_id,
                    restaurant_name=item.candidate.dish.restaurant.name,
                    price=float(item.candidate.dish.price),
                    match_percentage=round(item.total_score),
                    distance_km=item.distance_km,
                    signals=item.signals,
                )
                for item in selected
            ],
        )
