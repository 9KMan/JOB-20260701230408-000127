"""Retrieval-augmented generation (RAG) package.

Modules:

* :mod:`app.rag.embeddings` — :class:`EmbeddingClient` (OpenAI +
  Anthropic fallback) with retry + LRU cache.
* :mod:`app.rag.retriever` — :class:`Retriever` for chunking, storing,
  and cosine-similarity retrieval over pgvector.
* :mod:`app.rag.memory` — :class:`MemoryLayer` with three memory tiers:
  episodic (Postgres), semantic (pgvector), working (in-process TTL).
"""

from __future__ import annotations

from app.rag.embeddings import EmbeddingClient
from app.rag.memory import MemoryLayer, WorkingMemoryEntry
from app.rag.retriever import RetrievedChunk, Retriever, chunk_documents

__all__ = [
    "EmbeddingClient",
    "MemoryLayer",
    "RetrievedChunk",
    "Retriever",
    "WorkingMemoryEntry",
    "chunk_documents",
]