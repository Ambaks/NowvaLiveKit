"""Tests for CompactionService session folder creation and final flush on stop."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.services.compaction_service import CompactionService


class _FakeSession:
    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}

    def on(self, event_name: str, handler) -> None:
        self.handlers[event_name] = handler

    def off(self, event_name: str, handler) -> None:
        self.handlers.pop(event_name, None)


class _FakeState:
    def get_mode(self) -> str:
        return "main_menu"


class _FakeOpenAIClient:
    """Returns a fixed compression result and records calls."""

    def __init__(self, response_text: str = "COMPRESSED_SUMMARY") -> None:
        self.calls: list[dict] = []
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=response_text))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )

        async def _create(**kwargs):
            self.calls.append(kwargs)
            return response

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=_create))


def _make_service(tmp_path: Path, monkeypatch) -> tuple[CompactionService, _FakeOpenAIClient]:
    monkeypatch.setenv("NOWVA_SESSION_OUTPUT_DIR", str(tmp_path))
    client = _FakeOpenAIClient()
    service = CompactionService(
        session=_FakeSession(),
        state=_FakeState(),
        user_id="test_user",
        openai_client=client,
    )
    return service, client


def _conversation_event(role: str, text: str):
    return SimpleNamespace(item=SimpleNamespace(role=role, text_content=text))


class TestSessionFolder:
    def test_creates_compaction_dir_in_session_output(self, tmp_path, monkeypatch):
        service, _ = _make_service(tmp_path, monkeypatch)

        async def _run():
            await service.start()
            await service.stop()

        asyncio.run(_run())

        compaction_dir = tmp_path / "compaction"
        assert compaction_dir.is_dir()
        assert (compaction_dir / "memory.md").exists()
        assert (compaction_dir / "session_meta.json").exists()

    def test_final_metadata_written_on_stop(self, tmp_path, monkeypatch):
        service, _ = _make_service(tmp_path, monkeypatch)

        async def _run():
            await service.start()
            await service.stop()

        asyncio.run(_run())

        meta = json.loads((tmp_path / "compaction" / "session_meta.json").read_text())
        assert meta["user_id"] == "test_user"
        assert "session_end" in meta


class TestFinalFlush:
    def test_stop_flushes_buffered_events_to_memory(self, tmp_path, monkeypatch):
        service, client = _make_service(tmp_path, monkeypatch)

        async def _run():
            await service.start()
            handler = service._session.handlers["conversation_item_added"]
            handler(_conversation_event("user", "I squatted 100 kg for 5 reps"))
            handler(_conversation_event("assistant", "Great depth on that set"))
            await service.stop()

        asyncio.run(_run())

        memory = (tmp_path / "compaction" / "memory.md").read_text()
        assert "Session end flush" in memory
        assert "COMPRESSED_SUMMARY" in memory
        assert len(client.calls) == 1

    def test_stop_flushes_raw_when_llm_fails(self, tmp_path, monkeypatch):
        service, client = _make_service(tmp_path, monkeypatch)

        async def _failing_create(**kwargs):
            raise RuntimeError("API down")

        client.chat.completions.create = _failing_create

        async def _run():
            await service.start()
            handler = service._session.handlers["conversation_item_added"]
            handler(_conversation_event("user", "my knee hurts on rep three"))
            await service.stop()

        asyncio.run(_run())

        memory = (tmp_path / "compaction" / "memory.md").read_text()
        assert "Session end flush" in memory
        assert "my knee hurts on rep three" in memory

    def test_stop_without_events_writes_no_flush_section(self, tmp_path, monkeypatch):
        service, _ = _make_service(tmp_path, monkeypatch)

        async def _run():
            await service.start()
            await service.stop()

        asyncio.run(_run())

        memory = (tmp_path / "compaction" / "memory.md").read_text()
        assert "Session end flush" not in memory
