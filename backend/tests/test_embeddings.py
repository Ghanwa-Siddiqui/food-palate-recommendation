from app.services.data_core.embeddings import (
    DeterministicFakeEmbeddingProvider,
    build_dish_embedding_text,
)


def test_embedding_text_contains_all_relevant_dish_attributes():
    text = build_dish_embedding_text(
        name="Karahi",
        description="Rich tomato curry",
        cuisine="Pakistani",
        ingredients=["chicken", "ginger"],
        spice_level=4,
        oiliness=3,
        sweetness=0,
        sourness=1,
        saltiness=3,
        smokiness=2,
        richness=4,
        texture_tags=["tender"],
        dietary_tags=["halal"],
        allergens=[],
        preparation_style="stovetop",
        availability=True,
    )
    for expected in (
        "Karahi",
        "tomato",
        "Pakistani",
        "chicken",
        "spice 4/5",
        "smokiness: 2/5",
        "richness: 4/5",
        "tender",
        "halal",
    ):
        assert expected in text


def test_fake_embedding_is_deterministic_and_correct_dimension():
    provider = DeterministicFakeEmbeddingProvider()
    assert provider.embed("same dish") == provider.embed("same dish")
    assert provider.embed("same dish") != provider.embed("different dish")
    assert len(provider.embed("same dish")) == 384
