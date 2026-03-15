"""
Base agent class with shared properties and helpers for all Nova agents.
"""

import logging
from livekit.agents import Agent
from openai.types.beta.realtime.session import TurnDetection
from core.agent_state import AgentState

logger = logging.getLogger(__name__)


class BaseNovaAgent(Agent):
    """Base class for all Nova voice agents with shared state access and utilities."""

    def __init__(self, state: AgentState, userdata, instructions: str) -> None:
        self.state = state
        self.userdata = userdata
        super().__init__(instructions=instructions)

    @property
    def user_id(self) -> str:
        """Get current user ID from state"""
        return self.state.get_user().get("id")

    @property
    def user_name(self) -> str:
        """Get current user name from state, defaults to 'there'"""
        return self.state.get_user().get("name", "there")

    def _suppress_turn_detection(self):
        """Suppress auto-responses and interruptions on the Realtime session."""
        self.session.llm.update_options(
            turn_detection=TurnDetection(
                type="semantic_vad",
                eagerness="low",
                create_response=False,
                interrupt_response=False,
            )
        )

    def _restore_turn_detection(self):
        """Restore normal conversational turn detection."""
        self.session.llm.update_options(
            turn_detection=TurnDetection(
                type="semantic_vad",
                eagerness="low",
                create_response=True,
                interrupt_response=True,
            )
        )

    async def _say(self, instructions: str, wait: bool = True, restore: bool = True):
        """Generate a greeting that won't be cut off by turn detection.

        Suppresses auto-responses/interruptions before speaking, waits for
        full playout, then optionally restores normal turn detection.

        Args:
            instructions: The instruction for the LLM to generate speech from.
            wait: If True, block until speech finishes playing.
            restore: If True, restore normal turn detection after playout.
        """
        self._suppress_turn_detection()
        handle = self.session.generate_reply(
            instructions=instructions,
            tool_choice="none",
        )
        if wait:
            await handle.wait_for_playout()
        if restore:
            self._restore_turn_detection()
        return handle

    async def _truncate_context_for_handoff(self, max_items: int = 6):
        """Truncate conversation context before agent handoff.

        Prevents passing the full conversation history (e.g., an entire
        workout session) to the next agent. Keeps only the last N items.
        """
        try:
            ctx = self.chat_ctx
            if len(ctx.items) <= max_items:
                return
            old_count = len(ctx.items)
            new_ctx = ctx.copy()
            new_ctx.truncate(max_items=max_items)
            await self.update_chat_ctx(new_ctx)
            logger.info(
                f"[HANDOFF] Truncated context: {old_count} → {len(new_ctx.items)} items"
            )
        except Exception as e:
            logger.warning(f"[HANDOFF] Context truncation failed: {e}")

    def _log_function_call(self, function_name: str, parameters: dict, result):
        """Helper method to log function tool calls"""
        from core.session_logger import SessionLogger
        from core.token_estimator import estimate_function_call_tokens

        session_logger = SessionLogger.get_instance()
        estimated_tokens = estimate_function_call_tokens(function_name, parameters, result)

        session_logger.log_function_call(
            function_name=function_name,
            parameters=parameters,
            result=result,
            estimated_tokens=estimated_tokens
        )
