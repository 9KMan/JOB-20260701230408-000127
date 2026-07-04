"""SQLAlchemy declarative base + common mixins used across all ORM models.

We use SQLAlchemy 2.0 typed-Mapped style with ``DeclarativeBase``. All
ORM models in :mod:`app.models` inherit from :class:`Base` here, and
the mixins provide:

* ``TimestampMixin`` — auto-managed ``created_at`` / ``updated_at``.
* ``UUIDPrimaryKeyMixin`` — server-side ``gen_random_uuid()`` PK.

A custom ``JSONBDict``/``JSONBList`` type wrapper normalizes JSONB
columns so empty dicts/lists are stored consistently on PostgreSQL.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    """Return current UTC time (timezone-aware).

    All DateTime columns in this project are stored with
    ``timezone=True`` so they round-trip as aware datetimes.
    """
    return datetime.now(timezone.utc)


# PostgreSQL JSONB with a SQLite-compatible JSON fallback. This lets
# the test suite use an in-memory SQLite database without a Postgres
# instance while still producing JSONB columns in production.
JSONBDictType = JSONB().with_variant(JSON(), "sqlite")
JSONBListType = JSONB().with_variant(JSON(), "sqlite")


class Base(DeclarativeBase):
    """Project-wide declarative base.

    The ``type_annotation_map`` lets a column declared as
    ``Mapped[uuid.UUID]`` map to a PostgreSQL UUID automatically.
    """

    type_annotation_map = {
        uuid.UUID: UUID(as_uuid=True),
        dict[str, Any]: JSONBDictType,
        list[Any]: JSONBListType,
    }


class TimestampMixin:
    """Adds ``created_at`` and ``updated_at`` to a model.

    ``updated_at`` is bumped by SQLAlchemy on every UPDATE.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """Adds a server-side default UUID primary key column.

    Uses Postgres' ``gen_random_uuid()`` so the PK is generated in the
    database (rather than in Python), which lets us insert with
    ``RETURNING`` without first generating a UUID in the client.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default="gen_random_uuid()",
    )


__all__ = ["Base", "TimestampMixin", "UUIDPrimaryKeyMixin", "utc_now"]