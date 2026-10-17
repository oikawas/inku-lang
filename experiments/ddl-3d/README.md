# DDL 3D experiment

An optional, independent browser viewer for an existing Score JSON. Circles become spheres, squares become cubes or rectangular solids, triangles become pyramids, polygons become prisms, and lines become closed tubes. The canvas's Work tab can opt into the viewer without changing saved works. A button immediately left of the hash button at the bottom right names the destination: 3D in 2D mode, and 2D in 3D mode. Both modes keep the same overlaid work controls; zoom and full screen target the active view. Other work actions keep their saved-work meaning. The 3D controls, object counts and diagnostics are grouped in a collapsible overlay above the artwork, clear of its caption and bottom controls.

The first camera is front-facing and orthographic. Its world-to-pixel scale and pan come from the host's current 2D canvas, preserving frontmost-object size. Camera changes then remain independent; returning to the same work recalls them. Background choices are None (transparent), Support, Blue sky, Starry sky, Background fill color, White background and Black background; skies are local procedural textures without network requests. Background fill color is the default on first opening and when restoring a view state without a background choice. It uses the resolved saved-work background; White background and Black background use fixed white or black across the entire view. The view state remembers the background without changing the work. Reset restores the initial front view and thickness/layer depth while keeping the background.

The experiment has its own npm and Cargo locks. The main Web package imports no Three.js or WASM code. The only shared-core additions are the default-off `inku-render/geometry-export` feature, its read-only module, and a feature-gated arc-centerline wrapper. No database, server endpoint, migration, model call, storage write, or backup task is added.

## Build and local use

Run from a product checkout. Use the repository's pinned Rust toolchain, including its `wasm32-unknown-unknown` target, Node 22.12+ and npm. The wasm-bindgen CLI must match `0.2.129` in the adapter lock.

```sh
scripts/rust-toolchain.sh install wasm-bindgen-cli --version 0.2.129 --locked --root "$PWD/experiments/ddl-3d/.tools"
npm ci --prefix experiments/ddl-3d
WASM_BINDGEN="$PWD/experiments/ddl-3d/.tools/bin/wasm-bindgen" npm run build:wasm --prefix experiments/ddl-3d
npm run build --prefix experiments/ddl-3d
npm run preview --prefix experiments/ddl-3d -- --host 127.0.0.1 --port 5191 --strictPort
```

Open the local URL and choose a JSON file. Accepts a Score itself or an object with `score` plus saved rendering metadata. `fixtures/solids.json` includes deterministic example metadata. Everything stays in the browser.

`build:wasm` emits `public/wasm/provenance.json` with the core base SHA, dirty flag, source hash including new untracked core files, and adapter/mapping versions. Runtime results also carry the Score schema digest and engine version. A base SHA alone does not identify a dirty build. The build collects dependency license texts into `public/THIRD_PARTY_NOTICES.txt` for distribution with the viewer.

## Web connection and distribution

The Web app ships the separately built viewer registered in `web/src/lib/features/experimental-3d/installation.json`. The initial view remains 2D. Three.js, the Worker and WASM load only after selecting 3D. Main Web dependencies and build scripts do not build or import the viewer; the viewer's own package and locks produce a self-contained static distribution.

After building, install a uniquely named static artifact in the intended product checkout:

```sh
npm run install:viewer --prefix experiments/ddl-3d -- /absolute/product-checkout local-3d-001
```

The script prints `VITE_DDL_3D_VIEWER_URL=/experimental/ddl-3d/local-3d-001/index.html`. Set this at **Web build/dev startup** to override the bundled registration for a local build. With no override, the bundled viewer is available. Only same-origin versioned paths of this form are accepted. Installation refuses symlink destinations and existing build directories. It does not start, restart, or deploy any service.

For a distribution update, build from a clean, committed core source, install under a new immutable build name, update `installation.json`, and allow that exact directory in `web/.gitignore`. Commit the entire directory, including `wasm/provenance.json` and `THIRD_PARTY_NOTICES.txt`. Deploy it with the Web static files through the normal deployment workflow. Keep the previous directory while any running page still references it; never overwrite an existing build in place.

The bridge projects only the current Score and saved color/aspect/seed/version metadata into an immutable JSON string. It supports a saved work, a newly created work, and an unsaved candidate without requiring a history ID. Decimal seed strings never pass through `Number`. Unsafe numeric seeds are rejected rather than silently rounded.

## Viewing and exports

- Drag / one finger: orbit. Right drag or Shift-drag: pan. Wheel or two fingers: zoom. Arrow keys pan, `+`/`-` zoom while the canvas has focus. `F` fits, `R` resets, and `Esc` returns to 2D when embedded.
- Front, back, left, right, top, bottom and oblique views; perspective/orthographic projection; fit/reset; full screen; grid/axes/support; wireframe/flat color; automatic rotation; separate solid thickness and layer depth controls.
- Click selects a performed object and displays its original instruction number. Double-click or Focus selection fits it. GLB nodes retain zero-based source/performed/instance IDs and pair-fill provenance.
- PNG saves the current canvas view. GLB saves geometry, the current depth, colors/opacity and the visible support. Viewer guides, selection, camera, lights, automatic rotation, and wireframe inspection are not baked into GLB. A GLB consumer supplies its own lighting.
- Only the most recent snapshot's camera/projection/thickness/layer depth/background survives a 2D round trip, in memory. Other display controls reset. Nothing persists across a page reload.

## Mapping and compatibility

The WASM adapter uses the core's saved-Score reader, resource-aware checked performance, actual free-line/arc centerlines, palette resolution and tool width/opacity. It expands placement once, converts normalized positions to short-side units, and applies each affine once. X is centered; canvas Y is inverted. Group scaling also scales solid thickness by the smaller planar singular value. It does not infer front/back placement from text or color.

Layer depth (`paint-order-v1`) derives layers from the resolved geometry's paint order and original instruction IDs. Score has no explicit object Z coordinate. Copies of one instruction share a layer; arc pairs forming one closed fill share a layer so their contours and interior stay together. Only sources with visible meshes count. The first visible layer sits at negative Z, the last at positive Z, over a total span of 0.8 canvas short sides at the default setting. The slider scales this span from 0 to 3; 0 restores all centers to Z=0, and a single layer stays at Z=0. Solid thickness changes independently. This is an interpretation of drawing order, not a distance estimate or a guarantee against intersections. GLB retains node translations and layer metadata.

Ellipsoid Z radius is the smaller planar radius. Circles and ellipses use isolated Display SVG marks from the shared painter, including brushwork, surfaces, spread and clipping. Their painted alpha defines the sphere's equator and a front-projected texture preserves its color without added lighting. Unfilled rounds retain the original painted outline without added globe bands. Point mapping remains unchanged. Other unfilled objects use tube outlines and dashes partition tubes. Prism/box depth is the shorter planar extent. The triangle's three front vertices and rear apex form a closed pyramid. Cloud contours shrink into rings toward two poles. Filled closed arc pairs add an interior solid while retaining both source strokes. Source instruction groups organize the exported nodes; overlapping DDL scopes are not converted into a new 3D hierarchy.

Fill scopes intersect the actual mesh with extruded clip contours, including nested scopes, so GLB carries the clipped geometry. Completely clipped objects are counted explicitly. Recoverable Score diagnostics use the same shared performance rules as 2D: a failed relation can be removed while retaining its shape, and an unavailable source unit can be omitted while keeping independent shapes. A visible notice lists these decisions with original source IDs, and GLB model metadata retains them. A recovered diagnostic does not reject the whole work. The saved Score is never rewritten.

Presence layers, invalid/unknown Scores, integrity failures, degenerate geometry, unsupported contours and the viewer's own resource overruns still produce a failure with 2D recovery. Recovery from the saved Score's limits does not enlarge the viewer's limits.

For shapes other than circles and ellipses, tool grain, paper texture, ink spread and some organic surface variation are approximated and listed in Details. Lighting changes those shapes' apparent color. Circle textures use the current shared 2D painter with the saved seed and colors; their raster resolution and the sphere's tessellation bound fidelity. Missing saved seeds/colors use core defaults with a note. Existing 2D SVGs remain the reference for historical appearance.

Circle appearance limits: 2 MiB per isolated SVG, 16 MiB total SVG, at most 1,024 pixels per texture side and 16 million texture pixels in total without mipmaps. Each browser SVG decode has a five-second deadline. Replacing the work disposes its textures as well as meshes and materials.

Default limits: 16 MiB input, 4,096 objects, 500,000 triangles, 128 MiB mesh-buffer estimate, 32 nested clips, DPR ≤2, and a 10-second cancellable preparation. Saved resource-policy ceilings must fit the experiment's ceilings; their identities and stricter budgets are then retained. Input cannot enlarge the experiment's limits. Worker termination interrupts WASM/mesh work. A new work removes the previous scene before preparation. Rendering runs on change or while automatic rotation is enabled, and pauses in hidden tabs. Unmount disposes Workers, controls, listeners, animation callbacks and GPU resources.

## Verification

Each check covers a specific boundary: depth/aspect/handedness, clipping in exported geometry, long seeds, one-time placement, free-line curves, invalid input, or excessive mesh demand.

```sh
scripts/rust-toolchain.sh test --manifest-path "$PWD/experiments/ddl-3d/score-adapter/Cargo.toml" --locked
npm test --prefix experiments/ddl-3d
npm run check --prefix experiments/ddl-3d
npm run check --prefix web
npm run lint:i18n --prefix web
```

Build WASM before the Node tests. Browser verification must cover actual Work-tab switching, recovery, exports, and the 2D viewport. Unit and build checks alone are not GUI acceptance.

## Disable or remove

To disable, set `VITE_DDL_3D_VIEWER_URL=off` and rebuild/start Web using its normal workflow. Alternatively, set the registration's `viewerUrl` to an empty string and rebuild/start Web. This hides the switch and does not load viewer assets. Unsetting the environment override restores the bundled registration. This needs no database operation. Existing distributed asset directories may be removed separately when no page uses them.

To remove the implementation, remove `experiments/ddl-3d/`, `web/src/lib/features/experimental-3d/` (including the registration), `web/static/experimental/ddl-3d/`, the experimental imports/switch/conditional and `viewMode` guards in `CanvasPanel.svelte`, and the mode state/binding/keyboard condition in `+page.svelte`. Remove the seven `ddl3d*` labels from the two locale files and their type declarations. Remove the optional Cargo feature, module declaration and `geometry_export.rs`, and the feature-gated `export_arc_centerline` wrapper in `marks.rs`. Restore the original 2D branch and wheel/keyboard conditions. Remove the static-assets ignore entries and experimental SPEC/CHANGELOG entries as appropriate. The main npm/Cargo membership, DB and saved works have no reverse migration. Build and check Web and the default core afterward.
