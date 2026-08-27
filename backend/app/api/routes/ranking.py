import uuid
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query

from app.api.dependencies import PrivateAPIDependency, SessionDependency
from app.core.config import get_settings
from app.repositories.ranking import RankingRepository
from app.schemas.ranking import FeedPreferences, FeedResponse
from app.services.ranking.feed_service import RankingFeedService

router = APIRouter(prefix="/ranking", tags=["ranking"])


@router.get("/feed/{user_id}", response_model=FeedResponse)
def get_user_feed(
    user_id: uuid.UUID,
    session: SessionDependency,
    preferences: Annotated[FeedPreferences, Query()],
    _private: PrivateAPIDependency,
    actor: Annotated[str | None, Header(alias="X-Chaska-User-ID")] = None,
) -> FeedResponse:
    if get_settings().internal_api_key and actor != str(user_id):
        raise HTTPException(status_code=403, detail="User ownership check failed")
    return RankingFeedService(RankingRepository(session)).get_ranked_feed(user_id, preferences)
