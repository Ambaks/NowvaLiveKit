"""Tests for the rep validation sound.

The beep is the lifter's only confirmation that a rep counted, so it must
fire on every counted rep, on its own audio track, without waiting behind
whatever the coach happens to be saying.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.services.audio_cue_service import REP_SOUND_PATH
from agent.services.coaching_orchestrator import CoachingOrchestrator


def _orchestrator(has_audio=lambda key: True):
    played: list[str] = []

    async def _play(cue_key):
        played.append(cue_key)

    orch = CoachingOrchestrator(
        play_cached_audio_fn=_play,
        generate_llm_reply_fn=AsyncMock(),
        get_cue_audio_fn=has_audio,
    )
    return orch, played


async def _complete_reps(orch, count, faults=None):
    for _ in range(count):
        await orch.on_rep_complete(
            rep_number=0, depth="parallel", is_clean=True, faults=faults or [],
        )
    await asyncio.sleep(0)


class TestRepSoundAsset:
    def test_validation_sound_ships_with_the_repo(self):
        assert REP_SOUND_PATH.exists(), f"missing rep sound at {REP_SOUND_PATH}"


class TestRepSoundAlwaysFires:
    def test_every_counted_rep_beeps(self):
        async def _run():
            orch, played = _orchestrator()
            orch.reset_set(target_reps=None)
            await _complete_reps(orch, 5)
            assert played == [f"rep_{i}" for i in range(1, 6)]

        asyncio.run(_run())

    def test_the_last_rep_of_a_set_still_beeps(self):
        """The set-completion branch returns early — the beep must precede it."""

        async def _run():
            orch, played = _orchestrator()
            orch.reset_set(target_reps=3)
            await _complete_reps(orch, 3)
            assert "rep_3" in played

        asyncio.run(_run())

    def test_a_faulty_rep_still_beeps(self):
        async def _run():
            orch, played = _orchestrator()
            orch.reset_set(target_reps=None)
            await orch.on_rep_complete(
                rep_number=1, depth="parallel", is_clean=False,
                faults=["forward_lean", "knee_valgus"],
            )
            await asyncio.sleep(0)
            assert played == ["rep_1"]

        asyncio.run(_run())

    def test_beeps_past_the_twentieth_rep(self):
        """There are no per-rep WAVs on disk — the beep is one shared sound,
        so a high rep count must not fall off the end of a variant list."""

        async def _run():
            orch, played = _orchestrator()
            orch.reset_set(target_reps=None)
            await _complete_reps(orch, 23)
            assert played[-1] == "rep_23"
            assert len(played) == 23

        asyncio.run(_run())

    def test_beep_is_not_awaited_inline(self):
        """on_rep_complete must return before the sound finishes playing."""

        async def _run():
            blocked = asyncio.Event()
            started = asyncio.Event()

            async def _slow_play(cue_key):
                started.set()
                await blocked.wait()

            orch = CoachingOrchestrator(
                play_cached_audio_fn=_slow_play,
                generate_llm_reply_fn=AsyncMock(),
                get_cue_audio_fn=lambda key: True,
            )
            orch.reset_set(target_reps=None)

            await orch.on_rep_complete(
                rep_number=1, depth="parallel", is_clean=True, faults=[],
            )
            # Returned without the sound having completed.
            await asyncio.sleep(0)
            assert started.is_set()
            blocked.set()
            await asyncio.sleep(0)

        asyncio.run(_run())

    def test_no_beep_while_resting(self):
        """Reps during rest are not counted, so they must not beep either."""

        async def _run():
            orch, played = _orchestrator()
            orch.reset_set(target_reps=None)
            orch.resting = True
            await _complete_reps(orch, 3)
            assert played == []

        asyncio.run(_run())


class TestRepTrackSetup:
    def test_ensure_rep_track_is_safe_without_a_room(self):
        from agent.services.coaching_service import CoachingService

        service = CoachingService.__new__(CoachingService)
        service._audio_cue_service = None
        service._room = None
        assert asyncio.run(service.ensure_rep_track()) is False

    def test_ensure_rep_track_publishes_once(self):
        from agent.services.coaching_service import CoachingService

        calls: list = []

        class _Cues:
            rep_track_ready = False

            async def setup_rep_track(self, room):
                calls.append(room)
                type(self).rep_track_ready = True

        service = CoachingService.__new__(CoachingService)
        service._audio_cue_service = _Cues()
        service._room = object()

        assert asyncio.run(service.ensure_rep_track()) is True
        assert asyncio.run(service.ensure_rep_track()) is True
        assert len(calls) == 1, "track should only be published once"


class TestRepSoundFormat:
    """The beep is a real recording, not TTS output, so it does not
    necessarily match the 24kHz mono the spoken cues use. Frames described
    with the wrong format play as noise, at the wrong speed, or not at all —
    and nothing in the logs says so."""

    def _wav_format(self):
        import wave

        with wave.open(str(REP_SOUND_PATH), "rb") as wf:
            return wf.getframerate(), wf.getnchannels(), wf.getnframes()

    def _service(self):
        from agent.services.audio_cue_service import AudioCueService

        return AudioCueService(session=None)

    def test_frames_declare_the_files_real_format(self):
        rate, channels, _ = self._wav_format()
        frames = self._service()._rep_sound_frames
        assert frames, "rep sound failed to load"
        assert frames[0].sample_rate == rate
        assert frames[0].num_channels == channels

    def test_declared_duration_matches_the_file(self):
        rate, _, n_frames = self._wav_format()
        frames = self._service()._rep_sound_frames
        declared = sum(f.samples_per_channel for f in frames) / frames[0].sample_rate
        assert declared == pytest.approx(n_frames / rate, abs=0.01)

    def test_audio_source_would_match_the_frames(self):
        """A source built for a different rate/layout rejects the frames."""
        service = self._service()
        assert service._rep_sample_rate == service._rep_sound_frames[0].sample_rate
        assert service._rep_channels == service._rep_sound_frames[0].num_channels
