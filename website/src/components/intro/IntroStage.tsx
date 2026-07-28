"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";

const IntroScene = dynamic(
  () => import("@/components/three/scenes").then((m) => m.IntroScene),
  { ssr: false },
);

/* Grace period after the splash wipe before giving up on the 3D chunk. */
const SCENE_GRACE_MS = 1500;
/* Absolute ceiling from navigation start; finish no matter what. */
const HARD_MAX_MS = 9000;
const FADE_OUT_MS = 450;
/* Take over only if we hydrate comfortably before the splash wipe starts. */
const TAKEOVER_MARGIN_MS = 150;

type Phase = "idle" | "loading" | "playing" | "leaving";
type SceneModule = typeof import("@/components/three/scenes");

/* The CSS pipeline may normalize time units (1600ms → 1.6s). */
const cssMs = (name: string): number => {
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  const value = parseFloat(raw);
  if (Number.isNaN(value)) return 0;
  return raw.endsWith("ms") ? value : value * 1000;
};

/* The splash's CSS animation delay anchors at first style application
   (~first paint), not navigation start; read the real start time so the
   finish clamp and the pan mount track the actual wipe. */
const splashTimelineStart = (): number => {
  try {
    const splashAnimation = document
      .getAnimations()
      .find(
        (animation) =>
          "animationName" in animation &&
          (animation as CSSAnimation).animationName === "intro-exit",
      );
    if (!splashAnimation) return 0;
    const start = splashAnimation.startTime;
    return typeof start === "number" ? start : performance.now();
  } catch {
    return 0;
  }
};

/* Orchestrates intro stage 2: mounts an opaque overlay under the CSS splash
   so its wipe reveals the 3D pan, then flips html[data-intro] through
   "3d" → "done" to hold and release the hero entrance. Every exit path —
   pan complete, skip, Escape, chunk/load failure, timeout — funnels through
   one idempotent finish() clamped to never fire before the wipe completes.
   If it never takes over (repeat visit, reduced motion, no WebGL2, late
   hydration, no JS), the classic CSS-only intro plays untouched. */
export function IntroStage() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [played, setPlayed] = useState(false);
  const finishRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    const html = document.documentElement;

    if (html.dataset.intro === "off") return;

    const hold = cssMs("--intro-hold");
    const wipe = cssMs("--intro-wipe");
    const holdEnd = splashTimelineStart() + hold;
    const wipeEnd = holdEnd + wipe;

    /* Skip the entry guards when re-running after a StrictMode cleanup —
       we already own the takeover, and bailing here would strand the page
       in the "3d" state with no timers left to release it. */
    if (html.dataset.intro !== "3d") {
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches)
        return;
      if (hold === 0 || performance.now() > holdEnd - TAKEOVER_MARGIN_MS)
        return;
      if (!document.createElement("canvas").getContext("webgl2")) return;
    }

    html.dataset.intro = "3d";
    /* The takeover decision needs post-hydration DOM state, so this mount
       effect is the earliest safe place; the one extra render is intended. */
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPhase("loading");

    /* The overlay covers the page visually but does not remove it from the
       tab order; inert everything beneath so keyboard focus can only reach
       the skip button. */
    const inerted: HTMLElement[] = [];
    for (const sibling of Array.from(document.body.children)) {
      if (
        sibling instanceof HTMLElement &&
        !sibling.classList.contains("intro-loader") &&
        !sibling.classList.contains("intro-stage") &&
        !sibling.inert
      ) {
        sibling.inert = true;
        inerted.push(sibling);
      }
    }
    const releaseInert = () => {
      for (const sibling of inerted) sibling.inert = false;
      inerted.length = 0;
    };

    let finished = false;
    let sceneModule: SceneModule | null = null;
    const timers: number[] = [];
    const later = (fn: () => void, ms: number) => {
      timers.push(window.setTimeout(fn, Math.max(0, ms)));
    };

    const finish = () => {
      if (finished) return;
      finished = true;
      const go = () => {
        html.dataset.intro = "done";
        releaseInert();
        window.dispatchEvent(new Event("nv:intro-done"));
        setPhase("leaving");
        later(() => {
          setPhase("idle");
          /* Free the decoded GLB once the scene is unmounted. If the chunk
             never arrived nothing was decoded; if it arrives after this
             point the cached asset is a few MB of session-scoped memory. */
          sceneModule?.releaseIntroAssets();
        }, FADE_OUT_MS);
      };
      /* Never before the splash wipe completes. */
      const wait = wipeEnd - performance.now();
      if (wait > 0) later(go, wait);
      else go();
    };
    finishRef.current = finish;

    /* Soft deadline: chunk not ready shortly after the wipe → bail to the
       page. Cleared once the scene is ready to mount; the scene's own load
       watchdog and the hard ceiling cover everything after that. */
    let deadline: number | null = window.setTimeout(
      finish,
      Math.max(0, wipeEnd + SCENE_GRACE_MS - performance.now()),
    );
    later(finish, HARD_MAX_MS - performance.now());

    /* Start the pan as the wipe reveals it: wait for chunk AND splash hold. */
    const holdReached = new Promise<void>((resolve) => {
      later(resolve, holdEnd - performance.now());
    });
    const chunkLoaded = import("@/components/three/scenes").then((module) => {
      sceneModule = module;
      module.preloadIntroAssets();
    });
    Promise.all([chunkLoaded, holdReached])
      .then(() => {
        if (finished) return;
        if (deadline !== null) window.clearTimeout(deadline);
        deadline = null;
        setPlayed(true);
        setPhase("playing");
      })
      /* Chunk fetch failed (offline, stale deploy, blocker) — bail to the
         page now instead of waiting out the deadline, and never mount the
         scene: mounting a failed next/dynamic would throw with no error
         boundary above it in the root layout. */
      .catch(() => finish());

    const onKeydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") finish();
    };
    window.addEventListener("keydown", onKeydown);

    return () => {
      timers.forEach((id) => window.clearTimeout(id));
      if (deadline !== null) window.clearTimeout(deadline);
      window.removeEventListener("keydown", onKeydown);
      releaseInert();
    };
  }, []);

  if (phase === "idle") return null;

  /* Mount the scene only once its chunk is known-good ("playing"), and keep
     it through the fade-out only if it was actually playing. */
  const showScene =
    phase === "playing" || (phase === "leaving" && played);

  return (
    <div
      className={
        phase === "leaving" ? "intro-stage intro-stage--out" : "intro-stage"
      }
    >
      <div aria-hidden="true" className="intro-stage__canvas">
        {showScene && (
          <IntroScene
            onDone={() => finishRef.current?.()}
            onError={() => finishRef.current?.()}
          />
        )}
      </div>
      {phase === "playing" && (
        <button
          type="button"
          className="intro-stage__skip"
          onClick={() => finishRef.current?.()}
        >
          Skip intro
        </button>
      )}
    </div>
  );
}
