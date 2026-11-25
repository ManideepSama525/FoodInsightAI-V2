import httpx


class ToxiFruitServiceUnavailable(Exception):
    """The independent ToxiFruit inference service cannot be reached."""


class ToxiFruitServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


async def screen_produce(
    *,
    service_url: str,
    image_content: bytes,
    media_type: str,
    filename: str,
) -> dict:
    url = f"{service_url.rstrip('/')}/predict"

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                url,
                files={
                    "image": (
                        filename,
                        image_content,
                        media_type,
                    )
                },
            )
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        raise ToxiFruitServiceUnavailable(
            "ToxiFruit visual screening service is unavailable."
        ) from exc

    if response.status_code >= 500:
        raise ToxiFruitServiceUnavailable(
            "ToxiFruit visual screening service encountered an internal error."
        )

    if response.status_code >= 400:
        try:
            payload = response.json()
            detail = payload.get("detail", "ToxiFruit screening rejected.")
        except (ValueError, AttributeError):
            detail = "ToxiFruit screening rejected."

        raise ToxiFruitServiceError(response.status_code, str(detail))

    try:
        payload = response.json()
    except ValueError as exc:
        raise ToxiFruitServiceError(
            502,
            "ToxiFruit service returned an invalid response.",
        ) from exc

    if not isinstance(payload, dict):
        raise ToxiFruitServiceError(
            502,
            "ToxiFruit service returned an invalid response.",
        )

    return payload
