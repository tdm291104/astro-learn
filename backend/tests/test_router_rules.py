"""Unit tests for router rules added in Đợt 2.

We assert rule shapes directly without spinning up an LLM Router.
"""

from __future__ import annotations

from agents.orchestrator.router import (
    _CATALOG_MULTI_SEARCH_AGENT,
    _MODE_HINT_AGENT,
    _WEB_SEARCH_DIRECT_AGENT,
    _rule_catalog_mode_search,
    _rule_flashcard,
    _rule_mode_mismatch_suggest,
    _rule_quiz,
    _rule_summarize,
    _rule_web_search,
)


# --- _rule_catalog_mode_search --------------------------------------------


def test_catalog_mode_search_fires_when_no_results_yet() -> None:
    result = _rule_catalog_mode_search(
        {"mode": "catalog", "query": "M31"}
    )
    assert isinstance(result, tuple)
    agent, params = result
    assert agent == _CATALOG_MULTI_SEARCH_AGENT
    assert params["query"] == "M31"  # extracted target
    assert params["raw_question"] == "M31"


def test_catalog_mode_search_skipped_when_results_present() -> None:
    """Follow-up rule wins when catalog_results already attached."""
    result = _rule_catalog_mode_search(
        {
            "mode": "catalog",
            "query": "What is M31?",
            "catalog_results": [{"name": "M 31"}],
        }
    )
    assert result is None


def test_catalog_mode_search_skipped_outside_catalog_mode() -> None:
    result = _rule_catalog_mode_search({"mode": "general", "query": "M31"})
    assert result is None


def test_catalog_mode_search_skipped_without_query() -> None:
    result = _rule_catalog_mode_search({"mode": "catalog", "query": ""})
    assert result is None


# --- _rule_web_search honours force_web_search -----------------------------


def test_web_search_rule_fires_on_force_flag_even_without_keyword() -> None:
    result = _rule_web_search(
        {"query": "Andromeda galaxy", "force_web_search": True}
    )
    assert isinstance(result, tuple)
    agent, params = result
    assert agent == _WEB_SEARCH_DIRECT_AGENT
    assert params["query"] == "Andromeda galaxy"


def test_web_search_rule_force_flag_takes_priority_over_astronomy_block() -> None:
    """Astronomy-keyword block normally skips web search; force overrides."""
    result = _rule_web_search(
        {"query": "M31 galaxy", "force_web_search": True}
    )
    assert isinstance(result, tuple)


def test_web_search_rule_force_flag_needs_a_query() -> None:
    result = _rule_web_search({"force_web_search": True})
    assert result is None


def test_web_search_rule_unchanged_without_force_flag() -> None:
    """Plain astronomy keyword still falls through to the catalog rule path."""
    result = _rule_web_search({"query": "M31 galaxy"})
    assert result is None


# --- _rule_summarize / _rule_quiz / _rule_flashcard --- mode=notebook gate -


def test_summarize_rule_requires_notebook_mode() -> None:
    """Out-of-mode keyword must not hijack non-notebook turns."""
    base = {"notebook_id": "abc", "query": "tóm tắt notebook này"}
    assert _rule_summarize({**base, "mode": "fits"}) is None
    assert _rule_summarize({**base, "mode": "catalog"}) is None
    assert _rule_summarize({**base, "mode": "general"}) is None
    fired = _rule_summarize({**base, "mode": "notebook"})
    assert isinstance(fired, tuple) and fired[0] == "summarizer"


def test_quiz_rule_requires_notebook_mode() -> None:
    base = {"notebook_id": "abc", "query": "quiz me"}
    assert _rule_quiz({**base, "mode": "catalog"}) is None
    fired = _rule_quiz({**base, "mode": "notebook"})
    assert isinstance(fired, tuple) and fired[0] == "quiz"


def test_flashcard_rule_requires_notebook_mode() -> None:
    base = {"notebook_id": "abc", "query": "make flashcards"}
    assert _rule_flashcard({**base, "mode": "fits"}) is None
    fired = _rule_flashcard({**base, "mode": "notebook"})
    assert isinstance(fired, tuple) and fired[0] == "flashcard"


# --- _rule_mode_mismatch_suggest -------------------------------------------


def test_mode_hint_fits_mode_no_file_with_notebook_intent() -> None:
    result = _rule_mode_mismatch_suggest(
        {"mode": "fits", "query": "summarize my notebook"}
    )
    assert isinstance(result, tuple)
    agent, params = result
    assert agent == _MODE_HINT_AGENT
    assert params["suggest_mode"] == "notebook"


def test_mode_hint_notebook_mode_without_notebook_with_astronomy_query() -> None:
    result = _rule_mode_mismatch_suggest(
        {"mode": "notebook", "query": "Tell me about M31"}
    )
    assert isinstance(result, tuple)
    agent, params = result
    assert agent == _MODE_HINT_AGENT
    assert params["suggest_mode"] == "catalog"


def test_mode_hint_catalog_mode_with_notebook_intent() -> None:
    result = _rule_mode_mismatch_suggest(
        {"mode": "catalog", "query": "quiz me about M31"}
    )
    assert isinstance(result, tuple)
    agent, params = result
    assert agent == _MODE_HINT_AGENT
    assert params["suggest_mode"] == "notebook"


def test_mode_hint_catalog_mode_with_fits_keyword() -> None:
    result = _rule_mode_mismatch_suggest(
        {"mode": "catalog", "query": "show the FITS header"}
    )
    assert isinstance(result, tuple)
    agent, params = result
    assert agent == _MODE_HINT_AGENT
    assert params["suggest_mode"] == "fits"


def test_mode_hint_skipped_when_mode_matches_intent() -> None:
    """In-mode astronomy query should NOT trigger a hint."""
    assert _rule_mode_mismatch_suggest({"mode": "catalog", "query": "M31"}) is None


def test_mode_hint_skipped_when_notebook_mode_has_notebook_bound() -> None:
    """notebook_id present → user is properly inside notebook mode."""
    assert (
        _rule_mode_mismatch_suggest(
            {"mode": "notebook", "notebook_id": "abc", "query": "Tell me about M31"}
        )
        is None
    )


def test_mode_hint_skipped_for_general_mode() -> None:
    assert _rule_mode_mismatch_suggest({"mode": "general", "query": "summarize"}) is None


# --- Binding-required fall-through ----------------------------------------


def test_mode_hint_notebook_mode_without_notebook_falls_through() -> None:
    """Repro for 'Tôi muốn tạo notebooks' crashing the summarizer agent."""
    result = _rule_mode_mismatch_suggest(
        {"mode": "notebook", "query": "Tôi muốn tạo notebooks"}
    )
    assert isinstance(result, tuple)
    agent, params = result
    assert agent == _MODE_HINT_AGENT
    assert params["reason"] == "notebook_mode_needs_notebook"


def test_mode_hint_notebook_mode_without_notebook_random_chat() -> None:
    result = _rule_mode_mismatch_suggest(
        {"mode": "notebook", "query": "hello there"}
    )
    assert isinstance(result, tuple)
    _, params = result
    assert params["reason"] == "notebook_mode_needs_notebook"


def test_mode_hint_fits_mode_without_file_falls_through() -> None:
    result = _rule_mode_mismatch_suggest({"mode": "fits", "query": "hello"})
    assert isinstance(result, tuple)
    _, params = result
    assert params["reason"] == "fits_mode_needs_file"


def test_mode_hint_fits_mode_with_file_does_not_short_circuit() -> None:
    """file_id present → FITS analyst path handles it; no hint."""
    assert (
        _rule_mode_mismatch_suggest(
            {"mode": "fits", "file_id": "abc-123", "query": "hello"}
        )
        is None
    )


# --- Orchestrator planner agent filter -----------------------------------


def test_planner_filter_hides_notebook_agents_without_notebook_id() -> None:
    """Repro for 'Tôi muốn tạo notebooks' → summarizer crash with 'new_notebook'."""
    from agents.orchestrator.orchestrator_agent import OrchestratorAgent

    # Build a minimal instance via __new__ to avoid the heavy LLM/registry deps.
    inst = OrchestratorAgent.__new__(OrchestratorAgent)

    class _StubPlanner:
        available_agents = [
            "summarizer",
            "quiz",
            "flashcard",
            "qa",
            "catalog",
            "catalog_chat",
            "fits_analyst",
            "data_analyst",
        ]

    inst.planner = _StubPlanner()  # type: ignore[attr-defined]

    effective = inst._effective_planner_agents(
        {"mode": "general", "query": "Tôi muốn tạo notebooks"}
    )
    assert "summarizer" not in effective
    assert "quiz" not in effective
    assert "flashcard" not in effective
    assert "qa" not in effective
    # Catalog agents are mode-agnostic; they stay.
    assert "catalog" in effective


def test_planner_filter_hides_fits_agents_without_file_id() -> None:
    from agents.orchestrator.orchestrator_agent import OrchestratorAgent

    inst = OrchestratorAgent.__new__(OrchestratorAgent)

    class _StubPlanner:
        available_agents = [
            "summarizer",
            "fits_analyst",
            "data_analyst",
            "image_processor",
            "catalog",
        ]

    inst.planner = _StubPlanner()  # type: ignore[attr-defined]

    effective = inst._effective_planner_agents(
        {"mode": "general", "query": "open my fits file"}
    )
    assert "fits_analyst" not in effective
    assert "data_analyst" not in effective
    assert "image_processor" not in effective
    assert "catalog" in effective


def test_planner_filter_keeps_resource_agents_when_resource_bound() -> None:
    from agents.orchestrator.orchestrator_agent import OrchestratorAgent

    inst = OrchestratorAgent.__new__(OrchestratorAgent)

    class _StubPlanner:
        available_agents = ["summarizer", "fits_analyst", "catalog"]

    inst.planner = _StubPlanner()  # type: ignore[attr-defined]

    effective = inst._effective_planner_agents(
        {"notebook_id": "abc", "file_id": "xyz", "query": "anything"}
    )
    assert effective == ["summarizer", "fits_analyst", "catalog"]
