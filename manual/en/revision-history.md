# Manual Revision History

This file records revisions to user and operations documents under `manual/`. See `SPEC.ja.md` for the detailed product change history.

## 2026-08-08 — v2.11.8 unreleased baseline (Web Build 864)

The 13 places that name a version were updated to v2.11.8 / Build 864. **No manual text changed** — no screen action, CLI flag, setting or response key moved.

- **The drawings do change.** Under render engine 26, **every member of a repeated group finds its own angle.** The previous version gave each member its own size, but they all still faced the same way; **with a hand tool each one now differs, within 12 degrees either side.**
- **Rotring and Computer still repeat at exactly one angle.** Keeping the machine's repetition exact — in angle as well as in size and stroke — is deliberate: it is those two tools' signature.
- **A description that states an angle is drawn exactly as stated.** A group whose rotation you name never wavers. **That includes stating zero degrees.**
- **Lines and circles, grids, and groups of one are unchanged.** Turning a line makes a different line, turning a circle changes nothing you can see, and a tiling's point is that the cells match.
- **No new action was added.** "Several of this shape" was always the instruction; **reading it as "all of them facing the same way" was the drawing side's addition. Nothing about how you write a description changes.**
- **Redrawing the same description with the same seed changes only the groups that state repetition with a hand tool.** A work that states no repetition does not move by a pixel.

## 2026-08-08 — v2.11.7 unreleased baseline (Web Build 863)

The 13 places that name a version were updated to v2.11.7 / Build 863. **No manual text changed** — no screen action, CLI flag, setting or response key moved.

- **The drawings do change.** Under render engine 25, **every member of a repeated group gets its own size.** The N copies in a group used to be drawn exactly the same size; **with a hand tool each one now differs, within 25% either side of the stated dimension.**
- **Rotring and Computer still repeat at exactly one size.** Keeping the machine's repetition exact — in size as well as in stroke — is deliberate: it is those two tools' signature.
- **Grids and groups of one are unchanged.** A tiling's point is that the cells match.
- **No new action was added.** "Several of this shape" was always the instruction; **reading it as "all of them the same size" was the drawing side's addition. Nothing about how you write a description changes.**
- **Redrawing the same description with the same seed changes only the groups that state repetition with a hand tool.** A work that states no repetition does not move by a pixel.

## 2026-08-08 — v2.11.6 unreleased baseline (Web Build 862)

The 13 places that name a version were updated to v2.11.6 / Build 862. **No manual text changed** — no screen action, CLI flag, setting or response key moved.

- **The drawings do change.** Under render engine 24 a group's fade reaches every member. Saying "it fades from the centre to the edge" previously drew the whole group at one density; **now the nearer marks are darker and the farther ones paler.**
- **No new action was added.** The fade declaration already existed; only the side that draws it could not receive it. **Nothing about how you write a description changes.**
- **Redrawing the same description with the same seed changes only the groups that declared a fade.** A work that never declared one does not move by a pixel.

## 2026-08-08 — v2.11.5 unreleased baseline (Web Build 861)

The 13 places that name a version were updated to Build 861. **The application version is unchanged** (still v2.11.5), and **neither the screen nor the drawings change.**

- **The API reference description of `composition_seed` now states what the seed does under engine 23.** The descriptions on `/api/paint` and `/api/compose` still read "Stage 1.5 composition variation seed" and **did not say that from engine 23 this seed also decides where the marks are placed**. Only `/api/render-svg` carried the correct wording. **This text is what a direct API user reads, so all three now say the same thing.**
- Only the descriptions changed. **The accepted keys, their defaults and the responses are identical**, and the 36 fields of `/api/paint` and the 19 of `/api/compose` neither grew nor shrank.

## 2026-08-08 — v2.11.5 unreleased baseline (Web Build 860)

The 13 places that name a version were updated to v2.11.5 (Build 860).

- **`Another performance` now keeps the composition.** Until this version, changing only the touch also **moved where the marks were placed**, because one seed decided both. From this version the placement is decided by `composition_seed`, so a new touch seed leaves the composition where it was. **The action now behaves the way its own description said it did.**
- **`inku-cli --composition-seed` now actually draws at the placement you asked for.** It used to record the value in the output metadata and in the identity hash while **never drawing with it**. The flag's description in the `inku-cli Reference` was corrected as well.
- **Existing works look exactly as they did** (a stored SVG is returned unchanged). Redrawing the same description also gives the same picture as before unless you set a composition seed.
- The render engine goes 22 to 23. Section 6 of `Server Configuration` now states how the placement seed is resolved: it follows the performance seed when omitted, and `0` is a seed rather than "not given".

## 2026-08-07 — v2.11.4 unreleased baseline (Web Build 859)

The thirteen places that name a version now read v2.11.4 (Build 859). No explanatory text changed.

- The only thing this version moved is **how a fill is drawn** (render engine 21 to 22). **Nothing about the controls changed** — no item was added to or removed from the Web UI, the CLI, or the server settings. Filled shapes look different: the strokes now sit on an underlay that holds the field, and a thin tool leaves rubbings rather than scan lines. **Existing works are unaffected** (their saved SVG is returned as it was); redrawing the same description produces the new appearance.

## 2026-08-06 — v2.11.3 unreleased baseline (Web Build 858)

The thirteen places that name a version now read v2.11.3 (Build 858).

- Section 12 of `Creating Images` (Follow the Lineage) now names the **sketch grain**. Redrawing at a grain different from the parent's used to **fail to save at all** -- the server did not know the derivation kind, so no work, no history entry and no lineage edge was written. From this version the save succeeds and the relation is recorded. **The same kind covers switching the sketch layer on or off, not only changing the grain.**

## 2026-08-06 — v2.11.2 unreleased baseline (Web Build 857)

The thirteen places that name a version now read v2.11.2 (Build 857). No prose changed.

- The only thing this version moved is the internal structure of the Android app (the place that decides a run's colour catalogue is now a single one). Nothing visible to creators or administrators changed in the Web UI, the CLI, or server configuration.

## 2026-08-06 — v2.11.1 unreleased baseline (Web Build 856)

The thirteen places that name a version now read v2.11.1 (Build 856). No prose changed.

- The nine numbers on the `Limits` tab now use the same **stepper with `-` and `+`** as the DB backup tab. **How they are changed is unaffected** (the administration UI or `inku-cli config update`), so section 5.1 of `Server Configuration` still holds.

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
