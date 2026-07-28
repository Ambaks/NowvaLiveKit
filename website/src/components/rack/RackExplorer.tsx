"use client";

/* Full-bleed presentation shell for the exploded-view stage.
 *
 * No frame and no straight edges: the rack sits in a pool of darkness that
 * dissolves outward in every direction. A linear top/bottom fade would work on
 * the dark theme but smears into a grey band on the light one — a radial field
 * has no edge to smear. The WebGL bundle and the 1.1 MB model are only fetched
 * once the section is close to the viewport. */

import { Component, useEffect, useRef, useState, type ReactNode } from "react";
import dynamic from "next/dynamic";

const RackStage = dynamic(
  () => import("@/components/three/scenes").then((m) => m.loadRackStage()),
  { ssr: false },
);

/* A crashed stage (WebGL context loss, failed GLB fetch) degrades to the
   static backdrop instead of unmounting the whole page. */
class StageErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? null : this.props.children;
  }
}

/* Start loading this far before the section scrolls in. */
const PRELOAD_MARGIN = "600px";

/* Wider than the stage so the sides stay solid and only the top and bottom
   dissolve — a circular falloff would leave four pale corners. */
const POOL =
  "radial-gradient(ellipse 150% 62% at 50% 47%, #07070b 0%, #07070b 46%, rgba(7,7,11,0.92) 62%, rgba(7,7,11,0.55) 80%, rgba(7,7,11,0) 100%)";
const KEY_GLOW =
  "radial-gradient(ellipse 46% 44% at 50% 40%, rgba(139,92,246,0.20), transparent 72%)";
const FLOOR_GLOW =
  "radial-gradient(ellipse 55% 26% at 50% 80%, rgba(255,184,0,0.08), transparent 72%)";

export function RackExplorer() {
  const ref = useRef<HTMLDivElement>(null);
  const [armed, setArmed] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    /* three r163+ requires WebGL2; without it the renderer constructor
       throws, so unsupported browsers keep the static backdrop. */
    if (!document.createElement("canvas").getContext("webgl2")) return;

    /* Preflight the chunk before mounting: rendering a failed next/dynamic
       rethrows the load error, and a fetch failure (offline, stale deploy,
       blocker) must not take the page down for a decorative section. */
    const arm = () => {
      import("@/components/three/scenes")
        .then((m) => m.loadRackStage())
        .then(() => setArmed(true))
        .catch(() => {});
    };

    if (typeof IntersectionObserver === "undefined") {
      const id = window.setTimeout(arm, 0);
      return () => window.clearTimeout(id);
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          arm();
          observer.disconnect();
        }
      },
      { rootMargin: PRELOAD_MARGIN },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={ref} className="relative w-full select-none">
      <div className="rack-stage relative h-[78svh] min-h-[30rem] overflow-hidden">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{ background: POOL }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{ background: KEY_GLOW }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{ background: FLOOR_GLOW }}
        />

        {armed && (
          <StageErrorBoundary>
            <RackStage />
          </StageErrorBoundary>
        )}
      </div>
    </div>
  );
}
