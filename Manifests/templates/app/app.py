import asyncio
import json
import logging
import os
import random
import time
import uuid
from contextvars import ContextVar

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

SERVICE_NAME = os.getenv("SERVICE_NAME", "gateway")
UPSTREAM_URL = os.getenv("UPSTREAM_URL", "")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        span = trace.get_current_span()
        span_context = span.get_span_context()
        trace_id = format(span_context.trace_id, "032x") if span_context.is_valid else None
        span_id = format(span_context.span_id, "016x") if span_context.is_valid else None
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "level": record.levelname.lower(),
            "service": SERVICE_NAME,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get(),
            "trace_id": trace_id,
            "span_id": span_id,
        }
        extra_fields = getattr(record, "extra_fields", {})
        payload.update(extra_fields)
        return json.dumps(payload, separators=(",", ":"))

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger = logging.getLogger("workshop-app")
logger.handlers.clear()
logger.addHandler(handler)
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
logger.propagate = False

# Traces are enabled only when an OTLP endpoint is supplied. This means the
# same application image can be used in the metrics and logging labs without
# emitting traces there.
otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
if otel_endpoint and os.getenv("OTEL_SDK_DISABLED", "false").lower() != "true":
    resource = Resource.create(
        {
            "service.name": SERVICE_NAME,
            "service.version": "1.0.0",
            "deployment.environment": "workshop",
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
else:
    # A no-op provider is installed by default; explicitly touching the API
    # keeps the log formatter safe when traces are disabled.
    pass

app = FastAPI(title=f"Observability Workshop — {SERVICE_NAME}")

REQUESTS = Counter(
    "app_http_requests_total",
    "Total HTTP requests handled by the service",
    ["service", "method", "route", "status"],
)
DURATION = Histogram(
    "app_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["service", "method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)
INFLIGHT = Gauge(
    "app_http_inflight_requests",
    "Current number of in-flight HTTP requests",
    ["service"],
)
QUEUE = Gauge(
    "app_queue_depth",
    "Synthetic work queue depth used for training",
    ["service"],
)
QUEUE.labels(SERVICE_NAME).set(0)



def downstream_url(path: str, slow: bool) -> str:
    if not UPSTREAM_URL:
        return ""
    return f"{UPSTREAM_URL}{path}?delay_ms={800 if slow else 0}"


@app.middleware("http")
async def metrics_and_request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    token = request_id_ctx.set(request_id)
    INFLIGHT.labels(SERVICE_NAME).inc()
    started = time.perf_counter()
    status = "500"
    route = request.url.path
    try:
        response = await call_next(request)
        status = str(response.status_code)
        return response
    finally:
        elapsed = time.perf_counter() - started
        REQUESTS.labels(SERVICE_NAME, request.method, route, status).inc()
        DURATION.labels(SERVICE_NAME, request.method, route).observe(elapsed)
        INFLIGHT.labels(SERVICE_NAME).dec()
        logger.info(
            "request completed",
            extra={
                "extra_fields": {
                    "method": request.method,
                    "path": route,
                    "status": int(status),
                    "duration_ms": round(elapsed * 1000, 2),
                }
            },
        )
        request_id_ctx.reset(token)


# Instrument after the application middleware is registered so request logs can
# read the active server span and emit trace_id/span_id fields.
FastAPIInstrumentor().instrument_app(app, excluded_urls="metrics")
HTTPXClientInstrumentor().instrument()

@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
async def root():
    return {"service": SERVICE_NAME, "message": "observability workshop"}


@app.get("/fail")
async def fail():
    logger.error("intentional failure endpoint triggered")
    return Response(content=json.dumps({"error": "intentional training failure"}), status_code=500, media_type="application/json")


@app.get("/slow")
async def slow():
    await asyncio.sleep(0.8)
    return {"service": SERVICE_NAME, "slow": True}


@app.get("/checkout")
async def checkout(slow: int = 0):
    if SERVICE_NAME != "gateway":
        return {"service": SERVICE_NAME, "note": "checkout is intended for gateway"}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                downstream_url("/process", bool(slow)),
                headers={"X-Request-ID": request_id_ctx.get()},
            )
            response.raise_for_status()
            return {"checkout": "ok", "downstream": response.json()}
    except Exception as exc:
        logger.exception(
            "checkout failed",
            extra={"extra_fields": {"error_type": type(exc).__name__}},
        )
        return Response(
            content=json.dumps({"error": "checkout failed"}),
            status_code=502,
            media_type="application/json",
        )


@app.post("/process")
async def process(delay_ms: int = 0):
    if SERVICE_NAME != "orders":
        return {"service": SERVICE_NAME, "note": "process is intended for orders"}
    if delay_ms:
        await asyncio.sleep(delay_ms / 1000)
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                f"{UPSTREAM_URL}/reserve?delay_ms={delay_ms}",
                headers={"X-Request-ID": request_id_ctx.get()},
            )
            response.raise_for_status()
            return {"orders": "ok", "inventory": response.json()}
    except Exception as exc:
        logger.exception(
            "order processing failed",
            extra={"extra_fields": {"error_type": type(exc).__name__}},
        )
        return Response(
            content=json.dumps({"error": "order processing failed"}),
            status_code=502,
            media_type="application/json",
        )


@app.post("/reserve")
async def reserve(delay_ms: int = 0):
    if SERVICE_NAME != "inventory":
        return {"service": SERVICE_NAME, "note": "reserve is intended for inventory"}
    if delay_ms:
        await asyncio.sleep(delay_ms / 1000)
    if random.random() < float(os.getenv("INVENTORY_ERROR_RATE", "0")):
        logger.error("inventory reservation failed")
        return Response(
            content=json.dumps({"error": "inventory unavailable"}),
            status_code=503,
            media_type="application/json",
        )
    return {"inventory": "reserved"}
