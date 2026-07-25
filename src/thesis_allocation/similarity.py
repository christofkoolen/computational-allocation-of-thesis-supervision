"""Pluggable text similarity backends."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from thesis_allocation.errors import ThesisAllocationError


DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class SimilarityBackend(Protocol):
    """Contract used by the supervisor matcher."""

    def score(
        self,
        queries: list[str],
        candidates: list[str],
    ) -> np.ndarray:
        """Return a query-by-candidate similarity matrix."""


class TfidfSimilarity:
    """Offline lexical fallback used for testing and constrained environments."""

    def score(
        self,
        queries: list[str],
        candidates: list[str],
    ) -> np.ndarray:
        if not queries or not candidates:
            return np.zeros((len(queries), len(candidates)), dtype=float)
        if not any(text.strip() for text in [*queries, *candidates]):
            return np.zeros((len(queries), len(candidates)), dtype=float)

        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(
            lowercase=True,
            ngram_range=(1, 2),
            strip_accents="unicode",
        )
        try:
            matrix = vectorizer.fit_transform([*queries, *candidates])
        except ValueError as exc:
            if "empty vocabulary" in str(exc).casefold():
                return np.zeros((len(queries), len(candidates)), dtype=float)
            raise
        query_matrix = matrix[: len(queries)]
        candidate_matrix = matrix[len(queries) :]
        return cosine_similarity(query_matrix, candidate_matrix)


class SentenceTransformerSimilarity:
    """Semantic similarity based on normalized sentence embeddings."""

    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ThesisAllocationError(
                "Semantic matching requires the optional dependency. "
                "Install the project with: pip install -e '.[semantic]'"
            ) from exc
        self.model = SentenceTransformer(model_name)

    def score(
        self,
        queries: list[str],
        candidates: list[str],
    ) -> np.ndarray:
        if not queries or not candidates:
            return np.zeros((len(queries), len(candidates)), dtype=float)
        query_embeddings = self.model.encode(
            queries,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        candidate_embeddings = self.model.encode(
            candidates,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(query_embeddings) @ np.asarray(candidate_embeddings).T


def create_similarity_backend(
    name: str,
    *,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
) -> SimilarityBackend:
    """Construct a supported similarity backend."""

    normalized = name.strip().casefold().replace("_", "-")
    if normalized in {"sentence-transformers", "semantic", "embeddings"}:
        return SentenceTransformerSimilarity(model_name)
    if normalized in {"tfidf", "tf-idf"}:
        return TfidfSimilarity()
    raise ThesisAllocationError(
        f"Unknown similarity backend '{name}'; use sentence-transformers or tfidf"
    )
