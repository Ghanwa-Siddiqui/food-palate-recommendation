from app.models.interaction import Interaction
from app.models.review import Review
from app.models.user import User
from app.schemas.interaction import InteractionRead
from tests.factories import dish, restaurant


def test_user_restaurant_dish_review_and_interaction_relationships(session):
    user = User(name="Test User", email="user@example.test")
    owner = restaurant()
    session.add_all([user, owner])
    session.flush()
    menu_item = dish(owner.id)
    session.add(menu_item)
    session.flush()
    review = Review(user_id=user.id, dish_id=menu_item.id, rating=5, text="Great")
    interaction = Interaction(user_id=user.id, dish_id=menu_item.id, action="save")
    session.add_all([review, interaction])
    session.commit()
    session.refresh(user)
    session.refresh(owner)
    session.refresh(menu_item)

    assert owner.dishes == [menu_item]
    assert menu_item.restaurant is owner
    assert user.reviews == [review]
    assert review.user is user
    assert review.dish is menu_item
    assert user.interactions == [interaction]
    assert interaction.user is user
    assert interaction.dish is menu_item

    public = InteractionRead.model_validate(interaction).model_dump(mode="json")
    assert "ts" in public
    assert "created_at" not in public


def test_user_email_has_unique_constraint_without_redundant_index():
    email = User.__table__.c.email

    assert email.unique is True
    assert email.index in {False, None}
