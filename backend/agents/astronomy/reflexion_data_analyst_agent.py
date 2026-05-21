"""Reflexion data-analyst agent: ACT → CRITIQUE → REFINE with symbolic checker."""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from agents.base.agent_message import AgentMessage
from agents.base.agent_registry import AgentRegistry
from agents.base.agent_state import AgentState
from agents.base.base_agent import BaseAgent
from core.exceptions import AgentError, ToolError
from core.llm.llm_client import LLMClient
from tools.astronomy.symbolic_checker_tool import SymbolicFitsCheckerTool
from tools.base_tool import BaseTool

# Empirically optimal cap per thesis §5.6; 3 regresses on T3.
_DEFAULT_MAX_REFLECTIONS: int = int(os.getenv("FITSBENCH_MAX_REFLECTIONS", "2"))

_MAX_ACT_STEPS: int = 6

_NUMBER_RE: re.Pattern[str] = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")

_FENCE_PATTERN: re.Pattern[str] = re.compile(
    r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL
)

_SYSTEM_PROMPT = """You are an astronomical data-quality analyst.

Reply with a single JSON object — no prose outside it:
{"action": "call_tool", "tool": "<name>", "input": {...}}
or
{"action": "finish", "results": {...}, "summary": "<plain text explanation>"}

Tools available:
- fits_reader: open a FITS file by file_id and return HDU structure +
  headers + data summaries. Input: {"file_id": "<uuid>", "hdu_index": <int>}.
- astropy_compute: run an image or photometry computation on a FITS HDU.
  Input: {"file_id": "<uuid>", "operation": "image_stats"|"photometry",
  "hdu_index": <int>, ...}.

Your task is to analyse the file and surface every data-quality concern
you find: NaN regions, suspicious EXPTIME, NAXIS/BITPIX inconsistencies,
missing WCS, all-zero data, etc. Cite specific HDU indices and numeric
values from your tool outputs.

After at most {max_steps} tool calls, you MUST emit "finish" with a
"summary" string and any structured "results".
"""

_REFLECTION_PROMPT = """An automated symbolic checker reviewed your previous analysis and found:

{symbolic_feedback}

Internal consistency check against your tool outputs:
{consistency_issues}

Revise your analysis. Be explicit about each issue listed above, cite
the HDU index, and ground every numeric claim in a tool output. Use the
same JSON action protocol.

Original task: {task_description}
"""


@AgentRegistry.register
class ReflexionDataAnalystAgent(BaseAgent):
    """Reflexion FITS analysis with deterministic symbolic critic."""

    name: ClassVar[str] = "reflexion_data_analyst"
    description: ClassVar[str] = (
        "Analyse a FITS file with a self-critique loop driven by a "
        "deterministic rule-based checker. Best for open-ended quality "
        "audits where missing anomalies is more costly than extra "
        "tool calls."
    )
    capabilities: ClassVar[list[str]] = [
        "fits_analysis",
        "anomaly_detection",
        "self_critique",
    ]

    def __init__(
        self,
        llm: LLMClient,
        tools: list[BaseTool] | None = None,
        *,
        checker: SymbolicFitsCheckerTool | None = None,
        max_reflections: int | None = None,
    ) -> None:
        super().__init__(llm=llm, tools=tools)
        if checker is None:
            tool = self.get_tool(SymbolicFitsCheckerTool.name)
            if not isinstance(tool, SymbolicFitsCheckerTool):
                raise AgentError(
                    message=(
                        "ReflexionDataAnalystAgent needs a SymbolicFitsCheckerTool "
                        "either in `tools` or as the `checker` kwarg."
                    ),
                    code="missing_tool",
                    details={"required": SymbolicFitsCheckerTool.name},
                )
            checker = tool
        self._checker = checker
        self._max_reflections = (
            max_reflections if max_reflections is not None else _DEFAULT_MAX_REFLECTIONS
        )

    async def run(
        self,
        task: dict[str, Any],
        *,
        state: AgentState | None = None,
    ) -> AgentState:
        state = state or AgentState(agent_name=self.name)
        async for _ in self._iter(task, state):
            pass
        return state

    async def stream(
        self,
        task: dict[str, Any],
        *,
        state: AgentState | None = None,
    ) -> AsyncIterator[AgentMessage]:
        state = state or AgentState(agent_name=self.name)
        async for message in self._iter(task, state):
            yield message

    async def _iter(
        self,
        task: dict[str, Any],
        state: AgentState,
    ) -> AsyncIterator[AgentMessage]:
        file_id, task_description = self._validate_task(task)

        user_msg = AgentMessage(
            role="user",
            content=f"Reflexion analysis on file_id={file_id}: {task_description}",
        )
        state.append(user_msg)
        yield user_msg

        round_results: dict[str, Any] = {}
        tool_log: list[dict[str, Any]] = []
        async for msg in self._act_round(
            task_description, file_id, state, round_results, tool_log
        ):
            yield msg

        critique = await self._critique(file_id, round_results, tool_log)
        rounds_done = 0
        for round_idx in range(self._max_reflections):
            if not critique["symbolic_violations"] and not critique["consistency_issues"]:
                break

            note = AgentMessage(
                role="system",
                content=(
                    f"[reflexion round {round_idx + 1}] "
                    f"symbolic={len(critique['symbolic_violations'])} "
                    f"consistency={len(critique['consistency_issues'])}"
                ),
            )
            state.append(note)
            yield note

            augmented_task = _REFLECTION_PROMPT.format(
                symbolic_feedback=critique["symbolic_summary"] or "(none)",
                consistency_issues=("; ".join(critique["consistency_issues"]) or "(none)"),
                task_description=task_description,
            )
            async for msg in self._act_round(
                augmented_task, file_id, state, round_results, tool_log
            ):
                yield msg
            rounds_done = round_idx + 1
            critique = await self._critique(file_id, round_results, tool_log)

        final_critique = critique

        state.final_output = {
            "results": round_results,
            "tool_calls": tool_log,
            "reflection_rounds": rounds_done,
            "symbolic_violations": final_critique["symbolic_violations"],
            "consistency_issues": final_critique["consistency_issues"],
            "max_reflections": self._max_reflections,
            "artifacts": [],
        }

        terminal_summary = round_results.get("summary") or "Analysis complete."
        if rounds_done == self._max_reflections and (
            final_critique["symbolic_violations"] or final_critique["consistency_issues"]
        ):
            terminal_summary += " [Note: max reflection rounds reached]"

        assistant_msg = AgentMessage(role="assistant", content=terminal_summary)
        state.append(assistant_msg)
        yield assistant_msg

    async def _act_round(
        self,
        task_text: str,
        file_id: uuid.UUID,
        state: AgentState,
        round_results: dict[str, Any],
        tool_log: list[dict[str, Any]],
    ) -> AsyncIterator[AgentMessage]:
        """One ReAct tool-call loop; mutates round_results and tool_log."""
        # Use replace, not format: prompt body has literal {...} JSON examples.
        system_prompt = _SYSTEM_PROMPT.replace("{max_steps}", str(_MAX_ACT_STEPS))
        user_payload = {"file_id": str(file_id), "task": task_text}
        chat: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload)},
        ]

        for _ in range(_MAX_ACT_STEPS):
            response_text = (await self.llm.complete(chat, temperature=0.2) or "").strip()
            assistant_msg = AgentMessage(role="assistant", content=response_text)
            state.append(assistant_msg)
            yield assistant_msg
            chat.append({"role": "assistant", "content": response_text})

            payload = _try_parse_action(response_text)
            if payload is None:
                corrective = (
                    "Your previous response was not valid JSON. Reply with a "
                    "single JSON object using `call_tool` or `finish`."
                )
                note = AgentMessage(role="system", content=corrective)
                state.append(note)
                yield note
                chat.append({"role": "user", "content": corrective})
                continue

            action = payload.get("action")
            if action == "finish":
                results = payload.get("results") if isinstance(payload.get("results"), dict) else {}
                round_results.update(results)
                summary = payload.get("summary")
                if isinstance(summary, str) and summary.strip():
                    round_results["summary"] = summary.strip()
                return

            if action != "call_tool":
                corrective = "`action` must be `call_tool` or `finish`. Try again."
                note = AgentMessage(role="system", content=corrective)
                state.append(note)
                yield note
                chat.append({"role": "user", "content": corrective})
                continue

            tool_name = payload.get("tool")
            tool_input = payload.get("input") or {}
            if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
                chat.append(
                    {"role": "user", "content": "`tool` must be a string and `input` an object."}
                )
                continue
            tool = self.get_tool(tool_name)
            if tool is None:
                chat.append(
                    {
                        "role": "user",
                        "content": f"Unknown tool {tool_name!r}. Try a different one or finish.",
                    }
                )
                continue

            # LLM may omit file_id; inject from task.
            tool_input.setdefault("file_id", str(file_id))

            try:
                tool_result = await tool(**tool_input)
            except ToolError as exc:
                tool_result = {"error": exc.message, "code": exc.code}

            tool_log.append({"tool": tool_name, "input": tool_input, "output": tool_result})
            tool_msg = AgentMessage(
                role="tool",
                name=tool_name,
                content=json.dumps(_truncate_payload(tool_result), default=str),
            )
            state.append(tool_msg)
            yield tool_msg
            # Feed back as user role: Groq rejects role:tool without tool_call_id.
            chat.append(
                {
                    "role": "user",
                    "content": (
                        f"Tool {tool_name} returned:\n{tool_msg.content}"
                    ),
                }
            )

        # Loop exhausted; force finish.
        round_results.setdefault("summary", "Reached step budget without explicit finish.")

    async def _critique(
        self,
        file_id: uuid.UUID,
        round_results: dict[str, Any],
        tool_log: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Run symbolic + consistency critics; return structured feedback."""
        symbolic_dict = await self._checker.execute(file_id=file_id)
        violations: list[dict[str, Any]] = symbolic_dict.get("violations", []) or []
        symbolic_summary: str = symbolic_dict.get("summary", "") or ""

        consistency_issues = self._check_consistency(round_results, tool_log)

        return {
            "symbolic_violations": violations,
            "symbolic_summary": symbolic_summary,
            "consistency_issues": consistency_issues,
        }

    @staticmethod
    def _check_consistency(
        round_results: dict[str, Any],
        tool_log: list[dict[str, Any]],
    ) -> list[str]:
        """Check numeric claims trace back to tool outputs (NaN denial + ungrounded numbers)."""
        issues: list[str] = []
        answer = (round_results.get("summary") or "").strip()
        if not answer:
            return issues

        tool_values: list[float] = []
        nan_ratios: list[float] = []
        for call in tool_log:
            out = call.get("output") or {}
            if not isinstance(out, dict):
                continue
            for src in (out, out.get("data_summary") or {}):
                if not isinstance(src, dict):
                    continue
                for key in ("mean", "std", "stddev", "min", "max", "median", "nan_ratio"):
                    if key in src:
                        try:
                            tool_values.append(float(src[key]))
                        except (TypeError, ValueError):
                            pass
                if "nan_ratio" in src:
                    try:
                        nan_ratios.append(float(src["nan_ratio"]))
                    except (TypeError, ValueError):
                        pass

        lower = answer.lower()
        if any(p in lower for p in ("no nan", "0% nan", "zero nan", "no missing data")):
            if any(r > 0.05 for r in nan_ratios):
                issues.append(
                    f"Answer claims no NaN but tool reports nan_ratio up to "
                    f"{max(nan_ratios):.2%}."
                )

        answer_numbers = [float(m) for m in _NUMBER_RE.findall(answer)]
        ungrounded: list[float] = []
        for n in answer_numbers:
            if abs(n) < 1e-9:
                continue
            if any(_close(n, v) for v in tool_values):
                continue
            if n.is_integer() and abs(n) < 1000:
                continue  # HDU index, count, etc.
            ungrounded.append(n)
        if ungrounded:
            shown = ", ".join(f"{n:g}" for n in ungrounded[:5])
            issues.append(
                f"Answer mentions numeric values that do not match any tool output: {shown}."
            )

        return issues

    @staticmethod
    def _validate_task(task: dict[str, Any]) -> tuple[uuid.UUID, str]:
        raw_file_id = task.get("file_id")
        if raw_file_id is None:
            raise AgentError(
                message="ReflexionDataAnalystAgent requires task['file_id']",
                code="invalid_task",
            )
        if isinstance(raw_file_id, uuid.UUID):
            file_id = raw_file_id
        else:
            try:
                file_id = uuid.UUID(str(raw_file_id))
            except (TypeError, ValueError) as exc:
                raise AgentError(
                    message=f"Invalid file_id: {raw_file_id!r}",
                    code="invalid_task",
                ) from exc

        task_description = task.get("task_description")
        if not isinstance(task_description, str) or not task_description.strip():
            task_description = (
                "Inspect the file for data-quality anomalies (NaN regions, "
                "EXPTIME issues, NAXIS/BITPIX inconsistencies, WCS coverage, "
                "all-zero data) and report each finding with its HDU index."
            )
        return file_id, task_description.strip()


def _try_parse_action(text: str) -> dict[str, Any] | None:
    """Strip ```json fences then json.loads; fall back to outermost {...}."""
    if not text:
        return None
    match = _FENCE_PATTERN.match(text.strip())
    body = match.group(1) if match else text.strip()
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        start = body.find("{")
        end = body.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(body[start : end + 1])
            except json.JSONDecodeError:
                return None
        return None


def _truncate_payload(payload: Any, limit: int = 4000) -> Any:
    """Cap tool-output JSON length to protect context window."""
    text = json.dumps(payload, default=str)
    if len(text) <= limit:
        return payload
    return {"truncated": True, "preview": text[:limit] + "..."}


def _close(a: float, b: float, rel: float = 5e-3, abs_tol: float = 1e-6) -> bool:
    if a == b:
        return True
    return abs(a - b) <= max(abs_tol, rel * max(abs(a), abs(b)))
