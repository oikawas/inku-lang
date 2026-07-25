# Manual Revision History

This file records revisions to user and operations documents under `manual/`. See `SPEC.ja.md` for the detailed product change history.

## 2026-07-22 — Stated the Bootstrap Administrator Premise

- Documented in Server Configuration 2.2 and Application Installation 7 that inku has no self-service registration, that starting an empty DB without a bootstrap administrator leaves no way to sign in, and that setting the password and restarting recovers it.
- Documented that a blank `INKU_BOOTSTRAP_ADMIN_PASSWORD` counts as unset, so blanking the line and deleting it are equivalent after initial creation.
- Noted in Application Installation 16 Container Deployment that Compose refuses to start without a value.
- Added the same note to the bootstrap administrator section of the environment variable template.

## 2026-07-15 — Unreleased v1.85 Baseline (Web Build 564)

- Added inku-cli api for permission-aware access to every public API and documented every CLI command.
- Added Compose deployment for a non-root API, production Node Web service, and persistent data volume while retaining the existing development setup.
- Documented request-body limits, login rate limiting, CORS, renderer concurrency, and Idempotency-Key.
- Clarified trash confirmation, lineage tombstones, retry deduplication, and user scope.
- Reflected English Title Case consistency and the iPad-width layout baseline.

## 2026-07-15 — Unreleased v1.82 Baseline (Web Build 563)

Full revision.

- Aligned Creating Images with the current Web UI, including automatic instruction-language detection, color/model/canvas controls, and normalized-DDL editing.
- Added Refine Adjust, Model comparison, Language comparison, and deterministic word-based touch variation.
- Added Provenance Details, Prompts, and JSON, including per-stage languages, seeds, hashes, and derivation metadata.
- Added work lineage, intermediate works, promotion to regular history, Nearby works, and Timeline/By lineage History Manager modes.
- Rewrote Application Installation around lockfiles, pre-migration backup, reference systemd deployment, acceptance checks, and rollback.
- Rewrote Server Configuration around configuration boundaries, current environment variables, DB migration, four identities, authentication scope, language resolution, Renderer replay, backup, monitoring, and security.
- Aligned the environment, systemd, and logrotate templates with the current reference deployment and permission policy.
- Kept Japanese and English manuals on the same chapter structure and feature boundaries.

## Revision Policy

- Treat `SPEC.ja.md` as the canonical product specification.
- Update the Japanese manual first, then carry the same intent into English.
- Record the relevant Web Build whenever UI behavior changes.
- Never record real hostnames, IP addresses, user names, secrets, or local service details in the manuals.
