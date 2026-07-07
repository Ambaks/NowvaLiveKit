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

const JOINT_COUNT = 19;
const POSE_SIZE = JOINT_COUNT * 3;

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
    const currentPoints = new Float64Array(POSE_SIZE);

    function getPose(stackIndex) {
        return poseStack.subarray(stackIndex * POSE_SIZE, (stackIndex + 1) * POSE_SIZE);
    }

    function init(payload) {
        const stack = payload.pose_stack;
        poseCount = stack.length;
        poseStack = new Float64Array(poseCount * POSE_SIZE);
        for (let p = 0; p < poseCount; p++) {
            for (let j = 0; j < JOINT_COUNT; j++) {
                poseStack[p * POSE_SIZE + j * 3 + 0] = stack[p][j][0];
                poseStack[p * POSE_SIZE + j * 3 + 1] = stack[p][j][1];
                poseStack[p * POSE_SIZE + j * 3 + 2] = stack[p][j][2];
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
        if (state === IDLE) {
            currentPoints.set(livePose);
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

        if (state === MORPH_IN) {
            const w = easeInOut(Math.min(elapsed / timing.morphIn, 1));
            if (morphFrom) {
                cb.setOpacity(1);
                lerpPose(morphFrom, getPose(0), w, currentPoints);
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
                highlight = highlightMap[cue.cause_id] || [];
                cb.setCaption(cue.magnitude_text);
                cb.setGhost(getPose(cueIndex));
            } else if (state === SETTLE) {
                const w = easeInOut(elapsed / timing.settle);
                lerpPose(settleFrom, settleTo, w, currentPoints);
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
