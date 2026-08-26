import json

import pytest

from review_intelligence.src.extractor import ExtractionError, ReviewExtractor


class FakeClient:
    def __init__(self, response):
        self.response = response

    def generate(self, prompt):
        return self.response


@pytest.mark.parametrize(
    ("text", "response", "assertion"),
    [
        ("Absolutely delicious and amazing.", {"sentiment": 0.95, "spice_level": 0.5, "oiliness": 0.5, "flavor_tags": []}, lambda x: x.sentiment >= 0.8),
        ("Terrible food. Too salty and cold.", {"sentiment": 0.1, "spice_level": 0.5, "oiliness": 0.5, "flavor_tags": ["salty"]}, lambda x: x.sentiment <= 0.2),
        ("Extremely spicy. I could barely eat it.", {"sentiment": 0.25, "spice_level": 0.98, "oiliness": 0.5, "flavor_tags": ["spicy"]}, lambda x: x.spice_level >= 0.9),
        ("Very oily and greasy.", {"sentiment": 0.3, "spice_level": 0.5, "oiliness": 0.95, "flavor_tags": ["oily"]}, lambda x: x.oiliness >= 0.9),
        ("Mild and creamy with a smooth flavor.", {"sentiment": 0.75, "spice_level": 0.1, "oiliness": 0.5, "flavor_tags": ["mild", "creamy", "smooth"]}, lambda x: x.spice_level <= 0.2 and "creamy" in x.flavor_tags),
    ],
)
def test_extraction_with_mocked_llm(text, response, assertion):
    result = ReviewExtractor(FakeClient(json.dumps(response))).extract(text)
    assert assertion(result)


def test_malformed_model_json_is_clear_error():
    with pytest.raises(ExtractionError, match="malformed JSON"):
        ReviewExtractor(FakeClient("not json")).extract("Good food")


def test_invalid_score_is_rejected():
    bad = {"sentiment": 1.2, "spice_level": 0.5, "oiliness": 0.5, "flavor_tags": []}
    with pytest.raises(ExtractionError, match="between 0 and 1"):
        ReviewExtractor(FakeClient(json.dumps(bad))).extract("Good food")


@pytest.mark.parametrize(
    ("text", "response", "expected_sentiment"),
    [
        ("Amazing rich gravy but quite oily for my taste.", {"sentiment": 0.5, "spice_level": 0.5, "oiliness": 0.7, "flavor_tags": ["rich gravy", "oily"]}, 0.85),
        ("The gravy was bland and the chicken was dry.", {"sentiment": 0.5, "spice_level": 0.5, "oiliness": 0.5, "flavor_tags": ["dry"]}, 0.2),
        ("Cold and bland nihari arrived with greasy oil on top.", {"sentiment": 0.5, "spice_level": 0.5, "oiliness": 0.9, "flavor_tags": ["greasy"]}, 0.2),
        ("The beef nihari was deeply rich, tender, and warming.", {"sentiment": 0.5, "spice_level": 0.5, "oiliness": 0.5, "flavor_tags": ["rich", "tender"]}, 0.9),
    ],
)
def test_obvious_polarity_does_not_keep_uninformative_neutral_score(text, response, expected_sentiment):
    result = ReviewExtractor(FakeClient(json.dumps(response))).extract(text)
    assert result.sentiment == expected_sentiment


def test_unmentioned_spice_and_oil_are_not_returned_as_medium():
    response = {"sentiment": 0.85, "spice_level": 0.5, "oiliness": 0.5, "flavor_tags": ["tender"]}
    result = ReviewExtractor(FakeClient(json.dumps(response))).extract("The chicken was tender and delicious.")
    assert result.spice_level == 0.0
    assert result.oiliness == 0.0


def test_negated_oil_is_low_and_never_emitted_as_a_tag():
    response = {"sentiment": 0.7, "spice_level": 0.5, "oiliness": 0.8, "flavor_tags": ["mild", "greasy", "oil"]}
    result = ReviewExtractor(FakeClient(json.dumps(response))).extract(
        "Mild flavor, but the kebabs were fresh and not greasy."
    )
    assert result.spice_level == 0.0
    assert result.oiliness == 0.0
    assert set(result.flavor_tags) == {"mild", "fresh"}
    assert "greasy" not in result.flavor_tags


def test_tag_variants_are_normalized_and_unsupported_tags_are_removed():
    response = {"sentiment": 0.7, "spice_level": 0.0, "oiliness": 0.0, "flavor_tags": ["sweety", "smokey", "umami"]}
    result = ReviewExtractor(FakeClient(json.dumps(response))).extract("A sweet and smoky dessert.")
    assert result.flavor_tags == ["sweet", "smoky"]


@pytest.mark.parametrize(
    ("text", "rating"),
    [
        ("Cold and bland nihari arrived with greasy oil on top.", 1),
        ("Tough meat and a sour broth ruined the dish.", 1),
        ("The sauce was too oily and overly sweet.", 2),
        ("Too salty and heavy; the beef was tough.", 2),
        ("Dry rice and bland chicken made this disappointing.", 2),
        ("Too sweet and soggy; I did not enjoy it.", 2),
        ("Bland and watery haleem with no flavor.", 2),
    ],
)
def test_explicit_negative_language_and_rating_correct_a_wrong_positive_llm_score(text, rating):
    wrong_llm = {"sentiment": 0.85, "spice_level": 0.5, "oiliness": 0.5, "flavor_tags": []}
    result = ReviewExtractor(FakeClient(json.dumps(wrong_llm))).extract(text, rating=rating)
    assert result.sentiment <= 0.35


@pytest.mark.parametrize(
    ("text", "expected_spice", "expected_oil"),
    [
        ("Very spicy chicken with tender meat.", 0.9, 0.0),
        ("Warmly spiced haleem with a smooth texture.", 0.5, 0.0),
        ("Medium spice but slightly oily gravy.", 0.5, 0.5),
        ("Mild food with no excess oil.", 0.0, 0.0),
    ],
)
def test_explicit_spice_and_oil_phrases_override_misleading_llm_scores(text, expected_spice, expected_oil):
    wrong_llm = {"sentiment": 0.7, "spice_level": 0.0, "oiliness": 0.9, "flavor_tags": []}
    result = ReviewExtractor(FakeClient(json.dumps(wrong_llm))).extract(text)
    assert result.spice_level == expected_spice
    assert result.oiliness == expected_oil


@pytest.mark.parametrize(
    ("text", "expected_tags"),
    [
        ("Very spicy and delicious chicken karahi. The chicken was tender.", {"spicy", "delicious", "tender"}),
        ("Butter chicken was creamy, sweet, and wonderfully rich.", {"creamy", "sweet", "rich"}),
        ("Paya had a rich, spicy broth and tender meat.", {"rich", "spicy", "tender"}),
        ("Haleem was rich, creamy, and warmly spiced.", {"rich", "creamy", "spicy"}),
    ],
)
def test_source_supported_canonical_tags_are_added_when_llm_omits_them(text, expected_tags):
    empty_llm_tags = {"sentiment": 0.8, "spice_level": 0.0, "oiliness": 0.0, "flavor_tags": []}
    result = ReviewExtractor(FakeClient(json.dumps(empty_llm_tags))).extract(text)
    assert expected_tags.issubset(result.flavor_tags)
