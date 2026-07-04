"""Observability package — logging, tracing, and eval.

Modules:

* :mod:`app.observability.logging` — loguru JSON formatter +
  secrets-redacting filter.
* :mod:`app.observability.tracing` — OpenTelemetry tracer wrapper.
* :mod:`app.observability.eval` — :class:`EvalFramework` for grading
  agent runs against ground-truth datasets.
"""

from __future__ import annotations

from app.observability.eval import EvalFramework, EvalReport, EvalTaskScore
from app.observability.logging import SecretsFilter, configure_logging, get_logger
from app.observability.tracing import (
    TracerWrapper,
    configure_tracing,
    get_tracer,
)

__all__ = [
    "EvalFramework",
    "EvalReport",
    "EvalTaskScore",
    "SecretsFilter",
    "TracerWrapper",
    "configure_logging",
    "configure_tracing",
    "get_logger",
    "get_tracer",
]