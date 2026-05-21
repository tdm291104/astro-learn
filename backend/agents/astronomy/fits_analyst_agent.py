"""FITS chat agent: read_header → decide → analyze → interpret."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from agents.astronomy.fits_analyst_services import FitsAnalystServicesProtocol
from agents.astronomy.fits_decision import infer_analysis_types
from agents.base.agent_message import AgentMessage
from agents.base.agent_registry import AgentRegistry
from agents.base.agent_state import AgentState
from agents.base.base_agent import BaseAgent
from core.exceptions import AgentError, ToolError
from core.llm.llm_client import LLMClient
from core.llm.prompt_templates import (
    build_fits_header_block,
    build_fits_interpretation_prompt,
)
from core.llm.validators import validate_fits_interpretation
from schemas.fits_interpretation_schema import FitsInterpretation, ReflexionMeta
from tools.astronomy.symbolic_checker_tool import SymbolicFitsCheckerTool
from tools.base_tool import BaseTool

_DECISION_TYPES: frozenset[str] = frozenset(
    {"image_stats", "photometry", "spectroscopy", "wcs", "custom"}
)

# Bridge: decision token → dispatch token (only `wcs` vs `wcs_solve` differs).
_DISPATCH_TYPE: dict[str, str] = {
    "image_stats": "image_stats",
    "photometry": "photometry",
    "spectroscopy": "spectroscopy",
    "wcs": "wcs_solve",
    "custom": "custom",
}

# Cap interpretation retries before falling back to templated shell.
_MAX_INTERPRETATION_ATTEMPTS: int = 2

# Action verbs distinguish a request ("run photometry") from descriptive prose.
_OVERRIDE_VERB_RE: re.Pattern[str] = re.compile(
    r"\b(run|do|execute|use|perform|switch|instead|only|just)\b",
    re.IGNORECASE,
)


# Fast path: header-only queries skip the 120s analyze pipeline (EN + VI).
_METADATA_ONLY_RE: re.Pattern[str] = re.compile(
    r"\b("
    r"instrument|telescope|filter|exposure|exptime|object|target|"
    r"header|metadata|naxis|bitpix|wcs\s*present|"
    r"what\s+kind|what\s+type|when\s+was|where\s+was|"
    # Vietnamese
    r"k[íiỉĩị]nh|m[áaãàâấầẩẫậă]y|b[ộoọõôốồổỗộơớờởỡợ]\s*l[ọóòỏõọôốồổỗộơớờởỡợo]c|"
    r"th[ờờởỡợoọ]i\s*gian|ph[ơoớờởỡợ]i\s*s[áaãàâấầẩẫậă]ng|"
    r"th[ôốồổỗộơo]ng\s*tin|si[êeềểễệe]u\s*d[ữưừửữựu]\s*li[ệe]u"
    r")\b",
    re.IGNORECASE,
)


def _is_metadata_only_query(query: str | None) -> bool:
    """True when the user's question can be answered from header alone."""
    if not query:
        return False
    if _OVERRIDE_VERB_RE.search(query):
        # Explicit override wins over the fast path.
        return False
    return bool(_METADATA_ONLY_RE.search(query))


@AgentRegistry.register
class FitsAnalystAgent(BaseAgent):
    """Drive end-to-end FITS analysis for a chat turn."""

    name: ClassVar[str] = "fits_analyst"
    description: ClassVar[str] = (
        "Read a stored FITS file's header, decide which analyses fit, run them, "
        "and produce a structured human-readable interpretation."
    )
    capabilities: ClassVar[list[str]] = [
        "fits_analysis",
        "header_inference",
        "interpretation",
    ]

    def __init__(
        self,
        llm: LLMClient,
        tools: list[BaseTool] | None = None,
        *,
        services: FitsAnalystServicesProtocol | None = None,
        symbolic_checker: SymbolicFitsCheckerTool | None = None,
    ) -> None:
        super().__init__(llm=llm, tools=tools)
        # Optional only so tests can stub; required at runtime.
        self._services = services
        # Optional for legacy tests; production always injects via agent_factory.
        self._symbolic_checker = symbolic_checker

    async def run(
        self, task: dict[str, Any], *, state: AgentState | None = None,
    ) -> AgentState:
        state = state or AgentState(agent_name=self.name)
        async for _ in self._iter(task, state):
            pass
        return state

    async def stream(
        self, task: dict[str, Any], *, state: AgentState | None = None,
    ) -> AsyncIterator[AgentMessage]:
        state = state or AgentState(agent_name=self.name)
        async for message in self._iter(task, state):
            yield message

    async def _iter(
        self, task: dict[str, Any], state: AgentState,
    ) -> AsyncIterator[AgentMessage]:
        if self._services is None:
            raise AgentError(
                message="FitsAnalystAgent requires the services bundle to be injected",
                code="missing_dependency",
            )
        if state.user_id is None:
            raise AgentError(
                message="FitsAnalystAgent requires state.user_id",
                code="missing_user",
            )

        owner_id = state.user_id
        file_id, hdu_index, user_query = _validate_task(task)

        user_msg = AgentMessage(
            role="user",
            content=user_query or f"Analyse file {file_id}",
        )
        state.append(user_msg)
        yield user_msg

        yield _heartbeat("reading_header")
        try:
            filename, header_summary = await self._services.load_file_summary(
                owner_id, file_id
            )
        except AgentError as exc:
            if exc.code != "fits_not_found":
                raise
            # FE persists selectedFileId; surface actionable error so useChat
            # can prune the stale store entry via extra.missing_file_id.
            recovery = AgentMessage(
                role="assistant",
                name=self.name,
                content=(
                    "I can't find that FITS file anymore — it may have been "
                    "removed from your library. Please re-upload it in the "
                    "FITS panel on the left and try again."
                ),
                extra={
                    "chat_error": True,
                    "error_kind": "fits_not_found",
                    "missing_file_id": str(file_id),
                },
            )
            state.append(recovery)
            yield recovery
            state.final_output = {
                "error": "fits_not_found",
                "missing_file_id": str(file_id),
            }
            return

        # Fast path: header-only queries skip Celery analysis.
        if _is_metadata_only_query(user_query):
            yield _heartbeat("interpreting")
            answer = await self._answer_from_header(
                filename=filename,
                header_summary=header_summary,
                user_query=user_query or "Describe this file.",
            )
            final_msg = AgentMessage(
                role="assistant",
                name=self.name,
                content=answer,
                extra={"phase": "header_lookup"},
            )
            state.append(final_msg)
            yield final_msg
            state.final_output = {
                "answer": answer,
                "header_summary": header_summary,
                "fast_path": "header_lookup",
            }
            return

        analysis_types, reasoning = _resolve_decision(
            header_summary=header_summary,
            user_query=user_query,
        )
        decision_payload = {
            "analysis_types": analysis_types,
            "reasoning": reasoning,
        }
        yield _heartbeat("deciding", decision=decision_payload)
        # is_progress=True so the FE folds this narration into the reasoning
        # trail instead of rendering it as a second answer bubble.
        decide_msg = AgentMessage(
            role="assistant",
            name=self.name,
            content=(
                f"Planning to run: {', '.join(analysis_types)}. {reasoning}"
            ),
            extra={
                "phase": "deciding",
                "decision": decision_payload,
                "is_progress": True,
            },
        )
        state.append(decide_msg)
        yield decide_msg

        # Failures don't abort: interpret whatever succeeded.
        successful_runs: list[dict[str, Any]] = []
        run_analysis_ids: list[uuid.UUID] = []
        for decision_token in analysis_types:
            dispatch_type = _DISPATCH_TYPE[decision_token]
            yield _heartbeat("analyzing", analysis_type=decision_token)
            try:
                payload = await self._services.run_analysis(
                    owner_id,
                    file_id=file_id,
                    hdu_index=hdu_index,
                    analysis_type=dispatch_type,
                    params={},
                )
            except ToolError as exc:
                err_msg = AgentMessage(
                    role="tool",
                    name="run_fits_analysis",
                    content=json.dumps(
                        {
                            "error": exc.message,
                            "code": exc.code,
                            "analysis_type": decision_token,
                        }
                    ),
                    extra={
                        "phase": "analyzing",
                        "analysis_type": decision_token,
                        "error": True,
                    },
                )
                state.append(err_msg)
                yield err_msg
                continue

            successful_runs.append(
                {"analysis_type": decision_token, "payload": payload}
            )
            parsed_id = _parse_uuid(payload.get("analysis_id"))
            if parsed_id is not None:
                run_analysis_ids.append(parsed_id)

            tool_msg = AgentMessage(
                role="tool",
                name="run_fits_analysis",
                content=json.dumps(payload, default=str),
                extra={
                    "phase": "analyzing",
                    "analysis_type": decision_token,
                    "analysis_id": payload.get("analysis_id"),
                },
            )
            state.append(tool_msg)
            yield tool_msg

        yield _heartbeat("interpreting")
        interpretation = await self._interpret(
            filename=filename,
            header_summary=header_summary,
            decision=decision_payload,
            successful_runs=successful_runs,
            user_query=user_query,
        )

        # Symbolic checker catches anomalies the LLM misses (NaN, EXPTIME, WCS).
        yield _heartbeat("critiquing")
        reflexion_meta, refined_interpretation = await self._reflexion_pass(
            file_id=file_id,
            interpretation=interpretation,
        )
        interpretation = refined_interpretation
        interpretation["reflexion"] = reflexion_meta.model_dump()

        # Persist on every row so FE's activeAnalysisId always finds it.
        for aid in run_analysis_ids:
            await self._services.persist_interpretation(
                owner_id, aid, interpretation
            )

        final_msg = AgentMessage(
            role="assistant",
            name=self.name,
            content=_summary_paragraph(interpretation),
            extra={"fits_interpretation": interpretation},
        )
        state.append(final_msg)
        yield final_msg

        state.final_output = {
            "interpretation": interpretation,
            "analysis_ids": [str(aid) for aid in run_analysis_ids],
        }

    async def _answer_from_header(
        self,
        *,
        filename: str,
        header_summary: dict[str, Any],
        user_query: str,
    ) -> str:
        """One-shot LLM answer to a metadata-only question."""
        header_block = build_fits_header_block(header_summary)
        system_prompt = (
            "You are AstroLearn, an astronomy assistant. The user is asking a "
            "metadata-only question about a FITS file. Answer in 1-3 sentences "
            "using ONLY the header information below. If the requested field "
            "is missing or null, say so plainly and suggest what the user "
            "could check next. Never invent values. "
            "ALWAYS reply in the same natural language as the user's question.\n\n"
            f"Filename: {filename}\n{header_block}"
        )
        try:
            raw = await self.llm.complete(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query},
                ],
                temperature=0.2,
            )
        except Exception:
            # Surface raw header if LLM fails.
            return (
                f"Header for {filename}:\n{header_block}\n\n"
                "(Automated description unavailable; raw header above.)"
            )
        cleaned = (raw or "").strip()
        if not cleaned:
            return (
                f"Header for {filename}:\n{header_block}"
            )
        return cleaned

    async def _interpret(
        self,
        *,
        filename: str,
        header_summary: dict[str, Any],
        decision: dict[str, Any],
        successful_runs: list[dict[str, Any]],
        user_query: str | None = None,
    ) -> dict[str, Any]:
        """Call LLM, validate, retry once, fall back to templated shell."""
        header_block = build_fits_header_block(header_summary)
        raw_results_json = json.dumps(
            {
                "decision": decision,
                "results": successful_runs,
                "header_summary": header_summary,
                "filename": filename,
            },
            default=str,
        )
        base_prompt = build_fits_interpretation_prompt(
            header_block=header_block,
            raw_results_json=raw_results_json,
        )

        # Surface the user's original question so HOUSE_STYLE can mirror its
        # language; without this the LLM only sees English data + instructions
        # and defaults to English even for a Vietnamese asker.
        original_query = (user_query or "").strip()
        user_directive = (
            "Translate the raw_results into the FitsInterpretation JSON "
            "schema. Respond with ONE JSON object and nothing else. "
            "All natural-language fields (headline, interpretation, metric "
            "labels, anomalies, next_steps) MUST be written in the same "
            "language as the user's question shown above."
        )
        chat: list[dict[str, Any]] = [
            {"role": "system", "content": base_prompt},
        ]
        if original_query:
            chat.append(
                {
                    "role": "user",
                    "content": f"User question (mirror this language):\n{original_query}",
                }
            )
        chat.append({"role": "user", "content": user_directive})

        last_errors: list[str] = []
        for attempt in range(_MAX_INTERPRETATION_ATTEMPTS):
            raw_response = await self.llm.complete(chat, temperature=0.2)
            parsed = _try_parse_json(raw_response)
            if parsed is None:
                last_errors = ["LLM response was not valid JSON."]
            else:
                model, errors = validate_fits_interpretation(parsed)
                if model is not None:
                    return model.model_dump()
                last_errors = errors

            # Stop before cap so fallback fires on persistent invalid output.
            if attempt + 1 >= _MAX_INTERPRETATION_ATTEMPTS:
                break
            chat.append({"role": "assistant", "content": raw_response or ""})
            chat.append(
                {
                    "role": "user",
                    "content": (
                        "Your previous response failed validation:\n"
                        + "\n".join(f"- {e}" for e in last_errors)
                        + "\n\nRespond again with a single valid JSON object."
                    ),
                }
            )

        return _fallback_interpretation(
            filename=filename,
            header_summary=header_summary,
            decision=decision,
            successful_runs=successful_runs,
            errors=last_errors,
        ).model_dump()

    async def _reflexion_pass(
        self,
        *,
        file_id: uuid.UUID,
        interpretation: dict[str, Any],
    ) -> tuple[ReflexionMeta, dict[str, Any]]:
        """Run symbolic checker; fold violations into first result's anomalies."""
        if self._symbolic_checker is None:
            return ReflexionMeta(), interpretation

        try:
            check = await self._symbolic_checker.execute(file_id=file_id)
        except Exception:
            # Best-effort: don't block analysis on checker failure.
            return ReflexionMeta(), interpretation

        violations = check.get("violations") or []
        if not violations:
            return (
                ReflexionMeta(
                    symbolic_violations=0,
                    reflection_rounds=0,
                    summary=check.get("summary", "") or "No violations.",
                ),
                interpretation,
            )

        # Severity counts drive UI badge tone (error → red, warning → amber).
        error_count = sum(1 for v in violations if v.get("severity") == "error")
        warning_count = sum(1 for v in violations if v.get("severity") == "warning")

        refined = dict(interpretation)
        refined_results = list(interpretation.get("results") or [])
        if refined_results:
            first = dict(refined_results[0])
            anomalies = list(first.get("anomalies") or [])
            for v in violations:
                msg = _format_violation_line(v)
                if msg and msg not in anomalies:
                    anomalies.append(msg)
            first["anomalies"] = anomalies
            refined_results[0] = first
            refined["results"] = refined_results

        next_steps = list(interpretation.get("next_steps") or [])
        hint = "Review the flagged anomalies above before downstream use."
        if hint not in next_steps:
            next_steps.append(hint)
        refined["next_steps"] = next_steps

        return (
            ReflexionMeta(
                symbolic_violations=len(violations),
                reflection_rounds=1,
                error_count=error_count,
                warning_count=warning_count,
                summary=check.get("summary", "")
                or f"Found {len(violations)} violation(s).",
            ),
            refined,
        )


def _validate_task(
    task: dict[str, Any],
) -> tuple[uuid.UUID, int, str | None]:
    """Pull (file_id, hdu_index, user_query) from the task dict."""
    raw_file_id = task.get("file_id")
    if raw_file_id is None:
        raise AgentError(
            message="FitsAnalystAgent requires task['file_id']",
            code="invalid_task",
        )
    file_id = _parse_uuid(raw_file_id)
    if file_id is None:
        raise AgentError(
            message=f"Invalid file_id: {raw_file_id!r}",
            code="invalid_task",
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

    raw_query = task.get("query") or task.get("question") or task.get("task")
    user_query = (
        raw_query.strip() if isinstance(raw_query, str) and raw_query.strip() else None
    )
    return file_id, hdu_index, user_query


def _resolve_decision(
    *,
    header_summary: dict[str, Any],
    user_query: str | None,
) -> tuple[list[str], str]:
    """Combine header inference with explicit user override."""
    inferred, notes = infer_analysis_types(header_summary)
    override = _parse_user_override(user_query)

    if override:
        invalid = [t for t in override if t not in _DECISION_TYPES]
        valid = [t for t in override if t in _DECISION_TYPES]
        if valid:
            cite = ", ".join(valid)
            reason = (
                f"User explicitly asked to run {cite}; overriding the inferred "
                f"pipeline ({', '.join(inferred)})."
            )
            if invalid:
                reason += f" (Ignored unknown types: {', '.join(invalid)}.)"
            return valid, reason

    inferred_str = ", ".join(inferred)
    if notes:
        notes_str = " ".join(notes)
        reason = f"Inferred from header ({inferred_str}). {notes_str}"
    else:
        reason = f"Inferred from header ({inferred_str})."
    return inferred, reason


def _parse_user_override(user_query: str | None) -> list[str]:
    """Detect explicit "run X" intent; preserve user-mentioned order."""
    if not user_query:
        return []
    if not _OVERRIDE_VERB_RE.search(user_query):
        return []

    keyword_map: list[tuple[re.Pattern[str], str]] = [
        (re.compile(r"\bphotomet\w*", re.IGNORECASE), "photometry"),
        (re.compile(r"\bspectro\w*", re.IGNORECASE), "spectroscopy"),
        (re.compile(r"\b(?:wcs|astrometr\w*)\b", re.IGNORECASE), "wcs"),
        (re.compile(r"\bimage[\s_]?stats?\b", re.IGNORECASE), "image_stats"),
        (re.compile(r"\bstats?\b(?!\w)", re.IGNORECASE), "image_stats"),
        (re.compile(r"\bcustom\b", re.IGNORECASE), "custom"),
    ]

    hits: list[tuple[int, str]] = []
    seen: set[str] = set()
    for pattern, token in keyword_map:
        match = pattern.search(user_query)
        if match is None or token in seen:
            continue
        hits.append((match.start(), token))
        seen.add(token)
    hits.sort(key=lambda h: h[0])
    return [token for _, token in hits]


def _fallback_interpretation(
    *,
    filename: str,
    header_summary: dict[str, Any],
    decision: dict[str, Any],
    successful_runs: list[dict[str, Any]],
    errors: list[str],
) -> FitsInterpretation:
    """Minimal valid FitsInterpretation when LLM validation keeps failing."""
    from schemas.fits_interpretation_schema import (
        InterpContext,
        InterpDecision,
        InterpResult,
    )

    naxis1 = header_summary.get("naxis1")
    naxis2 = header_summary.get("naxis2")
    dimensions = (
        f"{naxis1} x {naxis2} px"
        if naxis1 and naxis2
        else str(header_summary.get("naxis") or "unknown")
    )

    results: list[InterpResult] = []
    for run in successful_runs:
        atype = str(run.get("analysis_type") or "image_stats")
        payload = run.get("payload") or {}
        raw_results = payload.get("results") or {}
        metrics = _metrics_from_raw_results(raw_results)
        results.append(
            InterpResult(
                # Fall back to image_stats for unknown decision tokens.
                type=atype if atype in _DECISION_TYPES else "image_stats",
                headline=f"{atype} completed with {len(metrics)} numeric metrics.",
                metrics=metrics,
                interpretation=(
                    "Automated interpretation unavailable; showing raw metrics."
                ),
                anomalies=["Interpretation step fell back to a template."],
            )
        )

    context = InterpContext(
        filename=filename,
        image_type=str(header_summary.get("naxis") and f"NAXIS={header_summary['naxis']}" or "FITS file"),
        dimensions=dimensions,
        instrument=header_summary.get("instrument"),
        filter=header_summary.get("filter"),
    )
    decision_model = InterpDecision(
        analysis_types=list(decision.get("analysis_types", [])),
        reasoning=str(decision.get("reasoning", "")) or "Inferred from header.",
    )
    return FitsInterpretation(
        context=context,
        decision=decision_model,
        results=results,
        next_steps=[
            "Re-run the analysis from the FITS history panel.",
            "Inspect the raw values in the 'View raw data' toggle below.",
        ],
    )


def _metrics_from_raw_results(raw_results: dict[str, Any]) -> list[Any]:
    """Project raw analysis result to InterpMetric entries with human labels."""
    from schemas.fits_interpretation_schema import InterpMetric

    label_renames: dict[str, str] = {
        "mean": "Mean pixel value",
        "median": "Median pixel value",
        "stddev": "Pixel standard deviation",
        "std": "Pixel standard deviation",
        "min": "Minimum pixel value",
        "max": "Maximum pixel value",
        "nan_count": "Non-finite pixel count",
        "size": "Pixel count",
    }
    out: list[InterpMetric] = []
    for raw_label, raw_value in raw_results.items():
        if not isinstance(raw_value, (int, float, str)):
            continue
        label = label_renames.get(str(raw_label), str(raw_label).replace("_", " ").title())
        out.append(
            InterpMetric(
                label=label,
                value=f"{raw_value}",
                interpretation="Raw value (fallback presentation).",
            )
        )
    return out


def _format_violation_line(violation: dict[str, Any]) -> str:
    """Render Violation as "[severity:rule_id @ HDU N] message"."""
    severity = str(violation.get("severity") or "info")
    rule_id = str(violation.get("rule_id") or "unknown")
    hdu_idx = violation.get("hdu_index")
    message = str(violation.get("message") or "").strip()
    if not message:
        return ""
    hdu_part = f" @ HDU {hdu_idx}" if isinstance(hdu_idx, int) else ""
    return f"[{severity}:{rule_id}{hdu_part}] {message}"


def _heartbeat(phase: str, **extras: Any) -> AgentMessage:
    """Heartbeat frame for useAgentStream."""
    extra: dict[str, Any] = {"heartbeat": True, "phase": phase}
    extra.update(extras)
    return AgentMessage(role="system", content=phase, extra=extra)


def _parse_uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _try_parse_json(text: str | None) -> dict[str, Any] | None:
    """Strip ```json fences before json.loads."""
    if not text:
        return None
    candidate = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", candidate, re.DOTALL)
    if fence is not None:
        candidate = fence.group(1).strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _summary_paragraph(interpretation: dict[str, Any]) -> str:
    """Pick human-readable string for assistant content; full payload on extra."""
    results = interpretation.get("results") or []
    if results:
        first = results[0]
        paragraph = first.get("interpretation") or first.get("headline")
        if isinstance(paragraph, str) and paragraph:
            return paragraph
    decision = interpretation.get("decision") or {}
    reasoning = decision.get("reasoning")
    if isinstance(reasoning, str) and reasoning:
        return reasoning
    return "FITS analysis complete."
