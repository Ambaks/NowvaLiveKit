# Hero media — landing page

The marketing hero (`frontend_demo/src/components/sections/Hero.tsx`) uses a
full-bleed photograph as an Ominin-style backdrop, with dark scrims for text
legibility, plus a live 3D biomechanics visualization on the right.

## 1. Hero background photo

- **File:** `frontend_demo/public/hero-athlete.jpg` (self-hosted, ~400 KB, 1920×1282)
- **Subject:** a female athlete at a squat rack with a barbell — dark, moody gym.
- **Source:** Unsplash, photo by **John Arano** — https://unsplash.com/photos/h4i9G-de7Po
- **License:** [Unsplash License](https://unsplash.com/license) (free for commercial
  use, no attribution required — attribution kept in-code as courtesy).
- **CDN original used to produce the file:**
  `https://images.unsplash.com/photo-1541534741688-6078c6bfb5c5?q=75&w=1920&auto=format&fit=crop`

### Replacing it with a bespoke / generated image later

1. Drop a new image at `frontend_demo/public/hero-athlete.jpg` (same filename → **no
   code change**). Keep a **wide, dark composition with the subject right-of-centre**
   so the left-hand copy stays readable.
2. If you change the aspect/framing, tune `object-[62%_center]` on the `<img>` in
   `Hero.tsx` and, if the source is bright, strengthen the scrim opacities just below it.
3. Keep the subject side dark enough that white/secondary text clears **WCAG AA**
   (4.5:1 body, 3:1 large). The three stacked scrims (`from-background` gradients +
   a flat `bg-background/55` on mobile) already do most of this.

To generate a bespoke image instead of using stock, any text-to-image pipeline works
(no key is wired in this repo). Prompt direction: *"cinematic dark gym, woman
mid-squat under a minimalist AI-equipped power rack, cyan accent lighting, shallow
depth of field, subject on the right third."*

## 2. Live 3D biomechanics scene

- **Component:** `frontend_demo/src/components/three/BiomechanicsScene.tsx`
  (wrapper) + `BiomechanicsCanvas.tsx` (raw **three.js** WebGL scene, lazy-loaded
  into its own chunk).
- Renders a 3D skeleton in a bottom-of-squat pose (joints, bones, barbell, ground
  grid, sweeping scan plane, amber knee "fault" marker) that slowly orbits.
- **Progressive enhancement / fallbacks:**
  - No WebGL → the hand-built SVG `RackVisualization` (rendered with `showReadouts={false}`).
  - `prefers-reduced-motion` → the 3D scene renders a single **static** frame (no orbit/scan).
  - `three` ships in a separate lazy chunk, off the critical path.

### What would need a real 3D asset pipeline

The current scene is an **abstract joint graph** — honest to the product and cheap to
run. A photoreal or anatomically rigged avatar (skinned mesh, muscle groups, real
motion-capture of a squat) is **not** doable purely in code: it needs a modelled +
rigged asset (Blender → glTF/`.glb`), which we would then load with three.js
`GLTFLoader`. That is the natural next step if a higher-fidelity figure is wanted.
