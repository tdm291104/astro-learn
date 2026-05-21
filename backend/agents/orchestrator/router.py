"""Hybrid rule + LLM router that picks an agent name for a task."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import date
from typing import Any, Final

from agents.base.agent_registry import AgentRegistry
from core.exceptions import AgentError, AgentNotFoundError
from core.llm.llm_client import LLMClient
from core.llm.prompt_templates import ORCHESTRATOR_ROUTER, render

# Bare name → raw task; tuple → (name, task_input) for typed agents.
RuleResult = str | tuple[str, dict[str, Any]] | None
RoutingRule = Callable[[dict[str, Any]], RuleResult]


def _rule_agent_name(result: RuleResult) -> str | None:
    """Pull agent name from either rule-result shape."""
    if isinstance(result, tuple):
        return result[0] if result else None
    return result


class Router:
    """Pick the best agent name for a task."""

    def __init__(
        self,
        llm: LLMClient,
        rules: list[RoutingRule] | None = None,
    ) -> None:
        self.llm = llm
        self.rules = rules or DEFAULT_RULES

    async def route(self, task: dict[str, Any]) -> str:
        for rule in self.rules:
            try:
                result = rule(task)
            except Exception:
                # Buggy rule must not crash routing.
                continue
            picked = _rule_agent_name(result)
            if picked and AgentRegistry.has(picked):
                return picked
        return await self._route_via_llm(task)

    async def _route_via_llm(self, task: dict[str, Any]) -> str:
        """LLM picks agent from registry names."""
        names = AgentRegistry.names()
        if not names:
            raise AgentError(
                message="No agents registered — cannot route via LLM",
                code="empty_registry",
            )

        system_prompt = render(ORCHESTRATOR_ROUTER, agents=", ".join(names))
        user_prompt = f"Task:\n{json.dumps(task, default=str)}"

        raw = await self.llm.complete(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        agent_name = self._parse_choice(raw)
        if not AgentRegistry.has(agent_name):
            raise AgentNotFoundError(
                message=f"LLM picked unknown agent {agent_name!r}",
                details={"available": sorted(names), "picked": agent_name},
            )
        return agent_name

    @staticmethod
    def _parse_choice(raw: str) -> str:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AgentError(
                message=f"Router LLM returned non-JSON: {raw[:200]!r}",
                code="invalid_output",
            ) from exc
        agent = parsed.get("agent") if isinstance(parsed, dict) else None
        if not isinstance(agent, str) or not agent.strip():
            raise AgentError(
                message="Router LLM output missing 'agent' field",
                code="invalid_output",
                details={"raw": raw[:500]},
            )
        return agent.strip()


_QUERY_FIELDS: Final[tuple[str, ...]] = ("query", "task", "description", "request")


# VI variants (with + without diacritics) folded in for fast-path matching.
_SUMMARIZE_RE: Final[re.Pattern[str]] = re.compile(
    r"summar"
    r"|t[óòỏõọôốồổỗộơớờởỡợo]m\s*t[ăắằẳẵặâấầẩẫậa]t"
    r"|t[ổôốồổỗộơớờởỡợo]ng\s*(?:k[ếềểễệe]t|h[ợopọ]p)",
    re.IGNORECASE,
)

# Union of notebook-tool intents (summary/quiz/flashcard) for mismatch hints.
_NOTEBOOK_INTENT_RE: Final[re.Pattern[str]] = re.compile(
    r"summari[sz]e|quiz|flashcard|flash\s*card"
    r"|t[óòỏõọôốồổỗộơớờởỡợo]m\s*t[ăắằẳẵặâấầẩẫậa]t"
    r"|th[ẻẻẽẹe]\s*(?:ghi\s*nh[ớờởỡợo]|h[ọóòỏõọo]c)"
    r"|c[âấầẩẫậa]u\s*h[ỏòỏõọo]i\s*tr[ăắằẳẵặâấầẩẫậa]c\s*nghi[ệe]m",
    re.IGNORECASE,
)

# FITS-leaning vocabulary; complement of catalog/astronomy general terms.
_FITS_INTENT_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:fits|header|hdu|exposure|wcs|primary\s*hdu)\b"
    r"|tệp\s*fits|đầu\s*ảnh|phổ\s*kế|ảnh\s*kính",
    re.IGNORECASE,
)
_QUIZ_RE: Final[re.Pattern[str]] = re.compile(
    r"quiz"
    r"|\btest\b"
    r"|\bquestions?\b"
    r"|c[âấầẩẫậa]u\s*h[ỏòỏõọo]i"
    r"|h[ỏòỏõọo]i\s*(?:t[ôốồổỗộơo]i|m[ìíĩỉị]nh)"
    r"|ki[ểềểễệe]m\s*tra"
    r"|\b[đd][ốồổỗộơo]\b",
    re.IGNORECASE,
)
_FLASHCARD_RE: Final[re.Pattern[str]] = re.compile(
    r"flashcard|flash\s*card|\bcards?\b"
    r"|th[ẻẻẽẹe]\s*(?:ghi\s*nh[ớờởỡợo]|h[ọóòỏõọo]c)",
    re.IGNORECASE,
)
# Only fires when no notebook_id/file_id, so quizzes aren't hijacked.
_ASTRONOMY_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:nebula|galaxy|star|simbad|ned|vizier|orion|andromeda|"
    r"milky.?way|M\d+|NGC\s*\d+|pulsar|supernova|quasar|black.?hole|"
    r"comet|asteroid)\b",
    re.IGNORECASE,
)


# Target extractor priority: catalog ID → RA,Dec → curated → Title-Case.

# NGC/IC/HD use "NGC 1234"; Messier uses "M31" (no space) per Simbad.
_CATALOG_ID_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(NGC\s*\d+|IC\s*\d+|HD\s*\d+|M\s*\d+)\b",
    re.IGNORECASE,
)

# Both numbers require decimals to avoid "1, 2 problems" false positives.
_RA_DEC_INLINE_RE: Final[re.Pattern[str]] = re.compile(
    r"([-+]?\d+\.\d+)\s*,\s*([-+]?\d+\.\d+)"
)

# 1-3 Title tokens; greedy so "Orion Nebula" beats "Orion".
_PROPER_NOUN_RE: Final[re.Pattern[str]] = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b"
)

# Limited to common-name asks; Messier objects covered by _CATALOG_ID_RE.
_CURATED_OBJECTS: Final[tuple[str, ...]] = (
    "Andromeda",
    "Pleiades",
    "Hyades",
    "Sirius",
    "Betelgeuse",
    "Rigel",
    "Vega",
    "Polaris",
    "Proxima Centauri",
    "Alpha Centauri",
    "Milky Way",
    "Orion Nebula",
    "Crab Nebula",
    "Eagle Nebula",
    "Ring Nebula",
    "Helix Nebula",
    "Horsehead Nebula",
    "Tarantula Nebula",
    "Whirlpool Galaxy",
    "Triangulum Galaxy",
    "Sombrero Galaxy",
    "Pillars of Creation",
    "Sagittarius A*",
)


def _compile_curated_patterns() -> list[tuple[str, re.Pattern[str]]]:
    """(canonical_name, regex) pairs sorted longest-first."""
    patterns: list[tuple[str, re.Pattern[str]]] = []
    for name in _CURATED_OBJECTS:
        pattern = re.compile(
            r"(?<![\w])" + re.escape(name) + r"(?![\w])",
            re.IGNORECASE,
        )
        patterns.append((name, pattern))
    patterns.sort(key=lambda p: -len(p[0]))
    return patterns


_CURATED_OBJECT_PATTERNS: Final[list[tuple[str, re.Pattern[str]]]] = (
    _compile_curated_patterns()
)

# Stop-words rejected as first token of Title-Case fallback.
_NOUN_PHRASE_STOP: Final[frozenset[str]] = frozenset({
    "tell", "show", "find", "search", "lookup", "look", "give", "get", "fetch",
    "what", "where", "who", "when", "why", "how", "which",
    "please", "could", "can", "would", "may",
    "the", "a", "an", "any", "some",
    "about", "for", "info", "information", "on", "with", "from", "in", "of",
    "this", "that", "these", "those",
    "me", "my", "us", "our", "we", "you", "your", "it",
})


def _normalise_catalog_id(raw: str) -> str:
    """Uppercase prefix; Simbad-friendly spacing."""
    upper = raw.strip().upper()
    for prefix in ("NGC", "IC", "HD"):
        if upper.startswith(prefix):
            digits = upper[len(prefix):].strip()
            return f"{prefix} {digits}"
    # Messier: no space between M and digits.
    return re.sub(r"\s+", "", upper)


def _extract_astronomy_target(text: str) -> str | None:
    """Narrow text to catalog-friendly target name, else None."""
    if not text:
        return None

    catalog_match = _CATALOG_ID_RE.search(text)
    if catalog_match:
        return _normalise_catalog_id(catalog_match.group(0))

    coord_match = _RA_DEC_INLINE_RE.search(text)
    if coord_match:
        return f"{coord_match.group(1)},{coord_match.group(2)}"

    for canonical, pattern in _CURATED_OBJECT_PATTERNS:
        if pattern.search(text):
            return canonical

    for match in _PROPER_NOUN_RE.finditer(text):
        phrase = match.group(0)
        first_token = phrase.split(maxsplit=1)[0].lower()
        if first_token in _NOUN_PHRASE_STOP:
            continue
        return phrase

    return None


def _free_text_blob(task: dict[str, Any]) -> str:
    """Concatenate free-text fields into a regex haystack."""
    parts: list[str] = []
    for key in _QUERY_FIELDS:
        value = task.get(key)
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts)


def _extract_query_text(task: dict[str, Any]) -> str | None:
    """Best candidate text for a search query."""
    for key in ("query", "question", "task"):
        value = task.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in task.values():
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _rule_fits_mode_to_fits_analyst(task: dict[str, Any]) -> RuleResult:
    """Route chat-mode FITS (mode='fits' + file_id) to FitsAnalystAgent."""
    if task.get("mode") != "fits":
        return None
    file_id = task.get("file_id")
    if file_id is None:
        return None
    return "fits_analyst", {
        "file_id": file_id,
        "hdu_index": task.get("hdu_index", 0),
        "query": task.get("query") or task.get("question"),
    }


def _rule_catalog_followup(task: dict[str, Any]) -> RuleResult:
    """Route catalog-mode chat with existing results to CatalogChatAgent."""
    if task.get("mode") != "catalog":
        return None
    results = task.get("catalog_results")
    if not isinstance(results, list) or len(results) == 0:
        return None
    question = task.get("query") or task.get("question")
    if not isinstance(question, str) or not question.strip():
        return None
    return "catalog_chat", {
        "question": question.strip(),
        "catalog_query": task.get("catalog_query") or "",
        "catalog_source": task.get("catalog_source") or "simbad",
        "catalog_results": results,
    }


def _rule_fits_to_data_analyst(task: dict[str, Any]) -> RuleResult:
    """`file_id` or literal 'fits' → data_analyst."""
    if "file_id" in task:
        return "data_analyst"
    for key in _QUERY_FIELDS:
        value = task.get(key)
        if isinstance(value, str) and "fits" in value.lower():
            return "data_analyst"
    return None


def _rule_qa_to_qa_agent(task: dict[str, Any]) -> RuleResult:
    """Route notebook-scoped Q&A turns to QAAgent (runs after keyword rules)."""
    notebook_id = task.get("notebook_id")
    if not notebook_id:
        return None
    question = task.get("question") or task.get("query")
    if not isinstance(question, str) or not question.strip():
        return None
    return "qa", {
        "notebook_id": notebook_id,
        "question": question.strip(),
    }


def _rule_summarize(task: dict[str, Any]) -> RuleResult:
    """mode='notebook' + notebook_id + 'summar' keyword → summarizer."""
    # Only fire inside notebook mode; keeps quiz/flashcard regex matches in
    # other modes from accidentally hijacking unrelated turns.
    if task.get("mode") != "notebook":
        return None
    notebook_id = task.get("notebook_id")
    if not notebook_id:
        return None
    if not _SUMMARIZE_RE.search(_free_text_blob(task)):
        return None
    return "summarizer", {
        "notebook_id": notebook_id,
        "max_bullets": 7,
        "style": "bullets",
    }


def _rule_quiz(task: dict[str, Any]) -> RuleResult:
    """mode='notebook' + notebook_id + quiz/test keyword → quiz agent."""
    if task.get("mode") != "notebook":
        return None
    notebook_id = task.get("notebook_id")
    if not notebook_id:
        return None
    if not _QUIZ_RE.search(_free_text_blob(task)):
        return None
    return "quiz", {
        "notebook_id": notebook_id,
        "n_questions": 5,
        "difficulty": "medium",
    }


def _rule_flashcard(task: dict[str, Any]) -> RuleResult:
    """mode='notebook' + notebook_id + flashcard/cards keyword → flashcards."""
    if task.get("mode") != "notebook":
        return None
    notebook_id = task.get("notebook_id")
    if not notebook_id:
        return None
    if not _FLASHCARD_RE.search(_free_text_blob(task)):
        return None
    return "flashcard", {
        "notebook_id": notebook_id,
        "n_cards": 10,
    }


# Sentinel routed inline by orchestrator._handle_nasa_direct.
_NASA_DIRECT_AGENT: Final[str] = "nasa_direct"

_APOD_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:picture\s+of\s+the\s+day|astronomy\s+picture|image\s+of\s+the\s+day|apod)\b",
    re.IGNORECASE,
)

_NEO_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:near[-\s]?earth|asteroid\s+today|neo\s+feed|close\s+approach)\b",
    re.IGNORECASE,
)


def _rule_apod(task: dict[str, Any]) -> RuleResult:
    """APOD-shaped asks → nasa_direct sentinel."""
    if task.get("notebook_id") or task.get("file_id"):
        return None
    if not _APOD_RE.search(_free_text_blob(task)):
        return None
    return _NASA_DIRECT_AGENT, {"endpoint": "apod"}


def _rule_neo(task: dict[str, Any]) -> RuleResult:
    """NEO-shaped asks → nasa_direct sentinel."""
    if task.get("notebook_id") or task.get("file_id"):
        return None
    if not _NEO_RE.search(_free_text_blob(task)):
        return None
    return _NASA_DIRECT_AGENT, {
        "endpoint": "neo",
        "date": date.today().isoformat(),
    }


# Sentinel routed inline by orchestrator._handle_mode_hint.
_MODE_HINT_AGENT: Final[str] = "mode_hint"


def _rule_mode_mismatch_suggest(task: dict[str, Any]) -> RuleResult:
    """Detect "wrong mode" turns and short-circuit with a mode-switch hint.

    Examples:
      - FITS mode, no file selected, user asks 'tóm tắt' → suggest notebook.
      - Notebook mode, no notebook bound, user asks about M31 → suggest catalog.
      - Catalog mode, user asks 'quiz me' → suggest notebook.
      - Catalog mode, user asks about a FITS header → suggest fits.
    """
    mode = task.get("mode")
    if mode not in {"fits", "notebook", "catalog"}:
        return None
    blob = _free_text_blob(task)
    if not blob:
        return None

    if mode == "fits" and not task.get("file_id"):
        if _NOTEBOOK_INTENT_RE.search(blob):
            return _MODE_HINT_AGENT, {
                "suggest_mode": "notebook",
                "reason": "notebook_intent_in_fits_mode",
            }
        # Catalog-ish question while no FITS picked → catalog mode is better.
        if _ASTRONOMY_RE.search(blob):
            return _MODE_HINT_AGENT, {
                "suggest_mode": "catalog",
                "reason": "astronomy_query_in_fits_mode_without_file",
            }
        # Fall-through: any other turn in FITS mode without a file picked
        # cannot be served — FitsAnalystAgent requires file_id. Short-circuit
        # with a "select a file" hint instead of letting the planner pick a
        # FITS-tool agent and crash on missing file_id.
        return _MODE_HINT_AGENT, {
            "suggest_mode": "fits",
            "reason": "fits_mode_needs_file",
        }

    if mode == "notebook" and not task.get("notebook_id"):
        # Notebook mode is useless without a bound notebook; route based on
        # the actual intent rather than failing in QA agent.
        if _FITS_INTENT_RE.search(blob):
            return _MODE_HINT_AGENT, {
                "suggest_mode": "fits",
                "reason": "fits_intent_in_notebook_mode_without_notebook",
            }
        if _ASTRONOMY_RE.search(blob):
            return _MODE_HINT_AGENT, {
                "suggest_mode": "catalog",
                "reason": "astronomy_query_in_notebook_mode_without_notebook",
            }
        # Fall-through guard: planner LLM tends to pick summarizer/qa
        # solely because mode=='notebook', then those agents crash on
        # notebook_id=None. Always hint instead.
        return _MODE_HINT_AGENT, {
            "suggest_mode": "notebook",
            "reason": "notebook_mode_needs_notebook",
        }

    if mode == "catalog":
        # Notebook ops never belong in catalog mode.
        if _NOTEBOOK_INTENT_RE.search(blob):
            return _MODE_HINT_AGENT, {
                "suggest_mode": "notebook",
                "reason": "notebook_intent_in_catalog_mode",
            }
        # FITS-shape ask without a file_id picked → fits mode is the home.
        if _FITS_INTENT_RE.search(blob) and not task.get("file_id"):
            return _MODE_HINT_AGENT, {
                "suggest_mode": "fits",
                "reason": "fits_intent_in_catalog_mode",
            }

    return None


# Sentinel routed inline by orchestrator._handle_catalog_multi_search.
_CATALOG_MULTI_SEARCH_AGENT: Final[str] = "catalog_multi_search"


def _rule_catalog_mode_search(task: dict[str, Any]) -> RuleResult:
    """mode='catalog' first turn (no results yet) → multi-source search."""
    if task.get("mode") != "catalog":
        return None
    existing = task.get("catalog_results")
    # Has results → follow-up rule handles it.
    if isinstance(existing, list) and existing:
        return None
    question = task.get("query") or task.get("question")
    if not isinstance(question, str) or not question.strip():
        return None
    target = _extract_astronomy_target(question) or question.strip()
    return _CATALOG_MULTI_SEARCH_AGENT, {
        "query": target,
        "raw_question": question.strip(),
    }


# Sentinel routed inline by orchestrator._handle_web_search_direct.
_WEB_SEARCH_DIRECT_AGENT: Final[str] = "web_search_direct"

_WEB_SEARCH_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:latest|recent(?:ly)?|news|current(?:ly)?|"
    r"search\s+the\s+web|look\s+up\s+online|find\s+online|"
    r"what\s+happened|this\s+week|this\s+year|"
    r"2024|2025|2026)\b",
    re.IGNORECASE,
)


def _rule_web_search(task: dict[str, Any]) -> RuleResult:
    """'Look it up online' asks → web_search_direct sentinel.

    Honours `force_web_search=True` (set by FE when user confirms after a
    catalog-empty result) regardless of other heuristics.
    """
    if task.get("force_web_search") is True:
        query = _extract_query_text(task)
        if query:
            return _WEB_SEARCH_DIRECT_AGENT, {"query": query}
        return None
    if task.get("notebook_id") or task.get("file_id"):
        return None
    blob = _free_text_blob(task)
    if not blob:
        return None
    # Astronomy catalog asks have their own path.
    if _ASTRONOMY_RE.search(blob):
        return None
    if not _WEB_SEARCH_RE.search(blob):
        return None
    query = _extract_query_text(task)
    if not query:
        return None
    return _WEB_SEARCH_DIRECT_AGENT, {"query": query}


def _rule_catalog(task: dict[str, Any]) -> RuleResult:
    """No notebook/file + astronomy keyword → catalog."""
    if task.get("notebook_id") or task.get("file_id"):
        return None
    if not _ASTRONOMY_RE.search(_free_text_blob(task)):
        return None
    query = _extract_query_text(task)
    if not query:
        return None
    target = _extract_astronomy_target(query) or query
    return "catalog", {
        "query": target,
        "source": "simbad",
        "limit": 20,
    }


# Order matters: most specific anchors first; LLM planner is the fallback.
# Mode-mismatch hint runs FIRST so we never dispatch to an agent the user is
# clearly aiming at the wrong mode for.
DEFAULT_RULES: list[RoutingRule] = [
    _rule_mode_mismatch_suggest,
    _rule_fits_mode_to_fits_analyst,
    _rule_catalog_followup,
    _rule_catalog_mode_search,
    _rule_fits_to_data_analyst,
    _rule_summarize,
    _rule_quiz,
    _rule_flashcard,
    _rule_qa_to_qa_agent,
    _rule_apod,
    _rule_neo,
    _rule_catalog,
    _rule_web_search,
]
