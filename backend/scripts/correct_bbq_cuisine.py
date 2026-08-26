"""Correct the legacy BBQ cuisine classification in development data."""

import argparse
import secrets
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_engine
from app.models.dish import Dish
from app.models.restaurant import Restaurant
from scripts.seed import (
    SeedSafetyError,
    extract_supabase_project_ref,
    stable_id,
    verify_seed_preconditions,
)

CORRECTION_CONFIRMATION = "CORRECT_CHASKA_BBQ_CUISINE"
BBQ_RESTAURANT_NAMES = (
    "Chaska Sample BBQ Kitchen 06",
    "Chaska Sample BBQ Kitchen 13",
    "Chaska Sample BBQ Kitchen 20",
    "Chaska Sample BBQ Kitchen 27",
)
BBQ_DISH_NAMES = ("Chicken Tikka", "Seekh Kebab", "Grilled Fish")


@dataclass(frozen=True)
class CorrectionResult:
    status: str
    restaurants_updated: int
    dishes_updated: int


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


def correct_bbq_cuisine(session: Session) -> CorrectionResult:
    """Validate and correct exactly four restaurants and twelve dishes."""
    expected_restaurant_ids = {name: stable_id("restaurant", name) for name in BBQ_RESTAURANT_NAMES}
    restaurants = session.scalars(
        select(Restaurant).where(Restaurant.name.in_(BBQ_RESTAURANT_NAMES))
    ).all()
    actual_restaurant_ids = {restaurant.name: restaurant.id for restaurant in restaurants}
    if actual_restaurant_ids != expected_restaurant_ids or len(restaurants) != 4:
        raise SeedSafetyError("BBQ correction restaurant count or IDs did not match expectations")

    restaurant_ids = set(expected_restaurant_ids.values())
    dishes = session.scalars(select(Dish).where(Dish.restaurant_id.in_(restaurant_ids))).all()
    expected_dish_ids = {
        (restaurant_name, dish_name): stable_id("dish", f"{restaurant_name}:{dish_name}")
        for restaurant_name in BBQ_RESTAURANT_NAMES
        for dish_name in BBQ_DISH_NAMES
    }
    restaurant_names_by_id = {value: key for key, value in expected_restaurant_ids.items()}
    actual_dish_ids = {
        (restaurant_names_by_id[dish.restaurant_id], dish.name): dish.id for dish in dishes
    }
    if actual_dish_ids != expected_dish_ids or len(dishes) != 12:
        raise SeedSafetyError("BBQ correction dish count, IDs, or relationships did not match")

    restaurants_are_legacy = all(r.cuisine_types == ["BBQ"] for r in restaurants)
    restaurants_are_corrected = all(r.cuisine_types == ["Pakistani"] for r in restaurants)
    dishes_are_legacy = all(
        dish.cuisine == "BBQ" and dish.preparation_style == "grilled" and dish.smokiness == 3
        for dish in dishes
    )
    dishes_are_corrected = all(
        dish.cuisine == "Pakistani" and dish.preparation_style == "BBQ" and dish.smokiness == 3
        for dish in dishes
    )

    if restaurants_are_corrected and dishes_are_corrected:
        return CorrectionResult("already_corrected", 0, 0)
    if not (restaurants_are_legacy and dishes_are_legacy):
        raise SeedSafetyError("BBQ correction records were in an unexpected or partial state")

    for restaurant in restaurants:
        restaurant.cuisine_types = ["Pakistani"]
    for dish in dishes:
        dish.cuisine = "Pakistani"
        dish.preparation_style = "BBQ"
        dish.smokiness = 3
    session.flush()
    return CorrectionResult("corrected", 4, 12)


def main() -> None:
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
            result = correct_bbq_cuisine(session)
    except SeedSafetyError as error:
        raise SystemExit(str(error)) from error

    if result.status == "already_corrected":
        print("Development cuisine data is already corrected; no changes made")
    else:
        print("Corrected 4 restaurants and 12 dishes")


if __name__ == "__main__":
    main()
