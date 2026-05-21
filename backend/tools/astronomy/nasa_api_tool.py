"""NASA public APIs (APOD, Exoplanet Archive, Mars rover photos)."""

from __future__ import annotations

from typing import Any, ClassVar, Literal

import httpx
from pydantic import BaseModel, Field

from core.config import Settings
from core.exceptions import ExternalServiceError
from tools.base_tool import BaseTool

NasaEndpoint = Literal["apod", "exoplanet_archive", "mars_photos", "neo_feed"]


class NasaApiInput(BaseModel):
    endpoint: NasaEndpoint
    params: dict[str, Any] = Field(default_factory=dict)


class NasaApiTool(BaseTool):
    """Thin wrapper over NASA Open APIs."""

    name: ClassVar[str] = "nasa_api"
    description: ClassVar[str] = (
        "Query NASA public APIs: APOD (Astronomy Picture of the Day), "
        "Exoplanet Archive, Mars rover photos, near-Earth object feed."
    )
    input_schema: ClassVar[type[BaseModel]] = NasaApiInput

    _BASE_URLS: ClassVar[dict[str, str]] = {
        "apod": "https://api.nasa.gov/planetary/apod",
        "exoplanet_archive": "https://exoplanetarchive.ipac.caltech.edu/TAP/sync",
        "mars_photos": "https://api.nasa.gov/mars-photos/api/v1/rovers",
        "neo_feed": "https://api.nasa.gov/neo/rest/v1/feed",
    }

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.http_client = http_client or httpx.AsyncClient(timeout=30.0)

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        endpoint: str = kwargs["endpoint"]
        params: dict[str, Any] = dict(kwargs.get("params") or {})
        url, request_params = self._build_request(endpoint, params)
        try:
            response = await self.http_client.get(url, params=request_params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(
                message=f"NASA API {endpoint!r} returned HTTP {exc.response.status_code}",
                code="nasa_api_http_error",
                details={"status_code": exc.response.status_code, "endpoint": endpoint},
            ) from exc
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                message=f"NASA API {endpoint!r} request failed: {exc}",
                code="nasa_api_request_failed",
                details={"endpoint": endpoint},
            ) from exc

        try:
            return response.json()
        except ValueError as exc:
            raise ExternalServiceError(
                message=f"NASA API {endpoint!r} returned non-JSON body",
                code="nasa_api_invalid_response",
                details={"endpoint": endpoint},
            ) from exc

    def _build_request(
        self,
        endpoint: str,
        params: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """(URL, query-params) pair for endpoint."""
        base = self._BASE_URLS[endpoint]
        request_params = dict(params)

        if endpoint == "mars_photos":
            rover = request_params.pop("rover", "curiosity")
            url = f"{base}/{rover}/photos"
        else:
            url = base

        if endpoint == "exoplanet_archive":
            # TAP endpoint expects ADQL `query` + format hint.
            request_params.setdefault("format", "json")
        else:
            # DEMO_KEY fallback for unconfigured deployments (low rate limit).
            request_params.setdefault(
                "api_key", self.settings.NASA_API_KEY or "DEMO_KEY"
            )

        return url, request_params
