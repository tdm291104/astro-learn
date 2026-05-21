"""Process-wide registry of agent classes — name to class lookup."""

from __future__ import annotations

from typing import ClassVar

from agents.base.base_agent import BaseAgent
from core.exceptions import AgentNotFoundError


class AgentRegistry:
    _agents: ClassVar[dict[str, type[BaseAgent]]] = {}

    @classmethod
    def register(cls, agent_class: type[BaseAgent]) -> type[BaseAgent]:
        name = getattr(agent_class, "name", None)
        if not name:
            raise ValueError(
                f"{agent_class.__name__} must set a non-empty `name` ClassVar"
            )
        if name in cls._agents and cls._agents[name] is not agent_class:
            raise ValueError(f"Agent name {name!r} is already registered")
        cls._agents[name] = agent_class
        return agent_class

    @classmethod
    def unregister(cls, name: str) -> None:
        cls._agents.pop(name, None)

    @classmethod
    def get(cls, name: str) -> type[BaseAgent]:
        try:
            return cls._agents[name]
        except KeyError as exc:
            raise AgentNotFoundError(
                message=f"No agent registered under name {name!r}",
                details={"available": sorted(cls._agents)},
            ) from exc

    @classmethod
    def has(cls, name: str) -> bool:
        return name in cls._agents

    @classmethod
    def list_agents(cls) -> list[type[BaseAgent]]:
        return list(cls._agents.values())

    @classmethod
    def names(cls) -> list[str]:
        return list(cls._agents.keys())
