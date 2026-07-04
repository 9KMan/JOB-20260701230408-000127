"""Logging setup — loguru with JSON output and secrets redaction.

We standardize on loguru because:

* Single import surface, no logger-per-module boilerplate.
* Built-in structured sinks (JSON file, stderr, syslog).
* Easy to add custom filters via ``logger.configure``.

The :class:`SecretsFilter` is the safety net: every record is scanned
for ``api_key``/``token``/``secret``/``password``/``webhook`` and any
matched substring is replaced with ``***REDACTED***``. The regex is
intentionally case-insensitive and tolerates underscores / hyphens /
colons (the typical separators in env-var dumps).
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Optional

from loguru import logger as _loguru_logger

# Match keys like:
#   api_key=abc123
#   api-key: "abc123"
#   SECRET_TOKEN -> xyz
#   webhook_url=https://...
# and any non-word chars after the key.
_SECRETS_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|webhook)\W*\S+",
)


class SecretsFilter:
    """loguru filter that redacts secret-shaped substrings from records."""

    def __init__(self, replacement: str = "***REDACTED***") -> None:
        self.replacement = replacement

    def __call__(self, record: dict[str, Any]) -> bool:
        """Scan every string field of the record and redact matches.

        Returns ``True`` so the record is not dropped — redaction only
        replaces the offending substring.
        """
        for key in ("message", "msg", "details", "extra"):
            value = record.get(key)
            if isinstance(value, str):
                record[key] = _SECRETS_RE.sub(
                    lambda m: m.group(1) + self.replacement, value
                )
            elif isinstance(value, dict):
                record[key] = _scrub_dict(value, self.replacement)
        # Top-level extras often carry request/response data.
        if "extra" in record and isinstance(record["extra"], dict):
            record["extra"] = _scrub_dict(record["extra"], self.replacement)
        return True


def _scrub_dict(d: dict[str, Any], replacement: str) -> dict[str, Any]:
    """Return a copy of ``d`` with secret-shaped values redacted."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, str):
            out[k] = _SECRETS_RE.sub(
                lambda m: m.group(1) + replacement, v
            )
        elif isinstance(v, dict):
            out[k] = _scrub_dict(v, replacement)
        elif isinstance(v, list):
            out[k] = [_scrub_dict(x, replacement) if isinstance(x, dict)
                      else (_SECRETS_RE.sub(
                          lambda m: m.group(1) + replacement, x
                      ) if isinstance(x, str) else x)
                      for x in v]
        else:
            out[k] = v
    return out


def _json_sink(message: Any) -> None:
    """Sink that writes each log record as a single JSON line to stderr."""
    record = message.record
    payload = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "message": record["message"],
        "module": record["name"],
        "function": record["function"],
        "line": record["line"],
        "extra": record.get("extra", {}),
    }
    if record["exception"] is not None:
        payload["exception"] = str(record["exception"])
    sys.stderr.write(json.dumps(payload, default=str) + "\n")
    sys.stderr.flush()


def configure_logging(
    level: str = "INFO",
    json_output: bool = True,
    redact_secrets: bool = True,
) -> None:
    """Configure the global loguru logger.

    Parameters
    ----------
    level : str
        One of ``"DEBUG"``, ``"INFO"``, ``"WARNING"``, ``"ERROR"``.
    json_output : bool
        When ``True`` (default), emit one JSON object per line. When
        ``False``, emit the human-readable loguru format.
    redact_secrets : bool
        When ``True`` (default), install the :class:`SecretsFilter`.
    """
    # Reset any existing handlers so reconfiguration is deterministic.
    _loguru_logger.remove()

    # loguru's add() takes a single filter, not a list. We compose
    # multiple filters via a single callable that runs them in order.
    filter_callable: Optional[Any] = None
    if redact_secrets:
        filter_callable = SecretsFilter()

    if json_output:
        _loguru_logger.add(
            _json_sink,
            level=level.upper(),
            filter=filter_callable,
            backtrace=False,
            diagnose=False,
        )
    else:
        _loguru_logger.add(
            sys.stderr,
            level=level.upper(),
            filter=filter_callable,
            backtrace=False,
            diagnose=False,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
                "<level>{level: <8}</level> "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                "<level>{message}</level>"
            ),
        )


def get_logger(name: Optional[str] = None) -> Any:
    """Return a loguru logger bound to ``name`` (or the default one)."""
    if name:
        return _loguru_logger.bind(component=name)
    return _loguru_logger