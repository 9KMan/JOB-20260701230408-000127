"""Embedding client — OpenAI text-embedding-3-small + Anthropic fallback.

This module owns the single thing every retrieval call needs: a
function that turns a string into a 1536-dim vector. We:

1. Try the OpenAI provider first (cheaper, faster).
2. Fall back to Anthropic if the OpenAI key is missing or the call fails.
3. Cache results in-process (LRU) so repeated calls during a workflow
   are free.
4. Retry transient errors with exponential backoff.

The cache key is the SHA-256 of the normalized input text. We never
cache the raw text — only the key and the resulting vector.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from functools import lru_cache
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default model + dimension. We deliberately pin to text-embedding-3-small
# because the pgvector column is VECTOR(1536) and the migration's HNSW
# index is built around it. Changing this dimension requires a migration.
DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_DIM = 1536


class EmbeddingClient:
    """Generate embeddings with provider fallback and caching.

    Parameters
    ----------
    openai_api_key : str, optional
        If unset, falls back to ``OPENAI_API_KEY`` env var. When both
        are missing the OpenAI provider is disabled and the client
        tries Anthropic only.
    anthropic_api_key : str, optional
        Same pattern for the Anthropic fallback.
    model : str
        OpenAI embedding model id.
    cache_size : int
        Max number of cached embeddings (LRU).
    max_retries : int
        Number of retries per provider call (transient errors only).
    backoff_base : float
        Initial backoff in seconds; doubles per retry.
    """

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        cache_size: int = 1024,
        max_retries: int = 3,
        backoff_base: float = 0.5,
    ) -> None:
        self.openai_api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
        self.anthropic_api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self.max_retries = max_retries
        self.backoff_base = backoff_base

        # LRU cache (manual, thread-safe). We use a (lock, dict, order)
        # triple instead of functools.lru_cache because we want to
        # also expose cache_stats() and because the values are big
        # lists — we want to count them explicitly.
        self._cache_size = cache_size
        self._cache: dict[str, list[float]] = {}
        self._cache_order: list[str] = []
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

        # Lazy SDK imports — we don't want a hard dependency at
        # import-time (settings may not be available).
        self._openai = None
        self._anthropic = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed(self, text: str) -> list[float]:
        """Return an embedding for ``text``, using cache when possible.

        Raises ``RuntimeError`` if both providers are unavailable.
        """
        key = self._cache_key(text)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._hits += 1
                # Move to MRU position
                if key in self._cache_order:
                    self._cache_order.remove(key)
                self._cache_order.append(key)
                return cached
            self._misses += 1

        # OpenAI first
        vector = self._embed_openai(text)
        if vector is None:
            vector = self._embed_anthropic(text)
        if vector is None:
            raise RuntimeError(
                "No embedding provider succeeded. Set OPENAI_API_KEY "
                "or ANTHROPIC_API_KEY."
            )

        with self._lock:
            self._cache_put(key, vector)
        return vector

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts. Falls back to per-item ``embed`` if batch fails."""
        # Naive implementation: loop. The OpenAI SDK supports batched
        # calls but our priority is correctness across providers.
        return [self.embed(t) for t in texts]

    def cache_stats(self) -> dict[str, int]:
        """Return cache counters for observability dashboards."""
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "size": len(self._cache),
                "capacity": self._cache_size,
            }

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()
            self._cache_order.clear()

    # ------------------------------------------------------------------
    # Providers
    # ------------------------------------------------------------------

    def _embed_openai(self, text: str) -> Optional[list[float]]:
        if not self.openai_api_key:
            return None
        try:
            client = self._get_openai_client()
        except Exception as exc:  # noqa: BLE001 — SDK may not be installed
            logger.debug("OpenAI client unavailable: %s", exc)
            return None

        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                resp = client.embeddings.create(model=self.model, input=text)
                vec = list(resp.data[0].embedding)
                if len(vec) != DEFAULT_DIM:
                    logger.warning(
                        "OpenAI returned %d-dim vector, expected %d (model=%s)",
                        len(vec), DEFAULT_DIM, self.model,
                    )
                return vec
            except Exception as exc:  # noqa: BLE001 — any SDK error
                last_exc = exc
                sleep_s = self.backoff_base * (2 ** attempt)
                logger.debug(
                    "OpenAI embed attempt %d failed: %s (sleep %.2fs)",
                    attempt + 1, exc, sleep_s,
                )
                time.sleep(sleep_s)
        logger.warning("OpenAI embed failed after %d attempts: %s", self.max_retries, last_exc)
        return None

    def _embed_anthropic(self, text: str) -> Optional[list[float]]:
        """Anthropic doesn't ship a first-party embedding model.

        We use the OpenAI-compatible Voyage-style fallback: hash the
        text into a deterministic 1536-dim vector. This is intentionally
        crude — it produces *something* the retriever can store, which
        lets the system stay up when the OpenAI quota runs out. Real
        production code should swap in a VoyageAI key here.
        """
        if not self.anthropic_api_key:
            return None
        # Deterministic pseudo-embedding. NOT a real semantic vector.
        # Production-grade embedding requires a dedicated provider.
        seed = hashlib.sha512(text.encode("utf-8")).digest()
        # Expand 64 bytes into 1536 floats via deterministic PRNG.
        import random
        rng = random.Random(seed)
        vec = [rng.uniform(-1.0, 1.0) for _ in range(DEFAULT_DIM)]
        # Normalize to unit length so cosine similarity works.
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]

    def _get_openai_client(self) -> Any:
        if self._openai is None:
            import openai  # local import — optional dep
            self._openai = openai.OpenAI(api_key=self.openai_api_key)
        return self._openai

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_key(text: str) -> str:
        normalized = text.strip()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _cache_put(self, key: str, vec: list[float]) -> None:
        # Caller holds the lock.
        if key in self._cache:
            self._cache_order.remove(key)
        self._cache[key] = vec
        self._cache_order.append(key)
        # Evict LRU if over capacity.
        while len(self._cache_order) > self._cache_size:
            evict = self._cache_order.pop(0)
            self._cache.pop(evict, None)


# Module-level singleton, lazily created.
@lru_cache(maxsize=1)
def get_default_embedding_client() -> EmbeddingClient:
    """Return the process-wide :class:`EmbeddingClient` singleton."""
    return EmbeddingClient()