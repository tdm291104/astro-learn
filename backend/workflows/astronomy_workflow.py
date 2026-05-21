"""FITS analysis pipeline: analyze, optionally render image, prepare report."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from workflows.base_workflow import AgentFactory, BaseWorkflow, WorkflowState
from workflows.workflow_engine import WorkflowEngine


class AstronomyWorkflow(BaseWorkflow):
    """Run an analysis on an uploaded FITS file and prepare a report."""

    name: ClassVar[str] = "astronomy"
    description: ClassVar[str] = (
        "End-to-end FITS analysis: analyse, optionally render a viewable "
        "image, and emit a stable analysis_id for downstream reporting."
    )

    def __init__(self, agent_factory: AgentFactory) -> None:
        super().__init__(agent_factory=agent_factory)
        self.engine = WorkflowEngine(agent_factory=agent_factory)

    async def run(
        self,
        input: dict[str, Any],
        *,
        state: WorkflowState | None = None,
    ) -> WorkflowState:
        """data_analyst → (optional) image_processor."""
        state = state or WorkflowState(workflow_name=self.name)
        state.status = "running"
        state.started_at = datetime.now(UTC)

        file_id: uuid.UUID = input["file_id"]
        hdu_index: int = input.get("hdu_index", 0)
        analysis_type: str = input["analysis_type"]
        params: dict[str, Any] = input.get("params") or {}
        render_image: bool = bool(input.get("render_image", False))

        try:
            analyst_state = await self.engine.run_step(
                state, "analyze", "data_analyst",
                self._build_analyst_input(file_id, hdu_index, analysis_type, params),
            )
            analyst_output = analyst_state.final_output or {}

            # Processor reads analyst output to target detected sources.
            image_url: str | None = None
            if render_image:
                image_state = await self.engine.run_step(
                    state, "render_image", "image_processor",
                    self._build_image_processor_input(file_id, hdu_index, analyst_output),
                )
                image_url = (image_state.final_output or {}).get("artifact_url")

            analyst_artifacts = [
                str(a) for a in (analyst_output.get("artifacts") or [])
            ]
            if image_url:
                analyst_artifacts.append(image_url)

            state.final_output = {
                "analysis_id": analyst_output.get("analysis_id"),
                "results": analyst_output.get("results", {}),
                "artifacts": analyst_artifacts,
                "image_artifact_url": image_url,
            }
            state.status = "succeeded"
        except Exception as exc:
            state.status = "failed"
            state.error = str(exc)
            raise
        finally:
            state.finished_at = datetime.now(UTC)

        return state

    @staticmethod
    def _build_analyst_input(
        file_id: uuid.UUID,
        hdu_index: int,
        analysis_type: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "file_id": file_id,
            "hdu_index": hdu_index,
            "analysis_type": analysis_type,
            "params": params,
        }

    @staticmethod
    def _build_image_processor_input(
        file_id: uuid.UUID,
        hdu_index: int,
        analyst_results: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "file_id": file_id,
            "hdu_index": hdu_index,
            "analyst_results": analyst_results,
        }
