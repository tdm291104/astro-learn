"""Inter-agent and agent-LLM message schema."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Mirrors schemas.session_schema.MessageRole.
AgentMessageRole = Literal["system", "user", "assistant", "tool"]


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentMessage(BaseModel):
    model_config = ConfigDict(frozen=False)

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    role: AgentMessageRole
    content: str = ""
    name: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None  # links to ToolCall.id when role="tool"
    extra: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_chat_dict(self) -> dict[str, Any]:
        """LiteLLM-compatible chat message dict."""
        msg: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name is not None:
            msg["name"] = self.name
        if self.tool_calls:
            # OpenAI shape: arguments is JSON-string, not dict.
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in self.tool_calls
            ]
        if self.tool_call_id is not None:
            msg["tool_call_id"] = self.tool_call_id
        return msg
