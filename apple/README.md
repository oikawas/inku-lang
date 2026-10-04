# Apple clients

This SwiftUI client is developed for macOS first. DDL, Score, prompts, state transitions, seeds, SVG generation, and rasterization use the same Rust core as Server and Android. The Swift host owns networking, Keychain, SQLite, OS lifecycle, and native presentation. The application runs without an inku Server or embedded Python runtime. The macOS application has no camera feature.

Swift-specific behavior is defined by the Japanese canonical [SWIFT_SPEC.ja.md](SWIFT_SPEC.ja.md) and its maintained English version, [SWIFT_SPEC.md](SWIFT_SPEC.md). Following Android's workflow, update the Japanese specification first and then synchronize English. Add dated product changes to the repository-root [CHANGELOG.ja.md](../CHANGELOG.ja.md) and [CHANGELOG.md](../CHANGELOG.md); Swift SPEC records the current behavior and incomplete scope. Root SPEC remains canonical for shared DDL, Score, and rendering meaning.

## Current scope

Following the M1 Swift/Rust and M2 standalone host/SQLite foundations, macOS now connects creation, whole-database history/library, lineage, DDL editing/hole approval, plugins/saijiki, comparison/advice/colophons, batch/demo, local settings, and all export formats. Saved-work facts are separate from upcoming input settings, and ordinary display is separate from explicit replay. See the 2026-10-03 section of [Swift SPEC](SWIFT_SPEC.md) for behavior and evidence boundaries.

Bounded checks have established DDL → Score/SVG → SQLite save → reload after recreating the app model, native CGImage creation, and export of the saved canonical SVG. Boundary checks cover owned pixels, input errors, and preservation of UInt64 seeds. macOS arm64/x86_64 Rust slices, linking an x86_64 Swift executable, and generating iOS device/simulator Rust artifacts have also been checked. Intel hardware performance and startup, requests to real LLM providers, and author acceptance of ordinary screen interactions are separate checks.

Isolated native checks of the updated Universal app confirmed DDL generation, an edited child, library comments/stars, Trash/restore, restart persistence, Japanese/English switching, lineage and PNG2160 saving of two selected works. Source integration, focused offline checks, native interaction and author acceptance are recorded separately. Old Server/Android physical DB import, real providers/OAuth, other native export recipes/performance, physical Intel/macOS14 and signing/distribution remain incomplete. The retired history.json migration array is not a current Web restoration format. iOS has shared packages and initial Rust artifacts; regeneration for the latest APIs, iPad/iPhone applications, camera, sharing and real-device acceptance remain incomplete.

Personal ChatGPT is explicitly enabled and connected in its dedicated settings page, where an offered drawing model is selected. It is separate from API key connections and disabled by default. An issued client ID and personal consent are required; actual sign-in, model discovery and inference remain unaccepted. Description, sketch, automatic color, composition reading and DDL hole filling are supported; unavailable uses such as Vision refinement and colophons are explained in the UI. See the [Swift specification](SWIFT_SPEC.md#personal-chatgpt).

## Operating systems and build environment

Minimum deployment versions are macOS 14 and iOS 17. SDK versions are independent of deployment minimums. The checked environment uses Xcode 27.0/Swift 6.4, Rust 1.95.0, and XcodeGen 2.46.0. Swift packages require tools 6.1, and the project requires XcodeGen 2.44.0 or newer.

Building requires macOS, Xcode command-line tools, XcodeGen, Python 3.11 or newer, Node.js 22.13 or newer, uv, and official rustup. Node.js [`stripTypeScriptTypes`](https://nodejs.org/download/release/v22.14.0/docs/api/module.html#modulestriptypescripttypescode-options) extracts Web text, canvas metadata, and Saijiki previews from the same checkout into build resources. Python/uv prepare Server data and pinned dictionaries; none of these runtimes is embedded in the app. The first build needs network access for pinned Cargo, SwiftPM, and Server uv.lock dependencies.

Key pinned dependencies are UniFFI 0.32.0 and GRDB 7.11.1. Rust versions are governed by `core/rust-toolchain.toml` and `core/Cargo.lock`; GRDB is governed by `Packages/InkuPersistence/Package.swift` and SwiftPM resolution records. The UniFFI generator is built from the same checkout's Cargo.lock and reads metadata from that Rust archive.

## Build macOS from a clean clone

Run these commands from the product repository root. After preparing Xcode and the required tools, install the pinned Rust toolchain and Mac targets. Scripts do not install toolchains or change Xcode or Apple account settings automatically.

```sh
rustup toolchain install 1.95.0 --profile minimal --component rustfmt --component clippy
rustup target add --toolchain 1.95.0 aarch64-apple-darwin x86_64-apple-darwin
apple/scripts/build-macos.sh Release
```

`build-macos.sh` generates defaults, catalogs, saijiki, and plugin resources from Server source and prepares locked build dependencies with `uv sync --project server --frozen`. The [dictionary script](scripts/prepare-meter-resources.py) verifies hashes for Sudachi small (about 113 MiB), reading configuration, and CMUdict, then copies them with their licenses into InkuHost resources. It builds shared Rust/bindings/XCFramework, generates the Xcode project, and builds a generic Mac destination with `ARCHS=arm64 x86_64` and `ONLY_ACTIVE_ARCH=NO`, then verifies both slices. This is an unsigned local build without an Apple account, Team, or certificate. Signing, notarization, and distribution are outside this procedure.

To avoid Rust 1.95's macOS host proc-macro [LINKEDIT alignment issue](https://github.com/rust-lang/rust/issues/157750), release builds disable stripping only for host build dependencies. Target Rust archive optimization and stripping remain enabled. No cache deletion or toolchain change is required.

The default is a Release application with release Rust archives. Selecting a Debug Xcode application still uses release Rust unless explicitly overridden. For both debug configurations, use:

```sh
INKU_APPLE_PROFILE=debug apple/scripts/build-macos.sh Debug
```

The Release application is generated at `apple/build/macOS/DerivedData/Build/Products/Release/Inku.app`. To use Xcode, open the generated `apple/Inku.xcodeproj`. Build outputs, Server-derived resources, Swift bindings, and the XCFramework are regenerated artifacts. Repeat the same procedure after source changes.

```sh
open apple/build/macOS/DerivedData/Build/Products/Release/Inku.app
```

### Keep one app in the Dock

The macOS icon is generated from the existing incu image and bundled with the app. Build and install at a fixed location with:

```sh
apple/scripts/build-macos.sh Release --install
open ~/Applications/Inku.app
```

Add this fixed app to the Dock once and keep using the same entry. Quit Inku before rebuilding. Installation retains the app directory while updating its contents, bundle ID, and database choice. A build without `--install` does not update the installed app.

To install an already built app against an existing trial database, pass its absolute path to the [installer](scripts/install-macos.py):

```sh
python3 apple/scripts/install-macos.py \
  --app apple/build/macOS/DerivedData/Build/Products/Release/Inku.app \
  --database /absolute/path/to/inku.sqlite
```

The database is not copied or moved. Its path is retained in the `InkuDatabasePath` bundle setting, so Dock launches use the same database. An explicit `--database` launch argument takes precedence.

## Normal use and an isolated trial

Batch takes one description per work on each line. Full-width history, previous-run resume information, next conditions, and the new-batch action follow the editor. New batches offer no DDL input. The model row's Change button opens service-grouped cards for shared Stage 1/2 selection; choose a draft and Confirm to apply it. Cancel and close retain the original selection. An enabled registered LLM is required; an unknown default waits for selection. The color dialog offers an automatic-description card followed by catalogs with ten color samples. Confirm or close applies the draft; Cancel discards it. There is no random choice.

Check sketch from life Off/On, Wild Off/On, and canvas, then choose Draw new batch. Batch sketch is independent of Paint and does not inherit a supplied sketch. Language and seed are under Details. The start action sits immediately after conditions; narrow layouts scroll through the work area as well. Blank lines retain original numbering, long lines scroll horizontally, and ruler numbers stay inside the editor.

Explicit history restoration replaces only editor text. Interrupted-run cards show remaining rows and frozen starting conditions; resuming preserves completed works. Distinguish the currently processed line from the displayed successful work, and inspect history before explicitly retrying or skipping ambiguous rows. When no batch work has been observed, the selected saved work remains on the right.

The initial input is direct English DDL, so generation can be tried without a model connection. OpenAI API Platform, Claude API, Gemini API, NVIDIA NIM, Ollama, and Ollama Cloud are supplied as default connections, with missing entries added once to older settings. Existing URLs and model selections are preserved, and deleted default connections stay deleted after restarting.

For description input, choose a service card in Settings → Model settings. Use Select models to search and edit purposes and usage, then save. Cancellation discards edits. Fetch model list explicitly contacts that service and saves new candidates; it is disabled while edits are unsaved. Rename, service memo, and addition open separate sheets.

Open Connection settings to enter any required API key yourself and save it to Keychain using the adjacent Save button. Configured keys are hidden; to replace one, confirm Remove… before saving a new key. URLs and rate limits each have their own Save button. Drawing defaults and token caps are committed through Drawing defaults → Save defaults. Ollama initially uses `http://localhost:11434/v1` on this Mac; change that URL for another host. Multiple API services can be registered; Stage1/Stage2 share the drawing model. Launching, adding presets, or saving connection settings alone sends no LLM request. Disabling a model retains existing references and works, but the next description drawing requires an enabled LLM model.

Choose the next service/model in the creation screen's next drawing conditions. This does not change saved Settings defaults or running batch/demo requests. Compact conditions and a details popover are separate from This work's provenance, and Paint/Stop remain outside the input scroll area. Edit opens an independent DDL draft; Cancel leaves the shown work unchanged. Command-N creates a new work, Command-O imports DDL, Command-comma opens Settings, Command-1 through 4 navigate screens, and Shift-Command-E opens export. Library checkboxes are distinct from the displayed work; creation exports its displayed saved work.

Library preview preserves inputs in Paint. Open in Paint explicitly switches works, and closing preview returns to the full-width list. Lineage supports branch expansion and a map that restores the normal browsing position when closed. The canvas mouse wheel zooms, recentering at 100% or less. Choose the next canvas by shape and intent; ordinary Saijiki browsing is reference-only. Tooltips have a toolbar toggle. Edit drawing limits in Settings and choose Save changes to apply them to new works.

Open Model suitability and use in Creation or model settings to read Server evaluations/purposes/comments separately from service-discovered information. Unregistered services/models receive no guessed rating. During a call, stage, requested model, attempts, and elapsed time appear; unavailable usage is Not recorded. Stop freezes time, and New clears the previous card.

Measured model calls in Creation shows actual call time and reported tokens for ordinary APIs and Personal ChatGPT, separating the underdrawing, composition, and hole completion. Saved works and replay comparison read saved metrics, preserving explicit zero versus missing usage. To capture bodies during development, launch with `INKU_DEVELOPER_MODE=1` and enable Record provider input and output when drawing in Settings. Capture is off by default. A developer disclosure reads locally stored bodies. A pre-send save failure prevents the request; partial replies are marked incomplete, and endpoints, headers, and credentials are excluded. The [Swift specification](SWIFT_SPEC.md) defines these boundaries.

Saved-work actions offer Change description and Redraw with/without sketch to draw a new child of that work. Direct-DDL and committed DDL-edited works cannot return to description authority. The catalog chooser shows color names, HEX values and explanations before applying the next generation settings. Import one DDL file through the standard panel or a window drop to update an unsaved creation draft.

Edit drawing parameters compares one/four composition, reading, or variation options, or one word-based touch option, and saves only selected options as children. Preparing or enlarging an option does not change the displayed work or normal history. Touch uses saved Score and shared Rust word seeds; the screen explains that current variation changes nothing. Stop/discard and adoption are separate. Adopt or discard unsaved options before moving to model Settings.

Model settings' Rate limits controls requests per minute (RPM), input tokens per minute (TPM), and requests per day (RPD). Adjacent explanation buttons describe their scope and daily reset. Zero disables a limit; the standard Gemini service defaults to 30/16,000/14,400 when unset. Use whole numbers from zero through 1,000,000,000 according to your plan. Drawing/retry reservations are durable in SQLite. Restarting or restoring an older DB backup cannot reset today's budget/cooldown, and waiting counts toward the attempt deadline.

The database is stored in the application's Application Support directory. Ordinary provider settings are stored beside it in `providers.json`; API keys are separate Keychain items. SQLite backup contains works, lineage, executions/ACKs/snapshots, comments/marks, colophons, unread words, and request budgets. It does not back up adjacent settings JSON or Keychain items.

To try the application with a temporary database, pass `--database` to its executable:

```sh
preview_dir="$(mktemp -d)"
apple/build/macOS/DerivedData/Build/Products/Release/Inku.app/Contents/MacOS/Inku \
  --database "$preview_dir/inku.sqlite"
```

This changes the database location and adjacent provider JSON location. Keychain remains independent. Reading saved work does not recompile DDL or regenerate its stored SVG. Ordinary Replay compares the stored SVG with the current engine's recreation without changing saved work, history, or lineage. Replay with next conditions saves a new child.

## Shared packages and iOS artifacts

`Packages/InkuCore` provides owned `Data` APIs and generated bindings, `Packages/InkuHost` provides provider transport/execution actors, `Packages/InkuPersistence` provides GRDB/SQLite, `Packages/InkuExport` handles saved SVG/PNG/DDL/cards/sheets/animation, and `Sources/InkuUI` provides native screens/app state. Swift source does not duplicate core semantics.

To generate only the shared Rust artifact, run the following. Direct Swift package builds also require artifact generation first.

```sh
apple/scripts/build-core.sh macos
```

For iOS artifacts, add the targets and select `all`:

```sh
rustup target add --toolchain 1.95.0 aarch64-apple-ios aarch64-apple-ios-sim x86_64-apple-ios
apple/scripts/build-core.sh all
```

The XCFramework keeps macOS arm64/x86_64, iOS arm64 device, and iOS arm64/x86_64 simulator in separate variants. Slices from different platforms are never combined with lipo. `Packages/InkuCore/Artifacts/build-manifest.json` records the product commit, core source fingerprint, toolchain/generator, archive hashes, profile, and deployment minimums. Running `macos` again replaces the artifact with a Mac-only version, so run `all` before an iOS build.

Direct Swift package builds require resources as well as the Rust artifact:

```sh
python3 apple/scripts/export-server-resources.py
uv sync --project server --frozen
python3 apple/scripts/prepare-meter-resources.py
```

Focused UI-difference selectors are `--library-browsing-only`, `--lineage-presentation-only`, `--ddl-editor-cancel-only`, `--drawing-limits-editing-only`, and `--canvas-wheel-only`. They use isolated databases for previews, comments, lineage restoration, cancellation, and saved limits. The wheel check covers scale and position calculations only; actual native events and appearance require separate review.

Additional AppCheck selectors are `--provider-progress-only` and `--model-guidance-only`. The former uses mocks/shared Rust for retry presentation, clocks, Stop, and late callbacks. The latter uses generated Server evaluations and temporary SQLite for suitability, unknown boundaries, and preserved selections/snapshots. Neither calls a real provider.

Composition checks use `--composition-host-only` and `--composition-progress-only`. The host check uses real Rust, mocks, and temporary SQLite for effects, pinned Stage 1 model/cap, schema, saves, finite retry/fallback, and legacy settings/saved-Score replay. Progress covers stage clocks, retries, Japanese/English text, prompt-history separation, and Stop. `--composition-personal-plan-gate-only` checks only the final Personal ChatGPT routing refusal with a valid unconnected UUID and empty temporary vault, without actual HTTP, OAuth, or Keychain access.

The focused request-budget check is `swift test --package-path apple/Packages/InkuHost --filter ProviderRateLimitChecks/testDurableAdmissionDeadlineAndRetryAccounting`. Temporary SQLite, mock HTTP, and a fake clock cover concurrent reservations, deadline/day/input limits, legacy import, and backup/restore without real providers, credentials, or the ordinary work DB.

Bounded CLI checks are available through `apple/scripts/check-core.sh` after artifact generation and `swift run --package-path apple InkuAppCheck` after resource generation. Select `--authoring-only`, `--comparison-only`, `--automation-only`, `--plugin-only`, `--model-selection-only`, `--work-edit-only`, `--refinement-only`, `--replay-comparison-only`, `--auxiliary-provenance-only`, or `--raster-only <SVG path>` for the relevant change. `--model-selection-only` uses a temporary DB and zero provider calls to verify creation model selection separately from saved defaults and startup snapshots. `--work-edit-only` uses mock transport and the shared core for saved-parent editing, sketch changes, a child's DDL authority, and cancellation. `--refinement-only` uses that isolated boundary for word seeds/saved Score, frozen four-option plans, no-op variation, explicit adoption/reopened DDL children, edge metadata, and late-response rejection. `--replay-comparison-only` checks provider-free comparison without persistence/display changes and its seed/stop boundaries; `--auxiliary-provenance-only` checks per-generation Vision/random provenance with mocks. These do not replace native screen, real-provider, or device acceptance. Run only checks needed for the concrete failure a change prevents.
