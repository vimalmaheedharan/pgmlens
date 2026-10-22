"""Optional OpenTelemetry tracing.

Enabled only when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set *and* the ``otel`` extra is installed
(``pip install "pgmlens-api[otel]"``). Otherwise this is a no-op.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI

log = logging.getLogger("pgmlens.telemetry")


def setup_telemetry(app: FastAPI) -> bool:
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return False
    try:  # pragma: no cover - exercised only when the extra is installed
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        log.warning(
            "OTEL_EXPORTER_OTLP_ENDPOINT is set but the 'otel' extra is not installed; tracing is off."
        )
        return False
    provider = TracerProvider(
        resource=Resource.create({"service.name": "pgmlens-api"})
    )  # pragma: no cover
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))  # pragma: no cover
    trace.set_tracer_provider(provider)  # pragma: no cover
    FastAPIInstrumentor.instrument_app(app)  # pragma: no cover
    return True  # pragma: no cover
