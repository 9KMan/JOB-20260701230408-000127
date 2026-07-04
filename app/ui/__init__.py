"""Admin UI package — server-side rendered FastAPI pages.

Modules:

* :mod:`app.ui.admin` — :class:`APIRouter` that serves the admin HTML
  pages and the Jinja2 templates that render them.

The UI is intentionally minimal: vanilla HTML, a small CSS file, no
client-side JS framework. We pre-render all data from the database and
ship it as HTML, so the only client behavior we need is a single
``POST`` form for the approve/reject buttons on the review page.
"""

from __future__ import annotations

from app.ui.admin import ADMIN_TEMPLATE_DIR, STATIC_DIR, router

__all__ = [
    "ADMIN_TEMPLATE_DIR",
    "STATIC_DIR",
    "router",
]