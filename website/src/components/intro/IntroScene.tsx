"use client";

import {
  Component,
  Suspense,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Canvas } from "@react-three/fiber";
import { ContactShadows, Environment, Lightformer } from "@react-three/drei";
import { CameraRig } from "./CameraRig";
import { RackModel } from "./RackModel";
import { CAMERA_FOV_DEG, PAN_DURATION_MS, type Framing } from "./introTimeline";

export { preloadIntroAssets, releaseIntroAssets } from "./RackModel";

export interface IntroSceneProps {
  onDone: () => void;
  onError?: (error: unknown) => void;
  durationMs?: number;
  loadTimeoutMs?: number;
}

class SceneErrorBoundary extends Component<
  { onError?: (error: unknown) => void; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    this.props.onError?.(error);
  }

  render() {
    return this.state.failed ? null : this.props.children;
  }
}

/* ContactShadows can't read the framing ref reactively; this mounts it once
   the model has been measured. Rendered after RackModel so its layout effect
   runs second and the ref is already populated. */
function GroundShadow({
  framingRef,
}: {
  framingRef: { current: Framing | null };
}) {
  const [groundY, setGroundY] = useState<number | null>(null);

  useLayoutEffect(() => {
    if (framingRef.current) setGroundY(framingRef.current.groundY);
  }, [framingRef]);

  if (groundY === null) return null;
  return (
    <ContactShadows
      position={[0, groundY + 0.001, 0]}
      opacity={0.5}
      scale={6}
      blur={2.4}
      far={2.2}
      resolution={512}
      frames={1}
      color="#000000"
    />
  );
}

/* Full-screen 3D pan around the rack. Transparent canvas over the
   orchestrator's #09090e backdrop so tone mapping never shifts the
   background; fades itself in on the first framed render. */
export default function IntroScene({
  onDone,
  onError,
  durationMs = PAN_DURATION_MS,
  loadTimeoutMs = 8000,
}: IntroSceneProps) {
  const [ready, setReady] = useState(false);
  const framingRef = useRef<Framing | null>(null);
  const onErrorRef = useRef(onError);

  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  useEffect(() => {
    if (ready) return;
    const watchdog = window.setTimeout(
      () => onErrorRef.current?.(new Error("intro-scene-load-timeout")),
      loadTimeoutMs,
    );
    return () => window.clearTimeout(watchdog);
  }, [ready, loadTimeoutMs]);

  return (
    <SceneErrorBoundary onError={onError}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          opacity: ready ? 1 : 0,
          transition: "opacity 400ms ease-out",
        }}
      >
        <Canvas
          dpr={[1, 2]}
          gl={{
            antialias: true,
            alpha: true,
            powerPreference: "high-performance",
            stencil: false,
          }}
          camera={{ fov: CAMERA_FOV_DEG, near: 0.1, far: 50 }}
          frameloop="always"
          onCreated={({ gl }) => {
            gl.domElement.addEventListener("webglcontextlost", (event) => {
              event.preventDefault();
              onErrorRef.current?.(new Error("webgl-context-lost"));
            });
          }}
        >
          <SceneErrorBoundary onError={onError}>
            <Suspense fallback={null}>
              <RackModel framingRef={framingRef} />
              <hemisphereLight args={["#5b4a91", "#09090e", 0.35]} />
              <directionalLight
                position={[3.5, 4.2, 2.5]}
                intensity={2.4}
                color="#ffffff"
              />
              <directionalLight
                position={[-4, 1.5, 2]}
                intensity={0.5}
                color="#c4b5fd"
              />
              <directionalLight
                position={[-1.5, 3, -4]}
                intensity={1.8}
                color="#7c3aed"
              />
              <Environment resolution={256} frames={1}>
                <Lightformer
                  form="rect"
                  intensity={2}
                  color="#ffffff"
                  scale={[4, 2, 1]}
                  position={[0, 4, 0]}
                  rotation={[-Math.PI / 2, 0, 0]}
                />
                <Lightformer
                  form="rect"
                  intensity={1.5}
                  color="#7c3aed"
                  scale={[6, 1, 1]}
                  position={[0, 1.5, -4]}
                />
              </Environment>
              <GroundShadow framingRef={framingRef} />
              <CameraRig
                framingRef={framingRef}
                durationMs={durationMs}
                onFirstFrame={() => setReady(true)}
                onDone={onDone}
              />
            </Suspense>
          </SceneErrorBoundary>
        </Canvas>
      </div>
    </SceneErrorBoundary>
  );
}
