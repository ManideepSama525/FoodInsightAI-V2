import unittest
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.integrations.sentinel_ip_containment_middleware import (
    SentinelIPContainmentMiddleware,
)
from backend.app.models.security_ip_block import SecurityIPBlock
from backend.app.services.security_ip_containment import (
    create_temporary_ip_block,
)


class SyntheticPeer:
    """Test-only ASGI wrapper; never installed in the real application."""
    def __init__(self, app):
        self.app = app
        self.peer = "127.0.0.1"

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope = dict(scope)
            scope["client"] = (self.peer, 43210)
        await self.app(scope, receive, send)


class Stage3Tests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SecurityIPBlock.__table__.create(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.clock = [datetime(2026, 11, 19, 12, 0, 0)]
        self.app = FastAPI()

        @self.app.get("/food-scan")
        def food_scan():
            return {"food_scan": "working"}

        @self.app.get("/nutrition")
        def nutrition():
            return {"nutrition": "working"}

        protected = SentinelIPContainmentMiddleware(
            self.app,
            session_factory=self.Session,
            now_factory=lambda: self.clock[0],
        )
        self.peer = SyntheticPeer(protected)
        self.client = TestClient(self.peer)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.engine.dispose()

    def block(self, source_ip="198.51.100.42", duration=30):
        with self.Session() as db:
            return create_temporary_ip_block(
                db,
                action_id=str(uuid4()),
                incident_id="INC-900003",
                source_ip=source_ip,
                duration_seconds=duration,
                reason="Isolated middleware enforcement simulation",
                now=self.clock[0],
            )

    def get(self, peer="198.51.100.42", path="/food-scan", headers=None):
        self.peer.peer = peer
        return self.client.get(path, headers=headers or {})

    def test_unblocked_synthetic_source_allowed(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["food_scan"], "working")

    def test_active_block_rejected(self):
        self.block()
        response = self.get()
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.json()["blocked"])

    def test_expiry_restores_access(self):
        self.block()
        self.assertEqual(self.get().status_code, 403)
        self.clock[0] += timedelta(seconds=31)
        self.assertEqual(self.get().status_code, 200)

    def test_exact_expiry_restores_access(self):
        self.block()
        self.clock[0] += timedelta(seconds=30)
        self.assertEqual(self.get().status_code, 200)

    def test_unblocked_other_source(self):
        self.block("198.51.100.42")
        self.assertEqual(
            self.get("203.0.113.99").status_code, 200
        )

    def test_loopback_unaffected(self):
        self.block()
        self.assertEqual(
            self.get("127.0.0.1").status_code, 200
        )

    def test_docker_gateway_unaffected(self):
        self.block()
        self.assertEqual(
            self.get("172.17.0.1").status_code, 200
        )

    def test_lan_ip_unaffected(self):
        self.block()
        self.assertEqual(
            self.get("192.168.1.10").status_code, 200
        )

    def test_public_ip_unaffected(self):
        self.block()
        self.assertEqual(
            self.get("8.8.8.8").status_code, 200
        )

    def test_forwarded_header_cannot_bypass_block(self):
        self.block()
        response = self.get(
            "198.51.100.42",
            headers={"X-Forwarded-For": "127.0.0.1"},
        )
        self.assertEqual(response.status_code, 403)

    def test_forwarded_header_cannot_create_blocked_identity(self):
        self.block()
        response = self.get(
            "127.0.0.1",
            headers={"X-Forwarded-For": "198.51.100.42"},
        )
        self.assertEqual(response.status_code, 200)

    def test_nutrition_route_unaffected_for_real_source(self):
        self.block()
        response = self.get(
            "192.168.1.10",
            path="/nutrition",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["nutrition"], "working")

    def test_undeliverable_database_lookup_fails_open(self):
        def broken_session():
            raise RuntimeError("Simulated database outage")

        protected = SentinelIPContainmentMiddleware(
            self.app,
            session_factory=broken_session,
        )
        peer = SyntheticPeer(protected)
        peer.peer = "198.51.100.42"
        with TestClient(peer) as client:
            response = client.get("/food-scan")
        self.assertEqual(response.status_code, 200)

    def test_expired_audit_record_remains(self):
        self.block()
        self.clock[0] += timedelta(seconds=31)
        self.assertEqual(self.get().status_code, 200)
        with self.Session() as db:
            rows = db.scalars(select(SecurityIPBlock)).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].result, "SUCCESS")


if __name__ == "__main__":
    unittest.main()
