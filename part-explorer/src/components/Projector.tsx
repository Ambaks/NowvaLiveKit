/**
 * Projects part centres to screen space each frame and writes the result
 * straight into the marker DOM nodes. Nothing here touches React state.
 */

import { useRef, type RefObject } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'

import { explodeConfig } from '../config/explode'
import type { BuiltAssembly, ExplodeSolution } from '../lib/assembly'
import { viewer } from '../lib/viewerStore'
import { LEADER_RISE, LEADER_RUN, type MarkerHandles } from './markerHandles'

const FADE_RANGE = 0.12

interface Props {
  assembly: BuiltAssembly
  explode: ExplodeSolution
  handles: RefObject<MarkerHandles>
  selectedId: string | null
}

export function Projector({ assembly, explode, handles, selectedId }: Props) {
  const camera = useThree((state) => state.camera)
  const size = useThree((state) => state.size)
  const world = useRef(new THREE.Vector3()).current
  const shown = useRef(new Map<string, boolean>()).current

  useFrame(() => {
    const t = viewer.getT()
    const gate = explodeConfig.markerThreshold
    const fade = THREE.MathUtils.clamp((t - gate) / FADE_RANGE, 0, 1)

    let selectedScreen: { x: number; y: number } | null = null

    for (const part of assembly.parts) {
      const dot = handles.current.dots.get(part.id)
      if (!dot) continue

      const offset = explode.offsets.get(part.id)
      world.copy(part.center)
      if (offset) world.addScaledVector(offset, t)
      world.project(camera)

      const isSelected = selectedId === part.id
      const onScreen = world.z < 1
      const visible = onScreen && (fade > 0 || isSelected)

      if (shown.get(part.id) !== visible) {
        shown.set(part.id, visible)
        dot.style.visibility = visible ? 'visible' : 'hidden'
        dot.tabIndex = visible ? 0 : -1
      }
      if (!visible) continue

      const x = (world.x * 0.5 + 0.5) * size.width
      const y = (-world.y * 0.5 + 0.5) * size.height

      dot.style.transform = `translate3d(${x}px, ${y}px, 0) translate(-50%, -50%)`
      dot.style.opacity = String(isSelected ? 1 : 0.28 + 0.42 * fade)

      if (isSelected) selectedScreen = { x, y }
    }

    // ------------------------------------------------------- leader line
    const label = handles.current.label
    const leader = handles.current.leader
    if (!label || !leader) return

    if (!selectedScreen) {
      label.style.visibility = 'hidden'
      leader.style.visibility = 'hidden'
      return
    }

    const flip = selectedScreen.x > size.width - 220
    const direction = flip ? -1 : 1
    const kinkX = selectedScreen.x + LEADER_RISE * direction
    const kinkY = selectedScreen.y - LEADER_RISE
    const endX = kinkX + LEADER_RUN * direction

    leader.setAttribute(
      'points',
      `${selectedScreen.x},${selectedScreen.y} ${kinkX},${kinkY} ${endX},${kinkY}`
    )
    leader.style.visibility = 'visible'

    label.style.transform =
      `translate3d(${endX}px, ${kinkY}px, 0) ` +
      `translate(${flip ? '-100%' : '0'}, -50%)`
    label.style.visibility = 'visible'
  })

  return null
}
