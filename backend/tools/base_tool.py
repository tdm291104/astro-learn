"""Abstract base class for all tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, ValidationError

from core.exceptions import ToolError


class BaseTool(ABC):
    """Strategy interface for an LLM-callable tool."""

    name: ClassVar[str]
    description: ClassVar[str]
    input_schema: ClassVar[type[BaseModel] | None] = None

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Run the tool with already-validated keyword arguments."""
        ...

    def to_openai_tool(self) -> dict[str, Any]:
        """Render this tool as an OpenAI / LiteLLM tool-spec dict."""
        if self.input_schema is not None:
            parameters: dict[str, Any] = self.input_schema.model_json_schema()
        else:
            parameters = {"type": "object", "properties": {}}
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }

    async def __call__(self, **kwargs: Any) -> Any:
        """Validate input against `input_schema` (if any) then call `execute`."""
        if self.input_schema is not None:
            try:
                validated = self.input_schema(**kwargs)
            except ValidationError as exc:
                raise ToolError(
                    message=f"Invalid input for tool {self.name!r}",
                    code="tool_invalid_input",
                    details={"errors": exc.errors()},
                ) from exc
            return await self.execute(**validated.model_dump())
        return await self.execute(**kwargs)
