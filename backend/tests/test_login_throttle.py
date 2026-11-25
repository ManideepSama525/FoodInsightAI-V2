from datetime import datetime, timedelta, timezone

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.models.login_throttle import LoginThrottleState
from backend.app.services.login_throttle import (
    clear_login_failures,
    get_login_cooldown_seconds,
    register_failed_login,
)


@pytest.fixture
def throttle_db(monkeypatch):
    monkeypatch.setenv(
        "SENTINEL_ACCOUNT_HASH_KEY",
        "stage2c-unit-test-secret",
    )

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    LoginThrottleState.__table__.create(bind=engine)

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    db = factory()

    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_progressive_cooldown_and_account_isolation(throttle_db):
    db = throttle_db
    email = "person-a@example.test"

    for _ in range(5):
        register_failed_login(db, email)

    state = db.query(LoginThrottleState).one()

    assert state.failure_count == 5

    first_cooldown = get_login_cooldown_seconds(db, email)
    assert 1 <= first_cooldown <= 15

    assert get_login_cooldown_seconds(
        db, "person-b@example.test"
    ) == 0

    state.blocked_until = (
        datetime.now(timezone.utc).replace(tzinfo=None)
        - timedelta(seconds=1)
    )
    db.commit()

    register_failed_login(db, email)

    state = db.query(LoginThrottleState).one()

    assert state.failure_count == 6

    second_cooldown = get_login_cooldown_seconds(db, email)
    assert 1 <= second_cooldown <= 30


def test_successful_login_clears_throttle_state(throttle_db):
    db = throttle_db
    email = "person-c@example.test"

    for _ in range(5):
        register_failed_login(db, email)

    clear_login_failures(db, email)

    assert db.query(LoginThrottleState).count() == 0
    assert get_login_cooldown_seconds(db, email) == 0


def test_expired_failure_window_resets_attempt_count(throttle_db):
    db = throttle_db
    email = "person-d@example.test"

    for _ in range(5):
        register_failed_login(db, email)

    state = db.query(LoginThrottleState).one()

    old_time = (
        datetime.now(timezone.utc).replace(tzinfo=None)
        - timedelta(minutes=16)
    )

    state.window_started_at = old_time
    state.blocked_until = old_time
    db.commit()

    register_failed_login(db, email)

    state = db.query(LoginThrottleState).one()

    assert state.failure_count == 1
    assert state.blocked_until is None
