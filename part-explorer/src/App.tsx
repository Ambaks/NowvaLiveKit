import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useProgress } from '@react-three/drei'

import { explodeConfig } from './config/explode'
import { resolveExplode, type BuiltAssembly } from './lib/assembly'
import { useReducedMotion } from './lib/useReducedMotion'
import { viewer, type SequencePhase } from './lib/viewerStore'
import { Controls } from './components/Controls'
import { InfoPanel } from './components/InfoPanel'
import { Markers } from './components/Markers'
import { Viewer } from './components/Viewer'
import { createMarkerHandles } from './components/markerHandles'

const KEYBOARD_STEP = 0.05

const initialSelection = () =>
  new URLSearchParams(window.location.search).get('part')

export default function App() {
  const [assembly, setAssembly] = useState<BuiltAssembly | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(initialSelection)
  const [phase, setPhase] = useState<SequencePhase>('idle')

  const handles = useRef(createMarkerHandles())
  const live = useRef<BuiltAssembly | null>(null)
  const reducedMotion = useReducedMotion()
  const { active, progress } = useProgress()

  // Offsets are cheap to re-derive, so editing src/config/explode.ts re-solves
  // the explode on hot reload without rebuilding a single merged geometry.
  const explode = useMemo(
    () => (assembly ? resolveExplode(assembly, explodeConfig) : null),
    [assembly]
  )

  const handleReady = useCallback((next: BuiltAssembly) => {
    if (live.current === next) return
    live.current?.dispose()
    live.current = next
    setAssembly(next)
  }, [])

  useEffect(() => () => {
    live.current?.dispose()
    live.current = null
  }, [])

  useEffect(() => viewer.subscribePhase(setPhase), [])

  // A deep link to a part that is not in this GLB should not leave the viewer
  // in a phantom selected state.
  useEffect(() => {
    if (assembly && selectedId && !assembly.byId.has(selectedId)) setSelectedId(null)
  }, [assembly, selectedId])

  useEffect(() => {
    const url = new URL(window.location.href)
    if (selectedId) url.searchParams.set('part', selectedId)
    else url.searchParams.delete('part')
    window.history.replaceState(null, '', url)
  }, [selectedId])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setSelectedId(null)
        return
      }

      // The range input handles its own arrow keys and fires input events.
      const target = event.target as HTMLElement | null
      if (target?.tagName === 'INPUT' || target?.isContentEditable) return

      const step =
        event.key === 'ArrowRight' || event.key === 'ArrowUp'
          ? KEYBOARD_STEP
          : event.key === 'ArrowLeft' || event.key === 'ArrowDown'
            ? -KEYBOARD_STEP
            : 0
      if (!step) return

      event.preventDefault()
      viewer.setT(viewer.getT() + step)
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const selectedPart = selectedId ? (assembly?.byId.get(selectedId) ?? null) : null

  return (
    <div className="relative flex h-full w-full flex-col overflow-hidden bg-ink">
      <header className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-between gap-4 px-5 py-4 sm:px-6">
        <div>
          <h1 className="font-mono text-[11px] uppercase tracking-[0.22em] text-fg">
            Nowva <span className="text-accent">rack</span>
          </h1>
          <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.16em] text-faint">
            exploded assembly
          </p>
        </div>

        {assembly && import.meta.env.DEV && (
          <p className="hidden text-right font-mono text-[10px] leading-relaxed tracking-[0.12em] text-faint sm:block">
            {assembly.stats.parts} parts · {assembly.stats.drawCalls} draw calls
            <br />
            {assembly.stats.triangles.toLocaleString()} tris
          </p>
        )}
      </header>

      <div className="relative min-h-0 flex-1">
        <Viewer
          assembly={assembly}
          explode={explode}
          selectedId={selectedId}
          reducedMotion={reducedMotion}
          handles={handles}
          onReady={handleReady}
          onSelect={setSelectedId}
        />

        {assembly && (
          <Markers
            assembly={assembly}
            handles={handles}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        )}

        <InfoPanel
          part={selectedPart}
          group={selectedId ? (explode?.groupOf.get(selectedId) ?? null) : null}
          onClose={() => setSelectedId(null)}
        />

        {active && (
          <p
            className="pointer-events-none absolute bottom-4 left-5 font-mono text-[10px] uppercase tracking-[0.18em] text-faint sm:left-6"
            role="status"
          >
            loading {Math.round(progress)}%
          </p>
        )}
      </div>

      <Controls phase={phase} disabled={!assembly} />
    </div>
  )
}
