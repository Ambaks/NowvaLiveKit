"""Benchmark: IPC _send_framed/_recv_framed roundtrip via UNIX socket."""

from __future__ import annotations

import json
import socket
import tempfile
import threading
from pathlib import Path

from benchmarks.config import BenchmarkResult, LatencyStats, evaluate_status, stats_from_profiler
from benchmarks.fixtures.data import generate_ipc_message
from benchmarks.profiler import ResourceProfiler

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from agent.core.ipc_communication import _send_framed, _recv_framed
from biomechanics.utils.timing import PipelineProfiler


def run(iterations: int = 100, warmup: int = 10) -> BenchmarkResult:
    name = "agent.ipc.roundtrip"
    msg = generate_ipc_message()
    profiler = PipelineProfiler(window_size=iterations)

    sock_path = tempfile.mktemp(suffix=".sock")

    server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server_sock.bind(sock_path)
    server_sock.listen(1)

    received = []

    def _echo_server():
        conn, _ = server_sock.accept()
        try:
            while True:
                data = _recv_framed(conn)
                if data is None:
                    break
                _send_framed(conn, data)
                received.append(1)
        except Exception:
            pass
        finally:
            conn.close()

    thread = threading.Thread(target=_echo_server, daemon=True)
    thread.start()

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(sock_path)

    # Warmup
    for _ in range(warmup):
        _send_framed(client, msg)
        _recv_framed(client)

    with ResourceProfiler() as rp:
        for _ in range(iterations):
            with profiler.time_layer(name):
                _send_framed(client, msg)
                _recv_framed(client)

    client.close()
    server_sock.close()
    Path(sock_path).unlink(missing_ok=True)

    stats = stats_from_profiler(profiler.get_stats(name))
    return BenchmarkResult(
        component_name=name,
        latency=stats,
        memory=rp.memory_stats,
        cpu_percent=rp.cpu_percent,
        gpu_vram_mb=rp.gpu_vram_delta,
        iterations=iterations,
        warmup=warmup,
        status=evaluate_status(stats.p95, name),
        threshold_ms=1.0,
        metadata={"message_bytes": len(json.dumps(msg).encode())},
    )
