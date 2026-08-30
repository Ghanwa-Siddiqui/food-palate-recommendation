"""Break up coincidental byte-identical taste vectors among seeded cluster
members, in development data.

Both customer-taste-demo seed batches derive each member's taste levels and
favourite-dish subset from small modulo cycles on their position within a
6-cluster, ~28-member archetype (e.g. `spice_preference = base + (member %
3 - 1)`), while sweetness/sourness/saltiness/oiliness never vary at all
within a cluster. With short cycles and several always-constant dimensions,
many members land on the exact same combination by coincidence - confirmed
live: 113 of 209 onboarded users (54%) shared a byte-identical taste_vector
with at least one other user, in groups as large as 5. Two users with an
identical vector aren't "very similar" taste twins, they're numerically
indistinguishable - a 100% match that has nothing to do with the real
embedding model working correctly (it is; identical input always produces
identical output).

This re-derives each matched user's taste levels and favourite-dish subset
from a hash of their own email - stable, unique per person, and independent
across users - instead of their position in a cycle: each of the six taste
dimensions gets an independent +/-2 jitter off the cluster's baseline, and
two of the cluster's five favourite dishes get dropped (a different pair
per user, ten possible 3-of-5 combinations), so the combined space makes a
coincidental full collision unlikely even across ~30 members of one
archetype, and produces visibly varied - not just non-identical - similarity
scores. An earlier, narrower version of this (+/-1 jitter, one dish
dropped) only spread members to 91-99.9% similarity; this wider version was
chosen after confirming empirically it stays well clear of the 0.65
collaborative-filtering floor. Cuisine and the cluster's own two core
textures are left alone, so members of a cluster stay genuinely similar to
each other - just not identical twins of each other.

Naturally idempotent: the hash is keyed on the user's own (stable) email
and the cluster's fixed baseline, not on the user's current (possibly
already-jittered) field values, so re-running recomputes the same result.
"""

from __future__ import annotations

import argparse
import hashlib
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_engine
from app.models.user import User
from scripts.seed import SeedSafetyError, extract_supabase_project_ref, verify_seed_preconditions
from scripts.seed_customer_taste_demo import CLUSTERS, _personalization

CORRECTION_CONFIRMATION = "DIVERSIFY_CHASKA_SEEDED_TASTE_VECTORS"

_DIM_FIELDS = (
    "spice_preference",
    "sweetness_preference",
    "sourness_preference",
    "saltiness_preference",
    "oiliness_preference",
    "richness_preference",
)

_BONUS_TEXTURES = (
    "juicy",
    "chargrilled",
    "fresh",
    "crunchy",
    "crispy",
    "tender",
    "soft",
    "creamy",
    "chewy",
    "cheesy",
)


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


def _cluster_for(user: User):
    dishes = set(user.favourite_dishes or [])
    if not dishes:
        return None
    for cluster in CLUSTERS:
        _, _, favourites, _, _ = cluster
        if dishes <= set(favourites):
            return cluster
    return None


def _digest_byte(email: str, salt: str) -> int:
    return hashlib.sha256(f"{email}:{salt}".encode()).digest()[0]


def _jitter(email: str, salt: str, base: int, spread: int = 1) -> int:
    offset = (_digest_byte(email, salt) % (2 * spread + 1)) - spread
    return max(0, min(5, base + offset))


def _pick_index(email: str, salt: str, n: int) -> int:
    return _digest_byte(email, salt) % n


def diversify_seeded_taste_vectors(session: Session, *, answers_and_builder=None) -> int:
    answers_cls, build_taste_vector = answers_and_builder or _personalization()
    users = list(session.scalars(select(User).where(User.onboarding_complete.is_(True))))
    matched = [(user, _cluster_for(user)) for user in users]
    matched = [(user, cluster) for user, cluster in matched if cluster is not None]
    if not matched:
        raise SeedSafetyError("no seeded cluster members found to diversify")

    now = datetime.now(UTC)
    for user, cluster in matched:
        _label, _cuisines, favourites, levels, textures = cluster

        for index, field in enumerate(_DIM_FIELDS):
            setattr(user, field, _jitter(user.email, field, levels[index], spread=2))

        # Drop two of the cluster's five favourites (not just one): with a
        # spread=1 jitter and a single dropped dish, cluster members still
        # landed at 91-99.9% similarity to each other - real, not identical,
        # but still narrow enough to look suspicious. Ten possible 3-of-5
        # combinations plus a wider taste-dimension spread gives noticeably
        # more visible person-to-person variety while staying well clear of
        # the 0.65 collaborative-filtering floor (verified empirically).
        remaining = list(range(len(favourites)))
        first_drop = _pick_index(user.email, "drop-dish-1", len(remaining))
        remaining.pop(first_drop)
        second_drop = _pick_index(user.email, "drop-dish-2", len(remaining))
        remaining.pop(second_drop)
        user.favourite_dishes = [favourites[i] for i in remaining]

        bonus_pool = [t for t in _BONUS_TEXTURES if t not in textures]
        bonus_index = _pick_index(user.email, "bonus-texture", len(bonus_pool) + 1)
        user.preferred_textures = list(textures) + (
            [bonus_pool[bonus_index]] if bonus_index < len(bonus_pool) else []
        )

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
    return len(matched)


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
            count = diversify_seeded_taste_vectors(session)
    except SeedSafetyError as error:
        raise SystemExit(str(error)) from error

    print(f"Diversified {count} seeded users' taste levels, dishes, and vectors")


if __name__ == "__main__":
    main()
