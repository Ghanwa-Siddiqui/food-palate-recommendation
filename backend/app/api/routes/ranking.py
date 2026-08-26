import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies import SessionDependency
from app.repositories.ranking import RankingRepository
from app.schemas.ranking import FeedPreferences, FeedResponse
from app.services.ranking.feed_service import RankingFeedService

router = APIRouter(prefix="/ranking", tags=["ranking"])


@router.get("/feed/{user_id}", response_model=FeedResponse)
def get_user_feed(
    user_id: uuid.UUID,
    session: SessionDependency,
    preferences: Annotated[FeedPreferences, Query()],
) -> FeedResponse:
    return RankingFeedService(RankingRepository(session)).get_ranked_feed(user_id, preferences)
