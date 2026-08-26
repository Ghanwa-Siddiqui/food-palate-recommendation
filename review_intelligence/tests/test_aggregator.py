import pytest

from review_intelligence.src.aggregator import aggregate_reviews
from review_intelligence.src.models import ValidationError


def test_aggregation_calculates_average_tags_and_vector():
    rows = [
        {"dish_id": "D001", "sentiment": 0.9, "spice_level": 0.9, "oiliness": 0.5, "flavor_tags": ["spicy", "tender"], "embedding": [1, 3]},
        {"dish_id": "D001", "sentiment": 0.8, "spice_level": 0.7, "oiliness": 0.7, "flavor_tags": ["spicy", "rich gravy"], "embedding": [3, 5]},
        {"dish_id": "D001", "sentiment": 0.95, "spice_level": 0.9, "oiliness": 0.6, "flavor_tags": ["spicy"], "embedding": [5, 7]},
    ]
    summary = aggregate_reviews(rows)["D001"]
    assert summary.avg_sentiment == 0.883
    assert summary.spice_level == 0.833
    assert summary.oiliness == 0.6
    assert summary.flavor_tags == ["spicy", "rich gravy", "tender"]
    assert summary.review_vector == [3.0, 5.0]


def test_missing_dish_id_is_rejected():
    with pytest.raises(ValidationError, match="dish_id"):
        aggregate_reviews([{"sentiment": 0.5, "spice_level": 0.5, "oiliness": 0.5, "flavor_tags": []}])
