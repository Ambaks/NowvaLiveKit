"""Cross-validate Python FK/costs/whatif against the JS KinodynamicsSolver.

Generates a known skeleton + q vector, runs both implementations, compares
results within 0.01 rad per DOF (the spec tolerance).
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from biomechanics.skeleton.definition import SkeletonModel
from biomechanics.skeleton.anthropometry import scale_skeleton
from biomechanics.optimizer.ik import _fk_jac, _build_descendants
from biomechanics.optimizer.costs import combined_cost_and_grad, _support_bounds
from biomechanics.optimizer.whatif import whatif_solve
from biomechanics.optimizer.temporal import gaussian_taper

ROOT = Path(__file__).parent.parent.parent.parent
SCRIPT = ROOT / "scripts" / "visualize_video_squats.py"


def _make_skeleton():
    return scale_skeleton(1.78, 80.0)


def _squat_q(skeleton, phase=0.7):
    q = skeleton.neutral_q()
    q[skeleton.dof_index("L_hip", "rx")] = np.radians(100 * phase)
    q[skeleton.dof_index("R_hip", "rx")] = np.radians(100 * phase)
    q[skeleton.dof_index("L_knee", "rx")] = np.radians(120 * phase)
    q[skeleton.dof_index("R_knee", "rx")] = np.radians(120 * phase)
    q[skeleton.dof_index("L_ankle", "rx")] = np.radians(30 * phase)
    q[skeleton.dof_index("R_ankle", "rx")] = np.radians(30 * phase)
    q[skeleton.dof_index("trunk", "rx")] = np.radians(40 * phase)
    return q


def _serialize_skeleton(skeleton):
    """Mirrors serialize_kinodynamics_state's skeleton_def output."""
    joints_ser = []
    for jd in skeleton.joints:
        joints_ser.append({
            "name": jd.name,
            "parent": jd.parent,
            "offset": [float(x) for x in jd.offset],
            "dof_axes": list(jd.dof_axes),
            "limits": [[float(lo), float(hi)] for lo, hi in jd.limits],
        })
    dof_map = {}
    for (joint, axis), idx in skeleton._dof_map.items():
        dof_map[f"{joint}.{axis}"] = idx
    bounds = skeleton.bounds()
    return {
        "joints": joints_ser,
        "n_dof": skeleton.n_dof,
        "n_joints": skeleton.n_joints,
        "dof_map": dof_map,
        "bounds": [[float(lo), float(hi)] for lo, hi in bounds],
        "joint_masses": [float(x) for x in skeleton.joint_masses],
    }


def _run_js(js_code):
    """Run JS code via Node.js and return parsed JSON output."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".mjs", delete=False) as f:
        f.write(js_code)
        f.flush()
        result = subprocess.run(
            ["node", f.name],
            capture_output=True, text=True, timeout=10
        )
    if result.returncode != 0:
        pytest.fail(f"JS execution failed:\n{result.stderr}")
    return json.loads(result.stdout)


def _extract_kino_solver_js():
    """Extract the KinodynamicsSolver class from the build_html f-string."""
    text = SCRIPT.read_text()
    start = text.find("class KinodynamicsSolver {{")
    end = text.find("\n// ======== KINODYNAMICS HELPERS", start)
    if start < 0 or end < 0:
        pytest.skip("KinodynamicsSolver not found in script")
    js = text[start:end]
    # Un-escape f-string doubled braces
    js = js.replace("{{", "{").replace("}}", "}")
    return js


# ── FK cross-validation ─────────────────────────────────────────────────

class TestFKCrossValidation:
    def test_fk_positions_match(self):
        skeleton = _make_skeleton()
        q = _squat_q(skeleton, 0.7)
        desc = _build_descendants(skeleton)
        pos_py, _ = _fk_jac(skeleton, q, desc)

        skel_json = json.dumps(_serialize_skeleton(skeleton))
        q_json = json.dumps(q.tolist())
        solver_js = _extract_kino_solver_js()

        js_code = f"""
{solver_js}

const skelDef = {skel_json};
const q = new Float64Array({q_json});
const solver = new KinodynamicsSolver(skelDef);
const {{pos}} = solver.fk(q);
const result = [];
for (let i = 0; i < solver.nj; i++) result.push([pos[i*3], pos[i*3+1], pos[i*3+2]]);
console.log(JSON.stringify(result));
"""
        pos_js = np.array(_run_js(js_code))

        np.testing.assert_allclose(pos_js, pos_py, atol=1e-6,
            err_msg="FK positions diverge between Python and JS")


# ── Cost cross-validation ────────────────────────────────────────────────

class TestCostCrossValidation:
    def test_combined_cost_matches(self):
        skeleton = _make_skeleton()
        q = _squat_q(skeleton, 0.7)
        q_ref = _squat_q(skeleton, 0.5)
        desc = _build_descendants(skeleton)
        pos0, _ = _fk_jac(skeleton, q, desc)
        sup = _support_bounds(skeleton, pos0)
        weights = {
            "pose_deviation": 1.0,
            "torque_proxy": 0.5,
            "load_over_midfoot": 2.0,
            "knee_tracking": 1.0,
            "balance_margin": 0.5,
        }

        cost_py, grad_py = combined_cost_and_grad(
            skeleton, q, q_ref, weights, sup, desc
        )

        skel_json = json.dumps(_serialize_skeleton(skeleton))
        q_json = json.dumps(q.tolist())
        qref_json = json.dumps(q_ref.tolist())
        sup_json = json.dumps(list(sup))
        w_json = json.dumps(weights)
        solver_js = _extract_kino_solver_js()

        js_code = f"""
{solver_js}

const skelDef = {skel_json};
const solver = new KinodynamicsSolver(skelDef);
const q = new Float64Array({q_json});
const qRef = new Float64Array({qref_json});
const sup = {sup_json};
const weights = {w_json};
const result = solver.combinedCostAndGrad(q, qRef, weights, sup, null);
console.log(JSON.stringify({{cost: result.cost, grad: Array.from(result.grad)}}));
"""
        js_result = _run_js(js_code)

        assert abs(js_result["cost"] - cost_py) < 1e-4, \
            f"Cost diverges: Python={cost_py:.6f}, JS={js_result['cost']:.6f}"
        np.testing.assert_allclose(
            np.array(js_result["grad"]), grad_py, atol=1e-4,
            err_msg="Gradient diverges between Python and JS"
        )


# ── Whatif solve cross-validation ────────────────────────────────────────

class TestWhatifCrossValidation:
    def test_js_whatif_feasible(self):
        """JS solver (browser fallback) produces a feasible solution:
        feet stay rooted and perturbed DOFs move toward target.

        The primary solver is Python SLSQP via PyWebView; the JS solver
        is a penalty-method fallback that may find a different local
        minimum, so we validate feasibility rather than exact match.
        """
        skeleton = _make_skeleton()
        q_fitted = _squat_q(skeleton, 0.7)
        perturbation = {"L_hip.rx": 0.09, "R_hip.rx": 0.09}

        skel_json = json.dumps(_serialize_skeleton(skeleton))
        q_json = json.dumps(q_fitted.tolist())
        pert_json = json.dumps(perturbation)
        solver_js = _extract_kino_solver_js()

        js_code = f"""
{solver_js}

const skelDef = {skel_json};
const solver = new KinodynamicsSolver(skelDef);
const qFitted = new Float64Array({q_json});
const pert = {pert_json};
const qCorr = solver.whatifSolve(qFitted, pert);
const {{pos}} = solver.fk(qCorr);
const {{pos: pos0}} = solver.fk(qFitted);
const la = solver._lAnkle, ra = solver._rAnkle;
const feetErr = Math.sqrt(
    [0,1,2].reduce((s,d) =>
        s + (pos[la*3+d]-pos0[la*3+d])**2 + (pos[ra*3+d]-pos0[ra*3+d])**2, 0));
const hipIdx = solver.dofMap['L_hip.rx'];
const hipDelta = qCorr[hipIdx] - qFitted[hipIdx];
console.log(JSON.stringify({{feetErr, hipDelta, q: Array.from(qCorr)}}));
"""
        result = _run_js(js_code)

        assert result["feetErr"] < 0.01, \
            f"Feet drift {result['feetErr']:.4f} m (tolerance: 0.01 m)"

        assert result["hipDelta"] > 0.01, \
            f"Perturbed hip DOF barely moved: delta={result['hipDelta']:.4f} rad"

    def test_python_whatif_exact_constraints(self):
        """Python SLSQP solver (primary, used via PyWebView) maintains
        exact feet constraint and applies perturbation."""
        skeleton = _make_skeleton()
        q_fitted = _squat_q(skeleton, 0.7)
        perturbation = {"L_hip.rx": 0.09, "R_hip.rx": 0.09}

        q_py = whatif_solve(skeleton, q_fitted, perturbation)

        desc = _build_descendants(skeleton)
        pos_fitted, _ = _fk_jac(skeleton, q_fitted, desc)
        pos_corrected, _ = _fk_jac(skeleton, q_py, desc)
        lai = skeleton.joint_index("L_ankle")
        rai = skeleton.joint_index("R_ankle")
        feet_err = np.sqrt(
            np.sum((pos_corrected[lai] - pos_fitted[lai]) ** 2)
            + np.sum((pos_corrected[rai] - pos_fitted[rai]) ** 2)
        )
        assert feet_err < 1e-6, f"Feet error: {feet_err:.2e}"

        hip_idx = skeleton.dof_index("L_hip", "rx")
        hip_delta = q_py[hip_idx] - q_fitted[hip_idx]
        assert hip_delta > 0.05, \
            f"Hip perturbation not applied: delta={hip_delta:.4f} rad"


# ── Temporal taper cross-validation ──────────────────────────────────────

class TestTemporalTaperCrossValidation:
    def test_taper_matches(self):
        n_frames = 60
        bottom = 30
        taper_py = gaussian_taper(n_frames, bottom)

        solver_js = _extract_kino_solver_js()
        js_code = f"""
{solver_js}

const taper = KinodynamicsSolver.gaussianTaper({n_frames}, {bottom});
console.log(JSON.stringify(Array.from(taper)));
"""
        taper_js = np.array(_run_js(js_code))

        np.testing.assert_allclose(taper_js, taper_py, atol=1e-10,
            err_msg="Gaussian taper diverges between Python and JS")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
