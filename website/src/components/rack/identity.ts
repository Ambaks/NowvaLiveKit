/* Ported from part-explorer/src/lib/identity.js (JS there so the inspection
   script can run under bare node). Part ids must match between the two, or the
   copy in partContent.ts stops lining up with the geometry. */

import type { Object3D } from "three";

/** GLTFLoader names the children of a multi-primitive node `<node>_<i>`. */
const PRIMITIVE_SUFFIX = /_\d+$/;

/** Onshape wraps every placed body in "occurrence of <part>"; three.js
 *  sanitizes glTF names, so the spaces arrive as underscores. */
export const OCCURRENCE_PREFIX = /^occurrence[_ ]of[_ ]/;

/** Onshape exports Z-up: the assembly's long axis is Z and it sits on z = 0.
 *  Rotating -90 deg about X puts it in the Y-up frame the explode assumes. */
export const UP_AXIS_CORRECTION = {
  label: "Z-up -> Y-up",
  euler: [-Math.PI / 2, 0, 0] as [number, number, number],
};

/** Leading token before the first `_` or the first digit run. */
export function prefixOf(name: string): string {
  const match = /^(.*?)(?:_|\d)/.exec(name);
  const head = match ? match[1] : name;
  return head.trim().replace(/[\s-]+$/, "");
}

export function slugify(name: string): string {
  return (
    name
      .replace(/[^A-Za-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .toUpperCase() || "PART"
  );
}

export interface GltfParserLike {
  json: { nodes: { mesh?: number }[] };
  associations: Map<object, { nodes?: number } | undefined>;
}

/** Only what the builder needs from a loaded glTF. three/examples and
 *  three-stdlib each ship their own GLTF type and drei returns the latter;
 *  depending on the shape rather than either declaration keeps them out of it. */
export interface LoadedGLTF {
  scene: Object3D;
  parser: GltfParserLike;
}

export interface PartNode {
  object: Object3D;
  id: string;
  nodeName: string;
  assemblyPath: string[];
  meshIndex: number | null;
}

/**
 * A part is an object created from a glTF node that carries a mesh. Uses the
 * loader's own object -> glTF association map rather than name heuristics, so
 * single-primitive nodes (a bare Mesh) and multi-primitive nodes (a Group of
 * Meshes) both resolve to exactly one part.
 */
export function buildPartResolver(gltf: { parser: GltfParserLike }) {
  const { json, associations } = gltf.parser;

  const nodeIndexOf = (object: Object3D): number | null => {
    const assoc = associations.get(object);
    if (!assoc || assoc.nodes === undefined) return null;
    return assoc.nodes;
  };

  const isPart = (object: Object3D): boolean => {
    const index = nodeIndexOf(object);
    if (index === null) return false;
    return json.nodes[index]?.mesh !== undefined;
  };

  /* Fallback if associations are ever unpopulated: a leaf group whose children
     are all primitive meshes, or a standalone named mesh. */
  const isPartByShape = (object: Object3D): boolean => {
    if ((object as { isMesh?: boolean }).isMesh) {
      return !PRIMITIVE_SUFFIX.test(object.name);
    }
    if (!object.children.length) return false;
    return object.children.every((child) => (child as { isMesh?: boolean }).isMesh);
  };

  const associationsWork = [...associations.keys()].some((key) =>
    isPart(key as Object3D),
  );

  return {
    isPart: associationsWork ? isPart : isPartByShape,
    meshIndexOf: (object: Object3D): number | null => {
      const index = nodeIndexOf(object);
      if (index === null) return null;
      return json.nodes[index]?.mesh ?? null;
    },
  };
}

export function collectPartNodes(
  root: Object3D,
  resolver: ReturnType<typeof buildPartResolver>,
): PartNode[] {
  const parts: PartNode[] = [];
  const seenIds = new Map<string, number>();

  const walk = (object: Object3D, path: string[]) => {
    if (resolver.isPart(object)) {
      const nodeName = object.name || "<unnamed>";
      const base = slugify(nodeName);
      const seen = (seenIds.get(base) ?? 0) + 1;
      seenIds.set(base, seen);

      parts.push({
        object,
        id: seen === 1 ? base : `${base}__${seen}`,
        nodeName,
        assemblyPath: path,
        meshIndex: resolver.meshIndexOf(object),
      });
      return;
    }

    const name = object.name ?? "";
    /* Occurrence wrappers carry the same name as the body they hold; only push
       a path segment for genuine subassembly containers. */
    const nextPath =
      name && !OCCURRENCE_PREFIX.test(name) ? [...path, name] : path;

    for (const child of object.children) walk(child, nextPath);
  };

  for (const child of root.children) walk(child, []);
  return parts;
}
