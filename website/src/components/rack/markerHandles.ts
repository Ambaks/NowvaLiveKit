/**
 * DOM handles the in-canvas projector writes to every frame.
 *
 * Markers are real DOM so they can be tabbed to and read by a screen reader,
 * but their positions come from the render loop. The projector mutates these
 * nodes directly — no React state, no re-render per frame.
 */

export interface MarkerHandles {
  dots: Map<string, HTMLButtonElement>
  label: HTMLDivElement | null
  leader: SVGPolylineElement | null
}

export const createMarkerHandles = (): MarkerHandles => ({
  dots: new Map(),
  label: null,
  leader: null,
})

/** Leader geometry, technical-drawing style: a kink then a horizontal run. */
export const LEADER_RUN = 34
export const LEADER_RISE = 28
