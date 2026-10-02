# Apple clients

This SwiftUI client is developed for macOS first. DDL, Score, prompts, state transitions, seeds, SVG generation, and rasterization use the same Rust core as Server and Android. The Swift host owns networking, Keychain, SQLite, OS lifecycle, and native presentation. The application runs without an inku Server or embedded Python runtime. The macOS application has no camera feature.

Swift-specific behavior is defined by the Japanese canonical [SWIFT_SPEC.ja.md](SWIFT_SPEC.ja.md) and its maintained English version, [SWIFT_SPEC.md](SWIFT_SPEC.md). Following Android's workflow, update the Japanese specification first and then synchronize English. Add dated product changes to the repository-root [CHANGELOG.ja.md](../CHANGELOG.ja.md) and [CHANGELOG.md](../CHANGELOG.md); Swift SPEC records the current behavior and incomplete scope. Root SPEC remains canonical for shared DDL, Score, and rendering meaning.

## Current scope

The M1 Swift/Rust foundation, M2 standalone host and SQLite boundary, and initial macOS screens are implemented. Connected actions include direct DDL generation, selecting and replaying saved work, DDL/Score display, canvas zoom and pan, recent work, library search, provider settings, SVG/PNG export, image copying, and database backup/restore.

Bounded checks have established DDL → Score/SVG → SQLite save → reload after recreating the app model, native CGImage creation, and export of the saved canonical SVG. Boundary checks cover owned pixels, input errors, and preservation of UInt64 seeds. macOS arm64/x86_64 Rust slices, linking an x86_64 Swift executable, and generating iOS device/simulator Rust artifacts have also been checked. Intel hardware performance and startup, requests to real LLM providers, and author acceptance of ordinary screen interactions are separate checks.

The full M3 UI remains incomplete. Lineage graphs, favorite/trash actions, plugin/model advice dialogs, batch/demo operation, custom and animated exports, and share cards remain future work. The lineage screen identifies its current unavailable state. iOS currently has shared packages and Rust artifact foundations; iPad/iPhone applications, camera, sharing, and real-device acceptance remain incomplete.

## Operating systems and build environment

Minimum deployment versions are macOS 14 and iOS 17. SDK versions are independent of deployment minimums. The checked environment uses Xcode 27.0/Swift 6.4, Rust 1.95.0, and XcodeGen 2.46.0. Swift packages require tools 6.1, and the project requires XcodeGen 2.44.0 or newer.

Building requires macOS, Xcode command-line tools, XcodeGen, Python 3.11 or newer, and official rustup. Python only generates build resources from the Server source and is not embedded in the application. An initial build needs network access to fetch pinned Cargo and SwiftPM dependencies.

Key pinned dependencies are UniFFI 0.32.0 and GRDB 7.11.1. Rust versions are governed by `core/rust-toolchain.toml` and `core/Cargo.lock`; GRDB is governed by `Packages/InkuPersistence/Package.swift` and SwiftPM resolution records. The UniFFI generator is built from the same checkout's Cargo.lock and reads metadata from that Rust archive.

## Build macOS from a clean clone

Run these commands from the product repository root. After preparing Xcode and the required tools, install the pinned Rust toolchain and Mac targets. Scripts do not install toolchains or change Xcode or Apple account settings automatically.

```sh
rustup toolchain install 1.95.0 --profile minimal --component rustfmt --component clippy
rustup target add --toolchain 1.95.0 aarch64-apple-darwin x86_64-apple-darwin
apple/scripts/build-macos.sh Release
```

`build-macos.sh` generates resources from the Server source, builds the shared Rust core and Swift binding/XCFramework, generates an Xcode project from `project.yml`, and builds the macOS application. It selects a generic Mac destination, `ARCHS=arm64 x86_64`, and `ONLY_ACTIVE_ARCH=NO`, then verifies both slices. This is an unsigned local build without an Apple account, Team, or certificate. Signing, notarization, and distribution are outside this procedure.

The default is a Release application with release Rust archives. Selecting a Debug Xcode application still uses release Rust unless explicitly overridden. For both debug configurations, use:

```sh
INKU_APPLE_PROFILE=debug apple/scripts/build-macos.sh Debug
```

The Release application is generated at `apple/build/macOS/DerivedData/Build/Products/Release/Inku.app`. To use Xcode, open the generated `apple/Inku.xcodeproj`. Build outputs, Server-derived resources, Swift bindings, and the XCFramework are regenerated artifacts. Repeat the same procedure after source changes.

```sh
open apple/build/macOS/DerivedData/Build/Products/Release/Inku.app
```

## Normal use and an isolated trial

The initial input is direct English DDL, so generation can be tried without a model connection. For description input, save a provider type, base URL, model, and any required API key in Settings, then select description mode in Create. The current settings screen provides one connection and uses the same model for Stage1 and Stage2. Saving the connection does not send an LLM request.

The database is stored in the application's Application Support directory. Ordinary provider settings are stored beside it in `providers.json`; API keys are separate Keychain items. SQLite backup provides a consistent database copy containing work, lineage, executions, ACKs, and snapshots. It does not back up provider JSON or Keychain items.

To try the application with a temporary database, pass `--database` to its executable:

```sh
preview_dir="$(mktemp -d)"
apple/build/macOS/DerivedData/Build/Products/Release/Inku.app/Contents/MacOS/Inku \
  --database "$preview_dir/inku.sqlite"
```

This changes the database location and adjacent provider JSON location. Keychain remains independent. Reading saved work does not recompile DDL or regenerate its stored SVG. Replay is an explicit operation that creates a new saved result.

## Shared packages and iOS artifacts

`Packages/InkuCore` provides the owned `Data` API and generated UniFFI bindings, `Packages/InkuHost` provides provider transport and execution actors, `Packages/InkuPersistence` provides the GRDB/SQLite adapter, and `Sources/InkuUI` provides native screens and the app model. Swift source does not duplicate core semantics.

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

Bounded CLI checks are available through `apple/scripts/check-core.sh` after artifact generation, and `swift run --package-path apple InkuAppCheck` after resource generation. These do not replace native screen, real-provider, or device acceptance. Select only checks needed for the concrete failure a change prevents.
