/**
 * The canvas. Suspense falls back to null rather than a blocking spinner, so
 * the chrome and the lit ground render immediately and the assembly appears
 * as soon as it has streamed in.
 */

import { Suspense, useEffect, useMemo, type RefObject } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { ContactShadows, Grid, useGLTF } from '@react-three/drei'

import { explodeConfig } from '../config/explode'
import { buildAssembly, type BuiltAssembly, type ExplodeSolution } from '../lib/assembly'
import { viewer } from '../lib/viewerStore'
import { AssemblyView } from './AssemblyView'
import { CameraRig } from './CameraRig'
import { Projector } from './Projector'
import type { MarkerHandles } from './markerHandles'

const MODEL_URL = '/models/rack.glb'

interface Props {
  assembly: BuiltAssembly | null
  explode: ExplodeSolution | null
  selectedId: string | null
  reducedMotion: boolean
  handles: RefObject<MarkerHandles>
  onReady: (assembly: BuiltAssembly) => void
  onSelect: (id: string | null) => void
}

function Loader({ onReady }: { onReady: (assembly: BuiltAssembly) => void }) {
  const gltf = useGLTF(MODEL_URL)
  const assembly = useMemo(() => buildAssembly(gltf), [gltf])

  useEffect(() => {
    onReady(assembly)
  }, [assembly, onReady])

  return null
}

/** Advances the run sequence once per frame, ahead of everything that reads t. */
function FrameDriver({ reducedMotion }: { reducedMotion: boolean }) {
  useFrame((_, delta) => {
    viewer.advance(delta, explodeConfig, !reducedMotion)
  }, -2)
  return null
}

function Lights() {
  return (
    <>
      <hemisphereLight args={['#cfd4ff', '#14131a', 1.1]} />
      <directionalLight position={[4, 7, 5]} intensity={2.1} color="#fff6e8" />
      <directionalLight position={[-6, 3, -2]} intensity={0.7} color="#8fa8ff" />
      <directionalLight position={[0, 2, -7]} intensity={0.5} color="#c9b6ff" />
    </>
  )
}

export function Viewer({
  assembly,
  explode,
  selectedId,
  reducedMotion,
  handles,
  onReady,
  onSelect,
}: Props) {
  const ground = assembly ? assembly.box.min.y : 0
  const span = assembly ? Math.max(assembly.size.x, assembly.size.z) : 4

  return (
    <Canvas
      dpr={[1, 2]}
      gl={{ antialias: true, powerPreference: 'high-performance' }}
      camera={{ fov: 38, position: [3.4, 2.2, 4.6], near: 0.1, far: 80 }}
      onPointerMissed={() => onSelect(null)}
    >
      <color attach="background" args={['#09090e']} />
      <Lights />

      <Suspense fallback={null}>
        <Loader onReady={onReady} />
      </Suspense>

      {assembly && explode && (
        <>
          <FrameDriver reducedMotion={reducedMotion} />
          <AssemblyView
            assembly={assembly}
            explode={explode}
            selectedId={selectedId}
            onSelect={onSelect}
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

          <Grid
            position={[assembly.center.x, ground - 0.002, assembly.center.z]}
            args={[span * 4, span * 4]}
            cellSize={0.1}
            cellThickness={0.5}
            cellColor="#2e2b3b"
            sectionSize={0.5}
            sectionThickness={0.9}
            sectionColor="#4a4560"
            fadeDistance={span * 3.2}
            fadeStrength={1.6}
            infiniteGrid
          />
          <ContactShadows
            position={[assembly.center.x, ground + 0.001, assembly.center.z]}
            scale={span * 2.4}
            resolution={512}
            blur={2.6}
            opacity={0.5}
            far={span}
          />
        </>
      )}
    </Canvas>
  )
}

useGLTF.preload(MODEL_URL)
