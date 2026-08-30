"""Guarded one-time development partner marketplace seed."""

from __future__ import annotations

import argparse
import csv
import os
import secrets
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_engine
from app.models.dish import Dish
from app.models.restaurant import Restaurant
from app.models.user import User
from app.repositories.ranking import RankingRepository
from app.schemas.dish import PartnerDishCreate
from app.services.data_core.embeddings import (
    SentenceTransformerEmbeddingProvider,
    build_dish_embedding_text,
)

_EMBEDDING_TEXT_FIELDS = (
    "name",
    "description",
    "cuisine",
    "ingredients",
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
)

BATCH = "partner-marketplace-demo-v1"
ROOT = Path(__file__).resolve().parents[2]
CREDENTIALS = ROOT / ".dev-data" / "partner-demo-credentials.csv"
NAMESPACE = uuid.UUID("bf203772-62f8-43ea-a374-c1269aa001f6")
PARTNERS = [
    ("Areeba Khan", "Lahore"),
    ("Hamza Qureshi", "Karachi"),
    ("Maham Siddiqui", "Islamabad"),
    ("Daniyal Ahmed", "Rawalpindi"),
    ("Zoya Malik", "Lahore"),
    ("Saad Raza", "Karachi"),
    ("Hira Shah", "Islamabad"),
    ("Bilal Tariq", "Rawalpindi"),
    ("Nimra Iqbal", "Lahore"),
    ("Omer Farooq", "Karachi"),
]
RESTAURANTS = [
    ("Saffron Courtyard", "Pakistani", "Lahore", "24 MM Alam Road, Gulberg III", 31.5204, 74.3587),
    ("Jade Wok House", "Chinese", "Lahore", "12 CCA, DHA Phase 5", 31.4697, 74.4091),
    ("Harbour Karahi", "Pakistani", "Karachi", "8-C Khayaban-e-Seher, DHA", 24.8072, 67.0648),
    ("Pasta Veranda", "Italian", "Karachi", "26-C Lane 4, Bukhari Commercial", 24.8162, 67.0438),
    ("Anatolia Table", "Turkish", "Islamabad", "F-7 Markaz", 33.7205, 73.0551),
    (
        "Capital Grill Room",
        "Continental",
        "Islamabad",
        "Blue Area, Jinnah Avenue",
        33.7102,
        73.0559,
    ),
    ("Pindi Tandoor", "Pakistani", "Rawalpindi", "Saddar, Bank Road", 33.5969, 73.0528),
    ("Urban Bun Works", "Fast Food", "Rawalpindi", "Bahria Food Street, Phase 7", 33.5177, 73.1175),
    ("Olive & Ember", "Continental", "Lahore", "Fortress Stadium, Cantt", 31.5320, 74.3660),
    ("Bosphorus Kitchen", "Turkish", "Lahore", "Johar Town, Block R1", 31.4694, 74.2728),
    ("Canton Garden", "Chinese", "Karachi", "Block 4, Clifton", 24.8138, 67.0305),
    ("Crust District", "Fast Food", "Karachi", "Bahadurabad, Tariq Road", 24.8824, 67.0676),
    ("Margalla Dastarkhwan", "Pakistani", "Islamabad", "E-11 Markaz", 33.6994, 72.9746),
    ("Roma Hearth", "Italian", "Islamabad", "Beverly Centre, Blue Area", 33.7077, 73.0525),
    (
        "Silk Route Wok",
        "Chinese",
        "Rawalpindi",
        "Commercial Market, Satellite Town",
        33.6420,
        73.0635,
    ),
    ("Copper Fork", "Continental", "Rawalpindi", "PWD Main Boulevard", 33.5704, 73.1345),
    ("Lahore Bun Lab", "Fast Food", "Lahore", "Model Town Link Road", 31.4839, 74.3262),
    ("Trattoria Noor", "Italian", "Lahore", "DHA Phase 6, Main Boulevard", 31.4747, 74.4632),
    ("Istanbul Passage", "Turkish", "Karachi", "Shahbaz Commercial, DHA", 24.8039, 67.0710),
    ("Seaview Continental", "Continental", "Karachi", "Sea View Road, Clifton", 24.7856, 67.0431),
]
DISHES = {
    "Pakistani": [
        "Chicken Biryani",
        "Chicken Karahi",
        "Mutton Pulao",
        "Beef Nihari",
        "Daal Makhani",
        "Seekh Kebab",
        "Chicken Tikka",
        "Palak Paneer",
        "Haleem",
        "Chapli Kebab",
    ],
    "Chinese": [
        "Chicken Chow Mein",
        "Egg Fried Rice",
        "Kung Pao Chicken",
        "Beef Chilli Dry",
        "Chicken Manchurian",
        "Hot and Sour Soup",
        "Szechuan Chicken",
        "Vegetable Chow Mein",
        "Honey Wings",
        "Mongolian Beef",
    ],
    "Italian": [
        "Margherita Pizza",
        "Chicken Alfredo",
        "Spaghetti Bolognese",
        "Penne Arrabbiata",
        "Lasagna",
        "Mushroom Risotto",
        "Pepperoni Pizza",
        "Pesto Pasta",
        "Chicken Parmigiana",
        "Tiramisu",
    ],
    "Turkish": [
        "Adana Kebab",
        "Chicken Shish",
        "Lahmacun",
        "Beef Doner",
        "Pide",
        "Manti",
        "Iskender Kebab",
        "Mercimek Soup",
        "Kofte",
        "Kunefe",
    ],
    "Fast Food": [
        "Classic Beef Burger",
        "Crispy Chicken Burger",
        "Loaded Fries",
        "Chicken Wings",
        "Club Sandwich",
        "Philly Cheesesteak",
        "Chicken Wrap",
        "Mozzarella Sticks",
        "Jalapeno Burger",
        "Chocolate Shake",
    ],
    "Continental": [
        "Grilled Chicken",
        "Pepper Steak",
        "Fish and Chips",
        "Chicken Stroganoff",
        "Beef Medallions",
        "Roast Chicken",
        "Cream of Mushroom Soup",
        "Caesar Salad",
        "Herb Crusted Fish",
        "Bread Pudding",
    ],
}


class SeedError(RuntimeError):
    pass


def _load_root_env() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def _id(kind: str, value: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{BATCH}:{kind}:{value}")


def plan() -> tuple[list[dict], list[dict]]:
    restaurants, dishes = [], []
    for index, row in enumerate(RESTAURANTS):
        owner_index = index // 2
        rid = _id("restaurant", row[0])
        restaurants.append(
            {
                "id": rid,
                "owner_index": owner_index,
                "name": row[0],
                "cuisine": row[1],
                "city": row[2],
                "address": row[3],
                "lat": row[4],
                "lng": row[5],
            }
        )
        for dish_index, name in enumerate(DISHES[row[1]]):
            dishes.append(
                {
                    "id": _id("dish", f"{row[0]}:{name}"),
                    "restaurant_id": rid,
                    "name": name,
                    "cuisine": row[1],
                    "index": dish_index,
                }
            )
    return restaurants, dishes


def _credentials() -> list[dict]:
    if CREDENTIALS.exists():
        with CREDENTIALS.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    CREDENTIALS.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, (name, _) in enumerate(PARTNERS):
        owned = [row[0] for row in RESTAURANTS[index * 2 : index * 2 + 2]]
        rows.append(
            {
                "display_name": name,
                "email": f"partner.demo.{index + 1:02d}@chaska.dev",
                "password": secrets.token_urlsafe(24) + "!9aA",
                "restaurant_names": " | ".join(owned),
            }
        )
    with CREDENTIALS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return rows


def _auth_user(url: str, key: str, row: dict) -> uuid.UUID:
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    payload = {
        "email": row["email"],
        "password": row["password"],
        "data": {"name": row["display_name"], "role": "restaurant_partner"},
    }
    response = httpx.post(
        f"{url.rstrip('/')}/auth/v1/signup", headers=headers, json=payload, timeout=20
    )
    if response.status_code in {400, 409, 422}:
        response = httpx.post(
            f"{url.rstrip('/')}/auth/v1/token?grant_type=password",
            headers=headers,
            json={"email": row["email"], "password": row["password"]},
            timeout=20,
        )
    if response.status_code >= 400:
        raise SeedError(f"Auth stopped with HTTP {response.status_code}")
    user = response.json().get("user") or {}
    try:
        return uuid.UUID(user["id"])
    except (KeyError, ValueError, TypeError) as exc:
        raise SeedError("Auth returned no valid user") from exc


def _login_user(url: str, key: str, row: dict) -> uuid.UUID:
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    response = httpx.post(
        f"{url.rstrip('/')}/auth/v1/token?grant_type=password",
        headers=headers,
        json={"email": row["email"], "password": row["password"]},
        timeout=20,
    )
    if response.status_code >= 400:
        raise SeedError(f"Auth verification stopped with HTTP {response.status_code}")
    try:
        return uuid.UUID(response.json()["user"]["id"])
    except (KeyError, ValueError, TypeError) as exc:
        raise SeedError("Auth verification returned no valid user") from exc


def _dish_profile(row: dict) -> PartnerDishCreate:
    sweet = row["name"] in {"Tiramisu", "Kunefe", "Chocolate Shake", "Bread Pudding"}
    ingredients = ["chicken", "rice", "herbs"] if not sweet else ["milk", "sugar", "flour"]
    return PartnerDishCreate(
        restaurant_id=row["restaurant_id"],
        name=row["name"],
        description=f"Development menu profile for {row['name']}.",
        cuisine=row["cuisine"],
        price=Decimal(450 + row["index"] * 125),
        availability=True,
        ingredients=ingredients,
        allergens=["dairy"] if sweet else [],
        dietary_tags=["vegetarian"] if sweet else [],
        preparation_style="stovetop" if row["cuisine"] != "Fast Food" else "griddle",
        image_path="/static/images/neutral-food-fallback.webp",
        spice_level=1 if sweet else 3,
        sweetness=5 if sweet else 1,
        sourness=1,
        saltiness=2,
        oiliness=2,
        richness=4 if sweet else 3,
        smokiness=1,
        texture_tags=["creamy"] if sweet else ["tender"],
    )


def _preflight(session: Session, restaurants: list[dict], dishes: list[dict]) -> None:
    version = session.scalar(text("SELECT version_num FROM alembic_version"))
    if version != "20260827_0006":
        raise SeedError("Database must be at migration 20260827_0006")
    expected_rids, expected_dids = {r["id"] for r in restaurants}, {d["id"] for d in dishes}
    existing_r = list(session.scalars(select(Restaurant).where(Restaurant.id.in_(expected_rids))))
    existing_d = list(session.scalars(select(Dish).where(Dish.id.in_(expected_dids))))
    if any(r.name != next(x["name"] for x in restaurants if x["id"] == r.id) for r in existing_r):
        raise SeedError("Conflicting batch restaurant found")
    if any(d.creation_key != f"{BATCH}:dish:{d.id.hex[:12]}" for d in existing_d):
        raise SeedError("Conflicting batch dish found")


def apply(
    session: Session,
    credentials: list[dict],
    auth_ids: list[uuid.UUID],
    restaurants: list[dict],
    dishes: list[dict],
) -> None:
    for index, row in enumerate(credentials):
        existing = session.scalar(
            select(User).where((User.id == auth_ids[index]) | (User.email == row["email"]))
        )
        if existing and (existing.id != auth_ids[index] or existing.role != "restaurant_partner"):
            raise SeedError("Conflicting application user found")
        if not existing:
            session.add(
                User(
                    id=auth_ids[index],
                    name=row["display_name"],
                    email=row["email"],
                    role="restaurant_partner",
                    show_review_display_name=True,
                )
            )
    session.flush()
    for row in restaurants:
        if session.get(Restaurant, row["id"]):
            continue
        session.add(
            Restaurant(
                id=row["id"],
                owner_id=auth_ids[row["owner_index"]],
                name=row["name"],
                description=f"Development demo restaurant. [batch:{BATCH}]",
                cuisine_types=[row["cuisine"]],
                address=row["address"],
                city=row["city"],
                latitude=Decimal(str(row["lat"])),
                longitude=Decimal(str(row["lng"])),
                location_verified=False,
                price_range="moderate",
                halal_status="unknown",
                halal_verification_status="pending",
                contact_phone=f"+92-300-555-{row['owner_index'] + 1000}",
                opening_information="Daily 12:00–23:00",
                available=True,
                image_path="/static/images/restaurant-warm-interior.webp",
            )
        )
    session.flush()
    provider = SentenceTransformerEmbeddingProvider(get_settings().embedding_model)
    for row in dishes:
        if session.get(Dish, row["id"]):
            continue
        profile = _dish_profile(row)
        profile_values = profile.model_dump(include=set(_EMBEDDING_TEXT_FIELDS))
        vector = provider.embed(build_dish_embedding_text(**profile_values))
        session.add(
            Dish(
                id=row["id"],
                **profile.model_dump(exclude={"restaurant_id"}),
                restaurant_id=row["restaurant_id"],
                embedding=vector,
                embedding_updated_at=datetime.now(UTC),
                creation_key=f"{BATCH}:dish:{row['id'].hex[:12]}",
            )
        )


def verify(
    session: Session, auth_ids: list[uuid.UUID], restaurants: list[dict], dishes: list[dict]
) -> None:
    rids, dids = {r["id"] for r in restaurants}, {d["id"] for d in dishes}
    if session.scalar(select(func.count()).select_from(User).where(User.id.in_(auth_ids))) != 10:
        raise SeedError("Partner verification failed")
    if (
        session.scalar(select(func.count()).select_from(Restaurant).where(Restaurant.id.in_(rids)))
        != 20
    ):
        raise SeedError("Restaurant verification failed")
    if session.scalar(select(func.count()).select_from(Dish).where(Dish.id.in_(dids))) != 200:
        raise SeedError("Dish verification failed")
    if any(
        len(list(d.embedding or [])) != 384
        for d in session.scalars(select(Dish).where(Dish.id.in_(dids)))
    ):
        raise SeedError("Vector verification failed")
    owner_counts = dict(
        session.execute(
            select(Restaurant.owner_id, func.count())
            .where(Restaurant.id.in_(rids))
            .group_by(Restaurant.owner_id)
        ).all()
    )
    if set(owner_counts) != set(auth_ids) or set(owner_counts.values()) != {2}:
        raise SeedError("Restaurant ownership verification failed")
    dish_counts = dict(
        session.execute(
            select(Dish.restaurant_id, func.count())
            .where(Dish.id.in_(dids))
            .group_by(Dish.restaurant_id)
        ).all()
    )
    if set(dish_counts) != rids or set(dish_counts.values()) != {10}:
        raise SeedError("Per-restaurant dish verification failed")
    emails = list(session.scalars(select(User.email).where(User.id.in_(auth_ids))))
    keys = list(session.scalars(select(Dish.creation_key).where(Dish.id.in_(dids))))
    if len(emails) != len(set(emails)) or len(keys) != len(set(keys)):
        raise SeedError("Batch email or creation key uniqueness failed")
    candidate_ids = {
        candidate.dish.id for candidate in RankingRepository(session).list_candidates()
    }
    if not dids <= candidate_ids:
        raise SeedError("Eligible batch dishes are missing from ranking candidates")


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    _load_root_env()
    restaurants, dishes = plan()
    with Session(get_engine()) as session:
        _preflight(session, restaurants, dishes)
    if args.dry_run:
        print("DRY RUN: 10 planned partner accounts; 20 planned restaurants; 200 planned dishes")
        return
    credentials = _credentials()
    url, key = os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    if not url or not key:
        raise SystemExit("Supabase public signup configuration is missing")
    if args.verify:
        auth_ids = [_login_user(url, key, row) for row in credentials]
        with Session(get_engine()) as session:
            _preflight(session, restaurants, dishes)
            verify(session, auth_ids, restaurants, dishes)
        print("VERIFIED: 10 partners, 20 restaurants, 200 dishes, and ranking eligibility")
        return
    auth_ids = []
    for row in credentials:
        auth_ids.append(_auth_user(url, key, row))
        time.sleep(1.25)
    try:
        with Session(get_engine()) as session, session.begin():
            _preflight(session, restaurants, dishes)
            apply(session, credentials, auth_ids, restaurants, dishes)
            session.flush()
            verify(session, auth_ids, restaurants, dishes)
    except SeedError as exc:
        raise SystemExit(str(exc)) from exc
    print("APPLIED: verified 10 partners, 20 restaurants, and 200 dishes")


if __name__ == "__main__":
    main()
