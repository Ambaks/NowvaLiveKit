"""
Tests for TeachingAgent state machine logic.

Covers: clean/fault rep counting, handoff trigger, fault deduplication,
phase gating, height threshold, fault list clearing, and independent
ascent/descent fault tracking.

All tests mock _say() and _truncate_context_for_handoff() to avoid
requiring a live LiveKit AgentSession.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.agents.teaching_agent import TeachingAgent, _TALL_THRESHOLD_CM
from agent.agents.teaching_phases import TeachingPhase
from biomechanics.utils.types import RepPhase
from agent.services.teaching_cues import CLEAN_REP_CUE_KEYS


# =============================================================================
# HELPERS
# =============================================================================


def _make_state(height_cm=170):
    """Create a mock AgentState with a user dict."""
    state = MagicMock()
    state.get_user.return_value = {
        "id": "test-user",
        "name": "Test",
        "height_cm": height_cm,
    }
    return state


def _make_userdata():
    """Create a mock userdata namespace with a stubbed AudioCueService."""
    ud = MagicMock()
    ud.audio_cue_service = MagicMock()
    ud.audio_cue_service.play_cue = AsyncMock()
    ud.audio_cue_service.cache_cues = AsyncMock()
    return ud


def _make_agent(height_cm=170, exercise="squat"):
    """Construct a TeachingAgent with all external deps mocked.

    Patches _say and _truncate_context_for_handoff so tests never
    reach into the real LiveKit session.
    """
    state = _make_state(height_cm)
    userdata = _make_userdata()
    agent = TeachingAgent(state=state, userdata=userdata, exercise=exercise)

    # Replace _say with an async no-op that records calls.
    agent._say = AsyncMock()

    # Replace _truncate_context_for_handoff with an async no-op.
    agent._truncate_context_for_handoff = AsyncMock()

    # Mock the session property for update_agent (handoff).
    mock_session = MagicMock()
    mock_session.update_agent = MagicMock()
    # Patch the property on the instance by setting _session and
    # monkey-patching the class-level property to return it.
    agent._mock_session = mock_session

    return agent


def _event(squat_phase="descending", knee_fault=False, chest_fault=False):
    """Build a minimal biomechanics event dict."""
    return {
        "squat_phase": squat_phase,
        "knee_fault": knee_fault,
        "chest_fault": chest_fault,
    }


# =============================================================================
# 1. Clean rep increments consecutive_correct_reps
# =============================================================================


class TestCleanRepIncrement:
    def test_clean_rep_increments(self):
        async def _run():
            agent = _make_agent()
            agent.phase = TeachingPhase.REP_COMPLETE
            agent.current_rep_faults = []

            await agent._complete_rep()

            assert agent.consecutive_correct_reps == 1
        asyncio.run(_run())

    def test_multiple_clean_reps_accumulate(self):
        async def _run():
            agent = _make_agent()
            agent.current_rep_faults = []

            for _ in range(3):
                agent.phase = TeachingPhase.REP_COMPLETE
                await agent._complete_rep()

            assert agent.consecutive_correct_reps == 3
        asyncio.run(_run())


# =============================================================================
# 2. Fault rep resets consecutive_correct_reps to 0
# =============================================================================


class TestFaultRepReset:
    def test_fault_resets_streak(self):
        async def _run():
            agent = _make_agent()
            agent.consecutive_correct_reps = 3
            agent.current_rep_faults = ["knee"]

            await agent._complete_rep()

            assert agent.consecutive_correct_reps == 0
        asyncio.run(_run())

    def test_fault_after_clean_reps_resets(self):
        async def _run():
            agent = _make_agent()

            # Two clean reps
            for _ in range(2):
                agent.current_rep_faults = []
                agent.phase = TeachingPhase.REP_COMPLETE
                await agent._complete_rep()
            assert agent.consecutive_correct_reps == 2

            # One fault rep
            agent.current_rep_faults = ["chest"]
            agent.phase = TeachingPhase.REP_COMPLETE
            await agent._complete_rep()
            assert agent.consecutive_correct_reps == 0
        asyncio.run(_run())


# =============================================================================
# 3. Four consecutive clean reps trigger _handoff()
# =============================================================================


class TestHandoffTrigger:
    def test_four_clean_reps_trigger_handoff(self):
        async def _run():
            agent = _make_agent()
            agent.consecutive_correct_reps = 3
            agent.current_rep_faults = []

            with patch.object(agent, '_handoff', new_callable=AsyncMock) as mock_handoff:
                await agent._complete_rep()
                mock_handoff.assert_awaited_once()
        asyncio.run(_run())

    def test_three_clean_reps_no_handoff(self):
        async def _run():
            agent = _make_agent()
            agent.consecutive_correct_reps = 2
            agent.current_rep_faults = []

            with patch.object(agent, '_handoff', new_callable=AsyncMock) as mock_handoff:
                await agent._complete_rep()
                mock_handoff.assert_not_awaited()
            assert agent.consecutive_correct_reps == 3
        asyncio.run(_run())

    def test_handoff_sets_phase_and_calls_say(self):
        async def _run():
            agent = _make_agent()

            # Patch session property to avoid LiveKit internals.
            with patch.object(
                type(agent), 'session',
                new_callable=lambda: property(lambda self: self._mock_session),
            ):
                await agent._handoff()

            assert agent.phase == TeachingPhase.HANDOFF
            agent._say.assert_awaited_once()
            agent._truncate_context_for_handoff.assert_awaited_once()
            agent._mock_session.update_agent.assert_called_once()
        asyncio.run(_run())


# =============================================================================
# 4. Fault deduplication — same fault does not fire cue twice in one rep
# =============================================================================


class TestFaultDeduplication:
    def test_knee_fault_fires_once_per_rep(self):
        async def _run():
            agent = _make_agent()
            agent.phase = TeachingPhase.DESCENDING
            audio = agent.userdata.audio_cue_service

            # First knee fault
            await agent.on_biomechanics_event(_event(knee_fault=True))
            assert audio.play_cue.await_count == 1

            # Second knee fault in same rep — should NOT fire
            await agent.on_biomechanics_event(_event(knee_fault=True))
            assert audio.play_cue.await_count == 1
        asyncio.run(_run())

    def test_different_faults_both_fire(self):
        async def _run():
            agent = _make_agent()
            agent.phase = TeachingPhase.DESCENDING
            audio = agent.userdata.audio_cue_service

            await agent.on_biomechanics_event(_event(knee_fault=True))
            await agent.on_biomechanics_event(_event(chest_fault=True))

            assert audio.play_cue.await_count == 2
            calls = [c[0][0] for c in audio.play_cue.call_args_list]
            assert "knees_out" in calls
            assert "chest_up" in calls
        asyncio.run(_run())


# =============================================================================
# 5. Phase only re-opens to DESCENDING after speech resolves
# =============================================================================


class TestPhaseGating:
    def test_phase_descending_after_clean_rep(self):
        async def _run():
            agent = _make_agent()
            agent.phase = TeachingPhase.REP_COMPLETE
            agent.current_rep_faults = []

            await agent._complete_rep()

            assert agent.phase == TeachingPhase.DESCENDING
        asyncio.run(_run())

    def test_phase_descending_after_fault_rep(self):
        async def _run():
            agent = _make_agent()
            agent.phase = TeachingPhase.REP_COMPLETE
            agent.current_rep_faults = ["knee"]

            await agent._complete_rep()

            assert agent.phase == TeachingPhase.DESCENDING
        asyncio.run(_run())

    def test_events_ignored_in_setup_phase(self):
        async def _run():
            agent = _make_agent()
            agent.phase = TeachingPhase.SETUP
            audio = agent.userdata.audio_cue_service

            await agent.on_biomechanics_event(_event(knee_fault=True))

            audio.play_cue.assert_not_awaited()
        asyncio.run(_run())

    def test_events_ignored_in_rep_complete_phase(self):
        async def _run():
            agent = _make_agent()
            agent.phase = TeachingPhase.REP_COMPLETE
            audio = agent.userdata.audio_cue_service

            await agent.on_biomechanics_event(_event(knee_fault=True))

            audio.play_cue.assert_not_awaited()
        asyncio.run(_run())

    def test_events_ignored_in_handoff_phase(self):
        async def _run():
            agent = _make_agent()
            agent.phase = TeachingPhase.HANDOFF
            audio = agent.userdata.audio_cue_service

            await agent.on_biomechanics_event(_event(knee_fault=True))

            audio.play_cue.assert_not_awaited()
        asyncio.run(_run())


# =============================================================================
# 6. is_tall flag set correctly at height boundary (185cm)
# =============================================================================


class TestHeightThreshold:
    def test_tall_at_185(self):
        agent = _make_agent(height_cm=185)
        assert agent.user_is_tall is True

    def test_not_tall_at_184(self):
        agent = _make_agent(height_cm=184)
        assert agent.user_is_tall is False

    def test_tall_above_185(self):
        agent = _make_agent(height_cm=200)
        assert agent.user_is_tall is True

    def test_not_tall_below_185(self):
        agent = _make_agent(height_cm=170)
        assert agent.user_is_tall is False

    def test_none_height_defaults_false(self):
        state = MagicMock()
        state.get_user.return_value = {"id": "u", "name": "N", "height_cm": None}
        userdata = _make_userdata()
        agent = TeachingAgent(state=state, userdata=userdata)
        assert agent.user_is_tall is False


# =============================================================================
# 7. current_rep_faults cleared at start of _complete_rep
# =============================================================================


class TestFaultListClearing:
    def test_faults_cleared_after_complete_rep(self):
        async def _run():
            agent = _make_agent()
            agent.current_rep_faults = ["knee", "chest"]

            await agent._complete_rep()

            assert agent.current_rep_faults == []
        asyncio.run(_run())

    def test_faults_cleared_even_on_clean_rep(self):
        async def _run():
            agent = _make_agent()
            agent.current_rep_faults = []

            await agent._complete_rep()

            assert agent.current_rep_faults == []
        asyncio.run(_run())

    def test_faults_copied_before_clearing(self):
        """Ensure the fault feedback uses the original faults, not the cleared list."""
        async def _run():
            agent = _make_agent()
            agent.current_rep_faults = ["knee", "chest_ascent"]

            # Track what _say is called with.
            captured_instructions = []
            original_mock = agent._say

            async def capture_say(instructions, **kwargs):
                captured_instructions.append(instructions)

            agent._say = AsyncMock(side_effect=capture_say)

            await agent._complete_rep()

            # The LLM instruction should mention the faults
            assert len(captured_instructions) == 1
            assert "knee" in captured_instructions[0]
            assert "chest_ascent" in captured_instructions[0]
            # But the fault list should be cleared
            assert agent.current_rep_faults == []
        asyncio.run(_run())


# =============================================================================
# 8. Ascent fault tracked independently from descent fault
# =============================================================================


class TestAscentDescentIndependence:
    def test_knee_tracked_independently(self):
        async def _run():
            agent = _make_agent()
            agent.phase = TeachingPhase.DESCENDING
            audio = agent.userdata.audio_cue_service

            # Knee fault on descent
            await agent.on_biomechanics_event(_event(knee_fault=True))
            assert "knee" in agent.current_rep_faults
            assert audio.play_cue.await_count == 1

            # Transition to bottom then ascending
            await agent.on_biomechanics_event(_event(squat_phase=RepPhase.BOTTOM.value))
            assert agent.phase == TeachingPhase.ASCENDING

            # Knee fault on ascent — should fire again (separate key)
            await agent.on_biomechanics_event(
                _event(squat_phase=RepPhase.ASCENDING.value, knee_fault=True)
            )
            assert "knee_ascent" in agent.current_rep_faults
            # play_cue called: knees_out (descent) + up (bottom) + knees_out (ascent) = 3
            assert audio.play_cue.await_count == 3
        asyncio.run(_run())

    def test_chest_tracked_independently(self):
        async def _run():
            agent = _make_agent()
            agent.phase = TeachingPhase.DESCENDING
            audio = agent.userdata.audio_cue_service

            # Chest fault on descent
            await agent.on_biomechanics_event(_event(chest_fault=True))
            assert "chest" in agent.current_rep_faults

            # Transition to ascending
            await agent.on_biomechanics_event(_event(squat_phase=RepPhase.BOTTOM.value))
            assert agent.phase == TeachingPhase.ASCENDING

            # Chest fault on ascent
            await agent.on_biomechanics_event(
                _event(squat_phase=RepPhase.ASCENDING.value, chest_fault=True)
            )
            assert "chest_ascent" in agent.current_rep_faults
            # chest_up (descent) + up (bottom) + chest_up (ascent) = 3
            assert audio.play_cue.await_count == 3
        asyncio.run(_run())

    def test_all_four_fault_keys_can_coexist(self):
        async def _run():
            agent = _make_agent()
            agent.phase = TeachingPhase.DESCENDING
            audio = agent.userdata.audio_cue_service

            # Both faults on descent
            await agent.on_biomechanics_event(_event(knee_fault=True, chest_fault=True))

            # Transition to ascending
            await agent.on_biomechanics_event(_event(squat_phase=RepPhase.BOTTOM.value))

            # Both faults on ascent
            await agent.on_biomechanics_event(
                _event(squat_phase=RepPhase.ASCENDING.value, knee_fault=True, chest_fault=True)
            )

            assert set(agent.current_rep_faults) == {"knee", "chest", "knee_ascent", "chest_ascent"}
        asyncio.run(_run())


# =============================================================================
# ADDITIONAL: Full rep cycle integration test
# =============================================================================


class TestFullRepCycle:
    def test_clean_rep_full_cycle(self):
        """Simulate a full clean rep: descending -> bottom -> ascending -> standing."""
        async def _run():
            agent = _make_agent()
            agent.phase = TeachingPhase.DESCENDING
            audio = agent.userdata.audio_cue_service

            # Descending (no faults)
            await agent.on_biomechanics_event(_event(squat_phase=RepPhase.DESCENDING.value))
            assert agent.phase == TeachingPhase.DESCENDING

            # Bottom
            await agent.on_biomechanics_event(_event(squat_phase=RepPhase.BOTTOM.value))
            assert agent.phase == TeachingPhase.ASCENDING

            # Ascending (no faults)
            await agent.on_biomechanics_event(_event(squat_phase=RepPhase.ASCENDING.value))
            assert agent.phase == TeachingPhase.ASCENDING

            # Standing — triggers rep completion
            await agent.on_biomechanics_event(_event(squat_phase=RepPhase.STANDING.value))

            assert agent.consecutive_correct_reps == 1
            assert agent.phase == TeachingPhase.DESCENDING
            assert agent.current_rep_faults == []

            # "up" cue + one random clean rep cue
            assert audio.play_cue.await_count == 2
            cue_calls = [c[0][0] for c in audio.play_cue.call_args_list]
            assert cue_calls[0] == "up"
            assert cue_calls[1] in CLEAN_REP_CUE_KEYS
        asyncio.run(_run())

    def test_four_clean_reps_trigger_handoff_full_cycle(self):
        """Simulate 4 clean reps end-to-end and verify handoff."""
        async def _run():
            agent = _make_agent()
            agent.phase = TeachingPhase.DESCENDING

            # Patch session property for the handoff call.
            with patch.object(
                type(agent), 'session',
                new_callable=lambda: property(lambda self: self._mock_session),
            ):
                for _ in range(4):
                    await agent.on_biomechanics_event(_event(squat_phase=RepPhase.BOTTOM.value))
                    await agent.on_biomechanics_event(_event(squat_phase=RepPhase.STANDING.value))

            assert agent.phase == TeachingPhase.HANDOFF
            agent._mock_session.update_agent.assert_called_once()
        asyncio.run(_run())
