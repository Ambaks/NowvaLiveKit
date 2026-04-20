#!/usr/bin/env python3
"""
Process a squat video through the biomechanics pipeline and generate
an interactive 3D replay HTML file.

Flow:
  1. Run pose estimation (MediaPipe) on every frame → 3D keypoints + joint angles
  2. Detect reps via the rep counter
  3. Use rep 1 as baseline → compute fault thresholds
  4. Generate an HTML viewer that replays reps 2-5 in a loop with fault overlays

Usage:
    python scripts/visualize_video_squats.py path/to/squat_video.mp4
    python scripts/visualize_video_squats.py video.mp4 --output my_replay.html
"""

import argparse
import json
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import cv2
import numpy as np

from biomechanics.pose.mediapipe_fallback import MediaPipePoseEstimator
from biomechanics.kinematics.analytical_ik import AnalyticalIKSolver
from biomechanics.faults.rep_counter import RepCounter, RepCounterConfig
from biomechanics.utils.filters import JointAngleFilter
from biomechanics.utils.derivatives import DerivativeTracker


def process_video(video_path: str):
    """Process video and return per-frame data + rep boundaries."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"ERROR: Could not open video: {video_path}")
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"Video: {video_path}")
    print(f"  {total_frames} frames @ {fps:.1f} fps ({total_frames/fps:.1f}s)")

    pose = MediaPipePoseEstimator(model_complexity=1)
    ik = AnalyticalIKSolver()
    angle_filter = JointAngleFilter(min_cutoff=1.0, beta=0.007)
    deriv_tracker = DerivativeTracker(smoothing_alpha=0.3)
    rep_counter = RepCounter(RepCounterConfig(
        entry_knee_angle=30.0,
        exit_knee_angle=25.0,
        min_depth_knee_angle=95.0,
        min_rep_duration_frames=15,
    ))

    frames_data = []  # per-frame: {kpts_3d, angles_dict, frame_idx}
    reps = []         # list of RepData
    rep_boundaries = []  # (start_frame, end_frame) per rep
    current_rep_start = None

    frame_idx = 0
    prev_in_rep = False

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        _, skeleton_3d = pose.estimate_both(frame)

        if skeleton_3d is not None:
            raw_angles = ik.solve(skeleton_3d)
            # Inject a monotonic timestamp so the derivative tracker gets valid dt
            raw_angles.timestamp = frame_idx / fps
            angles = angle_filter.filter_angles(raw_angles)
            angles.timestamp = raw_angles.timestamp
            derivs = deriv_tracker.update(angles)

            rep_data, _ = rep_counter.update(angles, derivs)

            # Track rep boundaries
            in_rep = rep_counter.in_rep
            if in_rep and not prev_in_rep:
                current_rep_start = frame_idx
            if not in_rep and prev_in_rep and current_rep_start is not None:
                rep_boundaries.append((current_rep_start, frame_idx))
                current_rep_start = None
            prev_in_rep = in_rep

            if rep_data is not None:
                reps.append(rep_data)
                print(f"  Rep {rep_data.rep_number}: depth={rep_data.max_depth_angle:.1f}°  "
                      f"frames {rep_boundaries[-1][0]}-{rep_boundaries[-1][1]}")

            # Convert 3D keypoints to viewer coords
            # MediaPipe world: Y=down, X=left, Z=forward (toward camera)
            # Viewer:          X=forward, Y=up, Z=lateral(right=+Z)
            kpts_mp = skeleton_3d.to_numpy()[:17]  # (17, 3) — only COCO-17
            kpts_vis = np.zeros_like(kpts_mp)
            kpts_vis[:, 0] = kpts_mp[:, 2]   # vis_x = mp_z (forward)
            kpts_vis[:, 1] = -kpts_mp[:, 1]  # vis_y = -mp_y (up)
            kpts_vis[:, 2] = -kpts_mp[:, 0]  # vis_z = -mp_x (right)

            frames_data.append({
                "kpts": kpts_vis.tolist(),
                "angles": {
                    "knee_flex": angles.avg_knee_flexion,
                    "trunk_flexion": angles.trunk_flexion,
                    "knee_valgus_l": angles.knee_valgus_l,
                    "knee_valgus_r": angles.knee_valgus_r,
                    "dorsi_l": angles.ankle_dorsiflexion_l,
                    "dorsi_r": angles.ankle_dorsiflexion_r,
                    "hip_flex_l": angles.hip_flexion_l,
                    "hip_flex_r": angles.hip_flexion_r,
                },
                "frame": frame_idx,
            })
        else:
            frames_data.append(None)

        frame_idx += 1
        if frame_idx % 100 == 0:
            print(f"  Processed {frame_idx}/{total_frames} frames...")

    cap.release()
    pose.release()

    print(f"\nDone: {len(reps)} reps detected across {frame_idx} frames")
    return frames_data, reps, rep_boundaries, fps


def ground_and_center(rep_frames):
    """Translate keypoints so ankles sit at y=0 and skeleton is centered at x/z=0."""
    for frame in rep_frames:
        if frame is None:
            continue
        kpts = np.array(frame["kpts"])
        # Ground: min ankle y → 0
        ankle_y = min(kpts[15][1], kpts[16][1])
        kpts[:, 1] -= ankle_y
        # Center: midpoint of hips at x=0, z=0
        hip_mid_x = (kpts[11][0] + kpts[12][0]) / 2
        hip_mid_z = (kpts[11][2] + kpts[12][2]) / 2
        kpts[:, 0] -= hip_mid_x
        kpts[:, 2] -= hip_mid_z
        frame["kpts"] = kpts.tolist()


def compute_baseline(rep_frames):
    """Compute baseline peaks from a single rep's frames (mirrors squat.py apply_baseline)."""
    peak_trunk_offset = 0.0
    peak_valgus = 0.0
    peak_knee_flex = 0.0
    peak_dorsi = 0.0

    for f in rep_frames:
        if f is None:
            continue
        a = f["angles"]
        trunk_offset = 180 - a["trunk_flexion"]
        peak_trunk_offset = max(peak_trunk_offset, trunk_offset)
        peak_valgus = max(peak_valgus, abs(a["knee_valgus_l"]), abs(a["knee_valgus_r"]))
        peak_knee_flex = max(peak_knee_flex, a["knee_flex"])
        peak_dorsi = max(peak_dorsi, a["dorsi_l"], a["dorsi_r"])

    return {
        "peakTrunkOffset": round(peak_trunk_offset, 2),
        "peakValgus": round(peak_valgus, 2),
        "peakKneeFlex": round(peak_knee_flex, 2),
        "peakDorsi": round(peak_dorsi, 2),
        "leanThresholds": {
            "mild": round(peak_trunk_offset + 10, 1),
            "moderate": round(peak_trunk_offset + 15, 1),
            "severe": round(peak_trunk_offset + 20, 1),
        },
        "valgusThresholds": {
            "mild": round(peak_valgus + 5, 1),
            "moderate": round(peak_valgus + 10, 1),
            "severe": round(peak_valgus + 15, 1),
        },
    }


def build_html(baseline, replay_reps_data, fps):
    """Generate the HTML replay viewer."""
    data_json = json.dumps({
        "baseline": baseline,
        "reps": replay_reps_data,
        "fps": fps,
    })

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Squat Video Replay</title>
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
    background: #0a0a1a;
    color: #e0e0e0;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    overflow: hidden;
    height: 100vh;
    display: flex;
}}
#scene-container {{ flex: 1; position: relative; }}
#controls {{
    width: 360px;
    background: #12122a;
    border-left: 1px solid #2a2a4a;
    overflow-y: auto;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 14px;
}}
h1 {{ font-size: 18px; font-weight: 600; color: #a0a0ff; margin-bottom: 4px; }}
.section {{
    background: #1a1a35;
    border: 1px solid #2a2a4a;
    border-radius: 8px;
    padding: 14px;
}}
.section-title {{
    font-size: 13px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 1px; margin-bottom: 10px; display: flex;
    align-items: center; gap: 8px;
}}
.section-title .dot {{
    width: 8px; height: 8px; border-radius: 50%; display: inline-block;
}}
.baseline .section-title {{ color: #2ecc71; }}
.baseline .dot {{ background: #2ecc71; }}
.angles .section-title {{ color: #a0a0ff; }}
.angles .dot {{ background: #a0a0ff; }}
.faults .section-title {{ color: #ff6b6b; }}
.faults .dot {{ background: #ff6b6b; }}
.playback .section-title {{ color: #ffd93d; }}
.playback .dot {{ background: #ffd93d; }}

.mono {{ font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; line-height: 1.8; }}
.lbl {{ color: #888; }}
.val {{ color: #a0a0ff; }}
.val-green {{ color: #2ecc71; font-weight: 600; }}
.val-red {{ color: #ff6b6b; font-weight: 600; }}

.severity-indicator {{
    font-size: 11px; padding: 2px 8px; border-radius: 10px;
    margin-left: 4px; font-weight: 600;
}}
.sev-none {{ background: #1a3a2a; color: #2ecc71; }}
.sev-mild {{ background: #3a3a1a; color: #f1c40f; }}
.sev-moderate {{ background: #3a2a1a; color: #e67e22; }}
.sev-severe {{ background: #3a1a1a; color: #e74c3c; }}

.btn {{
    padding: 10px 16px; border: none; border-radius: 6px;
    font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.2s;
}}
.btn-primary {{ background: linear-gradient(135deg, #6060ff, #4040cc); color: white; }}
.btn-primary:hover {{ background: linear-gradient(135deg, #7070ff, #5050dd); }}
.btn-row {{ display: flex; gap: 8px; align-items: center; }}

.anim-controls {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }}
.anim-controls button {{
    width: 32px; height: 32px; border-radius: 50%;
    border: 1px solid #3a3a5a; background: #2a2a4a; color: #e0e0e0;
    font-size: 14px; cursor: pointer; display: flex;
    align-items: center; justify-content: center;
}}
.anim-controls button:hover {{ background: #3a3a5a; }}
.slider-row {{
    display: flex; align-items: center; gap: 8px; margin-bottom: 8px;
}}
.slider-row label {{ font-size: 12px; color: #b0b0cc; min-width: 80px; flex-shrink: 0; }}
.slider-row input[type="range"] {{
    flex: 1; -webkit-appearance: none; height: 4px;
    background: #2a2a4a; border-radius: 2px; outline: none;
}}
.slider-row input[type="range"]::-webkit-slider-thumb {{
    -webkit-appearance: none; width: 14px; height: 14px;
    border-radius: 50%; background: #6060ff; cursor: pointer;
}}
.slider-row .value {{
    font-size: 12px; color: #8080cc; min-width: 42px; text-align: right;
    font-family: 'SF Mono', 'Fira Code', monospace;
}}

#info-overlay {{
    position: absolute; top: 12px; left: 12px;
    background: rgba(18, 18, 42, 0.85); border: 1px solid #2a2a4a;
    border-radius: 8px; padding: 10px 14px; font-size: 12px;
    font-family: 'SF Mono', 'Fira Code', monospace; line-height: 1.6;
    pointer-events: none;
}}
#info-overlay .lbl {{ color: #888; }}
#info-overlay .val {{ color: #a0a0ff; }}

#ground-label {{
    position: absolute; bottom: 12px; left: 12px;
    font-size: 11px; color: #555; pointer-events: none;
}}

.rep-btn {{
    padding: 6px 14px; border: 1px solid #3a3a5a; border-radius: 6px;
    background: #2a2a4a; color: #b0b0cc; font-size: 12px; font-weight: 600;
    cursor: pointer; transition: all 0.2s;
}}
.rep-btn:hover {{ background: #3a3a5a; }}
.rep-btn.active {{ background: #4040cc; color: white; border-color: #6060ff; }}
</style>
</head>
<body>
<div id="scene-container">
    <canvas id="three-canvas"></canvas>
    <div id="info-overlay"></div>
    <div id="ground-label">Drag to orbit | Scroll to zoom</div>
</div>
<div id="controls">
    <h1>Squat Video Replay</h1>

    <div class="section baseline">
        <div class="section-title"><span class="dot"></span> Baseline (Rep 1)</div>
        <div class="mono" id="baseline-info"></div>
    </div>

    <div class="section playback">
        <div class="section-title"><span class="dot"></span> Playback</div>
        <div class="btn-row" id="rep-buttons" style="flex-wrap:wrap; margin-bottom:10px;"></div>
        <div class="anim-controls">
            <button id="play-btn" title="Play/Pause">&#9646;&#9646;</button>
            <input type="range" id="frame-scrubber" min="0" max="100" value="0" step="1">
            <span class="value" id="frame-val" style="min-width:50px;">0/0</span>
        </div>
        <div class="slider-row">
            <label>Speed</label>
            <input type="range" id="speed-slider" min="0.1" max="3.0" value="1.0" step="0.1">
            <span class="value" id="speed-val">1.0x</span>
        </div>
    </div>

    <div class="section angles">
        <div class="section-title"><span class="dot"></span> Live Angles</div>
        <div class="mono" id="angles-info"></div>
    </div>

    <div class="section faults">
        <div class="section-title"><span class="dot"></span> Fault Classification</div>
        <div class="mono" id="faults-info"></div>
    </div>
</div>

<script type="module">
import * as THREE from 'three';
import {{ OrbitControls }} from 'three/addons/controls/OrbitControls.js';

const DATA = {data_json};

const BONE_CONNECTIONS = [
    [0, 1], [0, 2], [1, 3], [2, 4],
    [5, 6], [5, 7], [7, 9], [6, 8], [8, 10],
    [5, 11], [6, 12], [11, 12],
    [11, 13], [13, 15], [12, 14], [14, 16],
];

const baseline = DATA.baseline;
const LEAN_THRESHOLDS = baseline.leanThresholds;
const VALGUS_THRESHOLDS = baseline.valgusThresholds;

// Display baseline
document.getElementById('baseline-info').innerHTML = `
    <span class="lbl">Peak trunk offset:</span> <span class="val-green">${{baseline.peakTrunkOffset.toFixed(1)}}°</span><br>
    <span class="lbl">Peak knee flex:</span> <span class="val-green">${{baseline.peakKneeFlex.toFixed(1)}}°</span><br>
    <span class="lbl">Peak dorsiflexion:</span> <span class="val-green">${{baseline.peakDorsi.toFixed(1)}}°</span><br>
    <span class="lbl">Baseline valgus:</span> <span class="val-green">${{baseline.peakValgus.toFixed(1)}}°</span><br>
    <hr style="border-color:#2a2a4a; margin:6px 0">
    <span class="lbl">Lean thresholds:</span> <span class="val">${{LEAN_THRESHOLDS.mild}}° / ${{LEAN_THRESHOLDS.moderate}}° / ${{LEAN_THRESHOLDS.severe}}°</span><br>
    <span class="lbl">Valgus thresholds:</span> <span class="val">${{VALGUS_THRESHOLDS.mild}}° / ${{VALGUS_THRESHOLDS.moderate}}° / ${{VALGUS_THRESHOLDS.severe}}°</span>
`;

// Three.js setup
const canvas = document.getElementById('three-canvas');
const container = document.getElementById('scene-container');
const renderer = new THREE.WebGLRenderer({{ canvas, antialias: true }});
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setClearColor(0x0a0a1a);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 50);
camera.position.set(2.0, 1.0, 2.0);
camera.lookAt(0, 0.7, 0);

const controls = new OrbitControls(camera, canvas);
controls.target.set(0, 0.7, 0);
controls.enableDamping = true;
controls.dampingFactor = 0.08;

scene.add(new THREE.AmbientLight(0x404060, 0.6));
const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
dirLight.position.set(3, 5, 3);
scene.add(dirLight);
scene.add(new THREE.GridHelper(4, 20, 0x222244, 0x1a1a30));

const matNormal = new THREE.MeshPhongMaterial({{ color: 0x40e0a0, emissive: 0x103020 }});
const matFault = new THREE.MeshPhongMaterial({{ color: 0xff4444, emissive: 0x401010 }});
const matBone = new THREE.MeshPhongMaterial({{ color: 0x3090d0, emissive: 0x102030 }});
const matBoneFault = new THREE.MeshPhongMaterial({{ color: 0xff6666, emissive: 0x301010 }});

const sphereGeo = new THREE.SphereGeometry(0.018, 12, 8);
const jointMeshes = [];
const jointStates = [];
for (let i = 0; i < 17; i++) {{
    const m = new THREE.Mesh(sphereGeo, matNormal.clone());
    scene.add(m);
    jointMeshes.push(m);
    jointStates.push('normal');
}}

const boneMeshes = [];
for (const [a, b] of BONE_CONNECTIONS) {{
    const geo = new THREE.CylinderGeometry(0.006, 0.006, 1, 6);
    geo.translate(0, 0.5, 0);
    const m = new THREE.Mesh(geo, matBone.clone());
    scene.add(m);
    boneMeshes.push({{ mesh: m, a, b }});
}}

// State
let currentRepIdx = 0;
let currentFrame = 0;
let playing = true;
let lastTime = performance.now();
let playbackSpeed = 1.0;

const replayReps = DATA.reps;
const fps = DATA.fps;

// Build rep buttons
const repBtnContainer = document.getElementById('rep-buttons');
const allBtn = document.createElement('button');
allBtn.className = 'rep-btn active';
allBtn.textContent = 'All';
allBtn.dataset.idx = '-1';
repBtnContainer.appendChild(allBtn);

for (let i = 0; i < replayReps.length; i++) {{
    const btn = document.createElement('button');
    btn.className = 'rep-btn';
    btn.textContent = `Rep ${{i + 2}}`;
    btn.dataset.idx = String(i);
    repBtnContainer.appendChild(btn);
}}

let activeRepFilter = -1; // -1 = all

repBtnContainer.addEventListener('click', (e) => {{
    if (!e.target.classList.contains('rep-btn')) return;
    repBtnContainer.querySelectorAll('.rep-btn').forEach(b => b.classList.remove('active'));
    e.target.classList.add('active');
    activeRepFilter = parseInt(e.target.dataset.idx);
    currentRepIdx = activeRepFilter === -1 ? 0 : activeRepFilter;
    currentFrame = 0;
}});

// Scrubber
const scrubber = document.getElementById('frame-scrubber');
const frameVal = document.getElementById('frame-val');
scrubber.addEventListener('input', () => {{
    const rep = replayReps[currentRepIdx];
    if (!rep) return;
    currentFrame = parseInt(scrubber.value);
    playing = false;
    document.getElementById('play-btn').innerHTML = '&#9654;';
}});

document.getElementById('play-btn').addEventListener('click', () => {{
    playing = !playing;
    document.getElementById('play-btn').innerHTML = playing ? '&#9646;&#9646;' : '&#9654;';
}});

const speedSlider = document.getElementById('speed-slider');
const speedVal = document.getElementById('speed-val');
speedSlider.addEventListener('input', () => {{
    playbackSpeed = parseFloat(speedSlider.value);
    speedVal.textContent = playbackSpeed.toFixed(1) + 'x';
}});

// Fault classification
function classifyLean(trunkAngle) {{
    const offset = 180 - trunkAngle;
    if (offset >= LEAN_THRESHOLDS.severe) return 'severe';
    if (offset >= LEAN_THRESHOLDS.moderate) return 'moderate';
    if (offset >= LEAN_THRESHOLDS.mild) return 'mild';
    return 'none';
}}
function classifyValgus(val) {{
    const v = Math.abs(val);
    if (v >= VALGUS_THRESHOLDS.severe) return 'severe';
    if (v >= VALGUS_THRESHOLDS.moderate) return 'moderate';
    if (v >= VALGUS_THRESHOLDS.mild) return 'mild';
    return 'none';
}}
function sevBadge(sev) {{
    return `<span class="severity-indicator sev-${{sev}}">${{sev.toUpperCase()}}</span>`;
}}

// Update skeleton from keypoint data
function updateFromData(frameData) {{
    if (!frameData) return;
    const kpts = frameData.kpts;
    const angles = frameData.angles;

    const leanSev = classifyLean(angles.trunk_flexion);
    const valgusL = classifyValgus(angles.knee_valgus_l);
    const valgusR = classifyValgus(angles.knee_valgus_r);
    const valgusSev = valgusL !== 'none' || valgusR !== 'none'
        ? (valgusL === 'severe' || valgusR === 'severe' ? 'severe'
            : valgusL === 'moderate' || valgusR === 'moderate' ? 'moderate' : 'mild')
        : 'none';

    const faultJoints = new Set();
    if (leanSev !== 'none') [0,1,2,3,4,5,6].forEach(j => faultJoints.add(j));
    if (valgusSev !== 'none') [13,14].forEach(j => faultJoints.add(j));

    for (let i = 0; i < 17; i++) {{
        jointMeshes[i].position.set(kpts[i][0], kpts[i][1], kpts[i][2]);
        const target = faultJoints.has(i) ? 'fault' : 'normal';
        if (target !== jointStates[i]) {{
            jointMeshes[i].material = (target === 'fault' ? matFault : matNormal).clone();
            jointStates[i] = target;
        }}
    }}

    const faultBones = new Set();
    if (leanSev !== 'none') {{ faultBones.add('5-6'); faultBones.add('5-11'); faultBones.add('6-12'); }}
    if (valgusSev !== 'none') {{ faultBones.add('11-13'); faultBones.add('13-15'); faultBones.add('12-14'); faultBones.add('14-16'); }}

    for (const bone of boneMeshes) {{
        const pa = jointMeshes[bone.a].position;
        const pb = jointMeshes[bone.b].position;
        const dir = new THREE.Vector3().subVectors(pb, pa);
        const len = dir.length();
        dir.normalize();
        bone.mesh.position.copy(pa);
        bone.mesh.scale.set(1, len, 1);
        bone.mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
        const key = `${{bone.a}}-${{bone.b}}`;
        bone.mesh.material = faultBones.has(key) ? matBoneFault : matBone;
    }}

    // Angles panel
    const trunkOffset = (180 - angles.trunk_flexion).toFixed(1);
    document.getElementById('angles-info').innerHTML = `
        <span class="lbl">Knee Flex:</span> <span class="val">${{angles.knee_flex.toFixed(1)}}°</span><br>
        <span class="lbl">Trunk Angle:</span> <span class="val">${{angles.trunk_flexion.toFixed(1)}}°</span>
        (offset: ${{trunkOffset}}°)<br>
        <span class="lbl">Valgus L/R:</span> <span class="val">${{angles.knee_valgus_l.toFixed(1)}}° / ${{angles.knee_valgus_r.toFixed(1)}}°</span><br>
        <span class="lbl">Dorsi L/R:</span> <span class="val">${{angles.dorsi_l.toFixed(1)}}° / ${{angles.dorsi_r.toFixed(1)}}°</span><br>
        <span class="lbl">Hip Flex L/R:</span> <span class="val">${{angles.hip_flex_l.toFixed(1)}}° / ${{angles.hip_flex_r.toFixed(1)}}°</span>
    `;

    // Faults panel
    const faults = [];
    if (leanSev !== 'none') faults.push('Forward Lean ' + sevBadge(leanSev));
    if (valgusSev !== 'none') faults.push('Knee Valgus ' + sevBadge(valgusSev));
    document.getElementById('faults-info').innerHTML = faults.length > 0
        ? faults.join('<br>')
        : '<span class="val-green">Clean</span>';

    // Info overlay
    document.getElementById('info-overlay').innerHTML = `
        <span class="lbl">Rep:</span> <span class="val">${{currentRepIdx + 2}}</span>
        <span class="lbl" style="margin-left:12px">Frame:</span> <span class="val">${{currentFrame + 1}}/${{replayReps[currentRepIdx].length}}</span><br>
        <span class="lbl">Knee:</span> <span class="val">${{angles.knee_flex.toFixed(1)}}°</span>
        <span class="lbl" style="margin-left:8px">Trunk:</span> <span class="val">${{angles.trunk_flexion.toFixed(1)}}°</span>
    `;
}}

// Resize
function resize() {{
    const w = container.clientWidth, h = container.clientHeight;
    renderer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
}}
window.addEventListener('resize', resize);
resize();

// Accumulator for sub-frame timing
let frameAccum = 0;

function animate(now) {{
    requestAnimationFrame(animate);
    const dt = (now - lastTime) / 1000;
    lastTime = now;

    if (replayReps.length === 0) return;

    const rep = replayReps[currentRepIdx];
    if (!rep || rep.length === 0) return;

    if (playing) {{
        frameAccum += dt * fps * playbackSpeed;
        while (frameAccum >= 1) {{
            frameAccum -= 1;
            currentFrame++;
            if (currentFrame >= rep.length) {{
                // Advance to next rep or loop
                if (activeRepFilter === -1) {{
                    currentRepIdx = (currentRepIdx + 1) % replayReps.length;
                }}
                currentFrame = 0;
            }}
        }}
    }}

    // Clamp
    if (currentFrame >= rep.length) currentFrame = rep.length - 1;

    scrubber.max = rep.length - 1;
    scrubber.value = currentFrame;
    frameVal.textContent = `${{currentFrame + 1}}/${{rep.length}}`;

    updateFromData(rep[currentFrame]);

    controls.update();
    renderer.render(scene, camera);
}}

requestAnimationFrame(animate);
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Visualize squat video in 3D replay")
    parser.add_argument("video", help="Path to squat video file")
    parser.add_argument("--output", "-o", default=None, help="Output HTML file path")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open in browser")
    args = parser.parse_args()

    video_path = Path(args.video)
    if not video_path.exists():
        print(f"ERROR: Video not found: {video_path}")
        sys.exit(1)

    output_path = Path(args.output) if args.output else video_path.with_suffix(".html")

    frames_data, reps, rep_boundaries, fps = process_video(str(video_path))

    if len(reps) < 2:
        print(f"ERROR: Need at least 2 reps, found {len(reps)}. "
              "Make sure the video has clear squats with full depth.")
        sys.exit(1)

    print(f"\nUsing rep 1 as baseline, replaying reps 2-{len(reps)}...")

    # Extract per-rep frame slices
    rep_frame_slices = []
    for start, end in rep_boundaries:
        rep_slice = [f for f in frames_data[start:end + 1] if f is not None]
        rep_frame_slices.append(rep_slice)

    # Ground and center each rep
    for rep_slice in rep_frame_slices:
        ground_and_center(rep_slice)

    # Rep 1 = baseline
    baseline = compute_baseline(rep_frame_slices[0])
    print(f"  Baseline trunk offset: {baseline['peakTrunkOffset']}°")
    print(f"  Lean thresholds: {baseline['leanThresholds']}")
    print(f"  Valgus thresholds: {baseline['valgusThresholds']}")

    # Reps 2+ = replay data
    replay_reps = rep_frame_slices[1:]

    html = build_html(baseline, replay_reps, fps)
    output_path.write_text(html)
    print(f"\nSaved: {output_path}")

    if not args.no_open:
        webbrowser.open(f"file://{output_path.resolve()}")


if __name__ == "__main__":
    main()
