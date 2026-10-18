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

The host assigns the iframe URL after DOM attachment, then requests the viewer's ready state after mounting and after iframe load, so startup does not depend on a single unsolicited notification. Both sides validate the same origin, window and mount identity before exchanging work data.

The macOS app bundles the same registered build without committing a copy. Before each app build, `apple/scripts/build-macos.sh` runs `apple/scripts/sync-ddl3d-viewer.py`, which copies it unchanged, with the registration, into `apple/Sources/InkuUI/Resources/ddl3d/` (ignored by Git); after the build it compares the app's copy with the registered directory file by file, as the macOS release check does. The app serves it under the app-only origin `inku-3d://viewer/` behind the same kind of parent page and protocol, and its license list reads `THIRD_PARTY_NOTICES.txt` from that copy. A registration update needs no macOS commit; the next app build carries it. See the [Swift specification](../../apple/SWIFT_SPEC.md).

The Android app does the same at build time: the Gradle task `syncDdl3dViewer` copies the registered build, the registration and the native parent page into generated assets (never committed), and a JVM test compares the copy with the registered directory file by file. It serves them under `https://appassets.androidplatform.net/` from a WebView that reaches nothing else. See the [Android notes](../../android/ANDROID_SPEC.md).

`host/` is the native apps' parent page (`host.html`, `host.js`, `host.css`): the viewer frame, the origin/window/mount/protocol checks and the relay. Only the way to the app differs: Apple's `webkit.messageHandlers.ddl3d` with `window.inku3d.deliver`, or the MessagePort Android hands the main frame (data `inku.ddl3d.native`). Native hosts build the viewer input with the shared core's `ddl3d_snapshot` (`inku-pipeline`), which projects a stored Score and render metadata onto Web's `snapshot()` fields.

## Viewing and exports

- Drag / one finger: orbit. Right drag or Shift-drag: pan. Wheel or two fingers: zoom. Arrow keys pan, `+`/`-` zoom while the canvas has focus. `F` fits, `R` resets, and `Esc` returns to 2D when embedded.
- Front, back, left, right, top, bottom and oblique views; perspective/orthographic projection; fit/reset; full screen; grid/axes/support; wireframe/flat color; automatic rotation; separate solid thickness and layer depth controls.
- Click selects a performed object and displays its original instruction number. Double-click or Focus selection fits it. GLB nodes retain zero-based source/performed/instance IDs and pair-fill provenance.
- PNG saves the current canvas view. GLB saves geometry, the current depth, colors/opacity and the visible support. Viewer guides, selection, camera, lights, automatic rotation, and wireframe inspection are not baked into GLB. A GLB consumer supplies its own lighting.
- Only the most recent snapshot's camera/projection/thickness/layer depth/background survives a 2D round trip, in memory. Other display controls reset. Nothing persists across a page reload.

## Mapping and compatibility

The WASM adapter uses the core's saved-Score reader, resource-aware checked performance, actual free-line/arc centerlines, palette resolution and tool width/opacity. It expands placement once, converts normalized positions to short-side units, and applies each affine once. X is centered; canvas Y is inverted. Group scaling also scales solid thickness by the smaller planar singular value. It does not infer front/back placement from text or color.

Layer depth (`paint-order-joints-v3`) derives layers from resolved paint order and original instruction IDs. Score has no explicit object Z coordinate. Each performed/instance object, including copies, receives its own place in a total span of 0.8 canvas short sides. Later source layers stay in front; later objects within a layer recede. A closed arc pair and its interior share one place, and a single object starts at zero. Only visible meshes count. Straight-line endpoints meeting another line's endpoint or centerline share a joint depth, averaging the participating objects' depths. Interior joints split the host tube, with depth interpolated between joints. An endpoint touching another shape follows that rigid shape's depth. Interior crossings alone do not create connections. The Layer depth slider scales layer, individual-object and joint depths together from 0 to 3; 0 restores their centerlines to Z=0. Solid thickness changes tube thickness independently without separating joints. This interprets paint order, not physical distance, and does not prevent intersections. GLB retains the deformed geometry, node translations and layer/joint metadata.

Ellipsoid Z radius is the smaller planar radius. Circles and ellipses use isolated Display SVG marks from the shared painter, including brushwork, surfaces, spread and clipping. Their painted alpha defines the sphere's equator and a front-projected texture preserves its color without added lighting. Unfilled rounds retain the original painted outline without added globe bands. Point mapping remains unchanged. Other unfilled objects use tube outlines and dashes partition tubes. Prism/box depth is the shorter planar extent. The triangle's three front vertices and rear apex form a closed pyramid. Cloud contours shrink into rings toward two poles. Filled closed arc pairs add an interior solid while retaining both source strokes. Source instruction groups organize the exported nodes; overlapping DDL scopes are not converted into a new 3D hierarchy.

Fill scopes intersect the actual mesh with extruded clip contours, including nested scopes, so GLB carries the clipped geometry. Completely clipped objects are counted explicitly. Recoverable Score diagnostics use the same shared performance rules as 2D: a failed relation can be removed while retaining its shape, and an unavailable source unit can be omitted while keeping independent shapes. A visible notice lists these decisions with original source IDs, and GLB model metadata retains them. A recovered diagnostic does not reject the whole work. The saved Score is never rewritten.

Circle and ellipse subdivisions adapt to their painted bounds and count, reserving half the triangle budget for other geometry. All marks and their painted textures remain present; hard resource limits still apply. Abstract presence comes from the shared painter as a transparent plane behind the solids and ahead of the support, with a display note. Its SVG is capped at 256 KiB and its raster at 1,024 pixels on the longer side. The plane follows the back of the model when thickness or layer spacing changes and is included in PNG and GLB.

Straight lines whose finite centerline points all coincide have no tube. The viewer keeps them separate without inventing a length or adding point solids, and continues showing the other shapes. The 3D controls report their count and original instruction numbers. GLB model metadata retains their source/performed/instance IDs in `emptyPaths`. They do not contribute depth layers. Saved Scores and normal 2D rendering are unchanged.

Invalid/unknown Scores, integrity failures, other degenerate geometry, unsupported contours and the viewer's own resource overruns still produce a failure with 2D recovery. Recovery from the saved Score's limits does not enlarge the viewer's limits.

All marks, including squares, lines and closed arc interiors, receive isolated SVG paint from the current shared 2D painter with the saved seed and colors. This carries material filters, surface marks and ink spread. Front and back retain the SVG alpha. Extruded walls unfold Z through the texture and use pigment where the SVG is transparent, translating filter opacity to tonal variation on a solid wall. White specular bands are not added: painted materials are unlit and the fallback uses diffuse lighting. Circle and ellipse silhouettes still follow the painted radius. Raster resolution, idealized non-round geometry and tessellation bound fidelity. Missing saved seeds/colors use core defaults with a note; saved 2D SVGs remain the historical reference.

Paint appearance limits: 2 MiB per isolated SVG, 16 MiB total SVG, at most 1,024 pixels per texture side and 16 million texture pixels in total, including the wall maps, without mipmaps. Each browser SVG decode has a five-second deadline. Replacing the work disposes its textures as well as meshes and materials.

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

The macOS app follows the Web registration at its next build: with an empty `viewerUrl`, the build copies the registration alone, and the app hides the switch and reads no viewer file. An app built without any copy (a plain `swift build`) has no switch either. To remove the app's part, also remove the conditional `ddl3d` resource in `apple/Package.swift` and its entry in `apple/.gitignore`, `Ddl3D.swift` (with `Ddl3DViewerNotices`), `Ddl3DWebHost.swift` and `Views/Ddl3DViews.swift` under `apple/Sources/InkuUI/`, the 3D branches in `ArtworkCanvas`, `CreationControls`, `CreationView`, `ContentView` and `WorkspaceUIState`, the `ddl3d` notices group and entry in `ThirdPartyNoticesView` and the Release attachment's entry in `apple/scripts/build-macos-notices.py`, `apple/scripts/sync-ddl3d-viewer.py` with its two steps in `apple/scripts/build-macos.sh` and its release check, and InkuAppCheck `--ddl3d-only` with its two tooltip table rows.
