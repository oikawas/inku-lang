# inku Project Context

**Target version: v1.90.0 / Build 590**

This is the starting point for developers and AI agents. It avoids reloading the full specification for every task. `SPEC.ja.md` remains the canonical design source; when this summary conflicts with it, follow the Japanese specification.

## What to Read First

For ordinary work, read only what the task requires:

1. If a local `AGENTS.md` exists, read it for development, verification, deployment, and security rules.
2. Read this file for the purpose, architecture, and current contracts.
3. Inspect `git status --short --branch` and recent history.
4. Read only the relevant sections of `SPEC.ja.md` or its public English adaptation, `SPEC.md`, plus the implementation files being changed.
5. Search `CHANGELOG.md` or the more detailed `CHANGELOG.ja.md` only when historical context matters.

A full specification read is appropriate for first-time onboarding, design-philosophy changes, broad cross-cutting work, or a specification consistency audit.

## Purpose

`inku` is the reference implementation of DDL, the Drawing Description Language. DDL is conceived as a language for writing visual tanka rather than as a conventional drawing command language.

- The description is the durable work; an SVG is one performance.
- Authors write physical material, placement, motion, and observable relations rather than emotional judgments.
- Brevity and constraint reduce assertion and foreground presentation.
- The default path is reproducible. Variation belongs to renderer performance and explicit user operations.

## Current Architecture

```text
instruction
  -> Stage 1: interpretation
  -> normalized DDL (which may contain namespaced plugin words)
  -> declarative plugin expansion: deterministic writing-down to core DDL
  -> Stage 1.5: deterministic expansion and relation assignment
  -> Stage 2: JSON Score
  -> coerce / validation: boundary handling with a drop-only preference
  -> Render Engine: SVG performance
  -> history and artwork lineage
```

- `server/`: FastAPI backend for APIs, authentication, DB access, interpretation, composition, coercion, rendering, and lineage.
- `web/`: SvelteKit 2 / Svelte 5 frontend.
- `cli/`: `inku-cli`, which operates only through the public HTTP API.
- `android/`: separate Kotlin / Jetpack Compose implementation; `android/ANDROID_SPEC.ja.md` is its detailed canonical specification.
- `SPEC.ja.md`: canonical Japanese design and behavior specification.
- `SPEC.md`: maintained public English adaptation.
- `CHANGELOG.ja.md` / `CHANGELOG.md`: chronological design and implementation history.

## Contracts That Must Remain Intact

- DDL text may be written in the author's language. JSON Score keys remain English.
- Keep Stage 1 interpretation separate from Stage 2 structuring.
- Stage 1.5 must not overwrite interpreted intent or accumulate fixed finished-work recipes.
- Coerce should shrink over time. It must not inject a house style; invalid optional data should prefer drop-only handling.
- The same Score and seed reproduce the same work. Do not add implicit time seeds or automatic variation counters.
- Keep `dh1` description identity, `rh2` work-edition identity, history IDs, and lineage node IDs distinct.
- Lineage records explicit derivation operations only. Never infer parentage from similarity, time, or matching hashes.
- Metrics, similarity, and vision reviews are diagnostic mirrors, not generation gates or automatic best-branch selectors.
- Plugins are validated declarative documents, expanded to core DDL immediately after Stage 1. Stage 1.5, coerce, Score, replay, and rh2 do not depend on plugin content.
- Japanese and English behavior must stay aligned. Do not introduce English-only requirements.

## Current Product State

As of v1.89, the authenticated web application includes:

- automatic Japanese/English instruction detection and per-stage model/language comparison;
- color catalogs, canvas aspects, and reproducible touch/layout/reading refinement;
- user-scoped history, stars, comments, trash, search, and lineage grouping;
- explicit lineage nodes and edges, including intermediate works hidden from regular history;
- autonomous AI refinement, drawing-element/model/language comparison, lineage Okugaki, and generation/prompt/JSON inspection;
- a public-API CLI with administration and benchmark support;
- a `default` Render Engine behind an internal boundary for future Engine Packs.

In v1.90.0, Build 586 formalized `touching`, Build 587 unified relation geometry in transform-composed canvas coordinates, and Build 588 removed duplicate touching assignment. Build 589 adds validated `.inku-plugin.md` documents and a deterministic expansion layer immediately after Stage 1. Explicit qualified terms and `fires_on` nouns that are stated subjects may fire; metaphors and unknown objects may not. Validation rejects recursion, expansion beyond 48 instructions, fixed-coordinate repetition, external references, and namespace collisions. Provenance is ordinary history metadata, while Score, canonical artwork data, rh2, and replay remain independent of plugin documents. Build 590 adds a general boundary preventing Stage 1.5 from appending auxiliary shapes and Score from retaining instructions beyond the explicit numeric-region count after structural expansion. The boundary caps instruction count, while arrangement-driven visible multiplicity remains model-dependent between Mistral and Qwen.

## Where to Look for a Change

| Change area | Primary references |
|---|---|
| Language philosophy, vocabulary, variation, relations | `SPEC.ja.md` §§1–14 or the corresponding `SPEC.md` sections |
| Web UI, refinement, comparison | `SPEC.ja.md` §§7–8 and `web/src/` |
| Score, interpretation, composition, rendering | `SPEC.ja.md` §§5 and 12–14; `server/src/inku_server/` |
| History, lineage, Okugaki | refinement accounting and Okugaki sections; related API and DB code |
| Operations and verification | local `AGENTS.md`, `compose.yaml`, and component READMEs |
| Historical rationale | search `CHANGELOG.ja.md` or `CHANGELOG.md` by term, version, or Build number |

## Documentation Update Rules

- Update `SPEC.ja.md` first for a specification change, then adapt the same intent into `SPEC.md`.
- When current architecture or a major contract changes, update both project-context files.
- Update `CHANGELOG.ja.md` first for release/Build history, then reflect publicly relevant content in `CHANGELOG.md`.
- Keep current contracts in the specification and chronological implementation detail in the changelog.
- For Web behavior or UI changes, increment `web/BUILD_NUMBER`. When the application generation changes, also update the Web `APP_VERSION`.
