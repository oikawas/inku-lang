# inku architecture

This documentation maps the DDL design stages to the current implementation and to the boundaries among Web, Server, CLI, Android, external providers, and persistence. The baseline is public commit `88506e0e10ffa38fdeeac3f74dfe1c5f07b3e37c`, app `v2.13.47 / Build 946`.

## Reading order

1. `evidence-inventory.md` — Evidence IDs and primary sources
2. `system-context.md` — System boundary
3. `runtime-containers.md` — Runtime units
4. `ddl-processing-pipeline.md` — DDL processing
5. `description-to-svg.md` — From a description to an SVG, decision by decision (the pipeline deep dive)
6. `server-components.md` — Server internals
7. `client-boundaries.md` — Web, CLI, and Android
8. `data-history-lineage.md` — DB, identity, and lineage
9. `operations-security.md` — Operations and security boundaries
10. `change-impact-map.md` — Change propagation
11. `known-differences.md` — Differences and unknowns
12. `future-plan.md` — The generation-architecture improvement plan (as far as it is ruled)

Japanese counterparts use the same names with `.ja.md`.

## Reading the diagrams

- A solid edge is a call, data movement, or output confirmed in the implementation.
- A dashed edge is specification-only or not measured, and its label says so.
- Mermaid node IDs are stable ASCII. The evidence table after each diagram maps major nodes and boundaries to `evidence-inventory.md`.
- The DB is canonical. Automatic work files are optional derivatives.
- “The same Score” does not include a seed. Reproducibility requires the same JSON Score and render seed.

## Evidence notation

`Confirmed` means implementation evidence exists. `Specification` means specification only. `Inferred` means a stated static inference. `Unknown` means this review did not confirm the point. A difference between specification and implementation is preserved in `known-differences.md` rather than silently reconciled.

## Maintenance

1. Record the public branch, commit, and work-tree status.
2. Read `PROJECT_CONTEXT.ja.md`, then only the relevant sections of `SPEC.ja.md`.
3. Verify current entry points, routers, schemas, imports, tests, and manifests.
4. Update the snapshot and IDs in `evidence-inventory.md` first.
5. Update both language editions and move differences to `known-differences.md`.
6. Check Mermaid fences, cited paths, terminology, accidental disclosure, and the scoped Git difference.

Japanese design decisions are authoritative. English follows the correspondence table in `docs/i18n/glossary.md` and the rules in `web/src/lib/i18n/GLOSSARY.md`.
