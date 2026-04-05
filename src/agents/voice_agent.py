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
from livekit.plugins import deepgram, groq, cartesia, silero, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from core.agent_state import AgentState
from agents.onboarding_agent import OnboardingAgent
from agents.main_menu_agent import MainMenuAgent
from agents.workout_agent import WorkoutAgent
from agents.program_creation_agent import ProgramCreationAgent
from agents.schedule_agent import ScheduleMaintenanceAgent
from agents.shared.userdata import UserData
from core.latency_tracker import LatencyTracker
from services.compaction_service import CompactionService

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

    # Retrieve prewarmed AudioCueService (if available)
    prewarmed_cue_svc = ctx.proc.userdata.get("audio_cue_service")
    if prewarmed_cue_svc is not None:
        userdata.audio_cue_service = prewarmed_cue_svc
        logger.info("[NOVA] Prewarmed AudioCueService attached to userdata")

    # Initialize cascade pipeline components (STT + LLM + TTS)
    logger.info("[NOVA] Initializing cascade pipeline...")
    stt = deepgram.STT(
        model="nova-3",
        language="en",
        keyterm=[
            "Barbell Back Squat", "Romanian Deadlift", "Barbell Bench Press",
            "Barbell Overhead Press", "Barbell Front Squat", "Goblet Squat",
            "Sumo Deadlift", "Barbell Deadlift",
            "reps", "sets", "RPE", "deload", "hypertrophy",
        ],
    )

    llm = groq.LLM(
        model=os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
    )

    tts = cartesia.TTS(
        model="sonic-3",
        voice=os.getenv("CARTESIA_VOICE_ID", "default"),
    )
    logger.info("[NOVA] Cascade pipeline initialized")

    # Retrieve prewarmed VAD or load fresh as fallback
    vad = ctx.proc.userdata.get("vad")
    if vad is None:
        logger.warning("[NOVA] No prewarmed VAD found, loading fresh (~100-500ms)...")
        vad = silero.VAD.load()
    else:
        logger.info("[NOVA] Using prewarmed Silero VAD")

    # Create agent session with cascade pipeline
    logger.info("[NOVA] Creating agent session...")
    session = AgentSession(
        stt=stt,
        llm=llm,
        tts=tts,
        vad=vad,
        turn_handling={"turn_detection": MultilingualModel()},
        userdata=userdata,
        preemptive_generation=True,
    )
    logger.info("[NOVA] Agent session created")

    # Initialize compaction service for rolling context summarization
    compaction_service = CompactionService(
        session=session,
        state=state,
        user_id=user_id or "guest",
    )
    userdata.compaction_service = compaction_service

    # Select agent based on persisted mode
    mode = state.get_mode()
    agent_map = {
        "onboarding": OnboardingAgent,
        "main_menu": MainMenuAgent,
        "workout": WorkoutAgent,
        "program_creation": ProgramCreationAgent,
        "schedule": ScheduleMaintenanceAgent,
    }
    AgentClass = agent_map.get(mode, OnboardingAgent)
    agent = AgentClass(state=state, userdata=userdata)

    logger.info(f"[NOVA] Starting {AgentClass.__name__} (mode={mode})")

    # Initialize latency tracker
    latency_tracker = LatencyTracker.get_instance()
    latency_tracker.reset()

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
            # Feed TTFT into latency tracker
            latency_tracker.record_ttft(m.ttft)
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
        # Log final latency summary
        latency_tracker.log_summary()

        # Stop compaction service
        try:
            compaction = userdata.compaction_service
            if compaction:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(compaction.stop(), loop)
                userdata.compaction_service = None
                logger.info("[SESSION] Compaction service stopped on close")
        except Exception as e:
            logger.error(f"[SESSION] Failed to stop compaction service: {e}")

        # Graceful cleanup if session closes during workout
        if state.get_mode() == "workout":
            logger.info("[SESSION] Session closed during workout — saving state")
            try:
                coaching = userdata.coaching_service
                if coaching:
                    import asyncio
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.run_coroutine_threadsafe(coaching.stop(), loop)
                    userdata.coaching_service = None
                state.save_state()
                logger.info("[SESSION] Workout state saved on close")
            except Exception as e:
                logger.error(f"[SESSION] Failed to save workout state on close: {e}")

    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
            pre_connect_audio=True,
            pre_connect_audio_timeout=5.0,
        ),
    )

    # Start compaction service after session is live
    if userdata.compaction_service:
        await userdata.compaction_service.start()
        logger.info("[NOVA] Compaction service started")

    logger.info(f"Nova voice agent started in room: {ctx.room.name}")


def prewarm(proc: agents.JobProcess):
    """Pre-load heavy resources before any room connection.

    Runs silero VAD model loading and audio cue disk I/O concurrently
    so neither blocks the other.  Results are stored on proc.userdata
    for retrieval in entrypoint().
    """
    import concurrent.futures
    import time

    logger.info("[PREWARM] Starting parallel pre-load (VAD + audio cues)...")
    start = time.monotonic()

    def _load_vad():
        return silero.VAD.load()

    def _load_audio_cues():
        from services.audio_cue_service import AudioCueService
        return AudioCueService(session=None)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        vad_future = executor.submit(_load_vad)
        cue_future = executor.submit(_load_audio_cues)

        try:
            proc.userdata["vad"] = vad_future.result(timeout=10)
            logger.info("[PREWARM] Silero VAD pre-loaded")
        except Exception as e:
            logger.warning(f"[PREWARM] VAD pre-load failed (will load in entrypoint): {e}")

        try:
            cue_svc = cue_future.result(timeout=30)
            proc.userdata["audio_cue_service"] = cue_svc
            logger.info(
                f"[PREWARM] Audio cues pre-loaded: {len(cue_svc._memory_cache)} cue keys, "
                f"{sum(len(v) for v in cue_svc._memory_cache.values())} variants"
            )
        except Exception as e:
            logger.warning(f"[PREWARM] Audio cue pre-load failed (will retry at session start): {e}")

    elapsed = time.monotonic() - start
    logger.info(f"[PREWARM] Parallel pre-load complete in {elapsed:.3f}s")


if __name__ == "__main__":
    import sys

    try:
        agents.cli.run_app(
            agents.WorkerOptions(
                entrypoint_fnc=entrypoint,
                prewarm_fnc=prewarm,
            )
        )
    except KeyboardInterrupt:
        logger.info("[SHUTDOWN] Agent stopped by user")
        sys.exit(0)
    except Exception as e:
        if "termios" not in str(e).lower():
            logger.error(f"[ERROR] {e}")
        sys.exit(0)
