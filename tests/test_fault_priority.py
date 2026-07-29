"""Tests for fault cue priority.

Forward lean is the root-cause fault that drives the intra-set stance
correction, but it fires least often. With a flat rate limit the more
frequent knee and asymmetry faults claimed every cue slot and forward
lean was never heard — in one recorded session it fired 5 times and was
cued 0 times.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.services.coaching_orchestrator import CoachingOrchestrator, CuePriority
from biomechanics.coaching.cue_cache import (
    CueCache,
    can_cue_fault,
    fault_cue_priority,
)


def _orchestrator() -> CoachingOrchestrator:
    return CoachingOrchestrator(
        play_cached_audio_fn=AsyncMock(),
        generate_llm_reply_fn=AsyncMock(),
        get_cue_audio_fn=lambda key: bool(key),
    )


def _drain(orch) -> list[str]:
    out = []
    while not orch._queue.empty():
        out.append(orch._queue.get_nowait().cue_key)
    return out


class TestPriorityOrder:
    def test_forward_lean_outranks_knee_valgus_and_asymmetry(self):
        assert (
            fault_cue_priority("forward_lean")
            < fault_cue_priority("knee_valgus")
            < fault_cue_priority("bilateral_asymmetry")
        )

    def test_unlisted_faults_rank_last(self):
        assert fault_cue_priority("depth") > fault_cue_priority("bilateral_asymmetry")


class TestCueCachePreemption:
    def _cache(self) -> CueCache:
        cache = CueCache()
        cache.prepare_for_exercise("squat")
        return cache

    def test_forward_lean_preempts_same_frame(self):
        """The recorded failure: bilateral_asymmetry and forward_lean fire
        on the same detection frame. Forward lean (priority 0) must win."""
        cache = self._cache()
        assert cache.get_cue_for_fault("bilateral_asymmetry", 100.0) == "even_it_out"
        assert cache.get_cue_for_fault("forward_lean", 100.0) == "chest_up"

    def test_lower_priority_cannot_preempt_forward_lean(self):
        cache = self._cache()
        assert cache.get_cue_for_fault("forward_lean", 100.0) == "chest_up"
        assert cache.get_cue_for_fault("knee_valgus", 100.0) is None

    def test_same_fault_still_respects_the_gap(self):
        cache = self._cache()
        assert cache.get_cue_for_fault("forward_lean", 100.0) == "chest_up"
        assert cache.get_cue_for_fault("forward_lean", 100.0 + 0.5) is None

    def test_equal_priority_cannot_preempt(self):
        """Two faults at the same priority within the gap — second is blocked."""
        cache = self._cache()
        assert cache.get_cue_for_fault("knee_valgus", 100.0) == "knees_out"
        assert cache.get_cue_for_fault("knee_valgus", 100.0 + 0.5) is None

    def test_everything_flows_again_once_the_gap_expires(self):
        cache = self._cache()
        assert cache.get_cue_for_fault("forward_lean", 100.0) == "chest_up"
        later = 100.0 + cache.min_cue_gap + 0.1
        assert cache.get_cue_for_fault("bilateral_asymmetry", later) == "even_it_out"


class TestOrchestratorPreemption:
    def test_forward_lean_jumps_the_fault_gap(self):
        """The recorded failure: chest_up arrived 4.7s after knees_out and
        was dropped by the flat 8s gap."""

        async def _run():
            orch = _orchestrator()
            await orch.on_fault("knees_out", "knee_valgus", "mild")
            orch._last_fault_cue_time -= 4.7  # pretend 4.7s elapsed
            await orch.on_fault("chest_up", "forward_lean", "moderate")
            assert "chest_up" in _drain(orch)

        asyncio.run(_run())

    def test_asymmetry_does_not_jump_the_gap_behind_forward_lean(self):
        async def _run():
            orch = _orchestrator()
            await orch.on_fault("chest_up", "forward_lean", "moderate")
            orch._last_fault_cue_time -= 4.7
            await orch.on_fault("even_it_out", "bilateral_asymmetry", "mild")
            assert _drain(orch) == ["chest_up"]

        asyncio.run(_run())

    def test_forward_lean_preempts_half_second_after_asymmetry(self):
        """The recorded failure: bilateral_asymmetry played, then a SEVERE
        forward_lean arrived 0.5s later and was silently dropped."""

        async def _run():
            orch = _orchestrator()
            await orch.on_fault("even_it_out", "bilateral_asymmetry", "mild")
            orch._last_fault_cue_time -= 0.5  # pretend 0.5s elapsed
            await orch.on_fault("chest_up", "forward_lean", "severe")
            cues = _drain(orch)
            assert "chest_up" in cues

        asyncio.run(_run())

    def test_queued_faults_dispatch_most_important_first(self):
        async def _run():
            orch = _orchestrator()
            # All three enqueue because each has strictly higher priority.
            await orch.on_fault("even_it_out", "bilateral_asymmetry", "mild")
            await orch.on_fault("knees_out", "knee_valgus", "mild")
            await orch.on_fault("chest_up", "forward_lean", "mild")
            assert _drain(orch) == ["chest_up", "knees_out", "even_it_out"]

        asyncio.run(_run())

    def test_priority_resets_between_sets(self):
        async def _run():
            orch = _orchestrator()
            await orch.on_fault("chest_up", "forward_lean", "moderate")
            orch.reset_set(target_reps=5)
            # A new set must not be blocked by the previous set's top cue.
            await orch.on_fault("even_it_out", "bilateral_asymmetry", "mild")
            assert "even_it_out" in _drain(orch)

        asyncio.run(_run())
