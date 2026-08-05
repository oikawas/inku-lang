# Manual Revision History

This file records revisions to user and operations documents under `manual/`. See `SPEC.ja.md` for the detailed product change history.

## 2026-08-05 — Unreleased v2.11.0 Baseline (Web Build 854)

Caught up across 51 versions from v1.85 (Build 564). Both languages were brought onto the same chapter structure.

- Updated the eleven places that name a version to v2.11.0 (Build 854). `manual/README.md` alone had been older still, at v1.82 (Build 563).
- Rewrote Creating Images against the current Web UI. Added **Sketch from life (Stage 0.5)**, **Variation**, **Wild**, `From the description` for the color catalog, **UI mode**, the revision mark, `Replay`, contact sheets, animation export, search by the last four hash characters, and the ten settings tabs.
- Grew the chapter structure from fifteen sections to twenty. **Language comparison was dropped: it is not in the current UI** (`language_variation` survives as a derivation kind on stored works).
- Aligned the vocabulary with the current UI: instructions (normalized DDL), the `Paint` button, the `Work` and `Lineage` tabs on the right, and provenance as `Details` / `Prompts` / `JSON`.
- Corrected the canvases from six to **nine** (Square, Golden, A4, B4, Pillar, Oban, Wide, Byobu, Vertical).
- Added the **six commands that were missing** from the inku-cli Reference: `plugin`, `reference`, `colophon`, `user`, `group`, and `config`.
- Grouped the `paint` and `batch` flags into tables by purpose. **Twenty-six flags were undocumented**, among them the three sketch flags, the two variation flags, `--wild`, `--catalog-mode`, and `--interpretation-seed`. Stated that **an omitted flag paints under the server default**, and that **the server default is not always the Web UI default**.
- Added the **nineteen environment variables that were missing** from Server Configuration. Nothing documented had been retired. Added §2.5 for layers and plugins, moving providers to §2.6.
- Added §5.1 for the limits: the nine values, their defaults, and the rounding rule. Stated that **the environment variables only seed the first value and the DB settings are canonical thereafter**.
- Corrected the render hash from `rh2:` to **`rh3:`**, with the canonical payload and why its key names must not be renamed.
- Added Stage 0.5, plugin expansion, and coerce to the pipeline table. Stated that the sketch reaches three consumers, and that an absent `sketch_state` is not `off`.
- Corrected the Application Installation prerequisite from **Python 3.10 or newer to 3.12 or newer** (`requires-python` is `>=3.12`). Brought the acceptance checks onto the current UI.
- Corrected the description of `--kind reading` in the AI reference: it is **Stage 1, not Stage 1.5**, and Stage 1.5 is not an LLM. Added the `derivation_kind` mapping.
- Added §0.8, "Beware the silent sender", to the same document. **Variation takes effect only when both flags are given, so having passed a flag is not evidence it took effect.**
- Repaired a sentence in which Japanese and English had been spliced together, in the `refine perform` description.
- Added painting concurrency, the per-stage hard timeouts, sign-in methods, the plugin directory, the learned-word file, and Redis to the environment variable template.

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
