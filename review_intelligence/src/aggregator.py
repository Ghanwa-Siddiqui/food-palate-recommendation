"""Deterministic dish-level aggregation of extracted review features."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import DishReviewSummary, ReviewFeatures, ValidationError


def _vector(value: Any) -> list[float]:
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValidationError("embedding must be JSON list") from exc
    if not isinstance(value, list):
        raise ValidationError("embedding must be a list")
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise ValidationError("embedding must contain numeric values") from exc


def _features_from_row(row: Mapping[str, Any]) -> ReviewFeatures:
    """Decode CSV JSON columns before applying the shared feature validator."""
    value = dict(row)
    tags = value.get("flavor_tags")
    if isinstance(tags, str):
        try:
            value["flavor_tags"] = json.loads(tags)
        except json.JSONDecodeError as exc:
            raise ValidationError("flavor_tags must be a JSON list in feature CSV") from exc
    return ReviewFeatures.from_mapping(value)


def aggregate_reviews(rows: Iterable[Mapping[str, Any]], max_tags: int = 8) -> dict[str, DishReviewSummary]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        dish_id = str(row.get("dish_id", "")).strip()
        if not dish_id:
            raise ValidationError("Each review row requires dish_id")
        groups.setdefault(dish_id, []).append(row)

    summaries: dict[str, DishReviewSummary] = {}
    for dish_id, reviews in groups.items():
        features = [_features_from_row(review) for review in reviews]
        tag_counts = Counter(tag for feature in features for tag in feature.flavor_tags)
        # Frequency descending, then alphabetical tie-breaker makes API output stable.
        tags = [tag for tag, _ in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))[:max_tags]]
        vectors = [_vector(review.get("embedding")) for review in reviews]
        usable_vectors = [vector for vector in vectors if vector]
        if usable_vectors and len({len(vector) for vector in usable_vectors}) != 1:
            raise ValidationError(f"Embeddings for dish {dish_id} have inconsistent dimensions")
        mean_vector = [round(sum(values) / len(usable_vectors), 8) for values in zip(*usable_vectors)] if usable_vectors else []
        summaries[dish_id] = DishReviewSummary(
            dish_id=dish_id,
            avg_sentiment=round(sum(item.sentiment for item in features) / len(features), 3),
            spice_level=round(sum(item.spice_level for item in features) / len(features), 3),
            oiliness=round(sum(item.oiliness for item in features) / len(features), 3),
            flavor_tags=tags,
            review_vector=mean_vector,
        )
    return summaries


def load_feature_rows(path: str | Path) -> list[dict[str, str]]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Review features file not found: {file_path}. Run process_reviews.py first.")
    with file_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))
