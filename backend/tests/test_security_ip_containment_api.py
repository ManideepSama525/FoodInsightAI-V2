import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db.session import get_db
from backend.app.models.security_ip_block import SecurityIPBlock
from backend.app.api.routes.sentinel_response import router
from backend.app.services.security_ip_containment import is_test_ip_blocked


class Stage2Tests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SecurityIPBlock.__table__.create(self.engine)

        self.db = Session(self.engine)
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api/v1")

        def override_db():
            yield self.db

        self.app.dependency_overrides[get_db] = override_db
        self.environment = patch.dict(
            os.environ,
            {"SENTINEL_RESPONSE_TOKEN": "stage2-test-secret"},
        )
        self.environment.start()
        self.client = TestClient(self.app)
        self.url = "/api/v1/internal/sentinel/temporary-ip-block"

    def tearDown(self):
        self.client.close()
        self.environment.stop()
        self.db.close()
        self.engine.dispose()

    def payload(self, **changes):
        item = {
            "action_id": str(uuid4()),
            "incident_id": "INC-900002",
            "source_ip": "198.51.100.42",
            "duration_seconds": 30,
            "reason": "Controlled synthetic attack simulation",
        }
        item.update(changes)
        return item

    def post(self, payload, token="stage2-test-secret"):
        headers = (
            {"X-Sentinel-Response-Token": token}
            if token is not None else {}
        )
        return self.client.post(
            self.url,
            json=payload,
            headers=headers,
        )

    def test_requires_authentication(self):
        for token in (None, "incorrect-token"):
            with self.subTest(token=token):
                response = self.post(self.payload(), token)
                self.assertEqual(response.status_code, 401)

        self.assertEqual(
            self.db.query(SecurityIPBlock).count(), 0
        )

    def test_authenticated_block_persists(self):
        response = self.post(self.payload())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["accepted"])
        self.assertFalse(body["duplicate"])
        self.assertTrue(body["active"])
        self.assertFalse(body["firewall_modified"])
        self.assertFalse(body["middleware_enforcement_verified"])
        self.assertEqual(
            self.db.query(SecurityIPBlock).count(), 1
        )

    def test_duplicate_action_is_idempotent(self):
        item = self.payload()
        first = self.post(item)
        second = self.post(item)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["duplicate"])
        self.assertEqual(
            self.db.query(SecurityIPBlock).count(), 1
        )

    def test_reused_action_cannot_change_target(self):
        item = self.payload()
        self.assertEqual(self.post(item).status_code, 200)
        item["source_ip"] = "203.0.113.42"
        self.assertEqual(self.post(item).status_code, 422)
        self.assertEqual(
            self.db.query(SecurityIPBlock).count(), 1
        )

    def test_reused_action_cannot_extend_duration(self):
        item = self.payload()
        self.assertEqual(self.post(item).status_code, 200)
        item["duration_seconds"] = 300
        self.assertEqual(self.post(item).status_code, 422)

    def test_private_and_loopback_addresses_rejected(self):
        for address in (
            "127.0.0.1",
            "172.17.0.1",
            "192.168.1.20",
            "10.0.0.10",
        ):
            with self.subTest(address=address):
                self.assertEqual(
                    self.post(
                        self.payload(source_ip=address)
                    ).status_code,
                    422,
                )

    def test_public_address_rejected(self):
        self.assertEqual(
            self.post(
                self.payload(source_ip="8.8.8.8")
            ).status_code,
            422,
        )

    def test_unknown_fields_rejected(self):
        self.assertEqual(
            self.post(
                self.payload(automation_authorized=True)
            ).status_code,
            422,
        )

    def test_duration_bounds_enforced(self):
        for duration in (0, 4, 301, -1):
            with self.subTest(duration=duration):
                self.assertEqual(
                    self.post(
                        self.payload(duration_seconds=duration)
                    ).status_code,
                    422,
                )

    def test_expiration_and_audit_persistence(self):
        response = self.post(self.payload())
        self.assertEqual(response.status_code, 200)

        record = self.db.scalar(select(SecurityIPBlock))
        self.assertTrue(is_test_ip_blocked(
            self.db,
            record.source_ip,
            record.created_at + timedelta(seconds=5),
        ))
        self.assertFalse(is_test_ip_blocked(
            self.db,
            record.source_ip,
            record.expires_at,
        ))
        self.assertEqual(
            self.db.query(SecurityIPBlock).count(), 1
        )

    def test_forwarded_header_has_no_authority(self):
        item = self.payload(source_ip="127.0.0.1")
        response = self.client.post(
            self.url,
            json=item,
            headers={
                "X-Sentinel-Response-Token": "stage2-test-secret",
                "X-Forwarded-For": "198.51.100.42",
            },
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
