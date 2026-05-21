"""Agent routes — run / stream agents, list available, poll status."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agents.base.agent_message import AgentMessage
from core.dependencies import AgentServiceDep, CurrentUserDep
from core.exceptions import AstroLearnError, NotFoundError
from schemas.agent_schema import (
    AgentInfoResponse,
    AgentResponse,
    AgentRunRequest,
    AgentStatusResponse,
)

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/", response_model=list[AgentInfoResponse])
async def list_agents(
    current_user: CurrentUserDep,
    service: AgentServiceDep,
) -> list[AgentInfoResponse]:
    """Return every registered agent class."""
    return await service.list_available_agents()


@router.post("/run", response_model=AgentResponse)
async def run_agent(
    request: AgentRunRequest,
    current_user: CurrentUserDep,
    service: AgentServiceDep,
) -> AgentResponse | StreamingResponse:
    """Run an agent (SSE if stream=True, single response otherwise)."""
    if request.stream:
        return StreamingResponse(
            _sse_format(service.stream_agent(current_user.id, request)),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                # Disable nginx/reverse-proxy response buffering.
                "X-Accel-Buffering": "no",
            },
        )
    return await service.run_agent(current_user.id, request)


@router.get("/{run_id}/status", response_model=AgentStatusResponse)
async def get_agent_status(
    run_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: AgentServiceDep,
) -> AgentStatusResponse:
    status = await service.get_status(run_id, current_user.id)
    if status is None:
        raise NotFoundError(message="Agent run not found", code="run_not_found")
    return status


@router.get("/{run_id}", response_model=AgentResponse)
async def get_agent_run(
    run_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: AgentServiceDep,
) -> AgentResponse:
    """Full run record (input + output + status)."""
    response = await service.get_run(run_id, current_user.id)
    if response is None:
        raise NotFoundError(message="Agent run not found", code="run_not_found")
    return response


async def _sse_format(stream: AsyncIterator[AgentMessage]) -> AsyncIterator[bytes]:
    """Wrap an AgentMessage stream as Server-Sent Events."""
    # Informational only; recorder owns AgentModel state.
    try:
        async for msg in stream:
            payload = msg.model_dump_json()
            yield f"data: {payload}\n\n".encode()
    except AstroLearnError as exc:
        body = json.dumps({"code": exc.code, "message": exc.message})
        yield f"event: error\ndata: {body}\n\n".encode()
        return
    except Exception as exc:
        # Defensive; recorder already wrote failure to AgentModel row.
        body = json.dumps({"code": "agent_error", "message": str(exc)})
        yield f"event: error\ndata: {body}\n\n".encode()
        return
    yield b"event: done\ndata: {}\n\n"
