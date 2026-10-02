# inku Swift Implementation Specification

This directory contains the native SwiftUI client, developed for macOS first, and the shared Apple packages. [SWIFT_SPEC.ja.md](SWIFT_SPEC.ja.md) is the canonical specification for Swift host behavior; this document is its maintained English version. The [product specification](../SPEC.md) defines shared DDL, Score, prompts, authoring authority, pipeline transitions, seeds, and rendering semantics. Server remains the primary development host, and Swift follows the same Rust core without duplicating semantic processing.

Last updated: 2026-10-03.

Binding and protocol identities come from the bundled Rust core's version report; rendering layer identities use render metadata and the [Server layer definitions](../server/src/inku_server/layer_versions.py). Do not duplicate shared engine version constants in this document. The Swift app's product version follows formal version management; this initial implementation does not allocate a new version. Matching shared layer versions does not establish that host features and the native UI port are complete.

## Specification Update Workflow

- `SWIFT_SPEC.ja.md` is the canonical Swift specification.
- Update the Japanese specification first, then synchronize `SWIFT_SPEC.md` as a translation or adaptation that preserves its intent. Do not add English-only requirements.
- Record confirmed implementation changes and remaining scope in dated sections of this specification. Maintain product history in the shared [CHANGELOG.ja.md](../CHANGELOG.ja.md) and [CHANGELOG.md](../CHANGELOG.md). Do not create a separate Swift changelog.
- Update the relevant canonical document when shared semantics or persistence contracts change. This document explains how the Swift host applies them; it does not establish an independent shared specification.
- Public documentation describes source and reproducible procedures. Generated binaries, models, logs, credentials, device identifiers, and private operating records are not tracked product material.

## 2026-10-03 macOS creation, whole-database history, and surrounding features

### Creation and saved-work display

The left column contains description/direct DDL, upcoming generation conditions, and the saved sketch/DDL inspector. Displayed-work facts and work/lineage occupy the right. Input, upcoming conditions, and saved information use grouped panels; Generate/Stop remain outside the input scroll area. Narrow widths switch to a vertical arrangement. A compact summary and detail popover distinguish saved model, catalog, canvas, and size from upcoming settings. Captions, vertical/horizontal writing, placement, pan/zoom, and presentation are native display composition and do not alter saved SVG. Fit canvas resets zoom and position.

Creation offers registered services and drawing models. It includes configured models and explicitly discovered catalogs; only a user button starts discovery. The next model is passed to both interpretation and structure stages without changing saved Settings defaults or the parent work's models. Fresh generation, refinement, and initial comparison choices use it; running batch/demo models remain pinned to their starting snapshots. An unconfigured connection leads to Model settings.

macOS menus use the active scene's available actions. Command-N creates a new work, Command-O shares the screen button's DDL import, Command-comma opens Settings, Command-1 through 4 navigate creation/library/lineage/batch-demo, Shift-Command-E exports, and Shift-Command-C copies the image. Existing Command-Return generation, Escape stop, and Shift-Command-F presentation remain available. Generation, automation, import, dialogs, and presentation disable affected actions so menus cannot interrupt them with another write. Settings uses a system sidebar and grouped forms; model setup links open the appropriate category.

Server-derived resources include the saijiki, 13 color catalogs, 11 canvas formats, and seven Macro/plugin words. Shared Rust resolves definitions and digest locks. Plugin preferences affect new works; saved definitions remain pinned. `inku.ddl-export.v1` imports validate text, definitions, locks, and exact integer representation before attaching the package to a new work. Inputs beyond 4 MiB/64 definitions or with incomplete definitions are refused without adopting partial results.

The native color chooser displays catalog IDs, localized descriptions, ordered swatches, HEX values, and Japanese/English color names. Fixed, random, and description-based selection are drafts until Done applies them to upcoming conditions. Cancel/close preserve those conditions. Direct DDL does not use description-based selection; switching input to DDL normalizes an existing auto choice to fixed.

macOS accepts one DDL file dropped onto the window through the same URL reader and validation as the standard panel. Reading disables generation and batch starts; cancellation, scene disappearance, and changed draft context exclude late results. Success reveals Creation. Imported-definition notices belong to the current draft, and New or opening a saved work clears stale completion messages.

Draft inspection is read-only. Committed changes pass through core revision/authority rules, create a new work and lineage child, and never restore description authority after the first committed DDL mutation. Hole proposals remain separate from approval/decline. `ddl_source_origin` remains null or `legacy_expanded`, never an authoring-authority field.

Ordinary Replay opens the same read-only comparison as Server. It compares the pinned work's stored SVG with current shared-Rust output from its saved Score and conditions, without changing history, lineage, displayed work, or its original execution. It reports recorded/current render-engine versions, differences, and missing records. Saved touch words use the shared Rust seed first, otherwise the saved seed, otherwise provisional zero with a notice. An absent composition seed stays absent for core fallback. Creation, library, lineage, and work menus share this comparison; lineage dismisses its saved-information sheet before presenting it. Stop/close drain owned work and exclude late results. Replay with next conditions remains a separate operation that saves a new child.

Change description and redraw with/without sketch open the same dialog from the creation toolbar or library/lineage cards. The explicit parent remains pinned; its saved configuration, canvas, seeds, budgets, definitions, and locks reach shared core for a new child. The next drawing model is captured for both stages at startup. Changed words do not reuse the parent's old sketch prose, and explicitly enabling sketch regenerates it. Saved-context authority prevents direct or committed edited DDL from returning to description authority. Cancellation waits for the owned operation to finish; only a committed child closes the dialog and reveals Creation.

Edit-child edges retain Server's `edited_from_history_id`; sketch operations also retain `from_sketch_state` and `to_sketch_mode`. Added GenerationRequest fields are optional so existing pinned requests remain decodable.

Description/sketch dialogs keep the title and action footer fixed while placing the parent image and source text in the input's scrolling area. The parent image is 120 points square, and source text uses up to four lines and a tooltip. Reopening the dialog does not let input compress this parent card.

### History, library, and lineage

History uses whole-database 20-item pages; library has independent 30-item pages. The app's latest-100 list is not the population for search or navigation. Latest/newer/older/oldest navigation, full-description/full-hash/final-four search, AND-combined star/refinement/export filters, and independent thumbnail/list and chronological/lineage grouping are available.

Comments, marks, trash/restore, explicit permanent deletion, multiple selection, and lineage graph/path use SQLite. Permanent deletion removes work content while retaining node identity, root, time, and parent relationships as tombstones. Server ACL and user/group administration are excluded.

History generations follow Server: roots are generation one and each primary-parent edge adds one, including deleted ancestors. Works without a node are standalone. New preferences show generation and model; existing field choices remain intact. Variation kind or amplitude does not substitute for generation. Library distinguishes the displayed work from multiple-selection checkboxes; lineage distinguishes the displayed work from its scope-setting focus. A DDL-only work uses the first saved DDL line as its display title without filling in saved source text. Cards and menus expose hashes, comments, marks, and parent/child navigation.

Swift physical schema v2 adds annotations, colophons, and unread words to v1's six tables, for nine tables. Its sources are the [bundled migration](Packages/InkuPersistence/Sources/InkuPersistence/Resources/migration-v2.sql) and [schema export](../persistence/reference/swift-schema-v2.json). Only a known complete v1 migrates atomically, preserving works/snapshots/ACKs. Unknown schemas still fail closed. Backup/restore includes all nine tables; v1 backups migrate in an isolated snapshot before restoration. Server/Android DB and legacy JSON import are not included.

### Comparison, refinement, colophons, and automation

Edit drawing parameters pins an explicit saved parent and offers composition, reading, variation, or word-based touch. All conditions for one/four options are frozen before preparation. Private options remain outside normal history/lineage; enlargement stays inside the dialog and never replaces the displayed work. Only selected options commit atomically and idempotently as children; remaining options are discarded. Interrupted saving retains committed markers and retries do not duplicate saves. Stop/close drain owned tasks and late responses. Subsequent DDL edits, including after reopening an adopted work, create another saved child.

Composition retains the parent's DDL, definitions/locks, colors and touch while shared core uses new composition seeds. The dialog's model choice applies only to structuring and preserves the parent's reading model. Reading captures Creation's next model for both stages and generates new DDL from the original description and saved sketch prose; committed DDL authority refuses rereading. Local dialog model choices do not change saved defaults.

Word-based touch allows one option, preserves saved Score/DDL/colors/composition/Wild/model facts, and rerenders without provider calls. Shared Rust uses the existing Server's Python `str.strip()` whitespace and the first eight SHA-256 bytes of unchanged UTF-8 as an unsigned big-endian UInt64. It performs no Unicode normalization; Swift/Python do not duplicate trimming/hashing. Boundaries carry exact decimal seed strings, and edge provenance preserves integer values for old/new seeds and the words. Shared core refuses empty words.

Current shared Stage1.5 variation is a no-op: saved Score, colors, composition, touch, element count, and parent models remain unchanged in provider-free replay. The UI states “Variation (nothing moves now)” and “Moved: nothing”; amplitude and allocated seed are retained as provenance. An explicit Wild override is identified as a changed rendering condition.

Catalog/model comparison pins its source work, Score, and settings. Candidates enter normal history/lineage only through explicit, idempotent selection. Total candidates are not capped at four; Swift generates them sequentially. Stop and dialog close await completion and exclude late results.

Model advice, random/Vision refinement, and colophons share the normal provider transport and rate budget. Adopting editable advice and generating a new variation are separate; DDL-authoritative works do not receive description overwrites. Intermediate refinements use `lineage_only`. Each autonomous child edge records Web's `autonomous_refine_mode`; Vision also records that generation's `vision_model`, `vision_observation`, and `vision_next_direction`. Random provenance never includes stale displayed Vision advice. Colophons retain original and adopted text separately and are included in DB backups.

Batch accepts at most 1,000 nonblank inputs and pins original line numbers, models, providers, definitions, seeds, and settings at start. Only failed rows retry after a full pass, default zero and maximum five retries. Explicit resume preserves pinned settings. Crash-ambiguous rows require an explicit retry/skip decision and never resend automatically. Demo pins starting settings, displays generated descriptions/works, defaults to no history saves, uses intervals of 1–3,600 seconds and duration of 60–86,400 seconds, and stops on cancellation or expiry.

### Dictionaries and local settings

Japanese counting uses the Server's Sudachi small dictionary and English counting uses the same CMUdict pronunciation data through a thin Rust boundary. The [resource manifest](scripts/description-meter-resources.json) pins dictionaries, configuration, licenses, and hashes for build-time generation; the app has no Python runtime. Up to 4,000 characters are assessed with a 300 ms debounce. SQLite retains unread-word counts, dates, and contexts. Disabling assessment shows character/line counts.

Local preferences cover Japanese/English, theme, five text scales, full/simple/custom UI, captions, up to three history fields, tooltips, mascots, clipboard, rendering limits, and export templates/destinations. Multiple API services share the drawing model across pipeline stages and support explicit model discovery plus RPM/input TPM/RPD. Ordinary settings are adjacent JSON and API keys are in Keychain. Saving settings alone does not generate a work.

Automatic backup defaults off, runs only while the app is open, and waits for generation/restore/automation. A successful verified backup is recorded before rotating only app-owned generations; manual backups are excluded. Optional result logs record actual committed works, not merely opened old works.

### Personal ChatGPT

Personal ChatGPT is separate from API key connections and disabled by default. The user explicitly enables it, connects and selects an offered drawing model. Stage1 and Stage2 share that model. Several saved personal connections still use one local work library; they do not add multi-user behavior.

Sign-in uses a temporary listener on 127.0.0.1 with `/auth/callback`, state/nonce/PKCE, an issued client ID, verified identity and granted scopes. Credentials occupy an atomically committed AES-GCM vault capped at 1MiB, with a device-local 32-byte key in Keychain. There is no plaintext token fallback, and SQLite backups exclude credentials. The initial disabled state starts neither authentication nor inference.

Requests pin profile ID and generation at startup and never switch connections while queued or resuming batch/demo work. Disconnects, connection changes and quota failures invalidate old refreshes and late responses without implicit fallback to another provider. Responses/SSE carries only the shared Rust description, sketch, automatic-color and DDL-hole effects. Vision refinement, colophons, demo-description generation and model inspection explicitly remain unsupported for this connection. Actual sign-in, model discovery and inference acceptance are separate from offline checks.

### Export and native raster

[InkuExport](Packages/InkuExport/Package.swift) provides Display/Editable/Compat/Live SVG, PNG, DDL with definitions, share cards, review/AI contact sheets, and APNG/GIF. Display uses canonical saved SVG; other SVG profiles pass saved Score/context to the shared core. PNG retains canvas ratio at heights 1080/2160/4320 or custom 64–12000 pixels. Region raster tiles use the original scene without dropping filters or clips. Limits are 144,000,000 pixels for static images and 600,000,000 aggregate animation pixels. Cancelled output is not published.

Single-work animation supports layer progression and restart/reverse/once; multiple works support cut/crossfade/fade_white/slide. Chronological order and explicit lineage-path order remain distinct. The Server's Noto Serif JP and license are bundled. Destination bookmarks and PNG templates persist; multiple outputs use a new folder, with Finder and OS sharing actions.

The active screen determines export candidates: creation uses the displayed saved work, library uses checked works or the displayed work when none are checked, and lineage uses the path to its focus. An immutable snapshot prevents another screen's checkboxes from changing creation or lineage candidates. Unsaved previews are excluded from saved-work export. The export dialog shares the library's DDL display titles.

An immutable prepared scene reuses SVG parsing across resolutions and export tiles. Native caches have estimated scene-cost limits of 16 MiB/eight entries and image limits of 64 MiB/256 entries without modifying saved SVG or material effects. Display follows Retina scale, a 120 ms resize debounce, and an 8-megapixel requested-size budget. Focused Release measurements for 6,000 paths at four resolutions improved about 20% including preparation; heavy pencil filters improved little. The same gain is not promised for every work or operation.

### Verification boundaries

Focused real-core/temporary-DB checks passed for authoring, explicit comparison saves/cancellation, pinned batch resume/ambiguous rows, saved-plugin definitions, and prepared scene/image caches. Dictionary, library, SQLite migration/backup, export and tiling checks address concrete failures. Personal identity, SSE, loopback, refresh cancellation, quota and model resolution were checked with synthetic signatures and mock transport, not actual personal sign-in.

The updated unsigned Universal app linked both architectures and retained minimum macOS 14. On Apple Silicon/macOS27.0.1, isolated native checks confirmed DDL generation, an edited child, library comments/stars, Trash/restore, persistence after restart, Japanese/English switching, parent/child lineage and overview, correct String revisions, and PNG2160 export of two checkbox-selected works. Both files are 2160×2160 and the texture was visually inspected. Startup page-size recursion, empty sheet selection and an invalid Foundation write-option combination were fixed. Author acceptance, other native export recipes/performance, real providers/OAuth, physical Intel/macOS14, signing/distribution and iOS app/camera remain incomplete.

A further selected check confirmed the creation choice in both actual request stages, unchanged saved defaults and captured templates, and zero provider calls. One SQLite generation projection check covered a root, child, missing node, and deleted ancestor. Native checks at 1320×880 and a standard 1281×733 tile confirmed the fixed Generate button, canvas/history, generations one/two, Settings/navigation/New/import cancellation, model-category routing, separate lineage focus/display, and two library versus one creation export candidates. This representative check does not accept every narrow layout, VoiceOver, or the author's design approval.

A selected mock/shared-core saved-work edit check confirmed a reopened parent without a live execution, pinned saved conditions/plugin locks and next models, fresh sketch generation, DDL authority after saving a child, and rejection of late responses after stopping. Native checks confirmed description/sketch draft cancellation, catalog cancellation and applying next settings, Japanese/English color names and HEX values, and one DDL import through the standard panel. After moving the parent card into scrolling content, description/cancel/sketch/cancel/description showed the image, source, and original draft; all history/lineage rows stayed unchanged. Finder drop was retried from a fresh control connection, DB, and file selection, but encountered a tool window-position error or unchanged input after dragging. Successful import remains unverified; the source/tool cause is unresolved, and panel acceptance does not accept this gesture. Real-provider editing remains unaccepted.

The selected mock/shared-core drawing-element check confirmed an exact word seed above 2^53, zero-seed composition fallback, saved Score/colors/DDL with no provider calls, frozen four-option plans, current variation identity, reading models, unchanged normal history before adoption, idempotent adoption/reopened DDL children, optional edit metadata/legacy Codable, and drained late responses. A named Rust seed check and direct new-PyO3-to-Server-helper check also passed. With an isolated DB, the Debug Universal app confirmed one touch option's exact seed and discard, saving only two selected options from four compositions (normal history increased from two to four), a 640-pixel comparison sheet, automatic scrolling to options, variation's “Moved: none,” and no lingering preparation status after closing. Real providers, every width, VoiceOver, and author acceptance remain separate.

The new `--replay-comparison-only` check uses real Rust, temporary SQLite, and zero provider calls for stored/current SVGs and versions, seed precedence/provisional zero, absent composition, unchanged history/lineage/display/execution, and stale parent/token or stopped response rejection. `--auxiliary-provenance-only` uses real Rust and mock transport for two generations of Vision provenance, exclusion of stale advice from random mode, parent/intermediate work, fixed conditions, and call budgets. In the Release Universal native app, Creation and lineage saved information opened comparison; both images and versions were inspected by scrolling the narrow sheet. After closing, every row of two history works, two nodes, one edge, and two executions remained equal.

The Rust 1.95 macOS host proc-macro LINKEDIT alignment failure was avoided by setting only release host build dependencies to `strip="none"`. Target archive optimization and stripping remain in place. Current Mac core and unsigned Release Universal app builds succeeded for both architectures with minimum macOS 14. This does not accept physical Intel/macOS14, current iOS artifacts, or Release performance. Per-retry elapsed time/actual model/token presentation and model suitability/purpose guidance remain Server parity gaps.

## 2026-10-02 Shared Rust and standalone foundations for macOS (historical)

The following records the initial implementation. The dated section above defines the currently connected features.

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
