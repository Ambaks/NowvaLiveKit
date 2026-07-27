/**
 * Renders the merged parts and drives their transforms.
 *
 * Positions are written straight onto the three.js objects inside useFrame, so
 * dragging the scrub moves the model in the same frame as the pointer event —
 * no React state, no easing between the finger and the geometry.
 */

import { useEffect, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import type { ThreeEvent } from '@react-three/fiber'
import type * as THREE from 'three'

import { explodeConfig } from '../config/explode'
import type { BuiltAssembly, ExplodeSolution } from '../lib/assembly'
import { viewer } from '../lib/viewerStore'

/** Per-second convergence of the selection fade. */
const FADE_HALFLIFE = 0.0001

interface Props {
  assembly: BuiltAssembly
  explode: ExplodeSolution
  selectedId: string | null
  onSelect: (id: string | null) => void
}

export function AssemblyView({ assembly, explode, selectedId, onSelect }: Props) {
  const opacities = useRef(new Map<string, number>()).current
  const hovered = useRef(false)

  useEffect(() => {
    return () => {
      document.body.style.cursor = ''
    }
  }, [])

  useFrame((_, delta) => {
    const t = viewer.getT()
    const ease = 1 - Math.pow(FADE_HALFLIFE, Math.min(delta, 0.1))

    for (const part of assembly.parts) {
      const offset = explode.offsets.get(part.id)
      if (offset) part.object.position.copy(offset).multiplyScalar(t)

      const target =
        !selectedId || selectedId === part.id ? 1 : explodeConfig.dimmedOpacity
      const current = opacities.get(part.id) ?? 1
      if (Math.abs(target - current) < 0.002) {
        if (current !== target) {
          opacities.set(part.id, target)
          applyOpacity(part.materials, target)
        }
        continue
      }

      const next = current + (target - current) * ease
      opacities.set(part.id, next)
      applyOpacity(part.materials, next)
    }
  })

  const setCursor = (on: boolean) => {
    if (hovered.current === on) return
    hovered.current = on
    document.body.style.cursor = on ? 'pointer' : ''
  }

  return (
    <>
      {assembly.parts.map((part) => (
        <primitive
          key={part.id}
          object={part.object}
          onClick={(event: ThreeEvent<MouseEvent>) => {
            event.stopPropagation()
            onSelect(part.id === selectedId ? null : part.id)
          }}
          onPointerOver={(event: ThreeEvent<PointerEvent>) => {
            event.stopPropagation()
            setCursor(true)
          }}
          onPointerOut={() => setCursor(false)}
        />
      ))}
    </>
  )
}

function applyOpacity(materials: THREE.MeshStandardMaterial[], opacity: number) {
  const transparent = opacity < 0.999
  for (const material of materials) {
    if (material.transparent !== transparent) {
      material.transparent = transparent
      material.depthWrite = !transparent
      // `transparent` is part of the cached program key. Flipping it after the
      // material has rendered once is silently ignored without this — opacity
      // updates fine and the part still draws fully solid.
      material.needsUpdate = true
    }
    material.opacity = opacity
  }
}
