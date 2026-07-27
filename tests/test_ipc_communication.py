"""Tests for IPC server/client: framing, shutdown safety, reconnection, backpressure."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Iterator

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.core.ipc_communication import (
    SEND_QUEUE_MAX_SIZE,
    IPCClient,
    IPCServer,
    _SendQueue,
)

WAIT_TIMEOUT_S = 3.0
POLL_INTERVAL_S = 0.01
# AF_UNIX socket paths are limited to ~104 bytes on macOS
MAX_SOCKET_PATH_BYTES = 90


def _wait_until(predicate: Callable[[], bool], timeout: float = WAIT_TIMEOUT_S) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(POLL_INTERVAL_S)
    return predicate()


def _start_server(
    socket_path: str, on_message: Callable[[dict], None] | None = None
) -> tuple[IPCServer, threading.Thread]:
    server = IPCServer(socket_path=socket_path)
    server.bind(message_callback=on_message)

    def _serve() -> None:
        try:
            server.accept_client()
            server.listen()
        except OSError:
            if server.running:
                raise

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    return server, thread


def _frame_data_message(sequence_number: int) -> dict:
    return {"type": "frame_data", "seq": sequence_number}


@pytest.fixture
def socket_path(tmp_path: Path) -> Iterator[str]:
    candidate = tmp_path / "ipc.sock"
    if len(str(candidate).encode()) <= MAX_SOCKET_PATH_BYTES:
        yield str(candidate)
        return
    short_dir = tempfile.mkdtemp(prefix="nowva_ipc_")
    yield os.path.join(short_dir, "ipc.sock")
    shutil.rmtree(short_dir, ignore_errors=True)


class TestFraming:
    def test_client_to_server_round_trip(self, socket_path: str) -> None:
        received: list[dict] = []
        server, thread = _start_server(socket_path, received.append)
        client = IPCClient(socket_path=socket_path)
        try:
            assert client.connect(timeout=5) is True
            sent = [{"type": "fault", "seq": i, "payload": "x" * 200} for i in range(5)]
            for message in sent:
                client.send_message(message)
            assert _wait_until(lambda: len(received) == 5)
            assert received == sent
        finally:
            client.disconnect()
            server.stop()
            thread.join(timeout=2)

    def test_server_to_client_round_trip(self, socket_path: str) -> None:
        server, thread = _start_server(socket_path)
        client = IPCClient(socket_path=socket_path)
        received: list[dict] = []
        listener = threading.Thread(
            target=client.listen, kwargs={"message_callback": received.append}, daemon=True
        )
        try:
            assert client.connect(timeout=5) is True
            listener.start()
            assert _wait_until(lambda: server.client_socket is not None)
            server.send_message({"type": "rep_complete", "rep": 3})
            assert _wait_until(lambda: len(received) == 1)
            assert received[0] == {"type": "rep_complete", "rep": 3}
        finally:
            client.disconnect()
            server.stop()
            thread.join(timeout=2)
            listener.join(timeout=2)


class TestStopSafety:
    def test_message_sent_just_before_disconnect_is_delivered(self, socket_path: str) -> None:
        # pipeline_process sends a final 'error'/'pipeline_status' message and
        # immediately disconnects — stop() must flush it, not discard it
        received: list[dict] = []
        server, thread = _start_server(socket_path, received.append)
        client = IPCClient(socket_path=socket_path)
        try:
            assert client.connect(timeout=5) is True
            for _ in range(20):
                client.send_message({"type": "error", "value": "pipeline init failed"})
                client.disconnect()
                assert client.connect(timeout=5) is True
            client.send_message({"type": "pipeline_status", "status": "stopped"})
        finally:
            client.disconnect()
        assert _wait_until(lambda: len(received) == 21)
        assert received[0] == {"type": "error", "value": "pipeline init failed"}
        assert received[-1] == {"type": "pipeline_status", "status": "stopped"}
        server.stop()
        thread.join(timeout=2)

    def test_send_message_after_server_stop_does_not_raise(self, socket_path: str) -> None:
        server, thread = _start_server(socket_path)
        client = IPCClient(socket_path=socket_path)
        assert client.connect(timeout=5) is True
        assert _wait_until(lambda: server.client_socket is not None)

        server.stop()
        server.send_message({"type": "fault", "seq": 1})

        assert server.running is False
        assert server.client_socket is None
        assert server.server_socket is None
        client.disconnect()
        thread.join(timeout=2)

    def test_send_message_after_client_disconnect_does_not_raise(self, socket_path: str) -> None:
        server, thread = _start_server(socket_path)
        client = IPCClient(socket_path=socket_path)
        assert client.connect(timeout=5) is True

        client.disconnect()
        client.send_message({"type": "fault", "seq": 1})

        assert client.running is False
        assert client.client_socket is None
        server.stop()
        thread.join(timeout=2)

    def test_double_stop_does_not_raise(self, socket_path: str) -> None:
        server = IPCServer(socket_path=socket_path)
        server.bind()
        server.stop()
        server.stop()
        assert server.server_socket is None

    def test_bind_replaces_stale_socket_file(self, socket_path: str) -> None:
        Path(socket_path).touch()
        server = IPCServer(socket_path=socket_path)
        server.bind()
        try:
            client = IPCClient(socket_path=socket_path)
            assert client.connect(timeout=5) is True
            client.disconnect()
        finally:
            server.stop()
        assert not os.path.exists(socket_path)


class TestReconnection:
    def test_server_reaccepts_after_client_disconnect(self, socket_path: str) -> None:
        received: list[dict] = []
        server, thread = _start_server(socket_path, received.append)

        first_client = IPCClient(socket_path=socket_path)
        assert first_client.connect(timeout=5) is True
        assert _wait_until(lambda: server.client_socket is not None)
        first_client.send_message({"type": "hello", "n": 1})
        assert _wait_until(lambda: len(received) == 1)
        first_client.disconnect()
        assert _wait_until(lambda: server.client_socket is None)

        second_client = IPCClient(socket_path=socket_path)
        try:
            assert second_client.connect(timeout=5) is True
            assert _wait_until(lambda: server.client_socket is not None)
            second_client.send_message({"type": "hello", "n": 2})
            assert _wait_until(lambda: len(received) == 2)
            assert [message["n"] for message in received] == [1, 2]
        finally:
            second_client.disconnect()
            server.stop()
            thread.join(timeout=2)

    def test_client_connect_retries_until_server_binds(self, socket_path: str) -> None:
        server = IPCServer(socket_path=socket_path)

        def _bind_after_delay() -> None:
            time.sleep(0.7)
            server.bind()

        binder = threading.Thread(target=_bind_after_delay, daemon=True)
        binder.start()

        client = IPCClient(socket_path=socket_path)
        try:
            assert client.connect(timeout=5) is True
        finally:
            binder.join(timeout=2)
            client.disconnect()
            server.stop()

    def test_failed_connect_does_not_leak_file_descriptors(self, socket_path: str) -> None:
        if not os.path.exists("/dev/fd"):
            pytest.skip("/dev/fd not available on this platform")

        client = IPCClient(socket_path=socket_path)
        open_fds_before = len(os.listdir("/dev/fd"))
        assert client.connect(timeout=1) is False
        open_fds_after = len(os.listdir("/dev/fd"))
        assert open_fds_after == open_fds_before


class TestBackpressure:
    def test_frame_data_dropped_when_queue_full(self) -> None:
        send_queue = _SendQueue("test", lambda: None)
        for i in range(SEND_QUEUE_MAX_SIZE):
            send_queue.put(_frame_data_message(i))

        send_queue.put(_frame_data_message(SEND_QUEUE_MAX_SIZE))

        assert len(send_queue._messages) == SEND_QUEUE_MAX_SIZE
        assert send_queue._messages[-1]["seq"] == SEND_QUEUE_MAX_SIZE - 1

    def test_important_message_evicts_oldest_frame_data(self) -> None:
        send_queue = _SendQueue("test", lambda: None)
        for i in range(SEND_QUEUE_MAX_SIZE):
            send_queue.put(_frame_data_message(i))

        send_queue.put({"type": "fault", "severity": "SEVERE"})

        assert len(send_queue._messages) == SEND_QUEUE_MAX_SIZE
        assert send_queue._messages[-1] == {"type": "fault", "severity": "SEVERE"}
        assert send_queue._messages[0]["seq"] == 1

    def test_important_message_dropped_when_no_frame_data_queued(self) -> None:
        send_queue = _SendQueue("test", lambda: None)
        for i in range(SEND_QUEUE_MAX_SIZE):
            send_queue.put({"type": "fault", "seq": i})

        send_queue.put({"type": "fault", "seq": SEND_QUEUE_MAX_SIZE})

        assert len(send_queue._messages) == SEND_QUEUE_MAX_SIZE
        assert all(message["seq"] < SEND_QUEUE_MAX_SIZE for message in send_queue._messages)

    def test_send_message_queues_through_server_before_bind(self, socket_path: str) -> None:
        server = IPCServer(socket_path=socket_path)
        for i in range(SEND_QUEUE_MAX_SIZE + 5):
            server.send_message(_frame_data_message(i))
        assert len(server._sender._messages) == SEND_QUEUE_MAX_SIZE

    def test_raw_bytes_evicted_like_frame_data(self) -> None:
        send_queue = _SendQueue("test", lambda: None)
        for i in range(SEND_QUEUE_MAX_SIZE):
            send_queue.put_raw(json.dumps({"type": "frame_data", "seq": i}).encode())

        send_queue.put({"type": "fault", "severity": "SEVERE"})

        assert len(send_queue._messages) == SEND_QUEUE_MAX_SIZE
        assert send_queue._messages[-1] == {"type": "fault", "severity": "SEVERE"}

    def test_raw_bytes_dropped_when_queue_full(self) -> None:
        send_queue = _SendQueue("test", lambda: None)
        for i in range(SEND_QUEUE_MAX_SIZE):
            send_queue.put_raw(b'{"type":"frame_data"}')

        send_queue.put_raw(b'{"type":"frame_data","overflow":true}')

        assert len(send_queue._messages) == SEND_QUEUE_MAX_SIZE


def _start_raw_server(
    socket_path: str,
    on_raw_message: Callable[[dict, bytes], None],
) -> tuple[IPCServer, threading.Thread]:
    server = IPCServer(socket_path=socket_path)
    server.bind(raw_message_callback=on_raw_message)

    def _serve() -> None:
        try:
            server.accept_client()
            server.listen()
        except OSError:
            if server.running:
                raise

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    return server, thread


class TestRawForwarding:
    def test_raw_message_callback_receives_raw_bytes(self, socket_path: str) -> None:
        results: list[tuple[dict, bytes]] = []

        def _on_raw(msg: dict, raw: bytes) -> None:
            results.append((msg, raw))

        server, thread = _start_raw_server(socket_path, _on_raw)
        client = IPCClient(socket_path=socket_path)
        try:
            assert client.connect(timeout=5) is True
            sent = {"type": "frame_data", "joint_angles": {"knee_l": 90}}
            client.send_message(sent)
            assert _wait_until(lambda: len(results) == 1)

            parsed, raw_bytes = results[0]
            assert parsed == sent
            assert json.loads(raw_bytes.decode("utf-8")) == sent
        finally:
            client.disconnect()
            server.stop()
            thread.join(timeout=2)

    def test_send_raw_message_delivered_without_re_encoding(self, socket_path: str) -> None:
        """Simulate the forwarding path: receive raw bytes, forward them."""
        # Set up two socket pairs: source -> middleman -> destination
        src_path = socket_path
        dst_path = socket_path + ".dst"

        dst_received: list[dict] = []
        dst_server, dst_thread = _start_server(dst_path, dst_received.append)

        raw_captured: list[bytes] = []

        def _on_raw(msg: dict, raw: bytes) -> None:
            raw_captured.append(raw)
            if msg.get("type") == "frame_data":
                dst_server.send_raw_message(raw)
            else:
                dst_server.send_message(msg)

        mid_server, mid_thread = _start_raw_server(src_path, _on_raw)

        src_client = IPCClient(socket_path=src_path)
        dst_client = IPCClient(socket_path=dst_path)
        dst_listen_received: list[dict] = []
        dst_listener = threading.Thread(
            target=dst_client.listen,
            kwargs={"message_callback": dst_listen_received.append},
            daemon=True,
        )

        try:
            assert dst_client.connect(timeout=5) is True
            dst_listener.start()

            assert src_client.connect(timeout=5) is True
            assert _wait_until(lambda: mid_server.client_socket is not None)
            assert _wait_until(lambda: dst_server.client_socket is not None)

            original = {"type": "frame_data", "joint_angles": {"knee_l": 85}, "fps": 30.0}
            src_client.send_message(original)

            assert _wait_until(lambda: len(dst_listen_received) == 1)
            assert dst_listen_received[0] == original
        finally:
            src_client.disconnect()
            dst_client.disconnect()
            mid_server.stop()
            dst_server.stop()
            mid_thread.join(timeout=2)
            dst_thread.join(timeout=2)
            dst_listener.join(timeout=2)
            try:
                os.unlink(dst_path)
            except FileNotFoundError:
                pass
