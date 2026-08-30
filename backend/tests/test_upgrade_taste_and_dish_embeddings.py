import uuid

import pytest
from sqlalchemy.orm import Session

from app.models.dish import Dish
from app.models.user import User
from scripts.upgrade_taste_and_dish_embeddings import (
    CORRECTION_CONFIRMATION,
    authorize_correction,
    upgrade_dish_embeddings,
    upgrade_taste_vectors,
)
from scripts.seed import SeedSafetyError
from tests.factories import dish as make_dish
from tests.factories import restaurant as make_restaurant

REMOTE_URL = "postgresql://postgres.projectref:secret@pooler.supabase.com:6543/postgres"


class _FakeProvider:
    """Deterministic stand-in: same text always yields the same 384-dim
    vector, so tests can assert the upgrade actually ran without needing
    the real (heavy, network-downloading) Sentence Transformers model."""

    def embed(self, text: str) -> list[float]:
        seed = sum((index + 1) * ord(character) for index, character in enumerate(text))
        return [((seed + index * 17) % 1000) / 1000 for index in range(384)]


class _FakeAnswers:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _fake_build_taste_vector(answers: _FakeAnswers) -> list[float]:
    text = "|".join(f"{k}={v}" for k, v in sorted(answers.kwargs.items(), key=str))
    return _FakeProvider().embed(text)


def _onboarded_user(**overrides) -> User:
    values = {
        "id": uuid.uuid4(),
        "name": "Taste Tester",
        "email": f"{uuid.uuid4().hex}@example.test",
        "role": "customer",
        "onboarding_complete": True,
        "preferred_cuisines": ["Pakistani"],
        "favourite_dishes": ["Chicken Karahi"],
        "taste_vector": [0.0] * 384,
    }
    values.update(overrides)
    return User(**values)


def test_upgrade_dish_embeddings_replaces_every_dish_vector(session: Session):
    place = make_restaurant()
    session.add(place)
    session.flush()
    dishes = [make_dish(place.id, name=f"Dish {i}", embedding=[0.1] * 384) for i in range(5)]
    session.add_all(dishes)
    session.commit()

    count = upgrade_dish_embeddings(session, _FakeProvider())
    session.commit()

    assert count == 5
    session.expire_all()
    for stored in session.query(Dish).all():
        assert stored.embedding != [0.1] * 384
        assert len(stored.embedding) == 384
        assert stored.embedding_updated_at is not None


def test_upgrade_dish_embeddings_matches_a_direct_provider_call(session: Session):
    place = make_restaurant()
    session.add(place)
    session.flush()
    item = make_dish(place.id, name="Chicken Karahi", embedding=[0.1] * 384)
    session.add(item)
    session.commit()

    upgrade_dish_embeddings(session, _FakeProvider())
    session.commit()
    session.expire_all()

    stored = session.query(Dish).filter_by(id=item.id).one()
    assert stored.embedding == _FakeProvider().embed(
        f"name: {item.name} | description: {item.description} | cuisine: {item.cuisine} | "
        f"ingredients: {', '.join(item.ingredients)} | "
        f"taste: spice {item.spice_level}/5, oiliness {item.oiliness}/5, sweetness "
        f"{item.sweetness}/5, sourness {item.sourness}/5, saltiness {item.saltiness}/5 | "
        f"smokiness: {item.smokiness}/5 | richness: {item.richness}/5 | "
        f"textures: {', '.join(item.texture_tags)} | dietary: {', '.join(item.dietary_tags)} | "
        f"allergens: {', '.join(item.allergens)} | preparation: {item.preparation_style} | "
        f"available: {item.availability}"
    )


def test_upgrade_taste_vectors_only_touches_onboarded_users(session: Session):
    onboarded = _onboarded_user()
    not_onboarded = _onboarded_user(onboarding_complete=False, taste_vector=None)
    session.add_all([onboarded, not_onboarded])
    session.commit()

    count = upgrade_taste_vectors(
        session, answers_and_builder=(_FakeAnswers, _fake_build_taste_vector)
    )
    session.commit()

    assert count == 1
    session.expire_all()
    refreshed_onboarded = session.get(User, onboarded.id)
    refreshed_skipped = session.get(User, not_onboarded.id)
    assert refreshed_onboarded.taste_vector != [0.0] * 384
    assert len(refreshed_onboarded.taste_vector) == 384
    assert refreshed_onboarded.taste_updated_at is not None
    assert refreshed_skipped.taste_vector is None


def test_upgrade_taste_vectors_reflects_the_users_own_stored_preferences(session: Session):
    spicy = _onboarded_user(preferred_cuisines=["Pakistani"], spice_preference=5)
    mild = _onboarded_user(preferred_cuisines=["Continental"], spice_preference=0)
    session.add_all([spicy, mild])
    session.commit()

    upgrade_taste_vectors(session, answers_and_builder=(_FakeAnswers, _fake_build_taste_vector))
    session.commit()
    session.expire_all()

    refreshed_spicy = session.get(User, spicy.id)
    refreshed_mild = session.get(User, mild.id)
    assert refreshed_spicy.taste_vector != refreshed_mild.taste_vector


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
def test_upgrade_requires_every_authorization_gate(field: str, value: str | None):
    values = _authorization_values()
    values[field] = value
    with pytest.raises(SeedSafetyError):
        authorize_correction(**values)


def test_upgrade_accepts_exact_development_authorization():
    authorize_correction(**_authorization_values())
