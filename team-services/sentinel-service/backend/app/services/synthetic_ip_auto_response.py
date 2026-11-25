"""Opt-in synthetic containment triggered by persisted detections.

Only already-committed, newly created brute-force incidents may be
scheduled. The worker independently reloads and verifies database
evidence. No real IP containment or firewall manipulation.
"""
import logging
import os
from uuid import UUID, uuid5

from app.database.database import SessionLocal
from app.services.synthetic_ip_containment_coordinator import (
    coordinate_test_ip_containment,
)
from app.services.synthetic_ip_containment_policy import (
    allowed_synthetic_ip,
)
from app.services.synthetic_ip_http_transport import (
    make_synthetic_ip_transport,
)

logger = logging.getLogger("sentinel.synthetic_auto_containment")

_NAMESPACE = UUID("c6e42e24-cbc1-4c29-b8d9-396dd8757ea0")


def _enabled():
    return (
        os.getenv("SENTINEL_SYNTHETIC_AUTO_CONTAINMENT_ENABLED")
        == "1"
        and os.getenv("SENTINEL_SYNTHETIC_HTTP_DISPATCH_ENABLED")
        == "1"
    )


def schedule_containment_after_ingestion(
    background_tasks,
    record,
    detections,
):
    """Schedule only; never execute a response in ingestion transaction."""
    if not _enabled():
        return False

    if (
        getattr(record, "source", None) != "FoodInsightAI"
        or getattr(record, "event_type", None) != "authentication"
        or getattr(record, "status_code", None) != 401
        or getattr(record, "method", None) != "POST"
        or getattr(record, "path", None) not in (
            "/auth/login", "/api/v1/auth/login"
        )
        or not allowed_synthetic_ip(
            getattr(record, "source_ip", None)
        )
    ):
        return False

    if not isinstance(detections, list):
        return False

    scheduled = False
    for detection in detections:
        if not isinstance(detection, dict):
            continue
        if (
            detection.get("attack") != "Brute Force"
            or detection.get("created") is not True
            or not isinstance(detection.get("incident_id"), str)
        ):
            continue

        background_tasks.add_task(
            run_synthetic_auto_response,
            detection["incident_id"],
        )
        scheduled = True

    return scheduled


def run_synthetic_auto_response(incident_id):
    """Fresh database evidence, then restricted authenticated HTTP dispatch."""
    if not _enabled():
        return

    token = os.getenv("SENTINEL_RESPONSE_TOKEN", "")
    if not token or len(token) < 16:
        logger.warning(
            "Synthetic response not dispatched: response token unavailable."
        )
        return

    if not isinstance(incident_id, str):
        return

    db = None
    try:
        db = SessionLocal()

        # Deterministic ID: retrying a given incident cannot extend an
        # existing successful block or create a second action.
        action_id = str(uuid5(_NAMESPACE, incident_id))
        transport = make_synthetic_ip_transport(enabled=True)

        result = coordinate_test_ip_containment(
            db,
            incident_id=incident_id,
            action_id=action_id,
            reason=(
                "Verified repeated authentication failures; "
                "restricted synthetic test response"
            ),
            response_token=token,
            transport=transport,
            enabled=True,
        )

        if result.get("status") == "SUCCESS":
            logger.info(
                "FoodInsightAI confirmed synthetic block persistence "
                "for incident %s. Middleware enforcement not yet verified.",
                incident_id,
            )
        else:
            logger.warning(
                "Synthetic containment not confirmed for incident %s: %s.",
                incident_id,
                result.get("status"),
            )

    except Exception:
        logger.exception(
            "Synthetic automatic response failed for incident %s.",
            incident_id,
        )
    finally:
        if db is not None:
            db.close()
