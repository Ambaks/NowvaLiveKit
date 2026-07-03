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
        self.incoming: list[str] = []

    async def send(self, payload: str) -> None:
        self.sent.append(payload)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.incoming:
            return self.incoming.pop(0)
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

    def test_late_client_receives_latest_live_pose_only(self):
        """Live poses are not backlogged; only the most recent one is replayed."""
        bridge = DemoWSBridge()
        bridge.send_init(_make_demo_data())
        bridge.send_live_pose(np.zeros((19, 3)))
        bridge.send_live_pose(np.ones((19, 3)))

        fake_ws = _FakeWebSocket()
        asyncio.run(bridge._ws_handler(fake_ws))

        types = [json.loads(payload)["type"] for payload in fake_ws.sent]
        assert types == ["init", "live_pose"]

    def test_short_skeleton_live_pose_is_dropped(self):
        bridge = DemoWSBridge()
        bridge.send_live_pose(np.zeros((17, 3)))
        assert bridge._latest_live_payload is None


class TestStartedAck:

    def test_started_message_sets_event(self):
        bridge = DemoWSBridge()
        fake_ws = _FakeWebSocket()
        fake_ws.incoming = [json.dumps({"type": "started"})]
        asyncio.run(bridge._ws_handler(fake_ws))
        assert bridge.wait_started(timeout=0)

    def test_not_started_before_any_message(self):
        bridge = DemoWSBridge()
        assert not bridge.wait_started(timeout=0)
