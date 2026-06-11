"""Runs an AgentTask from non-inline contexts (e.g. IPC-triggered coaching demos)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from livekit.agents.voice.agent import _set_activity_task_info

logger = logging.getLogger(__name__)


def start_inline_agent_task(session, agent_task) -> asyncio.Task[Any]:
    """Schedule an AgentTask as if launched from an inline context.

    livekit-agents 1.5.17 only allows awaiting an AgentTask from on_enter/
    on_exit/function-tool tasks: Agent.__await_impl requires the inline_task
    marker on the current asyncio task and reads _AgentActivityContextVar.
    This mirrors how the framework launches on_enter itself
    (agent_activity.py:600-604): create the task via
    activity._create_speech_task (which sets the activity context var) and
    mark it inline. The AgentTask machinery then pauses the current agent's
    activity and resumes it when the task completes.

    Pinned to livekit-agents 1.5.17 private API. If this breaks after an
    upgrade, fall back to `session.update_agent(agent_task)` plus a re-entry
    guard in the previous agent's on_enter (update_agent closes rather than
    pauses the old activity).
    """
    activity = session._activity
    if activity is None:
        raise RuntimeError("No active agent activity — cannot start inline AgentTask")

    async def _await_task() -> Any:
        return await agent_task

    task = activity._create_speech_task(_await_task(), name="coaching_demo_runner")
    _set_activity_task_info(task, inline_task=True)
    return task
