"""Drives FITS analysis: image stats, photometry, spectroscopy, custom."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import AsyncIterator, Iterable
from typing import Any, ClassVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.base.agent_message import AgentMessage
from agents.base.agent_registry import AgentRegistry
from agents.base.agent_state import AgentState
from agents.base.base_agent import BaseAgent
from core.exceptions import (
    AgentError,
    AstroLearnError,
    ExternalServiceError,
    ToolError,
)
from core.llm.llm_client import LLMClient
from core.llm.prompt_templates import DATA_ANALYST_TOOL_LOOP, render
from repositories.agent_repository import AgentRepository
from tools.base_tool import BaseTool

# Mirrors astronomy_schema.AnalysisType.
_VALID_ANALYSIS_TYPES: frozenset[str] = frozenset(
    {"image_stats", "photometry", "spectroscopy", "wcs_solve", "custom"}
)

# Each step burns an LLM call.
_MAX_STEPS: int = 4

# Expected message count per path for progress fraction; custom uses None.
_PATH_TOTAL_STEPS: dict[str, int] = {
    "image_stats": 3,
    "photometry": 3,
    "spectroscopy": 4,
    "wcs_solve": 4,
}

# FITS WCS Paper I keys.
_WCS_KEYS: tuple[str, ...] = (
    "WCSAXES",
    "CRVAL1", "CRVAL2",
    "CRPIX1", "CRPIX2",
    "CDELT1", "CDELT2",
    "CTYPE1", "CTYPE2",
    "CUNIT1", "CUNIT2",
    "CD1_1", "CD1_2", "CD2_1", "CD2_2",
    "PC1_1", "PC1_2", "PC2_1", "PC2_2",
    "EQUINOX", "RADESYS",
)

# Defensive: llama-3.x adds fences despite prompt forbidding them.
_FENCE_PATTERN: re.Pattern[str] = re.compile(
    r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL
)


@AgentRegistry.register
class DataAnalystAgent(BaseAgent):
    """Run an analysis on a stored FITS file."""

    name: ClassVar[str] = "data_analyst"
    description: ClassVar[str] = (
        "Analyse astronomical data files (FITS). Picks the right tool for "
        "the requested analysis type and returns numeric results plus any "
        "generated plots."
    )
    capabilities: ClassVar[list[str]] = ["fits_analysis", "tool_planning", "plot_generation"]

    def __init__(
        self,
        llm: LLMClient,
        tools: list[BaseTool] | None = None,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        # session_factory enables cancellation polling against agent_runs.
        super().__init__(llm=llm, tools=tools)
        self._session_factory = session_factory

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
        file_id, hdu_index, analysis_type, params = self._validate_task(task)
        total_steps = _PATH_TOTAL_STEPS.get(analysis_type)

        # First progress write before any tool call so polling sees step_count=1.
        user_msg = AgentMessage(
            role="user",
            content=(
                f"Analyse FITS file_id={file_id} hdu={hdu_index} "
                f"analysis_type={analysis_type}"
            ),
        )
        state.append(user_msg)
        yield user_msg
        await self._write_progress(
            state,
            current_step=f"Starting {analysis_type} analysis",
            total_steps=total_steps,
        )

        if analysis_type == "image_stats":
            results: dict[str, Any] = {}
            async for msg in self._image_stats(file_id, hdu_index, state, results):
                yield msg
        elif analysis_type == "photometry":
            results = {}
            async for msg in self._photometry(file_id, hdu_index, state, results):
                yield msg
        elif analysis_type == "spectroscopy":
            results = {}
            async for msg in self._spectroscopy(file_id, hdu_index, params, state, results):
                yield msg
        elif analysis_type == "wcs_solve":
            results = {}
            async for msg in self._wcs_solve(file_id, hdu_index, params, state, results):
                yield msg
        elif analysis_type == "custom":
            # Custom drives its own assistant messages + final_output.
            async for msg in self._custom_loop(file_id, hdu_index, params, state):
                yield msg
            return
        else:                                    # pragma: no cover — guarded above
            raise AgentError(
                message=f"Unknown analysis_type: {analysis_type!r}",
                code="invalid_task",
            )

        assistant_msg = AgentMessage(
            role="assistant",
            content=f"Completed {analysis_type} analysis.",
        )
        state.append(assistant_msg)
        yield assistant_msg
        # Saturate fraction at 1.0 before recorder writes terminal status.
        await self._write_progress(
            state,
            current_step=f"Completed {analysis_type}",
            total_steps=total_steps,
        )

        state.final_output = {"results": results, "artifacts": []}

    async def _image_stats(
        self,
        file_id: uuid.UUID,
        hdu_index: int,
        state: AgentState,
        results: dict[str, Any],
    ) -> AsyncIterator[AgentMessage]:
        await self._check_cancelled(state)
        await self._write_progress(
            state,
            current_step="Reading FITS image stats",
            total_steps=_PATH_TOTAL_STEPS["image_stats"],
        )
        tool_result = await self._call_fits_reader(
            file_id=file_id,
            hdu_index=hdu_index,
            include_data_summary=True,
        )
        msg = _tool_message("fits_reader", tool_result)
        state.append(msg)
        yield msg
        results.update(_data_summary(tool_result))

    async def _photometry(
        self,
        file_id: uuid.UUID,
        hdu_index: int,
        state: AgentState,
        results: dict[str, Any],
    ) -> AsyncIterator[AgentMessage]:
        # Heavy photutils detection runs in astronomy_worker; we surface a pointer.
        await self._check_cancelled(state)
        await self._write_progress(
            state,
            current_step="Computing photometry stats",
            total_steps=_PATH_TOTAL_STEPS["photometry"],
        )
        tool_result = await self._call_fits_reader(
            file_id=file_id,
            hdu_index=hdu_index,
            include_data_summary=True,
            include_headers=True,
        )
        msg = _tool_message("fits_reader", tool_result)
        state.append(msg)
        yield msg

        results.update(
            {
                "method": "summary_only",
                "data_summary": _data_summary(tool_result),
                "note": (
                    f"photutils source detection runs in the ingest worker; see "
                    f"fits_artifacts/{file_id}/source_list.json"
                ),
            }
        )

    async def _spectroscopy(
        self,
        file_id: uuid.UUID,
        hdu_index: int,
        params: dict[str, Any],
        state: AgentState,
        results: dict[str, Any],
    ) -> AsyncIterator[AgentMessage]:
        total = _PATH_TOTAL_STEPS["spectroscopy"]
        await self._check_cancelled(state)
        await self._write_progress(
            state, current_step="Reading FITS spectrum", total_steps=total,
        )
        tool_result = await self._call_fits_reader(
            file_id=file_id,
            hdu_index=hdu_index,
            include_data_summary=True,
            include_headers=True,
        )
        msg = _tool_message("fits_reader", tool_result)
        state.append(msg)
        yield msg

        results["data_summary"] = _data_summary(tool_result)

        wavelength = params.get("wavelength")
        if wavelength is None:
            return
        try:
            wavelength_value = float(wavelength)
        except (TypeError, ValueError) as exc:
            raise AgentError(
                message=f"Invalid spectroscopy wavelength: {wavelength!r}",
                code="invalid_task",
            ) from exc

        unit = params.get("unit", "nm")
        await self._check_cancelled(state)
        await self._write_progress(
            state,
            current_step="Converting wavelength to frequency",
            total_steps=total,
        )
        astropy_result = await self._call_astropy(
            operation="wavelength_to_frequency",
            params={"wavelength": wavelength_value, "unit": unit},
        )
        astro_msg = _tool_message("astropy_compute", astropy_result)
        state.append(astro_msg)
        yield astro_msg

        results["frequency_hz"] = astropy_result.get("frequency_hz")
        results["wavelength"] = astropy_result.get("wavelength")
        results["unit"] = astropy_result.get("wavelength_unit")

    async def _wcs_solve(
        self,
        file_id: uuid.UUID,
        hdu_index: int,
        params: dict[str, Any],
        state: AgentState,
        results: dict[str, Any],
    ) -> AsyncIterator[AgentMessage]:
        total = _PATH_TOTAL_STEPS["wcs_solve"]
        await self._check_cancelled(state)
        await self._write_progress(
            state, current_step="Reading WCS headers", total_steps=total,
        )
        tool_result = await self._call_fits_reader(
            file_id=file_id,
            hdu_index=hdu_index,
            include_headers=True,
        )
        msg = _tool_message("fits_reader", tool_result)
        state.append(msg)
        yield msg

        results["wcs"] = _extract_wcs_keys(tool_result.get("headers") or [])

        ra_deg = params.get("ra_deg")
        dec_deg = params.get("dec_deg")
        if ra_deg is None or dec_deg is None:
            return
        try:
            ra_value = float(ra_deg)
            dec_value = float(dec_deg)
        except (TypeError, ValueError) as exc:
            raise AgentError(
                message=f"Invalid wcs_solve coords: ra={ra_deg!r}, dec={dec_deg!r}",
                code="invalid_task",
            ) from exc

        await self._check_cancelled(state)
        await self._write_progress(
            state,
            current_step="Computing coordinate transform",
            total_steps=total,
        )
        astropy_result = await self._call_astropy(
            operation="coord_convert",
            params={
                "ra_deg": ra_value,
                "dec_deg": dec_value,
                "from_frame": params.get("from_frame", "icrs"),
                "to_frame": params.get("to_frame", "galactic"),
            },
        )
        astro_msg = _tool_message("astropy_compute", astropy_result)
        state.append(astro_msg)
        yield astro_msg

        results["frame_check"] = astropy_result

    async def _custom_loop(
        self,
        file_id: uuid.UUID,
        hdu_index: int,
        params: dict[str, Any],
        state: AgentState,
    ) -> AsyncIterator[AgentMessage]:
        # Fail fast: missing tools mid-loop confuse the LLM.
        for required in ("fits_reader", "astropy_compute"):
            if self.get_tool(required) is None:
                raise AgentError(
                    message=(
                        f"DataAnalystAgent custom loop requires the "
                        f"{required!r} tool"
                    ),
                    code="missing_tool",
                    details={"required": required},
                )

        system_prompt = render(DATA_ANALYST_TOOL_LOOP)
        user_payload = {
            "file_id": str(file_id),
            "hdu_index": hdu_index,
            "params": params,
        }
        instructions = params.get("instructions")
        if isinstance(instructions, str) and instructions.strip():
            user_text = f"{instructions.strip()}\n\nContext:\n{json.dumps(user_payload)}"
        else:
            user_text = json.dumps(user_payload)

        chat: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]

        for iteration in range(_MAX_STEPS):
            # Poll cancellation before the (expensive) LLM call.
            await self._check_cancelled(state)
            # Open-ended path: no total; UI shows step count.
            await self._write_progress(
                state,
                current_step=f"Planning step {iteration + 1}/{_MAX_STEPS}",
                total_steps=None,
            )
            response_text = await self.llm.complete(chat, temperature=0.2)
            response_text = (response_text or "").strip()

            assistant_msg = AgentMessage(role="assistant", content=response_text)
            state.append(assistant_msg)
            yield assistant_msg
            chat.append({"role": "assistant", "content": response_text})

            payload = _try_parse_action(response_text)
            if payload is None:
                corrective = (
                    "Your previous response was not valid JSON. Reply with a "
                    "single JSON object: "
                    '{"action": "call_tool", "tool": "<name>", "input": {...}} '
                    'or {"action": "finish", "results": {...}}'
                )
                note_msg = AgentMessage(role="system", content=corrective)
                state.append(note_msg)
                yield note_msg
                chat.append({"role": "user", "content": corrective})
                continue

            action = payload.get("action")
            if action == "finish":
                results = payload.get("results")
                if not isinstance(results, dict):
                    results = {}
                state.final_output = {"results": results, "artifacts": []}
                return

            if action == "call_tool":
                tool_name = payload.get("tool")
                tool_input = payload.get("input") or {}
                if not isinstance(tool_name, str):
                    chat.append(
                        {
                            "role": "user",
                            "content": "`tool` must be a string. Try again.",
                        }
                    )
                    continue
                tool = self.get_tool(tool_name)
                if tool is None:
                    raise AgentError(
                        message=(
                            f"DataAnalystAgent custom loop requested unknown "
                            f"tool: {tool_name!r}"
                        ),
                        code="missing_tool",
                        details={"required": tool_name},
                    )
                if not isinstance(tool_input, dict):
                    chat.append(
                        {
                            "role": "user",
                            "content": "`input` must be a JSON object. Try again.",
                        }
                    )
                    continue

                # Re-check cancellation before external API call.
                await self._check_cancelled(state)
                await self._write_progress(
                    state,
                    current_step=f"Calling tool: {tool_name}",
                    total_steps=None,
                )
                tool_result = await _safe_tool_call(tool, tool_input)
                tool_msg = _tool_message(tool_name, tool_result)
                state.append(tool_msg)
                yield tool_msg
                # User-role wrapper avoids tool_call_id correlation.
                chat.append(
                    {
                        "role": "user",
                        "content": (
                            f"Tool {tool_name} returned:\n"
                            f"{json.dumps(tool_result)}"
                        ),
                    }
                )
                continue

            chat.append(
                {
                    "role": "user",
                    "content": (
                        f"Unknown action {action!r}. Use 'call_tool' or 'finish'."
                    ),
                }
            )

        raise AgentError(
            message=(
                f"DataAnalystAgent custom loop exceeded {_MAX_STEPS} steps "
                f"without emitting `finish`"
            ),
            code="max_steps_exceeded",
            details={"max_steps": _MAX_STEPS},
        )

    async def _write_progress(
        self,
        state: AgentState,
        *,
        current_step: str,
        total_steps: int | None,
    ) -> None:
        """Mirror in-flight progress onto agent_runs via independent session."""
        state.current_step = current_step
        if self._session_factory is None:
            return
        if total_steps is not None and total_steps > 0:
            progress: float | None = min(state.step_count / total_steps, 1.0)
        else:
            progress = None
        async with self._session_factory() as session:
            await AgentRepository(session).update_progress(
                state.run_id,
                step_count=state.step_count,
                current_step=current_step,
                progress=progress,
            )
            await session.commit()

    async def _check_cancelled(self, state: AgentState) -> None:
        """Raise CancelledError if agent_runs row was flipped to cancelled."""
        # Independent session: request session snapshot won't see mid-run UPDATE.
        if self._session_factory is None:
            return
        async with self._session_factory() as session:
            row = await AgentRepository(session).get(state.run_id)
        if row is not None and row.status == "cancelled":
            raise asyncio.CancelledError(
                f"agent run {state.run_id} was cancelled"
            )

    async def _call_fits_reader(self, **kwargs: Any) -> dict[str, Any]:
        tool = self.get_tool("fits_reader")
        if tool is None:
            raise AgentError(
                message="DataAnalystAgent requires the 'fits_reader' tool",
                code="missing_tool",
                details={"required": "fits_reader"},
            )
        return await tool(**kwargs)

    async def _call_astropy(self, **kwargs: Any) -> dict[str, Any]:
        tool = self.get_tool("astropy_compute")
        if tool is None:
            raise AgentError(
                message="DataAnalystAgent requires the 'astropy_compute' tool",
                code="missing_tool",
                details={"required": "astropy_compute"},
            )
        return await tool(**kwargs)

    @staticmethod
    def _validate_task(
        task: dict[str, Any],
    ) -> tuple[uuid.UUID, int, str, dict[str, Any]]:
        raw_file_id = task.get("file_id")
        if raw_file_id is None:
            raise AgentError(
                message="DataAnalystAgent requires task['file_id']",
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

        analysis_type = task.get("analysis_type")
        if analysis_type not in _VALID_ANALYSIS_TYPES:
            raise AgentError(
                message=f"Unknown analysis_type: {analysis_type!r}",
                code="invalid_task",
                details={
                    "analysis_type": analysis_type,
                    "valid": sorted(_VALID_ANALYSIS_TYPES),
                },
            )

        try:
            hdu_index = int(task.get("hdu_index", 0))
        except (TypeError, ValueError) as exc:
            raise AgentError(
                message=f"Invalid hdu_index: {task.get('hdu_index')!r}",
                code="invalid_task",
            ) from exc
        if hdu_index < 0:
            raise AgentError(
                message=f"hdu_index must be >= 0, got {hdu_index}",
                code="invalid_task",
            )

        params = task.get("params") or {}
        if not isinstance(params, dict):
            raise AgentError(
                message=f"params must be a dict, got {type(params).__name__}",
                code="invalid_task",
            )

        return file_id, hdu_index, analysis_type, params


def _tool_message(tool_name: str, payload: Any) -> AgentMessage:
    return AgentMessage(
        role="tool",
        name=tool_name,
        content=json.dumps(payload, default=str),
    )


def _data_summary(tool_result: dict[str, Any]) -> dict[str, Any]:
    summary = tool_result.get("data_summary")
    return dict(summary) if isinstance(summary, dict) else {}


def _extract_wcs_keys(header_cards: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Pull standard WCS keys from header; absence signals missing."""
    wanted = set(_WCS_KEYS)
    out: dict[str, Any] = {}
    for card in header_cards:
        keyword = card.get("keyword") if isinstance(card, dict) else None
        if isinstance(keyword, str) and keyword in wanted:
            out[keyword] = card.get("value")
    return out


def _try_parse_action(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    candidate = text.strip()
    fence = _FENCE_PATTERN.match(candidate)
    if fence is not None:
        candidate = fence.group(1).strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def _safe_tool_call(tool: Any, tool_input: dict[str, Any]) -> Any:
    """Run tool; surface known failures as JSON for the LLM."""
    try:
        return await tool(**tool_input)
    except (ToolError, ExternalServiceError) as exc:
        return {"error": exc.message, "code": exc.code, "details": exc.details}
    except AstroLearnError as exc:                 # pragma: no cover — defensive
        return {"error": exc.message, "code": exc.code, "details": exc.details}
