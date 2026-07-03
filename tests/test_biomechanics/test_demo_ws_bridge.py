"""Tests for the demo WebSocket bridge's event backlog replay."""

from __future__ import annotations

import asyncio
import json

import numpy as np

from biomechanics.diagnosis.demo_builder import DemoCue, DemoData
from biomechanics.viz.demo_ws_bridge import DemoWSBridge


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, payload: str) -> None:
        self.sent.append(payload)

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


def _make_demo_data() -> DemoData:
    cue = DemoCue(
        cue_index=0,
        cause_id="narrow_stance",
        explanation="widen your stance",
        magnitude_text="about 3 centimeters wider on each side",
    )
    return DemoData(pose_stack=np.zeros((2, 19, 3)), cues=[cue])


class TestEventBacklogReplay:

    def test_late_client_receives_init_and_backlog_in_order(self):
        """A browser that connects after events were sent must still get them."""
        bridge = DemoWSBridge()
        bridge.send_init(_make_demo_data())
        bridge.send_event({"type": "demo_start"})
        bridge.send_event({"type": "demo_cue", "cue_index": 0})

        fake_ws = _FakeWebSocket()
        asyncio.run(bridge._ws_handler(fake_ws))

        types = [json.loads(payload)["type"] for payload in fake_ws.sent]
        assert types == ["init", "demo_start", "demo_cue"]

    def test_client_without_init_receives_nothing(self):
        bridge = DemoWSBridge()
        fake_ws = _FakeWebSocket()
        asyncio.run(bridge._ws_handler(fake_ws))
        assert fake_ws.sent == []
