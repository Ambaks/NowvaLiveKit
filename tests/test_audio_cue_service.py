"""Tests for AudioCueService — TTS pre-caching for coaching cues."""

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from services.audio_cue_service import (
    CACHE_TTL_SECONDS,
    CUE_TEXT_MAP,
    AudioCueService,
)

# Sample cue dict as sent by biomechanics IPC bridge
SAMPLE_SQUAT_CUES = {
    "knees_out": "knees_out",
    "chest_up": "chest_up",
    "deeper": "deeper",
    "heels_down": "heels_down",
    "good_rep": "good_rep",
    "rep_1": "rep_1",
    "rep_2": "rep_2",
    "rep_3": "rep_3",
}

FAKE_PCM = b"\x00\x01" * 1200  # 2400 bytes of fake 16-bit PCM


def _make_speech_response(audio_bytes: bytes = FAKE_PCM):
    """Create a mock response for client.audio.speech.create()."""
    resp = MagicMock()
    resp.read.return_value = audio_bytes
    return resp


@pytest.fixture
def service():
    return AudioCueService()


# ------------------------------------------------------------------
# cache_cues
# ------------------------------------------------------------------

def test_cache_cues_generates_all_known_keys(service):
    """cache_cues should generate TTS for every key present in CUE_TEXT_MAP."""
    async def _run():
        mock_client = AsyncMock()
        mock_client.audio.speech.create = AsyncMock(return_value=_make_speech_response())
        service._client = mock_client

        await service.cache_cues(SAMPLE_SQUAT_CUES)

        assert len(service.cache) == len(SAMPLE_SQUAT_CUES)
        for key in SAMPLE_SQUAT_CUES:
            assert key in service.cache
            assert isinstance(service.cache[key], bytes)
            assert len(service.cache[key]) > 0

    asyncio.run(_run())


def test_cache_cues_skips_unknown_keys(service):
    """Keys not in CUE_TEXT_MAP should be silently skipped."""
    async def _run():
        mock_client = AsyncMock()
        mock_client.audio.speech.create = AsyncMock(return_value=_make_speech_response())
        service._client = mock_client

        cues = {"knees_out": "knees_out", "unknown_cue": "unknown_cue"}
        await service.cache_cues(cues)

        assert "knees_out" in service.cache
        assert "unknown_cue" not in service.cache

    asyncio.run(_run())


def test_cache_cues_concurrent_generation(service):
    """All cues should be generated concurrently (not sequentially)."""
    async def _run():
        call_times = []

        async def fake_create(**kwargs):
            call_times.append(time.monotonic())
            await asyncio.sleep(0.05)  # simulate 50ms API call
            return _make_speech_response()

        mock_client = AsyncMock()
        mock_client.audio.speech.create = fake_create
        service._client = mock_client

        start = time.monotonic()
        await service.cache_cues(SAMPLE_SQUAT_CUES)
        elapsed = time.monotonic() - start

        # If sequential, would take 8 * 0.05 = 0.4s. Concurrent should be ~0.05s.
        assert elapsed < 0.3, f"Cue generation took {elapsed:.2f}s — likely not concurrent"

    asyncio.run(_run())


def test_cache_cues_handles_partial_failure(service):
    """If some TTS calls fail, the rest should still be cached."""
    async def _run():
        call_count = 0

        async def flaky_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 3 == 0:
                raise RuntimeError("Simulated TTS API error")
            return _make_speech_response()

        mock_client = AsyncMock()
        mock_client.audio.speech.create = flaky_create
        service._client = mock_client

        await service.cache_cues(SAMPLE_SQUAT_CUES)

        # Some should succeed even though some failed
        assert len(service.cache) > 0
        assert len(service.cache) < len(SAMPLE_SQUAT_CUES)

    asyncio.run(_run())


def test_cache_cues_sets_expiry(service):
    """Cache expiry should be set to ~30 minutes from now."""
    async def _run():
        mock_client = AsyncMock()
        mock_client.audio.speech.create = AsyncMock(return_value=_make_speech_response())
        service._client = mock_client

        before = time.monotonic()
        await service.cache_cues(SAMPLE_SQUAT_CUES)
        after = time.monotonic()

        assert service.cache_expiry >= before + CACHE_TTL_SECONDS
        assert service.cache_expiry <= after + CACHE_TTL_SECONDS

    asyncio.run(_run())


# ------------------------------------------------------------------
# get_cue_audio
# ------------------------------------------------------------------

def test_get_cue_audio_returns_bytes_for_cached_key(service):
    """get_cue_audio should return cached bytes for a known key."""
    service.cache = {"knees_out": FAKE_PCM}
    service.cache_expiry = time.monotonic() + 600

    result = service.get_cue_audio("knees_out")
    assert result == FAKE_PCM


def test_get_cue_audio_returns_none_for_missing_key(service):
    """get_cue_audio should return None for keys not in cache."""
    service.cache = {"knees_out": FAKE_PCM}
    service.cache_expiry = time.monotonic() + 600

    assert service.get_cue_audio("nonexistent") is None


def test_get_cue_audio_returns_none_when_expired(service):
    """get_cue_audio should return None if TTL has expired."""
    service.cache = {"knees_out": FAKE_PCM}
    service.cache_expiry = time.monotonic() - 1  # expired

    assert service.get_cue_audio("knees_out") is None


def test_get_cue_audio_returns_none_when_empty(service):
    """get_cue_audio should return None if cache is empty."""
    assert service.get_cue_audio("knees_out") is None


def test_get_cue_audio_retrieval_under_10ms(service):
    """Cache retrieval should be a fast dict lookup (<10ms)."""
    service.cache = {f"rep_{i}": FAKE_PCM for i in range(1, 21)}
    service.cache_expiry = time.monotonic() + 600

    start = time.monotonic()
    for i in range(1, 21):
        service.get_cue_audio(f"rep_{i}")
    elapsed_ms = (time.monotonic() - start) * 1000

    assert elapsed_ms < 10, f"20 cache lookups took {elapsed_ms:.2f}ms"


# ------------------------------------------------------------------
# is_cache_valid
# ------------------------------------------------------------------

def test_is_cache_valid_true_when_populated_and_fresh(service):
    service.cache = {"knees_out": FAKE_PCM}
    service.cache_expiry = time.monotonic() + 600
    assert service.is_cache_valid() is True


def test_is_cache_valid_false_when_empty(service):
    service.cache_expiry = time.monotonic() + 600
    assert service.is_cache_valid() is False


def test_is_cache_valid_false_when_expired(service):
    service.cache = {"knees_out": FAKE_PCM}
    service.cache_expiry = time.monotonic() - 1
    assert service.is_cache_valid() is False


# ------------------------------------------------------------------
# get_cue_text (static, used by Option C fallback)
# ------------------------------------------------------------------

def test_get_cue_text_returns_text_for_known_key():
    assert AudioCueService.get_cue_text("knees_out") == "Knees out!"
    assert AudioCueService.get_cue_text("rep_5") == "Five!"
    assert AudioCueService.get_cue_text("good_rep") == "Good rep!"


def test_get_cue_text_returns_none_for_unknown_key():
    assert AudioCueService.get_cue_text("nonexistent") is None


# ------------------------------------------------------------------
# CUE_TEXT_MAP coverage
# ------------------------------------------------------------------

def test_cue_text_map_covers_all_rep_counts():
    """CUE_TEXT_MAP should have entries for rep_1 through rep_20."""
    for i in range(1, 21):
        assert f"rep_{i}" in CUE_TEXT_MAP


def test_cue_text_map_covers_squat_corrections():
    """CUE_TEXT_MAP should cover all squat correction cue keys."""
    squat_keys = ["knees_out", "chest_up", "deeper", "heels_down",
                  "even_it_out", "slow_down", "brace"]
    for key in squat_keys:
        assert key in CUE_TEXT_MAP


def test_cue_text_map_covers_positive_cues():
    """CUE_TEXT_MAP should cover all positive reinforcement cue keys."""
    positive_keys = ["good_rep", "great_depth", "strong", "clean", "perfect"]
    for key in positive_keys:
        assert key in CUE_TEXT_MAP
