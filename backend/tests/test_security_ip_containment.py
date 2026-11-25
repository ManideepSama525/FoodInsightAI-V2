import unittest
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.models.security_ip_block import SecurityIPBlock
from backend.app.services.security_ip_containment import (
    create_temporary_ip_block,
    is_test_ip_blocked,
    validate_test_source_ip,
)


class SecurityIPContainmentTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SecurityIPBlock.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.now = datetime(2026, 11, 19, 12, 0, 0)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def block(self, **overrides):
        values = {
            "action_id": str(uuid4()),
            "incident_id": "INC-900001",
            "source_ip": "198.51.100.42",
            "duration_seconds": 30,
            "reason": "Controlled repeated attack simulation",
            "now": self.now,
        }
        values.update(overrides)
        return create_temporary_ip_block(self.db, **values)

    def test_block_becomes_active(self):
        result = self.block()
        self.assertTrue(result["active"])
        self.assertTrue(
            is_test_ip_blocked(self.db, "198.51.100.42", self.now)
        )

    def test_expiry_restores_access(self):
        self.block()
        self.assertFalse(is_test_ip_blocked(
            self.db, "198.51.100.42",
            self.now + timedelta(seconds=31),
        ))

    def test_exact_expiry_is_not_blocked(self):
        self.block()
        self.assertFalse(is_test_ip_blocked(
            self.db, "198.51.100.42",
            self.now + timedelta(seconds=30),
        ))

    def test_replay_is_idempotent(self):
        action_id = str(uuid4())
        self.block(action_id=action_id)
        duplicate = self.block(action_id=action_id)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(
            len(self.db.scalars(
                select(SecurityIPBlock)
            ).all()), 1,
        )

    def test_action_id_cannot_change_target(self):
        action_id = str(uuid4())
        self.block(action_id=action_id)
        with self.assertRaises(ValueError):
            self.block(
                action_id=action_id,
                source_ip="203.0.113.22",
            )

    def test_live_addresses_are_rejected(self):
        for ip in (
            "127.0.0.1",
            "172.17.0.1",
            "192.168.1.10",
            "10.0.0.5",
            "8.8.8.8",
            "::1",
            "0.0.0.0",
        ):
            with self.subTest(ip=ip):
                with self.assertRaises(ValueError):
                    validate_test_source_ip(ip)

    def test_all_three_test_networks(self):
        for ip in (
            "192.0.2.25",
            "198.51.100.25",
            "203.0.113.25",
        ):
            self.assertEqual(validate_test_source_ip(ip), ip)

    def test_invalid_durations(self):
        for seconds in (0, 4, 301, -1, True, 30.5):
            with self.subTest(seconds=seconds):
                with self.assertRaises(ValueError):
                    self.block(duration_seconds=seconds)

    def test_unblocked_address(self):
        self.assertFalse(
            is_test_ip_blocked(self.db, "203.0.113.44", self.now)
        )

    def test_audit_record_survives_expiry(self):
        self.block()
        after = self.now + timedelta(minutes=5)
        self.assertFalse(
            is_test_ip_blocked(self.db, "198.51.100.42", after)
        )
        record = self.db.scalar(select(SecurityIPBlock))
        self.assertEqual(record.result, "SUCCESS")
        self.assertEqual(record.incident_id, "INC-900001")

    def test_forwarded_header_does_not_define_identity(self):
        # This service accepts only an explicit validated source_ip.
        # Request-header trust is handled separately at middleware level.
        with self.assertRaises(ValueError):
            self.block(source_ip="198.51.100.42, 127.0.0.1")


if __name__ == "__main__":
    unittest.main()
