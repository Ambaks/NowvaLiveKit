"""JSON + HTML report generation."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from benchmarks.runner import BenchmarkReport


def write_json_report(report: BenchmarkReport, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"benchmark_{timestamp}.json"

    data = {
        "timestamp": report.timestamp,
        "git_commit": report.git_commit,
        "git_branch": report.git_branch,
        "system": report.system,
        "elapsed_seconds": report.elapsed_seconds,
        "components": {
            name: result.to_dict()
            for name, result in report.components.items()
        },
        "pipelines": report.pipelines,
    }
    path.write_text(json.dumps(data, indent=2))
    return path


def load_all_reports(output_dir: Path) -> list[dict]:
    if not output_dir.exists():
        return []
    reports = []
    for f in sorted(output_dir.glob("benchmark_*.json")):
        try:
            reports.append(json.loads(f.read_text()))
        except Exception:
            pass
    return reports


def generate_html_report(
    report: BenchmarkReport,
    historical: list[dict] | None,
    regressions: list | None,
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"benchmark_report_{timestamp}.html"

    components_data = {}
    for name, result in report.components.items():
        components_data[name] = result.to_dict()

    regression_data = []
    if regressions:
        for r in regressions:
            regression_data.append({
                "component": r.component,
                "metric": r.metric,
                "baseline_ms": r.baseline_ms,
                "current_ms": r.current_ms,
                "delta_pct": r.delta_pct,
                "severity": r.severity,
            })

    trend_data = _prepare_trend_data(historical) if historical else {}

    html = _HTML_TEMPLATE.replace("{{COMPONENTS_JSON}}", json.dumps(components_data, indent=2))
    html = html.replace("{{PIPELINES_JSON}}", json.dumps(report.pipelines, indent=2))
    html = html.replace("{{REGRESSIONS_JSON}}", json.dumps(regression_data, indent=2))
    html = html.replace("{{TREND_JSON}}", json.dumps(trend_data, indent=2))
    html = html.replace("{{SYSTEM_JSON}}", json.dumps(report.system, indent=2))
    html = html.replace("{{GIT_COMMIT}}", report.git_commit)
    html = html.replace("{{GIT_BRANCH}}", report.git_branch)
    html = html.replace("{{TIMESTAMP}}", report.timestamp)
    html = html.replace("{{ELAPSED}}", str(report.elapsed_seconds))

    path.write_text(html)
    return path


def _prepare_trend_data(historical: list[dict]) -> dict:
    if not historical:
        return {}

    key_components = [
        "biomechanics.pose.mediapipe",
        "biomechanics.ik.analytical",
        "biomechanics.faults.rule_engine",
        "biomechanics.filters.combined",
        "biomechanics.bilstm",
        "biomechanics.pipeline_e2e",
    ]

    labels = []
    datasets: dict[str, list[float | None]] = {k: [] for k in key_components}

    for report_data in historical[-20:]:
        commit = report_data.get("git_commit", "?")
        labels.append(commit)
        components = report_data.get("components", {})
        for comp in key_components:
            if comp in components:
                datasets[comp].append(components[comp].get("latency_ms", {}).get("p95"))
            else:
                datasets[comp].append(None)

    return {"labels": labels, "datasets": datasets}


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nowva Benchmark Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0f1117; color: #e0e0e0; font-family: 'Segoe UI', system-ui, sans-serif; padding: 24px; }
  h1 { color: #fff; margin-bottom: 8px; font-size: 24px; }
  h2 { color: #a0a8c0; margin: 32px 0 16px; font-size: 18px; border-bottom: 1px solid #2a2d3a; padding-bottom: 8px; }
  .meta { color: #707890; font-size: 13px; margin-bottom: 24px; }
  .summary { display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
  .badge { padding: 8px 20px; border-radius: 8px; font-weight: 600; font-size: 15px; }
  .badge-pass { background: #1a3a2a; color: #4ade80; }
  .badge-warn { background: #3a3520; color: #fbbf24; }
  .badge-fail { background: #3a1a1a; color: #f87171; }
  .badge-skip { background: #2a2d3a; color: #707890; }
  .badge-info { background: #1a2a3a; color: #60a5fa; }
  .chart-container { background: #1a1d2a; border-radius: 12px; padding: 20px; margin-bottom: 24px; }
  canvas { max-height: 500px; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 24px; }
  th { background: #1a1d2a; padding: 10px 12px; text-align: left; font-size: 13px; color: #a0a8c0; }
  td { padding: 10px 12px; border-bottom: 1px solid #1a1d2a; font-size: 13px; }
  tr:hover { background: #1a1d2a; }
  .status-pass { color: #4ade80; }
  .status-warn { color: #fbbf24; }
  .status-fail { color: #f87171; font-weight: 600; }
  .status-skipped { color: #707890; }
  .regression-row { background: #2a1a1a !important; }
</style>
</head>
<body>
<h1>Nowva Pipeline Benchmark Report</h1>
<div class="meta">
  Branch: <strong>{{GIT_BRANCH}}</strong> &middot;
  Commit: <strong>{{GIT_COMMIT}}</strong> &middot;
  {{TIMESTAMP}} &middot;
  {{ELAPSED}}s total
</div>

<div class="summary" id="summary-badges"></div>

<h2>Component Status</h2>
<table id="status-table">
  <thead><tr><th>Component</th><th>Status</th><th>Mean</th><th>P50</th><th>P95</th><th>P99</th><th>Peak Mem</th><th>CPU %</th></tr></thead>
  <tbody></tbody>
</table>

<h2>Latency Distribution (P95)</h2>
<div class="chart-container"><canvas id="latencyChart"></canvas></div>

<h2>Pipeline Breakdown</h2>
<div class="chart-container" style="max-width:500px"><canvas id="breakdownChart"></canvas></div>

<h2>Memory Profile</h2>
<div class="chart-container"><canvas id="memoryChart"></canvas></div>

<h2>CPU Utilization</h2>
<div class="chart-container"><canvas id="cpuChart"></canvas></div>

<h2>Historical Trend (P95)</h2>
<div class="chart-container"><canvas id="trendChart"></canvas></div>

<div id="regression-section" style="display:none">
  <h2>Regression Alerts</h2>
  <table id="regression-table">
    <thead><tr><th>Component</th><th>Metric</th><th>Baseline</th><th>Current</th><th>Delta</th><th>Severity</th></tr></thead>
    <tbody></tbody>
  </table>
</div>

<script>
const components = {{COMPONENTS_JSON}};
const pipelines = {{PIPELINES_JSON}};
const regressions = {{REGRESSIONS_JSON}};
const trendData = {{TREND_JSON}};
const systemInfo = {{SYSTEM_JSON}};

// Summary badges
const counts = {pass:0, warn:0, fail:0, skipped:0};
Object.values(components).forEach(c => counts[c.status] = (counts[c.status]||0) + 1);
const badgesEl = document.getElementById('summary-badges');
badgesEl.innerHTML = `
  <span class="badge badge-pass">${counts.pass} Pass</span>
  <span class="badge badge-warn">${counts.warn} Warn</span>
  <span class="badge badge-fail">${counts.fail} Fail</span>
  <span class="badge badge-skip">${counts.skipped} Skip</span>
  ${pipelines.biomechanics_component_sum ? `<span class="badge badge-info">${pipelines.biomechanics_component_sum.estimated_fps} FPS est.</span>` : ''}
`;

// Status table
const tbody = document.querySelector('#status-table tbody');
Object.entries(components).sort((a,b) => a[0].localeCompare(b[0])).forEach(([name, c]) => {
  const row = document.createElement('tr');
  row.innerHTML = `
    <td>${name}</td>
    <td class="status-${c.status}">${c.status.toUpperCase()}</td>
    <td>${c.latency_ms.mean.toFixed(2)}ms</td>
    <td>${c.latency_ms.p50.toFixed(2)}ms</td>
    <td>${c.latency_ms.p95.toFixed(2)}ms</td>
    <td>${c.latency_ms.p99.toFixed(2)}ms</td>
    <td>${c.memory_mb.peak.toFixed(1)}MB</td>
    <td>${c.cpu_percent.toFixed(0)}%</td>
  `;
  tbody.appendChild(row);
});

// Color helper
function statusColor(status) {
  return {pass:'#4ade80', warn:'#fbbf24', fail:'#f87171', skipped:'#707890'}[status] || '#60a5fa';
}

// Latency bar chart
const latencyEntries = Object.entries(components).filter(([,c]) => c.status !== 'skipped').sort((a,b) => b[1].latency_ms.p95 - a[1].latency_ms.p95);
new Chart(document.getElementById('latencyChart'), {
  type: 'bar',
  data: {
    labels: latencyEntries.map(([n]) => n),
    datasets: [
      { label: 'P50', data: latencyEntries.map(([,c]) => c.latency_ms.p50), backgroundColor: '#3b82f6' },
      { label: 'P95', data: latencyEntries.map(([,c]) => c.latency_ms.p95), backgroundColor: latencyEntries.map(([,c]) => statusColor(c.status)) },
      { label: 'P99', data: latencyEntries.map(([,c]) => c.latency_ms.p99), backgroundColor: '#6366f1' },
    ]
  },
  options: {
    indexAxis: 'y',
    responsive: true,
    plugins: { legend: { labels: { color: '#a0a8c0' } } },
    scales: {
      x: { title: { display: true, text: 'Latency (ms)', color: '#a0a8c0' }, ticks: { color: '#707890' }, grid: { color: '#1a1d2a' } },
      y: { ticks: { color: '#a0a8c0', font: { size: 11 } }, grid: { display: false } }
    }
  }
});

// Pipeline breakdown doughnut
if (pipelines.biomechanics_component_sum) {
  const bd = pipelines.biomechanics_component_sum.breakdown_pct;
  const colors = ['#3b82f6','#8b5cf6','#ec4899','#f59e0b','#10b981','#ef4444','#06b6d4','#84cc16','#f97316','#6366f1','#14b8a6','#e879f9'];
  new Chart(document.getElementById('breakdownChart'), {
    type: 'doughnut',
    data: {
      labels: Object.keys(bd),
      datasets: [{ data: Object.values(bd), backgroundColor: colors.slice(0, Object.keys(bd).length) }]
    },
    options: {
      responsive: true,
      plugins: { legend: { position: 'right', labels: { color: '#a0a8c0', font: { size: 11 } } } }
    }
  });
}

// Memory chart
const memEntries = Object.entries(components).filter(([,c]) => c.memory_mb.peak > 0).sort((a,b) => b[1].memory_mb.peak - a[1].memory_mb.peak);
new Chart(document.getElementById('memoryChart'), {
  type: 'bar',
  data: {
    labels: memEntries.map(([n]) => n),
    datasets: [{ label: 'Peak MB', data: memEntries.map(([,c]) => c.memory_mb.peak), backgroundColor: '#8b5cf6' }]
  },
  options: {
    indexAxis: 'y',
    responsive: true,
    plugins: { legend: { labels: { color: '#a0a8c0' } } },
    scales: {
      x: { title: { display: true, text: 'Memory (MB)', color: '#a0a8c0' }, ticks: { color: '#707890' }, grid: { color: '#1a1d2a' } },
      y: { ticks: { color: '#a0a8c0', font: { size: 11 } }, grid: { display: false } }
    }
  }
});

// CPU chart
const cpuEntries = Object.entries(components).filter(([,c]) => c.cpu_percent > 0).sort((a,b) => b[1].cpu_percent - a[1].cpu_percent);
new Chart(document.getElementById('cpuChart'), {
  type: 'bar',
  data: {
    labels: cpuEntries.map(([n]) => n),
    datasets: [{ label: 'CPU %', data: cpuEntries.map(([,c]) => c.cpu_percent), backgroundColor: '#f59e0b' }]
  },
  options: {
    indexAxis: 'y',
    responsive: true,
    plugins: { legend: { labels: { color: '#a0a8c0' } } },
    scales: {
      x: { title: { display: true, text: 'CPU %', color: '#a0a8c0' }, ticks: { color: '#707890' }, grid: { color: '#1a1d2a' } },
      y: { ticks: { color: '#a0a8c0', font: { size: 11 } }, grid: { display: false } }
    }
  }
});

// Trend chart
if (trendData.labels && trendData.labels.length > 1) {
  const trendColors = ['#3b82f6','#8b5cf6','#ec4899','#f59e0b','#10b981','#ef4444'];
  const trendDatasets = Object.entries(trendData.datasets).map(([name, values], i) => ({
    label: name,
    data: values,
    borderColor: trendColors[i % trendColors.length],
    tension: 0.3,
    spanGaps: true,
    pointRadius: 3,
  }));
  new Chart(document.getElementById('trendChart'), {
    type: 'line',
    data: { labels: trendData.labels, datasets: trendDatasets },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: '#a0a8c0' } } },
      scales: {
        x: { ticks: { color: '#707890' }, grid: { color: '#1a1d2a' } },
        y: { title: { display: true, text: 'P95 Latency (ms)', color: '#a0a8c0' }, ticks: { color: '#707890' }, grid: { color: '#1a1d2a' } }
      }
    }
  });
} else {
  document.getElementById('trendChart').parentElement.innerHTML = '<p style="color:#707890;text-align:center;padding:20px">Need 2+ runs for trend data</p>';
}

// Regressions
if (regressions.length > 0) {
  document.getElementById('regression-section').style.display = 'block';
  const rtbody = document.querySelector('#regression-table tbody');
  regressions.forEach(r => {
    const row = document.createElement('tr');
    row.className = 'regression-row';
    row.innerHTML = `
      <td>${r.component}</td>
      <td>${r.metric}</td>
      <td>${r.baseline_ms.toFixed(2)}ms</td>
      <td>${r.current_ms.toFixed(2)}ms</td>
      <td class="status-fail">+${r.delta_pct.toFixed(1)}%</td>
      <td class="status-${r.severity === 'fail' ? 'fail' : 'warn'}">${r.severity.toUpperCase()}</td>
    `;
    rtbody.appendChild(row);
  });
}
</script>
</body>
</html>"""
