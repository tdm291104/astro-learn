"""Top-level supervisor agent that plans, routes, and dispatches sub-agents."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import date
from typing import Any, Final, Literal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.base.agent_message import AgentMessage
from agents.base.agent_registry import AgentRegistry
from agents.base.agent_state import AgentState
from agents.base.base_agent import BaseAgent
from agents.orchestrator.router import Router, _rule_agent_name
from agents.orchestrator.task_planner import PlannedStep, TaskPlan, TaskPlanner
from core.exceptions import AgentError, ExternalServiceError, ToolError
from core.llm.llm_client import LLMClient
from memory.short_term.conversation_memory import ConversationMemory
from repositories.message_repository import MessageRepository
from repositories.session_repository import SessionRepository
from tools.base_tool import BaseTool

_orchestrator_logger = structlog.get_logger(__name__)

# Sentinel kept in sync with router._NASA_DIRECT_AGENT.
_NASA_DIRECT_SENTINEL: Final[str] = "nasa_direct"

# Sentinel kept in sync with router._WEB_SEARCH_DIRECT_AGENT.
_WEB_SEARCH_DIRECT_SENTINEL: Final[str] = "web_search_direct"

# Sentinel kept in sync with router._CATALOG_MULTI_SEARCH_AGENT.
_CATALOG_MULTI_SEARCH_SENTINEL: Final[str] = "catalog_multi_search"

# Sentinel kept in sync with router._MODE_HINT_AGENT.
_MODE_HINT_SENTINEL: Final[str] = "mode_hint"

_MODE_LABEL: Final[dict[str, str]] = {
    "notebook": "Notebook",
    "fits": "FITS",
    "catalog": "Catalog",
    "general": "General",
}

# In notebook mode, these agent steps emit panel artefacts — the chat shows
# a friendly redirect rather than the raw JSON / bullet payload.
_NOTEBOOK_TOOL_AGENTS: Final[frozenset[str]] = frozenset(
    {"summarizer", "quiz", "flashcard"}
)

# agent_name → frontend panel key + artifact kind for upsert.
_NOTEBOOK_TOOL_PANEL_KEY: Final[dict[str, str]] = {
    "summarizer": "summary",
    "quiz": "quiz",
    "flashcard": "flashcards",
}
_NOTEBOOK_TOOL_ARTIFACT_KIND: Final[dict[str, str]] = {
    "summarizer": "summary",
    "quiz": "quiz",
    "flashcard": "flashcards",
}

_NOTEBOOK_TOOL_PANEL_LABEL: Final[dict[str, str]] = {
    "summary": "Summary",
    "quiz": "Quiz",
    "flashcards": "Flashcards",
}

# Cap per source so the merged grounding stays bounded.
_CATALOG_MULTI_SOURCE_LIMIT: Final[int] = 10

# Sources tried in order; results gain `_source` so the FE can label rows.
_CATALOG_MULTI_SOURCES: Final[tuple[str, ...]] = ("simbad", "ned", "vizier")

# Per-source timeout; Astroquery TAP can wedge for 30s+ without help.
_CATALOG_MULTI_PER_SOURCE_TIMEOUT_S: Final[float] = 20.0


_AgentFactory = Callable[[str], BaseAgent]


# Hard ceiling: Groq+LiteLLM can enter retry loops; cut losses here.
_PLANNER_TIMEOUT_S: Final[float] = 30.0

# Yields ~5 heartbeats over 30s — UI proof-of-life without flooding SSE.
_PLANNER_HEARTBEAT_INTERVAL_S: Final[float] = 5.0

# Fail open to "task" if classifier exceeds this; keeps bound at ~35s total.
_INTENT_CLASSIFIER_TIMEOUT_S: Final[float] = 5.0

_CHAT_RESPONSE_TIMEOUT_S: Final[float] = 30.0

# Matches frontend HISTORY_LIMIT in useChat.ts.
_MEMORY_HISTORY_LIMIT: Final[int] = 8


_OFF_TOPIC_DECLINE_MESSAGE: Final[str] = (
    "That's outside what I can help with. I'm specialized in "
    "astronomy research and notebook learning tools. Try asking about "
    "your notebooks or astronomical objects!"
)


_WEB_SEARCH_UNAVAILABLE_MESSAGE: Final[str] = (
    "I couldn't search the web right now. Please try again later or "
    "narrow your question to something I can answer from your notebooks."
)

# Matches WebSearchTool default max_results=5.
_WEB_SEARCH_RENDER_LIMIT: Final[int] = 5


_FRIENDLY_FALLBACK_MESSAGE: Final[str] = (
    "I'm not sure how to help with that. Try asking about your "
    "notebook (summarize, quiz, Q&A) or an astronomical object "
    "(search Simbad, analyze FITS)."
)


_CHAT_ERROR_FALLBACK: Final[str] = (
    "I had trouble responding just now. Please try again in a moment."
)


# Skip LLM intent call when free text contains astronomy keywords.
_ASTRONOMY_KEYWORDS: Final[re.Pattern[str]] = re.compile(
    r"\b(?:nebula|galaxy|galaxies|star|stars|simbad|ned|vizier|orion|"
    r"andromeda|milky\s*way|m\d+|ngc|astronom|fits|telescope|cluster|"
    r"planet|moon|sun|comet|asteroid|supernova|black\s*hole|quasar|pulsar|"
    r"spectrum|spectra|redshift|magnitude|RA[, ]+Dec)\b",
    re.IGNORECASE,
)


# Verb-first start = action intent; matches only at blob start.
_TASK_IMPERATIVES: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:summari[sz]e|quiz|flashcards?|q\s*&\s*a|qa|"
    r"search|find|look\s+up|analy[sz]e|upload|index|"
    r"generate|create|make|show|list|"
    r"tell\s+me\s+about|what\s+(?:can\s+you\s+find|do\s+you\s+know)\s+about)\b",
    re.IGNORECASE,
)


# Kept consistent with router rules so heuristics see same input.
_QUERY_FIELDS: Final[tuple[str, ...]] = ("query", "task", "description", "request")


# Order doubles as priority on multi-match LLM output.
Intent = Literal["chat", "task", "off_topic"]
_INTENT_LABELS: Final[tuple[Intent, ...]] = ("chat", "task", "off_topic")


_INTENT_CLASSIFIER_SYSTEM_PROMPT: Final[str] = (
    "Classify the user message into exactly one word: "
    "chat, task, or off_topic.\n\n"
    "chat = casual conversation, greetings, general knowledge "
    "questions, or questions about your capabilities.\n"
    "task = astronomy research or notebook operations.\n"
    "off_topic = unrelated requests we cannot help with.\n\n"
    "Examples:\n"
    "'Hello' -> chat\n"
    "'What can you do?' -> chat\n"
    "'How are you?' -> chat\n"
    "'What is a pulsar?' -> chat\n"
    "'Summarize my notebook' -> task\n"
    "'Search for M31' -> task\n"
    "'Write me a poem about love' -> off_topic\n"
    "'Help me code a website' -> off_topic\n\n"
    "Reply with exactly one word only."
)


_CONVERSATIONAL_SYSTEM_PROMPT: Final[str] = (
    "You are AstroLearn, an astronomy research assistant. "
    "Answer conversationally and helpfully. If asked what you can do, "
    "explain your capabilities (notebook Q&A, summarize, quiz, "
    "flashcards, FITS analysis, catalog search). "
    "Keep responses concise. "
    "ALWAYS reply in the same natural language as the user's latest message."
)


def _free_text_blob(task: dict[str, Any]) -> str:
    """Concatenate free-text fields for keyword scanning."""
    parts: list[str] = []
    for key in _QUERY_FIELDS:
        value = task.get(key)
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts)


def _has_clear_signal(task: dict[str, Any]) -> bool:
    """True if task has structural anchor or astronomy/imperative keyword."""
    if task.get("notebook_id") or task.get("file_id") or task.get("question"):
        return True
    if task.get("mode") == "catalog" and task.get("catalog_results"):
        return True
    blob = _free_text_blob(task).strip()
    if not blob:
        return False
    if _ASTRONOMY_KEYWORDS.search(blob):
        return True
    return _TASK_IMPERATIVES.match(blob) is not None


def _extract_user_text(task: dict[str, Any]) -> str:
    """Best candidate text for chat/classifier LLM."""
    for key in ("query", "question", "task"):
        value = task.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in task.values():
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


# Cap stored tool results so a chatty agent doesn't bloat the DB row.
_PERSISTED_TOOL_RESULT_CHARS: Final[int] = 10_000


def _track_tool_invocation(
    message: AgentMessage,
    step_entry: dict[str, Any],
    pending: dict[str, dict[str, Any]],
) -> None:
    """Fold tool_calls / tool results / progress narration into the trail."""
    # Intermediate narration ("Planning to run: …") enriches the rationale.
    if (
        message.role == "assistant"
        and message.content
        and message.extra.get("is_progress")
    ):
        existing = step_entry.get("rationale")
        step_entry["rationale"] = (
            f"{existing}\n\n{message.content}" if existing else message.content
        )
        return
    if message.role == "assistant" and message.tool_calls:
        for tc in message.tool_calls:
            inv = {
                "name": tc.name,
                "arguments": tc.arguments,
                "result": None,
            }
            step_entry["tool_invocations"].append(inv)
            if tc.id:
                pending[tc.id] = inv
        return
    if message.role == "tool":
        content = message.content or ""
        if len(content) > _PERSISTED_TOOL_RESULT_CHARS:
            content = content[:_PERSISTED_TOOL_RESULT_CHARS] + "…"
        target: dict[str, Any] | None = None
        if message.tool_call_id and message.tool_call_id in pending:
            target = pending.pop(message.tool_call_id)
        elif step_entry["tool_invocations"]:
            # Fallback: pair with the most recent un-resolved invocation.
            for inv in reversed(step_entry["tool_invocations"]):
                if inv["result"] is None:
                    target = inv
                    break
        if target is None:
            # Orphan tool result with no matching call; record on its own.
            step_entry["tool_invocations"].append({
                "name": message.name or "tool",
                "arguments": None,
                "result": content,
            })
            return
        target["result"] = content
        if message.name and target.get("name") in (None, "tool"):
            target["name"] = message.name


# Matches History sheet truncation.
_SESSION_TITLE_MAX_LEN: Final[int] = 60


def _derive_session_title(user_text: str) -> str:
    """Collapse user text into single-line title; empty if blank."""
    flat = " ".join(user_text.split())
    if not flat:
        return ""
    if len(flat) <= _SESSION_TITLE_MAX_LEN:
        return flat
    return flat[: _SESSION_TITLE_MAX_LEN - 1].rstrip() + "…"


def _parse_intent_label(raw: str) -> Intent:
    """Tolerant label parse; default to 'task' on hallucination."""
    text = raw.strip().lower()
    for label in _INTENT_LABELS:
        if label in text:
            return label
    return "task"


@AgentRegistry.register
class OrchestratorAgent(BaseAgent):
    """Coordinates other agents to fulfil a task."""

    name = "orchestrator"
    description = (
        "Routes a high-level task to the right specialist agent(s). "
        "Use this when you don't already know which agent to call."
    )
    capabilities = ["task_decomposition", "agent_routing", "result_aggregation"]

    def __init__(
        self,
        llm: LLMClient,
        tools: list[BaseTool] | None = None,
        *,
        planner: TaskPlanner | None = None,
        router: Router | None = None,
        factory: _AgentFactory | None = None,
        conversation_memory: ConversationMemory | None = None,
        memory_enabled: bool = True,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        super().__init__(llm=llm, tools=tools)
        # Recursion guard: planner must not pick the orchestrator itself.
        plannable = [n for n in AgentRegistry.names() if n != self.name]
        self.planner = planner or TaskPlanner(llm=llm, available_agents=plannable)
        self.router = router or Router(llm=llm)
        # Fallback factory builds tool-less agents (test path).
        self.factory: _AgentFactory = factory or self._fallback_factory
        self.conversation_memory = conversation_memory
        self.memory_enabled = memory_enabled
        # Redis = hot context window; DB session_factory = cold replay store.
        self._db_session_factory = session_factory

    async def run(
        self,
        task: dict[str, Any],
        *,
        state: AgentState | None = None,
    ) -> AgentState:
        """Classify intent then plan, route, dispatch, and aggregate."""
        state = state or AgentState(agent_name=self.name)
        self._record_user_task(state, task)
        await self._load_history(state, task)

        # Mode-mismatch hint short-circuit — never dispatch to a sub-agent
        # when the user is clearly in the wrong mode.
        mode_hint_params = self._match_mode_hint(task)
        if mode_hint_params is not None:
            hint_msg = self._handle_mode_hint(
                mode_hint_params, state, yield_to=None,
            )
            await self._persist_turn(
                state, task, hint_msg.content, assistant_extra=hint_msg.extra or None,
            )
            return state

        # NASA short-cut bypasses LLM classification.
        nasa_params = self._match_nasa_direct(task)
        if nasa_params is not None:
            nasa_msg = await self._handle_nasa_direct(nasa_params, state, yield_to=None)
            await self._persist_turn(state, task, nasa_msg.content)
            return state

        # Web-search short-cut: same bypass pattern.
        web_params = self._match_web_search_direct(task)
        if web_params is not None:
            web_msg = await self._handle_web_search_direct(
                web_params, state, yield_to=None,
            )
            await self._persist_turn(state, task, web_msg.content)
            return state

        # Catalog multi-source short-cut (mode='catalog' first turn).
        catalog_params = self._match_catalog_multi_search(task)
        if catalog_params is not None:
            cat_msg = await self._handle_catalog_multi_search(
                catalog_params, state, yield_to=None,
            )
            await self._persist_turn(
                state,
                task,
                cat_msg.content,
                assistant_extra=cat_msg.extra or None,
            )
            return state

        intent = await self._classify_intent_or_default(task)
        if intent == "off_topic":
            off_topic_msg = self._emit_off_topic(state)
            await self._persist_turn(state, task, off_topic_msg.content)
            return state
        if intent == "chat":
            chat_msg = await self._handle_chat(task, state, yield_to=None)
            # Skip persisting degraded replies; they'd derail follow-up context.
            if not chat_msg.extra.get("chat_error"):
                await self._persist_turn(state, task, chat_msg.content)
            return state

        plan = await self._plan(task)
        if not plan.steps:
            text = plan.summary or _FRIENDLY_FALLBACK_MESSAGE
            state.append(AgentMessage(role="assistant", content=text))
            state.final_output = self._empty_output(plan)
            await self._persist_turn(state, task, text)
            return state

        step_outputs: dict[str, Any] = {}
        task_mode_run = task.get("mode")
        for i, step in enumerate(plan.steps):
            if len(plan.steps) > 1:
                state.append(self._step_notice(step))
            sub_state = await self._dispatch_step(step, state)
            for message in sub_state.messages:
                state.append(message)
            step_outputs[self._step_key(i, step)] = sub_state.final_output

            is_notebook_tool = (
                step.agent_name in _NOTEBOOK_TOOL_AGENTS
                and task_mode_run == "notebook"
            )
            if is_notebook_tool:
                panel_key = _NOTEBOOK_TOOL_PANEL_KEY[step.agent_name]
                notebook_id = step.task_input.get("notebook_id") or task.get(
                    "notebook_id"
                )
                payload = sub_state.final_output or {}
                if isinstance(payload, dict) and notebook_id:
                    await self._persist_notebook_artifact(
                        str(notebook_id), step.agent_name, payload
                    )
                state.append(
                    AgentMessage(
                        role="assistant",
                        content=self._build_notebook_redirect_content(panel_key),
                        extra={
                            "suggest_panel": panel_key,
                            "auto_open": True,
                            "notebook_id": str(notebook_id) if notebook_id else None,
                        },
                    )
                )

        state.final_output = {
            "summary": plan.summary,
            "step_outputs": step_outputs,
        }
        # Persist user-facing outcome, not full sub-agent transcript.
        await self._persist_turn(state, task, self._task_outcome_text(state, plan))
        return state

    async def stream(
        self,
        task: dict[str, Any],
        *,
        state: AgentState | None = None,
    ) -> AsyncIterator[AgentMessage]:
        """Stream messages from each sub-agent in plan order."""
        state = state or AgentState(agent_name=self.name)
        user_msg = self._record_user_task(state, task)
        yield user_msg
        await self._load_history(state, task)

        mode_hint_params = self._match_mode_hint(task)
        if mode_hint_params is not None:
            hint_msgs: list[AgentMessage] = []
            hint_reply = self._handle_mode_hint(
                mode_hint_params, state, yield_to=hint_msgs,
            )
            for msg in hint_msgs:
                yield msg
            await self._persist_turn(
                state, task, hint_reply.content,
                assistant_extra=hint_reply.extra or None,
            )
            return

        # Buffer-then-yield so the helper serves both run() and stream().
        nasa_params = self._match_nasa_direct(task)
        if nasa_params is not None:
            nasa_msgs: list[AgentMessage] = []
            nasa_reply = await self._handle_nasa_direct(
                nasa_params, state, yield_to=nasa_msgs
            )
            for msg in nasa_msgs:
                yield msg
            await self._persist_turn(state, task, nasa_reply.content)
            return

        web_params = self._match_web_search_direct(task)
        if web_params is not None:
            web_msgs: list[AgentMessage] = []
            web_reply = await self._handle_web_search_direct(
                web_params, state, yield_to=web_msgs,
            )
            for msg in web_msgs:
                yield msg
            await self._persist_turn(state, task, web_reply.content)
            return

        catalog_params = self._match_catalog_multi_search(task)
        if catalog_params is not None:
            cat_msgs: list[AgentMessage] = []
            cat_reply = await self._handle_catalog_multi_search(
                catalog_params, state, yield_to=cat_msgs,
            )
            for msg in cat_msgs:
                yield msg
            await self._persist_turn(
                state,
                task,
                cat_reply.content,
                assistant_extra=cat_reply.extra or None,
            )
            return

        intent = await self._classify_intent_or_default(task)
        if intent == "off_topic":
            off_topic_msg = self._emit_off_topic(state)
            yield off_topic_msg
            await self._persist_turn(state, task, off_topic_msg.content)
            return
        if intent == "chat":
            chat_msgs: list[AgentMessage] = []
            chat_reply = await self._handle_chat(task, state, yield_to=chat_msgs)
            for msg in chat_msgs:
                yield msg
            if not chat_reply.extra.get("chat_error"):
                await self._persist_turn(state, task, chat_reply.content)
            return

        # Concurrent heartbeats keep SSE alive during slow planner calls.
        async for hb in self._plan_with_heartbeats(task):
            if isinstance(hb, AgentMessage):
                yield hb
            else:
                plan = hb
                break
        if not plan.steps:
            text = plan.summary or _FRIENDLY_FALLBACK_MESSAGE
            fallback = AgentMessage(role="assistant", content=text)
            state.append(fallback)
            yield fallback
            state.final_output = self._empty_output(plan)
            await self._persist_turn(state, task, text)
            return

        # Emit the plan up-front so the user sees the agent's reasoning.
        plan_notice = self._plan_notice(plan)
        if plan_notice is not None:
            state.append(plan_notice)
            yield plan_notice

        step_outputs: dict[str, Any] = {}
        total = len(plan.steps)
        # Persisted trail mirrors what the FE renders in the "Reasoning" pane.
        reasoning_trail: list[dict[str, Any]] = []
        final_extra: dict[str, Any] = {}
        task_mode = task.get("mode")
        for i, step in enumerate(plan.steps):
            notice = self._step_notice(step, index=i, total=total)
            state.append(notice)
            yield notice
            step_entry: dict[str, Any] = {
                "agent_name": step.agent_name,
                "rationale": step.rationale,
                "tool_invocations": [],
            }
            reasoning_trail.append(step_entry)
            pending_tool_calls: dict[str, dict[str, Any]] = {}
            agent = self.factory(step.agent_name)
            sub_state = self._sub_state(step, state)
            is_notebook_tool = (
                step.agent_name in _NOTEBOOK_TOOL_AGENTS
                and task_mode == "notebook"
            )
            async for message in agent.stream(step.task_input, state=sub_state):
                state.append(message)
                if is_notebook_tool and message.role == "assistant":
                    # Hide raw payload in chat; existing reasoning folding
                    # (`isReasoningFragment` checks is_progress) keeps it on
                    # the reasoning trail without rendering a bubble.
                    cloaked_extra = dict(message.extra or {})
                    cloaked_extra["is_progress"] = True
                    cloaked = AgentMessage(
                        role=message.role,
                        content=message.content,
                        name=message.name,
                        tool_calls=message.tool_calls,
                        tool_call_id=message.tool_call_id,
                        extra=cloaked_extra,
                    )
                    yield cloaked
                else:
                    yield message
                _track_tool_invocation(message, step_entry, pending_tool_calls)
                if message.role == "assistant" and message.extra:
                    # Last assistant extras win (citations / catalog_grounding).
                    final_extra.update(message.extra)
            step_outputs[self._step_key(i, step)] = sub_state.final_output

            if is_notebook_tool:
                panel_key = _NOTEBOOK_TOOL_PANEL_KEY[step.agent_name]
                notebook_id = step.task_input.get("notebook_id") or task.get(
                    "notebook_id"
                )
                payload = sub_state.final_output or {}
                if isinstance(payload, dict) and notebook_id:
                    await self._persist_notebook_artifact(
                        str(notebook_id), step.agent_name, payload
                    )
                redirect = AgentMessage(
                    role="assistant",
                    content=self._build_notebook_redirect_content(panel_key),
                    extra={
                        "suggest_panel": panel_key,
                        "auto_open": True,
                        "notebook_id": str(notebook_id) if notebook_id else None,
                    },
                )
                state.append(redirect)
                yield redirect

        state.final_output = {
            "summary": plan.summary,
            "step_outputs": step_outputs,
        }
        assistant_extra: dict[str, Any] = {
            "reasoning": {
                "plan_summary": plan.summary,
                "steps": reasoning_trail,
            },
        }
        if "citations" in final_extra:
            assistant_extra["citations"] = final_extra["citations"]
        if "catalog_grounding" in final_extra:
            assistant_extra["catalog_grounding"] = final_extra["catalog_grounding"]
        await self._persist_turn(
            state,
            task,
            self._task_outcome_text(state, plan),
            assistant_extra=assistant_extra,
        )

    async def _dispatch_step(
        self,
        step: PlannedStep,
        state: AgentState,
    ) -> AgentState:
        agent = self.factory(step.agent_name)
        sub_state = self._sub_state(step, state)
        return await agent.run(step.task_input, state=sub_state)

    async def _plan_with_heartbeats(
        self,
        task: dict[str, Any],
    ) -> AsyncIterator[AgentMessage | TaskPlan]:
        """Drive _plan() concurrently with periodic heartbeats."""
        planner_task = asyncio.create_task(self._plan(task))
        try:
            while True:
                # asyncio.wait (vs wait_for) doesn't cancel on timeout.
                done, _ = await asyncio.wait(
                    {planner_task}, timeout=_PLANNER_HEARTBEAT_INTERVAL_S,
                )
                if planner_task in done:
                    break
                yield self._planner_heartbeat()
        except BaseException:
            # Don't leak the planner task on consumer disconnect.
            planner_task.cancel()
            raise
        yield planner_task.result()

    @staticmethod
    def _planner_heartbeat() -> AgentMessage:
        return AgentMessage(
            role="system",
            content="planning",
            extra={"heartbeat": True, "phase": "planning"},
        )

    async def _plan(self, task: dict[str, Any]) -> TaskPlan:
        """Cheap path (router rule) first; else hand off to planner."""
        matched = self._try_router_rules(task)
        if matched is not None:
            picked, rule_task_input = matched
            # No rationale on the rule path — the LLM-free shortcut has no
            # natural-language reasoning to show, and the placeholder noise
            # was always English.
            return TaskPlan(
                steps=[
                    PlannedStep(
                        agent_name=picked,
                        task_input=rule_task_input,
                        rationale=None,
                    )
                ],
            )
        # Hide agents whose required resource isn't bound so the planner LLM
        # cannot pick (and hallucinate IDs for) e.g. summarizer without a
        # notebook_id. Repro: "Tôi muốn tạo notebooks" in general mode used
        # to crash summarizer with notebook_id='new_notebook'.
        effective_agents = self._effective_planner_agents(task)
        # wait_for caps Groq+LiteLLM silent retry loops.
        try:
            return await asyncio.wait_for(
                self.planner.plan(task, available_agents=effective_agents),
                timeout=_PLANNER_TIMEOUT_S,
            )
        except TimeoutError:
            return TaskPlan(
                steps=[],
                summary=(
                    "The planner took too long to respond. "
                    "Please try rephrasing your request."
                ),
            )

    def _effective_planner_agents(self, task: dict[str, Any]) -> list[str]:
        """Drop agents whose required resource isn't bound on `task`."""
        has_notebook = bool(task.get("notebook_id"))
        has_file = bool(task.get("file_id"))
        notebook_only = {"summarizer", "quiz", "flashcard", "qa"}
        fits_only = {
            "fits_analyst",
            "data_analyst",
            "reflexion_data_analyst",
            "image_processor",
        }
        out: list[str] = []
        for name in self.planner.available_agents:
            if name in notebook_only and not has_notebook:
                continue
            if name in fits_only and not has_file:
                continue
            out.append(name)
        return out

    def _try_router_rules(
        self, task: dict[str, Any]
    ) -> tuple[str, dict[str, Any]] | None:
        """Walk router rules without invoking the LLM fallback."""
        for rule in self.router.rules:
            try:
                result = rule(task)
            except Exception:
                continue
            picked = _rule_agent_name(result)
            if not picked or not AgentRegistry.has(picked):
                continue
            if isinstance(result, tuple):
                _, rule_task_input = result
                return picked, rule_task_input
            # Bare-string rule forwards task unchanged.
            return picked, task
        return None

    async def _classify_intent_or_default(self, task: dict[str, Any]) -> Intent:
        if _has_clear_signal(task):
            return "task"
        user_text = _extract_user_text(task)
        if not user_text:
            return "off_topic"
        try:
            raw = await asyncio.wait_for(
                self.llm.complete(
                    [
                        {"role": "system", "content": _INTENT_CLASSIFIER_SYSTEM_PROMPT},
                        {"role": "user", "content": user_text},
                    ],
                    temperature=0.0,
                    max_tokens=10,
                ),
                timeout=_INTENT_CLASSIFIER_TIMEOUT_S,
            )
        except Exception:
            # Fail open: planner is a richer fallback than a 500.
            return "task"
        return _parse_intent_label(raw)

    async def _handle_chat(
        self,
        task: dict[str, Any],
        state: AgentState,
        *,
        yield_to: list[AgentMessage] | None,
    ) -> AgentMessage:
        """One-shot conversational reply for intent == chat."""
        messages = self._build_chat_messages(task)
        reply: str
        error_kind: str | None = None
        try:
            raw = await asyncio.wait_for(
                self.llm.complete(
                    messages,
                    temperature=0.7,
                    max_tokens=300,
                ),
                timeout=_CHAT_RESPONSE_TIMEOUT_S,
            )
            stripped = raw.strip()
            if stripped:
                reply = stripped
            else:
                # Treat empty reply as failure so UI can warn.
                reply = _CHAT_ERROR_FALLBACK
                error_kind = "empty_reply"
        except TimeoutError:
            reply = _CHAT_ERROR_FALLBACK
            error_kind = "timeout"
        except Exception:
            reply = _CHAT_ERROR_FALLBACK
            error_kind = "llm_failure"

        if error_kind is not None:
            msg = AgentMessage(
                role="assistant",
                content=reply,
                extra={"chat_error": True, "error_kind": error_kind},
            )
            state.final_output = {
                "mode": "chat_error",
                "response": reply,
                "error_kind": error_kind,
            }
        else:
            msg = AgentMessage(role="assistant", content=reply)
            state.final_output = {"mode": "chat", "response": reply}

        state.append(msg)
        if yield_to is not None:
            yield_to.append(msg)
        return msg

    @staticmethod
    def _build_chat_messages(task: dict[str, Any]) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": _CONVERSATIONAL_SYSTEM_PROMPT}
        ]
        history = task.get("history")
        appended = False
        if isinstance(history, list):
            for item in history:
                if not isinstance(item, dict):
                    continue
                role = item.get("role")
                content = item.get("content")
                if role in ("user", "assistant") and isinstance(content, str):
                    messages.append({"role": role, "content": content})
                    appended = True
        if not appended:
            messages.append({"role": "user", "content": _extract_user_text(task)})
        return messages

    def _match_nasa_direct(self, task: dict[str, Any]) -> dict[str, Any] | None:
        """Walk router rules for the nasa_direct sentinel."""
        for rule in self.router.rules:
            try:
                result = rule(task)
            except Exception:
                continue
            if (
                isinstance(result, tuple)
                and len(result) == 2
                and result[0] == _NASA_DIRECT_SENTINEL
            ):
                params = result[1]
                if isinstance(params, dict):
                    return params
        return None

    async def _handle_nasa_direct(
        self,
        params: dict[str, Any],
        state: AgentState,
        *,
        yield_to: list[AgentMessage] | None,
    ) -> AgentMessage:
        """Call NasaApiTool inline; emit formatted assistant message."""
        endpoint = params.get("endpoint")
        tool = self.get_tool("nasa_api")

        if tool is None:
            return self._finalise_nasa(
                state,
                endpoint=endpoint,
                text=(
                    "The NASA discovery feature isn't available right now. "
                    "Please try again later."
                ),
                result=None,
                yield_to=yield_to,
            )

        try:
            if endpoint == "apod":
                result = await tool(endpoint="apod")
                text = _format_apod(result)
            elif endpoint == "neo":
                neo_date = params.get("date") or date.today().isoformat()
                result = await tool(
                    endpoint="neo_feed",
                    params={"start_date": neo_date, "end_date": neo_date},
                )
                text = _format_neo(result, neo_date)
            else:
                # Defensive: unknown endpoint matched sentinel.
                return self._finalise_nasa(
                    state,
                    endpoint=endpoint,
                    text=f"Unknown NASA endpoint: {endpoint!r}.",
                    result=None,
                    yield_to=yield_to,
                )
        except (ToolError, ExternalServiceError) as exc:
            return self._finalise_nasa(
                state,
                endpoint=endpoint,
                text=f"Couldn't reach NASA right now ({exc.code}). Try again shortly.",
                result=None,
                yield_to=yield_to,
            )

        return self._finalise_nasa(
            state,
            endpoint=endpoint,
            text=text,
            result=result,
            yield_to=yield_to,
        )

    def _match_web_search_direct(
        self, task: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Walk router rules for the web_search_direct sentinel."""
        for rule in self.router.rules:
            try:
                result = rule(task)
            except Exception:
                continue
            if (
                isinstance(result, tuple)
                and len(result) == 2
                and result[0] == _WEB_SEARCH_DIRECT_SENTINEL
            ):
                params = result[1]
                if isinstance(params, dict):
                    return params
        return None

    def _match_mode_hint(
        self, task: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Walk router rules for the mode_hint sentinel."""
        for rule in self.router.rules:
            try:
                result = rule(task)
            except Exception:
                continue
            if (
                isinstance(result, tuple)
                and len(result) == 2
                and result[0] == _MODE_HINT_SENTINEL
            ):
                params = result[1]
                if isinstance(params, dict):
                    return params
        return None

    def _handle_mode_hint(
        self,
        params: dict[str, Any],
        state: AgentState,
        *,
        yield_to: list[AgentMessage] | None,
    ) -> AgentMessage:
        """Emit a friendly mode-mismatch hint with a clickable target mode."""
        target_raw = params.get("suggest_mode")
        target = target_raw if isinstance(target_raw, str) else "general"
        reason = params.get("reason")
        label = _MODE_LABEL.get(target, target.capitalize())

        # Mode is correct, but the mode needs a bound resource (notebook /
        # FITS file) to function. Skip the "switch tab" copy and tell the
        # user how to unstick themselves.
        if reason == "notebook_mode_needs_notebook":
            text = (
                "Bạn đang ở mode Notebook nhưng chưa chọn notebook nào. "
                "Hãy chọn một notebook từ panel bên trái (hoặc tạo mới) "
                "trước khi đặt câu hỏi."
            )
            extra: dict[str, Any] = {
                "binding_action": "pick_or_create_notebook",
                "reason": reason,
            }
        elif reason == "fits_mode_needs_file":
            text = (
                "Bạn đang ở mode FITS nhưng chưa chọn file FITS nào. "
                "Hãy upload hoặc chọn một file từ panel bên trái trước "
                "khi đặt câu hỏi."
            )
            extra = {
                "binding_action": "pick_or_upload_fits",
                "reason": reason,
            }
        else:
            text = (
                f"Câu hỏi này phù hợp với mode {label} hơn. "
                f"Bấm vào tab {label} để hỏi lại nhé."
            )
            extra = {
                "suggest_mode": target,
                "reason": reason,
            }

        msg = AgentMessage(role="assistant", content=text, extra=extra)
        state.append(msg)
        state.final_output = {
            "mode": "mode_hint",
            "suggest_mode": target,
            "reason": reason,
        }
        if yield_to is not None:
            yield_to.append(msg)
        return msg

    def _match_catalog_multi_search(
        self, task: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Walk router rules for the catalog_multi_search sentinel."""
        for rule in self.router.rules:
            try:
                result = rule(task)
            except Exception:
                continue
            if (
                isinstance(result, tuple)
                and len(result) == 2
                and result[0] == _CATALOG_MULTI_SEARCH_SENTINEL
            ):
                params = result[1]
                if isinstance(params, dict):
                    return params
        return None

    async def _handle_catalog_multi_search(
        self,
        params: dict[str, Any],
        state: AgentState,
        *,
        yield_to: list[AgentMessage] | None,
    ) -> AgentMessage:
        """Fan out to CatalogAgent for Simbad/NED/VizieR in parallel.

        On any non-empty result: emit a regular catalog-grounded reply so the
        FE's existing catalog renderer picks it up. On all-empty: emit a
        prompt with `extra.action="confirm_web_search"` for the FE to render
        Yes/No buttons.
        """
        query_raw = params.get("query")
        query = (query_raw if isinstance(query_raw, str) else "").strip()
        raw_question = params.get("raw_question") or query

        if not query:
            return self._finalise_catalog_multi(
                state,
                query="",
                raw_question=raw_question,
                text=_FRIENDLY_FALLBACK_MESSAGE,
                results=[],
                yield_to=yield_to,
            )

        async def _query_source(source: str) -> tuple[str, list[dict[str, Any]]]:
            agent = self.factory("catalog")
            sub_state = AgentState(
                agent_name="catalog",
                user_id=state.user_id,
                session_id=state.session_id,
            )
            try:
                result_state = await asyncio.wait_for(
                    agent.run(
                        {
                            "query": query,
                            "source": source,
                            "limit": _CATALOG_MULTI_SOURCE_LIMIT,
                        },
                        state=sub_state,
                    ),
                    timeout=_CATALOG_MULTI_PER_SOURCE_TIMEOUT_S,
                )
            except (TimeoutError, ToolError, ExternalServiceError, AgentError):
                return source, []
            except Exception:  # noqa: BLE001 — never crash multi-search on one source
                return source, []
            rows = (result_state.final_output or {}).get("results") or []
            if not isinstance(rows, list):
                return source, []
            tagged: list[dict[str, Any]] = []
            for row in rows[:_CATALOG_MULTI_SOURCE_LIMIT]:
                if isinstance(row, dict):
                    tagged.append({**row, "_source": source})
            return source, tagged

        per_source = await asyncio.gather(
            *(_query_source(src) for src in _CATALOG_MULTI_SOURCES)
        )
        merged: list[dict[str, Any]] = []
        per_source_counts: dict[str, int] = {}
        for source, rows in per_source:
            per_source_counts[source] = len(rows)
            merged.extend(rows)

        if merged:
            text = _format_catalog_multi(query, per_source_counts)
            return self._finalise_catalog_multi(
                state,
                query=query,
                raw_question=raw_question,
                text=text,
                results=merged,
                yield_to=yield_to,
                per_source_counts=per_source_counts,
            )

        # All three returned empty → prompt user to confirm web fallback.
        text = (
            f"Không tìm thấy kết quả cho {query!r} trong Simbad, NED hay VizieR. "
            "Bạn có muốn em tìm trên internet không?"
        )
        msg = AgentMessage(
            role="assistant",
            content=text,
            extra={
                "action": "confirm_web_search",
                "query": raw_question,
            },
        )
        state.append(msg)
        state.final_output = {
            "mode": "catalog_empty_confirm",
            "query": raw_question,
            "tried_sources": list(_CATALOG_MULTI_SOURCES),
        }
        if yield_to is not None:
            yield_to.append(msg)
        return msg

    @staticmethod
    def _finalise_catalog_multi(
        state: AgentState,
        *,
        query: str,
        raw_question: str,
        text: str,
        results: list[Any],
        yield_to: list[AgentMessage] | None,
        per_source_counts: dict[str, int] | None = None,
    ) -> AgentMessage:
        # Project to the row shape the FE catalog-grounding renderer expects.
        grounding_rows: list[dict[str, Any]] = []
        for row in results[:_CATALOG_MULTI_SOURCE_LIMIT]:
            if not isinstance(row, dict):
                continue
            grounding_rows.append({
                "name": row.get("name") or row.get("main_id") or "(unnamed)",
                "object_type": row.get("object_type"),
                "ra_deg": row.get("ra_deg"),
                "dec_deg": row.get("dec_deg"),
            })

        active_sources = [
            src for src in _CATALOG_MULTI_SOURCES
            if (per_source_counts or {}).get(src, 0) > 0
        ]
        source_label = "+".join(active_sources) if active_sources else "multi"

        extra: dict[str, Any] = {
            "catalog_grounding": {
                "query": query,
                "source": source_label,
                "row_count": len(results),
                "rows": grounding_rows,
            },
            "catalog_results": results,
            "catalog_multi_source_counts": per_source_counts or {},
        }
        msg = AgentMessage(role="assistant", content=text, extra=extra)
        state.append(msg)
        state.final_output = {
            "mode": "catalog_multi_search",
            "query": query,
            "raw_question": raw_question,
            "results": results,
            "per_source_counts": per_source_counts or {},
        }
        if yield_to is not None:
            yield_to.append(msg)
        return msg

    async def _handle_web_search_direct(
        self,
        params: dict[str, Any],
        state: AgentState,
        *,
        yield_to: list[AgentMessage] | None,
    ) -> AgentMessage:
        """Call WebSearchTool inline; emit formatted assistant message."""
        query_raw = params.get("query")
        query = (query_raw if isinstance(query_raw, str) else "").strip()
        tool = self.get_tool("web_search")

        if tool is None or not query:
            return self._finalise_web_search(
                state,
                query=query,
                text=_WEB_SEARCH_UNAVAILABLE_MESSAGE,
                results=[],
                yield_to=yield_to,
            )

        try:
            raw = await tool(
                query=query,
                max_results=_WEB_SEARCH_RENDER_LIMIT,
            )
        except (ToolError, ExternalServiceError) as exc:
            return self._finalise_web_search(
                state,
                query=query,
                text=(
                    f"Couldn't search the web right now ({exc.code}). "
                    "Try again shortly."
                ),
                results=[],
                yield_to=yield_to,
            )

        results = raw if isinstance(raw, list) else []
        return self._finalise_web_search(
            state,
            query=query,
            text=_format_web_search(query, results),
            results=results,
            yield_to=yield_to,
        )

    @staticmethod
    def _finalise_web_search(
        state: AgentState,
        *,
        query: str,
        text: str,
        results: list[Any],
        yield_to: list[AgentMessage] | None,
    ) -> AgentMessage:
        msg = AgentMessage(role="assistant", content=text)
        state.append(msg)
        state.final_output = {
            "mode": "web_search",
            "query": query,
            "results": results,
        }
        if yield_to is not None:
            yield_to.append(msg)
        return msg

    @staticmethod
    def _finalise_nasa(
        state: AgentState,
        *,
        endpoint: Any,
        text: str,
        result: Any,
        yield_to: list[AgentMessage] | None,
    ) -> AgentMessage:
        msg = AgentMessage(role="assistant", content=text)
        state.append(msg)
        state.final_output = {
            "mode": "nasa_direct",
            "endpoint": endpoint,
            "result": result,
        }
        if yield_to is not None:
            yield_to.append(msg)
        return msg

    async def _persist_notebook_artifact(
        self,
        notebook_id: str,
        agent_name: str,
        payload: dict[str, Any],
    ) -> None:
        """Upsert summarizer/quiz/flashcard output to the notebook artifact row.

        Lets the FE panel show the chat-triggered result without re-running
        the agent. Best-effort — never blocks the SSE response on a DB blip.
        """
        if self._db_session_factory is None:
            return
        kind = _NOTEBOOK_TOOL_ARTIFACT_KIND.get(agent_name)
        if kind is None:
            return
        try:
            nb_uuid = uuid.UUID(str(notebook_id))
        except (ValueError, AttributeError, TypeError):
            return
        try:
            from repositories.notebook_artifact_repository import (
                NotebookArtifactRepository,
            )

            async with self._db_session_factory() as db:
                await NotebookArtifactRepository(db).upsert(
                    nb_uuid,
                    kind,
                    params={"source": "chat"},
                    payload=payload,
                )
                await db.commit()
        except Exception:  # noqa: BLE001 — best-effort persistence
            _orchestrator_logger.warning(
                "orchestrator.notebook_artifact_save_failed",
                notebook_id=str(notebook_id),
                kind=kind,
            )

    @staticmethod
    def _build_notebook_redirect_content(panel_key: str) -> str:
        """Friendly Vietnamese message replacing the raw agent payload."""
        label = _NOTEBOOK_TOOL_PANEL_LABEL.get(panel_key, panel_key)
        return (
            f"Đã tạo {label} cho notebook của bạn — panel {label} đang mở ở "
            f"bên phải để xem kết quả."
        )

    @staticmethod
    def _emit_off_topic(state: AgentState) -> AgentMessage:
        msg = AgentMessage(role="assistant", content=_OFF_TOPIC_DECLINE_MESSAGE)
        state.append(msg)
        state.final_output = {
            "mode": "off_topic",
            "response": _OFF_TOPIC_DECLINE_MESSAGE,
        }
        return msg

    def _memory_active(self, state: AgentState) -> bool:
        return (
            self.memory_enabled
            and self.conversation_memory is not None
            and state.session_id is not None
        )

    async def _load_history(
        self,
        state: AgentState,
        task: dict[str, Any],
    ) -> None:
        """Pre-populate task['history'] from memory; overrides inline on hit."""
        if not self._memory_active(state):
            return
        assert self.conversation_memory is not None
        assert state.session_id is not None
        msgs = await self.conversation_memory.history(
            state.session_id, limit=_MEMORY_HISTORY_LIMIT
        )
        if not msgs:
            return
        history: list[dict[str, str]] = [
            {"role": m.role, "content": m.content}
            for m in msgs
            if m.role in ("user", "assistant")
        ]
        # Tail current user turn to mirror inline-history layout.
        user_text = _extract_user_text(task)
        if user_text:
            history.append({"role": "user", "content": user_text})
        task["history"] = history

    async def _persist_turn(
        self,
        state: AgentState,
        task: dict[str, Any],
        assistant_content: str,
        *,
        assistant_extra: dict[str, Any] | None = None,
    ) -> None:
        """Append user + assistant turn to memory + DB."""
        if state.session_id is None:
            return
        user_text = _extract_user_text(task)
        if not user_text or not assistant_content:
            return

        # Hot path: Redis working window.
        if self._memory_active(state):
            assert self.conversation_memory is not None
            await self.conversation_memory.append_many(
                state.session_id,
                [
                    AgentMessage(role="user", content=user_text),
                    AgentMessage(role="assistant", content=assistant_content),
                ],
            )

        # Cold path: best-effort DB write must not break the streaming response.
        if self._db_session_factory is not None:
            try:
                await self._write_db_turn(
                    state.session_id,
                    user_text,
                    assistant_content,
                    assistant_extra=assistant_extra,
                )
            except Exception:  # noqa: BLE001 — best-effort persistence
                pass

    async def _write_db_turn(
        self,
        session_id: Any,
        user_text: str,
        assistant_content: str,
        *,
        assistant_extra: dict[str, Any] | None = None,
    ) -> None:
        """Insert user + assistant rows into messages."""
        assert self._db_session_factory is not None
        async with self._db_session_factory() as db:
            # Drop silently on stale session_id rather than FK error.
            sessions = SessionRepository(db)
            if not await sessions.exists(session_id):
                return
            messages = MessageRepository(db)
            await messages.create(
                {
                    "session_id": session_id,
                    "role": "user",
                    "content": user_text,
                    "extra": None,
                }
            )
            await messages.create(
                {
                    "session_id": session_id,
                    "role": "assistant",
                    "content": assistant_content,
                    "extra": assistant_extra or None,
                }
            )
            # Seed title from first user turn; preserves user-set titles.
            await sessions.set_title_if_unset(
                session_id, _derive_session_title(user_text)
            )
            await db.commit()

    @staticmethod
    def _task_outcome_text(state: AgentState, plan: TaskPlan) -> str:
        """Prefer plan.summary, else last assistant message."""
        if plan.summary:
            return plan.summary
        for msg in reversed(state.messages):
            if msg.role == "assistant" and msg.content:
                return msg.content
        return ""

    @staticmethod
    def _record_user_task(state: AgentState, task: dict[str, Any]) -> AgentMessage:
        msg = AgentMessage(role="user", content=json.dumps(task, default=str))
        state.append(msg)
        return msg

    @staticmethod
    def _sub_state(step: PlannedStep, parent: AgentState) -> AgentState:
        return AgentState(
            agent_name=step.agent_name,
            user_id=parent.user_id,
            session_id=parent.session_id,
        )

    @staticmethod
    def _step_key(index: int, step: PlannedStep) -> str:
        # Index disambiguates repeated agents.
        return f"step_{index}_{step.agent_name}"

    @staticmethod
    def _step_notice(
        step: PlannedStep, *, index: int = 0, total: int = 1
    ) -> AgentMessage:
        # `extra.step_kind="step"` flags this for the FE step renderer.
        return AgentMessage(
            role="system",
            content=f"→ Running: {step.agent_name}...",
            name=step.agent_name,
            extra={
                "step_kind": "step",
                "step_index": index,
                "step_total": total,
                "agent_name": step.agent_name,
                "rationale": step.rationale,
            },
        )

    @staticmethod
    def _plan_notice(plan: TaskPlan) -> AgentMessage | None:
        """One-shot reasoning preview shown before the steps execute."""
        steps_payload = [
            {
                "agent_name": s.agent_name,
                "rationale": s.rationale,
            }
            for s in plan.steps
        ]
        if not steps_payload and not plan.summary:
            return None
        # Plain text fallback so legacy renderers still show something useful.
        lines: list[str] = []
        if plan.summary:
            lines.append(plan.summary)
        for i, step in enumerate(plan.steps):
            tail = f" — {step.rationale}" if step.rationale else ""
            lines.append(f"{i + 1}. {step.agent_name}{tail}")
        return AgentMessage(
            role="system",
            content="\n".join(lines),
            extra={
                "step_kind": "plan",
                "summary": plan.summary,
                "steps": steps_payload,
            },
        )

    @staticmethod
    def _empty_output(plan: TaskPlan) -> dict[str, Any]:
        return {
            "summary": plan.summary or _FRIENDLY_FALLBACK_MESSAGE,
            "step_outputs": {},
        }

    def _fallback_factory(self, name: str) -> BaseAgent:
        """Tool-less factory for test path."""
        cls = AgentRegistry.get(name)
        return cls(llm=self.llm, tools=[])


_NEO_RENDER_LIMIT: Final[int] = 5


def _format_apod(data: dict[str, Any]) -> str:
    """Render APOD payload as chat string."""
    title = str(data.get("title") or "Astronomy Picture of the Day").strip()
    date_str = str(data.get("date") or "").strip()
    explanation = str(data.get("explanation") or "").strip()
    url = str(data.get("hdurl") or data.get("url") or "").strip()

    header = f"📸 {title}"
    if date_str:
        header += f" ({date_str})"

    parts = [header]
    if explanation:
        parts.append(explanation)
    if url:
        parts.append(f"Image: {url}")
    return "\n\n".join(parts)


def _format_catalog_multi(
    query: str, per_source_counts: dict[str, int]
) -> str:
    """Render a short summary of how many rows came from each catalog."""
    parts: list[str] = []
    labels = {"simbad": "Simbad", "ned": "NED", "vizier": "VizieR"}
    for src in _CATALOG_MULTI_SOURCES:
        n = per_source_counts.get(src, 0)
        if n > 0:
            parts.append(f"{labels.get(src, src)}: {n}")
    summary = ", ".join(parts) if parts else "no results"
    return (
        f"🔭 Catalog results for {query!r} — {summary}. "
        f"Open the table on the right for full rows."
    )


def _format_web_search(query: str, results: list[Any]) -> str:
    """Render WebSearchTool result list as chat string."""
    if not results:
        return f"🔍 No web results found for '{query}'."

    lines = [f"🔍 Web search results for '{query}':", ""]
    for i, raw in enumerate(results[:_WEB_SEARCH_RENDER_LIMIT], start=1):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "Untitled").strip() or "Untitled"
        url = str(raw.get("url") or "").strip()
        snippet = str(raw.get("snippet") or "").strip()
        head = f"{i}. **{title}**"
        if snippet:
            head = f"{head} — {snippet}"
        lines.append(head)
        if url:
            lines.append(f"   {url}")
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _format_neo(data: dict[str, Any], date_str: str) -> str:
    """Render NEO feed for one date as bullets."""
    feed = data.get("near_earth_objects")
    near_objects: list[dict[str, Any]] = []
    if isinstance(feed, dict):
        raw = feed.get(date_str)
        if isinstance(raw, list):
            near_objects = raw

    if not near_objects:
        return f"☄️ No near-Earth objects recorded for {date_str}."

    lines = [f"☄️ Near-Earth Objects for {date_str}:"]
    for obj in near_objects[:_NEO_RENDER_LIMIT]:
        name = str(obj.get("name") or "unknown").strip()
        approaches = obj.get("close_approach_data") or []
        miss_text = "?"
        if isinstance(approaches, list) and approaches:
            first = approaches[0] if isinstance(approaches[0], dict) else {}
            miss = (first.get("miss_distance") or {}).get("kilometers")
            try:
                miss_text = f"{float(miss):,.0f} km"
            except (TypeError, ValueError):
                miss_text = str(miss) if miss is not None else "?"
        lines.append(f"• {name}: {miss_text} away")
    return "\n".join(lines)
