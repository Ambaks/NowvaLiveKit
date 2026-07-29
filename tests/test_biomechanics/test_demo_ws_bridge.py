"""Tests for the demo WebSocket bridge's event backlog replay."""

from __future__ import annotations

import asyncio
import json

import numpy as np
import pytest

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

    def test_live_pose_converted_from_mediapipe_to_viewer_coords(self):
        """A MediaPipe Y-down skeleton must render head-up in viewer coords.

        The demo pose stack is transformed to viewer coords upstream; live
        poses arrive raw from the pipeline. Without the same transform the
        skeleton renders upside down when the demo morphs back to live.
        """
        bridge = DemoWSBridge()
        # MediaPipe world coords: hip-centered, Y=down — nose above hips
        # (negative y), ankles below (positive y).
        pose = np.zeros((19, 3))
        pose[0] = [0.0, -0.8, 0.0]     # nose
        pose[11] = [-0.1, 0.0, 0.0]    # hips
        pose[12] = [0.1, 0.0, 0.0]
        pose[15] = [-0.1, 0.9, 0.0]    # ankles
        pose[16] = [0.1, 0.9, 0.0]
        pose[17] = [-0.1, 1.0, 0.1]    # toes: below ankles, toward floor
        pose[18] = [0.1, 1.0, 0.1]

        bridge.send_live_pose(pose)

        points = json.loads(bridge._latest_live_payload)["points"]
        nose_y, ankle_y, toe_y = points[0][1], points[15][1], points[17][1]
        assert toe_y == 0.0
        assert ankle_y == pytest.approx(0.1)
        assert nose_y > ankle_y


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


class TestLivePoseJointCount:
    """The viewer morphs live poses against the init stack — a live pose
    with fewer joints leaves the extras unset and the morph goes NaN."""

    def test_live_pose_matches_a_21_joint_replay_init(self):
        bridge = DemoWSBridge()
        bridge.send_replay_init(
            np.zeros((21, 3)), highlight_joints=[], rep_number=1, rep_score=80.0,
        )
        bridge.send_live_pose(np.ones((21, 3)))
        payload = json.loads(bridge._latest_live_payload)
        assert len(payload["points"]) == 21

    def test_live_pose_matches_a_19_joint_demo_stack(self):
        bridge = DemoWSBridge()
        bridge.send_init(_make_demo_data())
        bridge.send_live_pose(np.ones((21, 3)))
        payload = json.loads(bridge._latest_live_payload)
        assert len(payload["points"]) == 19

    def test_live_pose_dropped_when_skeleton_is_too_small(self):
        bridge = DemoWSBridge()
        bridge.send_replay_init(
            np.zeros((21, 3)), highlight_joints=[], rep_number=1, rep_score=80.0,
        )
        bridge.send_live_pose(np.ones((19, 3)))
        assert bridge._latest_live_payload is None
