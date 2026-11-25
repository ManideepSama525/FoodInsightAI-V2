from __future__ import annotations

import hashlib
import hmac
import logging
import os
import queue
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("foodinsightai.sentinel_xdr")
_EVENT_QUEUE: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1000)
_STOP_EVENT = threading.Event()
_WORKER: threading.Thread | None = None
_START_LOCK = threading.Lock()
_DISABLED_WARNING_EMITTED = False


def _client_ip(request: Any) -> str | None:
    # Use the direct peer address. Do not trust arbitrary X-Forwarded-For headers.
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client is not None else None
    if not host:
        return None
    value = str(host).strip()
    return value[:45] or None


def _account_identifier_hash(email: str) -> str | None:
    key = os.getenv("SENTINEL_ACCOUNT_HASH_KEY", "")
    if not key:
        return None
    digest = hmac.new(
        key.encode("utf-8"),
        email.strip().casefold().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest


def _enqueue(payload: dict[str, Any]) -> bool:
    global _DISABLED_WARNING_EMITTED
    worker = _WORKER
    if worker is None or not worker.is_alive():
        if not _DISABLED_WARNING_EMITTED:
            logger.warning("Sentinel-XDR telemetry is not active; events are not being sent.")
            _DISABLED_WARNING_EMITTED = True
        return False
    try:
        _EVENT_QUEUE.put_nowait(payload)
        return True
    except queue.Full:
        logger.warning("Sentinel-XDR telemetry queue is full; one event was dropped.")
        return False


def publish_request_event(request: Any, status_code: int, api_prefix: str) -> None:
    path = str(getattr(getattr(request, "url", None), "path", ""))
    prefix = str(api_prefix or "/api/v1").rstrip("/")
    if not path.startswith(prefix + "/"):
        return
    if path.rstrip("/").endswith("/auth/login"):
        # The login handler emits a richer, account-pseudonymized event.
        return

    source_ip = _client_ip(request)
    if not source_ip:
        return

    route = getattr(request, "scope", {}).get("route")
    route_path = getattr(route, "path", None)
    safe_path = str(route_path or path).split("?", 1)[0][:512]

    payload = {
        "event_id": uuid.uuid4().hex,
        "source": "FoodInsightAI",
        "event_type": "request",
        "category": "api",
        "client_id": source_ip,
        "source_ip": source_ip,
        "method": str(getattr(request, "method", "GET")).upper()[:12],
        "path": safe_path,
        "status_code": int(status_code),
        "description": "FoodInsightAI API request metadata",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    _enqueue(payload)


def publish_payload_security_event(request: Any, status_code: int, indicator: dict[str, str], action_taken: str = "MONITOR") -> None:
    """Send only a fixed rule identifier and request metadata; never payload text."""
    source_ip = _client_ip(request)
    if not source_ip:
        return

    route = getattr(request, "scope", {}).get("route")
    route_path = getattr(route, "path", None)
    safe_path = str(route_path or "/blocked-request")
    safe_path = safe_path.split("?", 1)[0][:512]

    allowed_rules = {
        "FOOD_SQLI_001": "SQL Injection",
        "FOOD_XSS_001": "Cross Site Scripting",
        "FOOD_CMDI_001": "Command Injection",
        "FOOD_PATH_001": "Directory Traversal",
    }
    rule_id = str(indicator.get("rule_id", ""))
    attack = allowed_rules.get(rule_id)
    if not attack:
        return

    payload = {
        "event_id": uuid.uuid4().hex,
        "source": "FoodInsightAI",
        "event_type": "payload_security",
        "category": "web_attack",
        "severity": "High",
        "risk_score": 85.0,
        "client_id": source_ip,
        "source_ip": source_ip,
        "method": str(getattr(request, "method", "POST")).upper()[:12],
        "path": safe_path,
        "status_code": int(status_code),
        "detection_rule_id": rule_id,
        "description": f"Locally matched a {attack} indicator. Request content was not transmitted.",
        "action_taken": str(action_taken or "MONITOR")[:80],
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    _enqueue(payload)

def publish_authentication_event(
    request: Any,
    email: str,
    status_code: int,
    outcome: str,
    user_id: str | None = None,
    synthetic_probe: bool = False,
) -> None:
    source_ip = _client_ip(request)
    if not source_ip:
        return

    route = getattr(request, "scope", {}).get("route")
    route_path = getattr(route, "path", None)
    path = str(route_path or getattr(getattr(request, "url", None), "path", "/auth/login"))[:512]

    descriptions = {
        "success": "Authentication succeeded",
        "failure": "Authentication failed",
        "denied": "Authentication denied for inactive account",
        "rate_limited": "Authentication attempt rate limited",
    }
    payload = {
        "event_id": uuid.uuid4().hex,
        "source": "FoodInsightAI",
        "event_type": "authentication",
        "category": "authentication",
        "client_id": source_ip,
        "source_ip": source_ip,
        "account_id_hash": _account_identifier_hash(email),
        "user_id": str(user_id)[:64] if user_id else None,
        "method": str(getattr(request, "method", "POST")).upper()[:12],
        "path": path,
        "status_code": int(status_code),
        "description": (
            "Synthetic Sentinel login-protection probe: authentication failed"
            if synthetic_probe and outcome == "failure" and user_id is None
            else descriptions.get(outcome, "Authentication event")
        ),
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    _enqueue(payload)


def _worker_main() -> None:
    base_url = os.getenv("SENTINEL_XDR_URL", "http://127.0.0.1:8010").rstrip("/")
    token = os.getenv("SENTINEL_INGEST_TOKEN", "")
    endpoint = base_url + "/integration/events"
    headers = {"X-Sentinel-Ingest-Token": token}

    timeout = httpx.Timeout(2.0, connect=0.5)
    with httpx.Client(timeout=timeout, trust_env=False) as client:
        while not _STOP_EVENT.is_set() or not _EVENT_QUEUE.empty():
            try:
                payload = _EVENT_QUEUE.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                delivered = False
                for attempt in range(3):
                    try:
                        response = client.post(endpoint, json=payload, headers=headers)
                        if 200 <= response.status_code < 300:
                            delivered = True
                            # Sentinel's persisted detector decision is the
                            # authority. Never infer protection from /health.
                            if (
                                response.status_code == 202
                                and payload.get("description")
                                   == "Synthetic Sentinel login-protection probe: authentication failed"
                            ):
                                try:
                                    from backend.app.db.session import SessionLocal
                                    from backend.app.services.sentinel_login_guard import persist_confirmed_hold
                                    acknowledgment = response.json()
                                    with SessionLocal() as db:
                                        if persist_confirmed_hold(db, payload, acknowledgment):
                                            logger.info(
                                                "Sentinel confirmed synthetic login hold for event %s.",
                                                payload["event_id"],
                                            )
                                except Exception:
                                    logger.exception("Synthetic Sentinel hold recording failed.")
                            break
                        if response.status_code < 500:
                            logger.error(
                                "Sentinel-XDR rejected telemetry with HTTP %s; event discarded.",
                                response.status_code,
                            )
                            break
                    except httpx.HTTPError as exc:
                        if attempt == 2:
                            logger.warning("Sentinel-XDR telemetry delivery failed: %s", type(exc).__name__)
                    if attempt < 2:
                        _STOP_EVENT.wait(0.15 * (attempt + 1))

                if not delivered:
                    logger.debug("A Sentinel-XDR event was not delivered.")
            finally:
                _EVENT_QUEUE.task_done()


def start_telemetry() -> None:
    global _WORKER, _DISABLED_WARNING_EMITTED
    with _START_LOCK:
        if _WORKER is not None and _WORKER.is_alive():
            return
        token = os.getenv("SENTINEL_INGEST_TOKEN", "")
        if not token:
            logger.warning("SENTINEL_INGEST_TOKEN is not configured; Sentinel-XDR telemetry is disabled.")
            return
        _STOP_EVENT.clear()
        _DISABLED_WARNING_EMITTED = False
        _WORKER = threading.Thread(
            target=_worker_main,
            name="sentinel-xdr-telemetry",
            daemon=True,
        )
        _WORKER.start()
        logger.info("Sentinel-XDR telemetry worker started for %s.", os.getenv("SENTINEL_XDR_URL", "http://127.0.0.1:8010"))


def stop_telemetry() -> None:
    worker = _WORKER
    if worker is None:
        return
    _STOP_EVENT.set()
    worker.join(timeout=4.0)
    if worker.is_alive():
        logger.warning("Sentinel-XDR telemetry worker did not finish draining before shutdown.")