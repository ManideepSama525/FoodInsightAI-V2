import httpx


class FreshnessServiceUnavailable(Exception):
    """The independent freshness inference service cannot be reached."""


class FreshnessServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


async def predict_freshness(
    *,
    service_url: str,
    category: str,
    image_content: bytes,
    media_type: str,
    filename: str,
) -> dict:
    url = f"{service_url.rstrip('/')}/predict"

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                url,
                data={"category": category},
                files={
                    "image": (
                        filename,
                        image_content,
                        media_type,
                    )
                },
            )
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        raise FreshnessServiceUnavailable(
            "Freshness inference service is unavailable."
        ) from exc

    if response.status_code >= 500:
        raise FreshnessServiceUnavailable(
            "Freshness inference service encountered an internal error."
        )

    if response.status_code >= 400:
        try:
            payload = response.json()
            detail = payload.get("detail", "Freshness prediction rejected.")
        except (ValueError, AttributeError):
            detail = "Freshness prediction rejected."

        raise FreshnessServiceError(response.status_code, str(detail))

    try:
        payload = response.json()
    except ValueError as exc:
        raise FreshnessServiceError(
            502,
            "Freshness service returned an invalid response.",
        ) from exc

    if not isinstance(payload, dict):
        raise FreshnessServiceError(
            502,
            "Freshness service returned an invalid response.",
        )

    return payload
