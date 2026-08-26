"""Idempotently load development-only sample data.

Refuses to run unless --confirm-development-data is supplied. This script does not
represent verified businesses and should never be pointed at production.
"""

import argparse
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, inspect, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_engine
from app.models.deal import Deal
from app.models.dish import Dish
from app.models.restaurant import Restaurant
from app.services.data_core.embeddings import (
    SentenceTransformerEmbeddingProvider,
    build_dish_embedding_text,
)

NAMESPACE = uuid.UUID("ac7ce18c-65a7-4315-8994-cb78cc20f077")
LOCAL_DATABASE_HOSTS = {"localhost", "127.0.0.1", "::1"}
REMOTE_DEVELOPMENT_CONFIRMATION = "SEED_CHASKA_DEVELOPMENT"
OWNED_TABLES = {"users", "restaurants", "dishes", "deals", "reviews", "interactions"}
CATALOG_MODELS = (Restaurant, Dish, Deal)
PROJECT_REF_PATTERN = re.compile(r"^[a-z0-9]+$")
CITIES = [
    ("Karachi", Decimal("24.8607"), Decimal("67.0011")),
    ("Lahore", Decimal("31.5204"), Decimal("74.3587")),
    ("Islamabad", Decimal("33.6844"), Decimal("73.0479")),
]
ALLOWED_SEED_CUISINES = (
    "Pakistani",
    "Chinese",
    "Italian",
    "Turkish",
    "Fast Food",
    "Continental",
)

# Menu categories are separate from regional cuisine classification. Keeping
# the legacy BBQ category in names preserves the existing deterministic UUIDs.
SEED_MENU_CATEGORIES = (
    "Pakistani",
    "Chinese",
    "Italian",
    "Turkish",
    "Fast Food",
    "BBQ",
    "Continental",
)
MENU_CATEGORY_CUISINE = {category: category for category in ALLOWED_SEED_CUISINES} | {
    "BBQ": "Pakistani"
}
DISH_TEMPLATES = {
    "Pakistani": [
        ("Chicken Karahi", ["chicken", "tomato", "ginger", "chilli"], [4, 3, 0, 1, 3]),
        ("Daal Chawal", ["lentils", "rice", "cumin"], [2, 2, 0, 1, 2]),
        ("Beef Pulao", ["beef", "rice", "stock", "spices"], [2, 3, 0, 0, 3]),
    ],
    "Chinese": [
        ("Chicken Chow Mein", ["noodles", "chicken", "vegetables"], [2, 2, 1, 1, 3]),
        ("Vegetable Fried Rice", ["rice", "peas", "carrot", "soy"], [1, 2, 1, 0, 3]),
        ("Hot and Sour Soup", ["stock", "mushroom", "vinegar", "chilli"], [3, 1, 0, 4, 3]),
    ],
    "Italian": [
        ("Margherita Pizza", ["flour", "tomato", "mozzarella", "basil"], [0, 2, 1, 2, 3]),
        ("Penne Arrabbiata", ["pasta", "tomato", "garlic", "chilli"], [3, 2, 1, 2, 3]),
        ("Mushroom Risotto", ["rice", "mushroom", "parmesan"], [0, 3, 1, 1, 3]),
    ],
    "Turkish": [
        ("Chicken Doner", ["chicken", "pita", "yogurt", "salad"], [2, 2, 1, 1, 3]),
        ("Mercimek Soup", ["red lentils", "carrot", "lemon"], [1, 1, 1, 2, 2]),
        ("Cheese Pide", ["flour", "cheese", "herbs"], [0, 3, 1, 0, 3]),
    ],
    "Fast Food": [
        ("Crispy Chicken Burger", ["chicken", "bun", "lettuce", "sauce"], [2, 4, 1, 1, 4]),
        ("Loaded Fries", ["potato", "cheese", "jalapeno"], [3, 4, 1, 1, 4]),
        ("Grilled Chicken Wrap", ["chicken", "flatbread", "salad"], [2, 2, 1, 1, 3]),
    ],
    "BBQ": [
        ("Chicken Tikka", ["chicken", "yogurt", "spices"], [4, 2, 0, 2, 3]),
        ("Seekh Kebab", ["beef", "onion", "herbs", "spices"], [3, 3, 0, 1, 3]),
        ("Grilled Fish", ["fish", "lemon", "herbs"], [2, 1, 0, 2, 3]),
    ],
    "Continental": [
        ("Herb Chicken", ["chicken", "herbs", "vegetables"], [1, 2, 1, 1, 2]),
        ("Mushroom Steak", ["beef", "mushroom", "cream"], [1, 3, 1, 1, 3]),
        ("Garden Pasta", ["pasta", "seasonal vegetables", "olive oil"], [1, 2, 1, 1, 2]),
    ],
}


def stable_id(kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{kind}:{key}")


class SeedSafetyError(RuntimeError):
    """Raised without including connection details or environment values."""


def _is_local_target(url: URL) -> bool:
    return url.get_backend_name() == "sqlite" or (
        url.get_backend_name() == "postgresql" and url.host in LOCAL_DATABASE_HOSTS
    )


def extract_supabase_project_ref(database_url: str) -> str:
    url = make_url(database_url)
    host = (url.host or "").lower()
    if url.get_backend_name() != "postgresql" or not (
        host.endswith(".supabase.com") or host.endswith(".supabase.co")
    ):
        raise SeedSafetyError("remote development seed target must be a Supabase PostgreSQL URL")

    candidates: set[str] = set()
    username = url.username or ""
    if username.startswith("postgres."):
        candidates.add(username.removeprefix("postgres."))
    direct_host = re.fullmatch(r"db\.([a-z0-9]+)\.supabase\.co", host)
    if direct_host:
        candidates.add(direct_host.group(1))
    if len(candidates) != 1:
        raise SeedSafetyError("could not uniquely identify the Supabase project reference")
    project_ref = candidates.pop()
    if not PROJECT_REF_PATTERN.fullmatch(project_ref):
        raise SeedSafetyError("Supabase project reference has an invalid format")
    return project_ref


def authorize_seed_target(
    *,
    database_url: str,
    app_env: str,
    allow_remote_development: bool = False,
    remote_confirmation: str | None = None,
    expected_project_ref: str | None = None,
    with_embeddings: bool = False,
) -> bool:
    """Return True for an explicitly authorized remote development target."""
    url = make_url(database_url)
    if _is_local_target(url):
        if app_env not in {"development", "test"}:
            raise SeedSafetyError("local seed requires APP_ENV development or test")
        return False
    if not allow_remote_development:
        raise SeedSafetyError("remote database seeding is disabled by default")
    if app_env != "development":
        raise SeedSafetyError("remote development seed requires APP_ENV=development")
    if not secrets.compare_digest(remote_confirmation or "", REMOTE_DEVELOPMENT_CONFIRMATION):
        raise SeedSafetyError("remote development seed confirmation did not match")
    if not expected_project_ref:
        raise SeedSafetyError("EXPECTED_SUPABASE_PROJECT_REF is required")
    target_project_ref = extract_supabase_project_ref(database_url)
    if not secrets.compare_digest(target_project_ref, expected_project_ref):
        raise SeedSafetyError("Supabase project reference did not match the expected target")
    if with_embeddings:
        raise SeedSafetyError("remote development seed does not allow embedding generation")
    return True


def assert_safe_seed_target(database_url: str) -> None:
    authorize_seed_target(database_url=database_url, app_env="development")


def get_migration_head() -> str:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head()


def verify_seed_preconditions(session: Session, *, require_empty_catalog: bool) -> None:
    bind = session.get_bind()
    inspector = inspect(bind)
    missing_tables = sorted(OWNED_TABLES - set(inspector.get_table_names()))
    if missing_tables:
        raise SeedSafetyError("required Chaska tables are missing")
    if "alembic_version" not in inspector.get_table_names():
        raise SeedSafetyError("Alembic version table is missing")
    applied_versions = set(
        session.execute(text("SELECT version_num FROM alembic_version")).scalars()
    )
    if applied_versions != {get_migration_head()}:
        raise SeedSafetyError("database migration is not at the current Alembic head")
    if require_empty_catalog:
        counts = {
            model.__tablename__: session.scalar(select(func.count()).select_from(model)) or 0
            for model in CATALOG_MODELS
        }
        if any(counts.values()):
            raise SeedSafetyError("catalog tables must be empty before remote development seed")


def seed(
    session: Session,
    *,
    with_embeddings: bool = False,
    app_env: str = "development",
    allow_remote_development: bool = False,
    remote_confirmation: str | None = None,
    expected_project_ref: str | None = None,
) -> tuple[int, int, int]:
    remote_authorized = authorize_seed_target(
        database_url=str(session.get_bind().url),
        app_env=app_env,
        allow_remote_development=allow_remote_development,
        remote_confirmation=remote_confirmation,
        expected_project_ref=expected_project_ref,
        with_embeddings=with_embeddings,
    )
    if remote_authorized:
        verify_seed_preconditions(session, require_empty_catalog=True)
    provider = (
        SentenceTransformerEmbeddingProvider(get_settings().embedding_model)
        if with_embeddings
        else None
    )
    restaurants_added = dishes_added = deals_added = 0
    now = datetime.now(UTC)
    for index in range(30):
        menu_category = SEED_MENU_CATEGORIES[index % len(SEED_MENU_CATEGORIES)]
        cuisine = MENU_CATEGORY_CUISINE[menu_category]
        city, base_lat, base_lng = CITIES[index % len(CITIES)]
        name = f"Chaska Sample {menu_category} Kitchen {index + 1:02d}"
        restaurant_id = stable_id("restaurant", name)
        restaurant = session.get(Restaurant, restaurant_id)
        if restaurant is None:
            restaurant = Restaurant(
                id=restaurant_id,
                name=name,
                description="Development sample restaurant; not a verified real business.",
                cuisine_types=[cuisine],
                address=f"Sample Block {index + 1}, Development District",
                city=city,
                latitude=base_lat + Decimal(index) / Decimal("1000"),
                longitude=base_lng + Decimal(index) / Decimal("1000"),
                price_range=["budget", "moderate", "premium"][index % 3],
                halal_status="claimed" if index % 5 else "unknown",
            )
            session.add(restaurant)
            restaurants_added += 1
        for dish_index, (dish_name, ingredients, taste) in enumerate(DISH_TEMPLATES[menu_category]):
            dish_id = stable_id("dish", f"{name}:{dish_name}")
            if session.get(Dish, dish_id) is not None:
                continue
            description = f"Sample {cuisine.lower()} dish for development and testing."
            dietary_tags = (
                ["vegetarian"] if not {"chicken", "beef", "fish"} & set(ingredients) else ["halal"]
            )
            values = dict(
                name=dish_name,
                description=description,
                cuisine=cuisine,
                ingredients=ingredients,
                spice_level=taste[0],
                oiliness=taste[1],
                sweetness=taste[2],
                sourness=taste[3],
                saltiness=taste[4],
                smokiness=3 if menu_category in {"BBQ", "Turkish"} else 1,
                richness=3 if dish_index != 1 else 2,
                texture_tags=["tender", "savory"] if dish_index != 1 else ["soft", "comforting"],
                dietary_tags=dietary_tags,
                allergens=["dairy"] if "cheese" in ingredients else [],
                preparation_style=(
                    "BBQ"
                    if menu_category == "BBQ"
                    else "grilled"
                    if menu_category == "Turkish"
                    else "cooked"
                ),
                availability=True,
            )
            embedding = provider.embed(build_dish_embedding_text(**values)) if provider else None
            session.add(
                Dish(
                    id=dish_id,
                    restaurant_id=restaurant_id,
                    price=Decimal(450 + index * 25 + dish_index * 150),
                    embedding=embedding,
                    **values,
                )
            )
            dishes_added += 1
        deal_id = stable_id("deal", name)
        if session.get(Deal, deal_id) is None:
            session.add(
                Deal(
                    id=deal_id,
                    restaurant_id=restaurant_id,
                    title="Development Sample Weekday Deal",
                    description="Synthetic promotional data for development only.",
                    discount_percentage=Decimal(10 + index % 4 * 5),
                    starts_at=now - timedelta(days=1),
                    ends_at=now + timedelta(days=30),
                    is_active=True,
                )
            )
            deals_added += 1
    session.commit()
    return restaurants_added, dishes_added, deals_added


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-development-data", action="store_true")
    parser.add_argument("--with-embeddings", action="store_true")
    parser.add_argument("--allow-remote-development", action="store_true")
    parser.add_argument("--remote-confirmation")
    args = parser.parse_args()
    if not args.confirm_development_data:
        raise SystemExit("Refusing to seed without --confirm-development-data")
    settings = get_settings()
    try:
        remote_authorized = authorize_seed_target(
            database_url=settings.database_url,
            app_env=settings.app_env,
            allow_remote_development=args.allow_remote_development,
            remote_confirmation=args.remote_confirmation,
            expected_project_ref=settings.expected_supabase_project_ref,
            with_embeddings=args.with_embeddings,
        )
    except SeedSafetyError as error:
        raise SystemExit(str(error)) from error
    with Session(get_engine()) as session:
        try:
            if not remote_authorized:
                verify_seed_preconditions(session, require_empty_catalog=False)
            counts = seed(
                session,
                with_embeddings=args.with_embeddings,
                app_env=settings.app_env,
                allow_remote_development=args.allow_remote_development,
                remote_confirmation=args.remote_confirmation,
                expected_project_ref=settings.expected_supabase_project_ref,
            )
        except SeedSafetyError as error:
            raise SystemExit(str(error)) from error
    print(f"Added {counts[0]} restaurants, {counts[1]} dishes, and {counts[2]} deals")


if __name__ == "__main__":
    main()
