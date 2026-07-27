/**
 * Turns the loaded GLB into render-ready parts, then solves the explode.
 *
 * The source assembly is 864 primitive meshes split by face colour across 32
 * parts. Each part's primitives are baked into world space, grouped by
 * material and merged, which takes the draw call count to ~43 while leaving
 * every part independently transformable and independently fadeable.
 *
 * Geometry is built once. The explode solution is derived separately and
 * cheaply, so editing src/config/explode.ts re-solves on hot reload without
 * re-merging a single triangle.
 */

import * as THREE from 'three'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'

import { UP_AXIS_CORRECTION, buildPartResolver, collectPartNodes, prefixOf } from './identity.js'
import { buildGroups, type PartFacts, type PartGroup, type Vec3 } from './grouping'
import type { ExplodeConfig } from '../config/explode'

/**
 * Onshape writes metallicFactor 0 and no roughness, which renders as flat
 * clay. These keep the CAD base colours but give the surfaces something to
 * catch the key light with.
 */
const SURFACE_ROUGHNESS = 0.52
const SURFACE_METALNESS = 0.18

/**
 * Only what the builder actually needs from a loaded glTF. three/examples and
 * three-stdlib each ship their own GLTF type and drei returns the latter;
 * depending on the shape rather than either declaration keeps them out of it.
 */
export interface LoadedGLTF {
  scene: THREE.Object3D
  parser: {
    json: { nodes: { mesh?: number }[] }
    associations: Map<any, any>
  }
}

export interface BuiltPart {
  id: string
  nodeName: string
  facts: PartFacts
  triangles: number
  primitives: number
  /** Merged meshes at the origin — geometry is baked in world space. */
  object: THREE.Group
  materials: THREE.MeshStandardMaterial[]
  /** World-space centre at t = 0. */
  center: THREE.Vector3
  size: THREE.Vector3
}

export interface BuiltAssembly {
  parts: BuiltPart[]
  byId: Map<string, BuiltPart>
  center: THREE.Vector3
  size: THREE.Vector3
  box: THREE.Box3
  stats: { parts: number; primitives: number; triangles: number; drawCalls: number }
  dispose: () => void
}

export interface ExplodeSolution {
  groups: Map<string, PartGroup>
  /** Full displacement at t = 1, per part id. */
  offsets: Map<string, THREE.Vector3>
  groupOf: Map<string, PartGroup>
}

function triangleCount(geometry: THREE.BufferGeometry): number {
  if (geometry.index) return geometry.index.count / 3
  const position = geometry.getAttribute('position')
  return position ? position.count / 3 : 0
}

/**
 * mergeGeometries requires an identical attribute set across inputs. Onshape
 * emits position + normal on every primitive, but a stray extra attribute (or
 * a mix of indexed and non-indexed) would otherwise fail the merge.
 */
function normalizeForMerge(geometries: THREE.BufferGeometry[]): THREE.BufferGeometry[] {
  const allIndexed = geometries.every((geometry) => geometry.index !== null)

  return geometries.map((geometry) => {
    for (const name of Object.keys(geometry.attributes)) {
      if (name !== 'position' && name !== 'normal') geometry.deleteAttribute(name)
    }
    if (!geometry.getAttribute('normal')) geometry.computeVertexNormals()
    if (allIndexed) return geometry
    const flat = geometry.toNonIndexed()
    geometry.dispose()
    return flat
  })
}

export function buildAssembly(gltf: LoadedGLTF): BuiltAssembly {
  const scene = gltf.scene
  scene.updateMatrixWorld(true)

  const correction = new THREE.Matrix4()
  if (UP_AXIS_CORRECTION) {
    correction.makeRotationFromEuler(new THREE.Euler(...UP_AXIS_CORRECTION.euler))
  }

  const resolver = buildPartResolver(gltf)
  const nodes = collectPartNodes(scene, resolver)

  const ownedGeometries: THREE.BufferGeometry[] = []
  const ownedMaterials: THREE.Material[] = []

  const parts: BuiltPart[] = []
  const worldMatrix = new THREE.Matrix4()

  for (const node of nodes) {
    // Bucket this part's primitives by source material.
    const byMaterial = new Map<string, { material: THREE.Material; geometries: THREE.BufferGeometry[] }>()
    let primitives = 0

    node.object.traverse((child: THREE.Object3D) => {
      const mesh = child as THREE.Mesh
      if (!mesh.isMesh || !mesh.geometry) return
      primitives++

      const material = Array.isArray(mesh.material) ? mesh.material[0] : mesh.material
      const clone = mesh.geometry.clone()
      worldMatrix.multiplyMatrices(correction, mesh.matrixWorld)
      clone.applyMatrix4(worldMatrix)

      const bucket = byMaterial.get(material.uuid)
      if (bucket) bucket.geometries.push(clone)
      else byMaterial.set(material.uuid, { material, geometries: [clone] })
    })

    if (!primitives) continue

    const group = new THREE.Group()
    group.name = node.id
    const materials: THREE.MeshStandardMaterial[] = []
    let triangles = 0

    for (const bucket of byMaterial.values()) {
      const normalized = normalizeForMerge(bucket.geometries)
      const merged = normalized.length === 1 ? normalized[0] : mergeGeometries(normalized, false)
      if (normalized.length > 1) for (const geometry of normalized) geometry.dispose()
      if (!merged) continue

      merged.computeBoundingBox()
      merged.computeBoundingSphere()
      ownedGeometries.push(merged)
      triangles += triangleCount(merged)

      // One material instance per (part, source material): opacity animates
      // per part, so instances cannot be shared across parts.
      const source = bucket.material as THREE.MeshStandardMaterial
      const material = new THREE.MeshStandardMaterial({
        color: source.color?.clone() ?? new THREE.Color(0xb8bec6),
        roughness: SURFACE_ROUGHNESS,
        metalness: SURFACE_METALNESS,
      })
      ownedMaterials.push(material)
      materials.push(material)

      const mesh = new THREE.Mesh(merged, material)
      mesh.userData.partId = node.id
      group.add(mesh)
    }

    const box = new THREE.Box3().setFromObject(group)
    const center = box.getCenter(new THREE.Vector3())

    parts.push({
      id: node.id,
      nodeName: node.nodeName,
      triangles,
      primitives,
      object: group,
      materials,
      center,
      size: box.getSize(new THREE.Vector3()),
      facts: {
        id: node.id,
        nodeName: node.nodeName,
        prefix: prefixOf(node.nodeName),
        assemblyPath: node.assemblyPath,
        meshIndex: node.meshIndex,
        center: center.toArray() as Vec3,
        min: box.min.toArray() as Vec3,
        max: box.max.toArray() as Vec3,
      },
    })
  }

  const box = new THREE.Box3()
  for (const part of parts) {
    box.expandByPoint(new THREE.Vector3(...part.facts.min))
    box.expandByPoint(new THREE.Vector3(...part.facts.max))
  }

  return {
    parts,
    byId: new Map(parts.map((part) => [part.id, part])),
    center: box.getCenter(new THREE.Vector3()),
    size: box.getSize(new THREE.Vector3()),
    box,
    stats: {
      parts: parts.length,
      primitives: parts.reduce((sum, part) => sum + part.primitives, 0),
      triangles: parts.reduce((sum, part) => sum + part.triangles, 0),
      drawCalls: parts.reduce((sum, part) => sum + part.object.children.length, 0),
    },
    dispose: () => {
      for (const geometry of ownedGeometries) geometry.dispose()
      for (const material of ownedMaterials) material.dispose()
    },
  }
}

/** Cheap. Re-run whenever the explode config changes. */
export function resolveExplode(
  assembly: BuiltAssembly,
  config: ExplodeConfig
): ExplodeSolution {
  const facts = assembly.parts.map((part) => part.facts)
  const { keys, groups } = buildGroups(facts, assembly.center.toArray() as Vec3, config)

  const offsets = new Map<string, THREE.Vector3>()
  const groupOf = new Map<string, PartGroup>()

  for (const part of assembly.parts) {
    const group = groups.get(keys.get(part.id)!)!
    const offset = new THREE.Vector3(...group.offset)
    offsets.set(part.id, offset)
    groupOf.set(part.id, group)
  }

  return { groups, offsets, groupOf }
}
