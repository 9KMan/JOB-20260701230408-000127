"""Document ORM model — RAG source documents with pgvector embeddings.

Stores ingested source documents (``source_documents`` table) along
with their vector embedding for semantic search. The
``content_embedding`` column uses pgvector's ``vector(1536)`` type
and is indexed via HNSW for sub-100ms similarity search at scale.

The Phase 4 plan calls the embedding column
``content_embedding`` on the ``source_documents`` table; we follow
that name exactly so the migration SQL matches the ORM.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import JSONBDictType as JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A source document ingested into the RAG pipeline.

    Attributes:
        id: UUID PK.
        source_type: Logical source identifier (e.g. ``"jira"``,
            ``"confluence"``, ``"upload"``). Used together with
            ``external_id`` for idempotent ingest.
        external_id: Stable identifier within ``source_type``
            (e.g. the upstream document ID).
        title: Human-readable title.
        content_text: Extracted plain-text content. Large enough to
            be the chunking source but not the chunked vectors (those
            live in a separate ``document_chunks`` table — see the
            Phase 4 plan).
        content_embedding: 1536-dimensional vector embedding of
            ``content_text`` (or a representative summary). NULL until
            the embedding step has run.
        extra_metadata: JSON blob of arbitrary document-level metadata
            (author, tags, classification, etc.). Stored under the
            ``metadata`` column on disk but exposed as ``extra_metadata``
            in Python (since ``metadata`` is reserved by SQLAlchemy).
        fetched_at: When the document was fetched from its source.
    """

    __tablename__ = "source_documents"

    source_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    content_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=text("''"),
    )
    content_embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(dim=1536),
        nullable=True,
    )
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    fetched_at: Mapped[datetime] = mapped_column(
        # Uses the default from TimestampMixin via column definition
        # in app.models.base — we re-declare it here as ``fetched_at``
        # to keep the API distinct.
        nullable=False,
    )

    __table_args__ = (
        # (source_type, external_id) must be unique for idempotent
        # ingestion — the same source doc cannot be ingested twice.
        Index(
            "ux_source_documents_source_type_external_id",
            "source_type",
            "external_id",
            unique=True,
        ),
        # HNSW index for cosine-distance similarity search. Created
        # in the migration so that the ``vector_cosine_ops`` opclass
        # is referenced from the CREATE INDEX statement (SQLAlchemy
        # can't easily emit this directly, so it lives in 001_initial.sql).
        Index(
            "ix_source_documents_content_embedding_hnsw",
            "content_embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"content_embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Document id={self.id} source={self.source_type}:"
            f"{self.external_id} title={self.title!r}>"
        )


__all__ = ["Document"]