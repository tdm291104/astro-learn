"""Thin LiteLLM wrapper — the only module allowed to import litellm."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import httpx
import structlog

# litellm is the single LLM-SDK boundary every other module respects.
from litellm import acompletion, aembedding
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import Settings, get_settings
from core.exceptions import LLMError
from core.usage_context import get_current_user_id

_logger = structlog.get_logger(__name__)

# Lazy import to break agents.base ↔ LLMClient cycle.
if TYPE_CHECKING:
    from agents.base.agent_message import ToolCall


Message = dict[str, Any]
ChatChunk = dict[str, Any]


class AssistantTurn(BaseModel):
    """One assistant turn from a tool-calling LLM call."""

    # tool_calls typed Any to avoid cycle; runtime elements are ToolCall.
    model_config = {"arbitrary_types_allowed": True}

    content: str = ""
    tool_calls: list[Any] = Field(default_factory=list)


class LLMClient:
    """Stateless wrapper around `litellm.acompletion` / `aembedding`."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._settings: Settings = settings or get_settings()
        # Optional so unit tests don't need a DB; no-op when None.
        self._session_factory = session_factory

    async def _record_usage(self, model: str, response: Any) -> None:
        """Best-effort persist of token_usage_events; swallows DB errors."""
        if self._session_factory is None:
            return
        user_id = get_current_user_id()
        if user_id is None:
            return
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion = int(getattr(usage, "completion_tokens", 0) or 0)
        total = int(getattr(usage, "total_tokens", prompt + completion) or 0)
        if total == 0:
            return
        try:
            # Local import to break model-load → core cycle.
            from repositories.token_usage_repository import (
                TokenUsageRepository,
            )

            async with self._session_factory() as db:
                await TokenUsageRepository(db).record(
                    user_id=user_id,
                    model=model,
                    prompt_tokens=prompt,
                    completion_tokens=completion,
                    total_tokens=total,
                )
                await db.commit()
        except Exception as exc:  # noqa: BLE001 — best-effort persistence
            _logger.warning(
                "llm_client.record_usage_failed",
                model=model,
                error=str(exc),
            )

    async def complete(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Run a single non-streaming completion and return the text."""
        chat_kwargs = self._chat_kwargs(
            model=model, temperature=temperature, max_tokens=max_tokens
        )
        try:
            response = await acompletion(
                messages=messages,
                **chat_kwargs,
                **kwargs,
            )
        except Exception as exc:
            raise LLMError(
                message=f"LLM completion failed: {exc}",
                code="llm_completion_failed",
            ) from exc
        await self._record_usage(chat_kwargs["model"], response)
        return response.choices[0].message.content or ""

    async def stream(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatChunk]:
        """Async generator yielding streaming chunks from the model."""
        chat_kwargs = self._chat_kwargs(
            model=model, temperature=temperature, max_tokens=max_tokens
        )
        # Final-chunk usage block lets us record tokens without an extra call.
        stream_options = {"include_usage": True}
        try:
            response = await acompletion(
                messages=messages,
                stream=True,
                stream_options=stream_options,
                **chat_kwargs,
                **kwargs,
            )
        except Exception as exc:
            raise LLMError(
                message=f"LLM stream init failed: {exc}",
                code="llm_stream_failed",
            ) from exc

        try:
            async for chunk in response:
                # Final usage chunk has empty choices.
                if not chunk.choices and getattr(chunk, "usage", None):
                    await self._record_usage(chat_kwargs["model"], chunk)
                    continue
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = (choice.delta.content or "") if choice.delta else ""
                finish_reason = choice.finish_reason
                # Skip pure keep-alive chunks.
                if delta or finish_reason:
                    yield {"delta": delta, "finish_reason": finish_reason}
        except Exception as exc:
            raise LLMError(
                message=f"LLM stream interrupted: {exc}",
                code="llm_stream_failed",
            ) from exc

    async def complete_with_tools(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AssistantTurn:
        """Run a single completion that may emit tool calls."""
        call_kwargs = self._chat_kwargs(
            model=model, temperature=temperature, max_tokens=max_tokens
        )
        call_kwargs["tools"] = tools
        if tool_choice is not None:
            call_kwargs["tool_choice"] = tool_choice

        try:
            response = await acompletion(messages=messages, **call_kwargs, **kwargs)
        except Exception as exc:
            raise LLMError(
                message=f"LLM completion failed: {exc}",
                code="llm_completion_failed",
            ) from exc

        await self._record_usage(call_kwargs["model"], response)
        message = response.choices[0].message
        return AssistantTurn(
            content=message.content or "",
            tool_calls=self._parse_tool_calls(getattr(message, "tool_calls", None)),
        )

    @staticmethod
    def _parse_tool_calls(raw_calls: Any) -> list[Any]:
        """Convert LiteLLM tool-call objects to our ToolCall; decodes JSON args."""
        if not raw_calls:
            return []
        # Lazy import to break cycle.
        from agents.base.agent_message import ToolCall

        parsed: list[ToolCall] = []
        for raw in raw_calls:
            args_str = raw.function.arguments or "{}"
            try:
                arguments = json.loads(args_str)
            except json.JSONDecodeError as exc:
                raise LLMError(
                    message=f"LLM emitted unparseable tool-call arguments: {args_str!r}",
                    code="llm_invalid_tool_call",
                ) from exc
            parsed.append(
                ToolCall(id=raw.id, name=raw.function.name, arguments=arguments)
            )
        return parsed

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        """Return one embedding vector per input text."""
        try:
            response = await aembedding(
                model=model or self._settings.EMBEDDING_MODEL,
                input=texts,
                timeout=self._settings.LLM_TIMEOUT,
                # aembedding uses api_base (not base_url like chat completion).
                api_base=self._settings.LLM_BASE_URL,
                api_key=self._settings.LLM_API_KEY,
                # Infinity v2 rejects encoding_format: null.
                encoding_format="float",
            )
        except Exception as exc:
            raise LLMError(
                message=f"LLM embedding failed: {exc}",
                code="llm_embed_failed",
            ) from exc
        return [item["embedding"] for item in response.data]

    async def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        top_n: int | None = None,
        model: str | None = None,
    ) -> list[tuple[int, float]]:
        """Cross-encoder rerank via the LiteLLM proxy's /v1/rerank endpoint.

        Returns `[(orig_index, relevance_score)]` sorted by score desc.
        Caller maps indices back to its original candidate list.

        Bypasses the litellm SDK (which requires a provider-prefixed model
        for rerank) and posts to the proxy directly — same pattern Cohere
        uses, which the proxy is API-compatible with.
        """
        if not documents:
            return []
        base = self._settings.LLM_BASE_URL
        if not base:
            raise LLMError(
                message="rerank requires LLM_BASE_URL",
                code="rerank_no_base",
            )

        payload = {
            "model": model or self._settings.RERANKER_MODEL,
            "query": query,
            "documents": documents,
            "top_n": top_n if top_n is not None else len(documents),
        }
        headers = {"Content-Type": "application/json"}
        if self._settings.LLM_API_KEY:
            headers["Authorization"] = f"Bearer {self._settings.LLM_API_KEY}"

        # Jina free tier 429s under burst; exponential backoff 1/2/4/8s.
        async with httpx.AsyncClient(timeout=self._settings.LLM_TIMEOUT) as client:
            for attempt in range(5):
                response = await client.post(
                    f"{base.rstrip('/')}/v1/rerank",
                    json=payload,
                    headers=headers,
                )
                if response.status_code != 429:
                    break
                await asyncio.sleep(2 ** attempt)

        if response.status_code != 200:
            raise LLMError(
                message=f"Rerank failed: HTTP {response.status_code} {response.text[:200]}",
                code="llm_rerank_failed",
            )

        data = response.json()
        return [
            (int(item["index"]), float(item["relevance_score"]))
            for item in data.get("results", [])
        ]

    def _chat_kwargs(
        self,
        *,
        model: str | None,
        temperature: float | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        """Resolve per-call overrides against settings defaults."""
        kw: dict[str, Any] = {
            "model": model or self._settings.LLM_MODEL,
            "temperature": (
                temperature
                if temperature is not None
                else self._settings.LLM_TEMPERATURE
            ),
            "max_tokens": max_tokens or self._settings.LLM_MAX_TOKENS,
            "timeout": self._settings.LLM_TIMEOUT,
        }
        if self._settings.LLM_FALLBACK_MODELS:
            kw["fallbacks"] = self._settings.LLM_FALLBACK_MODELS
        if self._settings.LLM_BASE_URL:
            kw["base_url"] = self._settings.LLM_BASE_URL
        if self._settings.LLM_API_KEY:
            kw["api_key"] = self._settings.LLM_API_KEY
        return kw
