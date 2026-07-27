/**
 * Explode progress lives outside React.
 *
 * `t` changes every frame while scrubbing or running the sequence. Routing it
 * through useState would re-render the tree 60 times a second and put a frame
 * of lag between the finger and the model, so it is held here and read
 * directly inside useFrame. React only hears about phase changes.
 */

import type { ExplodeConfig } from '../config/explode'

export type SequencePhase = 'idle' | 'out' | 'hold' | 'back'

type Listener<T> = (value: T) => void

const easeInOutCubic = (x: number) =>
  x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2

class ViewerStore {
  private t = 0
  private phase: SequencePhase = 'idle'
  private elapsed = 0
  private tListeners = new Set<Listener<number>>()
  private phaseListeners = new Set<Listener<SequencePhase>>()

  /** Radians of orbit contributed by the running sequence. */
  orbit = 0

  getT() {
    return this.t
  }

  getPhase() {
    return this.phase
  }

  /** Manual input. Cancels a running sequence unless told otherwise. */
  setT(value: number, options: { fromSequence?: boolean } = {}) {
    if (!options.fromSequence && this.phase !== 'idle') this.setPhase('idle')

    const clamped = value < 0 ? 0 : value > 1 ? 1 : value
    if (clamped === this.t) return
    this.t = clamped
    for (const listener of this.tListeners) listener(clamped)
  }

  private setPhase(phase: SequencePhase) {
    if (phase === this.phase) return
    this.phase = phase
    if (phase === 'idle') this.orbit = 0
    for (const listener of this.phaseListeners) listener(phase)
  }

  startSequence() {
    this.elapsed = 0
    this.orbit = 0
    this.setT(0, { fromSequence: true })
    this.setPhase('out')
  }

  cancelSequence() {
    if (this.phase !== 'idle') this.setPhase('idle')
  }

  /**
   * Drives the run sequence. Called once per frame from inside the canvas.
   * Returns true while the sequence owns the camera.
   */
  advance(delta: number, config: ExplodeConfig, allowCameraMotion: boolean): boolean {
    if (this.phase === 'idle') return false

    const { out, hold, back, orbit } = config.sequence
    this.elapsed += delta
    const total = out + hold + back

    if (this.elapsed >= total) {
      this.setT(0, { fromSequence: true })
      this.setPhase('idle')
      return false
    }

    if (this.elapsed < out) {
      this.setPhase('out')
      this.setT(easeInOutCubic(this.elapsed / out), { fromSequence: true })
    } else if (this.elapsed < out + hold) {
      this.setPhase('hold')
      this.setT(1, { fromSequence: true })
    } else {
      this.setPhase('back')
      const progress = (this.elapsed - out - hold) / back
      this.setT(1 - easeInOutCubic(progress), { fromSequence: true })
    }

    // The sweep finishes as the hold ends, so the camera is already back at
    // the front while the assembly closes. Eased, so it accelerates away from
    // the opening view and decelerates arriving back at it.
    const sweep = Math.min(1, this.elapsed / (out + hold))
    this.orbit = allowCameraMotion ? easeInOutCubic(sweep) * orbit : 0
    return allowCameraMotion
  }

  subscribeT(listener: Listener<number>) {
    this.tListeners.add(listener)
    listener(this.t)
    return () => {
      this.tListeners.delete(listener)
    }
  }

  subscribePhase(listener: Listener<SequencePhase>) {
    this.phaseListeners.add(listener)
    listener(this.phase)
    return () => {
      this.phaseListeners.delete(listener)
    }
  }
}

export const viewer = new ViewerStore()
