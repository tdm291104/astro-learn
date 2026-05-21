"""Single-document learning: summarize → quiz → flashcards."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from workflows.base_workflow import (
    AgentFactory,
    BaseWorkflow,
    StepProgressCallback,
    WorkflowState,
)
from workflows.workflow_engine import WorkflowEngine

_LEARNING_WORKFLOW_STEPS: tuple[str, ...] = ("summarize", "quiz", "flashcards")


class LearningWorkflow(BaseWorkflow):
    """Guided learning loop for a single document."""

    name: ClassVar[str] = "learning"
    description: ClassVar[str] = (
        "Read-quiz-flashcard learning loop for a single document. "
        "Quiz and flashcards are generated using the summary as anchor."
    )

    def __init__(
        self,
        agent_factory: AgentFactory,
        *,
        on_step_complete: StepProgressCallback | None = None,
    ) -> None:
        super().__init__(
            agent_factory=agent_factory,
            on_step_complete=on_step_complete,
        )
        self.engine = WorkflowEngine(agent_factory=agent_factory)

    async def run(
        self,
        input: dict[str, Any],
        *,
        state: WorkflowState | None = None,
    ) -> WorkflowState:
        """Sequential: quiz+flashcard quality benefits from grounding on summary."""
        state = state or WorkflowState(workflow_name=self.name)
        state.status = "running"
        state.started_at = datetime.now(UTC)

        notebook_id: uuid.UUID = input["notebook_id"]
        document_id: uuid.UUID = input["document_id"]
        n_questions: int = input.get("n_questions", 5)
        n_cards: int = input.get("n_cards", 10)

        total = len(_LEARNING_WORKFLOW_STEPS)
        try:
            await self.engine.run_step(
                state, "summarize", "summarizer",
                self._build_summary_input(notebook_id, document_id),
            )
            summary = (state.get_output("summarize") or {}).get("summary") or ""
            await self._report_step("summarize", 0, total)

            await self.engine.run_step(
                state, "quiz", "quiz",
                self._build_quiz_input(notebook_id, document_id, n_questions, summary),
            )
            await self._report_step("quiz", 1, total)

            await self.engine.run_step(
                state, "flashcards", "flashcard",
                self._build_flashcard_input(notebook_id, document_id, n_cards, summary),
            )
            await self._report_step("flashcards", 2, total)

            state.final_output = {
                "summary": summary,
                "quiz": (state.get_output("quiz") or {}).get("questions"),
                "flashcards": (state.get_output("flashcards") or {}).get("cards"),
            }
            state.status = "succeeded"
        except Exception as exc:
            state.status = "failed"
            state.error = str(exc)
            raise
        finally:
            state.finished_at = datetime.now(UTC)

        return state

    async def _report_step(
        self,
        step_name: str,
        index: int,
        total: int,
    ) -> None:
        """Fire progress callback; never fails the workflow."""
        if self.on_step_complete is None:
            return
        try:
            await self.on_step_complete(step_name, index, total)
        except Exception:                              # pragma: no cover
            pass

    @staticmethod
    def _build_summary_input(
        notebook_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> dict[str, Any]:
        return {"notebook_id": notebook_id, "document_id": document_id}

    @staticmethod
    def _build_quiz_input(
        notebook_id: uuid.UUID,
        document_id: uuid.UUID,
        n_questions: int,
        summary: str | list[str],
    ) -> dict[str, Any]:
        return {
            "notebook_id": notebook_id,
            "document_id": document_id,
            "n_questions": n_questions,
            "summary_context": summary,
        }

    @staticmethod
    def _build_flashcard_input(
        notebook_id: uuid.UUID,
        document_id: uuid.UUID,
        n_cards: int,
        summary: str | list[str],
    ) -> dict[str, Any]:
        return {
            "notebook_id": notebook_id,
            "document_id": document_id,
            "n_cards": n_cards,
            "summary_context": summary,
        }
