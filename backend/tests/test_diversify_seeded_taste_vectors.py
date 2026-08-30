import uuid

import pytest
from sqlalchemy.orm import Session

from app.models.user import User
from scripts.diversify_seeded_taste_vectors import (
    CORRECTION_CONFIRMATION,
    authorize_correction,
    diversify_seeded_taste_vectors,
)
from scripts.seed import SeedSafetyError
from scripts.seed_customer_taste_demo import CLUSTERS

REMOTE_URL = "postgresql://postgres.projectref:secret@pooler.supabase.com:6543/postgres"

_SPICY_PAKISTANI = CLUSTERS[0]
_SPICY_LABEL, _SPICY_CUISINES, _SPICY_FAVOURITES, _SPICY_LEVELS, _SPICY_TEXTURES = _SPICY_PAKISTANI


class _FakeAnswers:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _fake_build_taste_vector(answers: _FakeAnswers) -> list[float]:
    # Deterministic stand-in sensitive to every field build_taste_vector's
    # real inputs cover, so tests can assert the vector actually changed
    # without needing the real (heavy) Sentence Transformers model.
    text = "|".join(f"{k}={v}" for k, v in sorted(answers.kwargs.items(), key=str))
    seed = sum((index + 1) * ord(character) for index, character in enumerate(text))
    return [((seed + index * 31) % 1000) / 1000 for index in range(384)]


def _cluster_member(email: str, *, dish_count: int = 4, **overrides) -> User:
    values = {
        "id": uuid.uuid4(),
        "name": email.split("@")[0],
        "email": email,
        "role": "customer",
        "onboarding_complete": True,
        "preferred_cuisines": list(_SPICY_CUISINES),
        "favourite_dishes": list(_SPICY_FAVOURITES[:dish_count]),
        "spice_preference": _SPICY_LEVELS[0],
        "sweetness_preference": _SPICY_LEVELS[1],
        "sourness_preference": _SPICY_LEVELS[2],
        "saltiness_preference": _SPICY_LEVELS[3],
        "oiliness_preference": _SPICY_LEVELS[4],
        "richness_preference": _SPICY_LEVELS[5],
        "preferred_textures": list(_SPICY_TEXTURES),
        "taste_vector": [0.0] * 384,
    }
    values.update(overrides)
    return User(**values)


def test_diversify_breaks_up_a_byte_identical_pair(session: Session):
    twin_a = _cluster_member("sadia@chaska.dev")
    twin_b = _cluster_member("naveed@chaska.dev")
    assert twin_a.favourite_dishes == twin_b.favourite_dishes  # identical to start

    session.add_all([twin_a, twin_b])
    session.commit()

    with Session(session.get_bind()) as correction_session:
        count = diversify_seeded_taste_vectors(
            correction_session, answers_and_builder=(_FakeAnswers, _fake_build_taste_vector)
        )
        correction_session.commit()

    assert count == 2
    session.expire_all()
    refreshed_a = session.get(User, twin_a.id)
    refreshed_b = session.get(User, twin_b.id)
    assert refreshed_a.taste_vector != refreshed_b.taste_vector


def test_diversify_keeps_cluster_identity_intact(session: Session):
    member = _cluster_member("member@chaska.dev")
    session.add(member)
    session.commit()

    with Session(session.get_bind()) as correction_session:
        diversify_seeded_taste_vectors(
            correction_session, answers_and_builder=(_FakeAnswers, _fake_build_taste_vector)
        )
        correction_session.commit()

    session.expire_all()
    refreshed = session.get(User, member.id)
    assert refreshed.preferred_cuisines == list(_SPICY_CUISINES)
    assert set(_SPICY_TEXTURES) <= set(refreshed.preferred_textures)
    assert len(refreshed.favourite_dishes) == 3
    assert set(refreshed.favourite_dishes) <= set(_SPICY_FAVOURITES)
    for field, index in zip(
        (
            "spice_preference", "sweetness_preference", "sourness_preference",
            "saltiness_preference", "oiliness_preference", "richness_preference",
        ),
        range(6),
    ):
        assert abs(getattr(refreshed, field) - _SPICY_LEVELS[index]) <= 2


def test_diversify_is_idempotent(session: Session):
    member = _cluster_member("member@chaska.dev")
    session.add(member)
    session.commit()

    with Session(session.get_bind()) as correction_session:
        diversify_seeded_taste_vectors(
            correction_session, answers_and_builder=(_FakeAnswers, _fake_build_taste_vector)
        )
        correction_session.commit()
    session.expire_all()
    first_pass = session.get(User, member.id)
    first_vector = list(first_pass.taste_vector)
    first_dishes = list(first_pass.favourite_dishes)

    with Session(session.get_bind()) as correction_session:
        diversify_seeded_taste_vectors(
            correction_session, answers_and_builder=(_FakeAnswers, _fake_build_taste_vector)
        )
        correction_session.commit()
    session.expire_all()
    second_pass = session.get(User, member.id)
    assert list(second_pass.taste_vector) == first_vector
    assert list(second_pass.favourite_dishes) == first_dishes


def test_diversify_ignores_users_that_do_not_match_a_known_cluster(session: Session):
    unmatched = _cluster_member("qa.tester@chaska.dev", favourite_dishes=["Biryani"])
    session.add(unmatched)
    session.commit()

    with Session(session.get_bind()) as correction_session:
        with pytest.raises(SeedSafetyError, match="no seeded cluster members"):
            diversify_seeded_taste_vectors(
                correction_session, answers_and_builder=(_FakeAnswers, _fake_build_taste_vector)
            )

    session.expire_all()
    untouched = session.get(User, unmatched.id)
    assert untouched.favourite_dishes == ["Biryani"]
    assert untouched.taste_vector == [0.0] * 384


def test_diversify_ignores_users_who_have_not_onboarded(session: Session):
    matched = _cluster_member("member@chaska.dev")
    not_onboarded = _cluster_member(
        "incomplete@chaska.dev", onboarding_complete=False, taste_vector=None
    )
    session.add_all([matched, not_onboarded])
    session.commit()

    with Session(session.get_bind()) as correction_session:
        count = diversify_seeded_taste_vectors(
            correction_session, answers_and_builder=(_FakeAnswers, _fake_build_taste_vector)
        )
        correction_session.commit()

    assert count == 1
    session.expire_all()
    assert session.get(User, not_onboarded.id).taste_vector is None


def _authorization_values():
    return {
        "database_url": REMOTE_URL,
        "app_env": "development",
        "confirmation": CORRECTION_CONFIRMATION,
        "expected_project_ref": "projectref",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("app_env", "production"),
        ("confirmation", None),
        ("confirmation", "wrong"),
        ("expected_project_ref", None),
        ("expected_project_ref", "differentref"),
    ],
)
def test_diversify_requires_every_authorization_gate(field: str, value: str | None):
    values = _authorization_values()
    values[field] = value
    with pytest.raises(SeedSafetyError):
        authorize_correction(**values)


def test_diversify_accepts_exact_development_authorization():
    authorize_correction(**_authorization_values())
