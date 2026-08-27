import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.api.dependencies import PrivateAPIDependency, SessionDependency
from app.models.dish import Dish
from app.models.interaction import Interaction
from app.models.review import Review
from app.models.user import User
from app.schemas.review import (
    OwnReviewRead,
    PublicReviewRead,
    ReviewCreate,
    ReviewSummary,
    ReviewUpdate,
)
from app.services.data_core.catalog import NotFoundError
from app.services.data_core.review_processing import ReviewProcessor, get_review_processor

router = APIRouter(prefix="/reviews", tags=["reviews"])
ANONYMOUS = "Anonymous Chaska diner"


def _actor(value: str | None) -> uuid.UUID:
    try:
        return uuid.UUID(value or "")
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Authenticated customer required") from exc


def _public(review: Review) -> PublicReviewRead:
    name = review.user.name if review.user and review.user.show_review_display_name else ANONYMOUS
    return PublicReviewRead(
        id=review.id,
        dish_id=review.dish_id,
        rating=review.rating,
        text=review.text or "",
        reviewer_name=name,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


def _recompute(dish: Dish, reviews: list[Review]) -> None:
    dish.review_count = len(reviews)
    dish.review_average = sum(item.rating for item in reviews) / len(reviews) if reviews else None
    structured = [item for item in reviews if item.processing_status == "complete"]
    dish.review_sentiment = (
        sum(item.sentiment for item in structured if item.sentiment is not None) / len(structured)
        if structured
        else None
    )
    dish.review_spice = (
        sum(item.spice_score for item in structured if item.spice_score is not None)
        / len(structured)
        if structured
        else None
    )
    dish.review_oiliness = (
        sum(item.oiliness_score for item in structured if item.oiliness_score is not None)
        / len(structured)
        if structured
        else None
    )
    tags = Counter(tag for item in structured for tag in item.flavor_tags)
    dish.review_flavor_tags = [
        tag for tag, _ in sorted(tags.items(), key=lambda value: (-value[1], value[0]))[:8]
    ]
    dish.review_aggregated_at = datetime.now(UTC)


def _process(review: Review, processor: ReviewProcessor) -> None:
    try:
        result = processor.process(review.text or "", review.rating)
        review.sentiment, review.spice_score, review.oiliness_score = (
            result.sentiment,
            result.spice,
            result.oiliness,
        )
        review.flavor_tags, review.review_embedding = result.tags, result.embedding
        review.processing_status, review.processing_error_code = "complete", None
    except Exception as exc:
        review.sentiment = review.spice_score = review.oiliness_score = None
        review.flavor_tags, review.review_embedding = [], None
        review.processing_status = "unavailable"
        review.processing_error_code = exc.__class__.__name__[:60]


@router.get("/{dish_id}", response_model=list[PublicReviewRead])
def list_reviews(dish_id: uuid.UUID, session: SessionDependency):
    rows = session.scalars(
        select(Review)
        .options(joinedload(Review.user))
        .where(Review.dish_id == dish_id, Review.archived_at.is_(None))
        .order_by(Review.created_at.desc())
    ).all()
    return [_public(row) for row in rows]


@router.get("/{dish_id}/mine", response_model=OwnReviewRead | None)
def my_review(
    dish_id: uuid.UUID,
    session: SessionDependency,
    _private: PrivateAPIDependency,
    actor: Annotated[str | None, Header(alias="X-Chaska-User-ID")] = None,
):
    user_id = _actor(actor)
    review = session.scalar(
        select(Review)
        .options(joinedload(Review.user))
        .where(Review.dish_id == dish_id, Review.user_id == user_id, Review.archived_at.is_(None))
    )
    if review is None:
        return None
    return OwnReviewRead(**_public(review).model_dump(), processing_status=review.processing_status)


@router.post("", response_model=OwnReviewRead)
def create_review(
    payload: ReviewCreate,
    session: SessionDependency,
    _private: PrivateAPIDependency,
    processor: Annotated[ReviewProcessor, Depends(get_review_processor)],
    actor: Annotated[str | None, Header(alias="X-Chaska-User-ID")] = None,
):
    user_id = _actor(actor)
    user, dish = session.get(User, user_id), session.get(Dish, payload.dish_id)
    if user is None or user.role != "customer":
        raise HTTPException(status_code=403, detail="Customer account required")
    if dish is None:
        raise NotFoundError("dish", payload.dish_id)
    existing_key = session.scalar(
        select(Review)
        .options(joinedload(Review.user))
        .where(Review.submission_key == payload.submission_key)
    )
    if existing_key:
        if existing_key.user_id != user_id:
            raise HTTPException(status_code=409, detail="Submission key already used")
        return OwnReviewRead(
            **_public(existing_key).model_dump(), processing_status=existing_key.processing_status
        )
    if dish.archived_at is not None or not dish.availability:
        raise HTTPException(status_code=409, detail="Dish is not accepting new reviews")
    if not payload.tried_confirmation:
        raise HTTPException(status_code=422, detail="Confirm that you tried this dish")
    tried = session.scalar(
        select(Interaction).where(
            Interaction.user_id == user_id,
            Interaction.dish_id == dish.id,
            Interaction.action == "tried",
        )
    )
    if tried is None:
        raise HTTPException(status_code=422, detail="Tried confirmation must be recorded first")
    duplicate = session.scalar(
        select(Review).where(
            Review.user_id == user_id, Review.dish_id == dish.id, Review.archived_at.is_(None)
        )
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="An active review already exists")
    user.show_review_display_name = payload.show_display_name
    review = Review(
        user_id=user_id,
        dish_id=dish.id,
        rating=payload.rating,
        text=payload.text,
        submission_key=payload.submission_key,
    )
    session.add(review)
    session.flush()
    _process(review, processor)
    _recompute(
        dish,
        [
            *session.scalars(
                select(Review).where(Review.dish_id == dish.id, Review.archived_at.is_(None))
            ).all()
        ],
    )
    session.commit()
    session.refresh(review)
    return OwnReviewRead(**_public(review).model_dump(), processing_status=review.processing_status)


@router.put("/{review_id}", response_model=OwnReviewRead)
def update_review(
    review_id: uuid.UUID,
    payload: ReviewUpdate,
    session: SessionDependency,
    _private: PrivateAPIDependency,
    processor: Annotated[ReviewProcessor, Depends(get_review_processor)],
    actor: Annotated[str | None, Header(alias="X-Chaska-User-ID")] = None,
):
    user_id = _actor(actor)
    review = session.scalar(
        select(Review)
        .options(joinedload(Review.user))
        .where(Review.id == review_id, Review.archived_at.is_(None))
    )
    if review is None:
        raise NotFoundError("review", review_id)
    if review.user_id != user_id or review.user.role != "customer":
        raise HTTPException(status_code=403, detail="Review ownership check failed")
    review.rating, review.text, review.updated_at = payload.rating, payload.text, datetime.now(UTC)
    review.user.show_review_display_name = payload.show_display_name
    _process(review, processor)
    dish = session.get(Dish, review.dish_id)
    _recompute(
        dish,
        list(
            session.scalars(
                select(Review).where(Review.dish_id == review.dish_id, Review.archived_at.is_(None))
            )
        ),
    )
    session.commit()
    session.refresh(review)
    return OwnReviewRead(**_public(review).model_dump(), processing_status=review.processing_status)


@router.get("/{dish_id}/summary", response_model=ReviewSummary)
def review_summary(dish_id: uuid.UUID, session: SessionDependency):
    dish = session.get(Dish, dish_id)
    if dish is None:
        raise NotFoundError("dish", dish_id)
    return ReviewSummary(
        dish_id=dish.id,
        review_count=dish.review_count,
        average_rating=float(dish.review_average) if dish.review_average is not None else None,
        avg_sentiment=float(dish.review_sentiment) if dish.review_sentiment is not None else None,
        spice_level=float(dish.review_spice) if dish.review_spice is not None else None,
        oiliness=float(dish.review_oiliness) if dish.review_oiliness is not None else None,
        flavor_tags=dish.review_flavor_tags,
    )
