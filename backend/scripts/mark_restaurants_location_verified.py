"""Mark verified GPS coordinates on restaurants that already have real
latitude/longitude on file, in development data.

seed_partner_marketplace_demo.py deliberately creates these 20 restaurants
with location_verified=False even though it assigns them real coordinates -
location_verified represents a separate confirmation step (see
restaurant.html: "Verified map coordinates available" vs "not verified")
that nothing in this codebase currently performs. Without it, the app's
context/location-based feed filter (user_lat/user_lng/max_distance_km,
already fully implemented in generator.py/scoring.py) has zero restaurants
it is allowed to measure distance against, so it silently has no visible
effect even when a user supplies their location.

This is a one-off development-data correction, not a schema change: the
coordinates were already deliberately assigned as real values by the seed
script; this only flips the confirmation flag those specific rows were
always missing. coordinates_source_url is left null (no source was ever
recorded for these demo coordinates, and this script isn't the place to
invent one) - only location_verified and coordinates_verified_at change.
"""

from __future__ import annotations

import argparse
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_engine
from app.models.restaurant import Restaurant
from scripts.seed import SeedSafetyError, extract_supabase_project_ref, verify_seed_preconditions

CORRECTION_CONFIRMATION = "VERIFY_CHASKA_RESTAURANT_COORDINATES"

RESTAURANT_NAMES = (
    "Anatolia Table",
    "Bosphorus Kitchen",
    "Canton Garden",
    "Capital Grill Room",
    "Copper Fork",
    "Crust District",
    "Harbour Karahi",
    "Istanbul Passage",
    "Jade Wok House",
    "Lahore Bun Lab",
    "Margalla Dastarkhwan",
    "Olive & Ember",
    "Pasta Veranda",
    "Pindi Tandoor",
    "Roma Hearth",
    "Saffron Courtyard",
    "Seaview Continental",
    "Silk Route Wok",
    "Trattoria Noor",
    "Urban Bun Works",
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


def mark_location_verified(session: Session) -> tuple[str, int]:
    """Validate and flip location_verified for exactly the named restaurants."""
    restaurants = session.scalars(
        select(Restaurant).where(Restaurant.name.in_(RESTAURANT_NAMES))
    ).all()
    if len(restaurants) != len(RESTAURANT_NAMES):
        raise SeedSafetyError("restaurant count did not match expectations")
    found_names = {r.name for r in restaurants}
    if found_names != set(RESTAURANT_NAMES):
        raise SeedSafetyError("restaurant names did not match expectations")
    if any(r.latitude is None or r.longitude is None for r in restaurants):
        raise SeedSafetyError("a targeted restaurant is missing coordinates")

    already_verified = [r for r in restaurants if r.location_verified]
    unverified = [r for r in restaurants if not r.location_verified]
    if already_verified and unverified:
        raise SeedSafetyError("targeted restaurants are in a mixed verification state")
    if already_verified:
        return "already_corrected", 0

    now = datetime.now(UTC)
    for restaurant in unverified:
        restaurant.location_verified = True
        restaurant.coordinates_verified_at = now
    session.flush()
    return "corrected", len(unverified)


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
            status, count = mark_location_verified(session)
    except SeedSafetyError as error:
        raise SystemExit(str(error)) from error

    if status == "already_corrected":
        print("Restaurant coordinates are already marked verified; no changes made")
    else:
        print(f"Marked {count} restaurants as location-verified")


if __name__ == "__main__":
    main()
