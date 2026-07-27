/**
 * Screen markers. Real DOM so they sit in the tab order and read out to
 * assistive tech; positioned every frame by Projector writing to these refs.
 */

import type { RefObject } from 'react'

import { displayNameFor } from '../lib/content'
import type { BuiltAssembly } from '../lib/assembly'
import type { MarkerHandles } from './markerHandles'

interface Props {
  assembly: BuiltAssembly
  handles: RefObject<MarkerHandles>
  selectedId: string | null
  onSelect: (id: string | null) => void
}

export function Markers({ assembly, handles, selectedId, onSelect }: Props) {
  const selected = selectedId ? assembly.byId.get(selectedId) : null

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      <svg className="absolute inset-0 h-full w-full" aria-hidden>
        <polyline
          ref={(el) => {
            handles.current.leader = el
          }}
          fill="none"
          stroke="var(--color-cta)"
          strokeWidth={1}
          strokeDasharray="5 4"
          style={{ visibility: 'hidden' }}
        />
      </svg>

      {assembly.parts.map((part) => {
        const isSelected = part.id === selectedId
        return (
          <button
            key={part.id}
            ref={(el) => {
              if (el) handles.current.dots.set(part.id, el)
              else handles.current.dots.delete(part.id)
            }}
            type="button"
            tabIndex={-1}
            onClick={() => onSelect(isSelected ? null : part.id)}
            aria-label={displayNameFor(part.id, part.nodeName)}
            aria-pressed={isSelected}
            className={[
              'pointer-events-auto absolute left-0 top-0 rounded-full transition-colors',
              isSelected
                ? 'h-3 w-3 bg-cta ring-2 ring-cta/35'
                : 'h-2 w-2 bg-fg/80 ring-1 ring-ink/60 hover:bg-accent',
            ].join(' ')}
            style={{ visibility: 'hidden' }}
          />
        )
      })}

      <div
        ref={(el) => {
          handles.current.label = el
        }}
        className="absolute left-0 top-0 whitespace-nowrap border-b border-cta/70 pb-1 font-mono text-[11px] uppercase tracking-[0.14em] text-cta"
        style={{ visibility: 'hidden' }}
        aria-hidden
      >
        {selected ? displayNameFor(selected.id, selected.nodeName) : ''}
      </div>
    </div>
  )
}
