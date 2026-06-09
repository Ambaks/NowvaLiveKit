"""Baseline comparison and regression detection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from benchmarks.runner import BenchmarkReport


@dataclass
class RegressionAlert:
    component: str
    metric: str
    baseline_ms: float
    current_ms: float
    delta_pct: float
    severity: str


def load_baseline(explicit_path: str | None, output_dir: Path) -> dict | None:
    if explicit_path:
        p = Path(explicit_path)
        if p.exists():
            return json.loads(p.read_text())
        return None

    if not output_dir.exists():
        return None

    reports = sorted(output_dir.glob("benchmark_*.json"))
    if len(reports) < 2:
        return None

    # Second-to-last is the baseline (last is current run being written)
    return json.loads(reports[-2].read_text())


def detect_regressions(
    current: BenchmarkReport,
    baseline: dict,
    threshold_pct: float = 10.0,
) -> list[RegressionAlert]:
    alerts = []
    baseline_components = baseline.get("components", {})

    for name, result in current.components.items():
        if name not in baseline_components:
            continue
        if result.status == "skipped":
            continue

        base = baseline_components[name]
        base_latency = base.get("latency_ms", {})

        for metric in ("p95", "p99"):
            base_val = base_latency.get(metric, 0)
            curr_val = getattr(result.latency, metric, 0)

            if base_val > 0 and curr_val > 0:
                delta_pct = ((curr_val - base_val) / base_val) * 100
                if delta_pct > threshold_pct:
                    alerts.append(RegressionAlert(
                        component=name,
                        metric=metric,
                        baseline_ms=base_val,
                        current_ms=curr_val,
                        delta_pct=round(delta_pct, 1),
                        severity="fail" if delta_pct > 25.0 else "warn",
                    ))

    return alerts
