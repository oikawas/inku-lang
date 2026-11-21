# Work pack v1

The shared core exports `workpack_read_line`, `workpack_plan`, and `workpack_encode_line` for line validation, import selection and lineage roots, and canonical JSON lines. The core enforces the 64 MiB limit per line. The host enforces the 256 MiB file limit, splits and stages lines, and owns database reads, writes and transactions.

An `.inkupack` file is UTF-8 JSON Lines separated by LF. The first line contains `format: "inku.workpack"`, `format_version: 1`, `persistence_contract_version: 2`, `exported_at` (Unix milliseconds), `producer` (host, app_version, build, schema_version), and `counts`. Following lines carry `kind` in this order: history, lineage_node, lineage_edge, annotation, colophon. Counts give the number of each kind; a mismatch indicates an incomplete file. Ignore unknown fields and kinds in the same format version; reject a newer format version.

The Server producer uses host `server` and its `MIGRATION_VERSION` as schema_version.

The history, lineage_node and lineage_edge fields are the logical names classified `required_common` or `optional_common` in the corresponding records in [contract.json](contract.json). Required fields include explicit nulls. Do not carry host_only fields. Preserve stored SVG, JSON strings and hashes unchanged.

## Encoding and JSON types

| encoding | JSON type |
| --- | --- |
| text, utf8_text, utf8_svg | string |
| unix_epoch_milliseconds, integer_milliseconds | integer |
| unsigned_decimal_text | decimal string |
| canonical_json_object | string containing a JSON object |
| boolean_0_1 | integer 0 or 1 |
| finite_number | finite number |
| null_or_legacy_expanded | null or the string `legacy_expanded` |
| rh3_or_legacy_text, dh1_or_legacy_text | string |

Add new encodings to this table before using them. Nullable fields may also contain null. Convert Server's text 0/1 to integers.

An annotation contains `history_id`, `note` (null or a string of at most 240 characters with surrounding whitespace removed), and `for_revision` (0/1). Do not carry the former `for_share`. A colophon contains `id`, `target_node_id`, `branch_snapshot` (JSON string), `model`, `at`, `language` (ja/en), `body`, `warnings_json`, and `fact_sheet_json`. Swift may add optional `generated_body`, `adopted_body`, and `signature`; body is the adopted text if present, otherwise the generated text. Hosts unable to read annotations or colophons may skip them.

Skip works whose work or node ID already exists, preserving existing marks and notes. Do not insert nodes without works. Insert edges only when both ends exist and the child has no parent, and recompute roots in the destination. Validate all lines before importing in a single transaction. The provisional limits are 256 MiB per file and 64 MiB per line. Exports omit trashed works; imports preserve `trashed`. Connection details, settings, execution records and thumbnails are excluded.

The common fixture is [workpack-minimal.inkupack](fixtures/workpack-minimal.inkupack).
