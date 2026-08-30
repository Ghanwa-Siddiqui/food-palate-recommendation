"""Regenerate every stored taste vector and dish embedding with the real
Sentence Transformers model, in development data.

Two different placeholder generators produced almost everything currently
in the `taste_vector`/`embedding` columns:

- `app/embedding.py` built user taste vectors from a SHA-256-seeded random
  vector per term (see git history) - explicitly documented there as a
  "Day-1 stand-in", not a trained model.
- `DeterministicDishEmbeddingService` (backend) built the 200 marketplace
  dishes' vectors the same way, under a different hashing scheme.

Neither has any notion of meaning: "Chicken Karahi" and a user who likes
"spicy Pakistani food" land on unrelated random vectors unless the exact
same words appear in both, so cosine similarity between them is close to
noise. That's why the ranking service's `taste` signal (the heaviest
weighted one, see scoring.py WEIGHTS) came out near-zero for almost every
dish regardless of actual fit.

Both source generators are already fixed to call a real local Sentence
Transformers model (`all-MiniLM-L6-v2` by default) going forward - this
script is the one-off backfill so data seeded before that fix stops being
compared against noise. It regenerates every dish's `embedding` from its
own stored fields via `build_dish_embedding_text` (matching what
`seed.py` already does for the base catalog), and every onboarded user's
`taste_vector` by feeding their stored preference fields back through the
real `build_taste_vector`.

Naturally idempotent: given fixed model weights, embedding the same text
twice produces the same vector, so re-running just recomputes the same
values.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_engine
from app.models.dish import Dish
from app.models.user import User
from app.services.data_core.embeddings import (
    SentenceTransformerEmbeddingProvider,
    build_dish_embedding_text,
)
from scripts.seed import SeedSafetyError, extract_supabase_project_ref, verify_seed_preconditions
from scripts.seed_customer_taste_demo import _personalization

CORRECTION_CONFIRMATION = "UPGRADE_CHASKA_TASTE_AND_DISH_EMBEDDINGS"


def authorize_correction(
    *,
    database_url: str,
    app_env: str,
    confirmation: str | None,
    expected_project_ref: str | None,
) -> None:
    if app_env != "development":
        raise SeedSafetyError("development-data correction requires APP_ENV=development")
    if not secrets.compare_digest(confirmation or "", CORRECTION_CONFIRMATION):
        raise SeedSafetyError("development-data correction confirmation did not match")
    if not expected_project_ref:
        raise SeedSafetyError("EXPECTED_SUPABASE_PROJECT_REF is required")
    target_project_ref = extract_supabase_project_ref(database_url)
    if not secrets.compare_digest(target_project_ref, expected_project_ref):
        raise SeedSafetyError("Supabase project reference did not match the expected target")


def _dish_embedding_text(dish: Dish) -> str:
    return build_dish_embedding_text(
        name=dish.name,
        description=dish.description,
        cuisine=dish.cuisine,
        ingredients=dish.ingredients,
        spice_level=dish.spice_level,
        oiliness=dish.oiliness,
        sweetness=dish.sweetness,
        sourness=dish.sourness,
        saltiness=dish.saltiness,
        smokiness=dish.smokiness,
        richness=dish.richness,
        texture_tags=dish.texture_tags,
        dietary_tags=dish.dietary_tags,
        allergens=dish.allergens,
        preparation_style=dish.preparation_style,
        availability=dish.availability,
    )


def upgrade_dish_embeddings(session: Session, provider: SentenceTransformerEmbeddingProvider) -> int:
    dishes = list(session.scalars(select(Dish)))
    now = datetime.now(UTC)
    for dish in dishes:
        dish.embedding = provider.embed(_dish_embedding_text(dish))
        dish.embedding_updated_at = now
    session.flush()
    return len(dishes)


def upgrade_taste_vectors(session: Session, *, answers_and_builder=None) -> int:
    answers_cls, build_taste_vector = answers_and_builder or _personalization()
    users = list(session.scalars(select(User).where(User.onboarding_complete.is_(True))))
    now = datetime.now(UTC)
    for user in users:
        answers = answers_cls(
            city=user.city,
            preferred_cuisines=user.preferred_cuisines,
            favourite_dishes=user.favourite_dishes,
            spice_preference=user.spice_preference,
            sweetness_preference=user.sweetness_preference,
            sourness_preference=user.sourness_preference,
            saltiness_preference=user.saltiness_preference,
            oiliness_preference=user.oiliness_preference,
            richness_preference=user.richness_preference,
            preferred_textures=user.preferred_textures,
            budget_min=float(user.budget_min),
            budget_max=float(user.budget_max),
            dietary_requirements=user.dietary_requirements,
            allergies=user.allergies,
            disliked_ingredients=user.disliked_ingredients,
            require_halal=user.require_halal,
        )
        user.taste_vector = build_taste_vector(answers)
        user.taste_updated_at = now
    session.flush()
    return len(users)


@dataclass(frozen=True)
class UpgradeResult:
    dishes_upgraded: int
    users_upgraded: int


def upgrade_embeddings(session: Session) -> UpgradeResult:
    provider = SentenceTransformerEmbeddingProvider(get_settings().embedding_model)
    dishes_upgraded = upgrade_dish_embeddings(session, provider)
    users_upgraded = upgrade_taste_vectors(session)
    return UpgradeResult(dishes_upgraded, users_upgraded)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", required=True)
    args = parser.parse_args()
    settings = get_settings()
    try:
        authorize_correction(
            database_url=settings.database_url,
            app_env=settings.app_env,
            confirmation=args.confirmation,
            expected_project_ref=settings.expected_supabase_project_ref,
        )
        with Session(get_engine()) as session, session.begin():
            verify_seed_preconditions(session, require_empty_catalog=False)
            result = upgrade_embeddings(session)
    except SeedSafetyError as error:
        raise SystemExit(str(error)) from error

    print(
        f"Upgraded {result.dishes_upgraded} dish embeddings and "
        f"{result.users_upgraded} taste vectors to the real embedding model"
    )


if __name__ == "__main__":
    main()
