# Apple clients

This SwiftUI client is developed for macOS first. DDL, Score, prompts, state transitions, seeds, SVG generation, and rasterization use the same Rust core as Server and Android. The Swift host owns networking, Keychain, SQLite, OS lifecycle, and native presentation. The application runs without an inku Server or embedded Python runtime. The macOS application has no camera feature.

Swift-specific behavior is defined by the Japanese canonical [SWIFT_SPEC.ja.md](SWIFT_SPEC.ja.md) and its maintained English version, [SWIFT_SPEC.md](SWIFT_SPEC.md). Following Android's workflow, update the Japanese specification first and then synchronize English. Add dated product changes to the repository-root [CHANGELOG.ja.md](../CHANGELOG.ja.md) and [CHANGELOG.md](../CHANGELOG.md); Swift SPEC records the current behavior and incomplete scope. Root SPEC remains canonical for shared DDL, Score, and rendering meaning.

## Current scope

Following the M1 Swift/Rust and M2 standalone host/SQLite foundations, macOS now connects creation, whole-database history/library, lineage, DDL editing/hole approval, plugins/saijiki, comparison/advice/colophons, batch/demo, local settings, and all export formats. Saved-work facts are separate from upcoming input settings, and ordinary display is separate from explicit replay. See the 2026-10-03 section of [Swift SPEC](SWIFT_SPEC.md) for behavior and evidence boundaries.

Bounded checks have established DDL → Score/SVG → SQLite save → reload after recreating the app model, native CGImage creation, and export of the saved canonical SVG. Boundary checks cover owned pixels, input errors, and preservation of UInt64 seeds. macOS arm64/x86_64 Rust slices, linking an x86_64 Swift executable, and generating iOS device/simulator Rust artifacts have also been checked. Intel hardware performance and startup, requests to real LLM providers, and author acceptance of ordinary screen interactions are separate checks.

Isolated native checks of the updated Universal app confirmed DDL generation, an edited child, library comments/stars, Trash/restore, restart persistence, Japanese/English switching, lineage and PNG2160 saving of two selected works. Source integration, focused offline checks, native interaction and author acceptance are recorded separately. Old Server/Android physical DB import, real providers/OAuth, other native export recipes/performance, physical Intel/macOS14 and signing/distribution remain incomplete. The retired history.json migration array is not a current Web restoration format. iOS has shared packages and initial Rust artifacts; regeneration for the latest APIs, iPad/iPhone applications, camera, sharing and real-device acceptance remain incomplete.

Personal ChatGPT is explicitly enabled and connected in its dedicated settings page, where an offered drawing model is selected. It is separate from API key connections and disabled by default. An issued client ID and personal consent are required; actual sign-in, model discovery and inference remain unaccepted. Description, sketch, automatic color and DDL hole filling are supported; unavailable uses such as Vision refinement and colophons are explained in the UI. See the [Swift specification](SWIFT_SPEC.md#personal-chatgpt).

## Operating systems and build environment

Minimum deployment versions are macOS 14 and iOS 17. SDK versions are independent of deployment minimums. The checked environment uses Xcode 27.0/Swift 6.4, Rust 1.95.0, and XcodeGen 2.46.0. Swift packages require tools 6.1, and the project requires XcodeGen 2.44.0 or newer.

Building requires macOS, Xcode command-line tools, XcodeGen, Python 3.11 or newer, uv, and official rustup. Python/uv generate Server-derived build resources and pinned dictionaries, and are not embedded in the app. The first build needs network access for pinned Cargo, SwiftPM, and Server uv.lock dependencies.

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

## Normal use and an isolated trial

The initial input is direct English DDL, so generation can be tried without a model connection. For description input, save a provider type, base URL, model, and any required API key in Settings, then select description mode in the creation screen. Multiple API services can be registered; Stage1/Stage2 share the drawing model. Model discovery uses an explicit button. Saving a connection does not send an LLM request.

Choose the next service/model in the creation screen's Next generation settings. This does not change saved Settings defaults or running batch/demo requests. Generate/Stop remains outside the input scroll area. Command-N creates a new work, Command-O imports DDL, Command-comma opens Settings, Command-1 through 4 navigate screens, and Shift-Command-E opens export. Library checkboxes are distinct from the displayed work; creation exports its displayed saved work.

Saved-work actions offer Change description and Redraw with/without sketch to draw a new child of that work. Direct-DDL and committed DDL-edited works cannot return to description authority. The catalog chooser shows color names, HEX values and explanations before applying the next generation settings. Import one DDL file through the standard panel or a window drop to update an unsaved creation draft.

Edit drawing parameters compares one/four composition, reading, or variation options, or one word-based touch option, and saves only selected options as children. Preparing or enlarging an option does not change the displayed work or normal history. Touch uses saved Score and shared Rust word seeds; the screen explains that current variation changes nothing. Stop/discard and adoption are separate. Adopt or discard unsaved options before moving to model Settings.

The database is stored in the application's Application Support directory. Ordinary provider settings are stored beside it in `providers.json`; API keys are separate Keychain items. SQLite backup contains works, lineage, executions/ACKs/snapshots, comments/marks, colophons, and unread words. It does not back up adjacent settings JSON or Keychain items.

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

Bounded CLI checks are available through `apple/scripts/check-core.sh` after artifact generation and `swift run --package-path apple InkuAppCheck` after resource generation. Select `--authoring-only`, `--comparison-only`, `--automation-only`, `--plugin-only`, `--model-selection-only`, `--work-edit-only`, `--refinement-only`, `--replay-comparison-only`, `--auxiliary-provenance-only`, or `--raster-only <SVG path>` for the relevant change. `--model-selection-only` uses a temporary DB and zero provider calls to verify creation model selection separately from saved defaults and startup snapshots. `--work-edit-only` uses mock transport and the shared core for saved-parent editing, sketch changes, a child's DDL authority, and cancellation. `--refinement-only` uses that isolated boundary for word seeds/saved Score, frozen four-option plans, no-op variation, explicit adoption/reopened DDL children, edge metadata, and late-response rejection. `--replay-comparison-only` checks provider-free comparison without persistence/display changes and its seed/stop boundaries; `--auxiliary-provenance-only` checks per-generation Vision/random provenance with mocks. These do not replace native screen, real-provider, or device acceptance. Run only checks needed for the concrete failure a change prevents.
