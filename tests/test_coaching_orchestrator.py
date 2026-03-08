"""
Tests for CoachingOrchestrator

Verifies priority ordering, motivation trigger logic, audio ducking,
set recap dispatch, and stale event handling.
"""

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from services.coaching_orchestrator import (
    CoachingEvent,
    CoachingOrchestrator,
    CuePriority,
)


# =============================================================================
# FIXTURES
# =============================================================================


def _make_callbacks():
    """Create mock async callbacks for the orchestrator."""
    return {
        "play_cached_audio_fn": AsyncMock(),
        "generate_llm_reply_fn": AsyncMock(),
        "duck_llm_fn": AsyncMock(),
        "unduck_llm_fn": AsyncMock(),
        "get_cue_audio_fn": lambda key: b"fake_audio" if key else None,
    }


@pytest.fixture
def mock_callbacks():
    return _make_callbacks()


@pytest.fixture
def orchestrator(mock_callbacks):
    return CoachingOrchestrator(**mock_callbacks)


# =============================================================================
# TEST PRIORITY ORDERING
# =============================================================================


class TestCuePriority:
    """Test that priority values are correctly ordered."""

    def test_fault_highest_priority(self):
        assert CuePriority.FAULT_CUE < CuePriority.REP_COUNT_CUE
        assert CuePriority.FAULT_CUE < CuePriority.LLM_MOTIVATION

    def test_cached_cues_before_llm(self):
        assert CuePriority.POSITIVE_CUE < CuePriority.LLM_MOTIVATION

    def test_motivation_before_recap(self):
        assert CuePriority.LLM_MOTIVATION < CuePriority.LLM_SET_RECAP

    def test_event_ordering(self):
        """CoachingEvents should sort by priority."""
        events = [
            CoachingEvent(CuePriority.LLM_SET_RECAP, time.monotonic(), "llm_set_recap"),
            CoachingEvent(CuePriority.FAULT_CUE, time.monotonic(), "cached_cue", "knees_out"),
            CoachingEvent(CuePriority.LLM_MOTIVATION, time.monotonic(), "llm_motivation"),
            CoachingEvent(CuePriority.REP_COUNT_CUE, time.monotonic(), "cached_cue", "rep_1"),
        ]
        sorted_events = sorted(events)
        assert sorted_events[0].priority == CuePriority.FAULT_CUE
        assert sorted_events[1].priority == CuePriority.REP_COUNT_CUE
        assert sorted_events[2].priority == CuePriority.LLM_MOTIVATION
        assert sorted_events[3].priority == CuePriority.LLM_SET_RECAP


# =============================================================================
# TEST MOTIVATION TRIGGERS
# =============================================================================


class TestMotivationTriggers:
    """Test deterministic motivation trigger logic."""

    def test_no_trigger_on_first_rep(self, orchestrator):
        assert orchestrator._should_trigger_motivation(1) is False

    def test_trigger_every_n_reps(self, orchestrator):
        assert orchestrator._should_trigger_motivation(3) is True
        assert orchestrator._should_trigger_motivation(6) is True
        assert orchestrator._should_trigger_motivation(9) is True

    def test_no_trigger_between_intervals(self, orchestrator):
        assert orchestrator._should_trigger_motivation(2) is False
        assert orchestrator._should_trigger_motivation(4) is False
        assert orchestrator._should_trigger_motivation(5) is False

    def test_trigger_last_2_reps(self, orchestrator):
        orchestrator._set_target_reps = 8
        assert orchestrator._should_trigger_motivation(6) is True
        assert orchestrator._should_trigger_motivation(7) is True

    def test_no_trigger_if_just_triggered(self, orchestrator):
        orchestrator._last_motivation_rep = 3
        assert orchestrator._should_trigger_motivation(4) is False
        assert orchestrator._should_trigger_motivation(5) is False

    def test_trigger_clean_streak(self, orchestrator):
        orchestrator._clean_streak = 3
        assert orchestrator._should_trigger_motivation(4) is True

    def test_no_trigger_clean_streak_under_3(self, orchestrator):
        orchestrator._clean_streak = 2
        assert orchestrator._should_trigger_motivation(2) is False

    def test_build_motivation_context(self, orchestrator):
        orchestrator._set_target_reps = 10
        orchestrator._clean_streak = 4
        orchestrator._recent_faults = ["knee_valgus", "forward_lean"]
        context = orchestrator._build_motivation_context(6, "parallel", True)
        assert context["rep_number"] == 6
        assert context["reps_remaining"] == 4
        assert context["clean_streak"] == 4
        assert "knee_valgus" in context["recent_faults"]


# =============================================================================
# TEST EVENT ENQUEUEING
# =============================================================================


class TestEventEnqueueing:
    """Test that events are correctly enqueued."""

    def test_on_fault_enqueues(self, orchestrator):
        async def _run():
            await orchestrator.on_fault("knees_out", "knee_valgus", "moderate")
            assert not orchestrator._queue.empty()
            event = orchestrator._queue.get_nowait()
            assert event.priority == CuePriority.FAULT_CUE
            assert event.cue_key == "knees_out"
        asyncio.run(_run())

    def test_on_fault_no_audio_skips(self):
        cbs = _make_callbacks()
        cbs["get_cue_audio_fn"] = lambda key: None
        orch = CoachingOrchestrator(**cbs)

        async def _run():
            await orch.on_fault("unknown_cue", "unknown", "mild")
            assert orch._queue.empty()
        asyncio.run(_run())

    def test_on_fault_rate_limited(self, orchestrator):
        async def _run():
            await orchestrator.on_fault("knees_out", "knee_valgus", "moderate")
            assert not orchestrator._queue.empty()
            orchestrator._queue.get_nowait()  # drain first
            # Second fault within gap should be skipped
            await orchestrator.on_fault("chest_up", "forward_lean", "severe")
            assert orchestrator._queue.empty()
        asyncio.run(_run())

    def test_on_fault_tracks_recent_faults(self, orchestrator):
        async def _run():
            await orchestrator.on_fault("knees_out", "knee_valgus", "moderate")
            assert "knee_valgus" in orchestrator._recent_faults
        asyncio.run(_run())

    def test_on_rep_complete_enqueues_rep_cue(self, orchestrator):
        async def _run():
            await orchestrator.on_rep_complete(1, "parallel", True, [])
            event = orchestrator._queue.get_nowait()
            assert event.priority == CuePriority.REP_COUNT_CUE
            assert event.cue_key == "rep_1"
        asyncio.run(_run())

    def test_on_rep_complete_clean_enqueues_positive(self, orchestrator):
        orchestrator._positive_cue_keys = ["good_rep", "strong"]

        async def _run():
            await orchestrator.on_rep_complete(1, "parallel", True, [])
            events = []
            while not orchestrator._queue.empty():
                events.append(orchestrator._queue.get_nowait())
            positive = [e for e in events if e.priority == CuePriority.POSITIVE_CUE]
            assert len(positive) == 1
            assert positive[0].cue_key in ("good_rep", "strong")
        asyncio.run(_run())

    def test_on_rep_complete_faulted_no_positive(self, orchestrator):
        orchestrator._positive_cue_keys = ["good_rep"]

        async def _run():
            await orchestrator.on_rep_complete(1, "parallel", False, ["knee_valgus"])
            events = []
            while not orchestrator._queue.empty():
                events.append(orchestrator._queue.get_nowait())
            positive = [e for e in events if e.priority == CuePriority.POSITIVE_CUE]
            assert len(positive) == 0
        asyncio.run(_run())

    def test_on_rep_complete_tracks_clean_streak(self, orchestrator):
        async def _run():
            await orchestrator.on_rep_complete(1, "parallel", True, [])
            assert orchestrator._clean_streak == 1
            await orchestrator.on_rep_complete(2, "parallel", True, [])
            assert orchestrator._clean_streak == 2
            await orchestrator.on_rep_complete(3, "parallel", False, ["knee_valgus"])
            assert orchestrator._clean_streak == 0
        asyncio.run(_run())

    def test_on_set_complete_enqueues(self, orchestrator):
        async def _run():
            set_data = {"set_number": 1, "total_reps": 5, "clean_reps": 3}
            await orchestrator.on_set_complete(set_data)
            event = orchestrator._queue.get_nowait()
            assert event.priority == CuePriority.LLM_SET_RECAP
            assert event.data["total_reps"] == 5
        asyncio.run(_run())


# =============================================================================
# TEST DISPATCH
# =============================================================================


class TestDispatch:
    """Test event dispatch behavior."""

    def test_cached_cue_ducks_and_unducks(self, mock_callbacks):
        orch = CoachingOrchestrator(**mock_callbacks)

        async def _run():
            event = CoachingEvent(
                CuePriority.FAULT_CUE, time.monotonic(), "cached_cue", "knees_out"
            )
            await orch._dispatch(event)
            mock_callbacks["duck_llm_fn"].assert_awaited_once()
            mock_callbacks["play_cached_audio_fn"].assert_awaited_once_with("knees_out")
            mock_callbacks["unduck_llm_fn"].assert_awaited_once()
        asyncio.run(_run())

    def test_stale_motivation_dropped(self, mock_callbacks):
        orch = CoachingOrchestrator(**mock_callbacks)

        async def _run():
            event = CoachingEvent(
                CuePriority.LLM_MOTIVATION,
                time.monotonic() - 10.0,
                "llm_motivation",
                data={"rep_number": 3, "reps_remaining": 5},
            )
            await orch._dispatch(event)
            mock_callbacks["generate_llm_reply_fn"].assert_not_awaited()
        asyncio.run(_run())

    def test_set_recap_calls_llm(self, mock_callbacks):
        orch = CoachingOrchestrator(**mock_callbacks)

        async def _run():
            event = CoachingEvent(
                CuePriority.LLM_SET_RECAP,
                time.monotonic(),
                "llm_set_recap",
                data={
                    "set_number": 1, "total_reps": 5, "clean_reps": 4,
                    "avg_depth": 95.0, "depth_consistency": 3.5, "fault_summary": {},
                },
            )
            await orch._dispatch(event)
            mock_callbacks["generate_llm_reply_fn"].assert_awaited_once()
            call_args = mock_callbacks["generate_llm_reply_fn"].call_args[0][0]
            assert "[SET RECAP DATA]" in call_args
            assert "5 reps" in call_args
        asyncio.run(_run())

    def test_motivation_calls_llm(self, mock_callbacks):
        orch = CoachingOrchestrator(**mock_callbacks)

        async def _run():
            event = CoachingEvent(
                CuePriority.LLM_MOTIVATION,
                time.monotonic(),
                "llm_motivation",
                data={"rep_number": 3, "reps_remaining": 5, "clean_streak": 2, "recent_faults": []},
            )
            await orch._dispatch(event)
            mock_callbacks["generate_llm_reply_fn"].assert_awaited_once()
            call_args = mock_callbacks["generate_llm_reply_fn"].call_args[0][0]
            assert "[COACHING CONTEXT]" in call_args
        asyncio.run(_run())


# =============================================================================
# TEST RESET
# =============================================================================


class TestReset:
    """Test reset_set clears per-set state."""

    def test_reset_clears_state(self, orchestrator):
        orchestrator._set_rep_count = 5
        orchestrator._clean_streak = 3
        orchestrator._recent_faults = ["knee_valgus"]
        orchestrator._last_motivation_rep = 3
        orchestrator._last_fault_cue_time = 99.0
        orchestrator.reset_set(target_reps=8, positive_cue_keys=["strong"])
        assert orchestrator._set_rep_count == 0
        assert orchestrator._clean_streak == 0
        assert orchestrator._recent_faults == []
        assert orchestrator._last_motivation_rep == 0
        assert orchestrator._set_target_reps == 8
        assert orchestrator._positive_cue_keys == ["strong"]
        assert orchestrator._last_fault_cue_time == 0.0
        assert orchestrator._set_clean_count == 0


# =============================================================================
# TEST SET COMPLETION (rep-count boundary)
# =============================================================================


class TestSetCompletion:
    """Test rep-count-based set boundary detection."""

    def test_set_complete_at_target_reps(self):
        """on_rep_complete should trigger on_set_complete when reps hit target."""
        cbs = _make_callbacks()
        advance_fn = AsyncMock(return_value=5)
        orch = CoachingOrchestrator(**cbs, advance_set_fn=advance_fn)
        orch.reset_set(target_reps=3)

        async def _run():
            await orch.on_rep_complete(1, "parallel", True, [])
            await orch.on_rep_complete(2, "parallel", True, [])
            await orch.on_rep_complete(3, "parallel", True, [])

            events = []
            while not orch._queue.empty():
                events.append(orch._queue.get_nowait())
            recap_events = [e for e in events if e.event_type == "llm_set_recap"]
            assert len(recap_events) == 1
            assert recap_events[0].data["trigger"] == "rep_count"
            assert recap_events[0].data["total_reps"] == 3
            assert recap_events[0].data["clean_reps"] == 3

            advance_fn.assert_awaited_once()
            # State should be reset for next set
            assert orch._set_rep_count == 0
            assert orch._set_target_reps == 5

        asyncio.run(_run())

    def test_no_set_complete_before_target(self):
        """on_rep_complete should NOT trigger set_complete before target."""
        cbs = _make_callbacks()
        advance_fn = AsyncMock(return_value=3)
        orch = CoachingOrchestrator(**cbs, advance_set_fn=advance_fn)
        orch.reset_set(target_reps=5)

        async def _run():
            await orch.on_rep_complete(1, "parallel", True, [])
            await orch.on_rep_complete(2, "parallel", True, [])

            events = []
            while not orch._queue.empty():
                events.append(orch._queue.get_nowait())
            recap_events = [e for e in events if e.event_type == "llm_set_recap"]
            assert len(recap_events) == 0
            advance_fn.assert_not_awaited()

        asyncio.run(_run())

    def test_no_set_complete_without_target(self):
        """No target_reps set -> never trigger set_complete from rep count."""
        cbs = _make_callbacks()
        advance_fn = AsyncMock()
        orch = CoachingOrchestrator(**cbs, advance_set_fn=advance_fn)

        async def _run():
            for i in range(1, 11):
                await orch.on_rep_complete(i, "parallel", True, [])
            advance_fn.assert_not_awaited()

        asyncio.run(_run())

    def test_set_complete_without_advance_fn(self):
        """Set complete should still trigger recap even without advance_set_fn."""
        cbs = _make_callbacks()
        orch = CoachingOrchestrator(**cbs)
        orch.reset_set(target_reps=2)

        async def _run():
            await orch.on_rep_complete(1, "parallel", True, [])
            await orch.on_rep_complete(2, "parallel", True, [])

            events = []
            while not orch._queue.empty():
                events.append(orch._queue.get_nowait())
            recap_events = [e for e in events if e.event_type == "llm_set_recap"]
            assert len(recap_events) == 1

        asyncio.run(_run())

    def test_clean_count_tracks_correctly(self):
        """_set_clean_count should track total clean reps, not just streak."""
        cbs = _make_callbacks()
        orch = CoachingOrchestrator(**cbs)
        orch.reset_set(target_reps=5)

        async def _run():
            await orch.on_rep_complete(1, "parallel", True, [])   # clean
            await orch.on_rep_complete(2, "parallel", False, [])  # not clean
            await orch.on_rep_complete(3, "parallel", True, [])   # clean
            assert orch._set_clean_count == 2
            assert orch._clean_streak == 1

        asyncio.run(_run())


# =============================================================================
# TEST FULL FLOW (integration-style)
# =============================================================================


class TestFullFlow:
    """Integration-style tests with the processor loop running."""

    def test_fault_plays_before_motivation(self):
        cbs = _make_callbacks()
        orch = CoachingOrchestrator(**cbs)

        async def _run():
            orch.start()
            try:
                # Enqueue motivation first, then fault
                await orch._queue.put(CoachingEvent(
                    CuePriority.LLM_MOTIVATION, time.monotonic(), "llm_motivation",
                    data={"rep_number": 3, "reps_remaining": 5, "clean_streak": 0, "recent_faults": []},
                ))
                await orch._queue.put(CoachingEvent(
                    CuePriority.FAULT_CUE, time.monotonic(), "cached_cue", "knees_out",
                ))
                await asyncio.sleep(0.3)
                cbs["play_cached_audio_fn"].assert_awaited_once_with("knees_out")
            finally:
                orch.stop()
        asyncio.run(_run())

    def test_rep_complete_full_flow(self):
        cbs = _make_callbacks()
        orch = CoachingOrchestrator(**cbs)
        orch._positive_cue_keys = ["strong"]

        async def _run():
            orch.start()
            try:
                await orch.on_rep_complete(1, "parallel", True, [])
                await asyncio.sleep(0.3)
                calls = cbs["play_cached_audio_fn"].call_args_list
                cue_keys = [c[0][0] for c in calls]
                assert "rep_1" in cue_keys
                # No LLM motivation on rep 1
                cbs["generate_llm_reply_fn"].assert_not_awaited()
            finally:
                orch.stop()
        asyncio.run(_run())


# =============================================================================
# TEST REST MODE
# =============================================================================


class TestRestMode:
    """Test that resting flag suppresses rep/fault processing."""

    def test_resting_blocks_on_fault(self, orchestrator):
        """Faults are ignored while resting."""
        orchestrator._resting = True

        async def _run():
            await orchestrator.on_fault("knees_out", "knee_valgus", "moderate")
            assert orchestrator._queue.empty()

        asyncio.run(_run())

    def test_resting_blocks_on_rep_complete(self, orchestrator):
        """Reps are ignored while resting."""
        orchestrator._resting = True

        async def _run():
            await orchestrator.on_rep_complete(1, "parallel", True, [])
            assert orchestrator._queue.empty()
            assert orchestrator._set_rep_count == 0  # Not incremented

        asyncio.run(_run())

    def test_on_rest_complete_clears_flag(self, orchestrator):
        """on_rest_complete() resumes normal processing."""
        orchestrator._resting = True
        orchestrator.on_rest_complete()
        assert orchestrator._resting is False

    def test_rest_set_after_advance(self):
        """After set completion with advance, orchestrator enters rest mode."""
        cbs = _make_callbacks()
        advance_mock = AsyncMock(return_value=5)
        orch = CoachingOrchestrator(**cbs, advance_set_fn=advance_mock)
        orch.reset_set(target_reps=3)

        async def _run():
            orch.start()
            try:
                for i in range(1, 4):
                    await orch.on_rep_complete(i, "parallel", True, [])
                await asyncio.sleep(0.3)
                assert orch._resting is True
                advance_mock.assert_awaited_once()
            finally:
                orch.stop()

        asyncio.run(_run())

    def test_reset_set_clears_resting(self, orchestrator):
        """reset_set() clears resting as safety."""
        orchestrator._resting = True
        orchestrator.reset_set(target_reps=5)
        assert orchestrator._resting is False


# =============================================================================
# TEST RELATIVE REP COUNTING
# =============================================================================


class TestRelativeRepCounting:
    """Test that orchestrator tracks per-set relative reps, not absolute pipeline numbers."""

    def test_rep_count_increments_by_one(self):
        """_set_rep_count should increment by 1 regardless of absolute rep_number."""
        cbs = _make_callbacks()
        orch = CoachingOrchestrator(**cbs)
        orch.reset_set(target_reps=10)

        async def _run():
            # Pipeline sends absolute rep numbers 5, 6, 7
            await orch.on_rep_complete(5, "parallel", True, [])
            assert orch._set_rep_count == 1
            await orch.on_rep_complete(6, "parallel", True, [])
            assert orch._set_rep_count == 2
            await orch.on_rep_complete(7, "parallel", True, [])
            assert orch._set_rep_count == 3

        asyncio.run(_run())

    def test_no_immediate_set_complete_after_reset(self):
        """After reset, high absolute rep numbers should NOT trigger immediate set completion."""
        cbs = _make_callbacks()
        advance_fn = AsyncMock(return_value=5)
        orch = CoachingOrchestrator(**cbs, advance_set_fn=advance_fn)
        orch.reset_set(target_reps=5)

        async def _run():
            # Simulate set 2: pipeline sends absolute rep 6 (first rep of new set)
            await orch.on_rep_complete(6, "parallel", True, [])
            # Should be counted as relative rep 1, NOT trigger set complete
            assert orch._set_rep_count == 1
            advance_fn.assert_not_awaited()

        asyncio.run(_run())

    def test_rep_cue_uses_relative_number(self):
        """Rep cue key should use per-set number, not absolute pipeline number."""
        cbs = _make_callbacks()
        orch = CoachingOrchestrator(**cbs)
        orch.reset_set(target_reps=10)

        async def _run():
            # Pipeline sends absolute rep 8, but it's the 1st rep of this set
            await orch.on_rep_complete(8, "parallel", True, [])
            event = orch._queue.get_nowait()
            assert event.cue_key == "rep_1"  # Not "rep_8"

        asyncio.run(_run())

    def test_set_number_increments_across_sets(self):
        """_set_number should increment with each completed set."""
        cbs = _make_callbacks()
        advance_fn = AsyncMock(return_value=3)
        orch = CoachingOrchestrator(**cbs, advance_set_fn=advance_fn)
        orch.reset_set(target_reps=3)

        async def _run():
            # Complete set 1
            for i in range(1, 4):
                await orch.on_rep_complete(i, "parallel", True, [])

            # Check set_number in recap event
            events = []
            while not orch._queue.empty():
                events.append(orch._queue.get_nowait())
            recap = [e for e in events if e.event_type == "llm_set_recap"]
            assert len(recap) == 1
            assert recap[0].data["set_number"] == 1

            # Clear rest mode before set 2
            orch.on_rest_complete()

            # Now complete set 2 (absolute reps 4, 5, 6)
            for i in range(4, 7):
                await orch.on_rep_complete(i, "parallel", True, [])

            events = []
            while not orch._queue.empty():
                events.append(orch._queue.get_nowait())
            recap = [e for e in events if e.event_type == "llm_set_recap"]
            assert len(recap) == 1
            assert recap[0].data["set_number"] == 2

        asyncio.run(_run())

    def test_motivation_uses_relative_rep(self):
        """Motivation should fire based on per-set rep count, not absolute."""
        cbs = _make_callbacks()
        orch = CoachingOrchestrator(**cbs)
        orch.reset_set(target_reps=10)

        async def _run():
            # Simulate reps 6, 7, 8 from pipeline (relative reps 1, 2, 3)
            await orch.on_rep_complete(6, "parallel", False, [])  # relative 1
            await orch.on_rep_complete(7, "parallel", False, [])  # relative 2
            await orch.on_rep_complete(8, "parallel", False, [])  # relative 3

            events = []
            while not orch._queue.empty():
                events.append(orch._queue.get_nowait())
            motivation = [e for e in events if e.event_type == "llm_motivation"]
            # Motivation fires at relative rep 3 (3 % 3 == 0)
            assert len(motivation) == 1

        asyncio.run(_run())
