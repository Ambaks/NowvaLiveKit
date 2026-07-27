/**
 * Hand-written copy, merged onto generated geometry facts by node id.
 *
 * Loaded through import.meta.glob so a missing or partial parts.json degrades
 * to raw node names instead of failing the build. Any mesh without an entry
 * still renders and is still clickable.
 */

export interface PartContent {
  displayName?: string
  category?: string
  role?: string
  specs?: [string, string][]
}

const modules = import.meta.glob<Record<string, PartContent>>('../data/parts.json', {
  eager: true,
  import: 'default',
})

export const partContent: Record<string, PartContent> = Object.values(modules)[0] ?? {}

export function contentFor(id: string): PartContent {
  return partContent[id] ?? {}
}

/** Falls back to the raw node name, which is the point: copy is optional. */
export function displayNameFor(id: string, nodeName: string): string {
  return partContent[id]?.displayName || nodeName
}
