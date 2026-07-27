/**
 * Part identity, shared by the inspection script and the viewer so a part's id
 * is derived exactly once. Plain JS because `npm run inspect` runs under bare
 * node with no transpile step.
 */

/** GLTFLoader names the children of a multi-primitive node `<node>_<i>`. */
const PRIMITIVE_SUFFIX = /_\d+$/

/**
 * Onshape wraps every placed body in a node named "occurrence of <part>".
 * three.js sanitizes glTF names, so the spaces arrive as underscores.
 */
export const OCCURRENCE_PREFIX = /^occurrence[_ ]of[_ ]/

/**
 * Onshape exports Z-up: the assembly's long axis is Z and it sits on z = 0.
 * Rotating -90 deg about X puts it in the Y-up frame the rest of the app
 * assumes, so the explode K vector reads (horizontal, vertical, horizontal).
 * Set to null if a future export is already Y-up.
 */
export const UP_AXIS_CORRECTION = {
  label: 'Z-up -> Y-up',
  euler: /** @type {[number, number, number]} */ ([-Math.PI / 2, 0, 0]),
}

/**
 * Spec rule: the leading token before the first `_` or the first digit run.
 * Names containing neither keep their whole name as the prefix.
 * @param {string} name
 */
export function prefixOf(name) {
  const match = /^(.*?)(?:_|\d)/.exec(name)
  const head = match ? match[1] : name
  return head.trim().replace(/[\s\-]+$/, '')
}

/** @param {string} name */
export function slugify(name) {
  return (
    name
      .replace(/[^A-Za-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .toUpperCase() || 'PART'
  )
}

/**
 * A part is an object created from a glTF node that carries a mesh. Uses the
 * loader's own object -> glTF association map rather than name heuristics, so
 * single-primitive nodes (a bare Mesh) and multi-primitive nodes (a Group of
 * Meshes) both resolve to exactly one part.
 *
 * @param {any} gltf
 */
export function buildPartResolver(gltf) {
  const json = gltf.parser.json
  const associations = gltf.parser.associations

  /** @param {import('three').Object3D} object */
  const nodeIndexOf = (object) => {
    const assoc = associations.get(object)
    if (!assoc || assoc.nodes === undefined) return null
    return assoc.nodes
  }

  /** @param {import('three').Object3D} object */
  const isPart = (object) => {
    const index = nodeIndexOf(object)
    if (index === null) return false
    return json.nodes[index]?.mesh !== undefined
  }

  // Fallback for loaders that do not populate associations: a leaf group whose
  // children are all primitive meshes, or a standalone named mesh.
  /** @param {any} object */
  const isPartByShape = (object) => {
    if (object.isMesh) return !PRIMITIVE_SUFFIX.test(object.name)
    if (!object.children.length) return false
    return object.children.every((/** @type {any} */ child) => child.isMesh)
  }

  const associationsWork = [...associations.keys()].some(isPart)

  return {
    isPart: associationsWork ? isPart : isPartByShape,
    usingAssociations: associationsWork,
    /** @param {import('three').Object3D} object */
    meshIndexOf: (object) => {
      const index = nodeIndexOf(object)
      if (index === null) return null
      return json.nodes[index]?.mesh ?? null
    },
  }
}

/**
 * Walks the scene and returns one record per part, in stable traversal order.
 * Ids are unique: three.js already uniquifies node names, and the `__n` suffix
 * is a backstop in case a future export collides after slugification.
 *
 * @param {import('three').Object3D} root
 * @param {ReturnType<typeof buildPartResolver>} resolver
 */
export function collectPartNodes(root, resolver) {
  /** @type {{object: any, id: string, nodeName: string, assemblyPath: string[], meshIndex: number | null}[]} */
  const parts = []
  /** @type {Map<string, number>} */
  const seenIds = new Map()

  /**
   * @param {import('three').Object3D} object
   * @param {string[]} path
   */
  const walk = (object, path) => {
    if (resolver.isPart(object)) {
      const nodeName = object.name || '<unnamed>'
      const base = slugify(nodeName)
      const seen = (seenIds.get(base) ?? 0) + 1
      seenIds.set(base, seen)

      parts.push({
        object,
        id: seen === 1 ? base : `${base}__${seen}`,
        nodeName,
        assemblyPath: path,
        meshIndex: resolver.meshIndexOf(object),
      })
      return
    }

    const name = object.name ?? ''
    // Occurrence wrappers carry the same name as the body they hold; only push
    // a path segment for genuine subassembly containers.
    const nextPath = name && !OCCURRENCE_PREFIX.test(name) ? [...path, name] : path

    for (const child of object.children) walk(child, nextPath)
  }

  for (const child of root.children) walk(child, [])
  return parts
}
