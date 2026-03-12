"""
Nova Voice Agent - Multi-Agent Entrypoint
Routes to the appropriate agent based on persisted mode.
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Add parent directory (src/) to path when running as subprocess
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()

from livekit import agents
from livekit.agents import AgentSession
from livekit.agents.voice.room_io import RoomInputOptions
from livekit.plugins import openai
from openai.types.beta.realtime.session import TurnDetection

from core.agent_state import AgentState
from agents.onboarding_agent import OnboardingAgent
from agents.main_menu_agent import MainMenuAgent
from agents.workout_agent import WorkoutAgent
from agents.program_creation_agent import ProgramCreationAgent
from agents.shared.userdata import UserData

logger = logging.getLogger(__name__)


async def entrypoint(ctx: agents.JobContext):
    """Main entry point for Nova voice agent"""

    logger.info("[NOVA] Entrypoint function called")

    # Discover user_id from room metadata or most recent state file
    logger.info("[NOVA] Checking for user_id in room metadata...")
    user_id = ctx.room.metadata.get('user_id') if ctx.room.metadata else None
    logger.info(f"[NOVA] user_id from metadata: {user_id}")

    if not user_id:
        import glob
        logger.info("[NOVA] Searching for state files...")
        state_files = glob.glob('.agent_state_*.json')
        logger.info(f"[NOVA] Found {len(state_files)} state files")
        if state_files:
            latest_state = max(state_files, key=os.path.getmtime)
            user_id = latest_state.replace('.agent_state_', '').replace('.json', '')
            logger.info(f"[NOVA] Found recent state file for user: {user_id}")

    # Initialize state
    logger.info(f"[NOVA] Creating AgentState with user_id: {user_id}...")
    state = AgentState(user_id=user_id)
    logger.info(f"[NOVA] Starting with mode: {state.get_mode()}")
    if user_id:
        logger.info(f"[NOVA] Loaded existing user: {user_id}")

    # Create shared userdata
    userdata = UserData(state=state, room=ctx.room)

    # Initialize OpenAI Realtime API model
    logger.info("[NOVA] Initializing OpenAI Realtime model...")
    realtime_model = openai.realtime.RealtimeModel(
        voice=os.getenv("REALTIME_VOICE", "alloy"),
        turn_detection=TurnDetection(
            type="semantic_vad",
            eagerness="low",
            create_response=True,
            interrupt_response=True,
        ),
        input_audio_noise_reduction="far_field",
        modalities=["audio", "text"],
    )
    logger.info("[NOVA] Realtime model initialized")

    # Create agent session
    logger.info("[NOVA] Creating agent session...")
    session = AgentSession(
        llm=realtime_model,
        userdata=userdata,
        preemptive_generation=False,
    )
    logger.info("[NOVA] Agent session created")

    # Select agent based on persisted mode
    mode = state.get_mode()
    agent_map = {
        "onboarding": OnboardingAgent,
        "main_menu": MainMenuAgent,
        "workout": WorkoutAgent,
        "program_creation": ProgramCreationAgent,
    }
    AgentClass = agent_map.get(mode, OnboardingAgent)
    agent = AgentClass(state=state, userdata=userdata)

    logger.info(f"[NOVA] Starting {AgentClass.__name__} (mode={mode})")

    # --- Session event tracking ---
    @session.on("agent_state_changed")
    def _on_agent_state(ev):
        logger.info(f"[SESSION] Agent state: {ev.old_state} → {ev.new_state}")

    @session.on("user_state_changed")
    def _on_user_state(ev):
        logger.info(f"[SESSION] User state: {ev.old_state} → {ev.new_state}")

    @session.on("user_input_transcribed")
    def _on_user_input(ev):
        if not ev.is_final and not ev.transcript.strip():
            return  # skip empty partials (VAD speech-start with no text yet)
        final_tag = "FINAL" if ev.is_final else "partial"
        logger.info(f"[SESSION] User speech [{final_tag}]: {ev.transcript}")

    @session.on("conversation_item_added")
    def _on_conversation_item(ev):
        item = ev.item
        role = getattr(item, "role", "unknown")
        text = getattr(item, "text_content", None)
        if callable(text):
            text = text()
        if text:
            logger.info(f"[SESSION] Conversation item ({role}): {text[:200]}")
        else:
            logger.info(f"[SESSION] Conversation item ({role}): [non-text content]")

    @session.on("speech_created")
    def _on_speech_created(ev):
        logger.info(
            f"[SESSION] Speech created — source={ev.source}, "
            f"user_initiated={ev.user_initiated}, "
            f"speech_id={ev.speech_handle.id}"
        )

    @session.on("metrics_collected")
    def _on_metrics(ev):
        m = ev.metrics
        if hasattr(m, "ttft"):
            logger.info(
                f"[METRICS] {m.type} — ttft={m.ttft:.3f}s, duration={m.duration:.3f}s, "
                f"cancelled={m.cancelled}, input_tokens={getattr(m, 'input_tokens', 'N/A')}, "
                f"output_tokens={getattr(m, 'output_tokens', 'N/A')}, "
                f"tps={getattr(m, 'tokens_per_second', 'N/A')}"
            )
        elif hasattr(m, "audio_duration"):
            logger.info(
                f"[METRICS] {m.type} — duration={m.duration:.3f}s, "
                f"audio_duration={m.audio_duration:.3f}s"
            )
        else:
            logger.info(f"[METRICS] {m.type}")

    @session.on("function_tools_executed")
    def _on_tools_executed(ev):
        for call, output in ev.zipped():
            result_str = str(output.output)[:150] if output else "None"
            logger.info(f"[SESSION] Tool executed: {call.name}({call.arguments}) → {result_str}")

    @session.on("error")
    def _on_error(ev):
        logger.error(f"[SESSION] Error from {ev.source}: {ev.error}")

    @session.on("close")
    def _on_close(ev):
        logger.info(f"[SESSION] Session closed — reason={ev.reason.value}, error={ev.error}")

    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            pre_connect_audio=True,
            pre_connect_audio_timeout=5.0,
        ),
    )

    logger.info(f"Nova voice agent started in room: {ctx.room.name}")


if __name__ == "__main__":
    import signal
    import sys

    shutting_down = False

    def signal_handler(signum, frame):
        """Handle shutdown signals gracefully"""
        global shutting_down
        if not shutting_down:
            shutting_down = True
            logger.info("[SHUTDOWN] Gracefully shutting down agent...")
            sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        agents.cli.run_app(
            agents.WorkerOptions(
                entrypoint_fnc=entrypoint,
            )
        )
    except KeyboardInterrupt:
        logger.info("[SHUTDOWN] Agent stopped by user")
        sys.exit(0)
    except Exception as e:
        if "termios" not in str(e).lower():
            logger.error(f"[ERROR] {e}")
        sys.exit(0)
