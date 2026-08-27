from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth import (
    AuthSession,
    AuthUser,
    DuplicateSignupError,
    InvalidCredentialsError,
    SignupResult,
    get_auth_provider,
)
from app.backend_client import (
    DishItem,
    FeedResult,
    InteractionItem,
    PublicReview,
    RestaurantItem,
    ReviewSummary,
    UserProfile,
    get_backend_client,
)
from app.main import app

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
DISH_ID = UUID("22222222-2222-4222-8222-222222222222")
RESTAURANT_ID = UUID("33333333-3333-4333-8333-333333333333")


class FakeAuthProvider:
    def __init__(self):
        self.user = AuthUser(USER_ID, "test@example.com", "Test Eater")
        self.password = "password123"
        self.valid_tokens = {"access": self.user}

    def signup(self, email, password, name, role="customer"):
        if email == self.user.email:
            raise DuplicateSignupError("An account with this email already exists")
        user = AuthUser(USER_ID, email, name)
        session = AuthSession(user, "access", "refresh")
        self.user = user
        self.password = password
        self.valid_tokens["access"] = user
        return SignupResult(user, session, False)

    def login(self, email, password):
        if email != self.user.email or password != self.password:
            raise InvalidCredentialsError("Email or password is incorrect")
        return AuthSession(self.user, "access", "refresh")

    def verify(self, access_token):
        if access_token not in self.valid_tokens:
            raise InvalidCredentialsError()
        return self.valid_tokens[access_token]

    def refresh(self, refresh_token):
        if refresh_token != "refresh":
            raise InvalidCredentialsError()
        return AuthSession(self.user, "access", "refresh")

    def logout(self, access_token, refresh_token):
        self.valid_tokens.pop(access_token, None)


class FakeBackendClient:
    def __init__(self):
        self.profile = UserProfile(
            user_id=USER_ID,
            name="Test Eater",
            email="test@example.com",
            role="customer",
            onboarding_complete=False,
            city=None,
            preferred_cuisines=[],
            favourite_dishes=[],
            spice_preference=2,
            sweetness_preference=2,
            sourness_preference=2,
            saltiness_preference=2,
            oiliness_preference=2,
            richness_preference=2,
            preferred_textures=[],
            budget_min=0,
            budget_max=1500,
            dietary_requirements=[],
            allergies=[],
            disliked_ingredients=[],
            require_halal=False,
            taste_updated_at=None,
        )
        self.actions = []
        self.reviews = []
        self.partner_dish_items = []
        self.partner_creation_keys = {}
        self.last_profile_payload = None
        self.sync_calls = 0
        self.empty = False
        self.fail = False
        self.dish = DishItem(
            id=DISH_ID,
            restaurant_id=RESTAURANT_ID,
            name="Chicken Karahi",
            description="Tomato-forward chicken karahi",
            cuisine="Pakistani",
            ingredients=["chicken", "tomato"],
            price=1250,
            spice_level=4,
            oiliness=3,
            sweetness=0,
            sourness=1,
            saltiness=3,
            smokiness=2,
            richness=4,
            texture_tags=["tender"],
            dietary_tags=[],
            allergens=[],
            preparation_style="stovetop",
            availability=True,
        )
        self.restaurant = RestaurantItem(
            id=RESTAURANT_ID,
            name="Real Restaurant",
            description=None,
            cuisine_types=["Pakistani"],
            address="Gulberg, Lahore",
            city="Lahore",
            lat=None,
            lng=None,
            location_verified=False,
            price_range="moderate",
            halal_status="unknown",
        )

    def _check(self):
        if self.fail:
            from app.backend_client import BackendUnavailable

            raise BackendUnavailable()

    def sync_user(self, user_id, name, email, role=None):
        self.sync_calls += 1
        self._check()
        self.profile = self.profile.model_copy(
            update={
                "user_id": user_id,
                "name": name,
                "email": email,
                **({"role": role} if role else {}),
            }
        )

    def partner_restaurants(self, user_id):
        self._check()
        return [self.restaurant] if self.restaurant.owner_id == user_id else []

    def create_partner_restaurant(self, user_id, payload):
        self._check()
        self.restaurant = self.restaurant.model_copy(
            update={**payload, "id": uuid4(), "owner_id": user_id}
        )
        return self.restaurant

    def update_partner_restaurant(self, user_id, restaurant_id, payload):
        self._check()
        if self.restaurant.owner_id != user_id or self.restaurant.id != restaurant_id:
            from app.backend_client import BackendValidationError

            raise BackendValidationError()
        self.restaurant = self.restaurant.model_copy(update=payload)
        return self.restaurant

    def partner_menu(self, user_id, restaurant_id):
        self._check()
        if self.restaurant.owner_id != user_id or self.restaurant.id != restaurant_id:
            from app.backend_client import BackendValidationError

            raise BackendValidationError()
        return [
            item
            for item in self.partner_dish_items
            if item.restaurant_id == restaurant_id
        ]

    def partner_dish(self, user_id, dish_id):
        self._check()
        item = next(dish for dish in self.partner_dish_items if dish.id == dish_id)
        if (
            self.restaurant.owner_id != user_id
            or item.restaurant_id != self.restaurant.id
        ):
            from app.backend_client import BackendValidationError

            raise BackendValidationError()
        return item

    def create_partner_dish(self, user_id, payload, idempotency_key):
        self._check()
        if idempotency_key in self.partner_creation_keys:
            return self.partner_creation_keys[idempotency_key]
        values = dict(payload)
        values["restaurant_id"] = UUID(values["restaurant_id"])
        item = DishItem(
            id=uuid4(),
            **values,
            archived_at=None,
            embedding_updated_at=datetime.now(UTC),
        )
        self.partner_dish_items.append(item)
        self.partner_creation_keys[idempotency_key] = item
        return item

    def update_partner_dish(self, user_id, dish_id, payload):
        item = self.partner_dish(user_id, dish_id)
        updated = item.model_copy(
            update={**payload, "embedding_updated_at": datetime.now(UTC)}
        )
        self.partner_dish_items[self.partner_dish_items.index(item)] = updated
        return updated

    def set_partner_dish_availability(self, user_id, dish_id, available):
        item = self.partner_dish(user_id, dish_id)
        updated = item.model_copy(update={"availability": available})
        self.partner_dish_items[self.partner_dish_items.index(item)] = updated
        return updated

    def archive_partner_dish(self, user_id, dish_id):
        item = self.partner_dish(user_id, dish_id)
        updated = item.model_copy(
            update={"availability": False, "archived_at": datetime.now(UTC)}
        )
        self.partner_dish_items[self.partner_dish_items.index(item)] = updated
        return updated

    def get_profile(self, user_id):
        self._check()
        return self.profile

    def update_profile(self, user_id, payload):
        self.last_profile_payload = payload
        update = {key: value for key, value in payload.items() if key != "taste_vector"}
        update.update(onboarding_complete=True, taste_updated_at=datetime.now(UTC))
        self.profile = self.profile.model_copy(update=update)
        return self.profile

    def get_feed(self, user_id, params):
        self._check()
        items = (
            []
            if self.empty
            else [
                {
                    "dish_id": DISH_ID,
                    "dish_name": self.dish.name,
                    "restaurant_id": RESTAURANT_ID,
                    "restaurant_name": self.restaurant.name,
                    "cuisine": "Pakistani",
                    "description": self.dish.description,
                    "price": self.dish.price,
                    "match_percentage": 92 + min(len(self.actions), 3),
                    "distance_km": None,
                    "halal_status": "unknown",
                    "availability": True,
                    "dietary_tags": [],
                    "texture_tags": ["tender"],
                    "taste_explanation": "Strongest available match: food profile.",
                    "review_insight": None,
                    "active_deals": [],
                    "saved": any(action.action == "save" for action in self.actions),
                    "signals": {
                        "taste": 90,
                        "food_profile": 95,
                        "review": 50,
                        "distance": 50,
                        "price": 80,
                        "popularity": 50,
                    },
                }
            ]
        )
        offset = int(dict(params).get("offset", 0))
        return FeedResult(
            user_id=user_id,
            total_candidates=len(items),
            items=items,
            neutral_signals=["review", "distance"],
            limit=12,
            offset=offset,
        )

    def similar_users(self, user_id):
        return []

    def interact(self, user_id, dish_id, action, client_event_id):
        existing = next(
            (item for item in self.actions if item.client_event_id == client_event_id),
            None,
        )
        if existing:
            return existing.model_copy(update={"duplicate": True})
        item = InteractionItem(
            id=uuid4(),
            user_id=user_id,
            dish_id=dish_id,
            action=action,
            ts=datetime.now(UTC),
            client_event_id=client_event_id,
        )
        self.actions.append(item)
        return item

    def unsave(self, user_id, dish_id):
        self.actions = [
            item
            for item in self.actions
            if not (item.dish_id == dish_id and item.action == "save")
        ]

    def interactions(self, user_id):
        return list(reversed(self.actions))

    def get_restaurant(self, restaurant_id):
        return self.restaurant

    def get_dish(self, dish_id):
        return self.dish

    def restaurant_deals(self, restaurant_id):
        return []

    def review_summary(self, dish_id):
        matching = [item for item in self.reviews if item.dish_id == dish_id]
        return ReviewSummary(
            dish_id=dish_id,
            review_count=len(matching),
            average_rating=(
                sum(item.rating for item in matching) / len(matching)
                if matching
                else None
            ),
            flavor_tags=[],
        )

    def dish_reviews(self, dish_id):
        return [item for item in self.reviews if item.dish_id == dish_id]

    def my_review(self, user_id, dish_id):
        return next((item for item in self.reviews if item.dish_id == dish_id), None)

    def create_review(self, user_id, payload):
        item = PublicReview(
            id=uuid4(),
            dish_id=UUID(payload["dish_id"]),
            rating=payload["rating"],
            text=payload["text"],
            reviewer_name="Test Eater"
            if payload["show_display_name"]
            else "Anonymous Chaska diner",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            processing_status="complete",
        )
        self.reviews.append(item)
        return item

    def update_review(self, user_id, review_id, payload):
        item = next(item for item in self.reviews if item.id == review_id)
        updated = item.model_copy(
            update={
                **payload,
                "reviewer_name": "Test Eater"
                if payload["show_display_name"]
                else "Anonymous Chaska diner",
                "updated_at": datetime.now(UTC),
            }
        )
        self.reviews[self.reviews.index(item)] = updated
        return updated


@pytest.fixture
def auth_provider():
    return FakeAuthProvider()


@pytest.fixture
def backend_client():
    return FakeBackendClient()


@pytest.fixture
def web_client(auth_provider, backend_client):
    app.dependency_overrides[get_auth_provider] = lambda: auth_provider
    app.dependency_overrides[get_backend_client] = lambda: backend_client
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    """Point the app's DATA_DIR at a per-test temp dir and reset caches."""
    monkeypatch.setattr("app.config.DATA_DIR", tmp_path)
    monkeypatch.setenv("STORAGE_BACKEND", "json")

    # Reset module-level caches that snapshotted DATA_DIR at import time.
    from app import dish_store

    dish_store.invalidate_cache()

    # Seed a minimal mock_dishes.json so dish_store returns something.
    import json

    from app.embedding import embed_dish

    dishes = [
        {
            "id": "d0000000-0000-4000-8000-000000000001",
            "restaurant_id": "r0000000-0000-4000-8000-000000000001",
            "name": "Chicken Karahi",
            "cuisine": "Pakistani",
            "ingredients": ["chicken", "tomato"],
            "price": 1000,
            "vector": embed_dish("Chicken Karahi", "Pakistani", ["chicken", "tomato"]),
            "lat": 24.8,
            "lng": 67.0,
        },
        {
            "id": "d0000000-0000-4000-8000-000000000002",
            "restaurant_id": "r0000000-0000-4000-8000-000000000002",
            "name": "Salmon Sushi",
            "cuisine": "Japanese",
            "ingredients": ["salmon", "rice"],
            "price": 1800,
            "vector": embed_dish("Salmon Sushi", "Japanese", ["salmon", "rice"]),
            "lat": 24.8,
            "lng": 67.0,
        },
    ]
    (tmp_path / "mock_dishes.json").write_text(json.dumps(dishes), encoding="utf-8")
    yield
    dish_store.invalidate_cache()
