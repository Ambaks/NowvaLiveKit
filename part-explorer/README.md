# Nowva part explorer

Interactive exploded-view viewer for the rack assembly. The explode is computed
at runtime from the GLB's own geometry — nothing is keyframed, and no explode
positions are baked into the model.

```bash
npm install
npm run inspect        # walk the GLB, regenerate src/data/parts.generated.json
npm run dev            # http://localhost:5173
```

## Source of truth

| What exists      | `../rack.glb` — read-only. Copied to `public/models/rack.glb` for serving. |
| ---------------- | ------------------------------------------------------------------------- |
| What it's called | `src/data/parts.json` — hand-written copy, keyed by node id.               |
| Geometry facts   | `src/data/parts.generated.json` — written by `npm run inspect`.            |

`npm run inspect` never touches `parts.json`. The two are merged by id at
runtime; a mesh with no entry renders, stays clickable, and shows its raw node
name. Scaffold the copy file once with `npm run seed:content` (it refuses to
overwrite an existing one), then edit `role` and `specs` by hand.

Part ids come from the glTF node names, uppercased and slugified —
`45 plate` → `45_PLATE`. Deep links use them: `?part=LUXURY_CASING`.

## Tuning the explode

Everything lives in `src/config/explode.ts` and hot reloads. Geometry is merged
once at load; changing config re-solves only the offsets, so edits apply
instantly.

- `k` — per-axis expansion, `(x, y, z)`. Not a scalar: the rack is as tall as it
  is wide, so `y` is deliberately lower than `x`/`z`.
- `dominantAxisSnap` — zero all but the largest component so parts travel on
  pure X/Y/Z. Note that pure affine expansion cannot self-intersect but snapping
  trades that guarantee for the cleaner read.
- `strategy` — how parts are grouped. `composite` (default) resolves overrides →
  subassembly → proximity clusters of repeated geometry → the part alone.
  `prefix` implements the leading-token rule if you want to A/B it.
- `groupOverrides` — force a part into a named group. Ships with the two 45s
  loaded on the bar assigned to `BARBELL` so they travel with it.

Selecting a part shows which group it landed in ("moves with …"), which is the
fastest way to see what a config change did.

## Notes on this GLB

- The Onshape export is **Z-up**. The loader rotates it −90° about X so the
  explode `k` reads as (horizontal, vertical, horizontal). The constant is
  `UP_AXIS_CORRECTION` in `src/lib/identity.js`, shared by the script and the app.
- A "part" is a glTF node carrying a mesh — 32 of them. Each is split into 6–142
  primitives by face colour (864 total). The viewer merges each part's
  primitives per material, giving **43 draw calls** for 215k triangles.
- The prefix rule groups poorly here: names starting with a digit (`45 plate`,
  `25 plate`) yield an empty prefix, collapsing all ten weight plates into one
  bucket, while `LEFT_DOOR`/`RIGHT_DOOR` split apart. Run `npm run inspect` to
  see all three groupings side by side.

`public/models/rack.glb` is a 7 MB copy of the source and is currently untracked,
matching how the other model files in this repo are handled. Commit or ignore it
to taste — the app needs it present to run.
