#!/usr/bin/env python3
"""Compare bottom-position keypoints between diagnosis and choreographer correction paths.

Loads a session file (same as --diagnose), runs both correction paths, prints
numerical diffs, and opens an HTML overlay viewer to visually confirm they match.

Usage:
    python scripts/demos/compare_bottom_positions.py
    python scripts/demos/compare_bottom_positions.py recordings/my_session.session.json
    python scripts/demos/compare_bottom_positions.py --no-open
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import numpy as np

from biomechanics.diagnosis import HypothesisEngine
from biomechanics.diagnosis.bridge import build_set_features, find_bottom_frame
from biomechanics.diagnosis.demo_builder import build_pose_stack, order_demo_causes
from biomechanics.diagnosis.keypoint_corrector import KeypointCorrector

SESSION_VERSION = 1
LAST_SESSION_POINTER = "last_session.path"

JOINT_NAMES = [
    "nose", "L_eye", "R_eye", "L_ear", "R_ear",
    "L_shoulder", "R_shoulder", "L_elbow", "R_elbow",
    "L_wrist", "R_wrist", "L_hip", "R_hip",
    "L_knee", "R_knee", "L_ankle", "R_ankle",
    "L_foot", "R_foot",
]


def _resolve_last_session(recordings_dir: Path) -> Path | None:
    pointer_path = recordings_dir / LAST_SESSION_POINTER
    if pointer_path.exists():
        pointed = Path(pointer_path.read_text().strip())
        if pointed.exists():
            return pointed
    candidates = sorted(
        recordings_dir.glob("*.session.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _load_session(session_path: Path) -> dict:
    if not session_path.exists():
        print(f"ERROR: Session file not found: {session_path}")
        sys.exit(1)
    try:
        payload = json.loads(session_path.read_text())
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid session JSON: {exc}")
        sys.exit(1)
    if payload.get("version") != SESSION_VERSION:
        print(f"ERROR: Unsupported session version {payload.get('version')}")
        sys.exit(1)
    return payload


def _compare_rep(
    rep_frames: list[dict],
    athlete_params: dict,
    baseline: dict,
    engine: HypothesisEngine,
    anthro: dict,
    rom: dict,
) -> dict:
    bottom_frame = find_bottom_frame(rep_frames)
    observed_kpts = bottom_frame["kpts"]

    single_rep_features = build_set_features([rep_frames], athlete_params, baseline)
    rep_diagnosis = engine.diagnose(single_rep_features)

    corrected_a = KeypointCorrector().correct(
        observed_kpts, rep_diagnosis, anthro=anthro, rom=rom,
    )

    pose_stack = build_pose_stack(
        observed_kpts, rep_diagnosis, anthro=anthro, rom=rom,
    )
    corrected_b = pose_stack[-1].tolist() if pose_stack is not None else None

    all_causes = [c.cause_id for c in rep_diagnosis.immediate_causes]
    ordered_causes = [c.cause_id for c in order_demo_causes(rep_diagnosis)]

    diffs_mm: list[float] = []
    both_corrected = corrected_a is not None and corrected_b is not None
    if both_corrected:
        a_arr = np.array(corrected_a)
        b_arr = np.array(corrected_b)
        diffs_mm = (np.linalg.norm(a_arr - b_arr, axis=1) * 1000.0).tolist()

    return {
        "observed": observed_kpts,
        "diagnosis": corrected_a,
        "choreographer": corrected_b,
        "all_causes": all_causes,
        "ordered_causes": ordered_causes,
        "has_correction": both_corrected,
        "diagnosis_only": corrected_a is not None and corrected_b is None,
        "diffs_mm": [round(d, 4) for d in diffs_mm],
    }


def _print_comparison(results: list[dict]) -> None:
    print("\n" + "=" * 50)
    print("  BOTTOM POSITION COMPARISON")
    print("=" * 50)

    for result in results:
        rep_num = result["rep_number"]
        print(f"\n  Rep {rep_num}:")
        print(f"    Tier-1 causes: {', '.join(result['all_causes']) or 'none'}")
        if result["ordered_causes"] != result["all_causes"]:
            print(f"    Choreographer causes: {', '.join(result['ordered_causes']) or 'none'}")

        if result["diagnosis_only"]:
            print("    Diagnosis corrected but choreographer has no matching causes — skipped")
            continue

        if not result["has_correction"]:
            print("    No corrections applied (no tier-1 causes)")
            continue

        diffs = result["diffs_mm"]
        max_diff = max(diffs)
        max_joint = diffs.index(max_diff)
        print(f"    Max diff: {max_diff:.4f}mm ({JOINT_NAMES[max_joint]})")

        if max_diff > 0.01:
            for j, d in enumerate(diffs):
                if d > 0.001:
                    print(f"      {JOINT_NAMES[j]:>12}: {d:.4f}mm")
        else:
            print("    All joints match within 0.01mm")

    all_diffs = [d for r in results for d in r["diffs_mm"]]
    if all_diffs:
        overall_max = max(all_diffs)
        print(f"\n  Overall max diff: {overall_max:.4f}mm")
        status = "PASS" if overall_max < 0.01 else "MISMATCH"
        print(f"  {status}")
    print()


def _build_html(results: list[dict]) -> str:
    data_json = json.dumps({
        "reps": results,
        "jointNames": JOINT_NAMES,
    })

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Bottom Position Comparison</title>
<script type="importmap">
{{
    "imports": {{
        "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
        "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
    }}
}}
</script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: #0a0a1a; color: #e0e0e0;
    font-family: 'Segoe UI', system-ui, sans-serif;
    overflow: hidden; height: 100vh; display: flex;
}}
#scene {{ flex: 1; position: relative; }}
canvas {{ display: block; width: 100%; height: 100%; }}
#panel {{
    width: 340px; flex-shrink: 0; background: #12122a;
    border-left: 1px solid #2a2a4a; overflow-y: auto;
    padding: 20px; display: flex; flex-direction: column; gap: 14px;
}}
h1 {{ font-size: 16px; color: #a0a0ff; }}
.section {{
    background: #1a1a35; border: 1px solid #2a2a4a;
    border-radius: 8px; padding: 12px;
}}
.section-title {{
    font-size: 12px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 1px; margin-bottom: 8px; color: #888;
}}
.rep-btn {{
    padding: 6px 14px; border: 1px solid #3a3a5a; border-radius: 6px;
    background: #2a2a4a; color: #b0b0cc; font-size: 12px;
    font-weight: 600; cursor: pointer;
}}
.rep-btn:hover {{ background: #3a3a5a; }}
.rep-btn.active {{ background: #4040cc; color: white; border-color: #6060ff; }}
.toggle {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 13px; }}
.toggle input {{ accent-color: #6060ff; }}
.dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; }}
.dot-gray {{ background: #888; }}
.dot-blue {{ background: #4080ff; }}
.dot-green {{ background: #40e0a0; }}
.mono {{
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 11px; line-height: 1.6;
}}
.pass {{ color: #2ecc71; font-weight: 600; }}
.fail {{ color: #ff4444; font-weight: 600; }}
.lbl {{ color: #888; }}
.val {{ color: #a0a0ff; }}
#diff-table {{ width: 100%; border-collapse: collapse; }}
#diff-table td {{ padding: 2px 6px; font-size: 11px; font-family: monospace; }}
#diff-table td:first-child {{ color: #888; }}
#diff-table td:last-child {{ color: #a0a0ff; text-align: right; }}
#diff-table tr.highlight td {{ color: #ff6b6b; }}
#ground-label {{
    position: absolute; bottom: 12px; left: 12px;
    font-size: 11px; color: #555;
}}
</style>
</head>
<body>
<div id="scene">
    <canvas id="c"></canvas>
    <div id="ground-label">Drag to orbit | Scroll to zoom</div>
</div>
<div id="panel">
    <h1>Bottom Position Comparison</h1>

    <div class="section">
        <div class="section-title">Rep</div>
        <div id="rep-btns" style="display:flex; gap:6px; flex-wrap:wrap;"></div>
    </div>

    <div class="section">
        <div class="section-title">Skeletons</div>
        <label class="toggle"><input type="checkbox" id="tog-obs" checked><span class="dot dot-gray"></span> Observed</label>
        <label class="toggle"><input type="checkbox" id="tog-diag" checked><span class="dot dot-blue"></span> Diagnosis (Path A)</label>
        <label class="toggle"><input type="checkbox" id="tog-choreo" checked><span class="dot dot-green"></span> Choreographer (Path B)</label>
    </div>

    <div class="section">
        <div class="section-title">Tier-1 Causes</div>
        <div class="mono" id="causes-info">—</div>
    </div>

    <div class="section">
        <div class="section-title">Keypoint Diff (mm)</div>
        <div id="diff-status" class="mono" style="margin-bottom:6px;"></div>
        <table id="diff-table"></table>
    </div>
</div>

<script type="module">
import * as THREE from 'three';
import {{ OrbitControls }} from 'three/addons/controls/OrbitControls.js';

const DATA = {data_json};
const BONES = [
    [0,1],[0,2],[1,3],[2,4],[0,5],[0,6],
    [5,6],[5,7],[7,9],[6,8],[8,10],
    [5,11],[6,12],[11,12],
    [11,13],[13,15],[12,14],[14,16],
    [15,17],[16,18],
];

const canvas = document.getElementById('c');
const container = document.getElementById('scene');
const renderer = new THREE.WebGLRenderer({{ canvas, antialias: true }});
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setClearColor(0x0a0a1a);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 50);
camera.position.set(2.0, 1.0, 2.0);
const ctrl = new OrbitControls(camera, canvas);
ctrl.target.set(0, 0.7, 0);
ctrl.enableDamping = true;
ctrl.dampingFactor = 0.08;

scene.add(new THREE.AmbientLight(0x404060, 0.6));
const dl = new THREE.DirectionalLight(0xffffff, 0.8);
dl.position.set(3, 5, 3);
scene.add(dl);
scene.add(new THREE.GridHelper(4, 20, 0x222244, 0x1a1a30));

function makeSkeleton(kpts, color, emissive) {{
    const group = new THREE.Group();
    if (!kpts) return group;

    const sGeo = new THREE.SphereGeometry(0.016, 10, 7);
    const mat = new THREE.MeshPhongMaterial({{ color, emissive, emissiveIntensity: 0.3 }});
    for (let i = 0; i < kpts.length; i++) {{
        const m = new THREE.Mesh(sGeo, mat);
        m.position.set(kpts[i][0], kpts[i][1], kpts[i][2]);
        group.add(m);
    }}

    const positions = [];
    for (const [a, b] of BONES) {{
        if (a >= kpts.length || b >= kpts.length) continue;
        positions.push(kpts[a][0], kpts[a][1], kpts[a][2]);
        positions.push(kpts[b][0], kpts[b][1], kpts[b][2]);
    }}
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    group.add(new THREE.LineSegments(geo, new THREE.LineBasicMaterial({{ color, linewidth: 2 }})));

    return group;
}}

const repGroups = [];
for (const rep of DATA.reps) {{
    const obs = makeSkeleton(rep.observed, 0x888888, 0x222222);
    const diag = makeSkeleton(rep.diagnosis, 0x4080ff, 0x102040);
    const choreo = makeSkeleton(rep.choreographer, 0x40e0a0, 0x103020);
    scene.add(obs); scene.add(diag); scene.add(choreo);
    obs.visible = false; diag.visible = false; choreo.visible = false;
    repGroups.push({{ obs, diag, choreo }});
}}

let currentRep = 0;

function showRep(idx) {{
    repGroups.forEach((g, i) => {{
        const active = i === idx;
        g.obs.visible = active && document.getElementById('tog-obs').checked;
        g.diag.visible = active && document.getElementById('tog-diag').checked;
        g.choreo.visible = active && document.getElementById('tog-choreo').checked;
    }});
    currentRep = idx;

    const rep = DATA.reps[idx];
    let causesText = rep.all_causes.length ? rep.all_causes.join(', ') : 'none';
    if (rep.ordered_causes.length !== rep.all_causes.length) {{
        causesText += '\\nChoreographer: ' + (rep.ordered_causes.length ? rep.ordered_causes.join(', ') : 'none');
    }}
    document.getElementById('causes-info').textContent = causesText;

    const diffStatus = document.getElementById('diff-status');
    const diffTable = document.getElementById('diff-table');
    diffTable.innerHTML = '';

    if (!rep.has_correction) {{
        const msg = rep.diagnosis_only
            ? 'Diagnosis corrected but choreographer has no matching causes'
            : 'No corrections for this rep';
        diffStatus.innerHTML = `<span class="lbl">${{msg}}</span>`;
        return;
    }}

    const maxDiff = Math.max(...rep.diffs_mm);
    const pass = maxDiff < 0.01;
    diffStatus.innerHTML = `Max: <span class="${{pass ? 'pass' : 'fail'}}">${{maxDiff.toFixed(4)}}mm</span>`
        + ` <span class="${{pass ? 'pass' : 'fail'}}">${{pass ? 'PASS' : 'MISMATCH'}}</span>`;

    for (let j = 0; j < rep.diffs_mm.length; j++) {{
        const d = rep.diffs_mm[j];
        const tr = document.createElement('tr');
        if (d > 0.01) tr.className = 'highlight';
        tr.innerHTML = `<td>${{DATA.jointNames[j]}}</td><td>${{d.toFixed(4)}}</td>`;
        diffTable.appendChild(tr);
    }}

    document.querySelectorAll('.rep-btn').forEach((b, i) => {{
        b.classList.toggle('active', i === idx);
    }});
}}

const btns = document.getElementById('rep-btns');
DATA.reps.forEach((rep, i) => {{
    const b = document.createElement('button');
    b.className = 'rep-btn';
    b.textContent = `Rep ${{rep.rep_number}}`;
    b.addEventListener('click', () => showRep(i));
    btns.appendChild(b);
}});

['tog-obs', 'tog-diag', 'tog-choreo'].forEach(id => {{
    document.getElementById(id).addEventListener('change', () => showRep(currentRep));
}});

if (DATA.reps.length > 0) showRep(0);

function resize() {{
    const w = container.clientWidth, h = container.clientHeight;
    renderer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
}}
window.addEventListener('resize', resize);
resize();

function animate() {{
    requestAnimationFrame(animate);
    ctrl.update();
    renderer.render(scene, camera);
}}
animate();
</script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare bottom-position keypoints: diagnosis vs choreographer",
    )
    parser.add_argument(
        "session", nargs="?", default=None,
        help="Path to .session.json (default: most recent)",
    )
    parser.add_argument("--no-open", action="store_true", help="Don't open HTML in browser")
    args = parser.parse_args()

    recordings_dir = Path(__file__).parent.parent / "recordings"

    if args.session:
        session_path = Path(args.session)
    else:
        session_path = _resolve_last_session(recordings_dir)
        if session_path is None:
            print("ERROR: No session found. Run visualize_video_squats.py first.")
            sys.exit(1)

    payload = _load_session(session_path)
    replay_reps = payload["replay_reps"]
    athlete_params = payload.get("athlete_params")
    baseline = payload["baseline"]

    if not athlete_params:
        print("ERROR: Session has no athlete params.")
        sys.exit(1)

    print(f"Session: {session_path}")
    print(f"Reps: {len(replay_reps)} replay")

    engine = HypothesisEngine()
    set_features = build_set_features(replay_reps, athlete_params, baseline)

    results = []
    for rep_idx, rep_frames in enumerate(replay_reps):
        result = _compare_rep(
            rep_frames, athlete_params, baseline, engine,
            anthro=set_features.anthropometry,
            rom=set_features.rom,
        )
        result["rep_number"] = rep_idx + 2
        results.append(result)

    _print_comparison(results)

    html = _build_html(results)
    recordings_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = recordings_dir / f"compare_bottom_{timestamp}.html"
    html_path.write_text(html)
    print(f"HTML saved: {html_path}")

    if not args.no_open:
        webbrowser.open(f"file://{html_path.resolve()}")


if __name__ == "__main__":
    main()
