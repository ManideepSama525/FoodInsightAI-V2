"""Isolated Sentinel synthetic-IP containment ASGI middleware.

Not registered in FoodInsightAI's live application in this stage.
Never trusts X-Forwarded-For, Forwarded, or client-controlled headers.
Does not modify a firewall and never blocks real network addresses.
"""
import logging
from datetime import datetime, timezone

from starlette.responses import JSONResponse

from backend.app.db.session import SessionLocal
from backend.app.services.security_ip_containment import (
    is_test_ip_blocked,
    validate_test_source_ip,
)

logger = logging.getLogger("foodinsightai.sentinel_containment")


class SentinelIPContainmentMiddleware:
    def __init__(
        self,
        app,
        session_factory=None,
        now_factory=None,
    ):
        self.app = app
        self.session_factory = (
            session_factory if session_factory is not None else SessionLocal
        )
        self.now_factory = (
            now_factory if now_factory is not None
            else lambda: datetime.now(timezone.utc)
        )

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        source_ip = client[0] if client else None

        # This validation is intentionally restricted to RFC 5737
        # documentation addresses. No database access is performed
        # for loopback, LAN, Docker, public, or unknown sources.
        try:
            source_ip = validate_test_source_ip(source_ip)
        except ValueError:
            await self.app(scope, receive, send)
            return

        blocked = False
        db = None

        try:
            db = self.session_factory()
            blocked = is_test_ip_blocked(
                db,
                source_ip,
                now=self.now_factory(),
            )
        except Exception:
            # Isolated test containment must not disrupt food services
            # if the security database lookup is unavailable.
            logger.exception(
                "Sentinel synthetic containment lookup failed; "
                "allowing request to proceed."
            )
            blocked = False
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    logger.exception(
                        "Sentinel containment session close failed."
                    )

        if blocked:
            response = JSONResponse(
                status_code=403,
                content={
                    "detail": "Temporarily blocked by Sentinel-XDR.",
                    "blocked": True,
                    "enforcement_scope": "SYNTHETIC_TEST_IP_ONLY",
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
