import { useEffect, useRef } from 'react';
import * as THREE from 'three';

/**
 * Real-time 3D biomechanics reconstruction — a WebGL skeleton in a bottom-of-squat
 * pose, slowly orbiting, with a scanning plane that sweeps the body. This is the
 * "3D triangulation" the product performs, rendered honestly as an abstract joint
 * graph (not a photoreal avatar — that would require a rigged Blender/glTF asset).
 *
 * Rendered with raw three.js (no r3f) to keep the dependency surface minimal and
 * give full control over cleanup, resize and prefers-reduced-motion. Lazy-loaded
 * by BiomechanicsScene so `three` ships in its own chunk, off the critical path.
 */

const ACCENT = 0x00e5ff;
const AMBER = 0xffb800;

// Squat pose, bottom position — hips just below knee height ("below parallel").
// Units ≈ metres, y up, x right, z toward camera. Order matters: bones index into this.
const JOINTS: [number, number, number][] = [
  [0, 1.2, 0.2], // 0  head
  [0, 1.03, 0.16], // 1  neck
  [-0.2, 1.0, 0.12], // 2  l_shoulder
  [0.2, 1.0, 0.12], // 3  r_shoulder
  [-0.31, 1.02, -0.02], // 4  l_elbow
  [0.31, 1.02, -0.02], // 5  r_elbow
  [-0.24, 1.08, -0.1], // 6  l_wrist
  [0.24, 1.08, -0.1], // 7  r_wrist
  [0, 0.82, 0.12], // 8  spine (mid-back)
  [0, 0.5, -0.02], // 9  pelvis
  [-0.13, 0.51, -0.02], // 10 l_hip
  [0.13, 0.51, -0.02], // 11 r_hip
  [-0.2, 0.55, 0.3], // 12 l_knee
  [0.2, 0.55, 0.3], // 13 r_knee
  [-0.16, 0.08, 0.14], // 14 l_ankle
  [0.16, 0.08, 0.14], // 15 r_ankle
  [-0.16, 0.0, 0.28], // 16 l_foot
  [0.16, 0.0, 0.28], // 17 r_foot
];

const BONES: [number, number][] = [
  [0, 1], [1, 2], [1, 3], [2, 4], [4, 6], [3, 5], [5, 7],
  [1, 8], [8, 9], [9, 10], [9, 11], [10, 12], [11, 13],
  [12, 14], [13, 15], [14, 16], [15, 17],
];

// Vertical centring offset so the figure sits around the origin.
const Y_OFFSET = -0.55;

export default function BiomechanicsCanvas({ reducedMotion }: { reducedMotion: boolean }) {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const width = mount.clientWidth || 400;
    const height = mount.clientHeight || 520;

    const scene = new THREE.Scene();

    const camera = new THREE.PerspectiveCamera(34, width / height, 0.1, 100);
    camera.position.set(1.35, 0.35, 2.75);
    camera.lookAt(0, 0.02, 0);

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' });
    } catch {
      return; // Guarded again upstream; bail silently to the SVG fallback.
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    renderer.setClearColor(0x000000, 0);
    mount.appendChild(renderer.domElement);
    renderer.domElement.setAttribute('aria-hidden', 'true');

    // Lighting — mostly for the metallic barbell; joints/bones are unlit for a clean glow.
    scene.add(new THREE.AmbientLight(0xffffff, 0.5));
    const key = new THREE.DirectionalLight(0xbfefff, 1.2);
    key.position.set(2, 3, 2);
    scene.add(key);
    const rim = new THREE.DirectionalLight(ACCENT, 0.8);
    rim.position.set(-2, 1, -1);
    scene.add(rim);

    // Rotating rig holding everything anchored to the figure.
    const rig = new THREE.Group();
    rig.position.y = Y_OFFSET;
    scene.add(rig);

    const vecs = JOINTS.map(([x, y, z]) => new THREE.Vector3(x, y, z));

    const disposables: { dispose: () => void }[] = [];
    const track = <T extends THREE.BufferGeometry | THREE.Material>(o: T): T => {
      disposables.push(o);
      return o;
    };

    // --- Bones: thin cylinders between joints -------------------------------
    const boneMat = track(
      new THREE.MeshBasicMaterial({ color: ACCENT, transparent: true, opacity: 0.5 }),
    );
    for (const [a, b] of BONES) {
      const start = vecs[a];
      const end = vecs[b];
      const dir = new THREE.Vector3().subVectors(end, start);
      const len = dir.length();
      const geo = track(new THREE.CylinderGeometry(0.011, 0.011, len, 6, 1, true));
      const mesh = new THREE.Mesh(geo, boneMat);
      mesh.position.copy(start).add(end).multiplyScalar(0.5);
      mesh.quaternion.setFromUnitVectors(
        new THREE.Vector3(0, 1, 0),
        dir.clone().normalize(),
      );
      rig.add(mesh);
    }

    // --- Joints: bright core sphere + additive halo -------------------------
    const coreMat = track(new THREE.MeshBasicMaterial({ color: 0xd8fbff }));
    const haloMat = track(
      new THREE.MeshBasicMaterial({
        color: ACCENT,
        transparent: true,
        opacity: 0.28,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    );
    const halos: THREE.Mesh[] = [];
    vecs.forEach((v, i) => {
      const isHead = i === 0;
      const r = isHead ? 0.055 : 0.028;
      const core = new THREE.Mesh(track(new THREE.SphereGeometry(r, 16, 16)), coreMat);
      core.position.copy(v);
      rig.add(core);

      const halo = new THREE.Mesh(track(new THREE.SphereGeometry(r * 2.4, 16, 16)), haloMat);
      halo.position.copy(v);
      rig.add(halo);
      halos.push(halo);
    });

    // --- Barbell across the shoulders --------------------------------------
    const barY = (vecs[2].y + vecs[3].y) / 2 + 0.02;
    const barZ = (vecs[2].z + vecs[3].z) / 2 - 0.04;
    const barMat = track(new THREE.MeshStandardMaterial({ color: 0x8a8a94, metalness: 0.9, roughness: 0.35 }));
    const bar = new THREE.Mesh(track(new THREE.CylinderGeometry(0.02, 0.02, 1.05, 12)), barMat);
    bar.rotation.z = Math.PI / 2;
    bar.position.set(0, barY, barZ);
    rig.add(bar);
    const plateMat = track(new THREE.MeshStandardMaterial({ color: 0x1f1f24, metalness: 0.6, roughness: 0.5 }));
    for (const sx of [-0.5, 0.5]) {
      const plate = new THREE.Mesh(track(new THREE.CylinderGeometry(0.13, 0.13, 0.03, 20)), plateMat);
      plate.rotation.z = Math.PI / 2;
      plate.position.set(sx, barY, barZ);
      rig.add(plate);
    }

    // --- Ground grid (subtle) ----------------------------------------------
    const grid = new THREE.GridHelper(2.4, 12, ACCENT, ACCENT);
    (grid.material as THREE.Material).transparent = true;
    (grid.material as THREE.Material).opacity = 0.08;
    grid.position.y = -0.005;
    rig.add(grid);
    disposables.push(grid.geometry, grid.material as THREE.Material);

    // --- Scan plane sweeping the body --------------------------------------
    const scanGeo = track(new THREE.PlaneGeometry(1.1, 1.1));
    const scanMat = track(
      new THREE.MeshBasicMaterial({
        color: ACCENT,
        transparent: true,
        opacity: 0.12,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        side: THREE.DoubleSide,
      }),
    );
    const scan = new THREE.Mesh(scanGeo, scanMat);
    scan.rotation.x = -Math.PI / 2;
    rig.add(scan);

    // Amber "fault" marker on the right knee — the fault-detection cue, made literal.
    const faultMat = track(
      new THREE.MeshBasicMaterial({
        color: AMBER,
        transparent: true,
        opacity: 0.5,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    );
    const fault = new THREE.Mesh(track(new THREE.RingGeometry(0.05, 0.075, 24)), faultMat);
    fault.position.copy(vecs[13]);
    fault.lookAt(camera.position.clone().sub(new THREE.Vector3(0, Y_OFFSET, 0)));
    rig.add(fault);

    const clock = new THREE.Clock();
    let raf = 0;

    const renderFrame = () => {
      const t = clock.getElapsedTime();
      // Orbit slowly, easing back and forth rather than full spin — calmer, more premium.
      rig.rotation.y = Math.sin(t * 0.28) * 0.5;
      // Scan sweep 0.0 → 1.25 in body space.
      const sy = ((t * 0.32) % 1) * 1.25;
      scan.position.y = sy;
      scanMat.opacity = 0.06 + 0.1 * Math.sin(t * 0.32 * Math.PI * 2) ** 2;
      // Gentle joint pulse.
      const pulse = 1 + Math.sin(t * 2) * 0.08;
      for (const h of halos) h.scale.setScalar(pulse);
      faultMat.opacity = 0.35 + 0.25 * (0.5 + 0.5 * Math.sin(t * 3));
      renderer.render(scene, camera);
      raf = requestAnimationFrame(renderFrame);
    };

    if (reducedMotion) {
      // Static, legible frame — no motion, no RAF loop.
      rig.rotation.y = 0.3;
      scan.visible = false;
      renderer.render(scene, camera);
    } else {
      renderFrame();
    }

    const ro = new ResizeObserver(() => {
      const w = mount.clientWidth || width;
      const h = mount.clientHeight || height;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      if (reducedMotion) renderer.render(scene, camera);
    });
    ro.observe(mount);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      for (const d of disposables) d.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement);
    };
  }, [reducedMotion]);

  return <div ref={mountRef} className="absolute inset-0" />;
}
