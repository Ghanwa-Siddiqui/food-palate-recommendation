"""Small, dependency-light data models and validation for the shared contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


class ValidationError(ValueError):
    """Raised when extraction output does not match the Review Intelligence schema."""


def _score(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValidationError(f"{name} must be a number between 0 and 1")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{name} must be a number between 0 and 1") from exc
    if not 0.0 <= result <= 1.0:
        raise ValidationError(f"{name} must be between 0 and 1; got {result}")
    return result


def _tags(value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(tag, str) for tag in value):
        raise ValidationError("flavor_tags must be a list of strings")
    # Preserve ordering, remove blanks and duplicate tags deterministically.
    result: list[str] = []
    for tag in value:
        cleaned = tag.strip().lower()
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


@dataclass(frozen=True)
class ReviewFeatures:
    sentiment: float
    spice_level: float
    oiliness: float
    flavor_tags: list[str]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ReviewFeatures":
        required = {"sentiment", "spice_level", "oiliness", "flavor_tags"}
        missing = required.difference(value)
        if missing:
            raise ValidationError(f"Missing required extraction fields: {', '.join(sorted(missing))}")
        return cls(
            sentiment=_score(value["sentiment"], "sentiment"),
            spice_level=_score(value["spice_level"], "spice_level"),
            oiliness=_score(value["oiliness"], "oiliness"),
            flavor_tags=_tags(value["flavor_tags"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DishReviewSummary:
    dish_id: str
    avg_sentiment: float
    spice_level: float
    oiliness: float
    flavor_tags: list[str]
    review_vector: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
