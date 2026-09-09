from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

import numpy as np

from thesis_allocation.similarity import (
    DEFAULT_EMBEDDING_BATCH_SIZE,
    DEFAULT_EMBEDDING_MODEL,
    MAX_EMBEDDING_SEQUENCE_LENGTH,
    SentenceTransformerSimilarity,
)


class _FakeSentenceTransformer:
    instances: list["_FakeSentenceTransformer"] = []

    def __init__(self, model_name: str):
        self.model_name = model_name
        self.max_seq_length = 8_192
        self.encode_calls: list[tuple[list[str], dict[str, object]]] = []
        self.instances.append(self)

    def encode(self, texts: list[str], **options: object) -> np.ndarray:
        self.encode_calls.append((texts, options))
        return np.asarray(
            [[float(index + 1), 1.0] for index, _ in enumerate(texts)],
            dtype=float,
        )


class SentenceTransformerSimilarityTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeSentenceTransformer.instances.clear()
        self.module = types.ModuleType("sentence_transformers")
        self.module.SentenceTransformer = _FakeSentenceTransformer

    def test_multilingual_model_is_the_default(self) -> None:
        self.assertEqual(DEFAULT_EMBEDDING_MODEL, "BAAI/bge-m3")

    def test_semantic_backend_caps_length_and_uses_conservative_batches(self) -> None:
        with patch.dict(sys.modules, {"sentence_transformers": self.module}):
            backend = SentenceTransformerSimilarity()
            scores = backend.score(["Dutch topic"], ["French profile"])

        model = _FakeSentenceTransformer.instances[0]
        self.assertEqual(model.model_name, "BAAI/bge-m3")
        self.assertEqual(model.max_seq_length, MAX_EMBEDDING_SEQUENCE_LENGTH)
        self.assertEqual(scores.shape, (1, 1))
        self.assertEqual(len(model.encode_calls), 2)
        for _, options in model.encode_calls:
            self.assertEqual(options["batch_size"], DEFAULT_EMBEDDING_BATCH_SIZE)
            self.assertTrue(options["normalize_embeddings"])
            self.assertFalse(options["show_progress_bar"])

    def test_existing_shorter_model_limit_is_preserved(self) -> None:
        class ShortModel(_FakeSentenceTransformer):
            def __init__(self, model_name: str):
                super().__init__(model_name)
                self.max_seq_length = 512

        module = types.ModuleType("sentence_transformers")
        module.SentenceTransformer = ShortModel
        with patch.dict(sys.modules, {"sentence_transformers": module}):
            backend = SentenceTransformerSimilarity(max_sequence_length=1_024)

        self.assertEqual(backend.model.max_seq_length, 512)


if __name__ == "__main__":
    unittest.main()
