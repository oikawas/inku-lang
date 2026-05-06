# inku Android Implementation Notes

This directory is a local Android workspace and is intentionally ignored by Git.

Last updated: 2026-05-06.

## Fixed Decisions

- Native Android implementation in Kotlin and Jetpack Compose.
- Room is the official database layer.
- SQLite is stored inside the application sandbox.
- Single-user standalone package.
- The local model provider is the default provider.
- External providers remain available for compatibility with the web reference:
  OpenAI, Claude, Gemini, NVIDIA NIM, Ollama, and Intel OVMS.
- The Android pipeline keeps the reference flow:
  description -> Stage 1 -> Stage 1.5 -> Stage 2 -> JSON Score -> SVG.
- JSON Score, render metadata, history import/export, color catalogs, canvas
  aspects, SVG profiles, and render hashes must remain compatible with the web
  implementation.
- SVG generation is ported to Kotlin. The app also has a native Compose Canvas
  preview path that renders stored JSON Score directly for reliable on-device
  thumbnails and main previews.
- Gemma 4 E2B is the default local model. Gemma 4 E4B is a high-quality option.
- First launch downloads the selected local model after a license confirmation.
- Target device class is Pixel 9 or newer.

## Current Implementation Status

The Android workspace currently contains a buildable standalone application
package with namespace `app.inku.mobile`.

Implemented:

- Gradle Android project with Kotlin, Jetpack Compose, Room, and KSP.
- `MainActivity` and `InkuApplication`.
- Room database named `inku.sqlite` in the app sandbox.
- Room entities and DAOs for:
  - history items
  - app settings
  - model assets
  - provider settings
  - color catalogs
  - plugin settings
  - export templates
- Repository and ViewModel layer for drawing, batch execution, demo execution,
  history selection, local settings, and placeholder model download state.
- Local model catalog and acquisition state management for Gemma 4 E2B/E4B:
  - official LiteRT-LM Hugging Face `.litertlm` URLs
  - SHA256 metadata
  - Room-backed license acceptance state
  - resumable `.part` downloads into the app sandbox
  - progress bytes, total bytes, ready, failed, cancelled, interrupted, and verifying states
  - SHA256 verification before finalizing the model file
  - recovery of a complete, already verified `.part` file without re-downloading
  - interrupted in-progress downloads are resumable from their `.part` files
  - app-sandbox final storage under `files/models/`
- Deterministic local fallback pipeline for:
  - natural language description to normalized DDL
  - DDL to JSON Score
  - JSON Score to SVG
  - render hash and render metadata generation
- Kotlin SVG renderer port for the current primitive subset.
- Native Compose preview renderer for stored JSON Score.
- Dark Compose workbench UI based on the web reference screenshots:
  - top application header
  - mode tabs: Draw, Batch, Demo, History, Settings
  - drawing input panel
  - central render panel
  - render sub-tabs: Artwork, Prompt, JSON
  - explicit button rows for model, color catalog, and canvas selection
  - bottom history strip with thumbnails
- History operations for the selected item:
  - star / unstar
  - soft trash
  - JSON share export through Android `FileProvider`
- Startup restoration of the latest selected history item into prompt, DDL,
  catalog, and canvas settings.
- Pixel 9 status bar and navigation bar safe-area handling.

Not implemented yet:

- Real LiteRT-LM runtime integration.
- Production-polished model download UX, including background continuation,
  notification progress, metered-network policy, and low-storage recovery.
- External provider execution. Provider records exist only as compatibility
  data structures at this stage.
- Full web feature parity for import/export, plugin management, advanced
  settings, user-management equivalents, and admin/server-only web features.
- Import from web-compatible JSON exports.
- Reference compatibility tests against exported web JSON fixtures.

## Verified Device State

Latest verified device class:

- Device: Pixel 9 connected by USB.
- APK: debug build from `android/app/build/outputs/apk/debug/app-debug.apk`.

Verified on device:

- App installs and launches.
- Process remains running after launch.
- Draw action creates a new Room history item.
- Batch-generated and single-draw history entries persist in `inku.sqlite`.
- Latest checked history count: `4`.
- Latest checked render hash short: `6D8E`.
- Stored JSON Score and render metadata are visible through the JSON render tab.
- Main preview and history thumbnails render from JSON Score on device.
- Star state updates are persisted to Room and reflected back into the selected
  history UI.
- JSON share export writes `inku-<render_hash_short>.json` into the app cache
  and opens the Android share sheet through `FileProvider`.
- Gemma 4 E2B/E4B model records are seeded into Room on launch.
- Gemma 4 E2B license acceptance persists as `ready_to_download`.
- No fatal Android runtime crash was observed in the checked logcat window.

The latest local verification screenshot was written to:

```text
/tmp/inku-android-workbench.png
```

## Data Source of Truth

The Room database is the source of truth for local history and settings.
Generated SVG, JSON export files, and PNG files are derived artifacts.

Heavy user-visible exports should use Android's Storage Access Framework.
Internal model files and app-owned artifacts live in the app sandbox.

## Compatibility Boundary

The Android app has no multi-user authentication. Web user-scoped records map to
one implicit local user. User-management and admin-only features should be
represented as local settings where they still make sense, but they should not
add login or role handling.

Server-only web features are kept out of the Android runtime unless they have a
clear local single-user equivalent.

## Implementation Order

Completed or substantially implemented:

1. Project skeleton, Room schema, and compatibility data models.
2. Local settings, model download state placeholders, and provider abstraction.
3. Kotlin renderer port for the current SVG primitive subset.
4. Stage 1 / Stage 1.5 / Stage 2 pipeline shape with deterministic fallback.
5. Compose UI for single drawing, batch, demo, history, settings shell, render
   previews, prompt view, and JSON view.

Remaining next order:

1. Wire the downloaded `.litertlm` files into LiteRT-LM-backed Gemma 4 E2B/E4B
   inference stages.
2. Harden model download UX with a foreground service or WorkManager,
   notifications, metered-network policy, and user-visible storage recovery.
3. Expand the Kotlin renderer and JSON Score parser to cover the full web
   primitive and style surface.
4. Extend export compatibility from current single-item share export to full
   history import/export flows with Android Storage Access Framework.
5. Add automated compatibility tests against reference web JSON and SVG/render
   metadata fixtures.
6. Finish settings screens for provider selection, plugins, logs, exports, and
   local-only equivalents of web administration controls.

## Build And Deployment Notes

Known working debug build command from the repository workspace:

```sh
cd android
GRADLE_USER_HOME=/tmp/inku-gradle-home JAVA_HOME=/Applications/Android\ Studio.app/Contents/jbr/Contents/Home gradle :app:assembleDebug
```

USB deployment commands use the target device serial from the local environment.
Do not commit concrete local device IDs:

```sh
adb -s "$ANDROID_SERIAL" install -r android/app/build/outputs/apk/debug/app-debug.apk
adb -s "$ANDROID_SERIAL" shell am force-stop app.inku.mobile
adb -s "$ANDROID_SERIAL" shell am start -n app.inku.mobile/.MainActivity
```

Room uses WAL. When inspecting the database from the connected debug device,
pull the main database and WAL files together:

```sh
adb -s "$ANDROID_SERIAL" exec-out run-as app.inku.mobile cat databases/inku.sqlite > /tmp/inku-android.sqlite
adb -s "$ANDROID_SERIAL" exec-out run-as app.inku.mobile cat databases/inku.sqlite-wal > /tmp/inku-android.sqlite-wal
adb -s "$ANDROID_SERIAL" exec-out run-as app.inku.mobile cat databases/inku.sqlite-shm > /tmp/inku-android.sqlite-shm
```
