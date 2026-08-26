"""Transactionally replace the exact deterministic sample catalog with the real manifest."""

import argparse
import json
import re
import secrets
import uuid
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_engine
from app.models.deal import Deal
from app.models.dish import Dish
from app.models.interaction import Interaction
from app.models.restaurant import Restaurant
from app.models.review import Review
from app.models.user import User
from scripts.seed import (
    DISH_TEMPLATES,
    OWNED_TABLES,
    SEED_MENU_CATEGORIES,
    SeedSafetyError,
    extract_supabase_project_ref,
    get_migration_head,
    stable_id,
)

CONFIRMATION = "REPLACE_CHASKA_SAMPLE_WITH_REAL_CATALOG"
MANIFEST_DIR = Path(__file__).resolve().parents[2] / "data" / "real_catalog"
FORBIDDEN_CUISINES = {"BBQ", "Grill", "Steak", "Seafood", "Café", "Cafe", "Bakery"}


def authorize_target(
    *, database_url: str, app_env: str, confirmation: str | None, expected_project_ref: str | None
) -> str:
    if app_env != "development":
        raise SeedSafetyError("replacement requires APP_ENV=development")
    if not secrets.compare_digest(confirmation or "", CONFIRMATION):
        raise SeedSafetyError("replacement confirmation token did not match")
    if not expected_project_ref:
        raise SeedSafetyError("EXPECTED_SUPABASE_PROJECT_REF is required")
    actual_ref = extract_supabase_project_ref(database_url)
    if not secrets.compare_digest(actual_ref, expected_project_ref):
        raise SeedSafetyError("Supabase project reference did not match the expected target")
    return actual_ref


def load_manifest(manifest_dir: Path = MANIFEST_DIR) -> tuple[list[dict], list[dict], dict]:
    try:
        restaurants = json.loads((manifest_dir / "restaurants.json").read_text(encoding="utf-8"))
        dishes = json.loads((manifest_dir / "dishes.json").read_text(encoding="utf-8"))
        sources = json.loads((manifest_dir / "sources.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SeedSafetyError("real catalog manifest could not be loaded") from error
    validate_manifest(restaurants, dishes, sources)
    return restaurants, dishes, sources


def validate_manifest(restaurants: list[dict], dishes: list[dict], sources: dict) -> None:
    errors: list[str] = []
    restaurant_ids = {row.get("id") for row in restaurants}
    dish_ids = {row.get("id") for row in dishes}
    dish_counts = Counter(row.get("restaurant_id") for row in dishes)
    restaurant_sources = {row.get("restaurant_id") for row in sources.get("restaurants", [])}
    dish_sources = {row.get("dish_id") for row in sources.get("dishes", [])}
    brands = [row.get("brand_name", "") for row in sources.get("restaurants", [])]
    normalized_brands = {re.sub(r"[^a-z0-9]", "", brand.lower()) for brand in brands}
    city_counts = Counter(
        "Islamabad/Rawalpindi"
        if row.get("city") in {"Islamabad", "Rawalpindi"}
        else row.get("city")
        for row in restaurants
    )
    restaurant_required = {
        "id",
        "name",
        "description",
        "cuisine_types",
        "address",
        "city",
        "lat",
        "lng",
        "location_verified",
        "coordinates_source_url",
        "coordinates_verified_at",
        "price_range",
        "halal_status",
        "created_at",
        "updated_at",
    }
    dish_required = {
        "id",
        "restaurant_id",
        "name",
        "description",
        "cuisine",
        "ingredients",
        "price",
        "spice_level",
        "oiliness",
        "sweetness",
        "sourness",
        "saltiness",
        "smokiness",
        "richness",
        "texture_tags",
        "dietary_tags",
        "allergens",
        "preparation_style",
        "availability",
        "lat",
        "lng",
        "created_at",
        "updated_at",
    }
    if len(restaurants) != 30 or len(restaurant_ids) != 30:
        errors.append("manifest must contain 30 unique restaurants")
    if len(dishes) != 90 or len(dish_ids) != 90:
        errors.append("manifest must contain 90 unique dishes")
    if restaurant_ids and any(dish_counts[rid] != 3 for rid in restaurant_ids):
        errors.append("each manifest restaurant must have exactly three dishes")
    if len(normalized_brands) != 30 or "" in normalized_brands:
        errors.append("manifest must contain 30 unique normalized brands")
    if city_counts != {"Lahore": 10, "Karachi": 10, "Islamabad/Rawalpindi": 10}:
        errors.append("manifest city split is invalid")
    if any(row.get("restaurant_id") not in restaurant_ids for row in dishes):
        errors.append("manifest contains orphan dishes")
    if any(not isinstance(row.get("price"), (int, float)) or row["price"] <= 0 for row in dishes):
        errors.append("manifest prices must be positive numbers")
    if any(set(row) != restaurant_required for row in restaurants):
        errors.append("restaurant manifest fields do not match the v1 contract")
    if any(set(row) != dish_required for row in dishes):
        errors.append("dish manifest fields do not match the v1 contract")
    if any((row["lat"] is None) != (row["lng"] is None) for row in restaurants + dishes):
        errors.append("manifest coordinate pairs are invalid")
    if any(row["lat"] is None and row["location_verified"] for row in restaurants):
        errors.append("null restaurant coordinates cannot be verified")
    if any(row["halal_status"] != "unknown" for row in restaurants):
        errors.append("manifest contains unsupported halal claims")
    if any("sample" in f"{row['name']} {row['address']}".lower() for row in restaurants):
        errors.append("manifest contains sample restaurant markers")
    if any(FORBIDDEN_CUISINES & set(row["cuisine_types"]) for row in restaurants):
        errors.append("manifest contains forbidden restaurant cuisine values")
    if any(row["cuisine"] in FORBIDDEN_CUISINES for row in dishes):
        errors.append("manifest contains forbidden dish cuisine values")
    if restaurant_sources != restaurant_ids or dish_sources != dish_ids:
        errors.append("manifest source mappings are incomplete")
    if any(
        not row.get("address_source_url") or not row.get("menu_source_url")
        for row in sources.get("restaurants", [])
    ):
        errors.append("restaurant source URLs are incomplete")
    if any(not row.get("menu_source_url") for row in sources.get("dishes", [])):
        errors.append("dish source URLs are incomplete")
    if sources.get("metadata", {}).get("deals_count") != 0:
        errors.append("manifest must contain zero deals")
    if errors:
        raise SeedSafetyError("; ".join(errors))


def expected_sample_state() -> tuple[set[uuid.UUID], set[uuid.UUID], set[uuid.UUID], dict]:
    restaurant_ids: set[uuid.UUID] = set()
    dish_ids: set[uuid.UUID] = set()
    deal_ids: set[uuid.UUID] = set()
    relationships: dict[uuid.UUID, uuid.UUID] = {}
    for index in range(30):
        category = SEED_MENU_CATEGORIES[index % len(SEED_MENU_CATEGORIES)]
        name = f"Chaska Sample {category} Kitchen {index + 1:02d}"
        restaurant_id = stable_id("restaurant", name)
        restaurant_ids.add(restaurant_id)
        deal_ids.add(stable_id("deal", name))
        for dish_name, _ingredients, _taste in DISH_TEMPLATES[category]:
            dish_id = stable_id("dish", f"{name}:{dish_name}")
            dish_ids.add(dish_id)
            relationships[dish_id] = restaurant_id
    return restaurant_ids, dish_ids, deal_ids, relationships


def verify_database_structure(session: Session) -> None:
    tables = set(inspect(session.get_bind()).get_table_names())
    if not OWNED_TABLES <= tables:
        raise SeedSafetyError("required Chaska tables are missing")
    if "alembic_version" not in tables:
        raise SeedSafetyError("Alembic version table is missing")
    versions = set(session.execute(text("SELECT version_num FROM alembic_version")).scalars())
    if versions != {get_migration_head()}:
        raise SeedSafetyError("database migration is not at the current Alembic head")


def _ids(session: Session, model) -> set[uuid.UUID]:
    return set(session.scalars(select(model.id)))


def is_real_catalog_installed(
    session: Session, restaurants: list[dict], dishes: list[dict]
) -> bool:
    expected_restaurants = {uuid.UUID(row["id"]) for row in restaurants}
    expected_dishes = {uuid.UUID(row["id"]) for row in dishes}
    if _ids(session, Restaurant) != expected_restaurants or _ids(session, Dish) != expected_dishes:
        return False
    if (session.scalar(select(func.count()).select_from(Deal)) or 0) != 0:
        return False
    relationships = dict(session.execute(select(Dish.id, Dish.restaurant_id)).all())
    return relationships == {
        uuid.UUID(row["id"]): uuid.UUID(row["restaurant_id"]) for row in dishes
    }


def verify_exact_sample_state(session: Session) -> None:
    expected_restaurants, expected_dishes, expected_deals, expected_relationships = (
        expected_sample_state()
    )
    if _ids(session, Restaurant) != expected_restaurants:
        raise SeedSafetyError(
            "database does not contain the exact deterministic sample restaurants"
        )
    if _ids(session, Dish) != expected_dishes:
        raise SeedSafetyError("database does not contain the exact deterministic sample dishes")
    if _ids(session, Deal) != expected_deals:
        raise SeedSafetyError("database does not contain the exact deterministic sample deals")
    relationships = dict(session.execute(select(Dish.id, Dish.restaurant_id)).all())
    if relationships != expected_relationships:
        raise SeedSafetyError("sample dish relationships do not match the deterministic seed")
    deal_parents = dict(session.execute(select(Deal.id, Deal.restaurant_id)).all())
    if set(deal_parents.values()) != expected_restaurants or len(deal_parents) != 30:
        raise SeedSafetyError("sample deal relationships do not match the deterministic seed")
    # The exact ID sets above reject every unexpected catalog row. These tables must also be
    # unused so replacement cannot invalidate user-owned development activity.
    related_counts = {
        "users": session.scalar(select(func.count()).select_from(User)) or 0,
        "reviews": session.scalar(select(func.count()).select_from(Review)) or 0,
        "interactions": session.scalar(select(func.count()).select_from(Interaction)) or 0,
    }
    if any(related_counts.values()):
        raise SeedSafetyError("users, reviews, and interactions must be empty before replacement")


def insert_manifest(session: Session, restaurants: list[dict], dishes: list[dict]) -> None:
    for row in restaurants:
        session.add(
            Restaurant(
                id=uuid.UUID(row["id"]),
                name=row["name"],
                description=row["description"],
                cuisine_types=row["cuisine_types"],
                address=row["address"],
                city=row["city"],
                latitude=row["lat"],
                longitude=row["lng"],
                location_verified=row["location_verified"],
                coordinates_source_url=row["coordinates_source_url"],
                coordinates_verified_at=(
                    datetime.fromisoformat(row["coordinates_verified_at"])
                    if row["coordinates_verified_at"]
                    else None
                ),
                price_range=row["price_range"],
                halal_status=row["halal_status"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
        )
    session.flush()
    for row in dishes:
        session.add(
            Dish(
                id=uuid.UUID(row["id"]),
                restaurant_id=uuid.UUID(row["restaurant_id"]),
                name=row["name"],
                description=row["description"],
                cuisine=row["cuisine"],
                ingredients=row["ingredients"],
                price=Decimal(str(row["price"])),
                spice_level=row["spice_level"],
                oiliness=row["oiliness"],
                sweetness=row["sweetness"],
                sourness=row["sourness"],
                saltiness=row["saltiness"],
                smokiness=row["smokiness"],
                richness=row["richness"],
                texture_tags=row["texture_tags"],
                dietary_tags=row["dietary_tags"],
                allergens=row["allergens"],
                preparation_style=row["preparation_style"],
                availability=row["availability"],
                embedding=None,
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
        )


def replace_catalog(
    session: Session,
    restaurants: list[dict],
    dishes: list[dict],
    *,
    verify_structure: bool = True,
    fail_after_delete: bool = False,
) -> str:
    if verify_structure:
        verify_database_structure(session)
    if is_real_catalog_installed(session, restaurants, dishes):
        return "already_installed"
    verify_exact_sample_state(session)
    sample_restaurants, sample_dishes, sample_deals, _ = expected_sample_state()
    session.execute(delete(Deal).where(Deal.id.in_(sample_deals)))
    session.execute(delete(Dish).where(Dish.id.in_(sample_dishes)))
    session.execute(delete(Restaurant).where(Restaurant.id.in_(sample_restaurants)))
    if fail_after_delete:
        raise RuntimeError("injected replacement failure")
    insert_manifest(session, restaurants, dishes)
    session.flush()
    if not is_real_catalog_installed(session, restaurants, dishes):
        raise SeedSafetyError("post-replacement catalog validation failed")
    return "replaced"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", required=True)
    args = parser.parse_args()
    settings = get_settings()
    try:
        authorize_target(
            database_url=settings.database_url,
            app_env=settings.app_env,
            confirmation=args.confirmation,
            expected_project_ref=settings.expected_supabase_project_ref,
        )
        restaurants, dishes, _sources = load_manifest()
        with Session(get_engine()) as session, session.begin():
            result = replace_catalog(session, restaurants, dishes)
    except (SeedSafetyError, RuntimeError) as error:
        raise SystemExit(str(error)) from error
    if result == "already_installed":
        print("Real catalog already installed; no database changes were made.")
    else:
        print("Replaced verified sample catalog with 30 restaurants, 90 dishes, and 0 deals.")


if __name__ == "__main__":
    main()
