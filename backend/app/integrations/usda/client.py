from typing import Any

import httpx

from backend.app.core.config import get_settings


class USDAClientError(RuntimeError):
    """Raised when FoodData Central cannot return a usable response."""


class USDAClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.usda_api_key
        self.base_url = (base_url or settings.usda_base_url).rstrip("/")

    async def search_foods(
        self,
        query: str,
        page_size: int = 10,
        page_number: int = 1,
        data_types: list[str] | None = None,
    ) -> dict[str, Any]:
        if not query.strip():
            raise ValueError("Food search query cannot be empty.")
        if not 1 <= page_size <= 50:
            raise ValueError("page_size must be between 1 and 50.")
        if page_number < 1:
            raise ValueError("page_number must be positive.")

        params: dict[str, Any] = {
            "query": query.strip(),
            "pageSize": page_size,
            "pageNumber": page_number,
            "api_key": self.api_key,
        }
        if data_types:
            params["dataType"] = data_types

        return await self._get("/foods/search", params)

    async def get_food(self, fdc_id: int) -> dict[str, Any]:
        if fdc_id <= 0:
            raise ValueError("fdc_id must be positive.")
        return await self._get(f"/food/{fdc_id}", {"api_key": self.api_key})

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        timeout = httpx.Timeout(15.0, connect=5.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(f"{self.base_url}{path}", params=params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise USDAClientError("FoodData Central request failed.") from exc

        if not isinstance(payload, dict):
            raise USDAClientError("FoodData Central returned an unexpected response.")
        return payload
