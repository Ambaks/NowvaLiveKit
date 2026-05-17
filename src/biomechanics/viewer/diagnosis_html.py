"""Build the self-contained HTML/JS for the diagnosis comparison viewer."""

from __future__ import annotations


def build_diagnosis_html() -> str:
    """Return a complete HTML page for the diagnosis comparison viewer.

    Three.js renders two skeletons (observed ghost + corrected accent)
    with a Gaussian-tapered morph loop.  A side panel shows tiered
    diagnosis text with collapsible sections.
    """
    return _HTML


_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Diagnosis Comparison</title>
<script type="importmap">
{
    "imports": {
        "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
        "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
    }
}
</script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    background: #0a0a1a; color: #e0e0e0;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    overflow: hidden; height: 100vh; display: flex;
}

#scene-container {
    flex: 1; position: relative;
}
#scene-container canvas { width: 100%; height: 100%; display: block; }

#controls-overlay {
    position: absolute; bottom: 20px; left: 20px;
    display: flex; gap: 10px; align-items: center; z-index: 10;
}
#controls-overlay button {
    background: rgba(30, 30, 60, 0.85); border: 1px solid #3a3a6a;
    color: #e0e0e0; font-size: 18px; width: 40px; height: 40px;
    border-radius: 8px; cursor: pointer; display: flex;
    align-items: center; justify-content: center;
    transition: background 0.2s;
}
#controls-overlay button:hover { background: rgba(60, 60, 100, 0.9); }

#rep-selector {
    background: rgba(30, 30, 60, 0.85); border: 1px solid #3a3a6a;
    color: #e0e0e0; font-size: 13px; padding: 6px 12px;
    border-radius: 8px; cursor: pointer;
}

.legend {
    position: absolute; top: 20px; left: 20px;
    background: rgba(20, 20, 40, 0.85); border: 1px solid #2a2a4a;
    border-radius: 8px; padding: 12px 16px; font-size: 12px;
    display: flex; flex-direction: column; gap: 6px; z-index: 10;
}
.legend-item { display: flex; align-items: center; gap: 8px; }
.legend-swatch {
    width: 14px; height: 14px; border-radius: 3px; flex-shrink: 0;
}

/* ── Diagnosis Panel ── */
#diagnosis-panel {
    width: 400px; background: #12122a; border-left: 1px solid #2a2a4a;
    overflow-y: auto; padding: 20px; display: flex;
    flex-direction: column; gap: 14px;
}
#diagnosis-panel h1 {
    font-size: 18px; font-weight: 600; color: #a0a0ff; margin-bottom: 2px;
}
.confidence-badge {
    display: inline-block; background: #1a1a35; border: 1px solid #2a2a4a;
    border-radius: 6px; padding: 4px 12px; font-size: 12px;
    font-weight: 600; margin-bottom: 4px;
}

.tier-section {
    background: #1a1a35; border: 1px solid #2a2a4a;
    border-radius: 8px; overflow: hidden;
}
.tier-header {
    padding: 12px 14px; cursor: pointer; display: flex;
    align-items: center; gap: 8px; user-select: none;
    transition: background 0.15s;
}
.tier-header:hover { background: #222245; }
.tier-icon {
    font-size: 10px; transition: transform 0.2s; display: inline-block;
    width: 14px; text-align: center; color: #888;
}
.tier-icon.expanded { transform: rotate(90deg); }
.tier-label { font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.8px; }
.tier-count { font-size: 11px; color: #777; margin-left: auto; }
.tier-body { padding: 0 14px 14px; display: none; }
.tier-body.visible { display: block; }

.tier-section[data-tier="1"] .tier-label { color: #4ecdc4; }
.tier-section[data-tier="2"] .tier-label { color: #f1c40f; }
.tier-section[data-tier="3"] .tier-label { color: #e67e22; }
.tier-section[data-tier="0"] .tier-label { color: #a0a0ff; }

.cause-card {
    background: #0f0f25; border: 1px solid #252545;
    border-radius: 6px; padding: 10px 12px; margin-top: 8px;
}
.cause-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 6px;
}
.cause-id {
    font-size: 13px; font-weight: 600; color: #ccc;
}
.cause-tag {
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.6px; padding: 2px 6px; border-radius: 3px;
    margin-left: 8px;
}
.cause-tag.mobility { background: #1a3a2a; color: #4ecdc4; }
.cause-tag.strength { background: #3a2a1a; color: #e67e22; }

.score-bar-container {
    width: 50px; height: 6px; background: #1a1a35;
    border-radius: 3px; overflow: hidden; flex-shrink: 0;
}
.score-bar-fill { height: 100%; border-radius: 3px; transition: width 0.3s; }

.cause-explanation {
    font-size: 12px; color: #aaa; line-height: 1.5;
}
.cause-evidence {
    font-size: 11px; color: #666; margin-top: 4px;
}

#loading-msg {
    position: absolute; top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    font-size: 14px; color: #777;
}
</style>
</head>
<body>

<div id="scene-container">
    <canvas id="three-canvas"></canvas>
    <div id="loading-msg">Loading diagnosis data...</div>
    <div class="legend" style="display:none" id="legend">
        <div class="legend-item">
            <div class="legend-swatch" style="background:#6688aa; opacity:0.6;"></div>
            <span>Observed (current form)</span>
        </div>
        <div class="legend-item">
            <div class="legend-swatch" style="background:#4ecdc4;"></div>
            <span>Corrected (target form)</span>
        </div>
    </div>
    <div id="controls-overlay" style="display:none">
        <button id="play-pause-btn" title="Play / Pause">&#9654;</button>
        <select id="rep-selector"></select>
    </div>
</div>

<div id="diagnosis-panel">
    <h1>Diagnosis Report</h1>
    <div class="confidence-badge" id="confidence-badge">--</div>
    <div id="tiers-container"></div>
</div>

<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const canvas = document.getElementById('three-canvas');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0a0a1a);

const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 50);
camera.position.set(2.0, 1.0, 2.0);
camera.lookAt(0, 0.6, 0);

const orbitCtrl = new OrbitControls(camera, canvas);
orbitCtrl.target.set(0, 0.6, 0);
orbitCtrl.enableDamping = true;
orbitCtrl.dampingFactor = 0.08;

scene.add(new THREE.AmbientLight(0x404060, 0.6));
const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
dirLight.position.set(3, 5, 3);
scene.add(dirLight);

const gridHelper = new THREE.GridHelper(4, 20, 0x222244, 0x1a1a35);
scene.add(gridHelper);

/* ── Bone connections (19-keypoint COCO) ── */
const BONE_CONNECTIONS = [
    [0, 1], [0, 2], [1, 3], [2, 4],
    [5, 6], [5, 7], [7, 9], [6, 8], [8, 10],
    [5, 11], [6, 12], [11, 12],
    [11, 13], [13, 15], [12, 14], [14, 16],
    [15, 17], [16, 18],
];

/* ── Skeleton builders ── */
function createSkeletonMeshes(jointColor, jointOpacity, boneColor, boneOpacity, boneRadius) {
    const jointMat = new THREE.MeshPhongMaterial({
        color: jointColor, transparent: jointOpacity < 1, opacity: jointOpacity,
    });
    const boneMat = new THREE.MeshPhongMaterial({
        color: boneColor, transparent: boneOpacity < 1, opacity: boneOpacity,
    });
    const joints = [];
    for (let i = 0; i < 19; i++) {
        const mesh = new THREE.Mesh(new THREE.SphereGeometry(0.018, 12, 8), jointMat);
        mesh.visible = false;
        scene.add(mesh);
        joints.push(mesh);
    }
    const bones = [];
    for (let i = 0; i < BONE_CONNECTIONS.length; i++) {
        const mesh = new THREE.Mesh(
            new THREE.CylinderGeometry(boneRadius, boneRadius, 1, 6), boneMat
        );
        mesh.visible = false;
        scene.add(mesh);
        bones.push(mesh);
    }
    return { joints, bones };
}

const observedSkeleton = createSkeletonMeshes(0x6688aa, 0.6, 0x556688, 0.5, 0.004);
const correctedSkeleton = createSkeletonMeshes(0x4ecdc4, 1.0, 0x3aaa9a, 1.0, 0.006);

function updateSkeletonPose(skeleton, keypoints) {
    if (!keypoints || keypoints.length < 19) return;
    for (let i = 0; i < 19; i++) {
        const kp = keypoints[i];
        skeleton.joints[i].position.set(kp[0], kp[1], kp[2]);
        skeleton.joints[i].visible = true;
    }
    for (let bi = 0; bi < BONE_CONNECTIONS.length; bi++) {
        const [start_idx, end_idx] = BONE_CONNECTIONS[bi];
        const start_pos = skeleton.joints[start_idx].position;
        const end_pos = skeleton.joints[end_idx].position;
        const mid = new THREE.Vector3().addVectors(start_pos, end_pos).multiplyScalar(0.5);
        const direction = new THREE.Vector3().subVectors(end_pos, start_pos);
        const bone_length = direction.length();
        skeleton.bones[bi].position.copy(mid);
        skeleton.bones[bi].scale.set(1, bone_length, 1);
        skeleton.bones[bi].quaternion.setFromUnitVectors(
            new THREE.Vector3(0, 1, 0), direction.normalize()
        );
        skeleton.bones[bi].visible = true;
    }
}

/* ── State ── */
let diagnosisData = null;
let currentRepIndex = 0;
let morphFrame = 0;
let morphPlaying = true;
let nMorphFrames = 60;
let lastFrameTime = 0;
const morphFrameInterval = 1000 / 30; // 30 fps

/* ── Controls ── */
const playPauseBtn = document.getElementById('play-pause-btn');
const repSelector = document.getElementById('rep-selector');

playPauseBtn.addEventListener('click', () => {
    morphPlaying = !morphPlaying;
    playPauseBtn.innerHTML = morphPlaying ? '&#9646;&#9646;' : '&#9654;';
});

repSelector.addEventListener('change', () => {
    currentRepIndex = parseInt(repSelector.value, 10);
    morphFrame = 0;
    updateObservedSkeleton();
});

/* ── Diagnosis panel builder ── */
function buildDiagnosisPanel(diagnosis) {
    const confidenceBadge = document.getElementById('confidence-badge');
    const confidence_pct = Math.round(diagnosis.confidence * 100);
    confidenceBadge.textContent = 'Confidence: ' + confidence_pct + '%';

    const tierOrder = ['1', '2', '3', '0'];
    const tiersContainer = document.getElementById('tiers-container');
    tiersContainer.innerHTML = '';

    for (const tierKey of tierOrder) {
        const tier = diagnosis.tiers[tierKey];
        if (!tier) continue;

        const section = document.createElement('div');
        section.className = 'tier-section';
        section.dataset.tier = tierKey;

        const header = document.createElement('div');
        header.className = 'tier-header';

        const icon = document.createElement('span');
        icon.className = 'tier-icon' + (tier.expanded ? ' expanded' : '');
        icon.textContent = '\\u25B6';

        const label = document.createElement('span');
        label.className = 'tier-label';
        label.textContent = tier.label;

        const count = document.createElement('span');
        count.className = 'tier-count';
        count.textContent = '(' + tier.causes.length + ')';

        header.appendChild(icon);
        header.appendChild(label);
        header.appendChild(count);

        const body = document.createElement('div');
        body.className = 'tier-body' + (tier.expanded ? ' visible' : '');

        for (const cause of tier.causes) {
            const card = document.createElement('div');
            card.className = 'cause-card';

            const cardHeader = document.createElement('div');
            cardHeader.className = 'cause-header';

            const causeIdContainer = document.createElement('div');
            causeIdContainer.style.display = 'flex';
            causeIdContainer.style.alignItems = 'center';

            const causeId = document.createElement('span');
            causeId.className = 'cause-id';
            causeId.textContent = cause.cause_id.replace(/_/g, ' ');
            causeIdContainer.appendChild(causeId);

            if (cause.tag) {
                const tag = document.createElement('span');
                tag.className = 'cause-tag ' + cause.tag.toLowerCase();
                tag.textContent = cause.tag;
                causeIdContainer.appendChild(tag);
            }

            const scoreContainer = document.createElement('div');
            scoreContainer.className = 'score-bar-container';
            const scoreFill = document.createElement('div');
            scoreFill.className = 'score-bar-fill';
            const score_pct = Math.round(cause.score * 100);
            scoreFill.style.width = score_pct + '%';
            const score_color = cause.score > 0.5 ? '#4ecdc4'
                : cause.score > 0.3 ? '#f1c40f' : '#e67e22';
            scoreFill.style.background = score_color;
            scoreContainer.appendChild(scoreFill);

            cardHeader.appendChild(causeIdContainer);
            cardHeader.appendChild(scoreContainer);

            const explanation = document.createElement('div');
            explanation.className = 'cause-explanation';
            explanation.textContent = cause.explanation;

            card.appendChild(cardHeader);
            card.appendChild(explanation);

            if (cause.implicated_by && cause.implicated_by.length > 0) {
                const evidence = document.createElement('div');
                evidence.className = 'cause-evidence';
                evidence.textContent = 'Evidence: ' + cause.implicated_by.join(', ').replace(/_/g, ' ');
                card.appendChild(evidence);
            }

            body.appendChild(card);
        }

        header.addEventListener('click', () => {
            const isVisible = body.classList.contains('visible');
            body.classList.toggle('visible');
            icon.classList.toggle('expanded');
        });

        section.appendChild(header);
        section.appendChild(body);
        tiersContainer.appendChild(section);
    }
}

/* ── Initialization ── */
function updateObservedSkeleton() {
    if (!diagnosisData) return;
    const rep = diagnosisData.reps[currentRepIndex];
    if (!rep) return;
    updateSkeletonPose(observedSkeleton, rep.observed_keypoints);
}

async function init() {
    if (!window.pywebview || !window.pywebview.api) {
        document.getElementById('loading-msg').textContent = 'Waiting for pywebview...';
        return;
    }

    diagnosisData = await window.pywebview.api.get_diagnosis_data();
    nMorphFrames = diagnosisData.n_morph_frames || 60;

    const hasReps = diagnosisData.reps && diagnosisData.reps.length > 0;

    if (hasReps) {
        document.getElementById('loading-msg').style.display = 'none';
        document.getElementById('legend').style.display = 'flex';

        const hasAnyCorrection = diagnosisData.reps.some(r => r.has_correction);
        if (hasAnyCorrection) {
            document.getElementById('controls-overlay').style.display = 'flex';
        }

        repSelector.innerHTML = '';
        for (let i = 0; i < diagnosisData.reps.length; i++) {
            const opt = document.createElement('option');
            opt.value = i;
            opt.textContent = 'Rep ' + diagnosisData.reps[i].rep_number;
            repSelector.appendChild(opt);
        }
        if (diagnosisData.reps.length <= 1) {
            repSelector.style.display = 'none';
        }
        updateObservedSkeleton();
    } else {
        const loadMsg = document.getElementById('loading-msg');
        loadMsg.textContent = 'No data available — see diagnosis panel';
        loadMsg.style.color = '#666';
    }

    buildDiagnosisPanel(diagnosisData.diagnosis);
}

/* ── Resize ── */
function onResize() {
    const container = document.getElementById('scene-container');
    const width = container.clientWidth;
    const height = container.clientHeight;
    renderer.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
}
window.addEventListener('resize', onResize);

/* ── Animation loop ── */
function animate(timestamp) {
    requestAnimationFrame(animate);
    orbitCtrl.update();

    if (diagnosisData && diagnosisData.reps.length > 0) {
        if (morphPlaying && (timestamp - lastFrameTime) >= morphFrameInterval) {
            morphFrame = (morphFrame + 1) % nMorphFrames;
            lastFrameTime = timestamp;
        }

        const rep = diagnosisData.reps[currentRepIndex];
        if (rep && rep.morph_frames && rep.has_correction) {
            updateSkeletonPose(correctedSkeleton, rep.morph_frames[morphFrame]);
        }
    }

    renderer.render(scene, camera);
}

/* ── Boot ── */
window.addEventListener('pywebviewready', () => { init(); });
setTimeout(() => {
    if (!diagnosisData) init();
}, 500);

onResize();
requestAnimationFrame(animate);
</script>
</body>
</html>
"""
