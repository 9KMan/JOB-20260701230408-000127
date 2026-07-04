"""Memory layer — episodic, semantic, and working memory.

The :class:`MemoryLayer` exposes a single interface over three storage
tiers:

* **Episodic** — Postgres-backed event log of agent actions. Used for
  replay, debugging, and audit. Each entry has a UUID, a creation
  timestamp, and an arbitrary JSONB payload.
* **Semantic** — pgvector-backed similarity store. Used for "what
  facts do I already know about X". Backed by :class:`Retriever`.
* **Working** — In-process dict with a TTL. Used for short-lived
  scratch state during a single workflow run.

The split mirrors the cognitive-architecture framing in the proposal
(Pillar 3: Memory). Working memory is *not* durable; episodic and
semantic memory are.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from app.db import session_scope
from app.models import Document
from app.rag.embeddings import EmbeddingClient, get_default_embedding_client
from app.rag.retriever import Retriever

DEFAULT_WORKING_TTL_S = 60 * 30  # 30 minutes


@dataclass
class WorkingMemoryEntry:
    """A single (key, value) tuple in working memory."""

    key: str
    value: Any
    expires_at: float
    created_at: float = field(default_factory=time.time)

    def is_expired(self, now: Optional[float] = None) -> bool:
        return (now or time.time()) >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
        }


class MemoryLayer:
    """Three-tier memory store.

    Parameters
    ----------
    embedding_client : EmbeddingClient, optional
        Used by the semantic tier. Defaults to the process-wide
        singleton.
    working_ttl_s : int
        Default TTL (seconds) for working memory entries.
    """

    def __init__(
        self,
        embedding_client: Optional[EmbeddingClient] = None,
        working_ttl_s: int = DEFAULT_WORKING_TTL_S,
    ) -> None:
        self.embedding_client = embedding_client or get_default_embedding_client()
        self.retriever = Retriever(embedding_client=self.embedding_client)
        self.working_ttl_s = working_ttl_s
        self._working: dict[str, WorkingMemoryEntry] = {}
        self._working_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Working memory (in-process, TTL)
    # ------------------------------------------------------------------

    def working_set(self, key: str, value: Any, ttl_s: Optional[int] = None) -> None:
        ttl = ttl_s if ttl_s is not None else self.working_ttl_s
        with self._working_lock:
            self._working[key] = WorkingMemoryEntry(
                key=key,
                value=value,
                expires_at=time.time() + ttl,
            )

    def working_get(self, key: str, default: Any = None) -> Any:
        with self._working_lock:
            entry = self._working.get(key)
            if entry is None:
                return default
            if entry.is_expired():
                del self._working[key]
                return default
            return entry.value

    def working_delete(self, key: str) -> bool:
        with self._working_lock:
            return self._working.pop(key, None) is not None

    def working_clear(self) -> None:
        with self._working_lock:
            self._working.clear()

    def working_keys(self) -> list[str]:
        """Return non-expired keys."""
        now = time.time()
        with self._working_lock:
            expired = [k for k, v in self._working.items() if v.is_expired(now)]
            for k in expired:
                self._working.pop(k, None)
            return list(self._working.keys())

    def working_size(self) -> int:
        """Return the count of non-expired entries."""
        return len(self.working_keys())

    # ------------------------------------------------------------------
    # Semantic memory (pgvector)
    # ------------------------------------------------------------------

    def remember_fact(
        self,
        text: str,
        source: str = "user",
        metadata: Optional[dict[str, Any]] = None,
    ) -> list[uuid.UUID]:
        """Store a fact in semantic memory.

        Returns the list of document IDs created (one per chunk).
        """
        return self.retriever.store_documents(
            title=f"fact:{source}",
            content=text,
            source_type=f"memory:{source}",
            metadata=metadata or {},
        )

    def recall(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.7,
    ) -> list[Any]:
        """Return the top-k facts most similar to ``query``."""
        return self.retriever.retrieve(query, top_k=top_k, threshold=threshold)

    # ------------------------------------------------------------------
    # Episodic memory (Postgres event log)
    # ------------------------------------------------------------------

    def record_episode(
        self,
        event_type: str,
        payload: dict[str, Any],
        agent_id: Optional[uuid.UUID] = None,
        task_id: Optional[uuid.UUID] = None,
    ) -> uuid.UUID:
        """Append an episode to the audit log.

        We reuse the :class:`Document` model as an event store: each
        episode is a row with ``source_type="episode"`` and the event
        payload stored in ``extra_metadata``. This avoids creating a
        new table while keeping the durable audit trail queryable.

        Returns the episode's document id.
        """
        meta = {
            "event_type": event_type,
            "agent_id": str(agent_id) if agent_id else None,
            "task_id": str(task_id) if task_id else None,
            "occurred_at": time.time(),
            "payload": payload,
        }
        title = f"episode:{event_type}"

        import asyncio

        async def _insert() -> uuid.UUID:
            async with session_scope() as session:
                doc = Document(
                    source_type="episode",
                    external_id=None,
                    title=title,
                    content_text=json.dumps(payload, default=str)[:8000],
                    content_embedding=None,
                    extra_metadata=meta,
                )
                session.add(doc)
                await session.flush()
                return doc.id

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    return ex.submit(asyncio.run, _insert()).result()
            return loop.run_until_complete(_insert())
        except RuntimeError:
            return asyncio.run(_insert())

    def list_episodes(
        self,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return recent episodes (optionally filtered by event_type)."""
        import asyncio

        async def _query() -> list[dict[str, Any]]:
            async with session_scope() as session:
                from sqlalchemy import select
                stmt = select(Document).where(Document.source_type == "episode")
                if event_type is not None:
                    stmt = stmt.where(
                        Document.extra_metadata["event_type"].astext == event_type
                    )
                stmt = stmt.order_by(Document.fetched_at.desc()).limit(limit)
                rows = (await session.execute(stmt)).scalars().all()
                return [
                    {
                        "id": str(r.id),
                        "title": r.title,
                        "metadata": r.extra_metadata,
                        "fetched_at": r.fetched_at,
                    }
                    for r in rows
                ]

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    return ex.submit(asyncio.run, _query()).result()
            return loop.run_until_complete(_query())
        except RuntimeError:
            return asyncio.run(_query())