/**
 * Orbit controls, the eased look-at target, and the run sequence's camera
 * sweep. Manual input cancels a running sequence.
 */

import { useEffect, useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import * as THREE from 'three'

import type { BuiltAssembly, ExplodeSolution } from '../lib/assembly'
import { viewer, type SequencePhase } from '../lib/viewerStore'

const FRAMING_MARGIN = 1.08
/**
 * Framing the assembled extents alone leaves parts outside the frame at t = 1;
 * framing the exploded extents leaves the assembled rack marooned in the
 * middle. Fit something between the two so the whole scrub range reads.
 */
const FRAMING_EXPLODE_BLEND = 0.5
const TARGET_HALFLIFE = 0.0015

const ORIGIN = new THREE.Vector3()

interface Props {
  assembly: BuiltAssembly
  explode: ExplodeSolution
  selectedId: string | null
  reducedMotion: boolean
}

export function CameraRig({ assembly, explode, selectedId, reducedMotion }: Props) {
  const controls = useRef<OrbitControlsImpl>(null)
  const camera = useThree((state) => state.camera)
  const desired = useRef(new THREE.Vector3())
  const baseAzimuth = useRef(0)
  const lastPhase = useRef<SequencePhase>('idle')

  useEffect(() => {
    const perspective = camera as THREE.PerspectiveCamera
    const halfFov = (perspective.fov * THREE.MathUtils.DEG2RAD) / 2

    // Fitting per world axis is wrong for an angled view — the silhouette of a
    // diagonally-viewed box is wider than any single axis. Measure the model
    // on the camera's own right/up axes instead, evaluated part-way through the
    // explode so both ends of the scrub stay in frame.
    const direction = new THREE.Vector3(0.62, 0.34, 1).normalize()
    const right = new THREE.Vector3()
      .crossVectors(new THREE.Vector3(0, 1, 0), direction)
      .normalize()
    const up = new THREE.Vector3().crossVectors(direction, right).normalize()

    const corner = new THREE.Vector3()
    let halfWidth = 0
    let halfHeight = 0
    let towardCamera = 0

    for (const part of assembly.parts) {
      const offset = explode.offsets.get(part.id) ?? ORIGIN
      const { min, max } = part.facts
      for (let bit = 0; bit < 8; bit++) {
        corner
          .set(
            bit & 1 ? max[0] : min[0],
            bit & 2 ? max[1] : min[1],
            bit & 4 ? max[2] : min[2]
          )
          .addScaledVector(offset, FRAMING_EXPLODE_BLEND)
          .sub(assembly.center)

        halfWidth = Math.max(halfWidth, Math.abs(corner.dot(right)))
        halfHeight = Math.max(halfHeight, Math.abs(corner.dot(up)))
        towardCamera = Math.max(towardCamera, corner.dot(direction))
      }
    }

    const distance =
      Math.max(halfHeight / Math.tan(halfFov), halfWidth / (Math.tan(halfFov) * perspective.aspect)) *
        FRAMING_MARGIN +
      towardCamera

    camera.position.copy(assembly.center).addScaledVector(direction, distance)
    perspective.near = Math.max(0.05, distance / 200)
    perspective.far = distance * 12
    perspective.updateProjectionMatrix()

    desired.current.copy(assembly.center)
    controls.current?.target.copy(assembly.center)
  }, [assembly, explode, camera])

  useFrame((_, delta) => {
    const orbit = controls.current
    if (!orbit) return

    const t = viewer.getT()

    if (selectedId) {
      const part = assembly.byId.get(selectedId)
      if (part) {
        desired.current.copy(part.center)
        const offset = explode.offsets.get(selectedId)
        if (offset) desired.current.addScaledVector(offset, t)
      }
    } else {
      desired.current.copy(assembly.center)
    }

    orbit.target.lerp(desired.current, 1 - Math.pow(TARGET_HALFLIFE, Math.min(delta, 0.1)))

    const phase = viewer.getPhase()
    if (phase !== 'idle') {
      if (lastPhase.current === 'idle') baseAzimuth.current = orbit.getAzimuthalAngle()
      if (!reducedMotion) {
        orbit.setAzimuthalAngle(baseAzimuth.current + viewer.orbit)
        orbit.update()
      }
    }
    lastPhase.current = phase
  })

  return (
    <OrbitControls
      ref={controls}
      makeDefault
      enableDamping
      dampingFactor={0.08}
      enablePan={false}
      minDistance={assembly.size.length() * 0.18}
      maxDistance={assembly.size.length() * 3}
      maxPolarAngle={Math.PI * 0.495}
      onStart={() => viewer.cancelSequence()}
    />
  )
}
