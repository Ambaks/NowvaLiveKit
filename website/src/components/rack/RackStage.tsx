"use client";

/* eslint-disable react-hooks/immutability -- ref callbacks register marker DOM nodes into a
   handles map that the render loop writes to directly; that is the whole
   point of keeping markers out of React state. */

/* The interactive exploded-view stage: canvas, screen markers, part panel and
   scrub. Mounted only once the section nears the viewport (see RackExplorer). */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type RefObject,
} from "react";
import { Canvas } from "@react-three/fiber";
import { ContactShadows, useGLTF } from "@react-three/drei";
import type * as THREE from "three";
import { useReducedMotion } from "motion/react";

import { explodeConfig } from "./explode";
import {
  buildAssembly,
  resolveExplode,
  type BuiltAssembly,
  type BuiltPart,
} from "./assembly";
import { contentFor, displayNameFor } from "./partContent";
import { viewer, type SequencePhase } from "./viewerStore";
import { createMarkerHandles, type MarkerHandles } from "./markerHandles";
import { AssemblyView, CameraRig, FrameDriver, Projector } from "./SceneParts";

const MODEL_URL = "/models/rack-parts.glb";
const DRACO_PATH = "/draco/";

useGLTF.preload(MODEL_URL, DRACO_PATH);

/* ------------------------------------------------------------------ scene */

/* Built once per loaded glTF and stashed on its scene, so StrictMode's mount ->
   unmount -> remount cycle (and Fast Refresh, which would reset a module-level
   cache after the source buffers below are freed) reuses the same merged
   geometry instead of rebuilding it. */
const BUILT_ASSEMBLY_KEY = "builtAssembly";

/* The merged copies are the only geometry this stage ever renders. Once they
   exist, drop the decoded source buffers — 864 primitives of positions and
   normals otherwise sit in heap for the page's lifetime purely as merge input.
   The scene graph itself stays in drei's cache (see the no-clear note below). */
function releaseSourceGeometry(scene: THREE.Object3D): void {
  scene.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if (!mesh.isMesh || !mesh.geometry) return;
    mesh.geometry.dispose();
    for (const name of Object.keys(mesh.geometry.attributes)) {
      mesh.geometry.deleteAttribute(name);
    }
    mesh.geometry.setIndex(null);
  });
}

function Loader({ onReady }: { onReady: (assembly: BuiltAssembly) => void }) {
  const gltf = useGLTF(MODEL_URL, DRACO_PATH);
  const assembly = useMemo(() => {
    let built = gltf.scene.userData[BUILT_ASSEMBLY_KEY] as
      | BuiltAssembly
      | undefined;
    if (!built) {
      built = buildAssembly(gltf);
      gltf.scene.userData[BUILT_ASSEMBLY_KEY] = built;
      releaseSourceGeometry(gltf.scene);
    }
    return built;
  }, [gltf]);
  useEffect(() => onReady(assembly), [assembly, onReady]);
  return null;
}

function Lights() {
  return (
    <>
      <hemisphereLight args={["#cfd4ff", "#0a0910", 1.15]} />
      <directionalLight position={[4, 7, 5]} intensity={2.1} color="#fff6e8" />
      <directionalLight position={[-6, 3, -2]} intensity={0.75} color="#8fa8ff" />
      <directionalLight position={[0, 2, -7]} intensity={0.55} color="#c9b6ff" />
    </>
  );
}

/* drei's ContactShadows re-bakes for `frames` frames after every render of the
   component (its bake counter is a per-render closure). Subscribing this
   wrapper to the explode amount re-renders it only while t is changing, so the
   shadow re-bakes during scrubs and run sequences and stays a static texture
   the rest of the session — part positions are the only thing it depends on. */
function BakedShadows({ assembly }: { assembly: BuiltAssembly }) {
  const [, setBakeT] = useState(0);
  useEffect(() => viewer.subscribeT(setBakeT), []);

  return (
    <ContactShadows
      position={[
        assembly.center.x,
        assembly.box.min.y + 0.001,
        assembly.center.z,
      ]}
      scale={Math.max(assembly.size.x, assembly.size.z) * 2.4}
      resolution={512}
      frames={1}
      blur={2.8}
      opacity={0.55}
      far={Math.max(assembly.size.x, assembly.size.z)}
    />
  );
}

/* ---------------------------------------------------------------- markers */

function Markers({
  assembly,
  handles,
  selectedId,
  onSelect,
}: {
  assembly: BuiltAssembly;
  handles: RefObject<MarkerHandles>;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const selected = selectedId ? assembly.byId.get(selectedId) : null;

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      <svg className="absolute inset-0 size-full" aria-hidden>
        <polyline
          ref={(el) => {
            handles.current.leader = el;
          }}
          fill="none"
          stroke="var(--cta)"
          strokeWidth={1}
          strokeDasharray="5 4"
          style={{ visibility: "hidden" }}
        />
      </svg>

      {assembly.parts.map((part) => {
        const isSelected = part.id === selectedId;
        return (
          <button
            key={part.id}
            ref={(el) => {
              if (el) handles.current.dots.set(part.id, el);
              else handles.current.dots.delete(part.id);
            }}
            type="button"
            tabIndex={-1}
            onClick={() => onSelect(isSelected ? null : part.id)}
            aria-label={displayNameFor(part.id, part.nodeName)}
            aria-pressed={isSelected}
            className={
              /* The visible dot stays tiny; the ::before pseudo pads the hit
                 area out to >=44px for touch. */
              "pointer-events-auto absolute left-0 top-0 rounded-full transition-colors before:absolute before:-inset-4.5 before:content-[''] " +
              (isSelected
                ? "size-3 bg-cta ring-2 ring-cta/35"
                : "size-2 bg-white/85 ring-1 ring-black/50 hover:bg-accent")
            }
            style={{ visibility: "hidden" }}
          />
        );
      })}

      <div
        ref={(el) => {
          handles.current.label = el;
        }}
        className="absolute left-0 top-0 whitespace-nowrap border-b border-cta/70 pb-1 font-mono text-[0.65rem] uppercase tracking-[0.16em] text-cta"
        style={{ visibility: "hidden" }}
        aria-hidden
      >
        {selected ? displayNameFor(selected.id, selected.nodeName) : ""}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ panel */

function PartPanel({
  part,
  onClose,
}: {
  part: BuiltPart | null;
  onClose: () => void;
}) {
  if (!part) return null;
  const content = contentFor(part.id);
  const specs = content.specs ?? [];

  return (
    <aside
      className="pointer-events-auto absolute inset-x-0 bottom-0 z-20 max-h-[55%] overflow-y-auto border-t border-white/10 bg-black/70 backdrop-blur-xl md:inset-y-0 md:left-auto md:right-0 md:max-h-none md:w-[22rem] md:border-l md:border-t-0"
      aria-label="Part details"
    >
      <div className="flex items-start justify-between gap-4 border-b border-white/10 px-6 py-5">
        <div className="min-w-0">
          {content.category && (
            <p className="mb-1.5 font-mono text-[0.6rem] uppercase tracking-[0.2em] text-accent">
              {content.category}
            </p>
          )}
          <h3 className="font-display text-lg font-bold leading-tight text-white">
            {displayNameFor(part.id, part.nodeName)}
          </h3>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close part details"
          className="relative -mr-1.5 -mt-1.5 shrink-0 rounded-md p-1.5 text-white/50 transition-colors before:absolute before:-inset-2.5 before:content-[''] hover:bg-white/10 hover:text-white"
        >
          <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden>
            <path
              d="M3.5 3.5l8 8M11.5 3.5l-8 8"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </div>

      <div className="space-y-6 px-6 py-5">
        {content.role && (
          <p className="text-[0.86rem] leading-relaxed text-white/65">
            {content.role}
          </p>
        )}
        {specs.length > 0 && (
          <dl className="divide-y divide-white/10 border-y border-white/10">
            {specs.map(([term, value], index) => (
              <div key={`${term}-${index}`} className="flex gap-4 py-2.5">
                <dt className="w-[38%] shrink-0 font-mono text-[0.6rem] uppercase tracking-[0.12em] text-white/40">
                  {term}
                </dt>
                <dd className="min-w-0 flex-1 text-[0.8rem] text-white/85">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </aside>
  );
}

/* --------------------------------------------------------------- controls */

function ExplodeControls({
  phase,
  disabled,
}: {
  phase: SequencePhase;
  disabled: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const readout = useRef<HTMLSpanElement>(null);

  useEffect(
    () =>
      viewer.subscribeT((t) => {
        if (input.current) input.current.value = String(t);
        if (readout.current) {
          readout.current.textContent = `${Math.round(t * 100)}%`;
        }
      }),
    [],
  );

  const running = phase !== "idle";

  return (
    <div className="pointer-events-auto flex items-center gap-4 rounded-full border border-white/12 bg-black/55 px-4 py-2.5 backdrop-blur-xl sm:gap-5 sm:px-5">
      <button
        type="button"
        disabled={disabled}
        onClick={() =>
          running ? viewer.cancelSequence() : viewer.startSequence()
        }
        className="shrink-0 font-mono text-[0.62rem] uppercase tracking-[0.18em] text-white transition-colors hover:text-cta disabled:opacity-40"
      >
        {running ? "Cancel" : "Take it apart"}
      </button>
      <span aria-hidden className="h-4 w-px shrink-0 bg-white/15" />
      <label className="flex min-w-0 flex-1 items-center gap-3">
        <span className="sr-only">Explode amount</span>
        <input
          ref={input}
          type="range"
          min={0}
          max={1}
          step={0.001}
          defaultValue={0}
          disabled={disabled}
          onInput={(event) => viewer.setT(Number(event.currentTarget.value))}
          className="rack-scrub h-4 w-32 min-w-0 flex-1 disabled:opacity-40 sm:w-44"
          aria-label="Explode amount"
        />
        <span
          ref={readout}
          className="w-9 shrink-0 text-right font-mono text-[0.62rem] tabular-nums text-white/50"
        >
          0%
        </span>
      </label>
    </div>
  );
}

/* ------------------------------------------------------------------ stage */

export default function RackStage() {
  const [assembly, setAssembly] = useState<BuiltAssembly | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [phase, setPhase] = useState<SequencePhase>("idle");
  const [inView, setInView] = useState(
    () => typeof IntersectionObserver === "undefined",
  );

  const rootRef = useRef<HTMLDivElement>(null);
  const handles = useRef(createMarkerHandles());
  const reducedMotion = useReducedMotion() ?? false;

  const explode = useMemo(
    () => (assembly ? resolveExplode(assembly, explodeConfig) : null),
    [assembly],
  );

  const handleReady = useCallback((next: BuiltAssembly) => {
    setAssembly(next);
  }, []);

  /* Deliberately no dispose-on-unmount and no useGLTF.clear() here. StrictMode
     double-invokes effect cleanups while the component is still mounted, so
     either one would tear down assets the immediate remount still points at —
     clearing the cache re-suspends the loader, which clears again, and the GLB
     refetches forever. See the same warning on releaseIntroAssets() in
     components/intro/RackModel.tsx. The stage lives for the page's lifetime;
     GPU memory dies with the canvas context. */

  useEffect(() => viewer.subscribePhase(setPhase), []);

  /* The stage stays mounted for the page's lifetime, so the render loop only
     runs while it is actually near the viewport — frameloop flips to "never"
     the moment the section scrolls away, instead of drawing a dead scene at
     full rate under the rest of the page. */
  useEffect(() => {
    const node = rootRef.current;
    if (!node) return;
    if (typeof IntersectionObserver === "undefined") return;

    const observer = new IntersectionObserver(
      (entries) => setInView(entries.some((entry) => entry.isIntersecting)),
      { rootMargin: "160px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelectedId(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const selectedPart = selectedId
    ? (assembly?.byId.get(selectedId) ?? null)
    : null;

  return (
    <div
      ref={rootRef}
      className={
        "absolute inset-0 transition-opacity duration-1000 " +
        (assembly ? "opacity-100" : "opacity-0")
      }
    >
      <Canvas
        frameloop={inView ? "always" : "never"}
        dpr={[1, 2]}
        gl={{ antialias: true, powerPreference: "high-performance" }}
        camera={{ fov: 38, position: [3.4, 2.2, 4.6], near: 0.1, far: 80 }}
        onPointerMissed={() => setSelectedId(null)}
        /* Vertical swipes scroll the page; horizontal drags orbit the model. */
        style={{ touchAction: "pan-y" }}
      >
        <Lights />
        <Loader onReady={handleReady} />

        {assembly && explode && (
          <>
            <FrameDriver reducedMotion={reducedMotion} />
            <AssemblyView
              assembly={assembly}
              explode={explode}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
            <CameraRig
              assembly={assembly}
              explode={explode}
              selectedId={selectedId}
              reducedMotion={reducedMotion}
            />
            <Projector
              assembly={assembly}
              explode={explode}
              handles={handles}
              selectedId={selectedId}
            />
            <BakedShadows assembly={assembly} />
          </>
        )}
      </Canvas>

      {assembly && (
        <Markers
          assembly={assembly}
          handles={handles}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
      )}

      <PartPanel part={selectedPart} onClose={() => setSelectedId(null)} />

      <div
        className={
          /* On <md the part panel is a bottom sheet the pill would cover, so
             the controls yield to it while a part is selected. */
          "pointer-events-none absolute inset-x-0 bottom-8 z-30 justify-center px-5 md:bottom-10 " +
          (selectedPart ? "hidden md:flex" : "flex")
        }
      >
        <ExplodeControls phase={phase} disabled={!assembly} />
      </div>
    </div>
  );
}
