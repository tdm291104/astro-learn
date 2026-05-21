"""Web search via Tavily or SerpAPI — provider chosen by available env keys."""

from __future__ import annotations

from typing import Any, ClassVar, Literal

import httpx
from pydantic import BaseModel, Field

from core.config import Settings
from core.exceptions import ExternalServiceError, ToolError
from tools.base_tool import BaseTool

_TAVILY_URL: str = "https://api.tavily.com/search"
_SERPAPI_URL: str = "https://serpapi.com/search"


SearchProvider = Literal["tavily", "serpapi"]


class WebSearchInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=512)
    max_results: int = Field(5, ge=1, le=20)
    include_snippets: bool = True


class WebSearchResult(BaseModel):
    title: str
    url: str
    snippet: str | None = None
    score: float | None = None


class WebSearchTool(BaseTool):
    """Web search; provider chosen by available env keys."""

    name: ClassVar[str] = "web_search"
    description: ClassVar[str] = (
        "Search the public web. Use this when the answer requires recent "
        "information not in the indexed documents or trained knowledge."
    )
    input_schema: ClassVar[type[BaseModel]] = WebSearchInput

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.http_client = http_client or httpx.AsyncClient(timeout=20.0)

    async def execute(self, **kwargs: Any) -> list[dict[str, Any]]:
        provider = self._select_provider()
        query: str = kwargs["query"]
        max_results: int = kwargs.get("max_results", 5)
        include_snippets: bool = kwargs.get("include_snippets", True)

        if provider == "tavily":
            results = await self._search_tavily(query, max_results)
        else:
            results = await self._search_serpapi(query, max_results)

        if not include_snippets:
            for r in results:
                r.snippet = None
        return [r.model_dump() for r in results]

    def _select_provider(self) -> SearchProvider:
        tavily = (self.settings.TAVILY_API_KEY or "").strip()
        serpapi = (self.settings.SERPAPI_API_KEY or "").strip()
        if tavily:
            return "tavily"
        if serpapi:
            return "serpapi"
        raise ToolError(
            message="No web search provider configured. Set TAVILY_API_KEY or SERPAPI_API_KEY.",
            code="web_search_no_provider",
        )

    async def _search_tavily(self, query: str, max_results: int) -> list[WebSearchResult]:
        body = {
            "api_key": self.settings.TAVILY_API_KEY,
            "query": query,
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        }
        payload = await self._post_json(_TAVILY_URL, body, provider="tavily")
        raw_results = payload.get("results") or []
        return [
            WebSearchResult(
                title=str(r.get("title") or ""),
                url=str(r.get("url") or ""),
                snippet=r.get("content"),
                score=r.get("score"),
            )
            for r in raw_results
        ]

    async def _search_serpapi(self, query: str, max_results: int) -> list[WebSearchResult]:
        params = {
            "api_key": self.settings.SERPAPI_API_KEY,
            "q": query,
            "engine": "google",
            "num": max_results,
        }
        payload = await self._get_json(_SERPAPI_URL, params, provider="serpapi")
        organic = payload.get("organic_results") or []
        # SerpAPI may not honour `num` exactly; slice defensively.
        return [
            WebSearchResult(
                title=str(r.get("title") or ""),
                url=str(r.get("link") or ""),
                snippet=r.get("snippet"),
                score=None,  # SerpAPI organic has no score
            )
            for r in organic[:max_results]
        ]

    async def _post_json(
        self, url: str, body: dict[str, Any], *, provider: str
    ) -> dict[str, Any]:
        try:
            response = await self.http_client.post(url, json=body)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(
                message=f"{provider} returned HTTP {exc.response.status_code}",
                code=f"{provider}_http_error",
                details={"status_code": exc.response.status_code},
            ) from exc
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                message=f"{provider} request failed: {exc}",
                code=f"{provider}_request_failed",
            ) from exc
        return self._parse_json(response, provider=provider)

    async def _get_json(
        self, url: str, params: dict[str, Any], *, provider: str
    ) -> dict[str, Any]:
        try:
            response = await self.http_client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(
                message=f"{provider} returned HTTP {exc.response.status_code}",
                code=f"{provider}_http_error",
                details={"status_code": exc.response.status_code},
            ) from exc
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                message=f"{provider} request failed: {exc}",
                code=f"{provider}_request_failed",
            ) from exc
        return self._parse_json(response, provider=provider)

    @staticmethod
    def _parse_json(response: httpx.Response, *, provider: str) -> dict[str, Any]:
        try:
            return response.json()
        except ValueError as exc:
            raise ExternalServiceError(
                message=f"{provider} returned non-JSON body",
                code=f"{provider}_invalid_response",
            ) from exc
