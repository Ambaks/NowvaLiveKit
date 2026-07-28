// Choreographer state machine for the coaching-demo viewer.
// Pure logic — no THREE.js / DOM. The host injects rendering callbacks,
// so the same module runs in the browser page and under node's test runner.

export const IDLE = 'idle';
export const MORPH_IN = 'morph_in';
export const CUE_LOOP = 'cue_loop';
export const SETTLE = 'settle';
export const FINAL_HOLD = 'final_hold';
export const MORPH_OUT = 'morph_out';

export const DEFAULT_TIMING = {
    morphIn: 0.8,
    morphOut: 0.8,
    yoyoTravel: 1.2,
    yoyoHold: 0.25,
    settle: 0.4,
    finalHold: 1.0,
};

// Poses carry 19 joints when captured before heel tracking, 21 with heels.
// The real count comes from the payload in init().
const DEFAULT_JOINT_COUNT = 19;

const HIP_L = 11, HIP_R = 12;
const KNEE_L = 13, KNEE_R = 14;
const ANKLE_L = 15, ANKLE_R = 16;
const FOOT_L = 17, FOOT_R = 18;
const HEEL_L = 19, HEEL_R = 20;

const BONE_PAIRS = [
    [5, 7], [7, 9],     // L arm
    [6, 8], [8, 10],    // R arm
    [5, 6],              // shoulders
    [HIP_L, HIP_R],     // hips
    [5, HIP_L], [6, HIP_R], // torso
    // Feet. Both contact points hang off the ankle, so a toe-out cue rotates
    // the foot without the lerp chording the arc and shortening it — an
    // unconstrained foot shears mid-morph and reads as a tiptoe.
    [ANKLE_L, FOOT_L], [ANKLE_R, FOOT_R],
    [ANKLE_L, HEEL_L], [ANKLE_R, HEEL_R],
];

function _jx(flat, j) { return flat[j * 3]; }
function _jy(flat, j) { return flat[j * 3 + 1]; }
function _jz(flat, j) { return flat[j * 3 + 2]; }

function _dist3(flat, a, b) {
    const dx = _jx(flat, a) - _jx(flat, b);
    const dy = _jy(flat, a) - _jy(flat, b);
    const dz = _jz(flat, a) - _jz(flat, b);
    return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

function _solveKnee(flat, hip, ankle, knee, thighLen, shinLen) {
    const hx = _jx(flat, hip), hy = _jy(flat, hip), hz = _jz(flat, hip);
    const ax = _jx(flat, ankle), ay = _jy(flat, ankle), az = _jz(flat, ankle);
    let dx = ax - hx, dy = ay - hy, dz = az - hz;
    let dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
    if (dist < 1e-9) dist = 1e-9;
    const ux = dx / dist, uy = dy / dist, uz = dz / dist;

    const dMin = Math.abs(thighLen - shinLen) + 1e-4;
    const dMax = thighLen + shinLen - 1e-4;
    const dc = Math.max(dMin, Math.min(dMax, dist));

    let cosA = (thighLen * thighLen + dc * dc - shinLen * shinLen) / (2 * thighLen * dc);
    cosA = Math.max(-1, Math.min(1, cosA));
    const sinA = Math.sin(Math.acos(cosA));

    const kx = _jx(flat, knee), ky = _jy(flat, knee), kz = _jz(flat, knee);
    let px = kx - hx, py = ky - hy, pz = kz - hz;
    const dotP = px * ux + py * uy + pz * uz;
    px -= dotP * ux; py -= dotP * uy; pz -= dotP * uz;
    let pLen = Math.sqrt(px * px + py * py + pz * pz);
    if (pLen < 1e-6) {
        px = -ux * uy; py = 1.0 - uy * uy; pz = -uz * uy;
        pLen = Math.sqrt(px * px + py * py + pz * pz);
        if (pLen < 1e-9) pLen = 1e-9;
    }
    px /= pLen; py /= pLen; pz /= pLen;

    flat[knee * 3]     = hx + thighLen * cosA * ux + thighLen * sinA * px;
    flat[knee * 3 + 1] = hy + thighLen * cosA * uy + thighLen * sinA * py;
    flat[knee * 3 + 2] = hz + thighLen * cosA * uz + thighLen * sinA * pz;
}

function _enforceSegLen(flat, prox, dist, targetLen) {
    const dx = flat[dist * 3] - flat[prox * 3];
    const dy = flat[dist * 3 + 1] - flat[prox * 3 + 1];
    const dz = flat[dist * 3 + 2] - flat[prox * 3 + 2];
    const len = Math.sqrt(dx * dx + dy * dy + dz * dz);
    if (len < 1e-9 || Math.abs(len - targetLen) < 1e-6) return;
    const s = targetLen / len;
    flat[dist * 3]     = flat[prox * 3] + dx * s;
    flat[dist * 3 + 1] = flat[prox * 3 + 1] + dy * s;
    flat[dist * 3 + 2] = flat[prox * 3 + 2] + dz * s;
}

export function enforceBoneLengths(flat, refPose) {
    const thighL = _dist3(refPose, HIP_L, KNEE_L);
    const shinL  = _dist3(refPose, KNEE_L, ANKLE_L);
    const thighR = _dist3(refPose, HIP_R, KNEE_R);
    const shinR  = _dist3(refPose, KNEE_R, ANKLE_R);

    _solveKnee(flat, HIP_L, ANKLE_L, KNEE_L, thighL, shinL);
    _solveKnee(flat, HIP_R, ANKLE_R, KNEE_R, thighR, shinR);

    for (const [p, d] of BONE_PAIRS) {
        // Heel pairs are absent from 19-joint poses.
        if (d * 3 + 2 >= flat.length) continue;
        _enforceSegLen(flat, p, d, _dist3(refPose, p, d));
    }
}

export function easeInOut(t) {
    t = Math.min(1, Math.max(0, t));
    return t * t * (3 - 2 * t);
}

export function yoyoWeight(elapsed, travel, hold) {
    const period = 2 * (travel + hold);
    let phase = elapsed % period;
    if (phase < hold) return 0;
    phase -= hold;
    if (phase < travel) return easeInOut(phase / travel);
    phase -= travel;
    if (phase < hold) return 1;
    return 1 - easeInOut((phase - hold) / travel);
}

export function lerpPose(a, b, w, out) {
    for (let i = 0; i < a.length; i++) {
        out[i] = a[i] + (b[i] - a[i]) * w;
    }
    return out;
}

// Callbacks (all optional):
//   render(points, highlight)  draw the main skeleton
//   setOpacity(o)              main skeleton opacity 0..1
//   setCaption(text|null)      cue magnitude caption
//   setGhost(pose|null)        static reference skeleton, null hides it
//   hideSkeleton()             hide the main skeleton entirely
//   onCueCamera(causeId)       a cue became active — move the camera
//   onStarted()                morph-in actually began
//   onDone()                   demo finished (after morph-out)
export function createChoreographer(callbacks = {}) {
    const noop = () => {};
    const cb = {
        render: noop, setOpacity: noop, setCaption: noop, setGhost: noop,
        hideSkeleton: noop, onCueCamera: noop, onStarted: noop, onDone: noop,
        ...callbacks,
    };

    let timing = { ...DEFAULT_TIMING };
    let state = IDLE;
    let stateStart = 0;
    let poseStack = null;
    let poseCount = 0;
    let cues = [];
    let highlightMap = {};
    let cueIndex = 0;
    let pendingCues = [];
    let settleFrom = null;
    let settleTo = null;
    let afterSettleCue = null;
    let morphFrom = null;
    let morphOutFrom = null;
    let livePose = null;
    let jointCount = DEFAULT_JOINT_COUNT;
    let poseSize = jointCount * 3;
    let currentPoints = new Float64Array(poseSize);

    function getPose(stackIndex) {
        return poseStack.subarray(stackIndex * poseSize, (stackIndex + 1) * poseSize);
    }

    function init(payload) {
        const stack = payload.pose_stack;
        poseCount = stack.length;
        // Trust the payload's joint count: 19 for poses captured before heel
        // tracking, 21 with heels. Sizing off a constant would silently drop
        // the heels and render the foot as a spike.
        jointCount = (stack[0] && stack[0].length) || DEFAULT_JOINT_COUNT;
        poseSize = jointCount * 3;
        currentPoints = new Float64Array(poseSize);
        poseStack = new Float64Array(poseCount * poseSize);
        for (let p = 0; p < poseCount; p++) {
            for (let j = 0; j < jointCount; j++) {
                poseStack[p * poseSize + j * 3 + 0] = stack[p][j][0];
                poseStack[p * poseSize + j * 3 + 1] = stack[p][j][1];
                poseStack[p * poseSize + j * 3 + 2] = stack[p][j][2];
            }
        }
        cues = payload.cues || [];
        highlightMap = payload.highlight_map || {};
        if (payload.timing) {
            timing = { ...timing, ...payload.timing };
        }
    }

    function setLivePose(flatPoints) {
        livePose = Float64Array.from(flatPoints);
        if (!poseStack && livePose.length !== poseSize) {
            // No demo loaded yet, so the live feed defines the joint count.
            poseSize = livePose.length;
            jointCount = Math.floor(poseSize / 3);
            currentPoints = new Float64Array(poseSize);
        }
        if (state === IDLE) {
            // A stored 19-joint demo alongside a 21-joint live feed would
            // overrun currentPoints; copy the shared prefix instead of throwing.
            currentPoints.set(livePose.subarray(0, Math.min(livePose.length, poseSize)));
            cb.setOpacity(1);
            cb.render(currentPoints, []);
        }
    }

    function start(now) {
        if (!poseStack) return;
        pendingCues = [];
        cueIndex = 0;
        morphFrom = livePose ? Float64Array.from(livePose) : null;
        currentPoints.set(morphFrom || getPose(0));
        state = MORPH_IN;
        stateStart = now;
        cb.setCaption(null);
        cb.setGhost(null);
        cb.onStarted();
        if (cues.length > 0) {
            cb.onCueCamera(cues[0].cause_id);
        }
    }

    function advanceCue(idx, now) {
        if (!poseStack || idx >= cues.length) return;
        const morphing = state === MORPH_IN && (now - stateStart) < timing.morphIn;
        if (morphing) {
            // Queue instead of overwrite: burst-replayed cues (e.g. event
            // backlog to a slow browser) settle through each pose in order.
            pendingCues.push(idx);
            return;
        }
        beginSettle(getPose(idx), idx, now);
        cb.onCueCamera(cues[idx].cause_id);
    }

    function finish(now) {
        if (!poseStack) {
            state = IDLE;
            return;
        }
        pendingCues = [];
        beginSettle(getPose(poseCount - 1), null, now);
        cb.setCaption(null);
    }

    function beginSettle(target, nextCue, now) {
        settleFrom = Float64Array.from(currentPoints);
        settleTo = target;
        afterSettleCue = nextCue;
        state = SETTLE;
        stateStart = now;
    }

    function tick(now) {
        if (state === IDLE || !poseStack) return;
        const elapsed = now - stateStart;

        if (state === SETTLE && elapsed >= timing.settle) {
            if (afterSettleCue !== null) {
                if (pendingCues.length > 0) {
                    // More queued cues: pass through this pose and settle on.
                    const next = pendingCues.shift();
                    beginSettle(getPose(next), next, now);
                    cb.onCueCamera(cues[next].cause_id);
                    tick(now);
                    return;
                }
                cueIndex = afterSettleCue;
                state = CUE_LOOP;
            } else {
                state = FINAL_HOLD;
            }
            stateStart = now;
            tick(now);
            return;
        }

        if (state === FINAL_HOLD && elapsed >= timing.finalHold) {
            state = MORPH_OUT;
            stateStart = now;
            morphOutFrom = Float64Array.from(getPose(poseCount - 1));
            tick(now);
            return;
        }

        if (state === MORPH_OUT && elapsed >= timing.morphOut) {
            state = IDLE;
            cb.setCaption(null);
            cb.setGhost(null);
            if (livePose) {
                currentPoints.set(livePose);
                cb.setOpacity(1);
                cb.render(currentPoints, []);
            } else {
                cb.hideSkeleton();
            }
            cb.onDone();
            return;
        }

        if (state === MORPH_IN && pendingCues.length > 0 && elapsed >= timing.morphIn) {
            const idx = pendingCues.shift();
            beginSettle(getPose(idx), idx, now);
            cb.onCueCamera(cues[idx].cause_id);
            tick(now);
            return;
        }

        let highlight = [];

        const refPose = getPose(0);

        if (state === MORPH_IN) {
            const w = easeInOut(Math.min(elapsed / timing.morphIn, 1));
            if (morphFrom) {
                cb.setOpacity(1);
                lerpPose(morphFrom, getPose(0), w, currentPoints);
                enforceBoneLengths(currentPoints, refPose);
            } else {
                cb.setOpacity(w);
                currentPoints.set(getPose(0));
            }
            cb.setGhost(null);
            cb.render(currentPoints, highlight);
        } else if (state === MORPH_OUT) {
            const w = easeInOut(Math.min(elapsed / timing.morphOut, 1));
            if (livePose) {
                cb.setOpacity(1);
                lerpPose(morphOutFrom, livePose, w, currentPoints);
                enforceBoneLengths(currentPoints, refPose);
            } else {
                cb.setOpacity(1 - w);
                currentPoints.set(morphOutFrom);
            }
            cb.setGhost(null);
            cb.render(currentPoints, highlight);
        } else {
            cb.setOpacity(1);
            if (state === CUE_LOOP) {
                const cue = cues[cueIndex];
                const w = yoyoWeight(elapsed, timing.yoyoTravel, timing.yoyoHold);
                lerpPose(getPose(cueIndex), getPose(cueIndex + 1), w, currentPoints);
                enforceBoneLengths(currentPoints, refPose);
                highlight = highlightMap[cue.cause_id] || [];
                cb.setCaption(cue.magnitude_text);
                cb.setGhost(getPose(cueIndex));
            } else if (state === SETTLE) {
                const w = easeInOut(elapsed / timing.settle);
                lerpPose(settleFrom, settleTo, w, currentPoints);
                enforceBoneLengths(currentPoints, refPose);
                cb.setCaption(null);
                cb.setGhost(null);
            } else if (state === FINAL_HOLD) {
                currentPoints.set(getPose(poseCount - 1));
                cb.setCaption(null);
                cb.setGhost(getPose(0));
            }
            cb.render(currentPoints, highlight);
        }
    }

    return {
        init, setLivePose, start, advanceCue, finish, tick,
        get state() { return state; },
        get timing() { return timing; },
        get cueCount() { return cues.length; },
    };
}
