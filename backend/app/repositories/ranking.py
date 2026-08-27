from collections import defaultdict
from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models.dish import Dish
from app.models.interaction import Interaction
from app.models.restaurant import Restaurant
from app.models.review import Review
from app.models.user import User
from app.services.ranking.generator import RankingCandidate, TasteTwinReviewEvidence
from app.services.ranking.scoring import calculate_cosine_similarity

ANONYMOUS_DINER = "Anonymous Chaska diner"


class RankingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_candidates(self, user_id=None) -> list[RankingCandidate]:
        interaction_subquery = (
            select(
                Interaction.dish_id,
                func.sum(
                    case(
                        (Interaction.action == "order", 3),
                        (Interaction.action == "save", 2),
                        else_=1,
                    )
                ).label("interaction_count"),
            )
            .group_by(Interaction.dish_id)
            .subquery()
        )
        saved_ids = (
            set(
                self.session.scalars(
                    select(Interaction.dish_id).where(
                        Interaction.user_id == user_id, Interaction.action == "save"
                    )
                )
            )
            if user_id is not None
            else set()
        )
        rows = (
            self.session.execute(
                select(
                    Dish,
                    Dish.review_average,
                    Dish.review_sentiment,
                    interaction_subquery.c.interaction_count,
                )
                .options(joinedload(Dish.restaurant).joinedload(Restaurant.deals))
                .join(Dish.restaurant)
                .outerjoin(interaction_subquery, interaction_subquery.c.dish_id == Dish.id)
                .where(
                    Dish.availability.is_(True),
                    Dish.archived_at.is_(None),
                    Dish.embedding.is_not(None),
                    Restaurant.available.is_(True),
                )
            )
            .unique()
            .all()
        )
        candidates = [
            RankingCandidate(
                dish=dish,
                review_average=float(review_average) if review_average is not None else None,
                review_sentiment=(
                    float(review_sentiment) if review_sentiment is not None else None
                ),
                interaction_count=int(interaction_count or 0),
                saved=dish.id in saved_ids,
            )
            for dish, review_average, review_sentiment, interaction_count in rows
        ]
        return self._with_collaborative_evidence(candidates, user_id)

    @staticmethod
    def _recency(ts: datetime) -> float:
        value = ts if ts.tzinfo else ts.replace(tzinfo=UTC)
        days = max(0.0, (datetime.now(UTC) - value).total_seconds() / 86400)
        return max(0.5, 1.0 - days / 365)

    def _with_collaborative_evidence(self, candidates, user_id):
        if user_id is None:
            return candidates
        current = self.session.get(User, user_id)
        if current is None or current.taste_vector is None:
            return candidates
        users = list(
            self.session.scalars(
                select(User).where(User.id != user_id, User.taste_vector.is_not(None))
            )
        )
        interactions = list(
            self.session.scalars(select(Interaction).where(Interaction.action != "click"))
        )
        reviews = list(self.session.scalars(select(Review).where(Review.archived_at.is_(None))))
        action_quality = {"like": 1.0, "save": 0.85, "order": 0.75, "tried": 0.5}
        evidence: dict[object, dict[object, float]] = defaultdict(dict)
        negative = {
            (item.user_id, item.dish_id) for item in interactions if item.action == "dislike"
        }
        tried = {(item.user_id, item.dish_id) for item in interactions if item.action == "tried"}
        for item in interactions:
            quality = action_quality.get(item.action)
            if quality is not None:
                evidence[item.user_id][item.dish_id] = max(
                    evidence[item.user_id].get(item.dish_id, 0), quality * self._recency(item.ts)
                )
        positive_reviews = {}
        for review in reviews:
            if review.rating < 4 or (review.sentiment is not None and review.sentiment < 0.5):
                negative.add((review.user_id, review.dish_id))
                continue
            if (review.user_id, review.dish_id) not in tried:
                continue
            quality = ((review.rating - 3) / 2) * self._recency(review.updated_at)
            evidence[review.user_id][review.dish_id] = max(
                evidence[review.user_id].get(review.dish_id, 0), quality
            )
            positive_reviews[(review.user_id, review.dish_id)] = review
        for negative_key in negative:
            evidence[negative_key[0]].pop(negative_key[1], None)
            positive_reviews.pop(negative_key, None)
        disliked = {
            item.dish_id
            for item in interactions
            if item.user_id == user_id and item.action == "dislike"
        }
        settings = get_settings()
        neighbours = []
        current_evidence = evidence[user_id]
        for user in users:
            similarity = max(
                0.0,
                calculate_cosine_similarity(list(current.taste_vector), list(user.taste_vector)),
            )
            if similarity < settings.collaborative_min_similarity:
                continue
            shared = set(current_evidence) & set(evidence[user.id])
            shared_quality = min(
                1.0,
                sum(
                    min(current_evidence[dish_id], evidence[user.id][dish_id]) for dish_id in shared
                ),
            )
            if shared_quality < settings.collaborative_min_evidence:
                continue
            neighbours.append((user, 0.75 * similarity + 0.25 * shared_quality, similarity))
        enriched = []
        for candidate in candidates:
            dish_id = candidate.dish.id
            if dish_id in disliked:
                continue
            contributions = []
            for user, evidence_weight, taste_similarity in neighbours:
                quality = evidence[user.id].get(dish_id, 0)
                review = positive_reviews.get((user.id, dish_id))
                if quality >= settings.collaborative_min_evidence and review is not None:
                    contributions.append(
                        (
                            min(1.0, evidence_weight * quality),
                            user,
                            review,
                            taste_similarity,
                        )
                    )
            contributions.sort(key=lambda value: (-value[0], str(value[1].id)))
            if not contributions:
                enriched.append(candidate)
                continue
            capped = contributions[:5]
            score = min(100.0, 100 * sum(value[0] for value in capped) / len(capped))
            best = capped[0]
            review = best[2]
            public_name = best[1].name if best[1].show_review_display_name else ANONYMOUS_DINER
            preview_contributions = sorted(
                capped,
                key=lambda value: (-value[3], -value[0], str(value[1].id)),
            )
            previews = tuple(
                TasteTwinReviewEvidence(
                    reviewer_name=(user.name if user.show_review_display_name else ANONYMOUS_DINER),
                    rating=float(twin_review.rating),
                    excerpt=(twin_review.text or "")[:180],
                    similarity_percent=round(taste_similarity * 100),
                )
                for _, user, twin_review, taste_similarity in preview_contributions[:2]
            )
            if len(capped) == 1 and review is not None:
                explanation = f"{public_name} has similar tastes and rated this {review.rating}/5."
            else:
                noun = "diners" if len(capped) != 1 else "diner"
                explanation = (
                    f"Popular with {len(capped)} {noun} whose tastes are similar to yours."
                )
            enriched.append(
                replace(
                    candidate,
                    collaborative_score=round(score, 2),
                    similar_user_count=len(capped),
                    collaborative_explanation=explanation,
                    collaborative_reviewer_name=(public_name if review else None),
                    collaborative_review_excerpt=((review.text or "")[:180] if review else None),
                    collaborative_review_rating=(float(review.rating) if review else None),
                    taste_twin_review_count=len(capped),
                    taste_twin_reviews=previews,
                )
            )
        return enriched
