"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { useFrame, useThree } from "@react-three/fiber";
import { cameraPose, clamp01, type Framing } from "./introTimeline";

interface CameraRigProps {
  framingRef: { current: Framing | null };
  durationMs: number;
  onFirstFrame: () => void;
  onDone: () => void;
}

/* Scripted pan — no user input. Skips frames until the model has been
   measured, latches the clock on the first framed render, and fires onDone
   exactly once when the timeline completes, freezing on the final pose. */
export function CameraRig({
  framingRef,
  durationMs,
  onFirstFrame,
  onDone,
}: CameraRigProps) {
  const camera = useThree((state) => state.camera) as THREE.PerspectiveCamera;
  const gl = useThree((state) => state.gl);
  const startRef = useRef<number | null>(null);
  const doneRef = useRef(false);
  const sizeRef = useRef(new THREE.Vector2());

  useEffect(() => () => camera.clearViewOffset(), [camera]);

  useFrame(({ clock }) => {
    const framing = framingRef.current;
    if (!framing) return;

    if (startRef.current === null) {
      startRef.current = clock.elapsedTime;
      onFirstFrame();
    }
    const u = clamp01(
      ((clock.elapsedTime - startRef.current) * 1000) / durationMs,
    );

    const { width, height } = gl.getSize(sizeRef.current);
    const pose = cameraPose(u, framing, width / height);

    const heightDelta = pose.cameraY - pose.targetY;
    const horizontal = Math.sqrt(
      Math.max(pose.distance ** 2 - heightDelta ** 2, (0.5 * pose.distance) ** 2),
    );
    camera.position.set(
      horizontal * Math.sin(pose.azimuthRad),
      pose.cameraY,
      horizontal * Math.cos(pose.azimuthRad),
    );
    camera.lookAt(0, pose.targetY, 0);
    camera.setViewOffset(
      width,
      height,
      width * pose.viewOffsetXRatio,
      0,
      width,
      height,
    );

    if (u === 1 && !doneRef.current) {
      doneRef.current = true;
      onDone();
    }
  });

  return null;
}
