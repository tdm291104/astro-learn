"""Abstract base class for every agent in the system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from agents.base.agent_message import AgentMessage
from agents.base.agent_state import AgentState
from core.llm.llm_client import LLMClient
from tools.base_tool import BaseTool


class BaseAgent(ABC):
    """Abstract agent."""

    name: ClassVar[str]
    description: ClassVar[str]
    capabilities: ClassVar[list[str]] = []

    def __init__(
        self,
        llm: LLMClient,
        tools: list[BaseTool] | None = None,
    ) -> None:
        self.llm = llm
        self.tools: dict[str, BaseTool] = {t.name: t for t in (tools or [])}

    @abstractmethod
    async def run(
        self,
        task: dict[str, Any],
        *,
        state: AgentState | None = None,
    ) -> AgentState:
        """Execute the agent to completion and return the final state."""
        ...

    @abstractmethod
    async def stream(
        self,
        task: dict[str, Any],
        *,
        state: AgentState | None = None,
    ) -> AsyncIterator[AgentMessage]:
        """Stream incremental messages as the agent works."""
        ...

    def get_tool(self, name: str) -> BaseTool | None:
        """Return a registered tool by name or None."""
        return self.tools.get(name)
