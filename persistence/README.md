# Portable persistence contract

This directory defines the logical SQLite persistence boundary shared by the Server, Android, and a possible future iOS adapter. It does not define a database file that every host opens directly.

The authority order is:

1. `SPEC.ja.md` for product meaning;
2. `contract.json` for logical persistence fields, encodings, and host mappings;
3. `reference/logical-projection-v1.sql` for executable SQLite constraints;
4. `fixtures/` for small language-neutral examples;
5. each host adapter for its physical schema and lifecycle.

## Logical and physical storage

The logical record names are `history`, `lineage_nodes`, and `lineage_edges`. Physical storage may use different names. For example:

| Logical field | Server physical storage | Android physical storage |
|---|---|---|
| history record | `history` | `history_items` |
| `at` | `at` | `created_at` |
| `input` | `input` | `original_input` |
| `score` | `score` | `score_json` |
| `svg` | `svg` | `display_svg` |
| `render_engine_id` | dedicated column | `render_metadata_json` path |

The mapping is deliberate. Portability requires equal meaning, NULL distinctions, encoding, and constraints at the adapter boundary; it does not require equal physical names.

`required_common` means both current hosts persist or deterministically expose the fact. `optional_common` reserves a shared meaning but allows a host without a producer to omit it. Host-only extensions remain outside the logical field list.

Dedicated Android columns are authoritative for `render_seed`, `composition_seed`, and `render_wild`. Matching values inside `render_metadata_json` are integrity echoes used by render identity, not a second writable persistence authority. Metadata without a dedicated column, such as the rendered color map, is mapped directly from its existing JSON path.

## NULL and identity

- A NULL `source_text` means the row predates separate source recording. Readers may fall back to `input` without rewriting the NULL.
- A NULL `sketch_state` is older than the field and is not the same as `off`.
- A NULL `compose_fallback` is older than fallback recording and is not the same as the recorded value `none`.
- `render_hash` is not unique. Two saves of the same drawing are two works.
- History primary-key collisions are rejected rather than replaced.
- Persistence does not recalculate `rh3`, `dh1`, Score, or canonical SVG.

## Current runtime ownership

The portable contract records these owners without moving them:

- Server `init_db()` creates metadata, runs `_migrate_columns()`, seeds bootstrap/permission rows, assigns unowned history, and backfills history identity/lineage. Later migration stages must turn the unbounded repair work into named one-shot migrations.
- Android `InkuRepository.saveResult()` already wraps the history row, lineage node, and optional edge in one `database.withTransaction` block. Thumbnail generation runs after that canonical transaction.
- Android Room v10 enforces the history/node one-to-one keys and one parent per child with unique indexes. The fresh-schema callback creates separate INSERT and UPDATE triggers that reject self-edges. The intentional one-time reset discards only Room v1–9 databases before creating this v10 schema; v10 and later databases are not a destructive fallback.

Constraint coverage is host-specific:

| Logical constraint | Server | Android Room v10 |
|---|---|---|
| history id collision rejected | database | database |
| render hash remains non-unique | database | database |
| history to lineage node is one-to-one | database | database |
| lineage node to history is one-to-one | database | database |
| one primary parent per child | database | database |
| parent cannot equal child | database | database |
| history, node, and edge write atomically | application transaction | application transaction |

The logical reference SQL expresses the target constraints. A host mapping is current only when every declared constraint is enforced at its adapter boundary. The current Server and Android Room v10 mappings have no declared constraint gaps.

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
