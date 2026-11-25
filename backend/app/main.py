from collections import deque
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.app.api.router import api_router
from backend.app.core.config import get_settings
from backend.app.core.errors import DomainError, domain_error_handler
from backend.app.db.session import engine
from backend.app.db.init_db import initialize_database
from backend.app.services.knowledge_graph import knowledge_graph
from backend.app.integrations.security_indicators import (
    MAX_INSPECT_BODY_BYTES,
    detect_payload_indicators,
    should_capture_request_body,
)
from backend.app.integrations.sentinel_xdr import (
    publish_payload_security_event,
    publish_request_event,
    start_telemetry,
    stop_telemetry,
)

settings = get_settings()
production = settings.app_env == "production"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    initialize_database()
    start_telemetry()
    try:
        yield
    finally:
        stop_telemetry()
        knowledge_graph.close()


app = FastAPI(
    lifespan=lifespan,
    title=settings.app_name,
    version="0.2.0",
    description="Food recognition, nutrition intelligence and recipe analysis API.",
    docs_url=None if production else "/docs",
    redoc_url=None if production else "/redoc",
    openapi_url=None if production else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


# SENTINEL_SYNTHETIC_IP_CONTAINMENT_STAGE4
# Explicit opt-in only. Production FoodInsightAI behavior is unchanged
# unless the operator deliberately enables this isolated test mechanism.
import os as _sentinel_containment_os

if (
    _sentinel_containment_os.getenv(
        "SENTINEL_SYNTHETIC_IP_CONTAINMENT_ENABLED", ""
    ) == "1"
):
    from backend.app.integrations.sentinel_ip_containment_middleware import (
        SentinelIPContainmentMiddleware,
    )
    app.add_middleware(SentinelIPContainmentMiddleware)

app.add_exception_handler(DomainError, domain_error_handler)


@app.middleware("http")
async def security_headers(request, call_next):
    # Buffer only bounded JSON/form bodies so inspection happens before routing.
    # Every buffered ASGI message is replayed unchanged to the downstream app.
    captured_body = bytearray()
    body_overflow = False
    content_length = request.headers.get("content-length")
    content_type = request.headers.get("content-type", "")
    capture_body = should_capture_request_body(
        request.url.path,
        content_type,
        content_length,
    )

    if capture_body:
        original_receive = request._receive
        replay_messages = deque()
        total_body_bytes = 0

        while True:
            message = await original_receive()
            replay_messages.append(message)
            if message.get("type") != "http.request":
                break

            chunk = message.get("body", b"")
            if total_body_bytes + len(chunk) > MAX_INSPECT_BODY_BYTES:
                body_overflow = True
                break

            captured_body.extend(chunk)
            total_body_bytes += len(chunk)
            if not message.get("more_body", False):
                break

        async def replay_receive():
            if replay_messages:
                return replay_messages.popleft()
            return await original_receive()

        request._receive = replay_receive

    # Detection is performed before call_next, so matched requests never reach
    # an API endpoint. On oversized bodies, path/query inspection still applies.
    try:
        indicators = detect_payload_indicators(
            path=request.url.path,
            query=request.url.query,
            body=b"" if body_overflow else bytes(captured_body),
        )
    except Exception:
        # Inspection failure must not break legitimate food-analysis requests.
        indicators = []

    blocked = bool(indicators)
    if blocked:
        response = JSONResponse(
            status_code=403,
            content={"detail": "Request blocked by security policy."},
        )
    else:
        response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()"
    )

    if request.url.path in {"/docs", "/redoc"}:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "font-src 'self' data: https://cdn.jsdelivr.net; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
    else:
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )

    if production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    if not blocked:
        try:
            publish_request_event(
                request,
                response.status_code,
                settings.api_v1_prefix,
            )
        except Exception:
            # Security telemetry must never break food-analysis requests.
            pass
    else:
        for indicator in indicators:
            try:
                publish_payload_security_event(
                    request,
                    response.status_code,
                    indicator,
                    action_taken="BLOCK_REQUEST",
                )
            except Exception:
                # Enforcement remains local even if Sentinel telemetry is offline.
                pass

    return response
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "status": "operational",
        "docs": "/docs" if not production else "disabled",
    }


@app.get("/api/v1/system/readiness", tags=["system"])
def readiness() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Database is not ready.",
        ) from exc

    graph_status = "disabled"
    if knowledge_graph.enabled:
        if not knowledge_graph.verify():
            raise HTTPException(
                status_code=503,
                detail="Knowledge graph is not ready.",
            )
        graph_status = "connected"

    return {
        "status": "ready",
        "database": "connected",
        "knowledge_graph": graph_status,
    }