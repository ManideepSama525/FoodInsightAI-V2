from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.app.api.router import api_router
from backend.app.core.config import get_settings
from backend.app.core.errors import DomainError, domain_error_handler
from backend.app.db.session import engine
from backend.app.services.knowledge_graph import knowledge_graph

settings = get_settings()
production = settings.app_env == "production"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
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

app.add_exception_handler(DomainError, domain_error_handler)


@app.middleware("http")
async def security_headers(request, call_next):
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