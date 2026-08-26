import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies import SessionDependency
from app.repositories.deals import DealRepository
from app.schemas.deal import DealPage, DealRead
from app.services.data_core.catalog import DealService

router = APIRouter(prefix="/deals", tags=["deals"])


@router.get("", response_model=DealPage)
def list_deals(
    session: SessionDependency,
    restaurant: uuid.UUID | None = None,
    active_only: bool = True,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DealPage:
    return DealService(DealRepository(session)).list(
        restaurant_id=restaurant,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )


@router.get("/{deal_id}", response_model=DealRead)
def get_deal(deal_id: uuid.UUID, session: SessionDependency) -> DealRead:
    return DealService(DealRepository(session)).get(deal_id)
