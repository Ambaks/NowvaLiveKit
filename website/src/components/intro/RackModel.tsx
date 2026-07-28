"use client";

import { useLayoutEffect, useRef } from "react";
import * as THREE from "three";
import { useGLTF } from "@react-three/drei";
import {
  DRACO_PATH,
  MODEL_ROTATION,
  MODEL_URL,
  MODEL_YAW,
  type Framing,
} from "./introTimeline";

/* Called by the orchestrator as soon as the chunk lands, so the GLB and the
   self-hosted Draco decoder start fetching during the CSS splash hold. Not a
   module-scope side effect: the chunk graph is shared with the rack stage
   (see components/three/scenes.ts), and evaluating it for the rack section
   must not fetch the intro's model. */
export function preloadIntroAssets(): void {
  useGLTF.preload(MODEL_URL, DRACO_PATH);
}

/* Called by the orchestrator after the scene unmounts. Dropping the cache
   entry releases the decoded scene graph to GC; GPU memory dies with the
   canvas context. Not an unmount effect on purpose: StrictMode double-
   invokes effect cleanups while the component is still mounted, which
   would evict the cache mid-pan and re-fetch the GLB. */
export function releaseIntroAssets(): void {
  useGLTF.clear(MODEL_URL);
}

export function RackModel({
  framingRef,
}: {
  framingRef: { current: Framing | null };
}) {
  const groupRef = useRef<THREE.Group>(null);
  const { scene, materials } = useGLTF(MODEL_URL, DRACO_PATH);

  /* eslint-disable react-hooks/immutability -- three.js objects are
     imperative by design; tuning the loaded material and centering the
     scene graph are the intended way to prepare a GLTF for display. */
  useLayoutEffect(() => {
    const group = groupRef.current;
    if (!group) return;

    /* gltf-transform palette-merged everything into one material that ships
       with roughness 1 / metalness 0 — the rim light and IBL do nothing
       until this override. Keep doubleSided: the pod interior is visible. */
    const palette = materials.PaletteMaterial001 as
      | THREE.MeshStandardMaterial
      | undefined;
    if (palette) {
      palette.roughness = 0.45;
      palette.metalness = 0.2;
      palette.envMapIntensity = 0.6;
    }

    /* Box3.setFromObject is instance-aware, so the six GPU-instanced plates
       count toward the bounds. Center the model at the world origin and
       publish framing before first paint so the camera rig never sees
       defaults. */
    group.updateWorldMatrix(true, true);
    const box = new THREE.Box3().setFromObject(group);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    group.position.sub(center);
    framingRef.current = {
      width: size.x,
      height: size.y,
      depth: size.z,
      radius: size.length() / 2,
      groundY: -size.y / 2,
    };
  }, [materials, framingRef]);
  /* eslint-enable react-hooks/immutability */

  /* One wrapper group owns orientation; child nodes keep their baked
     transforms (the plates node has its own axis-permutation quaternion). */
  return (
    <group ref={groupRef} rotation={MODEL_ROTATION}>
      <group rotation-y={MODEL_YAW}>
        <primitive object={scene} />
      </group>
    </group>
  );
}
