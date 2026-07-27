// Tests for the demo choreographer state machine (run: node --test tests/js/).
import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import {
    CUE_LOOP,
    DEFAULT_TIMING,
    FINAL_HOLD,
    IDLE,
    MORPH_IN,
    MORPH_OUT,
    SETTLE,
    createChoreographer,
    easeInOut,
    yoyoWeight,
} from '../../src/biomechanics/viz/choreographer.mjs';

const T = DEFAULT_TIMING;
const WEIGHT_TOL = 1e-9;

function makePose(stanceHalfWidth) {
    const pose = [];
    for (let j = 0; j < 19; j++) pose.push([0, 0, 0]);
    pose[0] = [0.0, 1.6, 0.0];
    pose[11] = [0.0, 0.5, -0.15];
    pose[12] = [0.0, 0.5, 0.15];
    pose[15] = [0.0, 0.0, -stanceHalfWidth];
    pose[16] = [0.0, 0.0, stanceHalfWidth];
    return pose;
}

function makeInitPayload(numCues = 2) {
    const poseStack = [];
    for (let k = 0; k <= numCues; k++) poseStack.push(makePose(0.15 + 0.03 * k));
    const cues = [];
    for (let k = 0; k < numCues; k++) {
        cues.push({
            cue_index: k,
            cause_id: 'narrow_stance',
            explanation: 'test',
            magnitude_text: 'about 3 centimeters wider on each side',
        });
    }
    return {
        pose_stack: poseStack,
        cues,
        highlight_map: { narrow_stance: [13, 14, 15, 16, 17, 18] },
        timing: T,
    };
}

function makeHarness(numCues = 2) {
    const calls = {
        rendered: [], opacity: [], captions: [], ghosts: [],
        cameras: [], started: 0, done: 0, hidden: 0,
    };
    const choreo = createChoreographer({
        render: (pts, hl) => calls.rendered.push({ pts: Float64Array.from(pts), hl }),
        setOpacity: (o) => calls.opacity.push(o),
        setCaption: (t) => calls.captions.push(t),
        setGhost: (g) => calls.ghosts.push(g ? Float64Array.from(g) : null),
        hideSkeleton: () => calls.hidden++,
        onCueCamera: (c) => calls.cameras.push(c),
        onStarted: () => calls.started++,
        onDone: () => calls.done++,
    });
    choreo.init(makeInitPayload(numCues));
    return { choreo, calls };
}

function lastRender(calls) {
    return calls.rendered[calls.rendered.length - 1];
}

describe('yoyoWeight', () => {
    test('zero at start', () => {
        assert.ok(Math.abs(yoyoWeight(0, T.yoyoTravel, T.yoyoHold)) < WEIGHT_TOL);
    });

    test('one after hold and travel', () => {
        const w = yoyoWeight(T.yoyoHold + T.yoyoTravel, T.yoyoTravel, T.yoyoHold);
        assert.ok(Math.abs(w - 1) < WEIGHT_TOL);
    });

    test('holds at endpoints', () => {
        const startHold = yoyoWeight(T.yoyoHold * 0.5, T.yoyoTravel, T.yoyoHold);
        const endHold = yoyoWeight(
            T.yoyoHold + T.yoyoTravel + T.yoyoHold * 0.5, T.yoyoTravel, T.yoyoHold,
        );
        assert.ok(Math.abs(startHold) < WEIGHT_TOL);
        assert.ok(Math.abs(endHold - 1) < WEIGHT_TOL);
    });

    test('periodic', () => {
        const period = 2 * (T.yoyoTravel + T.yoyoHold);
        const sample = T.yoyoHold + T.yoyoTravel * 0.3;
        const first = yoyoWeight(sample, T.yoyoTravel, T.yoyoHold);
        const second = yoyoWeight(sample + period, T.yoyoTravel, T.yoyoHold);
        assert.ok(Math.abs(first - second) < WEIGHT_TOL);
    });
});

describe('easeInOut', () => {
    test('clamps and hits endpoints', () => {
        assert.equal(easeInOut(-1), 0);
        assert.equal(easeInOut(0), 0);
        assert.equal(easeInOut(0.5), 0.5);
        assert.equal(easeInOut(1), 1);
        assert.equal(easeInOut(2), 1);
    });
});

describe('state machine', () => {
    test('idle before start, morph_in after, onStarted fired', () => {
        const { choreo, calls } = makeHarness();
        assert.equal(choreo.state, IDLE);
        choreo.start(0);
        assert.equal(choreo.state, MORPH_IN);
        assert.equal(calls.started, 1);
        assert.deepEqual(calls.cameras, ['narrow_stance']);
    });

    test('start without init is a no-op', () => {
        const calls = { started: 0 };
        const choreo = createChoreographer({ onStarted: () => calls.started++ });
        choreo.start(0);
        assert.equal(choreo.state, IDLE);
        assert.equal(calls.started, 0);
    });

    test('morph-in without live pose fades opacity and renders pose 0', () => {
        const { choreo, calls } = makeHarness();
        choreo.start(0);
        choreo.tick(T.morphIn * 0.5);
        assert.equal(calls.opacity[calls.opacity.length - 1], easeInOut(0.5));
        const pts = lastRender(calls).pts;
        assert.ok(Math.abs(pts[15 * 3 + 2] - (-0.15)) < 1e-9);
    });

    test('cue during morph-in is deferred, then settles into cue loop', () => {
        const { choreo } = makeHarness();
        choreo.start(0);
        choreo.advanceCue(0, T.morphIn * 0.5);
        assert.equal(choreo.state, MORPH_IN);
        choreo.tick(T.morphIn + 0.01);
        assert.equal(choreo.state, SETTLE);
        choreo.tick(T.morphIn + 0.01 + T.settle + 0.01);
        assert.equal(choreo.state, CUE_LOOP);
    });

    test('cue loop yoyos between pose k and k+1 with highlight, caption, ghost', () => {
        const { choreo, calls } = makeHarness();
        choreo.start(0);
        choreo.tick(T.morphIn + 0.01);
        choreo.advanceCue(0, T.morphIn + 0.02);
        const loopStart = T.morphIn + 0.02 + T.settle + 0.01;
        choreo.tick(loopStart);
        assert.equal(choreo.state, CUE_LOOP);

        // Sample at the far endpoint of the yoyo travel: weight == 1 → pose 1.
        choreo.tick(loopStart + T.yoyoHold + T.yoyoTravel);
        const { pts, hl } = lastRender(calls);
        assert.ok(Math.abs(pts[16 * 3 + 2] - 0.18) < 1e-6);
        assert.deepEqual(hl, [13, 14, 15, 16, 17, 18]);
        assert.equal(calls.captions[calls.captions.length - 1],
            'about 3 centimeters wider on each side');

        const ghost = calls.ghosts[calls.ghosts.length - 1];
        assert.ok(ghost !== null);
        assert.ok(Math.abs(ghost[16 * 3 + 2] - 0.15) < 1e-6);
    });

    test('finish settles to final pose, holds with observed ghost, morphs out, fires done', () => {
        const { choreo, calls } = makeHarness();
        choreo.start(0);
        let now = T.morphIn + 0.01;
        choreo.tick(now);
        choreo.finish(now);
        assert.equal(choreo.state, SETTLE);

        now += T.settle + 0.01;
        choreo.tick(now);
        assert.equal(choreo.state, FINAL_HOLD);
        const ghost = calls.ghosts[calls.ghosts.length - 1];
        assert.ok(Math.abs(ghost[16 * 3 + 2] - 0.15) < 1e-6);
        const pts = lastRender(calls).pts;
        assert.ok(Math.abs(pts[16 * 3 + 2] - 0.21) < 1e-6);

        now += T.finalHold + 0.01;
        choreo.tick(now);
        assert.equal(choreo.state, MORPH_OUT);

        now += T.morphOut + 0.01;
        choreo.tick(now);
        assert.equal(choreo.state, IDLE);
        assert.equal(calls.done, 1);
        assert.equal(calls.hidden, 1);
        assert.equal(calls.ghosts[calls.ghosts.length - 1], null);
    });

    test('out-of-range cue is ignored', () => {
        const { choreo } = makeHarness();
        choreo.start(0);
        choreo.tick(T.morphIn + 0.01);
        choreo.advanceCue(99, T.morphIn + 0.02);
        assert.equal(choreo.state, MORPH_IN);
    });

    test('cues burst during morph-in are queued and settle through in order', () => {
        const { choreo, calls } = makeHarness(2);
        choreo.start(0);
        choreo.advanceCue(0, T.morphIn * 0.3);
        choreo.advanceCue(1, T.morphIn * 0.5);
        assert.equal(choreo.state, MORPH_IN);

        // Morph-in completes: first queued cue begins its settle.
        let now = T.morphIn + 0.01;
        choreo.tick(now);
        assert.equal(choreo.state, SETTLE);
        assert.equal(calls.cameras.length, 2); // start + cue 0

        // First settle completes: second queued cue chains into another settle
        // instead of being dropped.
        now += T.settle + 0.01;
        choreo.tick(now);
        assert.equal(choreo.state, SETTLE);
        assert.equal(calls.cameras.length, 3); // + cue 1

        // Second settle completes: cue loop runs on the last cue (poses 1→2).
        now += T.settle + 0.01;
        choreo.tick(now);
        assert.equal(choreo.state, CUE_LOOP);
        choreo.tick(now + T.yoyoHold + T.yoyoTravel);
        const { pts } = lastRender(calls);
        assert.ok(Math.abs(pts[16 * 3 + 2] - 0.21) < 1e-6);
    });

    test('finish clears queued cues and reaches final hold', () => {
        const { choreo } = makeHarness(2);
        choreo.start(0);
        choreo.advanceCue(0, T.morphIn * 0.3);
        choreo.advanceCue(1, T.morphIn * 0.4);
        choreo.finish(T.morphIn * 0.5);
        assert.equal(choreo.state, SETTLE);

        choreo.tick(T.morphIn * 0.5 + T.settle + 0.01);
        assert.equal(choreo.state, FINAL_HOLD);
    });
});

describe('live pose', () => {
    function livePose() {
        const flat = new Float64Array(19 * 3);
        flat[15 * 3 + 2] = -0.30;
        flat[16 * 3 + 2] = 0.30;
        return flat;
    }

    test('idle live pose renders immediately at full opacity', () => {
        const { choreo, calls } = makeHarness();
        choreo.setLivePose(livePose());
        assert.equal(calls.opacity[calls.opacity.length - 1], 1);
        const pts = lastRender(calls).pts;
        assert.ok(Math.abs(pts[16 * 3 + 2] - 0.30) < 1e-9);
    });

    test('morph-in lerps from live pose at full opacity', () => {
        const { choreo, calls } = makeHarness();
        choreo.setLivePose(livePose());
        choreo.start(0);
        choreo.tick(T.morphIn * 0.5);
        assert.equal(calls.opacity[calls.opacity.length - 1], 1);
        // easeInOut(0.5) == 0.5 → midway between live 0.30 and observed 0.15.
        const pts = lastRender(calls).pts;
        assert.ok(Math.abs(pts[16 * 3 + 2] - 0.225) < 1e-9);
    });

    test('morph-out returns to the live pose and keeps the skeleton visible', () => {
        const { choreo, calls } = makeHarness();
        choreo.setLivePose(livePose());
        choreo.start(0);
        let now = T.morphIn + 0.01;
        choreo.tick(now);
        choreo.finish(now);
        now += T.settle + 0.01;
        choreo.tick(now);
        now += T.finalHold + 0.01;
        choreo.tick(now);
        assert.equal(choreo.state, MORPH_OUT);

        choreo.tick(now + T.morphOut * 0.5);
        // Midway between final pose 0.21 and live 0.30.
        const pts = lastRender(calls).pts;
        assert.ok(Math.abs(pts[16 * 3 + 2] - 0.255) < 1e-9);

        choreo.tick(now + T.morphOut + 0.01);
        assert.equal(choreo.state, IDLE);
        assert.equal(calls.done, 1);
        assert.equal(calls.hidden, 0);
        const finalPts = lastRender(calls).pts;
        assert.ok(Math.abs(finalPts[16 * 3 + 2] - 0.30) < 1e-9);
    });
});
