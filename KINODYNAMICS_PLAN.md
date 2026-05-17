# Spec Review & Implementation Plan: Kinodynamics Squat Visualizer

## Context

Revamp `scripts/visualize_video_squats.py` with a kinodynamics-based "what-if" correction system. The existing `ConstrainedChainSolver` (embedded JS in the HTML output) will be upgraded to a full soft-cost optimizer running in the browser. Heavy computation (IK, rep detection, fault detection) stays in Python. New code goes inside `src/biomechanics/`, reusing existing modules. Starting with a 20-DOF skeleton model.

---

## Key Decisions

| Decision | Choice |
|----------|--------|
| What-if interaction | Upgrade ConstrainedChainSolver in JS (runs in browser) |
| Code location | Inside `src/biomechanics/` (new `skeleton/` and `optimizer/` submodules) |
| DOF scope | Reduced 20-DOF first, expand later |
| Server/API | **None** — self-contained HTML output, no FastAPI |

---

## Architecture Overview

```
Python (build time)                          Browser (runtime)
─────────────────                            ────────────────
MediaPipe landmarks                          Three.js renderer
       ↓                                           ↑
IK trajectory fit (scipy L-BFGS-B)           Upgraded ConstrainedChainSolver
       ↓                                     - Soft cost formulation (5 terms)
Rep detection (reuse rep_segmenter)          - Temporal taper
       ↓                                     - Motion warping
Fault detection (reuse existing rules)       - Slider-driven perturbations
       ↓                                           ↑
build_html() ──────── embeds JSON ──────────→ Self-contained HTML file
  skeleton_def, q_trajectory,                 (opens with file:// protocol)
  foot_targets, faults, rep boundaries
```

### What Python computes (at capture/generation time):
- IK: Fit 20-DOF joint angle trajectory from MediaPipe landmarks
- Rep detection: Reuse `analysis/rep_segmenter.py`
- Fault detection: Reuse existing rules + add `limited_dorsiflexion` and `bar_drift`
- Skeleton definition + anthropometry: Serialize to JSON for the browser

### What JS computes (in real-time at 60fps in the browser):
- Forward kinematics from joint angles
- What-if optimization: soft-cost solver with perturbation sliders
- Temporal taper: Gaussian weighting centered on bottom frame
- Motion warping: apply tapered corrections across the full rep
- COM tracking, balance visualization, barbell rendering

### Why JS optimizer works here
The current `ConstrainedChainSolver` (lines 1438-1528 of `visualize_video_squats.py`) already solves a constrained kinematic chain analytically in JS at interactive rates. The upgrade path:
1. Keep the analytical chain solver as the **fast core** (closed-form knee-from-depth, trunk-from-COM)
2. Add soft-cost correction terms as **iterative refinement** on top (few iterations of gradient-free optimization)
3. The temporal taper is just multiplication — no optimization needed
4. Motion warping is a loop over frames calling the single-frame solver

This avoids needing scipy.optimize in JS. The analytical solver handles the hard constraints implicitly, and the soft costs are applied as small corrections.

---

## Changes to the Spec

### Remove entirely:
- `biomech-engine/` directory and `pyproject.toml` (use existing project structure)
- FastAPI app, CORS, route registration (`app/main.py`)
- `app/routes/analyze.py` and `app/routes/whatif.py`
- `app/schemas.py` (Pydantic request/response models for API)
- WebSocket lifecycle, session management, cancellation logic
- `concurrently`-based dev script

### Modify:
- **Skeleton**: 20 DOF instead of 34. Drop: head (2), lumbar/thorax split (use single trunk), L/R_foot ry (2), L/R_shoulder (6), L/R_elbow (2). Add these back in a later phase.
- **IK solver**: Keep the L-BFGS-B approach but with 20-DOF bounds. Reduce landmark targets to match (drop wrist/elbow targets, simplify nose target).
- **What-if optimizer**: Rewrite as JS class inheriting from `ConstrainedChainSolver`. Analytical core + iterative soft-cost refinement.
- **Fault detection**: Reuse 4 existing rules, add 2 new ones. Don't rebuild the rule engine.
- **Rep detection**: Reuse `rep_segmenter.py` for post-hoc detection (it already uses scipy.signal.find_peaks on smoothed hip position).

### Keep as-is from spec:
- Core design principles (soft-cost formulation, temporal taper, single load reference, knee tracking)
- Cost term definitions (pose deviation, torque proxy, load-over-midfoot, knee tracking, balance margin)
- Hard constraint logic (feet rooted, COM inside support polygon)
- Temporal taper function
- Anthropometric scaling (de Leva 1996 mass fractions)
- Performance budgets (adjust for JS: target <16ms per frame for 60fps what-if)
- Proportional response test (critical correctness test — port to JS test framework or validate in Python)

---

## 20-DOF Skeleton (Phase 1)

| name      | parent   | offset           | dof            | limits |
|-----------|----------|------------------|----------------|--------|
| pelvis    | None     | [0, 0.95, 0]     | tx,ty,tz,rx,ry,rz | trans unbounded; rx ±45, ry ±90, rz ±30 |
| trunk     | pelvis   | [0, 0.28, 0]     | rx, rz         | rx [-30, 60], rz ±25 |
| L_hip     | pelvis   | [-0.10, 0, 0]    | rx, ry, rz     | rx [-15, 130], ry [-30, 45], rz [-30, 40] |
| R_hip     | pelvis   | [0.10, 0, 0]     | rx, ry, rz     | rx [-15, 130], ry [-45, 30], rz [-40, 30] |
| L_knee    | L_hip    | [0, -0.45, 0]    | rx             | rx [0, 150] |
| R_knee    | R_hip    | [0, -0.45, 0]    | rx             | rx [0, 150] |
| L_ankle   | L_knee   | [0, -0.43, 0]    | rx, ry         | rx [-30, 40], ry [-20, 20] |
| R_ankle   | R_knee   | [0, -0.43, 0]    | rx, ry         | rx [-30, 40], ry [-20, 20] |

**Total: 20 DOF.** Arms, head, and feet are rendered from captured data (not optimized). Trunk combines lumbar + thorax as a single segment.

---

## File Structure (new and modified files)

```
src/biomechanics/
├── skeleton/                    # NEW
│   ├── __init__.py
│   ├── definition.py            # 20-DOF joint hierarchy, SkeletonModel class
│   ├── anthropometry.py         # scale_skeleton(), de Leva mass fractions
│   └── forward_kin.py           # FK, body_com_world(), load_reference_point()
├── optimizer/                   # NEW
│   ├── __init__.py
│   ├── ik.py                    # fit_frame(), fit_trajectory() — scipy L-BFGS-B
│   ├── costs.py                 # Python versions of all 5 cost terms (for testing)
│   ├── temporal.py              # taper()
│   └── whatif.py                # Python what-if solver (for validation/testing only)
├── faults/
│   └── rules/
│       ├── limited_dorsiflexion.py  # NEW rule
│       └── bar_drift.py             # NEW rule
├── analysis/
│   └── rep_segmenter.py         # EXISTING (reuse as-is)
└── utils/
    └── types.py                 # EXISTING (extend with new skeleton types if needed)

scripts/
└── visualize_video_squats.py    # MODIFIED — upgraded build_html() with new JS engine

tests/
└── biomechanics/
    └── optimizer/               # NEW
        ├── fixtures/
        │   ├── synth_clean_squat.json
        │   └── synth_bad_squat.json
        ├── test_fk.py
        ├── test_ik.py
        ├── test_costs.py
        ├── test_proportional_response.py
        ├── test_temporal_taper.py
        └── test_warper.py
```

---

## Prompt Breakdown (6 sessions)

### Prompt 1: Skeleton + FK + Anthropometry + Fixture Generator
**Files:** `src/biomechanics/skeleton/{definition,anthropometry,forward_kin}.py`
**Tests:** `test_fk.py`
**Key deliverable:** `SkeletonModel` class with 20 DOF, FK that returns world transforms, anthropometric scaling, synthetic fixture generator (run FK on known q to produce fake landmarks)

### Prompt 2: IK Solver
**Files:** `src/biomechanics/optimizer/ik.py`
**Tests:** `test_ik.py`
**Key deliverable:** `fit_frame()` and `fit_trajectory()` using scipy L-BFGS-B. Single-camera depth handling. Warm-started trajectory fit with Gaussian smoothing. Perf: <30ms/frame.

### Prompt 3: Fault Detection Upgrades + Rep Integration
**Files:** `src/biomechanics/faults/rules/{limited_dorsiflexion,bar_drift}.py`
**Tests:** Smoke test on synthetic fixtures
**Key deliverable:** 2 new fault rules integrated into existing rule engine. Verify rep_segmenter works with new IK output format.

### Prompt 4: Cost Functions + What-If Optimizer (Python reference)
**Files:** `src/biomechanics/optimizer/{costs,temporal,whatif}.py`
**Tests:** `test_costs.py`, `test_proportional_response.py`, `test_temporal_taper.py`
**Key deliverable:** All 5 cost terms + temporal taper + single-frame what-if solver in Python. This is the reference implementation that the JS port must match. **The proportional response test is the gate.**

### Prompt 5: JS Engine — Port Optimizer to Browser
**Files:** `scripts/visualize_video_squats.py` (the embedded JS section)
**Tests:** Manual browser testing + Python-vs-JS numerical comparison
**Key deliverable:** Upgraded `ConstrainedChainSolver` → `KinodynamicsSolver` class in embedded JS. Includes:
- FK from joint angles
- 5 soft cost terms
- Analytical core + iterative refinement
- Temporal taper + motion warping loop
- All running at interactive rates (<16ms/frame)

### Prompt 6: Full Integration + UI
**Files:** `scripts/visualize_video_squats.py` (build_html, data pipeline)
**Tests:** End-to-end: capture → analyze → HTML → browser → sliders work
**Key deliverable:** Complete pipeline. Python outputs `{skeleton_def, q_trajectory, foot_targets, faults, rep_boundaries}` as JSON. HTML renders with new slider UI (dorsiflexion, stance width, toe angle, knee tracking). Original vs. corrected toggle. Smooth animation.

---

## Verification Plan

1. **Unit tests** (Python): FK positions, IK recovery, cost monotonicity, taper shape, proportional response
2. **Cross-validation** (Python vs JS): Run the same what-if solve in both, compare q_corrected within 0.01 rad per DOF
3. **Browser testing**: Open generated HTML, exercise all sliders, verify:
   - Standing frames unchanged regardless of perturbation magnitude
   - Bottom frame shows proportional corrections
   - Smooth transitions (no popping/snapping)
   - COM stays inside support polygon
   - Barbell/bodyweight modes both work
4. **Performance**: JS solver stays under 16ms/frame for 60fps playback with slider interaction
