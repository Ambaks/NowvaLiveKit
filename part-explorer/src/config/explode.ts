/**
 * Explode tuning. Every value here is meant to be edited by eye — Vite hot
 * reloads the module and the viewer re-derives offsets without a page reload.
 *
 * Offsets are affine expansion about the assembly centroid:
 *
 *   offset   = (groupCenter - assemblyCenter) * K
 *   position = basePosition + offset * t
 *
 * All distances are metres in the Y-up frame (the loader corrects the source
 * GLB's Z-up orientation). The assembly is roughly 2.0 x 2.1 x 2.1 m.
 */

export type GroupingStrategy = 'composite' | 'prefix' | 'subassembly' | 'none'

export interface GroupTuning {
  /**
   * Multiplies this group's offset. 0 pins it in place so everything else
   * moves around it; >1 pushes it clear of whatever it nests inside.
   */
  travel?: number
  /**
   * Forces the travel axis instead of letting the dominant-axis snap choose.
   * Useful when two axes are nearly tied and the snap picks the one that reads
   * worse — the doors sit almost exactly diagonal to the assembly centre.
   */
  axis?: 'x' | 'y' | 'z'
}

export interface ExplodeConfig {
  /**
   * Per-axis expansion. Not a scalar: the rack is as tall as it is wide, so
   * expanding Y as hard as X/Z throws the top crossmember out of frame.
   * Raise x/z to spread wider, raise y to lift the stack apart vertically.
   */
  k: [number, number, number]

  /**
   * Zero every component of an offset except the largest, so parts travel
   * along pure X, Y or Z. Reads as a service manual rather than a starburst.
   *
   * Note: pure affine expansion cannot self-intersect; snapping trades that
   * guarantee for the cleaner read. If two nested groups end up sliding the
   * same direction (the shell and the base both run -Z at the default K),
   * pull them apart with a groupOverride or turn this off.
   */
  dominantAxisSnap: boolean

  /**
   * How group membership is decided.
   *
   *   composite   - overrides, then subassembly, then spatial clusters of
   *                 repeated geometry, then the part alone. Default.
   *   prefix      - the leading token before the first `_` or digit run.
   *                 Kept so it can be A/B'd; on this GLB it puts all ten
   *                 weight plates in one bucket (their names start with a
   *                 digit, so the prefix is empty) and splits the doors.
   *   subassembly - scene-graph parent path only. Two groups on this GLB.
   *   none        - every part moves independently.
   */
  strategy: GroupingStrategy

  /**
   * composite only. Parts that share a glTF mesh index (the same physical
   * component placed more than once) are clustered when their centres are
   * within this distance, so a stack of plates on one peg moves as a stack
   * while the identical plate across the rack does not join it.
   */
  repeatClusterDistance: number

  /**
   * Force a part into a named group, overriding everything above. This is the
   * escape hatch for assemblies the geometry cannot imply.
   */
  groupOverrides: Record<string, string>

  /**
   * Per-group travel and axis adjustments, keyed by group key. A part that is
   * its own group uses its id as the key (`STEEL_BASE`); the id is shown in the
   * info panel alongside the group a part belongs to.
   */
  groupTuning: Record<string, GroupTuning>

  /** Run-sequence timing, seconds. */
  sequence: {
    out: number
    hold: number
    back: number
    /**
     * Radians of orbit, swept across `out + hold` and then held still for
     * `back`. A full turn brings the camera back around to the front just as
     * the assembly starts closing, so the re-assembly is watched head-on.
     */
    orbit: number
  }

  /** Screen markers fade in past this t. */
  markerThreshold: number

  /** Opacity the rest of the assembly drops to when a part is selected. */
  dimmedOpacity: number
}

export const explodeConfig: ExplodeConfig = {
  k: [1.4, 0.45, 1.4],

  dominantAxisSnap: true,

  strategy: 'composite',

  // 0 keeps every plate its own group, so affine expansion opens a gap between
  // neighbouring plates on the same peg instead of moving the stack as a slab.
  // Raise to ~0.25 to weld each peg's stack back together.
  repeatClusterDistance: 0,

  groupOverrides: {
    // The two 45s loaded on the bar are physically carried by it — they have
    // to travel with the bar, not with the plates parked on the storage pegs.
    BARBELL_PUT_UP: 'BARBELL',
    '45_PLATE_3': 'BARBELL',
    '45_PLATE_4': 'BARBELL',
  },

  groupTuning: {
    // Anchor. Everything else separates around the frame.
    STEEL_BASE: { travel: 0 },
    // The doors nest inside the shell, so matching its travel leaves them
    // buried in it. Send them sideways instead of back, and further out.
    LEFT_DOOR: { travel: 1.6, axis: 'x' },
    RIGHT_DOOR: { travel: 1.6, axis: 'x' },
  },

  sequence: { out: 3.4, hold: 1.8, back: 2.4, orbit: Math.PI * 2 },

  markerThreshold: 0.18,

  dimmedOpacity: 0.1,
}
