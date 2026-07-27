/* Pure timeline math for the intro rack pan: easings, camera keyframe
   formulas, and model-orientation constants. No three.js imports so the
   numbers stay trivially testable and tunable in one place. */

export const MODEL_URL = "/models/nowva-rack.glb";
export const DRACO_PATH = "/draco/";

/* Onshape bakes Z-up content into the Y-up glTF (the plates node carries an
   axis-permutation quaternion); verify visually and set to [0,0,0] if the
   export turns out to be natively Y-up. MODEL_YAW aims the pod opening
   toward the camera's starting azimuth. */
export const MODEL_ROTATION: [number, number, number] = [-Math.PI / 2, 0, 0];
export const MODEL_YAW = 0;

export const PAN_DURATION_MS = 3000;
export const CAMERA_FOV_DEG = 35;

/* 1 = the model's bounding sphere exactly fills the frame at the end of the
   dolly-in; below 1 is safe because the sphere overestimates the silhouette. */
const FRAME_FILL = 0.95;

const AZIMUTH_START_DEG = -55;
const AZIMUTH_SWEEP_DEG = 70;
const DOLLY_PULLBACK = 0.22;
const CAM_HEIGHT_START = 0.28;
const CAM_HEIGHT_RISE = 0.34;
const TARGET_HEIGHT_START = 0.52;
const TARGET_HEIGHT_RISE = 0.06;
const VIEW_OFFSET_START = -0.08;
const VIEW_OFFSET_SETTLE = 0.4;

export interface Framing {
  width: number;
  height: number;
  depth: number;
  radius: number;
  groundY: number;
}

export interface CameraPose {
  azimuthRad: number;
  distance: number;
  cameraY: number;
  targetY: number;
  viewOffsetXRatio: number;
}

export const clamp01 = (value: number): number =>
  Math.min(Math.max(value, 0), 1);

export const easeInOutCubic = (u: number): number =>
  u < 0.5 ? 4 * u * u * u : 1 - (-2 * u + 2) ** 3 / 2;

export const easeInOutSine = (u: number): number =>
  -(Math.cos(Math.PI * u) - 1) / 2;

/* Distance at which a sphere of `radius` fits the tighter of the two view
   angles, recomputed per frame so resizes and portrait aspect stay framed. */
export function fitDistance(radius: number, aspect: number): number {
  const fovV = (CAMERA_FOV_DEG * Math.PI) / 180;
  const fovH = 2 * Math.atan(Math.tan(fovV / 2) * aspect);
  return (radius * FRAME_FILL) / Math.sin(Math.min(fovV, fovH) / 2);
}

/* Low front-left hero angle sweeping past the front to the right, rising to
   chest height with a gentle continuous dolly-in; the model sits slightly
   right of center throughout (rule of thirds), settling toward center. */
export function cameraPose(
  u: number,
  framing: Framing,
  aspect: number,
): CameraPose {
  const e = easeInOutCubic(u);
  const fit = fitDistance(framing.radius, aspect);
  const azimuthRad =
    ((AZIMUTH_START_DEG + AZIMUTH_SWEEP_DEG * e) * Math.PI) / 180;
  const distance =
    fit * (1 + DOLLY_PULLBACK - DOLLY_PULLBACK * easeInOutSine(u));
  const cameraY =
    framing.groundY + framing.height * (CAM_HEIGHT_START + CAM_HEIGHT_RISE * e);
  const targetY =
    framing.groundY +
    framing.height * (TARGET_HEIGHT_START + TARGET_HEIGHT_RISE * e);
  const viewOffsetXRatio = VIEW_OFFSET_START * (1 - VIEW_OFFSET_SETTLE * e);
  return { azimuthRad, distance, cameraY, targetY, viewOffsetXRatio };
}
