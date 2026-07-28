/* Single async boundary for everything that touches three.js. Both 3D
   surfaces load through this module so Turbopack builds one shared chunk
   graph: the intro's dynamic() pulls IntroScene (and the three/fiber/drei
   vendor graph) from here, and the rack stage loads through loadRackStage()
   below — a nested boundary, so its chunk contains only rack app code and
   reuses the vendor chunks already loaded with this module. Pointing the
   two dynamic() calls at their scene files directly instead creates two
   sibling chunk groups that each ship a private ~950 KB copy of three. */

export {
  default as IntroScene,
  preloadIntroAssets,
  releaseIntroAssets,
} from "../intro/IntroScene";

/* Declared here — not in RackExplorer — so the rack chunk group is a child
   of this one and inherits its vendor chunks instead of duplicating them. */
export function loadRackStage(): Promise<typeof import("../rack/RackStage")> {
  return import("../rack/RackStage");
}
