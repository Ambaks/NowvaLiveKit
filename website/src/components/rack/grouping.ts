/* Ported from part-explorer/. Tune the explode there with `npm run inspect`,
   then copy explode.ts / grouping.ts / assembly.ts across. */
/**
 * Group resolution and explode offsets. Pure functions over geometry facts —
 * no three.js, no React — so the tuning behaviour can be reasoned about (and
 * tested) without a renderer.
 */

import type { ExplodeConfig } from './explode'

export type Vec3 = [number, number, number]

export interface PartFacts {
  id: string
  nodeName: string
  prefix: string
  assemblyPath: string[]
  meshIndex: number | null
  center: Vec3
  min: Vec3
  max: Vec3
}

export interface PartGroup {
  key: string
  label: string
  memberIds: string[]
  center: Vec3
  offset: Vec3
}

const AXIS_INDEX = { x: 0, y: 1, z: 2 } as const

const distance = (a: Vec3, b: Vec3) =>
  Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])

/** Single-linkage clustering: a part joins a cluster if it is within
 *  `threshold` of any member, so a run of stacked plates chains together. */
function clusterByProximity(parts: PartFacts[], threshold: number): PartFacts[][] {
  const pending = [...parts]
  const clusters: PartFacts[][] = []

  while (pending.length) {
    const cluster = [pending.pop()!]
    let grew = true
    while (grew) {
      grew = false
      for (let i = pending.length - 1; i >= 0; i--) {
        if (cluster.some((member) => distance(member.center, pending[i].center) <= threshold)) {
          cluster.push(pending.splice(i, 1)[0])
          grew = true
        }
      }
    }
    clusters.push(cluster)
  }

  return clusters
}

/**
 * Maps every part id to a group key. Parts sharing a key share one offset and
 * move as a unit.
 *
 * composite resolution order:
 *   1. explicit override from config
 *   2. subassembly path, when the part sits below the root assembly
 *   3. proximity cluster among parts that reuse the same glTF mesh
 *   4. the part on its own
 */
export function resolveGroupKeys(
  parts: PartFacts[],
  config: ExplodeConfig
): Map<string, string> {
  const keys = new Map<string, string>()

  if (config.strategy === 'none') {
    for (const part of parts) keys.set(part.id, config.groupOverrides[part.id] ?? part.id)
    return keys
  }

  if (config.strategy === 'prefix') {
    for (const part of parts) {
      keys.set(part.id, config.groupOverrides[part.id] ?? `prefix:${part.prefix}`)
    }
    return keys
  }

  if (config.strategy === 'subassembly') {
    for (const part of parts) {
      keys.set(part.id, config.groupOverrides[part.id] ?? `sub:${part.assemblyPath.join('/')}`)
    }
    return keys
  }

  // composite
  const remaining: PartFacts[] = []
  for (const part of parts) {
    const override = config.groupOverrides[part.id]
    if (override) keys.set(part.id, override)
    else if (part.assemblyPath.length > 1) keys.set(part.id, `sub:${part.assemblyPath.join('/')}`)
    else remaining.push(part)
  }

  const byMesh = new Map<number, PartFacts[]>()
  for (const part of remaining) {
    if (part.meshIndex === null) continue
    const bucket = byMesh.get(part.meshIndex)
    if (bucket) bucket.push(part)
    else byMesh.set(part.meshIndex, [part])
  }

  for (const part of remaining) {
    const siblings = part.meshIndex === null ? undefined : byMesh.get(part.meshIndex)
    if (!siblings || siblings.length < 2) {
      keys.set(part.id, part.id)
      continue
    }
    const cluster = clusterByProximity(siblings, config.repeatClusterDistance).find((members) =>
      members.some((member) => member.id === part.id)
    )!
    if (cluster.length < 2) {
      keys.set(part.id, part.id)
      continue
    }
    // Keyed on the lowest member id so the key is stable regardless of the
    // order clustering happened to visit parts in.
    const anchor = cluster.map((member) => member.id).sort()[0]
    keys.set(part.id, `repeat:${anchor}`)
  }

  return keys
}

function labelFor(key: string, members: PartFacts[]): string {
  if (members.length === 1) return members[0].nodeName
  if (key.startsWith('sub:')) return key.slice(4).split('/').pop() ?? key
  if (key.startsWith('prefix:')) return key.slice(7) || 'unprefixed'
  if (key.startsWith('repeat:')) return `${members[0].nodeName} ×${members.length}`
  return key
}

/**
 * Affine expansion about the assembly centroid. Parts scale outward from the
 * centre rather than translating along authored vectors.
 *
 *   offset = (groupCenter - assemblyCenter) * K
 */
export function buildGroups(
  parts: PartFacts[],
  assemblyCenter: Vec3,
  config: ExplodeConfig
): { keys: Map<string, string>; groups: Map<string, PartGroup> } {
  const keys = resolveGroupKeys(parts, config)

  const members = new Map<string, PartFacts[]>()
  for (const part of parts) {
    const key = keys.get(part.id)!
    const bucket = members.get(key)
    if (bucket) bucket.push(part)
    else members.set(key, [part])
  }

  const groups = new Map<string, PartGroup>()

  for (const [key, group] of members) {
    const min: Vec3 = [Infinity, Infinity, Infinity]
    const max: Vec3 = [-Infinity, -Infinity, -Infinity]
    for (const part of group) {
      for (let axis = 0; axis < 3; axis++) {
        min[axis] = Math.min(min[axis], part.min[axis])
        max[axis] = Math.max(max[axis], part.max[axis])
      }
    }

    const center: Vec3 = [
      (min[0] + max[0]) / 2,
      (min[1] + max[1]) / 2,
      (min[2] + max[2]) / 2,
    ]

    const offset: Vec3 = [
      (center[0] - assemblyCenter[0]) * config.k[0],
      (center[1] - assemblyCenter[1]) * config.k[1],
      (center[2] - assemblyCenter[2]) * config.k[2],
    ]

    const tuning = config.groupTuning[key]

    // An explicit axis implies snapping to it, whether or not the global snap
    // is on — asking for one axis means only that axis.
    if (config.dominantAxisSnap || tuning?.axis) {
      let kept: number = tuning?.axis ? AXIS_INDEX[tuning.axis] : 0
      if (!tuning?.axis) {
        for (let axis = 1; axis < 3; axis++) {
          if (Math.abs(offset[axis]) > Math.abs(offset[kept])) kept = axis
        }
      }
      for (let axis = 0; axis < 3; axis++) {
        if (axis !== kept) offset[axis] = 0
      }
    }

    if (tuning?.travel !== undefined) {
      for (let axis = 0; axis < 3; axis++) offset[axis] *= tuning.travel
    }

    groups.set(key, {
      key,
      label: labelFor(key, group),
      memberIds: group.map((part) => part.id),
      center,
      offset,
    })
  }

  return { keys, groups }
}
