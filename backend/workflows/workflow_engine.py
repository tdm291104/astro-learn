"""Execution helpers: sequential, parallel, conditional."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from agents.base.agent_state import AgentState
from workflows.base_workflow import AgentFactory, WorkflowState

StepSpec = tuple[str, str, dict[str, Any]]


ConditionPredicate = Callable[[WorkflowState], bool]


class WorkflowEngine:
    """Helpers for executing one or more steps inside a workflow."""

    def __init__(self, agent_factory: AgentFactory) -> None:
        self.agent_factory = agent_factory

    async def run_step(
        self,
        state: WorkflowState,
        step_name: str,
        agent_name: str,
        task_input: dict[str, Any],
    ) -> AgentState:
        """Build agent, run it, store result under step_name."""
        state.current_step = step_name
        agent = self.agent_factory(agent_name)
        sub_state = AgentState(
            agent_name=agent_name,
            user_id=state.user_id,
            session_id=state.session_id,
        )
        result = await agent.run(task_input, state=sub_state)
        state.step_results[step_name] = result
        return result

    async def run_parallel(
        self,
        state: WorkflowState,
        steps: list[StepSpec],
    ) -> dict[str, AgentState]:
        """Run steps concurrently; any exception cancels siblings."""
        if not steps:
            return {}

        async def _one(step: StepSpec) -> tuple[str, AgentState]:
            step_name, agent_name, task_input = step
            agent = self.agent_factory(agent_name)
            sub_state = AgentState(
                agent_name=agent_name,
                user_id=state.user_id,
                session_id=state.session_id,
            )
            result = await agent.run(task_input, state=sub_state)
            return step_name, result

        completed = await asyncio.gather(*(_one(s) for s in steps))

        result_map = dict(completed)
        state.step_results.update(result_map)
        return result_map

    async def run_conditional(
        self,
        state: WorkflowState,
        branches: list[tuple[ConditionPredicate, StepSpec]],
        *,
        default: StepSpec | None = None,
    ) -> AgentState | None:
        """Run first matching branch, else default. Predicate errors propagate."""
        for predicate, spec in branches:
            if predicate(state):
                step_name, agent_name, task_input = spec
                return await self.run_step(state, step_name, agent_name, task_input)
        if default is not None:
            step_name, agent_name, task_input = default
            return await self.run_step(state, step_name, agent_name, task_input)
        return None
