# inku Swift Implementation Specification

This directory contains the native SwiftUI client, developed for macOS first, and the shared Apple packages. [SWIFT_SPEC.ja.md](SWIFT_SPEC.ja.md) is the canonical specification for Swift host behavior; this document is its maintained English version. The [product specification](../SPEC.md) defines shared DDL, Score, prompts, authoring authority, pipeline transitions, seeds, and rendering semantics. Server remains the primary development host, and Swift follows the same Rust core without duplicating semantic processing.

Last updated: 2026-10-02.

Binding and protocol identities come from the bundled Rust core's version report; rendering layer identities use render metadata and the [Server layer definitions](../server/src/inku_server/layer_versions.py). Do not duplicate shared engine version constants in this document. The Swift app's product version follows formal version management; this initial implementation does not allocate a new version. Matching shared layer versions does not establish that host features and the native UI port are complete.

## Specification Update Workflow

- `SWIFT_SPEC.ja.md` is the canonical Swift specification.
- Update the Japanese specification first, then synchronize `SWIFT_SPEC.md` as a translation or adaptation that preserves its intent. Do not add English-only requirements.
- Record confirmed implementation changes and remaining scope in dated sections of this specification. Maintain product history in the shared [CHANGELOG.ja.md](../CHANGELOG.ja.md) and [CHANGELOG.md](../CHANGELOG.md). Do not create a separate Swift changelog.
- Update the relevant canonical document when shared semantics or persistence contracts change. This document explains how the Swift host applies them; it does not establish an independent shared specification.
- Public documentation describes source and reproducible procedures. Generated binaries, models, logs, credentials, device identifiers, and private operating records are not tracked product material.

## 2026-10-02 Shared Rust and standalone foundations for macOS

### Platforms and implementation stage

The minimum operating systems are macOS 14 and iOS 17. SDK versions are managed separately from deployment targets. The arm64/x86_64 Universal macOS app will reach full functionality first, followed by iPad and iPhone. The current implementation covers the M1 Swift/Rust connection, M2 standalone host and SQLite persistence boundaries, and initial macOS UI. The full M3 UI remains incomplete.

The Apple client is a local app for one user. It does not inherit Server authentication, administration, or multi-user features. Neither inku Server nor a Python runtime is required at runtime. Camera support belongs to the future iOS client and will not be added to macOS. The iOS app and camera feature are not implemented.

### Packages and responsibilities

| Component | Responsibility |
| --- | --- |
| [InkuCore](Packages/InkuCore/Package.swift) | Owned `Data` APIs into Rust from the same checkout through UniFFI, version reports, shared registries, and compile/step/render/raster boundaries. |
| [InkuHost](Packages/InkuHost/Package.swift) | Provider transport, Keychain, provider settings, execution actors, and effects requested by the core. |
| [InkuPersistence](Packages/InkuPersistence/Package.swift) | GRDB/SQLite storage for works, lineage, executions, ACKs, and snapshots; CAS; manual backup and restore. |
| [InkuUI](Package.swift) | Native views, the app model, OS file panels and clipboard, and the display image cache. |

UniFFI bindings are generated using pinned Cargo dependencies and metadata from the matching Rust archive. Handwritten Swift does not add unsafe FFI. Public boundaries contain Rust input errors and panics. DDL compilation, saved Score rendering, and canvas/color registries use existing shared facades. Large pixel buffers are not converted into JSON or base64 payloads.

Build resources for default settings and color catalogs are generated from Server source. Full resource integration for Macro definitions and plugins remains in M3. Python is a development dependency for that generation and is not embedded in the app. See the [build instructions](README.md), package manifests, and `core/Cargo.lock` for pinned dependencies and generator procedures.

### Executions, providers, and cancellation

[PipelineHost](Packages/InkuHost/Sources/InkuHost/PipelineHost.swift) uses a driver for each execution to serialize core mutations and persistence. Prompts, schemas, retry decisions, documents, and authoring authority retain their core-defined semantics. Swift performs the requested transport and persistence effects. Core snapshots are stored as opaque owned bytes.

Provider adapters support OpenAI-compatible services, the MLX API profile, Anthropic, and Gemini. The current settings view stores one endpoint and one model shared by Stage1 and Stage2. Ordinary settings live in `providers.json` beside the DB; API keys live in separate Keychain items. Saving connection settings does not send an LLM request. Sending requests to real providers and accepting individual models require separate checks.

A pending claim is persisted before a provider request starts, and a response from an obsolete request cannot update state after cancellation. Cancellation reaches the transport task and the shared core's cancel command. The app model waits for stopping to finish before starting another generation. Swift's JSON boundary preserves integer lexemes and does not round UInt64 seeds through `Double`.

Restoring a saved execution is read-only and never automatically repeats an interrupted provider request. The explicit resume API completes durable local effects only; it does not restart provider work. Executions with a pending provider claim refuse resume. User-facing recovery controls for this API are not connected yet.

### Storage, reading, and saved Score replay

Storage semantics follow the [portable persistence contract](../persistence/README.md), [contract.json](../persistence/contract.json), and [logical projection v2](../persistence/reference/logical-projection-v2.sql). Swift has an independent physical schema v1, defined by its [bundled SQL](Packages/InkuPersistence/Sources/InkuPersistence/Resources/schema-v1.sql), [schema export](../persistence/reference/swift-schema-v1.json), and [record mapping](Packages/InkuPersistence/Sources/InkuPersistence/Records.swift). Its physical schema version is not interchangeable with the portable contract or other hosts' schema versions.

`ddl` is the only instruction body used for saving, display, editing, and replay. Optional `ddl_source_origin` records adoption of a legacy body; it is neither a second body nor authoring authority. NULL versus empty strings, unknown states/fallbacks and JSON fields, and original whitespace and line endings are preserved. When `source_text` is NULL, readers can display `input` without changing the stored value. Seeds are decimal TEXT; `at` is Unix epoch milliseconds.

One `InkuDatabase` actor and a GRDB `DatabaseQueue` own the writer. Existing DBs undergo read-only schema validation before a writer opens. Unknown, future, or partial schemas are refused. Only new DBs are created with the current schema, and there is no destructive fallback. Swift does not directly open Server or Android databases, and macOS/iOS do not share a live DB file.

A work, its lineage node, and an optional edge are saved in one transaction. History primary-key collisions are refused; render hashes are not unique. `commitEffect` atomically commits the next snapshot/storage revision, ACK, and optional work/lineage records. A success ACK is returned only after the DB commit. Retrying an identical effect does not duplicate a save; different contents or a stale storage revision cause a conflict. Storage revisions are distinct from document authority revisions.

Selecting or reading a saved work uses its stored DDL, Score, and canonical SVG without compiling or rendering again. Explicit replay validates the saved Score and its attested policies, clip, and options, invokes the shared `renderSaved` boundary, and saves a new work and lineage child. It does not rewrite the source work or invent policies for a work without rendering context. The current UI replays with the saved options.

### Backup and restore

Manual backup uses the SQLite Backup API to capture a consistent snapshot including WAL contents. After schema, integrity, and stored-value validation, a standalone SQLite file is published at a new destination. Existing backups are not overwritten. Copying only the DB file is not treated as a backup.

Restore cannot start from the UI during generation. It stops host executions, keeps the original backup read-only, validates an isolated snapshot, and replaces the active DB through the Backup API. After success, the app model resets execution, selection, and display state and reloads works. DB backups include works, lineage, executions, snapshots, and ACKs; adjacent provider JSON and Keychain credentials are excluded.

Automatic backup generations, FTS, and import of legacy Server/Android databases or legacy JSON are not implemented. The legacy-body selection helper using the fixed Unicode whitespace set does not establish a complete import feature.

### Raster and native display

The [shared raster crate](../core/crates/inku-svg-raster/Cargo.toml) renders SVG and returns owned premultiplied RGBA8 with width, height, stride, and pixel format. Swift mechanically converts this to an sRGB `CGImage` and retains the pixels for the image's lifetime. The display path does not omit filters or medium effects. Raster requests obey shared SVG size, dimension, and pixel limits and do not obtain resources from external networks or filesystems.

The [ArtworkRenderer](Sources/InkuUI/ArtworkRenderer.swift) actor maintains a bounded cache keyed by SVG digest, raster API version, requested dimensions, and color space. Canvas and thumbnails request rasters when needed for display. Current PNG export rasterizes the saved SVG at height 1024; SVG export writes the saved canonical SVG unchanged. This does not implement the full custom-size or animated export specification.

### Initial macOS UI and disconnected features

A `NavigationSplitView` rail provides creation, library, lineage, and settings views. Creation binds description/direct DDL, language, shared catalog/canvas, seed, and wild settings to the app model. The initial input is English direct DDL that can run without a model connection. Generation/cancellation, saved-work selection and replay, read-only DDL/Score, canvas zoom/pan, recent works, library search, provider settings, SVG/PNG export, image copy, and manual backup/restore are connected.

Library and recent works show normal, nontrashed records and disable selection during processing. Search operates on loaded works; it is not whole-DB FTS or a pagination UI. Works with an empty source use the display title "無題" without changing their stored source.

Remaining M3 features include the lineage graph, favorite/trash controls, plugin/model advice dialogs, batch/demo, custom and animated exports, and share cards. The lineage view explicitly reports that it is disconnected. Unimplemented features do not appear as successful actions. The iPad/iPhone app, camera, sharing, device lifecycle handling, and real-device acceptance remain future work.

### Build and verification boundaries

See [README.md](README.md) for clean-clone tools, pinned dependencies, resource generation, generators, artifacts, and execution commands. [build-macos.sh](scripts/build-macos.sh) defaults to release Rust and a Release app; debug can be selected explicitly. It builds the Xcode project generated from [project.yml](project.yml) using a generic Mac destination, both architectures, and `ONLY_ACTIVE_ARCH=NO`. This is an unsigned local build. Signing, notarization, and distribution are separate work. Generated bindings, XCFrameworks, resources, the project, and build outputs are reproducible artifacts.

Bounded checks confirmed Mac arm64/x86_64 Rust artifacts and Swift linking, plus a Universal macOS app build. On Apple Silicon, direct DDL produced Score/SVG, SQLite storage survived app-model recreation, owned rasters displayed natively, and canonical saved SVG export succeeded. Initial native views also displayed the generated work and recent thumbnail, selected library works, and created new history through saved Score replay. UInt64 seed preservation, pixel ownership, input errors, and persistence boundaries are checked through small cases tied to concrete failures.

iOS device/simulator Rust artifacts were generated, but iOS app builds, signing, and real-device acceptance are incomplete. Intel hardware startup/performance, real provider requests, and author acceptance of routine use and full functionality require separate checks. CLI checks, Universal builds, native-view checks, and real-device acceptance do not substitute for one another. Select verification according to the concrete failure a change prevents.

The app's `--database` argument selects a temporary DB for isolated trials. It changes the DB and adjacent provider JSON destination, while Keychain storage remains independent. README contains the concrete commands for normal use and isolated trials.
