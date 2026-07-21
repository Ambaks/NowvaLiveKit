"""Interactive browser-based biomechanics dashboard.

Generates self-contained HTML files with Plotly.js charts for post-workout
analysis.  Dark neon theme, interactive hover tooltips with derivatives.
"""

from __future__ import annotations

import json
import webbrowser
from pathlib import Path
from typing import Optional

import numpy as np

from biomechanics.analysis.rep_segmenter import segment_set


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_set_dashboard(
    plot_data: dict,
    seg_result: dict,
    out_dir: str,
    set_number: int,
    auto_open: bool = False,
) -> str:
    """Generate an interactive HTML dashboard for a single set.

    Args:
        plot_data: The ``plot_export`` dict from ``finalize_set``.
        seg_result: Output of ``segment_set(plot_data)``.
        out_dir: Directory to write the HTML file.
        set_number: Set number for the title.
        auto_open: Open in browser automatically.

    Returns:
        Path to the generated HTML file.
    """
    payload = _prepare_dashboard_payload(plot_data, seg_result)
    html = _render_html(payload, is_session=False)
    path = str(Path(out_dir) / f"set{set_number}_dashboard.html")
    Path(path).write_text(html)
    print(f"  Saved: {path}")
    if auto_open:
        webbrowser.open(f"file://{Path(path).resolve()}")
    return path


def generate_session_dashboard(
    set_data_list: list[dict],
    session_info: dict,
    out_dir: str,
    auto_open: bool = True,
) -> str:
    """Generate a multi-set session dashboard with tab switching.

    Args:
        set_data_list: List of ``plot_export`` dicts, one per set.
        session_info: Dict with ``exercise``, ``target_sets``, ``target_reps``.
        out_dir: Directory to write the HTML file.
        auto_open: Open in browser automatically.

    Returns:
        Path to the generated HTML file.
    """
    sets_payload = []
    for pd in set_data_list:
        seg = segment_set(pd)
        sets_payload.append(_prepare_dashboard_payload(pd, seg))

    full_payload = {
        "sets": sets_payload,
        "session_info": session_info,
    }
    html = _render_html(full_payload, is_session=True)
    path = str(Path(out_dir) / "session_dashboard.html")
    Path(path).write_text(html)
    print(f"  Saved: {path}")
    if auto_open:
        webbrowser.open(f"file://{Path(path).resolve()}")
    return path


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------

def _compute_derivative(timestamps: list, values: list) -> list:
    """Compute numerical derivative using numpy.gradient."""
    if len(values) < 2:
        return [0.0] * len(values)
    t = np.asarray(timestamps, dtype=np.float64)
    v = np.asarray(values, dtype=np.float64)
    return np.gradient(v, t).tolist()


def _prepare_dashboard_payload(plot_data: dict, seg_result: dict) -> dict:
    """Enrich plot_data with derivatives and segmentation for the JS frontend."""
    ts = plot_data["timestamps"]

    # Derivative signals
    signals = {
        "hip_position_cm": ("d_hip_position_cm_s", "cm/s"),
        "hip_velocity_cm_s": ("d_hip_velocity_cm_s2", "cm/s²"),
        "knee_angle_deg": ("d_knee_angle_deg_s", "°/s"),
        "hip_angle_deg": ("d_hip_angle_deg_s", "°/s"),
        "trunk_angle_deg": ("d_trunk_angle_deg_s", "°/s"),
        "pipeline_knee_flexion_deg": ("d_pipeline_knee_deg_s", "°/s"),
        "pipeline_hip_flexion_deg": ("d_pipeline_hip_deg_s", "°/s"),
        "pipeline_trunk_flexion_deg": ("d_pipeline_trunk_deg_s", "°/s"),
        "hip_adduction_l_deg": ("d_hip_adduction_l_deg_s", "°/s"),
        "hip_adduction_r_deg": ("d_hip_adduction_r_deg_s", "°/s"),
        "knee_valgus_l_deg": ("d_knee_valgus_l_deg_s", "°/s"),
        "knee_valgus_r_deg": ("d_knee_valgus_r_deg_s", "°/s"),
        "bilateral_asymmetry_deg": ("d_bilateral_asymmetry_deg_s", "°/s"),
    }

    derivatives = {}
    for key, (d_key, _unit) in signals.items():
        vals = plot_data.get(key, [])
        if vals:
            derivatives[d_key] = _compute_derivative(ts, vals)
        else:
            derivatives[d_key] = []

    # Use segmentation end times as rep markers (standing position = rep complete)
    # Shifted by ½ period from bottom so labels align with rep completion.
    rep_markers = []
    for rep in seg_result.get("reps", []):
        rep_markers.append({
            "time_s": rep["end_time_s"],
            "rep_number": rep["rep_number"],
        })

    return {
        "set_number": plot_data.get("set_number", 1),
        "timestamps": ts,
        "hip_position_cm": plot_data.get("hip_position_cm", []),
        "hip_velocity_cm_s": plot_data.get("hip_velocity_cm_s", []),
        "knee_angle_deg": plot_data.get("knee_angle_deg", []),
        "hip_angle_deg": plot_data.get("hip_angle_deg", []),
        "trunk_angle_deg": plot_data.get("trunk_angle_deg", []),
        "pipeline_knee_flexion_deg": plot_data.get("pipeline_knee_flexion_deg", []),
        "pipeline_hip_flexion_deg": plot_data.get("pipeline_hip_flexion_deg", []),
        "pipeline_trunk_flexion_deg": plot_data.get("pipeline_trunk_flexion_deg", []),
        "hip_adduction_l_deg": plot_data.get("hip_adduction_l_deg", []),
        "hip_adduction_r_deg": plot_data.get("hip_adduction_r_deg", []),
        "knee_valgus_l_deg": plot_data.get("knee_valgus_l_deg", []),
        "knee_valgus_r_deg": plot_data.get("knee_valgus_r_deg", []),
        "knee_ankle_sep_ratio": plot_data.get("knee_ankle_sep_ratio", []),
        "bilateral_asymmetry_deg": plot_data.get("bilateral_asymmetry_deg", []),
        **derivatives,
        "rep_markers": rep_markers,
        "segmentation": seg_result,
        "fault_events": plot_data.get("fault_events", []),
        "valgus_band": plot_data.get("valgus_band", None),
        "thresholds": plot_data.get("thresholds", None),
    }


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

_CSS = """\
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    background: #1a1a2e;
    color: #e0e0e0;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    padding: 24px;
    min-height: 100vh;
}
h1 {
    text-align: center;
    font-size: 1.8rem;
    font-weight: 600;
    letter-spacing: 2px;
    text-transform: uppercase;
    background: linear-gradient(90deg, #00f5ff, #ff00ff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 8px;
}
.subtitle {
    text-align: center;
    color: #888;
    font-size: 0.9rem;
    margin-bottom: 24px;
}
/* Summary cards */
.cards-row {
    display: flex;
    gap: 16px;
    justify-content: center;
    flex-wrap: wrap;
    margin-bottom: 28px;
}
.stat-card {
    background: #16213e;
    border: 1px solid rgba(0, 245, 255, 0.2);
    border-radius: 12px;
    padding: 16px 24px;
    min-width: 150px;
    text-align: center;
    box-shadow: 0 0 12px rgba(0, 245, 255, 0.08);
}
.stat-card .label {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #888;
    margin-bottom: 6px;
}
.stat-card .value {
    font-size: 1.5rem;
    font-weight: 700;
    color: #00f5ff;
}
.stat-card .value.magenta { color: #ff00ff; }
.stat-card .value.lime { color: #39ff14; }
.stat-card .value.orange { color: #ff9800; }
/* Chart cards */
.chart-card {
    background: #16213e;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 20px;
    box-shadow: 0 0 20px rgba(0,0,0,0.3);
}
.chart-card h2 {
    font-size: 1rem;
    font-weight: 500;
    color: #ccc;
    margin-bottom: 8px;
    letter-spacing: 1px;
}
/* Rep table */
.rep-table-wrap {
    background: #16213e;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 20px;
    overflow-x: auto;
    box-shadow: 0 0 20px rgba(0,0,0,0.3);
}
.rep-table-wrap h2 {
    font-size: 1rem;
    font-weight: 500;
    color: #ccc;
    margin-bottom: 12px;
    letter-spacing: 1px;
}
table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
}
th {
    text-align: left;
    padding: 8px 12px;
    border-bottom: 1px solid rgba(0, 245, 255, 0.3);
    color: #00f5ff;
    font-weight: 600;
    white-space: nowrap;
}
td {
    padding: 8px 12px;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    white-space: nowrap;
}
tr:hover td { background: rgba(0, 245, 255, 0.04); }
/* Tabs */
.tab-bar {
    display: flex;
    gap: 4px;
    justify-content: center;
    margin-bottom: 24px;
    flex-wrap: wrap;
}
.tab-btn {
    background: #16213e;
    border: 1px solid rgba(0, 245, 255, 0.2);
    border-radius: 8px;
    color: #aaa;
    padding: 8px 20px;
    cursor: pointer;
    font-size: 0.85rem;
    transition: all 0.2s;
}
.tab-btn:hover { border-color: #00f5ff; color: #fff; }
.tab-btn.active {
    background: rgba(0, 245, 255, 0.12);
    border-color: #00f5ff;
    color: #00f5ff;
    font-weight: 600;
}
.set-panel { display: none; }
.set-panel.active { display: block; }
/* Knee Valgus section */
.valgus-section {
    background: #16213e;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 20px;
    box-shadow: 0 0 20px rgba(0,0,0,0.3);
    position: relative;
}
.valgus-section > h2 {
    font-size: 1rem;
    font-weight: 500;
    color: #ccc;
    margin-bottom: 8px;
    letter-spacing: 1px;
}
.valgus-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
}
.valgus-chart {
    background: #1a1a2e;
    border: 1px solid rgba(255,255,255,0.04);
    border-radius: 8px;
    padding: 8px;
}
.valgus-chart h3 {
    font-size: 0.8rem;
    font-weight: 500;
    color: #888;
    margin: 0 0 4px 4px;
    letter-spacing: 0.5px;
}
.valgus-chart.delta {
    grid-column: 1 / -1;
}
.valgus-readout {
    position: absolute;
    top: 12px;
    right: 16px;
    z-index: 10;
    background: rgba(22,33,62,0.92);
    border: 1px solid rgba(0,245,255,0.25);
    border-radius: 8px;
    padding: 10px 14px;
    min-width: 170px;
    pointer-events: none;
}
.valgus-readout .readout-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 2px 0;
    font-size: 0.8rem;
}
.valgus-readout .readout-label {
    color: #666;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-size: 0.7rem;
}
.valgus-readout .readout-value {
    font-family: 'SF Mono', 'Fira Code', monospace;
    color: #ccc;
    min-width: 60px;
    text-align: right;
}
.valgus-readout .readout-value.left { color: #00f5ff; }
.valgus-readout .readout-value.right { color: #f44336; }
.valgus-readout .readout-value.delta { color: #bb86fc; }
@media (max-width: 768px) {
    .valgus-grid { grid-template-columns: 1fr; }
    .valgus-chart.delta { grid-column: auto; }
}
"""

_PLOTLY_LAYOUT_BASE = {
    "paper_bgcolor": "#16213e",
    "plot_bgcolor": "#1a1a2e",
    "font": {"color": "#ccc", "family": "Segoe UI, system-ui, sans-serif", "size": 12},
    "xaxis": {
        "gridcolor": "rgba(255,255,255,0.06)",
        "zerolinecolor": "rgba(255,255,255,0.12)",
        "title": {"text": "Time (s)"},
    },
    "yaxis": {
        "gridcolor": "rgba(255,255,255,0.06)",
        "zerolinecolor": "rgba(255,255,255,0.12)",
    },
    "legend": {"bgcolor": "rgba(0,0,0,0)", "font": {"size": 11}},
    "margin": {"l": 60, "r": 80, "t": 36, "b": 44},
    "hovermode": "x unified",
}


def _render_html(payload: dict, is_session: bool = False) -> str:
    """Build the complete self-contained HTML string."""
    data_json = json.dumps(payload, default=str)
    layout_json = json.dumps(_PLOTLY_LAYOUT_BASE)

    if is_session:
        title = f"Nowva Session Dashboard"
        subtitle = payload.get("session_info", {}).get("exercise", "")
    else:
        sn = payload.get("set_number", 1)
        title = f"Nowva Biomechanics — Set {sn}"
        subtitle = ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>{_CSS}</style>
</head>
<body>
<h1>{title}</h1>
{"<p class='subtitle'>" + subtitle + "</p>" if subtitle else ""}

<div id="app"></div>

<script>
const IS_SESSION = {str(is_session).lower()};
const DATA = {data_json};
const BASE_LAYOUT = {layout_json};

// ---- Helpers ----
function deepCopy(o) {{ return JSON.parse(JSON.stringify(o)); }}

function makeLayout(overrides) {{
    const L = deepCopy(BASE_LAYOUT);
    Object.assign(L, overrides || {{}});
    if (overrides && overrides.xaxis) Object.assign(L.xaxis, overrides.xaxis);
    if (overrides && overrides.yaxis) Object.assign(L.yaxis, overrides.yaxis);
    return L;
}}

function repShapes(markers) {{
    return markers.map(m => ({{
        type: 'line', x0: m.time_s, x1: m.time_s, y0: 0, y1: 1,
        xref: 'x', yref: 'paper',
        line: {{ color: 'rgba(57,255,20,0.35)', width: 1, dash: 'dash' }},
    }}));
}}

function repAnnotations(markers) {{
    return markers.map(m => ({{
        x: m.time_s, y: 1.02, xref: 'x', yref: 'paper',
        text: 'Rep ' + m.rep_number, showarrow: false,
        font: {{ size: 10, color: '#39ff14' }},
    }}));
}}

// ---- Threshold line helpers ----
const THRESH_COLORS = {{
    mild: '#ffeb3b',
    moderate: '#ff9800',
    severe: '#f44336',
}};

function thresholdShapes(thresholds, faultKey, levels) {{
    if (!thresholds || !thresholds[faultKey]) return [];
    const t = thresholds[faultKey];
    return levels.map(([field, label, color]) => ({{
        type: 'line', x0: 0, x1: 1, y0: t[field], y1: t[field],
        xref: 'paper', yref: 'y',
        line: {{ color: color, width: 1.5, dash: 'dot' }},
    }})).filter(s => s.y0 != null);
}}

function thresholdAnnotations(thresholds, faultKey, levels) {{
    if (!thresholds || !thresholds[faultKey]) return [];
    const t = thresholds[faultKey];
    return levels.map(([field, label, color]) => ({{
        x: 1, y: t[field], xref: 'paper', yref: 'y',
        text: label, showarrow: false, xanchor: 'left',
        font: {{ size: 9, color: color }},
        bgcolor: 'rgba(22,33,62,0.85)', borderpad: 2,
    }})).filter(a => a.y != null);
}}

// ---- Fault marker config ----
const FAULT_STYLES = {{
    'knee_valgus':         {{ color: '#f44336', symbol: 'triangle-down', chart: 'valgus-left' }},
    'forward_lean':        {{ color: '#ff9800', symbol: 'diamond',       chart: 'pipeline' }},
    'bilateral_asymmetry': {{ color: '#bb86fc', symbol: 'square',        chart: 'asymmetry' }},
    'heel_rise':           {{ color: '#ffeb3b', symbol: 'star',          chart: 'pipeline' }},
    'depth':               {{ color: '#00bcd4', symbol: 'circle',        chart: 'hip-pos' }},
}};

const SEVERITY_SIZE = {{ 'mild': 8, 'moderate': 11, 'severe': 14 }};

function nearestIdx(timestamps, t) {{
    let best = 0, bestD = Infinity;
    for (let i = 0; i < timestamps.length; i++) {{
        const d = Math.abs(timestamps[i] - t);
        if (d < bestD) {{ bestD = d; best = i; }}
    }}
    return best;
}}

function faultTracesForChart(faultEvents, chartKey, timestamps, signalValues) {{
    const relevant = (faultEvents || []).filter(f => {{
        const s = FAULT_STYLES[f.fault_type];
        return s && s.chart === chartKey;
    }});
    if (relevant.length === 0) return [];
    const groups = {{}};
    relevant.forEach(f => {{
        if (!groups[f.fault_type]) groups[f.fault_type] = [];
        groups[f.fault_type].push(f);
    }});
    const traces = [];
    Object.entries(groups).forEach(([faultType, events]) => {{
        const style = FAULT_STYLES[faultType];
        const xs = [], ys = [], texts = [], sizes = [];
        events.forEach(e => {{
            xs.push(e.time_s);
            const idx = nearestIdx(timestamps, e.time_s);
            ys.push(signalValues ? signalValues[idx] : 0);
            texts.push(e.severity.toUpperCase() + ': ' + e.message + ' (Rep ' + e.rep_number + ')');
            sizes.push(SEVERITY_SIZE[e.severity] || 10);
        }});
        traces.push({{
            x: xs, y: ys, mode: 'markers',
            marker: {{ symbol: style.symbol, color: style.color, size: sizes,
                      line: {{ color: '#fff', width: 1 }} }},
            name: faultType.replace(/_/g, ' ') + ' fault',
            text: texts, hoverinfo: 'text', showlegend: true,
        }});
    }});
    return traces;
}}

function faultAnnotations(faultEvents, chartKey, timestamps, signalValues) {{
    const relevant = (faultEvents || []).filter(f => {{
        const s = FAULT_STYLES[f.fault_type];
        return s && s.chart === chartKey;
    }});
    const offsets = [30, -35, 45, -50, 60, -65];
    return relevant.map((f, idx) => {{
        const style = FAULT_STYLES[f.fault_type];
        const i = nearestIdx(timestamps, f.time_s);
        const yVal = signalValues ? signalValues[i] : 0;
        return {{
            x: f.time_s, y: yVal, xref: 'x', yref: 'y',
            text: f.severity.charAt(0).toUpperCase(),
            showarrow: true, arrowhead: 2, arrowsize: 1, arrowwidth: 1.5,
            arrowcolor: style.color,
            ax: 0, ay: offsets[idx % offsets.length],
            font: {{ size: 9, color: style.color }},
            bgcolor: 'rgba(22,33,62,0.9)',
            bordercolor: style.color, borderpad: 2,
        }};
    }});
}}

function hoverText(ts, vals, derivs, valUnit, derivUnit) {{
    const out = [];
    for (let i = 0; i < ts.length; i++) {{
        const v = vals[i] != null ? vals[i].toFixed(1) : '-';
        const d = derivs[i] != null ? derivs[i].toFixed(2) : '-';
        out.push(v + ' ' + valUnit + '  |  rate: ' + d + ' ' + derivUnit);
    }}
    return out;
}}

// ---- Valgus readout helpers ----
function updateValgusReadout(prefix, idx, ts, leftData, rightFlipped, deltaData) {{
    const el = (s) => document.getElementById(prefix + '-valgus-' + s);
    const t = el('time'), l = el('val-l'), r = el('val-r'), d = el('val-d');
    if (t) t.textContent = ts[idx].toFixed(2) + 's';
    if (l) l.textContent = leftData[idx].toFixed(1) + '\u00b0';
    if (r) r.textContent = rightFlipped[idx].toFixed(1) + '\u00b0';
    if (d) d.textContent = deltaData[idx].toFixed(1) + '\u00b0';
}}

function clearValgusReadout(prefix) {{
    ['time', 'val-l', 'val-r', 'val-d'].forEach(s => {{
        const el = document.getElementById(prefix + '-valgus-' + s);
        if (el) el.textContent = '--';
    }});
}}

// ---- Chart builders ----
function chartHipPosition(setD, divId) {{
    const traces = [{{
        x: setD.timestamps, y: setD.hip_position_cm,
        text: hoverText(setD.timestamps, setD.hip_position_cm, setD.d_hip_position_cm_s, 'cm', 'cm/s'),
        hoverinfo: 'x+text', mode: 'lines',
        line: {{ color: '#00f5ff', width: 2 }},
        name: 'Hip Height (rel. ankle)',
    }}];
    const layout = makeLayout({{
        yaxis: {{ title: {{ text: 'Hip Height (cm)' }}, autorange: 'reversed',
                  gridcolor: 'rgba(255,255,255,0.06)', zerolinecolor: 'rgba(255,255,255,0.12)' }},
        shapes: repShapes(setD.rep_markers),
        annotations: [...repAnnotations(setD.rep_markers),
                       ...faultAnnotations(setD.fault_events, 'hip-pos', setD.timestamps, setD.hip_position_cm)],
    }});
    const fTraces = faultTracesForChart(setD.fault_events, 'hip-pos', setD.timestamps, setD.hip_position_cm);
    Plotly.newPlot(divId, [...traces, ...fTraces], layout, {{ responsive: true }});
}}

function chartHipVelocity(setD, divId) {{
    const negVel = setD.hip_velocity_cm_s.map(v => -v);
    const negAcc = setD.d_hip_velocity_cm_s2.map(v => -v);
    const traces = [{{
        x: setD.timestamps, y: negVel,
        text: hoverText(setD.timestamps, negVel, negAcc, 'cm/s', 'cm/s²'),
        hoverinfo: 'x+text', mode: 'lines',
        line: {{ color: '#ff00ff', width: 2 }},
        name: 'Hip Velocity',
    }}];
    const layout = makeLayout({{
        yaxis: {{ title: {{ text: 'Velocity (cm/s)' }},
                  gridcolor: 'rgba(255,255,255,0.06)', zerolinecolor: 'rgba(255,255,255,0.12)' }},
        shapes: [
            ...repShapes(setD.rep_markers),
            {{ type: 'line', x0: 0, x1: 1, y0: 0, y1: 0,
               xref: 'paper', yref: 'y',
               line: {{ color: 'rgba(255,255,255,0.3)', width: 1 }} }},
        ],
        annotations: repAnnotations(setD.rep_markers),
    }});
    Plotly.newPlot(divId, traces, layout, {{ responsive: true }});
}}

function chartJointAngles(setD, divId) {{
    const traces = [
        {{
            x: setD.timestamps, y: setD.knee_angle_deg,
            text: hoverText(setD.timestamps, setD.knee_angle_deg, setD.d_knee_angle_deg_s, '°', '°/s'),
            hoverinfo: 'x+text', mode: 'lines',
            line: {{ color: '#00f5ff', width: 2 }}, name: 'Knee Angle',
        }},
        {{
            x: setD.timestamps, y: setD.hip_angle_deg,
            text: hoverText(setD.timestamps, setD.hip_angle_deg, setD.d_hip_angle_deg_s, '°', '°/s'),
            hoverinfo: 'x+text', mode: 'lines',
            line: {{ color: '#ff00ff', width: 2 }}, name: 'Hip Flexion',
        }},
        {{
            x: setD.timestamps, y: setD.trunk_angle_deg,
            text: hoverText(setD.timestamps, setD.trunk_angle_deg, setD.d_trunk_angle_deg_s, '°', '°/s'),
            hoverinfo: 'x+text', mode: 'lines',
            line: {{ color: '#39ff14', width: 2 }}, name: 'Trunk Lean',
        }},
    ];
    const layout = makeLayout({{
        yaxis: {{ title: {{ text: 'Angle (°)' }},
                  gridcolor: 'rgba(255,255,255,0.06)', zerolinecolor: 'rgba(255,255,255,0.12)' }},
        shapes: repShapes(setD.rep_markers),
        annotations: repAnnotations(setD.rep_markers),
    }});
    Plotly.newPlot(divId, traces, layout, {{ responsive: true }});
}}

function chartPipelineAngles(setD, divId) {{
    if (!setD.pipeline_knee_flexion_deg || setD.pipeline_knee_flexion_deg.length === 0) {{
        document.getElementById(divId).parentElement.style.display = 'none';
        return;
    }}
    const traces = [
        {{
            x: setD.timestamps, y: setD.pipeline_knee_flexion_deg,
            text: hoverText(setD.timestamps, setD.pipeline_knee_flexion_deg, setD.d_pipeline_knee_deg_s, '°', '°/s'),
            hoverinfo: 'x+text', mode: 'lines',
            line: {{ color: '#00f5ff', width: 2 }}, name: 'Knee (IK)',
        }},
        {{
            x: setD.timestamps, y: setD.pipeline_hip_flexion_deg,
            text: hoverText(setD.timestamps, setD.pipeline_hip_flexion_deg, setD.d_pipeline_hip_deg_s, '°', '°/s'),
            hoverinfo: 'x+text', mode: 'lines',
            line: {{ color: '#ff00ff', width: 2 }}, name: 'Hip (IK)',
        }},
        {{
            x: setD.timestamps, y: setD.pipeline_trunk_flexion_deg,
            text: hoverText(setD.timestamps, setD.pipeline_trunk_flexion_deg, setD.d_pipeline_trunk_deg_s, '°', '°/s'),
            hoverinfo: 'x+text', mode: 'lines',
            line: {{ color: '#39ff14', width: 2 }}, name: 'Trunk (IK)',
        }},
    ];
    const depthLevels = [
        ['parallel_threshold', 'Deep Squat', '#00bcd4'],
        ['half_threshold', 'Parallel', '#0097a7'],
        ['quarter_threshold', 'Half Squat', '#00697a'],
    ];
    const forwardLeanLevels = [
        ['mild', 'Lean Mild', THRESH_COLORS.mild],
        ['moderate', 'Lean Mod', THRESH_COLORS.moderate],
        ['severe', 'Lean Severe', THRESH_COLORS.severe],
    ];
    const layout = makeLayout({{
        yaxis: {{ title: {{ text: 'Angle (°)' }},
                  gridcolor: 'rgba(255,255,255,0.06)', zerolinecolor: 'rgba(255,255,255,0.12)' }},
        shapes: [
            ...repShapes(setD.rep_markers),
            ...thresholdShapes(setD.thresholds, 'depth', depthLevels),
            ...thresholdShapes(setD.thresholds, 'forward_lean', forwardLeanLevels),
        ],
        annotations: [...repAnnotations(setD.rep_markers),
                       ...faultAnnotations(setD.fault_events, 'pipeline', setD.timestamps, setD.pipeline_trunk_flexion_deg),
                       ...thresholdAnnotations(setD.thresholds, 'depth', depthLevels),
                       ...thresholdAnnotations(setD.thresholds, 'forward_lean', forwardLeanLevels)],
    }});
    const fTraces = faultTracesForChart(setD.fault_events, 'pipeline', setD.timestamps, setD.pipeline_trunk_flexion_deg);
    Plotly.newPlot(divId, [...traces, ...fTraces], layout, {{ responsive: true }});
}}

function chartKneeValgusSection(setD, prefix) {{
    const section = document.getElementById(prefix + '-valgus-section');
    // Prefer real valgus data; fall back to hip adduction proxy
    const hasValgus = setD.knee_valgus_l_deg && setD.knee_valgus_l_deg.length > 0;
    const hasAdduction = setD.hip_adduction_l_deg && setD.hip_adduction_l_deg.length > 0;
    if (!hasValgus && !hasAdduction) {{
        if (section) section.style.display = 'none';
        return;
    }}

    // --- Derived data ---
    const ts = setD.timestamps;
    const leftData = hasValgus ? setD.knee_valgus_l_deg : setD.hip_adduction_l_deg;
    const rightRaw = hasValgus ? setD.knee_valgus_r_deg : setD.hip_adduction_r_deg;
    const rightFlipped = rightRaw.map(v => -v);
    const deltaData = leftData.map((v, i) => Math.abs(v) - Math.abs(rightRaw[i]));
    const leftDeriv = hasValgus ? setD.d_knee_valgus_l_deg_s : setD.d_hip_adduction_l_deg_s;
    const rightDerivFlipped = (hasValgus
        ? (setD.d_knee_valgus_r_deg_s || [])
        : (setD.d_hip_adduction_r_deg_s || [])).map(v => -v);
    const metricLabel = hasValgus ? 'Valgus' : 'Adduction (proxy)';

    const valgusLevels = [
        ['mild', 'Valgus Mild', THRESH_COLORS.mild],
        ['moderate', 'Valgus Mod', THRESH_COLORS.moderate],
        ['severe', 'Valgus Severe', THRESH_COLORS.severe],
    ];

    const zeroLine = {{ type: 'line', x0: 0, x1: 1, y0: 0, y1: 0,
        xref: 'paper', yref: 'y',
        line: {{ color: 'rgba(255,255,255,0.3)', width: 1 }} }};

    const bandShapes = (setD.valgus_band != null) ? [
        {{ type: 'rect', x0: 0, x1: 1, y0: 0, y1: setD.valgus_band,
           xref: 'paper', yref: 'y',
           fillcolor: 'rgba(0,245,255,0.08)', line: {{ width: 0 }} }},
        {{ type: 'line', x0: 0, x1: 1, y0: setD.valgus_band, y1: setD.valgus_band,
           xref: 'paper', yref: 'y',
           line: {{ color: 'rgba(0,245,255,0.3)', width: 1, dash: 'dash' }} }},
    ] : [];

    // --- KASR trace (secondary axis, shown on left chart only) ---
    const kasrData = setD.knee_ankle_sep_ratio || [];

    // --- Left Knee chart ---
    const leftTraces = [{{
        x: ts, y: leftData,
        text: hoverText(ts, leftData, leftDeriv, '\u00b0', '\u00b0/s'),
        hoverinfo: 'x+text', mode: 'lines',
        line: {{ color: '#00f5ff', width: 2 }}, name: 'Left ' + metricLabel,
    }}];
    if (kasrData.length > 0) {{
        leftTraces.push({{
            x: ts, y: kasrData, yaxis: 'y2',
            hoverinfo: 'x+text', mode: 'lines',
            text: kasrData.map(v => 'KASR: ' + v.toFixed(2)),
            line: {{ color: '#4CAF50', width: 1, dash: 'dot' }}, name: 'KASR', opacity: 0.6,
        }});
    }}
    const leftLayout = makeLayout({{
        yaxis: {{ title: {{ text: metricLabel + ' (\u00b0)' }},
                  gridcolor: 'rgba(255,255,255,0.06)', zerolinecolor: 'rgba(255,255,255,0.12)' }},
        yaxis2: {{ title: 'KASR', overlaying: 'y', side: 'right', showgrid: false,
                   range: [0, 2], tickfont: {{ size: 10, color: '#4CAF50' }} }},
        margin: {{ l: 50, r: 50, t: 24, b: 36 }},
        shapes: [
            ...repShapes(setD.rep_markers), zeroLine, ...bandShapes,
            ...thresholdShapes(setD.thresholds, 'knee_valgus', valgusLevels),
        ],
        annotations: [...repAnnotations(setD.rep_markers),
                       ...faultAnnotations(setD.fault_events, 'valgus-left', ts, leftData),
                       ...thresholdAnnotations(setD.thresholds, 'knee_valgus', valgusLevels)],
    }});
    const leftFaults = faultTracesForChart(setD.fault_events, 'valgus-left', ts, leftData);
    const leftDiv = prefix + '-valgus-left';
    Plotly.newPlot(leftDiv, [...leftTraces, ...leftFaults], leftLayout, {{ responsive: true }});

    // --- Right Knee chart (flipped) ---
    const rightTraces = [{{
        x: ts, y: rightFlipped,
        text: hoverText(ts, rightFlipped, rightDerivFlipped, '\u00b0', '\u00b0/s'),
        hoverinfo: 'x+text', mode: 'lines',
        line: {{ color: '#f44336', width: 2 }}, name: 'Right ' + metricLabel + ' (flipped)',
    }}];
    const rightLayout = makeLayout({{
        yaxis: {{ title: {{ text: metricLabel + ' (\u00b0)' }},
                  gridcolor: 'rgba(255,255,255,0.06)', zerolinecolor: 'rgba(255,255,255,0.12)' }},
        margin: {{ l: 50, r: 50, t: 24, b: 36 }},
        shapes: [
            ...repShapes(setD.rep_markers), zeroLine, ...bandShapes,
            ...thresholdShapes(setD.thresholds, 'knee_valgus', valgusLevels),
        ],
        annotations: [...repAnnotations(setD.rep_markers),
                       ...thresholdAnnotations(setD.thresholds, 'knee_valgus', valgusLevels)],
    }});
    // Map fault events onto the flipped right signal for y-positioning
    const rightFaults = faultTracesForChart(setD.fault_events, 'valgus-left', ts, rightFlipped);
    const rightDiv = prefix + '-valgus-right';
    Plotly.newPlot(rightDiv, [...rightTraces, ...rightFaults], rightLayout, {{ responsive: true }});

    // --- Delta chart (L-R imbalance) ---
    const deltaTraces = [{{
        x: ts, y: deltaData,
        hoverinfo: 'x+text', mode: 'lines',
        text: ts.map((t, i) => deltaData[i].toFixed(1) + '\u00b0'),
        line: {{ color: '#bb86fc', width: 1.5 }}, name: 'L \u2212 R Imbalance',
        fill: 'tozeroy',
        fillcolor: 'rgba(187,134,252,0.12)',
    }}];
    const deltaLayout = makeLayout({{
        height: 180,
        yaxis: {{ title: {{ text: 'Imbalance (\u00b0)' }},
                  gridcolor: 'rgba(255,255,255,0.06)', zerolinecolor: 'rgba(255,255,255,0.12)' }},
        margin: {{ l: 50, r: 50, t: 24, b: 36 }},
        shapes: [...repShapes(setD.rep_markers), zeroLine],
        annotations: [...repAnnotations(setD.rep_markers)],
    }});
    const deltaDiv = prefix + '-valgus-delta';
    Plotly.newPlot(deltaDiv, deltaTraces, deltaLayout, {{ responsive: true }});

    // --- Linked crosshairs ---
    const divIds = [leftDiv, rightDiv, deltaDiv];
    const divs = divIds.map(id => document.getElementById(id));
    let hoverLock = false;

    divs.forEach((div, idx) => {{
        div.on('plotly_hover', function(ev) {{
            if (hoverLock) return;
            hoverLock = true;
            const pt = ev.points[0];
            const pi = pt.pointIndex;
            divs.forEach((other, oi) => {{
                if (oi !== idx) {{
                    Plotly.Fx.hover(other, [{{ curveNumber: 0, pointNumber: pi }}]);
                }}
            }});
            updateValgusReadout(prefix, pi, ts, leftData, rightFlipped, deltaData);
            hoverLock = false;
        }});
        div.on('plotly_unhover', function() {{
            if (hoverLock) return;
            hoverLock = true;
            divs.forEach((other, oi) => {{
                if (oi !== idx) Plotly.Fx.unhover(other);
            }});
            clearValgusReadout(prefix);
            hoverLock = false;
        }});
    }});
}}

function chartBilateralAsymmetry(setD, divId) {{
    if (!setD.bilateral_asymmetry_deg || setD.bilateral_asymmetry_deg.length === 0) {{
        document.getElementById(divId).parentElement.style.display = 'none';
        return;
    }}
    const traces = [{{
        x: setD.timestamps, y: setD.bilateral_asymmetry_deg,
        text: hoverText(setD.timestamps, setD.bilateral_asymmetry_deg, setD.d_bilateral_asymmetry_deg_s, '°', '°/s'),
        hoverinfo: 'x+text', mode: 'lines',
        line: {{ color: '#bb86fc', width: 2 }},
        name: 'Bilateral Asymmetry (max of knee/hip)',
    }}];
    const asymLevels = [
        ['mild', 'Asym Mild', THRESH_COLORS.mild],
        ['moderate', 'Asym Mod', THRESH_COLORS.moderate],
        ['severe', 'Asym Severe', THRESH_COLORS.severe],
    ];
    const layout = makeLayout({{
        yaxis: {{ title: {{ text: 'Asymmetry (°)' }},
                  gridcolor: 'rgba(255,255,255,0.06)', zerolinecolor: 'rgba(255,255,255,0.12)' }},
        shapes: [
            ...repShapes(setD.rep_markers),
            {{ type: 'line', x0: 0, x1: 1, y0: 0, y1: 0,
               xref: 'paper', yref: 'y',
               line: {{ color: 'rgba(255,255,255,0.3)', width: 1 }} }},
            ...thresholdShapes(setD.thresholds, 'bilateral_asymmetry', asymLevels),
        ],
        annotations: [...repAnnotations(setD.rep_markers),
                       ...faultAnnotations(setD.fault_events, 'asymmetry', setD.timestamps, setD.bilateral_asymmetry_deg),
                       ...thresholdAnnotations(setD.thresholds, 'bilateral_asymmetry', asymLevels)],
    }});
    const fTraces = faultTracesForChart(setD.fault_events, 'asymmetry', setD.timestamps, setD.bilateral_asymmetry_deg);
    Plotly.newPlot(divId, [...traces, ...fTraces], layout, {{ responsive: true }});
}}

function chartSegmentation(setD, divId) {{
    const seg = setD.segmentation;
    if (!seg || !seg.reps || seg.reps.length === 0) {{
        document.getElementById(divId).parentElement.style.display = 'none';
        return;
    }}
    const ts = setD.timestamps;
    const pos = setD.hip_position_cm;
    const vel = setD.hip_velocity_cm_s.map(v => -v);  // negate for display

    // Active region shapes
    const activeShapes = seg.reps.map(r => ({{
        type: 'rect',
        x0: ts[r.descent_onset_idx], x1: ts[r.ascent_end_idx],
        y0: 0, y1: 1, xref: 'x', yref: 'paper',
        fillcolor: 'rgba(57,255,20,0.06)', line: {{ width: 0 }},
    }}));

    // Bottom markers
    const bottomX = seg.reps.map(r => ts[r.bottom_idx]);
    const bottomY = seg.reps.map(r => pos[r.bottom_idx]);
    const bottomText = seg.reps.map(r => 'Rep ' + r.rep_number + ' bottom: ' + r.bottom_position_cm.toFixed(1) + ' cm');

    // Standing markers
    const standX = seg.reps.map(r => ts[r.start_idx]);
    const standY = seg.reps.map(r => pos[r.start_idx]);
    const standText = seg.reps.map(r => 'Rep ' + r.rep_number + ' standing: ' + r.standing_position_cm.toFixed(1) + ' cm');

    // Depth annotations
    const depthAnnotations = seg.reps.map(r => ({{
        x: (ts[r.start_idx] + ts[r.bottom_idx]) / 2,
        y: (pos[r.start_idx] + pos[r.bottom_idx]) / 2,
        xref: 'x', yref: 'y',
        text: r.depth_cm.toFixed(1) + ' cm',
        showarrow: false,
        font: {{ size: 10, color: '#aaa' }},
        bgcolor: 'rgba(22,33,62,0.9)', bordercolor: '#555', borderpad: 3,
    }}));

    // Pause annotations
    const pauseAnnotations = [];
    const pauses = (seg.summary && seg.summary.pauses) || [];
    pauses.forEach(p => {{
        const ri = p.after_rep - 1;
        if (ri < seg.reps.length - 1) {{
            const t1 = seg.reps[ri].ascent_end_time_s;
            const t2 = seg.reps[ri + 1].descent_onset_time_s;
            pauseAnnotations.push({{
                x: (t1 + t2) / 2, y: 0.5, xref: 'x', yref: 'paper',
                text: 'Pause ' + p.rest_s.toFixed(1) + 's',
                showarrow: false,
                font: {{ size: 10, color: '#bb86fc' }},
                bgcolor: 'rgba(187,134,252,0.12)', bordercolor: '#bb86fc', borderpad: 3,
            }});
        }}
    }});

    // Position subplot
    const tracePos = {{
        x: ts, y: pos, mode: 'lines',
        line: {{ color: '#00f5ff', width: 2 }}, name: 'Hip Position',
        hovertemplate: '%{{x:.2f}}s<br>%{{y:.1f}} cm<extra></extra>',
    }};
    const traceBottom = {{
        x: bottomX, y: bottomY, mode: 'markers',
        marker: {{ symbol: 'triangle-down', size: 10, color: '#f44336' }},
        name: 'Squat Bottom', text: bottomText, hoverinfo: 'text',
    }};
    const traceStand = {{
        x: standX, y: standY, mode: 'markers',
        marker: {{ symbol: 'triangle-up', size: 8, color: '#448aff' }},
        name: 'Standing Peak', text: standText, hoverinfo: 'text',
    }};

    // Velocity subplot (negated)
    const traceVel = {{
        x: ts, y: vel, mode: 'lines', xaxis: 'x2', yaxis: 'y2',
        line: {{ color: '#ff9800', width: 1.5 }}, name: 'Hip Velocity',
        hovertemplate: '%{{x:.2f}}s<br>%{{y:.1f}} cm/s<extra></extra>',
    }};
    const traceVelBottom = {{
        x: bottomX, y: seg.reps.map(r => -setD.hip_velocity_cm_s[r.bottom_idx]),
        mode: 'markers', xaxis: 'x2', yaxis: 'y2',
        marker: {{ symbol: 'circle', size: 5, color: '#f44336' }},
        name: 'Bottom (vel)', showlegend: false,
        hoverinfo: 'skip',
    }};

    const segLayout = {{
        ...deepCopy(BASE_LAYOUT),
        grid: {{ rows: 2, columns: 1, subplots: [['xy'], ['x2y2']], roworder: 'top to bottom' }},
        xaxis: {{ ...BASE_LAYOUT.xaxis, title: '', gridcolor: 'rgba(255,255,255,0.06)' }},
        yaxis: {{
            title: {{ text: 'Position (cm)' }}, autorange: 'reversed',
            gridcolor: 'rgba(255,255,255,0.06)', zerolinecolor: 'rgba(255,255,255,0.12)',
            domain: [0.38, 1],
        }},
        xaxis2: {{ ...BASE_LAYOUT.xaxis, anchor: 'y2', gridcolor: 'rgba(255,255,255,0.06)' }},
        yaxis2: {{
            title: {{ text: 'Velocity (cm/s)' }}, anchor: 'x2',
            gridcolor: 'rgba(255,255,255,0.06)', zerolinecolor: 'rgba(255,255,255,0.12)',
            domain: [0, 0.32],
        }},
        shapes: activeShapes,
        annotations: [...depthAnnotations, ...pauseAnnotations],
        height: 520,
        margin: {{ l: 60, r: 20, t: 36, b: 44 }},
    }};

    Plotly.newPlot(divId, [tracePos, traceBottom, traceStand, traceVel, traceVelBottom], segLayout, {{ responsive: true }});
}}

// ---- Summary cards ----
function summaryCardsHTML(setD) {{
    const seg = setD.segmentation || {{}};
    const s = seg.summary || {{}};
    const nReps = seg.total_reps || 0;
    const avgDepth = s.avg_depth_cm != null ? s.avg_depth_cm.toFixed(1) + ' cm' : '-';
    const depthCons = s.depth_consistency != null ? (s.depth_consistency * 100).toFixed(0) + '%' : '-';
    const tempoCons = s.tempo_consistency != null ? (s.tempo_consistency * 100).toFixed(0) + '%' : '-';
    const avgDescent = s.avg_descent_time_s != null ? s.avg_descent_time_s.toFixed(2) + 's' : '-';
    const avgAscent = s.avg_ascent_time_s != null ? s.avg_ascent_time_s.toFixed(2) + 's' : '-';
    return `
        <div class="stat-card"><div class="label">Reps</div><div class="value">${{nReps}}</div></div>
        <div class="stat-card"><div class="label">Avg Depth</div><div class="value magenta">${{avgDepth}}</div></div>
        <div class="stat-card"><div class="label">Depth Consistency</div><div class="value lime">${{depthCons}}</div></div>
        <div class="stat-card"><div class="label">Tempo Consistency</div><div class="value orange">${{tempoCons}}</div></div>
        <div class="stat-card"><div class="label">Avg Descent</div><div class="value">${{avgDescent}}</div></div>
        <div class="stat-card"><div class="label">Avg Ascent</div><div class="value magenta">${{avgAscent}}</div></div>
    `;
}}

// ---- Rep table ----
function repTableHTML(setD) {{
    const reps = (setD.segmentation && setD.segmentation.reps) || [];
    if (reps.length === 0) return '';
    let rows = reps.map(r => `<tr>
        <td>${{r.rep_number}}</td>
        <td>${{r.depth_cm.toFixed(1)}}</td>
        <td>${{r.avg_descent_velocity_cm_s.toFixed(1)}}</td>
        <td>${{r.avg_ascent_velocity_cm_s.toFixed(1)}}</td>
        <td>${{r.descent_time_s.toFixed(2)}}</td>
        <td>${{r.ascent_time_s.toFixed(2)}}</td>
        <td>${{r.time_at_bottom_s.toFixed(2)}}</td>
        <td>${{r.rest_at_top_s != null ? r.rest_at_top_s.toFixed(2) : '-'}}</td>
    </tr>`).join('');
    return `<table>
        <thead><tr>
            <th>Rep</th><th>Depth (cm)</th><th>Avg Down (cm/s)</th><th>Avg Up (cm/s)</th>
            <th>Descent (s)</th><th>Ascent (s)</th><th>Bottom (s)</th><th>Rest (s)</th>
        </tr></thead>
        <tbody>${{rows}}</tbody>
    </table>`;
}}

// ---- Render a single set ----
function renderSet(setD, prefix) {{
    const app = document.getElementById(prefix);
    app.innerHTML = `
        <div class="cards-row" id="${{prefix}}-cards"></div>
        <div class="chart-card"><h2>Hip Position</h2><div id="${{prefix}}-hip-pos"></div></div>
        <div class="chart-card"><h2>Hip Velocity</h2><div id="${{prefix}}-hip-vel"></div></div>
        <div class="chart-card"><h2>Joint Angles (3D Geometry)</h2><div id="${{prefix}}-angles"></div></div>
        <div class="chart-card"><h2>Pipeline Angles (IK + One Euro)</h2><div id="${{prefix}}-pipeline"></div></div>
        <div class="valgus-section" id="${{prefix}}-valgus-section">
            <h2>Knee Valgus</h2>
            <div class="valgus-readout" id="${{prefix}}-valgus-readout">
                <div class="readout-row"><span class="readout-label">Time</span><span class="readout-value" id="${{prefix}}-valgus-time">--</span></div>
                <div class="readout-row"><span class="readout-label">Left</span><span class="readout-value left" id="${{prefix}}-valgus-val-l">--</span></div>
                <div class="readout-row"><span class="readout-label">Right</span><span class="readout-value right" id="${{prefix}}-valgus-val-r">--</span></div>
                <div class="readout-row"><span class="readout-label">&Delta;</span><span class="readout-value delta" id="${{prefix}}-valgus-val-d">--</span></div>
            </div>
            <div class="valgus-grid">
                <div class="valgus-chart"><h3>Left Knee</h3><div id="${{prefix}}-valgus-left"></div></div>
                <div class="valgus-chart"><h3>Right Knee (flipped)</h3><div id="${{prefix}}-valgus-right"></div></div>
                <div class="valgus-chart delta"><h3>L &minus; R Imbalance</h3><div id="${{prefix}}-valgus-delta"></div></div>
            </div>
        </div>
        <div class="chart-card"><h2>Bilateral Asymmetry</h2><div id="${{prefix}}-asymmetry"></div></div>
        <div class="chart-card"><h2>Rep Segmentation</h2><div id="${{prefix}}-seg"></div></div>
        <div class="rep-table-wrap"><h2>Per-Rep Metrics</h2><div id="${{prefix}}-table"></div></div>
    `;
    document.getElementById(prefix + '-cards').innerHTML = summaryCardsHTML(setD);
    chartHipPosition(setD, prefix + '-hip-pos');
    chartHipVelocity(setD, prefix + '-hip-vel');
    chartJointAngles(setD, prefix + '-angles');
    chartPipelineAngles(setD, prefix + '-pipeline');
    chartKneeValgusSection(setD, prefix);
    chartBilateralAsymmetry(setD, prefix + '-asymmetry');
    chartSegmentation(setD, prefix + '-seg');
    document.getElementById(prefix + '-table').innerHTML = repTableHTML(setD);
}}

// ---- Init ----
function init() {{
    const app = document.getElementById('app');
    if (IS_SESSION) {{
        const sets = DATA.sets;
        // Tab bar
        let tabHTML = '<div class="tab-bar" id="tab-bar">';
        sets.forEach((s, i) => {{
            tabHTML += '<button class="tab-btn' + (i === 0 ? ' active' : '') + '" onclick="switchTab(' + i + ')">Set ' + s.set_number + '</button>';
        }});
        tabHTML += '</div>';
        // Panels
        let panelsHTML = '';
        sets.forEach((s, i) => {{
            panelsHTML += '<div class="set-panel' + (i === 0 ? ' active' : '') + '" id="panel-' + i + '"></div>';
        }});
        app.innerHTML = tabHTML + panelsHTML;
        // Render first set immediately
        renderSet(sets[0], 'panel-0');
        // Lazy-render others on tab switch
        window._rendered = {{ 0: true }};
        window.switchTab = function(idx) {{
            document.querySelectorAll('.tab-btn').forEach((b, i) => b.classList.toggle('active', i === idx));
            document.querySelectorAll('.set-panel').forEach((p, i) => p.classList.toggle('active', i === idx));
            if (!window._rendered[idx]) {{
                renderSet(sets[idx], 'panel-' + idx);
                window._rendered[idx] = true;
            }}
            // Trigger Plotly resize for newly visible charts
            setTimeout(() => window.dispatchEvent(new Event('resize')), 50);
        }};
    }} else {{
        app.innerHTML = '<div id="single-set"></div>';
        renderSet(DATA, 'single-set');
    }}
}}

document.addEventListener('DOMContentLoaded', init);
</script>
</body>
</html>"""


