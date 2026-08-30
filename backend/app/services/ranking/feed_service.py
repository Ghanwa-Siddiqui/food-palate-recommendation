import uuid
from datetime import UTC, datetime

from app.models.user import User
from app.repositories.ranking import RankingRepository
from app.schemas.ranking import FeedPreferences, FeedResponse, RankedDishItem
from app.services.data_core.catalog import NotFoundError
from app.services.ranking.generator import filter_candidates
from app.services.ranking.scoring import score_candidate


class RankingFeedService:
    def __init__(self, repository: RankingRepository) -> None:
        self.repository = repository

    @staticmethod
    def _effective_preferences(user: User, requested: FeedPreferences) -> FeedPreferences:
        updates = {}
        supplied = requested.model_fields_set
        # Budget is intentionally NOT defaulted from the stored profile: it's a
        # per-visit choice made through the feed's own sidebar filter, not an
        # app-wide constraint like dietary/allergy/halal (those stay defaulted
        # below since they're safety requirements, not taste preferences).
        defaults = {
            "dietary_restrictions": user.dietary_requirements,
            "allergies": user.allergies,
            "disliked_ingredients": user.disliked_ingredients,
            "require_halal": user.require_halal,
            "taste_vector": list(user.taste_vector) if user.taste_vector is not None else None,
        }
        for field, value in defaults.items():
            if field not in supplied:
                updates[field] = value
        return requested.model_copy(update=updates)

    def get_ranked_feed(self, user_id: uuid.UUID, preferences: FeedPreferences) -> FeedResponse:
        user = self.repository.session.get(User, user_id)
        if user is None:
            raise NotFoundError("user", user_id)
        effective = self._effective_preferences(user, preferences)
        candidates = filter_candidates(self.repository.list_candidates(user_id), effective)
        maximum_interactions = max(
            (candidate.interaction_count for candidate in candidates), default=0
        )
        scored = [
            score_candidate(candidate, effective, user, maximum_interactions=maximum_interactions)
            for candidate in candidates
        ]
        scored.sort(
            key=lambda item: (
                -item.total_score,
                item.candidate.dish.name.casefold(),
                str(item.candidate.dish.id),
            )
        )
        selected = scored[effective.offset : effective.offset + effective.limit]
        neutral_signals = sorted(
            set().union(*(item.neutral_signals for item in selected)) if selected else set()
        )
        now = datetime.now(UTC)
        items = []
        for item in selected:
            dish = item.candidate.dish
            restaurant = dish.restaurant
            strongest = max(
                (
                    (name, value)
                    for name, value in item.signals.model_dump().items()
                    if name not in item.neutral_signals
                ),
                key=lambda pair: pair[1],
                default=None,
            )
            explanation = (
                f"Strongest available match: {strongest[0].replace('_', ' ')}."
                if strongest
                else "Available ranking signals are neutral for this dish."
            )
            if item.candidate.collaborative_explanation:
                explanation = f"Taste-profile match: {explanation}"
            review_insight = (
                f"Average review sentiment {item.candidate.review_sentiment:+.2f}."
                if item.candidate.review_sentiment is not None
                else (
                    f"Average reviewer rating {item.candidate.review_average:.1f}/5."
                    if item.candidate.review_average is not None
                    else None
                )
            )
            active_deals = [
                deal.title
                for deal in restaurant.deals
                if deal.is_active and deal.starts_at <= now <= deal.ends_at
            ]
            items.append(
                RankedDishItem(
                    dish_id=dish.id,
                    dish_name=dish.name,
                    restaurant_id=dish.restaurant_id,
                    restaurant_name=restaurant.name,
                    cuisine=dish.cuisine,
                    description=dish.description,
                    price=float(dish.price),
                    match_percentage=round(item.total_score),
                    distance_km=item.distance_km,
                    halal_status=restaurant.halal_status,
                    availability=dish.availability,
                    dietary_tags=dish.dietary_tags,
                    texture_tags=dish.texture_tags,
                    taste_explanation=explanation,
                    review_insight=review_insight,
                    active_deals=active_deals,
                    saved=item.candidate.saved,
                    signals=item.signals,
                    collaborative_score=item.candidate.collaborative_score,
                    collaborative_explanation=item.candidate.collaborative_explanation,
                    collaborative_reviewer_name=item.candidate.collaborative_reviewer_name,
                    collaborative_review_excerpt=item.candidate.collaborative_review_excerpt,
                    collaborative_review_rating=item.candidate.collaborative_review_rating,
                    taste_twin_review_count=item.candidate.taste_twin_review_count,
                    taste_twin_reviews=[
                        {
                            "reviewer_name": review.reviewer_name,
                            "rating": review.rating,
                            "excerpt": review.excerpt,
                            "similarity_percent": review.similarity_percent,
                        }
                        for review in item.candidate.taste_twin_reviews
                    ],
                )
            )
        collaborative_available = any(item.collaborative_score is not None for item in items)
        return FeedResponse(
            user_id=user_id,
            total_candidates=len(candidates),
            neutral_signals=neutral_signals,
            collaborative_available=collaborative_available,
            similar_user_count=max(
                (item.candidate.similar_user_count for item in selected), default=0
            ),
            items=items,
            limit=effective.limit,
            offset=effective.offset,
        )
