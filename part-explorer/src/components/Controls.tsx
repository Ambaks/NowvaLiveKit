/**
 * Scrub and run-sequence controls.
 *
 * The range input is uncontrolled: its value goes straight into the viewer
 * store on input, and the store writes back only so the thumb follows the run
 * sequence. React never sits between the pointer and the model.
 */

import { useEffect, useRef } from 'react'

import { viewer, type SequencePhase } from '../lib/viewerStore'

interface Props {
  phase: SequencePhase
  disabled: boolean
}

export function Controls({ phase, disabled }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const readout = useRef<HTMLSpanElement>(null)

  useEffect(
    () =>
      viewer.subscribeT((t) => {
        if (input.current) input.current.value = String(t)
        if (readout.current) readout.current.textContent = `${Math.round(t * 100)}%`
      }),
    []
  )

  const running = phase !== 'idle'

  return (
    <div className="pointer-events-auto flex items-center gap-4 border-t border-line bg-ink/85 px-4 py-3 backdrop-blur-md sm:gap-5 sm:px-6">
      <button
        type="button"
        disabled={disabled}
        onClick={() => (running ? viewer.cancelSequence() : viewer.startSequence())}
        className="shrink-0 rounded-full border border-line-strong px-4 py-1.5 font-mono text-[11px] uppercase tracking-[0.16em] text-fg transition-colors hover:border-cta hover:text-cta disabled:opacity-40 disabled:hover:border-line-strong disabled:hover:text-fg"
      >
        {running ? 'Cancel' : 'Run sequence'}
      </button>

      <label className="flex min-w-0 flex-1 items-center gap-3">
        <span className="sr-only">Explode amount</span>
        <input
          ref={input}
          type="range"
          min={0}
          max={1}
          step={0.001}
          defaultValue={0}
          disabled={disabled}
          onInput={(event) => viewer.setT(Number(event.currentTarget.value))}
          className="scrub h-5 min-w-0 flex-1 disabled:opacity-40"
          aria-label="Explode amount"
        />
        <span
          ref={readout}
          className="w-11 shrink-0 text-right font-mono text-[11px] tabular-nums text-muted"
        >
          0%
        </span>
      </label>
    </div>
  )
}
