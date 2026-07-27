/**
 * Detail panel for the selected part. Side rail on desktop, bottom sheet under
 * 768px. Every field is optional — a part with no entry in parts.json still
 * opens, showing its raw node name.
 */

import { contentFor, displayNameFor } from '../lib/content'
import type { BuiltPart } from '../lib/assembly'
import type { PartGroup } from '../lib/grouping'

interface Props {
  part: BuiltPart | null
  group: PartGroup | null
  onClose: () => void
}

export function InfoPanel({ part, group, onClose }: Props) {
  if (!part) return null

  const content = contentFor(part.id)
  const specs = content.specs ?? []

  return (
    <aside
      className="pointer-events-auto absolute inset-x-0 bottom-0 z-20 max-h-[58svh] overflow-y-auto border-t border-line bg-surface/95 backdrop-blur-xl md:inset-y-0 md:left-auto md:right-0 md:max-h-none md:w-[350px] md:border-l md:border-t-0"
      aria-label="Part details"
    >
      <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
        <div className="min-w-0">
          {content.category && (
            <p className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
              {content.category}
            </p>
          )}
          <h2 className="text-[17px] leading-tight font-medium text-fg">
            {displayNameFor(part.id, part.nodeName)}
          </h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close details"
          className="-mr-1 -mt-1 shrink-0 rounded-md p-1.5 text-muted transition-colors hover:bg-surface-2 hover:text-fg"
        >
          <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden>
            <path
              d="M3.5 3.5l8 8M11.5 3.5l-8 8"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </div>

      <div className="space-y-6 px-5 py-5">
        {content.role ? (
          <p className="text-[13.5px] leading-relaxed text-muted">{content.role}</p>
        ) : (
          <p className="text-[13.5px] leading-relaxed text-faint italic">
            No description written yet.
          </p>
        )}

        {specs.length > 0 && (
          <dl className="divide-y divide-line border-y border-line">
            {specs.map(([term, value], index) => (
              <div key={`${term}-${index}`} className="flex gap-4 py-2.5">
                <dt className="w-[38%] shrink-0 font-mono text-[10.5px] uppercase tracking-[0.12em] text-faint">
                  {term}
                </dt>
                <dd className="min-w-0 flex-1 text-[13px] text-fg">{value}</dd>
              </div>
            ))}
          </dl>
        )}

        {/* Authoring aids: the id to key parts.json by and the group to key
            groupTuning by. Stripped from production so visitors never see it. */}
        {import.meta.env.DEV && (
          <p className="font-mono text-[10.5px] leading-relaxed text-faint">
            <span className="text-muted">id</span> {part.id}
            <br />
            <span className="text-muted">tris</span> {part.triangles.toLocaleString()}
            {group && group.memberIds.length > 1 && (
              <>
                <br />
                <span className="text-muted">moves with</span> {group.key} (
                {group.memberIds.length})
              </>
            )}
          </p>
        )}
      </div>
    </aside>
  )
}
