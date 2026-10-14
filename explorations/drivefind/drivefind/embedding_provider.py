"""Turns searchable text into vectors for semantic similarity search.

VoyageEmbeddingProvider is the real path (needs VOYAGE_API_KEY, calls
api.voyageai.com directly over HTTP — no SDK dependency needed for a single
endpoint). FakeEmbeddingProvider is a deterministic, offline stand-in used to
exercise the store/search logic without any network access or API key.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

import httpx
import numpy as np

from . import config

VOYAGE_EMBEDDINGS_URL = "https://api.voyageai.com/v1/embeddings"
FAKE_EMBEDDING_DIM = 256


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class VoyageEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        api_key = api_key or config.VOYAGE_API_KEY
        if not api_key:
            raise RuntimeError("VOYAGE_API_KEY is not set.")
        self._api_key = api_key
        self._model = model or config.VOYAGE_MODEL

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = httpx.post(
            VOYAGE_EMBEDDINGS_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"input": texts, "model": self._model},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return [item["embedding"] for item in data]


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic bag-of-words hashing embedding — for offline dev/tests only."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = np.zeros(FAKE_EMBEDDING_DIM, dtype=np.float64)
        for word in text.lower().split():
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % FAKE_EMBEDDING_DIM
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec.tolist()
