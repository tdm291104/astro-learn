"""Full notebook learning pipeline: summarize then quiz+flashcards in parallel."""

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

# Quiz + flashcards parallel but reported as one step for progress.
_NOTEBOOK_WORKFLOW_STEPS: tuple[str, ...] = (
    "summarize",
    "quiz_and_flashcards",
    "validate_quiz",
)


class NotebookWorkflow(BaseWorkflow):
    """Generate a notebook study pack: summary plus quiz plus flashcards."""

    name: ClassVar[str] = "notebook"
    description: ClassVar[str] = (
        "Build a complete study pack (summary + quiz + flashcards) for "
        "a notebook in one pass."
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
        """summarize → (quiz || flashcards) → validate."""
        state = state or WorkflowState(workflow_name=self.name)
        state.status = "running"
        state.started_at = datetime.now(UTC)

        notebook_id: uuid.UUID = input["notebook_id"]
        max_bullets: int = input.get("max_bullets", 7)
        n_questions: int = input.get("n_questions", 5)
        n_cards: int = input.get("n_cards", 10)

        total = len(_NOTEBOOK_WORKFLOW_STEPS)
        try:
            await self.engine.run_step(
                state, "summarize", "summarizer",
                self._build_summary_input(notebook_id, max_bullets),
            )
            await self._report_step("summarize", 0, total)

            await self.engine.run_parallel(state, [
                ("quiz", "quiz", self._build_quiz_input(notebook_id, n_questions)),
                ("flashcards", "flashcard", self._build_flashcard_input(notebook_id, n_cards)),
            ])
            await self._report_step("quiz_and_flashcards", 1, total)

            # repair=True: fix malformed quiz in place rather than failing.
            quiz_output = state.get_output("quiz") or {}
            await self.engine.run_step(
                state, "validate_quiz", "validator",
                {
                    "content": quiz_output,
                    "criteria": [
                        "must contain a non-empty list 'questions'",
                        "each question must have exactly 4 options",
                        "each question must have a `correct_index` in 0..3",
                    ],
                    "repair": True,
                },
            )
            await self._report_step("validate_quiz", 2, total)

            # Prefer validator's repaired version.
            validation = state.get_output("validate_quiz") or {}
            quiz_final = validation.get("repaired") or quiz_output

            state.final_output = {
                "summary": (state.get_output("summarize") or {}).get("summary"),
                "quiz": (quiz_final or {}).get("questions"),
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
    def _build_summary_input(notebook_id: uuid.UUID, max_bullets: int) -> dict[str, Any]:
        return {"notebook_id": notebook_id, "max_bullets": max_bullets}

    @staticmethod
    def _build_quiz_input(notebook_id: uuid.UUID, n_questions: int) -> dict[str, Any]:
        return {"notebook_id": notebook_id, "n_questions": n_questions}

    @staticmethod
    def _build_flashcard_input(notebook_id: uuid.UUID, n_cards: int) -> dict[str, Any]:
        return {"notebook_id": notebook_id, "n_cards": n_cards}
