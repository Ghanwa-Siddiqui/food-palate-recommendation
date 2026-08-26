"""Reusable local Sentence Transformers embeddings for review text."""

from __future__ import annotations

from typing import Protocol

from .config import DEFAULT_EMBEDDING_MODEL


class EmbeddingError(RuntimeError):
    pass


class _Encoder(Protocol):
    def encode(self, sentences: list[str], **kwargs: object) -> object: ...


class ReviewEmbedder:
    """Lazily loads a local/cacheable Sentence Transformers model once per instance."""

    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL, model: _Encoder | None = None):
        self.model_name, self._model = model_name, model

    def _load_model(self) -> _Encoder:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
            except Exception as exc:  # dependency/model downloads can fail in many ways
                raise EmbeddingError(
                    f"Could not load embedding model `{self.model_name}`. Install sentence-transformers "
                    "and ensure the model can be downloaded or is cached locally."
                ) from exc
        return self._model

    def embed(self, text: str) -> list[float]:
        if not isinstance(text, str) or not text.strip():
            raise EmbeddingError("Review text must be a non-empty string")
        try:
            vector = self._load_model().encode([text], normalize_embeddings=True)
            return [float(value) for value in vector[0]]  # type: ignore[index]
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError("Embedding generation failed") from exc
