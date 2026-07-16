# inku Changelog

**Public English release notes** — See [SPEC.md](SPEC.md) for the current English specification and [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) for the short developer entry point.

This file records changes chronologically. If a historical note conflicts with the current specification, the current specification wins. The more detailed canonical history is maintained in Japanese in [CHANGELOG.ja.md](CHANGELOG.ja.md).

---

### v1.72 — Refine and Compare UI

- Unified touch, layout, and reading selection, including the hierarchy in which reading regenerates layout and touch.
- Unified one/four-candidate selection and saving, cancellable generation, cross-panel generation exclusion, dynamic progress/cost copy, and DDL hover previews.
- Replaced sequential variation counters with independent JavaScript-safe random seeds, made touch changes visible for fixed shapes, and restored seeds when loading history into the canvas.
- Persisted caption visibility per user.
- Preserved tab context during previous/next navigation and expanded model comparison to three Stage 1/2 modes.

### v1.73 — System prompt optimization (2026-07-12)

- Fixed self-contradictions in the Stage 1 / Stage 2 prompts: conversion examples that used vague counts ("several"/「数本」) against the prompts' own concrete-count rule, and inconsistent radius notation. Added the missing motions category to the ja Saijiki list and the missing sparse-validity rule to the ja Stage 2 prompt (the en prompt has had it since Build 415).
- Stabilized the "Ground: ..." / 「地: ...」 route to canvas.ground: added ground-retention examples to the Stage 1 example pool, added an explicit Ground→canvas.ground / Surface→main-shape routing rule with an anti-duplication guard to Stage 2, and canonicalized the Stage 2 ground example inputs to the actual Stage 1 output form.
- Fixed a defect in api.py where a canvas_aspect override replaced the whole canvas value and destroyed any Stage 2-generated canvas.ground (the true cause of the 0/12 ground adoption recorded at v1.71). Targeted 12-prompt bench: ground adoption 0/12 → 5/12.
- Merged duplicated placement-mapping bullets and grouped the ~70-bullet Stage 2 rule list under eight subsection headers (content and order effectively unchanged).
- JP/EN 30+30 regression bench on the Build 448 prompt set: JP improved on every metric (visual_event 89.7→94.9); a main-branch baseline run attributed the apparent EN drop vs 448 to pre-existing v1.70/v1.71 drift, with this change improving on main across all quality metrics. All fingerprint gates pass.

### v1.74 — NIM Qwen3.5 397B Migration & Relation Tuning (2026-07-12)

- **Switched Default Models to Qwen3.5 397B**:
  - Switched the default Stage 1 / Stage 2 models to NVIDIA NIM `qwen/qwen3.5-397b-a17b`.
  - Restricted the `is_qwen3` thinking-trace suppression override (`/no_think` prefix injection) to local OVMS provider runs only. This change enables NIM Qwen3.5 397B to fully leverage its reasoning capability, improving both generation quality and latency by roughly 30%.
- **relation Duplication Prevention (F-1)**:
  - Tuned the Stage 2 prompt (`composer.py` relations section and examples) in both Japanese and English to add an anti-duplication guard: "Generate at most one relation per fixed relation phrase. Do not replicate the same relation phrase into multiple instructions," and added corresponding negative examples.
- **Achieved 100% ground Mapping Adoption (F-3)**:
  - Achieved a **6/6 (100%)** `canvas.ground` mapping adoption rate in the targeted 12-prompt texture benchmark, resolving the remaining ground-routing misses from v1.73. Verified no quality regressions on the JP30/EN30 regression sets.


### v1.74.1 — ground hotfix (2026-07-13)

- Added Japanese and English Stage 2 rules that prohibit inferred `canvas.ground` unless normalized DDL contains an explicit 「地: ...」 / "Ground: ..." sentence.
- Added a general Stage 1 support-preservation rule for Qwen3 Next: explicit 「〜の地」「〜の紙に」 / "... ground" / "on ... paper" wording must remain a `地:` / `Ground:` sentence and must not be rewritten as a background fill.
- Added a drop-only ground literal gate after composition. It removes only unmarked ground while preserving canvas aspect; it never creates, repairs, or replaces ground when a marker is present. Drops remain observable through a warning log.
- Moved display ground texture opacity (clamped to 0.02–0.18) onto the texture rect itself and changed the filter alpha table to `0 1`. Filter-capable browsers retain the same effective alpha, while filter-free PNG rasterizers now degrade to a faint veil instead of an opaque gray wall.
- Audited every renderer filter use and found no other wide filtered shape whose transparency depended entirely on its filter.
- Build 508 passed 314 tests with 30 skipped on both Mac and pentala; ruff, web check, and web build were green. Fixed-model Qwen3 Next benchmarks completed 12/12 surface/ground prompts (6/6 explicit ground, zero inferred ground, no gray wall) and 30/30 prompts in both Japanese and English (zero inferred ground, no quality drop beyond the threshold, all fingerprint gates passed, and zero 502s, timeouts, or fallbacks). Full results are recorded under “v1.74.1: ground hotfix” in the local benchmark log.


### v1.75 — Literal tiling pattern field (2026-07-13)

- Added the physical motion word `tile` / 「敷き詰める」 to Saijiki. It is selected only for a literally requested regular repeated surface, never inferred from merely “many” or “countless.”
- Added `layout="grid"` with optional `rows`, `cols`, and `jitter`. Grid fills `at.region` or the margin-bounded canvas; explicit rows×cols take priority over count. The schema limit is 2000 for literal tiling while ordinary arrangements keep the existing 1–1000 prompt contract.
- Grid performance layers seeded cell jitter, distinct per-element variation phase, and material-specific weight behavior while preserving bit-identical replay for the same Score and seed. Coerce does not add fade, clustering, preserved space, or count reduction to grid. Build 515 limits English literal markers to tile/tiled/tiling and adds a drop-only boundary so a motif label containing grid alone cannot create a spontaneous grid.
- Added matched Japanese and English Stage 1 / Stage 2 rules and wallpaper, four-direction, and square-grid examples. Four directions remain a maximum of four overlaid instructions; no new primitive was introduced.
- Build 515.


### v1.76 — Artwork lineage (2026-07-14)

- Added `dh1:<sha256>` as description identity over NFC-normalized text with LF line endings and trimmed outer whitespace. Batch labels such as `#1` are presentation metadata and do not affect `dh1`. Description identity, the existing `rh2` edition identity, history IDs, and lineage node IDs remain separate concepts.
- Added independent lineage nodes and edges. Parentage is recorded only by explicit touch, layout, interpretation, model, DDL-edit, description-edit, replay, or canvas-aspect-change operations; it is never inferred from hashes, timestamps, or visual similarity. Existing history rows are backfilled as separate roots.
- When generation, DDL drawing, or further refinement continues from an unsaved refinement candidate, only that direct ancestor is automatically retained as an intermediate `lineage_only` work. The Canvas labels the preview as unsaved and reports that automatic intermediate retention is hidden from regular history. If retention fails, drawing does not silently continue as a new root. Intermediate cards are labeled as hidden from history; they do not affect regular history counts or starred views, and the user can promote the same node and edges with “Save to regular history” from the lineage view.
- Added a focused Canvas lineage view showing nearby generations as artwork thumbnails with arrows between parent and child cards and labels for the operation that produced each child. Opening a card changes both the displayed artwork and the parent for the next refinement. Card checkboxes support confirmation-gated bulk moves to trash. Trash preserves lineage; permanent deletion removes content and hashes while leaving a content-free tombstone to preserve the path.
- Users can explicitly start a new root. Ordinary DRAW actions are not automatically attached to the latest history item.
- Lineage depth and branching are not quality scores, achievements, or generation controls. The graph records the creative process; it does not choose a best branch.
- History-manager artwork selection uses a compact, dedicated check control independent from opening an artwork, with exactly one state change per activation. Thumbnails do not show enlarged hover previews.
- Stars toggle immediately without a confirmation dialog. Artwork comments are stored independently from star state and are edited in lineage-card details; removing a star does not erase an existing comment.
- Works generated in Refine's Model comparison subview use the same circular image-corner `+` adoption control as Adjust candidates and show `✓` after being saved to history. Starring remains independent from adoption.
- The displayed artwork and the bottom-history current marker stay synchronized by history ID. Opening an off-page work from lineage, History Manager, or replay uses `anchor_id` to load the page containing that work. Background Compare/Refine saves do not steal the marker, and unsaved candidate previews do not leave a different history work marked current.
- While History Manager is open, external-history polling does not replace its items or page size. Thumbnail action areas use a uniform height, and the page row count is calculated once from the maximum measured card height, preventing clipped final rows and the refresh loop that replaced roughly 90 items with the bottom strip's smaller item count.
- Build 525.

**v1.76 closure (2026-07-15):** Build 525 is the accepted v1.76 release. Successive real-browser reviews confirmed that any lineage work can become the next derivation source, parent-child paths remain traceable through generation arrows, the displayed work stays synchronized with bottom history, and History Manager selection, bulk deletion, and page sizing remain stable. Feedback was incorporated across Builds 518–525. Subsequent work, beginning with v1.80, uses this lineage contract and the separation of the four identities as its foundation.

### v1.87 — Printmaking Grammar and Vocabulary Refinement (2026-07-16)

- Added a deterministic five-layer stroke performance: intended path, damped hand dynamics, one shared 1/f-like latent energy signal, sparse events, and per-tool grammar. Width, lateral deviation, and apparent density covary; rotring explicitly blocks the expressive engine to preserve uniformity.
- Added `burin` and `drypoint`. Burin tapers at both ends and swells through the cut; drypoint adds a seed-selected one-sided burr. These model general tool behavior, not an artist or period.
- Extended existing surfaces with `hatch`, `crosshatch`, and stepped `aquatint`; added `mezzotint` ground and `mode="carve"` with `light|half|bright`. Rendering order is ground, additive marks, carved light, then plate tone.
- Plate tone, mezzotint grain, drypoint burr, and register shift remain deterministic under the existing texture-seed convention. The `rh2` canonical payload is unchanged.
- Printmaking fields are literal-input only. Stage 1.5 cannot inject them, and invalid carve without a dark ground is dropped without repair.
- Removed `rope` from the core vocabulary, Score schema, renderer, prompts, and Saijiki. Because inku is unreleased, v1.87 uses the opportunity to remove an ambiguous object-metaphor touch instead of carrying compatibility debt. The resulting touch vocabulary has ten entries.
- SVG transfers the grammar of engraved line and tone; it does not claim to reproduce physical plate indentation or raised ink.
- **Build 568:** Fixed the rendering order that allowed legacy fixed-width lines to cover variable-width stroke outlines. Burin taper and swell, drypoint's one-sided burr, and the existing writing-tool gestures now remain visible in the primary mark. All ten Saijiki touch previews were aligned with those observable renderer differences.
- **Build 569:** Normalized DDL now names one touch for every visible line, arc, or outline. Japanese and English Stage 1 rules and examples were updated, dynamic few-shot selection guarantees a non-pen material example, and Stage 1.5 applies the same rule to its added marks. Filled shapes are not assigned material mechanically, and post-rewrite double expansion is prevented.
- Builds 567–569.

### v1.88 — Okugaki Lineage Recitation (2026-07-17)

- Added manual first-person recitation of one root-to-target branch using structurally prefix-only generation requests.
- Deterministic feature differences and invariants come from the existing read-only composition mirror; SVG works are rasterized to PNG for vision input, and the server adds the model/date signature.
- Added user-scoped append-only storage, oldest-first display, deletion without editing, and Idempotency-Key handling.
- Added the explicit Lineage UI action and `inku-cli okugaki` with `--dry-run`. The feature remains disconnected from dh1/rh2 and every generation or refinement decision.
- Build 570.
- **Build 571:** Okugaki Idempotency-Key generation now uses a UUID fallback based on `getRandomValues()` (with a final compatibility fallback), so appending works in LAN HTTP browser contexts where `crypto.randomUUID()` is unavailable.
- **Build 572:** History Manager thumbnail capacity is now derived from a stable layout contract instead of measuring partially painted cards. Removing per-card `content-visibility` prevents missing thumbnails, page-size oscillation, and flicker inside the modal.

### v1.89 — UI Refinement (2026-07-17)

- **Model selection (Build 573):** Replaced provider/model dropdowns with a dialog that presents available model names grouped by provider. The `Stage 1/2` tab assigns one model to both stages, while the `Stage 1` and `Stage 2` tabs allow separate choices. Existing confirm, cancel, and per-user persistence behavior remains intact.
- **LLM / Vision settings split (Build 574):** Separated the Vision default from Stage 1/2 LLM settings across the model dialog, admin model-purpose settings, Okugaki, API, and CLI. The legacy `/api/models` `catalog` and CLI `--model` option remain compatibility paths.
