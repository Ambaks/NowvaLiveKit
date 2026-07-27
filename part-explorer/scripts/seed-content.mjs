/**
 * Scaffolds src/data/parts.json from the generated geometry facts.
 *
 * Writes displayName and an inferred category, leaves role and specs empty for
 * hand editing. Refuses to touch an existing file — run `npm run inspect` to
 * see which ids are missing copy and add them by hand.
 */

import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const GENERATED = resolve(ROOT, 'src/data/parts.generated.json')
const CONTENT = resolve(ROOT, 'src/data/parts.json')

const CATEGORY_RULES = [
  [/SCREW|WASHER|BOLT|NUT/, 'fastener'],
  [/PLATE|BARBELL/, 'load'],
  [/DOOR|CASING/, 'enclosure'],
  [/SEAT|SLIDER|BENCH/, 'bench'],
]

function categoryFor(part) {
  if (part.assemblyPath.length > 1) {
    for (const [pattern, category] of CATEGORY_RULES) {
      if (pattern.test(part.id)) return category
    }
    return 'bench'
  }
  for (const [pattern, category] of CATEGORY_RULES) {
    if (pattern.test(part.id)) return category
  }
  return 'structure'
}

function humanize(nodeName) {
  const words = nodeName
    .replace(/[_\-]+/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

if (!existsSync(GENERATED)) {
  console.error('src/data/parts.generated.json missing — run `npm run inspect` first.')
  process.exit(1)
}

if (existsSync(CONTENT)) {
  console.error('src/data/parts.json already exists — refusing to overwrite hand-edited copy.')
  process.exit(1)
}

const { parts } = JSON.parse(readFileSync(GENERATED, 'utf8'))

const content = {}
for (const part of parts) {
  content[part.id] = {
    displayName: humanize(part.nodeName),
    category: categoryFor(part),
    role: '',
    specs: [],
  }
}

writeFileSync(CONTENT, JSON.stringify(content, null, 2) + '\n')
console.log(`wrote ${CONTENT} — ${parts.length} entries, role/specs left empty.`)
