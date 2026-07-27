/**
 * GLB inspection pass.
 *
 * Loads the assembly with GLTFLoader, walks the scene graph, prints the node
 * tree with triangle counts and world-space bounds, and writes
 * src/data/parts.generated.json (geometry facts only).
 *
 * Never writes src/data/parts.json — that file is hand-edited prose and is
 * merged with this output by id at runtime.
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

import {
  OCCURRENCE_PREFIX,
  UP_AXIS_CORRECTION,
  buildPartResolver,
  collectPartNodes,
  prefixOf,
} from '../src/lib/identity.js'

const HERE = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(HERE, '..')

const SOURCE_GLB = resolve(ROOT, '..', 'rack.glb')
const GENERATED_OUT = resolve(ROOT, 'src/data/parts.generated.json')
const CONTENT_FILE = resolve(ROOT, 'src/data/parts.json')

// ---------------------------------------------------------------- formatting

const num = (n) => n.toLocaleString('en-US')
const f3 = (n) => (n >= 0 ? ' ' : '') + n.toFixed(3)
const vec = (v) => `${f3(v.x)}, ${f3(v.y)}, ${f3(v.z)}`

function bar(n, max, width = 22) {
  const filled = max > 0 ? Math.max(1, Math.round((n / max) * width)) : 0
  return '#'.repeat(filled).padEnd(width, '.')
}

// ------------------------------------------------------------------ geometry

function triangleCount(mesh) {
  const geometry = mesh.geometry
  if (!geometry) return 0
  if (geometry.index) return geometry.index.count / 3
  const position = geometry.getAttribute('position')
  return position ? position.count / 3 : 0
}

function subtreeTriangles(object) {
  let total = 0
  object.traverse((child) => {
    if (child.isMesh) total += triangleCount(child)
  })
  return total
}

function subtreeMeshes(object) {
  const meshes = []
  object.traverse((child) => {
    if (child.isMesh) meshes.push(child)
  })
  return meshes
}

// ----------------------------------------------------------------- tree print

function printTree(root, resolver) {
  const lines = []

  const walk = (object, depth, isLast, prefixChars) => {
    // An occurrence wrapper is pure placement: same name, same bounds, one
    // child. Print the body it holds instead of both.
    if (OCCURRENCE_PREFIX.test(object.name ?? '') && object.children.length === 1) {
      walk(object.children[0], depth, isLast, prefixChars)
      return
    }

    const branch = depth === 0 ? '' : isLast ? '`-- ' : '|-- '
    const label = object.name || `<${object.type}>`
    const part = resolver.isPart(object)

    const box = new THREE.Box3().setFromObject(object)
    const size = box.isEmpty() ? new THREE.Vector3() : box.getSize(new THREE.Vector3())
    const tris = subtreeTriangles(object)

    const detail = tris ? `  ${num(tris).padStart(8)} tris   size ${vec(size)}` : ''
    lines.push(`${prefixChars}${branch}${label}${part ? ' *PART*' : ''}${detail}`)

    const childPrefix = prefixChars + (depth === 0 ? '' : isLast ? '    ' : '|   ')

    if (part) {
      const prims = subtreeMeshes(object).length
      if (prims > 1) lines.push(`${childPrefix}    (${prims} primitive meshes, collapsed)`)
      return
    }

    object.children.forEach((child, i) => {
      walk(child, depth + 1, i === object.children.length - 1, childPrefix)
    })
  }

  walk(root, 0, true, '')
  return lines
}

// --------------------------------------------------------------------- report

function groupBy(parts, keyFn) {
  const groups = new Map()
  for (const part of parts) {
    const key = keyFn(part)
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(part)
  }
  return [...groups.entries()].sort((a, b) => b[1].length - a[1].length)
}

function printGroups(title, groups, note) {
  console.log(`\n${title}`)
  if (note) console.log(`  ${note}`)
  const max = Math.max(...groups.map(([, members]) => members.length))
  for (const [key, members] of groups) {
    const label = key === '' ? '<empty>' : key
    const names = [...new Set(members.map((p) => p.nodeName))].join(', ')
    console.log(
      `  ${String(members.length).padStart(2)}  ${bar(members.length, max, 12)}  ` +
        `${label.padEnd(30)} ${names.length > 70 ? names.slice(0, 67) + '...' : names}`
    )
  }
  const singletons = groups.filter(([, m]) => m.length === 1).length
  console.log(
    `  -> ${groups.length} groups, ${singletons} singleton${singletons === 1 ? '' : 's'}`
  )
}

// ----------------------------------------------------------------------- main

async function main() {
  if (!existsSync(SOURCE_GLB)) {
    console.error(`Source GLB not found: ${SOURCE_GLB}`)
    process.exit(1)
  }

  const bytes = readFileSync(SOURCE_GLB)
  const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)

  const loader = new GLTFLoader()
  const gltf = await new Promise((res, rej) => loader.parse(buffer, '', res, rej))

  const scene = gltf.scene
  scene.updateMatrixWorld(true)
  const rawBox = new THREE.Box3().setFromObject(scene)

  // Measure in the same frame the viewer renders in.
  const root = new THREE.Group()
  root.add(scene)
  if (UP_AXIS_CORRECTION) root.rotation.set(...UP_AXIS_CORRECTION.euler)
  root.updateMatrixWorld(true)

  const resolver = buildPartResolver(gltf)
  const parts = collectPartNodes(scene, resolver).map((part) => {
    const meshes = subtreeMeshes(part.object)
    const box = new THREE.Box3().setFromObject(part.object)
    return {
      ...part,
      prefix: prefixOf(part.nodeName),
      primitives: meshes.length,
      triangles: meshes.reduce((sum, mesh) => sum + triangleCount(mesh), 0),
      materials: new Set(meshes.map((mesh) => mesh.material?.uuid)).size,
      center: box.getCenter(new THREE.Vector3()),
      size: box.getSize(new THREE.Vector3()),
      min: box.min.clone(),
      max: box.max.clone(),
    }
  })

  const assemblyBox = new THREE.Box3().setFromObject(root)
  const assemblyCenter = assemblyBox.getCenter(new THREE.Vector3())
  const assemblySize = assemblyBox.getSize(new THREE.Vector3())

  // ---------------------------------------------------------------- tree
  console.log('='.repeat(100))
  console.log(`NODE TREE  -  ${SOURCE_GLB}`)
  console.log(`generator: ${gltf.parser.json.asset?.generator ?? 'unknown'}`)
  console.log(
    `part detection: ${resolver.usingAssociations ? 'glTF node associations' : 'shape heuristic (associations unavailable)'}`
  )
  console.log('='.repeat(100))
  for (const line of printTree(scene, resolver)) console.log(line)

  // ------------------------------------------------------------- summary
  const totalTris = parts.reduce((sum, p) => sum + p.triangles, 0)
  const totalPrims = parts.reduce((sum, p) => sum + p.primitives, 0)
  const mergedDrawCalls = parts.reduce((sum, p) => sum + p.materials, 0)
  const uniqueMeshes = new Set(parts.map((p) => p.meshIndex).filter((m) => m !== null))

  console.log('\n' + '='.repeat(100))
  console.log('SUMMARY')
  console.log('='.repeat(100))
  console.log(`  parts (glTF nodes with a mesh)  ${num(parts.length)}`)
  console.log(`  three.js Mesh objects           ${num(totalPrims)}   <- primitives, not parts`)
  console.log(`  unique glTF mesh definitions    ${num(uniqueMeshes.size)}   <- geometry shared across parts`)
  console.log(`  triangles (rendered total)      ${num(totalTris)}`)
  console.log(`  draw calls, merged per material ${num(mergedDrawCalls)}   <- what the viewer builds`)

  const rawSize = rawBox.getSize(new THREE.Vector3())
  const longestOf = (size) => ['x', 'y', 'z'].reduce((a, b) => (size[a] > size[b] ? a : b))
  console.log()
  console.log(`  source frame     size ${vec(rawSize)}   longest axis: ${longestOf(rawSize).toUpperCase()}`)
  console.log(`  correction       ${UP_AXIS_CORRECTION ? UP_AXIS_CORRECTION.label : 'none'}`)
  console.log(`  assembly bounds  min ${vec(assemblyBox.min)}`)
  console.log(`                   max ${vec(assemblyBox.max)}`)
  console.log(`                  size ${vec(assemblySize)}`)
  console.log(`                center ${vec(assemblyCenter)}`)
  console.log(`  vertical extent ${assemblySize.y.toFixed(3)} m on Y   (a 2 m rack should read here)`)

  // ------------------------------------------------------------ groupings
  printGroups(
    'PREFIX GROUPS  (spec rule: leading token before first `_` or digit run)',
    groupBy(parts, (p) => p.prefix)
  )
  printGroups(
    'SUBASSEMBLY GROUPS  (scene-graph parent path)',
    groupBy(parts, (p) => p.assemblyPath.join(' / ') || '<root>')
  )
  printGroups(
    'IDENTICAL-GEOMETRY GROUPS  (shared glTF mesh index = repeated part)',
    groupBy(parts, (p) => `mesh#${p.meshIndex}`)
  )

  // -------------------------------------------------------- part listing
  console.log('\n' + '='.repeat(100))
  console.log('PARTS')
  console.log('='.repeat(100))
  console.log(
    `  ${'id'.padEnd(34)} ${'prefix'.padEnd(18)} ${'tris'.padStart(8)}  ${'center (x, y, z)'.padEnd(26)} size (x, y, z)`
  )
  for (const p of [...parts].sort((a, b) => b.triangles - a.triangles)) {
    console.log(
      `  ${p.id.padEnd(34)} ${(p.prefix || '<empty>').padEnd(18)} ${num(p.triangles).padStart(8)}  ` +
        `${vec(p.center).padEnd(26)} ${vec(p.size)}`
    )
  }

  // ------------------------------------------------------------- content
  console.log('\n' + '='.repeat(100))
  console.log('CONTENT COVERAGE  (src/data/parts.json)')
  console.log('='.repeat(100))
  if (!existsSync(CONTENT_FILE)) {
    console.log('  parts.json does not exist — every part renders with its raw node name.')
    console.log('  run `npm run seed:content` to scaffold it.')
  } else {
    const content = JSON.parse(readFileSync(CONTENT_FILE, 'utf8'))
    const written = parts.filter((p) => content[p.id]?.role)
    const missing = parts.filter((p) => !content[p.id])
    const orphans = Object.keys(content).filter((id) => !parts.some((p) => p.id === id))
    console.log(`  ${Object.keys(content).length}/${parts.length} parts have an entry`)
    console.log(`  ${written.length}/${parts.length} have prose written`)
    if (missing.length) console.log(`  no entry: ${missing.map((p) => p.id).join(', ')}`)
    if (orphans.length) console.log(`  stale ids (no matching mesh): ${orphans.join(', ')}`)
  }

  // ----------------------------------------------------------- write out
  const payload = {
    source: 'rack.glb',
    generator: gltf.parser.json.asset?.generator ?? null,
    upAxisCorrection: UP_AXIS_CORRECTION,
    assembly: {
      center: assemblyCenter.toArray(),
      size: assemblySize.toArray(),
      min: assemblyBox.min.toArray(),
      max: assemblyBox.max.toArray(),
    },
    parts: parts.map((p) => ({
      id: p.id,
      nodeName: p.nodeName,
      prefix: p.prefix,
      assemblyPath: p.assemblyPath,
      meshIndex: p.meshIndex,
      primitives: p.primitives,
      triangles: p.triangles,
      center: p.center.toArray(),
      size: p.size.toArray(),
      min: p.min.toArray(),
      max: p.max.toArray(),
    })),
  }

  mkdirSync(dirname(GENERATED_OUT), { recursive: true })
  writeFileSync(GENERATED_OUT, JSON.stringify(payload, null, 2) + '\n')
  console.log(`\nwrote ${GENERATED_OUT}  (${parts.length} parts)`)
  console.log('src/data/parts.json untouched.')
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
