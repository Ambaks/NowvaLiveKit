# Solver Audit — V1 Kinematic Form Solver

## Solver Inventory

The codebase contains a single solver:

| Solver | Method | Scope | File |
|--------|--------|-------|------|
| `whatif_solve` | SLSQP (scipy) | Single-frame | `src/biomechanics/optimizer/whatif.py` |

There are no separate "independent", "compensated", or "kinodynamic" solver variants.
`whatif_solve` optimizes all DOFs jointly in a single pass with hard constraints.

---

## Cost Terms

Defined in `src/biomechanics/optimizer/costs.py`:

| Cost Term | Classification | Default Weight | Description |
|-----------|---------------|----------------|-------------|
| `pose_deviation` | KINEMATIC | 1.0 | Quadratic penalty on deviation from reference q (per-DOF weighting for locked perturbations) |
| `torque_proxy` | DYNAMIC | 0.5 | Horizontal moment-arms at 6 major joints (ankles, knees, hips) — minimizes gravity-resisting torque |
| `load_over_midfoot` | STATIC_BALANCE | 2.0 | Trunk (load proxy) aligned over midfoot in the xz plane |
| `knee_tracking` | KINEMATIC | 1.0 | Knees track ankles in the frontal plane (prevents varus/valgus drift) |
| `balance_margin` | STATIC_BALANCE | 0.5 | Soft barrier when COM approaches support-polygon edge |

---

## V1 Cost Configuration

Decision rule: KEEP geometric/balance terms, DROP anything force/momentum/inverse-dynamics.

| Cost Term | V1 Status | V1 Weight | Rationale |
|-----------|-----------|-----------|-----------|
| `pose_deviation` | KEEP | 1.0 | Pure kinematic regularization |
| `torque_proxy` | DROP | 0.0 | Dynamic term (moment-arm minimization) — requires force model |
| `load_over_midfoot` | KEEP | 2.0 | Geometric vertical load path — no dynamics needed |
| `knee_tracking` | KEEP | 1.0 | Frontal-plane geometry |
| `balance_margin` | KEEP | 0.5 | COM containment — static geometry |

V1 cost weights passed to `whatif_solve`:
```python
V1_COST_WEIGHTS = {
    "torque_proxy": 0.0,
    # All others use DEFAULT_COST_WEIGHTS values
}
```

---

## Hard Constraints (always active)

1. **Feet rooted**: L and R ankle world positions pinned to baseline (or offset by `foot_target_delta`)
2. **COM in support polygon**: Center of mass stays within rectangular bounds extended ±5cm from ankle positions

These are equality/inequality constraints in SLSQP, not soft costs. They cannot be "weighted" — they either hold or the solver reports infeasibility.

---

## Foot Rotation Contract

**Question**: Does `whatif_solve` accept angular foot rotation (toe-out delta)?

**Answer**: YES — via the perturbation dict, not via `foot_target_delta`.

The ankle joint has 2 DOF:
- `L_ankle.rx` / `R_ankle.rx` — dorsiflexion
- `L_ankle.ry` / `R_ankle.ry` — rotation (toe-out/toe-in)

Toe-out corrections are applied as:
```python
perturbation = {"L_ankle.ry": +delta_rad, "R_ankle.ry": -delta_rad}
```

The `foot_target_delta` parameter is **translational only**: `[dLx, dLy, dLz, dRx, dRy, dRz]` (meters).
It shifts the pinned ankle positions but does not rotate the foot.

`delta_widen_foot_angle()` in `src/biomechanics/diagnosis/graph/parameter_deltas.py` already uses `L_ankle.ry` / `R_ankle.ry` — no approximation or workaround needed for V1.

---

## Why This Solver for V1

`whatif_solve` is the correct V1 choice because:
1. It's single-frame — matches the "correct the bottom position" use case
2. With `torque_proxy=0.0`, all remaining costs are purely kinematic or static-geometric
3. Hard constraints preserve physical plausibility (feet planted, COM stable)
4. It already accepts the exact perturbation format produced by `DiagnosisResult.combined_perturbation`
5. No force plate, ground reaction force, or inertial data required
