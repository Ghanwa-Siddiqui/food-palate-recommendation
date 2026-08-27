"""Guarded customer taste/review demo seed for the development project."""

from __future__ import annotations

import argparse
import csv
import importlib
import importlib.util
import math
import os
import secrets
import sys
import time
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.routes.reviews import _process, _recompute
from app.db.session import get_engine
from app.models.dish import Dish
from app.models.interaction import Interaction
from app.models.review import Review
from app.models.user import User
from app.schemas.interaction import InteractionCreate
from app.schemas.review import ReviewCreate
from app.services.data_core.embeddings import DeterministicFakeEmbeddingProvider
from app.services.data_core.review_processing import ProcessedReview
from app.services.ranking.scoring import calculate_cosine_similarity

if __package__:
    from scripts.seed_partner_marketplace_demo import plan as marketplace_plan
else:
    from seed_partner_marketplace_demo import plan as marketplace_plan

BATCH = "customer-taste-demo-v1"
ROOT = Path(__file__).resolve().parents[2]
CREDENTIALS = ROOT / ".dev-data" / "customer-demo-credentials.csv"
NAMESPACE = uuid.UUID("b8690f8c-bad9-4f88-bd39-1d22607218f1")

CLUSTERS = [
    (
        "Spicy Pakistani",
        ["Pakistani"],
        ["Chicken Biryani", "Chicken Karahi", "Beef Nihari", "Chicken Tikka", "Haleem"],
        [5, 1, 2, 3, 4, 5],
        ["tender", "crispy"],
    ),
    (
        "Smoky Turkish and BBQ",
        ["Turkish", "Pakistani"],
        ["Adana Kebab", "Chicken Shish", "Seekh Kebab", "Chicken Tikka", "Kofte"],
        [3, 1, 1, 3, 2, 4],
        ["tender", "chargrilled"],
    ),
    (
        "Chinese/Japanese umami",
        ["Chinese"],
        [
            "Chicken Chow Mein",
            "Egg Fried Rice",
            "Kung Pao Chicken",
            "Szechuan Chicken",
            "Mongolian Beef",
        ],
        [3, 1, 2, 5, 3, 3],
        ["chewy", "crunchy"],
    ),
    (
        "Italian/Fast Food",
        ["Italian", "Fast Food"],
        [
            "Margherita Pizza",
            "Chicken Alfredo",
            "Classic Beef Burger",
            "Pepperoni Pizza",
            "Lasagna",
        ],
        [2, 2, 1, 3, 2, 5],
        ["crispy", "cheesy"],
    ),
    (
        "Mild Continental and health-conscious",
        ["Continental"],
        [
            "Grilled Chicken",
            "Caesar Salad",
            "Cream of Mushroom Soup",
            "Herb Crusted Fish",
            "Roast Chicken",
        ],
        [1, 1, 2, 3, 1, 2],
        ["fresh", "tender"],
    ),
    (
        "Sweet, café and dessert",
        ["Italian", "Continental", "Fast Food", "Turkish"],
        ["Tiramisu", "Bread Pudding", "Chocolate Shake", "Kunefe", "Mushroom Risotto"],
        [0, 5, 1, 1, 2, 5],
        ["soft", "creamy"],
    ),
]
NAMES = [
    "Ayesha Malik",
    "Hassan Raza",
    "Maham Noor",
    "Aliya Khan",
    "Usman Tariq",
    "Zara Ahmed",
    "Ibrahim Shah",
    "Anaya Siddiqui",
    "Rayyan Qureshi",
    "Hiba Farooq",
    "Meher Fatima",
    "Saif Rehman",
    "Eman Iqbal",
    "Ahad Mir",
    "Laiba Aslam",
    "Rida Hussain",
    "Faris Baig",
    "Nawal Sheikh",
    "Zain Abbas",
    "Sana Javed",
    "Areej Mahmood",
    "Owais Akhtar",
    "Inaya Saleem",
    "Huzaifa Khan",
    "Minal Rauf",
    "Noor Bukhari",
    "Talha Amin",
    "Amna Saeed",
    "Rameez Haider",
    "Dua Khalid",
]
CITIES = ["Lahore", "Islamabad", "Rawalpindi", "Karachi"]


class SeedError(RuntimeError):
    pass


class SeedReviewProcessor:
    """Deterministic Review Intelligence adapter for controlled demo text."""

    def __init__(self) -> None:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from review_intelligence.src.extractor import (
            CANONICAL_TAGS,
            _normalise_tags,
            _oiliness_from_text,
            _rule_assisted_sentiment,
            _spice_from_text,
        )

        self.canonical_tags = CANONICAL_TAGS
        self.normalise_tags = _normalise_tags
        self.oiliness = _oiliness_from_text
        self.sentiment = _rule_assisted_sentiment
        self.spice = _spice_from_text
        self.embedder = DeterministicFakeEmbeddingProvider()

    def process(self, review_text: str, rating: int) -> ProcessedReview:
        rating_sentiment = {1: 0.1, 2: 0.3, 3: 0.5, 4: 0.75, 5: 0.9}[rating]
        return ProcessedReview(
            sentiment=self.sentiment(rating_sentiment, review_text, rating),
            spice=self.spice(review_text),
            oiliness=self.oiliness(review_text),
            tags=self.normalise_tags(list(self.canonical_tags), review_text),
            embedding=self.embedder.embed(review_text),
        )


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


def _personalization():
    package = "_chaska_customer_seed"
    if package not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            package,
            ROOT / "app" / "__init__.py",
            submodule_search_locations=[str(ROOT / "app")],
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[package] = module
        assert spec and spec.loader
        spec.loader.exec_module(module)
    models = importlib.import_module(f"{package}.models")
    personalization = importlib.import_module(f"{package}.personalization")
    return models.OnboardingAnswers, personalization.build_taste_vector


def _dish_lookup() -> dict[str, uuid.UUID]:
    _, dishes = marketplace_plan()
    result = {}
    for row in dishes:
        result.setdefault(row["name"], row["id"])
    return result


def plan() -> tuple[list[dict], list[dict]]:
    Answers, build_vector = _personalization()
    dish_ids = _dish_lookup()
    users, feedback = [], []
    for cluster_index, cluster in enumerate(CLUSTERS):
        label, cuisines, favourites, levels, textures = cluster
        for member in range(5):
            index = cluster_index * 5 + member
            preferred = cuisines + (
                ["Continental"] if member == 4 and "Continental" not in cuisines else []
            )
            answers = Answers(
                city=CITIES[index % len(CITIES)],
                preferred_cuisines=preferred,
                favourite_dishes=favourites[:3] + [favourites[(member + 3) % 5]],
                spice_preference=max(0, min(5, levels[0] + (member % 3 - 1))),
                sweetness_preference=levels[1],
                sourness_preference=levels[2],
                saltiness_preference=levels[3],
                oiliness_preference=levels[4],
                richness_preference=max(0, min(5, levels[5] + (member % 2))),
                preferred_textures=textures + (["juicy"] if member == 4 else []),
                budget_min=300 + 50 * (member % 2),
                budget_max=1200 + 250 * member,
                dietary_requirements=["balanced"] if cluster_index == 4 else [],
                allergies=["peanuts"] if cluster_index == 4 and member == 4 else [],
                disliked_ingredients=["excess oil"] if cluster_index in {4, 5} else [],
                require_halal=member in {0, 3},
            )
            vector = build_vector(answers)
            if len(vector) != 384:
                raise SeedError("Authoritative taste vector dimension is not 384")
            users.append(
                {
                    "index": index,
                    "name": NAMES[index],
                    "email": f"customer.taste.demo.{index + 1:02d}@chaska.dev",
                    "cluster": label,
                    "public": index < 20,
                    "answers": answers,
                    "vector": vector,
                }
            )
            selected = [
                favourites[0],
                favourites[1],
                favourites[2 + member % 3],
                favourites[4 - member % 2],
            ]
            selected = list(dict.fromkeys(selected))
            for candidate in favourites:
                if len(selected) == 4:
                    break
                if candidate not in selected:
                    selected.append(candidate)
            for slot, dish_name in enumerate(selected):
                global_index = index * 4 + slot
                if slot < 2 or global_index % 20 == 10:
                    rating = 5 if (index + slot) % 2 == 0 else 4
                elif global_index % 4 == 3 and index % 5 != 4:
                    rating = 2 if index % 2 else 1
                else:
                    rating = 3
                feedback.append(
                    {
                        "user_index": index,
                        "dish_id": dish_ids[dish_name],
                        "dish_name": dish_name,
                        "rating": rating,
                        "text": _review_text(dish_name, rating, index),
                    }
                )
    return users, feedback


def _review_text(dish: str, rating: int, index: int) -> str:
    if rating >= 4:
        endings = [
            "The flavour was aromatic and the texture was tender.",
            "It was fresh, flavorful and worth ordering again.",
            "The seasoning felt balanced and delicious.",
        ]
    elif rating == 3:
        endings = [
            "Good flavour, but it was oilier than I prefer.",
            "The portion was fair, although the seasoning felt mild.",
            "It was enjoyable but slightly rich for my taste.",
        ]
    else:
        endings = [
            "It was too oily and the flavour felt disappointing.",
            "The texture was dry and I did not enjoy the seasoning.",
            "It tasted bland and the value did not feel right.",
        ]
    return f"I tried the {dish}. {endings[index % len(endings)]}"


def _credentials(users: list[dict]) -> list[dict]:
    if CREDENTIALS.exists():
        with CREDENTIALS.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != 30:
            raise SeedError("Conflicting customer credentials file")
        return rows
    CREDENTIALS.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "display_name": u["name"],
            "email": u["email"],
            "password": secrets.token_urlsafe(24) + "!9aA",
            "taste_cluster": u["cluster"],
            "city": u["answers"].city,
            "public_name_opt_in": str(u["public"]).lower(),
        }
        for u in users
    ]
    with CREDENTIALS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return rows


def _auth_user(url: str, key: str, row: dict) -> uuid.UUID:
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    try:
        response = httpx.post(
            f"{url.rstrip('/')}/auth/v1/signup",
            headers=headers,
            json={
                "email": row["email"],
                "password": row["password"],
                "data": {"name": row["display_name"], "role": "customer"},
            },
            timeout=45,
        )
        if response.status_code in {400, 409, 422}:
            response = httpx.post(
                f"{url.rstrip('/')}/auth/v1/token?grant_type=password",
                headers=headers,
                json={"email": row["email"], "password": row["password"]},
                timeout=45,
            )
    except httpx.HTTPError as exc:
        raise SeedError(f"Auth stopped on {exc.__class__.__name__}; rerun to resume") from exc
    if response.status_code >= 400:
        raise SeedError(f"Auth stopped with HTTP {response.status_code}")
    try:
        return uuid.UUID(response.json()["user"]["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SeedError("Auth returned no valid user") from exc


def _preflight(session: Session, users: list[dict], feedback: list[dict]) -> None:
    if session.scalar(text("SELECT version_num FROM alembic_version")) != "20260827_0006":
        raise SeedError("Database must be at migration 20260827_0006")
    marketplace_ids = {row["id"] for row in marketplace_plan()[1]}
    if (
        session.scalar(select(func.count()).select_from(Dish).where(Dish.id.in_(marketplace_ids)))
        != 200
    ):
        raise SeedError("The verified 200-dish marketplace batch is required")
    emails = [row["email"] for row in users]
    existing = list(session.scalars(select(User).where(User.email.in_(emails))))
    if any(row.role != "customer" for row in existing):
        raise SeedError("Conflicting customer batch user")
    keys = {f"{BATCH}:review:{row['user_index']:02d}:{row['dish_id'].hex[:12]}" for row in feedback}
    if any(
        row.user_id not in {u.id for u in existing}
        for row in session.scalars(select(Review).where(Review.submission_key.in_(keys)))
    ):
        raise SeedError("Conflicting customer batch review")


def apply(
    session: Session,
    users: list[dict],
    feedback: list[dict],
    credentials: list[dict],
    auth_ids: list[uuid.UUID],
) -> None:
    now = datetime.now(UTC)
    existing_users = {
        user.email: user
        for user in session.scalars(
            select(User).where(User.email.in_([row["email"] for row in users]))
        )
    }
    for row, credential, auth_id in zip(users, credentials, auth_ids, strict=True):
        user = existing_users.get(credential["email"])
        if user and (user.id != auth_id or user.role != "customer"):
            raise SeedError("Conflicting application customer")
        values = row["answers"].model_dump()
        if user is None:
            user = User(id=auth_id, name=row["name"], email=row["email"], role="customer")
            session.add(user)
        for key, value in values.items():
            setattr(user, key, value)
        user.onboarding_complete = True
        user.show_review_display_name = row["public"]
        user.taste_vector = row["vector"]
        user.taste_updated_at = now
    session.flush()
    processor = SeedReviewProcessor()
    touched = set()
    existing_interactions = {
        item.client_event_id: item
        for item in session.scalars(
            select(Interaction).where(Interaction.client_event_id.like(f"{BATCH}:%"))
        )
    }
    review_keys = {
        f"{BATCH}:review:{row['user_index']:02d}:{row['dish_id'].hex[:12]}" for row in feedback
    }
    existing_reviews = {
        item.submission_key: item
        for item in session.scalars(select(Review).where(Review.submission_key.in_(review_keys)))
    }
    for row in feedback:
        user_id = auth_ids[row["user_index"]]
        dish_id = row["dish_id"]
        tried_key = f"{BATCH}:tried:{row['user_index']:02d}:{dish_id.hex[:12]}"
        payload = InteractionCreate(dish_id=dish_id, action="tried", client_event_id=tried_key)
        if tried_key not in existing_interactions:
            item = Interaction(user_id=user_id, **payload.model_dump())
            session.add(item)
            existing_interactions[tried_key] = item
        action = "like" if row["rating"] >= 4 else "dislike" if row["rating"] <= 2 else None
        if action:
            action_key = f"{BATCH}:{action}:{row['user_index']:02d}:{dish_id.hex[:12]}"
            if action_key not in existing_interactions:
                item = Interaction(
                    user_id=user_id,
                    dish_id=dish_id,
                    action=action,
                    client_event_id=action_key,
                )
                session.add(item)
                existing_interactions[action_key] = item
        if row["rating"] >= 4 and row["user_index"] % 2 == 0:
            save_key = f"{BATCH}:save:{row['user_index']:02d}:{dish_id.hex[:12]}"
            if save_key not in existing_interactions:
                item = Interaction(
                    user_id=user_id,
                    dish_id=dish_id,
                    action="save",
                    client_event_id=save_key,
                )
                session.add(item)
                existing_interactions[save_key] = item
        review_key = f"{BATCH}:review:{row['user_index']:02d}:{dish_id.hex[:12]}"
        validated = ReviewCreate(
            dish_id=dish_id,
            rating=row["rating"],
            text=row["text"],
            tried_confirmation=True,
            show_display_name=users[row["user_index"]]["public"],
            submission_key=review_key,
        )
        review = existing_reviews.get(review_key)
        if review is None:
            review = Review(
                user_id=user_id,
                dish_id=dish_id,
                rating=validated.rating,
                text=validated.text,
                submission_key=review_key,
            )
            session.add(review)
            _process(review, processor)
            existing_reviews[review_key] = review
        elif review.user_id != user_id or review.dish_id != dish_id:
            raise SeedError("Conflicting review idempotency key")
        touched.add(dish_id)
    session.flush()
    dishes = {dish.id: dish for dish in session.scalars(select(Dish).where(Dish.id.in_(touched)))}
    reviews_by_dish = defaultdict(list)
    for review in session.scalars(
        select(Review).where(Review.dish_id.in_(touched), Review.archived_at.is_(None))
    ):
        reviews_by_dish[review.dish_id].append(review)
    for dish_id in touched:
        _recompute(dishes[dish_id], reviews_by_dish[dish_id])


def verify(
    session: Session, users: list[dict], feedback: list[dict], auth_ids: list[uuid.UUID]
) -> None:
    batch_users = list(session.scalars(select(User).where(User.id.in_(auth_ids))))
    if len(batch_users) != 30 or Counter(u.role for u in batch_users) != {"customer": 30}:
        raise SeedError("Customer count verification failed")
    if any(
        not u.onboarding_complete or len(list(u.taste_vector or [])) != 384 for u in batch_users
    ):
        raise SeedError("Profile/vector verification failed")
    review_keys = [
        f"{BATCH}:review:{r['user_index']:02d}:{r['dish_id'].hex[:12]}" for r in feedback
    ]
    reviews = list(session.scalars(select(Review).where(Review.submission_key.in_(review_keys))))
    tried = list(
        session.scalars(
            select(Interaction).where(Interaction.client_event_id.like(f"{BATCH}:tried:%"))
        )
    )
    if (
        len(reviews) != 120
        or len(tried) != 120
        or any(r.processing_status != "complete" for r in reviews)
        or any(len(list(r.review_embedding or [])) != 384 for r in reviews)
    ):
        raise SeedError("Review/interaction processing verification failed")
    counts = Counter(r.user_id for r in reviews)
    if set(counts.values()) != {4} or len({(r.user_id, r.dish_id) for r in reviews}) != 120:
        raise SeedError("Per-customer or duplicate review verification failed")
    if Counter(u.show_review_display_name for u in batch_users) != {True: 20, False: 10}:
        raise SeedError("Reviewer privacy verification failed")
    if not ({1, 2} & {r.rating for r in reviews}) or not ({4, 5} & {r.rating for r in reviews}):
        raise SeedError("Rating distribution verification failed")
    user_by_index = dict(enumerate(auth_ids))
    by_cluster = defaultdict(list)
    for row in users:
        by_cluster[row["cluster"]].append(user_by_index[row["index"]])
    for members in by_cluster.values():
        positive = Counter(r.dish_id for r in reviews if r.user_id in members and r.rating >= 4)
        if sum(count >= 2 for count in positive.values()) < 2:
            raise SeedError("Cluster shared-positive verification failed")
        member_users = [
            next(user for user in batch_users if user.id == member) for member in members
        ]
        if (
            min(
                calculate_cosine_similarity(
                    list(member_users[0].taste_vector), list(other.taste_vector)
                )
                for other in member_users[1:]
            )
            < 0.65
        ):
            raise SeedError("Cluster taste-similarity verification failed")
        positives_by_user = {
            member: {r.dish_id for r in reviews if r.user_id == member and r.rating >= 4}
            for member in members
        }
        if not any(
            positives_by_user[source] - positives_by_user[target]
            for source in members
            for target in members
            if source != target
        ):
            raise SeedError("Cluster collaborative-candidate verification failed")
    touched = {r.dish_id for r in reviews}
    all_active = list(
        session.scalars(
            select(Review).where(Review.dish_id.in_(touched), Review.archived_at.is_(None))
        )
    )
    active_by_dish = defaultdict(list)
    for review in all_active:
        active_by_dish[review.dish_id].append(review)
    for dish in session.scalars(select(Dish).where(Dish.id.in_(touched))):
        active = active_by_dish[dish.id]
        expected_average = sum(review.rating for review in active) / len(active)
        if (
            dish.review_aggregated_at is None
            or dish.review_count != len(active)
            or not math.isclose(float(dish.review_average), expected_average, abs_tol=0.01)
        ):
            raise SeedError("Dish aggregate verification failed")


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    _load_root_env()
    users, feedback = plan()
    if len(users) != 30 or len(feedback) != 120:
        raise SystemExit("Plan count invariant failed")
    with Session(get_engine()) as session:
        _preflight(session, users, feedback)
    if args.dry_run:
        print("DRY RUN: 30 planned customer accounts/profiles; 120 planned reviews")
        return
    credentials = _credentials(users)
    if args.verify:
        with Session(get_engine()) as session:
            _preflight(session, users, feedback)
            by_email = {
                user.email: user.id
                for user in session.scalars(
                    select(User).where(User.email.in_([row["email"] for row in credentials]))
                )
            }
            if len(by_email) != 30:
                raise SystemExit("Customer application mapping verification failed")
            auth_ids = [by_email[row["email"]] for row in credentials]
            verify(session, users, feedback, auth_ids)
        print(
            "VERIFIED: customer demo batch counts, profiles, reviews, "
            "aggregates and collaborative evidence"
        )
        return
    url, key = os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    if not url or not key:
        raise SystemExit("Supabase public signup configuration is missing")
    auth_ids = []
    try:
        for row in credentials:
            auth_ids.append(_auth_user(url, key, row))
            time.sleep(1.5)
    except SeedError as exc:
        raise SystemExit(str(exc)) from None
    try:
        with Session(get_engine()) as session, session.begin():
            _preflight(session, users, feedback)
            apply(session, users, feedback, credentials, auth_ids)
            session.flush()
            verify(session, users, feedback, auth_ids)
    except SeedError as exc:
        raise SystemExit(str(exc)) from exc
    except Exception as exc:
        name = exc.__class__.__name__
        raise SystemExit(f"Seed transaction stopped on {name}; rerun to resume") from exc
    print("APPLIED: verified 30 customers, 120 tried interactions and 120 processed reviews")


if __name__ == "__main__":
    main()
