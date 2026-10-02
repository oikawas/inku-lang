# Portable persistence contract

This directory defines the logical SQLite persistence boundary shared by the Server, Android, and the Apple client's Swift adapter. Each host owns its database file. The shared Swift package targets macOS 14 and iOS 17 and is used by the current macOS app; the iOS app itself is not implemented yet.

The authority order is:

1. `SPEC.ja.md` for product meaning;
2. `contract.json` for logical persistence fields, encodings, and host mappings;
3. `reference/logical-projection-v2.sql` for executable SQLite constraints;
4. `fixtures/` for small language-neutral examples;
5. each host adapter for its physical schema and lifecycle.

The v1 reference SQL remains the historical definition for old input.
`fixtures/history-minimal.json` is current v2;
`fixtures/history-legacy-v1.json` is old two-text JSON input, not current output.

## Logical and physical storage

The logical record names are `history`, `lineage_nodes`, and `lineage_edges`. Physical storage may use different names. For example:

| Logical field | Server physical storage | Android physical storage | Swift physical storage |
|---|---|---|---|
| history record | `history` | `history_items` | `history` |
| `at` | `at` | `created_at` | `at` |
| `input` | `input` | `original_input` | `input` |
| `ddl` | `ddl` | `normalized_ddl` | `ddl` |
| `ddl_source_origin` | `ddl_source_origin` | `ddl_source_origin` | `ddl_source_origin` |
| `score` | `score` | `score_json` | `score` |
| `svg` | `svg` | `display_svg` | `svg` |
| `render_engine_id` | dedicated column | `render_metadata_json` path | dedicated column |

The mapping is deliberate. Portability requires equal meaning, NULL distinctions, encoding, and constraints at the adapter boundary; it does not require equal physical names.

Android's current physical authority is the generated [Room schema 14](../android/app/schemas/app.inku.mobile.data.db.InkuDatabase/14.json). Both `history_items.normalized_ddl` and `ddl_source_origin` are nullable TEXT, and the retired `expanded_ddl` column is absent. The portable checker verifies the current Server, Android, and Swift schemas against contract v2.

Swift's implementation is [InkuPersistence](../apple/Packages/InkuPersistence/Package.swift), with GRDB 7.11.1 pinned in the [SwiftPM resolution](../apple/Packages/InkuPersistence/Package.resolved). The [physical schema v1 SQL](../apple/Packages/InkuPersistence/Sources/InkuPersistence/Resources/schema-v1.sql), [v2 migration](../apple/Packages/InkuPersistence/Sources/InkuPersistence/Resources/migration-v2.sql), and [current schema export](reference/swift-schema-v2.json) define the current nine-table schema v2, including annotations, colophons and unread words. Its version is independent of Room 14 and Server registry v4. [SavedWork, LineageNode, and LineageEdge](../apple/Packages/InkuPersistence/Sources/InkuPersistence/Records.swift) map to tables and columns with the logical names and preserve all common fields, including optional common fields. Each Apple host keeps its database in local Application Support. Server and Android databases are not opened directly as Swift databases, and macOS and iOS do not share a live database file.

The Server owns a SQLAlchemy/SQLite schema, Android owns a Room/SQLite schema, and Swift owns a GRDB/SQLite schema. Server-only authentication and administration tables, and device-only provider, model, and cache storage, are host extensions rather than portability gaps.

`required_common` means every declared host persists or deterministically exposes the fact. `optional_common` reserves a shared meaning but allows a host without a producer to omit it. Host-only extensions remain outside the logical field list.

Dedicated Android columns are authoritative for `render_seed`, `composition_seed`, and `render_wild`. Matching values inside `render_metadata_json` are integrity echoes used by render identity, not a second writable persistence authority. Metadata without a dedicated column, such as the rendered color map, is mapped directly from its existing JSON path.

## DDL in contract v2

Contract v2 saves one instruction text, `ddl`, for display, editing, and redraw.
At old JSON input boundaries and explicit database migration, a nonempty `ddl`
wins. Only when it has no body is a nonempty old `expanded_ddl` transferred.
When neither has a body, the original `ddl` null or blank is retained. Selection
does not trim, normalize Unicode, convert newlines, compile, or redraw.

An absent body contains only the fixed Unicode White_Space set U+0009–000D,
0020, 0085, 00A0, 1680, 2000–200A, 2028, 2029, 202F, 205F, and 3000, or is
NULL. The code point list in `contract.json` and `fixtures/ddl-selection.json`
define the shared Server, Android, Swift, and old JSON boundaries. Swift's
`DDLSource` uses this fixed set as well. U+001C and U+200B count as body characters.

The optional common `ddl_source_origin` is NULL or `legacy_expanded`, recording
only a transfer from the retired text. It is neither a second text nor authoring
authority; NULL implies no author or stage. Export/import preserves the origin,
and old works remain `legacy_unknown`. Historical parent/child input DDL
comparisons treat `legacy_expanded` as unknown input. Ordinary fork/replay uses
the unified `ddl`; a new work saves its current pipeline document and authority.

## NULL and identity

- A NULL `source_text` means the row predates separate source recording. Readers may fall back to `input` without rewriting the NULL.
- A NULL `sketch_state` is older than the field and is not the same as `off`.
- A NULL `compose_fallback` is older than fallback recording and is not the same as the recorded value `none`.
- `at` is an INTEGER in Unix epoch milliseconds. `render_seed`, `composition_seed`, and `variation_seed` retain their unsigned decimal TEXT exactly; persistence does not convert them to signed INTEGER or JSON Double values.
- The Swift adapter preserves unknown state and fallback strings, unknown fields inside stored JSON documents, and the whitespace and newlines of stored strings without guessing or normalization.
- `render_hash` is not unique. Two saves of the same drawing are two works.
- History primary-key collisions are rejected rather than replaced.
- Persistence does not recalculate `rh3`, `dh1`, Score, or canonical SVG.

## Current runtime ownership

The portable contract records these owners without moving them:

- Server `db.init_db()` is the composition façade. `MigrationBaselineCallbacks`
  owns fresh-schema creation. Old two-text databases require explicit manual
  DDL migration and are refused by ordinary startup. A migrated database is
  checked for registry/checksums, required columns, absence of retired columns,
  and FTS. Frozen old schemas/adapters serve isolated backup restoration;
  current metadata is not a substitute for an old schema.
- Android `InkuRepository.saveResult()` already wraps the history row, lineage node, and optional edge in one `database.withTransaction` block. Thumbnail generation runs after that canonical transaction.
- Android Room enforces the history/node one-to-one keys and one parent per child with unique indexes. The fresh-schema callback creates separate INSERT and UPDATE triggers that reject self-edges. The intentional one-time reset discards only Room v1–9 databases; v10 and later databases follow non-destructive migrations.
- Swift [InkuDatabase.save and commitEffect](../apple/Packages/InkuPersistence/Sources/InkuPersistence/InkuDatabase.swift) save history, its lineage node, and an optional edge in one transaction. One `InkuDatabase` actor owns the GRDB `DatabaseQueue` writer. Fresh databases use physical schema v2. Before opening a writer for an existing database, read-only inspection checks `user_version`, schema objects and migration records. Only an exact known v1 schema migrates atomically to v2, preserving stored values, snapshots and ACKs. Unknown, future, and partial schemas fail closed; there is no version guessing or destructive fallback.

Constraint coverage is host-specific:

| Logical constraint | Server | Android Room | Swift GRDB |
|---|---|---|---|
| history id collision rejected | database | database | database |
| render hash remains non-unique | database | database | database |
| history to lineage node is one-to-one | database | database | database |
| lineage node to history is one-to-one | database | database | database |
| one primary parent per child | database | database | database |
| parent cannot equal child | database | database | database |
| history, node, and edge write atomically | application transaction | application transaction | application transaction |

The logical reference SQL expresses the target constraints. A host mapping is
current only when every declared constraint is enforced at its adapter boundary.

The document and authoring authority used by Swift's [PipelineHost](../apple/Packages/InkuHost/Sources/InkuHost/PipelineHost.swift) remain in the opaque execution snapshot. `ddl_source_origin` does not supply missing authority, and the authority revision is distinct from the SQLite persistence revision. `compareAndSwapExecution` requires the expected persistence revision. `commitEffect` commits the next snapshot and revision, ACK, and optional history/node/edge together and returns a successful ACK only after the database commit. An identical retry with the same effect ID, snapshot, ACK, and save payload returns the original result without another save. Different contents for the same ID, or a stale persistence revision for a new write, cause a conflict. Reading execution state alone never automatically resends an interrupted provider request.

Swift manual backup uses SQLite Backup API to capture a consistent snapshot including WAL contents. After schema, integrity, and stored-value validation, it publishes a new standalone SQLite file without required sidecars. Existing backups are not overwritten. Restore requires the host pipeline to be stopped, preserves the original backup read-only, validates an isolated snapshot, and replaces the active database through Backup API. Copying only the active database's main file is not a backup.

SQLite backup covers all nine tables, including works, lineage, execution snapshots, ACKs, annotations, colophons and unread words. A v1 backup migrates in an isolated snapshot before restoration. The adjacent `providers.json` is saved separately by [ProviderSettingsStore](../apple/Packages/InkuHost/Sources/InkuHost/ProviderSettings.swift), API keys are Keychain items, and Personal ChatGPT credentials occupy a separate encrypted vault; these files and credentials are outside SQLite backup and restore. Automatic backup retains generations only after snapshot validation succeeds, and search queries the whole database with SQL. A dedicated FTS index and import of old Server/Android physical databases remain unsupported. The obsolete history.json array is not a current Web restoration format and is distinct from the `DDLSource` legacy-text selector and DDL/plugin package import.

## Manual Server migration

A fresh database has registry v4 `single_history_ddl`; migration from v3 retains
the v3 row and appends v4. `server/scripts/migrate_history_ddl.py` starts no API
and operates only on the explicitly selected, canonical existing database.
SQLite 3.35 or newer with `DROP COLUMN` is required. Known source fingerprints
and registry/checksums are checked; unknown and partial states are refused.

From `server/`, inspect read-only first. Supply the selected product commit's
full 40-character SHA.

```sh
uv run python scripts/migrate_history_ddl.py \
  --database /absolute/path/inku.db --source-commit '<exact-product-sha>' --dry-run
```

Before a production apply, lock writes, finish in-flight saves, and stop the API.
Supply the verified fingerprint and a new private report path.

```sh
uv run python scripts/migrate_history_ddl.py \
  --database /absolute/path/inku.db --source-commit '<exact-product-sha>' \
  --expect-fingerprint '<verified-source-fingerprint>' \
  --report /absolute/private/path/migration-report.json --apply
```

SQLite Backup API creates a WAL-safe copy retained owner-only in the database's
adjacent `migration-backups/`. After the writer lock, schema, registry, and all
persistent values must match that copy; a mismatch is refused before changes.
Text selection, origin-column addition, retired-column removal, all protected
value and rowid/link/FTS/integrity checks, and registry update share one
transaction. The report records prepared, committing, successful, or rolled-back
state. A second apply to a migrated database exits without changes.

For an accepted v1/v2 or pre-registry backup, supply the original as `--database`,
a new canonical destination as `--restore-copy`, and `--apply`. The frozen old
schema/coordinator restores a new v3 copy, whose verified postimage is then
unified. The original remains unchanged. Registered older databases also require
a known physical schema; an unknown shape is never guessed to be an old release.
Restoration and DDL unification are separate phases, both identified in the report.

Copies, backups, and failed reports are retained. An uncertain result is never
automatically resent or restarted. Confirm rollback before recovery from a
pre-commit failure. For a post-commit rollback, preserve the new database and
restore the pre-migration backup and old code together. Verify registry, physical
schema, and successful report agree before starting the new release.

## Legacy Server schema fingerprint

`sha256-canonical-sqlite-master-v1` fingerprints schema objects, never row data:

1. read `table`, `index`, `trigger`, and `view` objects from `sqlite_master`;
2. exclude SQLite-internal names and derived `history_fts*` objects;
3. collapse SQL whitespace without rewriting identifiers or literals;
4. sort by object type, name, and owning table;
5. hash canonical UTF-8 JSON with SHA-256.

The FTS objects are excluded because they are derived search acceleration and can vary with SQLite's available FTS build. Their presence is checked separately during migration. A migration may accept only explicitly named schema fingerprints; absence of a migration registry alone is not a supported-version test.

Production fingerprint execution belongs to private migration evidence. Public files must not contain host paths, row contents, credentials, or deployment topology.

## Verification

From `server/`:

```sh
uv run python scripts/check_portable_persistence_contract.py
uv run pytest tests/test_portable_persistence_contract.py -q
```

The verifier reads source and exported schema files only. It never opens the developer or production database.
It refuses a declared host mapping that disagrees with the actual schema.

For the Swift mapping alone, use `uv run python scripts/check_portable_persistence_contract.py --swift-only`. The checker creates a temporary in-memory database from the bundled SQL and checks its schema export, Codable mapping, fixed DDL whitespace set, and constraints. Swift's focused [PersistenceBoundaryTests](../apple/Packages/InkuPersistence/Tests/InkuPersistenceTests/PersistenceBoundaryTests.swift) cover DDL/NULL preservation, collision and lineage rollback, ACK/CAS, WAL backup/restore, and unknown-schema rejection using temporary databases. Select only the checks needed for the concrete failure a change prevents.
