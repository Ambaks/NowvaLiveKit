"""Benchmark: AgentState save/load to disk."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from agent.core.agent_state import AgentState
from biomechanics.utils.timing import PipelineProfiler

from benchmarks.config import BenchmarkResult, evaluate_status, stats_from_profiler
from benchmarks.fixtures.data import generate_agent_state_dict
from benchmarks.profiler import ResourceProfiler


def run(iterations: int = 100, warmup: int = 10) -> BenchmarkResult:
    save_name = "agent.state.save"
    load_name = "agent.state.load"

    state = AgentState.__new__(AgentState)
    state._user_loaded_from_db = True
    state.state = {
        "mode": "onboarding",
        "user": {"id": "bench_user"},
        "session": {"started_at": None, "last_mode_switch": None, "conversation_history": []},
        "workout": {"active": False, "current_session": None, "exercise": None, "reps": 0, "sets": 0},
        "quick_exercise": {"exercise_name": None, "gathering_params": False},
        "program_creation": {},
    }
    state.state.update(generate_agent_state_dict())

    tmp_dir = tempfile.mkdtemp()
    filepath = str(Path(tmp_dir) / "bench_state.json")

    p_save = PipelineProfiler(window_size=iterations)
    p_load = PipelineProfiler(window_size=iterations)

    import logging
    logging.disable(logging.CRITICAL)

    for _ in range(warmup):
        state.save_state(filepath)

    with ResourceProfiler() as rp:
        for _ in range(iterations):
            with p_save.time_layer(save_name):
                state.save_state(filepath)

            load_state = AgentState.__new__(AgentState)
            load_state._user_loaded_from_db = True
            load_state.state = {"mode": "onboarding", "user": {"id": "bench_user"}}
            with p_load.time_layer(load_name):
                load_state.load_state("bench_user")

    logging.disable(logging.NOTSET)

    # Cleanup
    Path(filepath).unlink(missing_ok=True)
    Path(filepath + ".tmp").unlink(missing_ok=True)

    stats_save = stats_from_profiler(p_save.get_stats(save_name))
    stats_load = stats_from_profiler(p_load.get_stats(load_name))

    return BenchmarkResult(
        component_name=save_name,
        latency=stats_save,
        memory=rp.memory_stats,
        cpu_percent=rp.cpu_percent,
        gpu_vram_mb=rp.gpu_vram_delta,
        iterations=iterations,
        warmup=warmup,
        status=evaluate_status(stats_save.p95, save_name),
        threshold_ms=5.0,
        sub_results=[
            BenchmarkResult(
                component_name=load_name,
                latency=stats_load,
                iterations=iterations,
                warmup=warmup,
                status=evaluate_status(stats_load.p95, load_name),
                threshold_ms=5.0,
            ),
        ],
    )
