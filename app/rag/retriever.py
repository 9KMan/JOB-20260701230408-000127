"""Retriever — chunking, storing, and cosine-similarity retrieval.

The :class:`Retriever` is the workhorse of the RAG layer. It owns:

* :func:`chunk_documents` — split long text into overlapping chunks.
* :meth:`Retriever.store_documents` — embed + persist chunks into
  ``source_documents`` with pgvector ``VECTOR(1536)`` column.
* :meth:`Retriever.retrieve` — embed a query and pull the ``top_k``
  closest chunks by cosine distance.

The retriever depends on :class:`~app.rag.embeddings.EmbeddingClient`
for the actual embedding calls, but defers provider construction to
the call site so tests can inject a deterministic stub.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from sqlalchemy import select, text

from app.db import session_scope
from app.models import Document
from app.rag.embeddings import EmbeddingClient, get_default_embedding_client

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_OVERLAP = 200


@dataclass
class RetrievedChunk:
    """A chunk returned from :meth:`Retriever.retrieve`."""

    document_id: uuid.UUID
    chunk_index: int
    text: str
    score: float
    metadata: dict[str, Any]


def chunk_documents(
    text_value: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """Split ``text_value`` into overlapping chunks.

    The chunker is character-based, not token-based. This is a
    deliberate trade-off: tokenization depends on the LLM provider, but
    character counts are predictable. The downstream embedding call
    naturally handles the resulting token-budget variations because
    most embedding models truncate gracefully.

    Rules:

    * ``chunk_size`` must be > 0; we cap it at 100,000.
    * ``overlap`` must be >= 0 and < ``chunk_size``.
    * If the input fits in a single chunk, we return it as-is.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_size > 100_000:
        raise ValueError("chunk_size too large (cap is 100,000)")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be 0 <= overlap < chunk_size")

    text_value = text_value.strip()
    if not text_value:
        return []
    if len(text_value) <= chunk_size:
        return [text_value]

    step = chunk_size - overlap
    chunks: list[str] = []
    for i in range(0, len(text_value), step):
        chunk = text_value[i : i + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        if i + chunk_size >= len(text_value):
            break
    return chunks


class Retriever:
    """Chunk + embed + cosine-retrieve over pgvector."""

    def __init__(
        self,
        embedding_client: Optional[EmbeddingClient] = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_OVERLAP,
    ) -> None:
        self.embedding_client = embedding_client or get_default_embedding_client()
        self.chunk_size = chunk_size
        self.overlap = overlap

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def store_documents(
        self,
        title: str,
        content: str,
        source_type: str = "manual",
        external_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> list[uuid.UUID]:
        """Chunk ``content``, embed each chunk, and persist as :class:`Document` rows.

        Returns the list of created document IDs, one per chunk.
        """
        chunks = chunk_documents(content, self.chunk_size, self.overlap)
        if not chunks:
            return []
        embeddings = self.embedding_client.embed_batch(chunks)
        ids: list[uuid.UUID] = []
        with_metadata = metadata or {}
        with_metadata.setdefault("chunk_size", self.chunk_size)
        with_metadata.setdefault("overlap", self.overlap)

        async def _persist() -> list[uuid.UUID]:
            async with session_scope() as session:
                ids_local: list[uuid.UUID] = []
                for idx, (chunk_text, emb) in enumerate(zip(chunks, embeddings)):
                    doc = Document(
                        source_type=source_type,
                        external_id=(
                            f"{external_id}:{idx}" if external_id else None
                        ),
                        title=title,
                        content_text=chunk_text,
                        content_embedding=emb,
                        extra_metadata={**with_metadata, "chunk_index": idx},
                    )
                    session.add(doc)
                    await session.flush()
                    ids_local.append(doc.id)
                return ids_local

        import asyncio
        ids = asyncio.get_event_loop().run_until_complete(_persist()) \
            if not asyncio.get_event_loop().is_running() else []
        if not ids:
            # Async context — call the coro via a fresh loop.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(asyncio.run, _persist())
                ids = fut.result()
        return ids

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.7,
    ) -> list[RetrievedChunk]:
        """Return the top-k chunks most similar to ``query``.

        ``threshold`` is a cosine-similarity lower bound. Chunks below
        it are dropped. Set ``threshold`` to ``-1.0`` to disable filtering.
        """
        if top_k <= 0:
            return []
        query_vec = self.embedding_client.embed(query)
        return self._retrieve_with_vec(query_vec, top_k, threshold, query=query)

    def _retrieve_with_vec(
        self,
        query_vec: list[float],
        top_k: int,
        threshold: float,
        query: Optional[str] = None,
    ) -> list[RetrievedChunk]:
        """Internal: pgvector cosine-distance query using a precomputed vector."""
        import asyncio

        async def _query() -> list[RetrievedChunk]:
            async with session_scope() as session:
                # pgvector operator: <=> is cosine distance (1 - cos_sim).
                # We filter by distance to keep the implementation portable.
                # The Document model stores content_embedding as Vector(1536).
                vec_literal = "[" + ",".join(f"{v:.8f}" for v in query_vec) + "]"
                stmt = text(
                    """
                    SELECT id,
                           doc_metadata,
                           content_text,
                           (content_embedding <=> :vec) AS distance
                    FROM source_documents
                    WHERE content_embedding IS NOT NULL
                      AND (content_embedding <=> :vec) <= :max_distance
                    ORDER BY content_embedding <=> :vec ASC
                    LIMIT :top_k
                    """
                )
                # Cosine similarity = 1 - distance. Threshold 0.7 (sim)
                # means max distance 0.3.
                max_distance = max(0.0, 1.0 - threshold)
                rows = (
                    await session.execute(
                        stmt,
                        {
                            "vec": vec_literal,
                            "max_distance": max_distance,
                            "top_k": top_k,
                        },
                    )
                ).all()
                results: list[RetrievedChunk] = []
                for row in rows:
                    distance = float(row.distance)
                    score = max(0.0, 1.0 - distance)
                    if score < threshold:
                        continue
                    metadata = row.doc_metadata or {}
                    results.append(
                        RetrievedChunk(
                            document_id=row.id,
                            chunk_index=int(metadata.get("chunk_index", 0)),
                            text=row.content_text or "",
                            score=score,
                            metadata=dict(metadata),
                        )
                    )
                return results

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    return ex.submit(asyncio.run, _query()).result()
            return loop.run_until_complete(_query())
        except RuntimeError:
            return asyncio.run(_query())