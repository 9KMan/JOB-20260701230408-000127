"""OpenTelemetry tracing wrapper.

The wrapper keeps the rest of the codebase from importing OpenTelemetry
directly. Two reasons:

1. **Stable surface area.** The wrapper exposes only ``get_tracer``,
   ``configure_tracing``, and ``TracerWrapper`` — anything else
   means a refactor is needed before swapping providers.
2. **Soft dependency.** If the OTel SDK isn't installed
   (``opentelemetry-sdk``), the wrapper silently no-ops instead of
   crashing the orchestrator.

In production we expect to point the OTel exporter at a Langfuse or
Honeycomb collector via ``OTEL_EXPORTER_OTLP_ENDPOINT``.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator, Optional


class _NoopSpan:
    """Fallback span used when OpenTelemetry isn't installed."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def record_exception(self, exc: BaseException) -> None:
        pass

    def set_status(self, status: Any) -> None:
        pass

    def end(self) -> None:
        pass

    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class _NoopTracer:
    def start_as_current_span(self, name: str, **kwargs: Any) -> _NoopSpan:
        return _NoopSpan()


class TracerWrapper:
    """Thin wrapper around the global OpenTelemetry tracer.

    The wrapper is intentionally *not* a singleton — call sites use
    :func:`get_tracer` instead, which memoizes the underlying OTel
    tracer on first use.
    """

    def __init__(self, tracer: Any) -> None:
        self._tracer = tracer

    def start_span(self, name: str, **attrs: Any) -> Any:
        """Start a new span and bind initial attributes."""
        span = self._tracer.start_as_current_span(name)
        # We have to set attrs *after* entering the context — but the
        # wrapper hides that complexity via the `span` context below.
        for k, v in attrs.items():
            span.set_attribute(k, v)
        return span

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[Any]:
        """Context manager: ``with tracer.span('foo') as s: ...``"""
        with self._tracer.start_as_current_span(name) as span:
            for k, v in attrs.items():
                span.set_attribute(k, v)
            yield span

    # ------------------------------------------------------------------
    # Decorators / helpers
    # ------------------------------------------------------------------

    def trace_call(self, name: Optional[str] = None) -> Any:
        """Decorator: wrap a function call in a span."""
        def decorator(fn: Any) -> Any:
            span_name = name or fn.__qualname__

            if _IS_ASYNC(fn):
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    with self.span(span_name) as span:
                        try:
                            result = await fn(*args, **kwargs)
                            span.set_attribute("status", "ok")
                            return result
                        except Exception as exc:
                            span.record_exception(exc)
                            span.set_attribute("status", "error")
                            raise
                return async_wrapper

            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                with self.span(span_name) as span:
                    try:
                        result = fn(*args, **kwargs)
                        span.set_attribute("status", "ok")
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_attribute("status", "error")
                        raise
            return sync_wrapper
        return decorator


def _IS_ASYNC(fn: Any) -> bool:
    import inspect
    return inspect.iscoroutinefunction(fn)


def configure_tracing(
    service_name: str = "agentic-ai-platform",
    otlp_endpoint: Optional[str] = None,
) -> bool:
    """Best-effort OTel SDK configuration.

    Returns ``True`` if OTel was configured, ``False`` if the SDK is
    unavailable. We don't crash on missing dependencies — observability
    is opt-in.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )
    except ImportError:
        return False

    endpoint = otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
            exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except ImportError:
            # No HTTP exporter — fall back to console for dev visibility.
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        # Local dev: just write spans to stderr so dev still gets visibility.
        try:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        except Exception:  # noqa: BLE001 — observability must never crash startup
            pass

    trace.set_tracer_provider(provider)
    return True


_TRACER_INSTANCE: Optional[TracerWrapper] = None


def get_tracer(name: str = "agentic-ai-platform") -> TracerWrapper:
    """Return the process-wide :class:`TracerWrapper`.

    The underlying OTel tracer is memoized — subsequent calls reuse the
    same provider, so we don't re-instrument the world.
    """
    global _TRACER_INSTANCE
    if _TRACER_INSTANCE is None:
        try:
            from opentelemetry import trace
            tracer = trace.get_tracer(name)
        except ImportError:
            tracer = _NoopTracer()
        _TRACER_INSTANCE = TracerWrapper(tracer)
    return _TRACER_INSTANCE


def reset_tracer() -> None:
    """Drop the cached tracer (tests)."""
    global _TRACER_INSTANCE
    _TRACER_INSTANCE = None