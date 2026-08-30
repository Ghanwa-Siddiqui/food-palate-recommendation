"""Additive "wave 2" customer taste/review demo seed.

Adds more users to the *same* 6 taste-archetype clusters defined in
seed_customer_taste_demo.py, without touching that script, its data, or its
test — this repo's dev database already has that 30-user batch applied (from
another machine; its credentials file isn't present locally), so this script
is deliberately additive rather than a rewrite. Reuses the original's cluster
archetypes and helpers directly so the two batches stay in sync and produce
taste vectors that are genuinely cosine-similar to each other, not just
internally.

Same CLI as the original: --dry-run / --apply / --verify.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import secrets
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
from app.services.ranking.scoring import calculate_cosine_similarity

if __package__:
    from scripts.seed_customer_taste_demo import (
        CITIES,
        CLUSTERS,
        SeedReviewProcessor,
        _dish_lookup,
        _load_root_env,
        _personalization,
    )
    from scripts.seed_partner_marketplace_demo import plan as marketplace_plan
else:
    from seed_customer_taste_demo import (
        CITIES,
        CLUSTERS,
        SeedReviewProcessor,
        _dish_lookup,
        _load_root_env,
        _personalization,
    )
    from seed_partner_marketplace_demo import plan as marketplace_plan

BATCH = "customer-taste-demo-wave2-v1"
ROOT = Path(__file__).resolve().parents[2]
CREDENTIALS = ROOT / ".dev-data" / "customer-demo-wave2-credentials.csv"
# Same namespace as wave 1 - fine, since BATCH differs the hashed ids stay disjoint.
NAMESPACE = uuid.UUID("b8690f8c-bad9-4f88-bd39-1d22607218f1")

MEMBERS_PER_CLUSTER = 28


class SeedError(RuntimeError):
    pass


FIRST_NAMES = [
    "Bilal", "Sadia", "Kamran", "Nimra", "Faizan", "Sara", "Danish", "Mahnoor",
    "Adeel", "Kiran", "Waqas", "Sidra", "Junaid", "Alishba", "Shahzad", "Komal",
    "Naveed", "Sundas", "Asad", "Mehak", "Fahad", "Warda", "Umer", "Zoya",
    "Salman", "Iqra", "Bilawal", "Fizza",
]
LAST_NAMES = [
    "Chaudhry", "Butt", "Cheema", "Gill", "Warraich", "Dar", "Baig", "Ansari",
    "Qadri", "Chishti", "Awan", "Bhatti", "Niazi", "Soomro",
]


def _generate_names(count: int) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for last in LAST_NAMES:
        for first in FIRST_NAMES:
            full = f"{first} {last}"
            if full in seen:
                continue
            seen.add(full)
            names.append(full)
            if len(names) == count:
                return names
    raise SeedError(f"Name pool exhausted before reaching {count} unique names")


NAMES = _generate_names(MEMBERS_PER_CLUSTER * len(CLUSTERS))

# Larger phrase pool than wave 1's 3-endings-per-tier: at ~670 reviews here,
# 3 endings would repeat ~220 times each and read as obviously templated.
_OPENINGS = [
    "I tried the {dish}.",
    "Ordered the {dish} last night.",
    "Finally got to taste the {dish}.",
    "Picked up the {dish} for dinner.",
    "Gave the {dish} a shot this week.",
]
_ENDINGS = {
    "positive": [
        "The flavour was aromatic and the texture was tender.",
        "It was fresh, flavorful and worth ordering again.",
        "The seasoning felt balanced and delicious.",
        "Every bite was satisfying and well spiced.",
        "It arrived hot and tasted exactly as described.",
        "The portion was generous and the taste was spot on.",
        "Genuinely one of the better versions I have had.",
        "Well balanced, nothing to complain about.",
        "Rich flavour without feeling heavy.",
        "Consistent quality, would happily order again.",
    ],
    "neutral": [
        "Good flavour, but it was oilier than I prefer.",
        "The portion was fair, although the seasoning felt mild.",
        "It was enjoyable but slightly rich for my taste.",
        "Decent overall, though it could use a bit more spice.",
        "Solid choice, nothing stood out either way.",
        "Fine for the price, but not memorable.",
        "Average experience, might try something else next time.",
        "Reasonable taste, service was a bit slow though.",
        "It was okay, texture was a little inconsistent.",
        "Middle of the road - not bad, not great.",
    ],
    "negative": [
        "It was too oily and the flavour felt disappointing.",
        "The texture was dry and I did not enjoy the seasoning.",
        "It tasted bland and the value did not feel right.",
        "Overcooked and underseasoned, would not order again.",
        "The portion was small for the price.",
        "Arrived lukewarm and the taste suffered for it.",
        "Too salty and the texture was off.",
        "Not what I expected, flavour felt one-note.",
        "Disappointing compared to other places I have tried.",
        "The seasoning was uneven throughout the dish.",
    ],
}


def _review_text(dish: str, rating: int, index: int, slot: int) -> str:
    tier = "positive" if rating >= 4 else "neutral" if rating == 3 else "negative"
    opening = _OPENINGS[(index + slot) % len(_OPENINGS)]
    ending = _ENDINGS[tier][(index * 3 + slot * 7) % len(_ENDINGS[tier])]
    return f"{opening.format(dish=dish)} {ending}"


def plan() -> tuple[list[dict], list[dict]]:
    Answers, build_vector = _personalization()
    dish_ids = _dish_lookup()
    users, feedback = [], []
    for cluster_index, cluster in enumerate(CLUSTERS):
        label, cuisines, favourites, levels, textures = cluster
        for member in range(MEMBERS_PER_CLUSTER):
            index = cluster_index * MEMBERS_PER_CLUSTER + member
            preferred = cuisines + (
                ["Continental"] if member % 7 == 4 and "Continental" not in cuisines else []
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
                preferred_textures=textures + (["juicy"] if member % 7 == 4 else []),
                budget_min=300 + 50 * (member % 2),
                budget_max=1200 + 250 * (member % 5),
                dietary_requirements=["balanced"] if cluster_index == 4 else [],
                allergies=["peanuts"] if cluster_index == 4 and member % 7 == 4 else [],
                disliked_ingredients=["excess oil"] if cluster_index in {4, 5} else [],
                require_halal=member % 4 in {0, 3},
            )
            vector = build_vector(answers)
            if len(vector) != 384:
                raise SeedError("Authoritative taste vector dimension is not 384")
            users.append(
                {
                    "index": index,
                    "name": NAMES[index],
                    "email": f"customer.taste.demo.wave2.{index + 1:03d}@chaska.dev",
                    "cluster": label,
                    # ~2/3 public, matching wave 1's 20-of-30 ratio.
                    "public": member % 3 != 0,
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
                        "text": _review_text(dish_name, rating, index, slot),
                    }
                )
    return users, feedback


def _credentials(users: list[dict]) -> list[dict]:
    if CREDENTIALS.exists():
        with CREDENTIALS.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != len(users):
            raise SeedError("Conflicting wave-2 customer credentials file")
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


# Total budget if every attempt for one user is 429'd: sum(_BACKOFFS) seconds
# of waiting before giving up on that single user. Bounded so a stuck run
# fails loudly within a few minutes rather than hanging silently for hours.
_BACKOFFS = [5, 15, 30, 60, 120]


def _signup_or_login(url: str, key: str, row: dict) -> httpx.Response:
    """Try login before signup.

    Supabase's signup endpoint carries a much tighter burst rate limit than
    its password-login endpoint (observed directly: repeated 429s from
    /auth/v1/signup for accounts that already exist, while /auth/v1/token
    for the same accounts goes through cleanly). Since this script is
    idempotent and re-run to resume, most calls are for a user this batch
    already created in a prior run - trying login first means those calls
    never touch the endpoint that's actually rate-limited. A brand new user
    still gets created correctly: login fails (no such account), and the
    code falls through to signup exactly as before.
    """
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    response = httpx.post(
        f"{url.rstrip('/')}/auth/v1/token?grant_type=password",
        headers=headers,
        json={"email": row["email"], "password": row["password"]},
        timeout=45,
    )
    if response.status_code >= 400 and response.status_code != 429:
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
    return response


def _auth_user(url: str, key: str, row: dict, *, on_retry=None) -> uuid.UUID:
    response = None
    for wait in [0, *_BACKOFFS]:
        if wait:
            if on_retry:
                on_retry(row["email"], wait)
            time.sleep(wait)
        try:
            response = _signup_or_login(url, key, row)
        except httpx.HTTPError as exc:
            raise SeedError(f"Auth stopped on {exc.__class__.__name__}; rerun to resume") from exc
        if response.status_code != 429:
            break
    if response is None or response.status_code == 429:
        raise SeedError(
            f"Auth rate-limited repeatedly for {row['email']}; rerun to resume later"
        )
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
        raise SeedError("Conflicting wave-2 customer batch user")
    keys = {f"{BATCH}:review:{row['user_index']:03d}:{row['dish_id'].hex[:12]}" for row in feedback}
    if any(
        row.user_id not in {u.id for u in existing}
        for row in session.scalars(select(Review).where(Review.submission_key.in_(keys)))
    ):
        raise SeedError("Conflicting wave-2 customer batch review")


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
            raise SeedError("Conflicting wave-2 application customer")
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
    existing_interactions = {
        item.client_event_id: item
        for item in session.scalars(
            select(Interaction).where(Interaction.client_event_id.like(f"{BATCH}:%"))
        )
    }
    review_keys = {
        f"{BATCH}:review:{row['user_index']:03d}:{row['dish_id'].hex[:12]}" for row in feedback
    }
    existing_reviews = {
        item.submission_key: item
        for item in session.scalars(select(Review).where(Review.submission_key.in_(review_keys)))
    }
    touched = set()
    for row in feedback:
        user_id = auth_ids[row["user_index"]]
        dish_id = row["dish_id"]
        tried_key = f"{BATCH}:tried:{row['user_index']:03d}:{dish_id.hex[:12]}"
        payload = InteractionCreate(dish_id=dish_id, action="tried", client_event_id=tried_key)
        if tried_key not in existing_interactions:
            item = Interaction(user_id=user_id, **payload.model_dump())
            session.add(item)
            existing_interactions[tried_key] = item
        action = "like" if row["rating"] >= 4 else "dislike" if row["rating"] <= 2 else None
        if action:
            action_key = f"{BATCH}:{action}:{row['user_index']:03d}:{dish_id.hex[:12]}"
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
            save_key = f"{BATCH}:save:{row['user_index']:03d}:{dish_id.hex[:12]}"
            if save_key not in existing_interactions:
                item = Interaction(
                    user_id=user_id,
                    dish_id=dish_id,
                    action="save",
                    client_event_id=save_key,
                )
                session.add(item)
                existing_interactions[save_key] = item
        review_key = f"{BATCH}:review:{row['user_index']:03d}:{dish_id.hex[:12]}"
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
            raise SeedError("Conflicting wave-2 review idempotency key")
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
    expected_public = sum(1 for u in users if u["public"])
    expected_private = len(users) - expected_public
    batch_users = list(session.scalars(select(User).where(User.id.in_(auth_ids))))
    if len(batch_users) != len(users) or Counter(u.role for u in batch_users) != {
        "customer": len(users)
    }:
        raise SeedError("Wave-2 customer count verification failed")
    if any(
        not u.onboarding_complete or len(list(u.taste_vector or [])) != 384 for u in batch_users
    ):
        raise SeedError("Wave-2 profile/vector verification failed")
    review_keys = [
        f"{BATCH}:review:{r['user_index']:03d}:{r['dish_id'].hex[:12]}" for r in feedback
    ]
    reviews = list(session.scalars(select(Review).where(Review.submission_key.in_(review_keys))))
    tried = list(
        session.scalars(
            select(Interaction).where(Interaction.client_event_id.like(f"{BATCH}:tried:%"))
        )
    )
    if (
        len(reviews) != len(feedback)
        or len(tried) != len(feedback)
        or any(r.processing_status != "complete" for r in reviews)
        or any(len(list(r.review_embedding or [])) != 384 for r in reviews)
    ):
        raise SeedError("Wave-2 review/interaction processing verification failed")
    counts = Counter(r.user_id for r in reviews)
    if set(counts.values()) != {4} or len({(r.user_id, r.dish_id) for r in reviews}) != len(
        feedback
    ):
        raise SeedError("Wave-2 per-customer or duplicate review verification failed")
    if Counter(u.show_review_display_name for u in batch_users) != {
        True: expected_public,
        False: expected_private,
    }:
        raise SeedError("Wave-2 reviewer privacy verification failed")
    if not ({1, 2} & {r.rating for r in reviews}) or not ({4, 5} & {r.rating for r in reviews}):
        raise SeedError("Wave-2 rating distribution verification failed")
    user_by_index = dict(enumerate(auth_ids))
    by_cluster = defaultdict(list)
    for row in users:
        by_cluster[row["cluster"]].append(user_by_index[row["index"]])
    for members in by_cluster.values():
        positive = Counter(r.dish_id for r in reviews if r.user_id in members and r.rating >= 4)
        if sum(count >= 2 for count in positive.values()) < 2:
            raise SeedError("Wave-2 cluster shared-positive verification failed")
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
            raise SeedError("Wave-2 cluster taste-similarity verification failed")
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
            raise SeedError("Wave-2 cluster collaborative-candidate verification failed")
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
            raise SeedError("Wave-2 dish aggregate verification failed")


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    _load_root_env()
    users, feedback = plan()
    if len(feedback) != len(users) * 4:
        raise SystemExit("Wave-2 plan count invariant failed")
    with Session(get_engine()) as session:
        _preflight(session, users, feedback)
    if args.dry_run:
        print(
            f"DRY RUN: {len(users)} planned wave-2 customer accounts/profiles; "
            f"{len(feedback)} planned reviews"
        )
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
            if len(by_email) != len(users):
                raise SystemExit("Wave-2 customer application mapping verification failed")
            auth_ids = [by_email[row["email"]] for row in credentials]
            verify(session, users, feedback, auth_ids)
        print(
            "VERIFIED: wave-2 customer demo batch counts, profiles, reviews, "
            "aggregates and collaborative evidence"
        )
        return
    url, key = os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    if not url or not key:
        raise SystemExit("Supabase public signup configuration is missing")
    with Session(get_engine()) as session:
        existing_by_email = {
            user.email: user.id
            for user in session.scalars(
                select(User).where(User.email.in_([row["email"] for row in credentials]))
            )
        }
    def on_retry(email: str, wait: float) -> None:
        print(f"  rate-limited on {email}, backing off {wait:.0f}s...", flush=True)

    auth_ids = []
    try:
        for i, row in enumerate(credentials):
            if row["email"] in existing_by_email:
                auth_ids.append(existing_by_email[row["email"]])
                continue
            auth_ids.append(_auth_user(url, key, row, on_retry=on_retry))
            print(f"  signed up {i + 1}/{len(credentials)}: {row['email']}", flush=True)
            # 3s, not the original script's 1.5s: the first wave-2 attempt at
            # 1.5s hit Supabase's Auth rate limit (HTTP 429) with zero users
            # applied. A slower pace trades a longer run for not tripping it
            # again.
            time.sleep(3.0)
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
        raise SystemExit(f"Wave-2 seed transaction stopped on {name}; rerun to resume") from exc
    print(
        f"APPLIED: verified {len(users)} wave-2 customers, {len(feedback)} tried "
        f"interactions and {len(feedback)} processed reviews"
    )


if __name__ == "__main__":
    main()
