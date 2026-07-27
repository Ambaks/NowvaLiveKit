"use client";

/* eslint-disable react-hooks/immutability -- three.js objects, camera state and marker DOM nodes are
   mutated imperatively every frame by design - that is what a render loop is.
   Routing any of it through React state would re-render 60x a second. */

/* Scene internals: the merged parts, the camera rig, the sequence driver and
   the screen-space projector. Everything that changes per frame is written
   straight onto three.js objects or DOM nodes — React never re-renders here. */

import { useEffect, useRef, type RefObject } from "react";
import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import * as THREE from "three";

import { explodeConfig } from "./explode";
import type { BuiltAssembly, ExplodeSolution } from "./assembly";
import { viewer, type SequencePhase } from "./viewerStore";
import { LEADER_RISE, LEADER_RUN, type MarkerHandles } from "./markerHandles";

const FADE_HALFLIFE = 0.0001;
const FRAMING_MARGIN = 1.08;
const FRAMING_EXPLODE_BLEND = 0.5;
const TARGET_HALFLIFE = 0.0015;
const MARKER_FADE_RANGE = 0.12;
const ORIGIN = new THREE.Vector3();

/* ------------------------------------------------------------------ parts */

function applyOpacity(
  materials: THREE.MeshStandardMaterial[],
  opacity: number,
) {
  const transparent = opacity < 0.999;
  for (const material of materials) {
    if (material.transparent !== transparent) {
      material.transparent = transparent;
      material.depthWrite = !transparent;
      /* `transparent` is part of the cached program key. Flipping it after the
         material has rendered once is silently ignored without this. */
      material.needsUpdate = true;
    }
    material.opacity = opacity;
  }
}

export function AssemblyView({
  assembly,
  explode,
  selectedId,
  onSelect,
}: {
  assembly: BuiltAssembly;
  explode: ExplodeSolution;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const opacities = useRef(new Map<string, number>()).current;
  const hovered = useRef(false);

  useEffect(
    () => () => {
      document.body.style.cursor = "";
    },
    [],
  );

  useFrame((_, delta) => {
    const t = viewer.getT();
    const ease = 1 - Math.pow(FADE_HALFLIFE, Math.min(delta, 0.1));

    for (const part of assembly.parts) {
      const offset = explode.offsets.get(part.id);
      if (offset) part.object.position.copy(offset).multiplyScalar(t);

      const target =
        !selectedId || selectedId === part.id ? 1 : explodeConfig.dimmedOpacity;
      const current = opacities.get(part.id) ?? 1;

      if (Math.abs(target - current) < 0.002) {
        if (current !== target) {
          opacities.set(part.id, target);
          applyOpacity(part.materials, target);
        }
        continue;
      }

      const next = current + (target - current) * ease;
      opacities.set(part.id, next);
      applyOpacity(part.materials, next);
    }
  });

  const setCursor = (on: boolean) => {
    if (hovered.current === on) return;
    hovered.current = on;
    document.body.style.cursor = on ? "pointer" : "";
  };

  return (
    <>
      {assembly.parts.map((part) => (
        <primitive
          key={part.id}
          object={part.object}
          onClick={(event: ThreeEvent<MouseEvent>) => {
            event.stopPropagation();
            onSelect(part.id === selectedId ? null : part.id);
          }}
          onPointerOver={(event: ThreeEvent<PointerEvent>) => {
            event.stopPropagation();
            setCursor(true);
          }}
          onPointerOut={() => setCursor(false)}
        />
      ))}
    </>
  );
}

/* ----------------------------------------------------------------- camera */

export function CameraRig({
  assembly,
  explode,
  selectedId,
  reducedMotion,
}: {
  assembly: BuiltAssembly;
  explode: ExplodeSolution;
  selectedId: string | null;
  reducedMotion: boolean;
}) {
  const controls = useRef<OrbitControlsImpl>(null);
  const camera = useThree((state) => state.camera);
  const desired = useRef(new THREE.Vector3());
  const baseAzimuth = useRef(0);
  const lastPhase = useRef<SequencePhase>("idle");

  useEffect(() => {
    const perspective = camera as THREE.PerspectiveCamera;
    const halfFov = (perspective.fov * THREE.MathUtils.DEG2RAD) / 2;

    /* Fitting per world axis is wrong for an angled view — the silhouette of a
       diagonally-viewed box is wider than any single axis. Measure on the
       camera's own right/up axes, part-way through the explode so both ends of
       the scrub stay in frame. */
    const direction = new THREE.Vector3(0.62, 0.34, 1).normalize();
    const right = new THREE.Vector3()
      .crossVectors(new THREE.Vector3(0, 1, 0), direction)
      .normalize();
    const up = new THREE.Vector3().crossVectors(direction, right).normalize();

    const corner = new THREE.Vector3();
    let halfWidth = 0;
    let halfHeight = 0;
    let towardCamera = 0;

    for (const part of assembly.parts) {
      const offset = explode.offsets.get(part.id) ?? ORIGIN;
      const { min, max } = part.facts;
      for (let bit = 0; bit < 8; bit++) {
        corner
          .set(
            bit & 1 ? max[0] : min[0],
            bit & 2 ? max[1] : min[1],
            bit & 4 ? max[2] : min[2],
          )
          .addScaledVector(offset, FRAMING_EXPLODE_BLEND)
          .sub(assembly.center);

        halfWidth = Math.max(halfWidth, Math.abs(corner.dot(right)));
        halfHeight = Math.max(halfHeight, Math.abs(corner.dot(up)));
        towardCamera = Math.max(towardCamera, corner.dot(direction));
      }
    }

    const distance =
      Math.max(
        halfHeight / Math.tan(halfFov),
        halfWidth / (Math.tan(halfFov) * perspective.aspect),
      ) *
        FRAMING_MARGIN +
      towardCamera;

    camera.position.copy(assembly.center).addScaledVector(direction, distance);
    perspective.near = Math.max(0.05, distance / 200);
    perspective.far = distance * 12;
    perspective.updateProjectionMatrix();

    desired.current.copy(assembly.center);
    controls.current?.target.copy(assembly.center);
  }, [assembly, explode, camera]);

  useFrame((_, delta) => {
    const orbit = controls.current;
    if (!orbit) return;

    const t = viewer.getT();

    if (selectedId) {
      const part = assembly.byId.get(selectedId);
      if (part) {
        desired.current.copy(part.center);
        const offset = explode.offsets.get(selectedId);
        if (offset) desired.current.addScaledVector(offset, t);
      }
    } else {
      desired.current.copy(assembly.center);
    }

    orbit.target.lerp(
      desired.current,
      1 - Math.pow(TARGET_HALFLIFE, Math.min(delta, 0.1)),
    );

    const phase = viewer.getPhase();
    if (phase !== "idle") {
      if (lastPhase.current === "idle") {
        baseAzimuth.current = orbit.getAzimuthalAngle();
      }
      if (!reducedMotion) {
        orbit.setAzimuthalAngle(baseAzimuth.current + viewer.orbit);
        orbit.update();
      }
    }
    lastPhase.current = phase;
  });

  return (
    <OrbitControls
      ref={controls}
      makeDefault
      enableDamping
      dampingFactor={0.08}
      enablePan={false}
      enableZoom={false}
      minDistance={assembly.size.length() * 0.18}
      maxDistance={assembly.size.length() * 3}
      maxPolarAngle={Math.PI * 0.495}
      onStart={() => viewer.cancelSequence()}
    />
  );
}

/* -------------------------------------------------------------- projector */

export function Projector({
  assembly,
  explode,
  handles,
  selectedId,
}: {
  assembly: BuiltAssembly;
  explode: ExplodeSolution;
  handles: RefObject<MarkerHandles>;
  selectedId: string | null;
}) {
  const camera = useThree((state) => state.camera);
  const size = useThree((state) => state.size);
  const world = useRef(new THREE.Vector3()).current;
  const shown = useRef(new Map<string, boolean>()).current;

  useFrame(() => {
    const t = viewer.getT();
    const fade = THREE.MathUtils.clamp(
      (t - explodeConfig.markerThreshold) / MARKER_FADE_RANGE,
      0,
      1,
    );

    let selectedScreen: { x: number; y: number } | null = null;

    for (const part of assembly.parts) {
      const dot = handles.current.dots.get(part.id);
      if (!dot) continue;

      const offset = explode.offsets.get(part.id);
      world.copy(part.center);
      if (offset) world.addScaledVector(offset, t);
      world.project(camera);

      const isSelected = selectedId === part.id;
      const visible = world.z < 1 && (fade > 0 || isSelected);

      if (shown.get(part.id) !== visible) {
        shown.set(part.id, visible);
        dot.style.visibility = visible ? "visible" : "hidden";
        dot.tabIndex = visible ? 0 : -1;
      }
      if (!visible) continue;

      const x = (world.x * 0.5 + 0.5) * size.width;
      const y = (-world.y * 0.5 + 0.5) * size.height;

      dot.style.transform = `translate3d(${x}px, ${y}px, 0) translate(-50%, -50%)`;
      dot.style.opacity = String(isSelected ? 1 : 0.28 + 0.42 * fade);

      if (isSelected) selectedScreen = { x, y };
    }

    const label = handles.current.label;
    const leader = handles.current.leader;
    if (!label || !leader) return;

    if (!selectedScreen) {
      label.style.visibility = "hidden";
      leader.style.visibility = "hidden";
      return;
    }

    const flip = selectedScreen.x > size.width - 220;
    const direction = flip ? -1 : 1;
    const kinkX = selectedScreen.x + LEADER_RISE * direction;
    const kinkY = selectedScreen.y - LEADER_RISE;
    const endX = kinkX + LEADER_RUN * direction;

    leader.setAttribute(
      "points",
      `${selectedScreen.x},${selectedScreen.y} ${kinkX},${kinkY} ${endX},${kinkY}`,
    );
    leader.style.visibility = "visible";

    label.style.transform =
      `translate3d(${endX}px, ${kinkY}px, 0) translate(${flip ? "-100%" : "0"}, -50%)`;
    label.style.visibility = "visible";
  });

  return null;
}

/* Advances the run sequence once per frame, ahead of everything reading t. */
export function FrameDriver({ reducedMotion }: { reducedMotion: boolean }) {
  useFrame((_, delta) => {
    viewer.advance(delta, explodeConfig, !reducedMotion);
  }, -2);
  return null;
}
