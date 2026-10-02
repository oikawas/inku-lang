# Portable persistence contract

This directory defines the logical SQLite persistence boundary shared by the Server, Android, and a possible future iOS adapter. It does not define a database file that every host opens directly.

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

| Logical field | Server physical storage | Android physical storage |
|---|---|---|
| history record | `history` | `history_items` |
| `at` | `at` | `created_at` |
| `input` | `input` | `original_input` |
| `ddl` | `ddl` | `normalized_ddl` |
| `score` | `score` | `score_json` |
| `svg` | `svg` | `display_svg` |
| `render_engine_id` | dedicated column | `render_metadata_json` path |

The mapping is deliberate. Portability requires equal meaning, NULL distinctions, encoding, and constraints at the adapter boundary; it does not require equal physical names.

The Server owns a SQLAlchemy/SQLite schema, Android owns a Room/SQLite schema,
and a possible future iOS client would own another physical adapter. Server-only
authentication and administration tables, and device-only provider, model, and
cache tables, are host extensions rather than portability gaps.

`required_common` means both current hosts persist or deterministically expose the fact. `optional_common` reserves a shared meaning but allows a host without a producer to omit it. Host-only extensions remain outside the logical field list.

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
define the shared Server, Android, and old JSON boundaries. U+001C and U+200B
count as body characters.

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

Constraint coverage is host-specific:

| Logical constraint | Server | Android Room |
|---|---|---|
| history id collision rejected | database | database |
| render hash remains non-unique | database | database |
| history to lineage node is one-to-one | database | database |
| lineage node to history is one-to-one | database | database |
| one primary parent per child | database | database |
| parent cannot equal child | database | database |
| history, node, and edge write atomically | application transaction | application transaction |

The logical reference SQL expresses the target constraints. A host mapping is
current only when every declared constraint is enforced at its adapter boundary.

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
