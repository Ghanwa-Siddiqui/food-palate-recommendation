import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.constants import EMBEDDING_DIMENSION


@dataclass(frozen=True)
class ProcessedReview:
    sentiment: float
    spice: float
    oiliness: float
    tags: list[str]
    embedding: list[float] | None


class ReviewProcessor(Protocol):
    def process(self, text: str, rating: int) -> ProcessedReview: ...


class LiveReviewProcessor:
    def process(self, text: str, rating: int) -> ProcessedReview:
        repository_root = str(Path(__file__).resolve().parents[4])
        if repository_root not in sys.path:
            sys.path.insert(0, repository_root)
        from review_intelligence.src.embeddings import ReviewEmbedder
        from review_intelligence.src.extractor import ReviewExtractor

        features = ReviewExtractor().extract(text, rating)
        embedding = ReviewEmbedder().embed(text)
        if len(embedding) != EMBEDDING_DIMENSION:
            raise ValueError("review_embedding_dimension")
        return ProcessedReview(
            features.sentiment,
            features.spice_level,
            features.oiliness,
            features.flavor_tags,
            embedding,
        )


def get_review_processor() -> ReviewProcessor:
    return LiveReviewProcessor()
