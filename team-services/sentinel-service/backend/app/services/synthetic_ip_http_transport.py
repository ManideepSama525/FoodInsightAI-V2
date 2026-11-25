"""Restricted Sentinel-to-FoodInsightAI test transport.

Not registered with a live route or ingestion handler.
No network request is possible without an explicit opt-in.
The destination is fixed to the local FoodInsightAI backend.
"""
import httpx

from app.services.synthetic_ip_containment_policy import (
    allowed_synthetic_ip,
)

ENDPOINT = (
    "http://127.0.0.1:8000"
    "/api/v1/internal/sentinel/temporary-ip-block"
)


def make_synthetic_ip_transport(
    *,
    enabled=False,
    client=None,
):
    """Return the transport(payload, headers) used by Stage IP-6.

    An injected httpx client permits completely offline tests.
    No token is stored in this adapter or placed in a URL.
    """
    if enabled is not True:
        raise ValueError("Synthetic HTTP transport is disabled.")

    if client is not None and not isinstance(
        client, httpx.Client
    ):
        raise ValueError("An httpx.Client is required.")

    def transport(payload, headers):
        if not isinstance(payload, dict):
            raise ValueError("Invalid containment request.")

        if not allowed_synthetic_ip(
            payload.get("source_ip")
        ):
            raise ValueError(
                "Transport rejects non-synthetic source."
            )

        if (
            payload.get("duration_seconds") != 30
            or type(payload.get("duration_seconds")) is not int
        ):
            raise ValueError(
                "Transport accepts only a 30-second test block."
            )

        if not isinstance(headers, dict):
            raise ValueError("Invalid authorization headers.")

        token = headers.get("X-Sentinel-Response-Token")
        if not isinstance(token, str) or len(token) < 16:
            raise ValueError(
                "Response channel token is missing."
            )

        # A caller-supplied HTTP client is supported for offline
        # mock testing. Production callers use a fresh client with
        # environment proxy settings disabled.
        owns_client = client is None
        http_client = client

        if owns_client:
            http_client = httpx.Client(
                timeout=httpx.Timeout(
                    6.0, connect=2.0
                ),
                trust_env=False,
                follow_redirects=False,
            )

        try:
            response = http_client.post(
                ENDPOINT,
                json=payload,
                headers={
                    "X-Sentinel-Response-Token": token,
                    "Content-Type": "application/json",
                },
            )

            try:
                body = response.json()
            except ValueError:
                body = {}

            return {
                "status_code": response.status_code,
                "body": body,
            }
        finally:
            if owns_client and http_client is not None:
                http_client.close()

    return transport
