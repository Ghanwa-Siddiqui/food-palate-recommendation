from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.dish import Dish
from app.models.interaction import Interaction
from app.models.review import Review
from app.services.ranking.generator import RankingCandidate


class RankingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_candidates(self) -> list[RankingCandidate]:
        review_subquery = (
            select(Review.dish_id, func.avg(Review.rating).label("review_average"))
            .group_by(Review.dish_id)
            .subquery()
        )
        interaction_subquery = (
            select(Interaction.dish_id, func.count().label("interaction_count"))
            .group_by(Interaction.dish_id)
            .subquery()
        )
        rows = self.session.execute(
            select(
                Dish,
                review_subquery.c.review_average,
                interaction_subquery.c.interaction_count,
            )
            .options(joinedload(Dish.restaurant))
            .outerjoin(review_subquery, review_subquery.c.dish_id == Dish.id)
            .outerjoin(interaction_subquery, interaction_subquery.c.dish_id == Dish.id)
        ).all()
        return [
            RankingCandidate(
                dish=dish,
                review_average=float(review_average) if review_average is not None else None,
                interaction_count=int(interaction_count or 0),
            )
            for dish, review_average, interaction_count in rows
        ]
