"""Local-only restricted entrypoint for the recovered Sentinel demo."""
from fastapi.responses import JSONResponse
from app.main import app as original_app

BLOCKED_PATHS = frozenset({"/seed", "/login"})
BLOCKED_PREFIXES = ("/gateway",)

async def app(scope, receive, send):
    if scope["type"] == "http":
        path = scope.get("path", "")
        if path in BLOCKED_PATHS or any(path.startswith(p) for p in BLOCKED_PREFIXES):
            response = JSONResponse({"detail": "Disabled in team demo"}, status_code=404)
            return await response(scope, receive, send)
    return await original_app(scope, receive, send)
