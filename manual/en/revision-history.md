# Manual Revision History

This file records revisions to user and operations documents under `manual/`. See `SPEC.ja.md` for the detailed product change history.

## 2026-08-11 — Unreleased v2.12.1 Baseline (Web Build 878)

Updated the 13 places that name a version to v2.12.1 / Build 878, and **revised `Creating Images` §3 for the wider reach of a written number**.

- **A written number now reaches up to 239, where it used to stop at eleven.** Numbers written as "thirty" or "two hundred and thirty-three" are drawn as written.
- **The boundary is the same value as `Stated counts` in `Server Configuration` (240 by default).** No new setting was added; moving that boundary moves the reach of a written number with it.
- **The condition is unchanged.** It applies only when the sentence points to a single group; where the sentence does not settle on one, the count is left alone.
- **When the number asked for would cross the limit for one work or for one group, it is not drawn part of the way.** It is left as it is, because **a partial count is neither the number written nor the number of a crowd.**
- **Treatment of 240 and above is unchanged** (the work is shown as a crowd).

## 2026-08-10 — Unreleased v2.12.0 Baseline (Web Build 877)

Updated the 13 places that name a version to v2.12.0 / Build 877, and **revised `Server Configuration` §2.2 and §4, the `inku-cli Reference`, and `Application Installation` §7 for the new way permission is decided**.

- **What a member may do is now decided by the permission groups they hold, not by a role.** There are three groups — `admins`, `leaders`, and `users` — and no more can be created.
- **One member may hold several groups.** Someone holding both `admins` and `leaders` is treated as the stronger of the two, `admins`.
- **Existing roles move one-to-one at startup.** `admin` becomes `admins`, `group_lead` becomes `leaders`, and `user` becomes `users`. **Nothing has to be set up again.**
- **An `inku-cli` flag changed.** `user create --role` is no longer accepted; pass **`--permission-group {users,leaders,admins}`**, repeating it if you need more than one.
- **User groups — the organisational unit — are unchanged.** They are a separate thing from permission groups: one per member, and independent of permission.
- **Restoring from a backup works as before.** The `role` column stays on the user row, written by the machine from the memberships. **Nowhere is it read to decide what somebody may do.**

## 2026-08-10 — Unreleased v2.11.20 Baseline (Web Build 876)

Updated the 13 places that name a version to v2.11.20 / Build 876, and **added how a written count is treated to `Creating Images` §3**.

- **A number from one to eleven is now drawn as written.** Until now only an emphatic form such as "three lines only" held a number; **a count written the ordinary way — "place three circles" — could be overwritten by downstream guesswork.**
- **It takes effect only when the sentence points to a single group.** If several groups share the same shape, colour and weight so that the sentence does not settle on one of them, the count is left alone. **Applying an ambiguous match would break the number some other sentence stated.**
- **Numbers of twelve and above are unchanged.** (`Stated counts` in `Server Configuration` still governs them.)
- **Cloud forms are now read as a shape.** Writing "cloud form" could previously be treated as a line.

## 2026-08-10 — Unreleased v2.11.19 Baseline (Web Build 875)

Updated the 13 places that name a version to v2.11.19 / Build 875, and **revised the body for single-user mode**.

- **The distribution can be used without writing a single environment variable.** A server started with `INKU_SINGLE_USER` (the distributed compose default is `1`) settles on one person and signs them in automatically. **The sign-in screen never appears.**
- **`INKU_BOOTSTRAP_ADMIN_PASSWORD` is handled differently.** It used to be required, and `docker compose up` stopped before startup without it. **Compose no longer checks this value** — it is unnecessary while single-user mode is on, and Compose interpolation cannot express that condition. **If you set `INKU_SINGLE_USER=0`, set this value yourself.**
- **"This first setting cannot be skipped" now describes single-user mode being off.** (`Application Installation` §7)
- **In single-user mode the sign-out control is hidden**, because using it would only sign you back in. **Changing the password and managing users stay visible** — under the distribution default the account's password is a value nobody knows, so that is the only way back from single-user operation to ordinary operation. The settings panel states this in one line.
- **`inku-cli` now sends requests without having run `login`.** Against a single-user server they go through; against any other server the familiar message appears.
- **Added `INKU_SINGLE_USER` to the environment variable table.** (`Server Configuration` §2.2)

## 2026-08-10 — Unreleased v2.11.18 Baseline (Web Build 874)

Updated the 13 places that name a version to v2.11.18 / Build 874. **The manual body is unchanged** — no screen operation, setting, or response key moved.

- **The drawing changes.** When a description names only one color, **that color now goes to every member of a group**. Until now a color the description never named could join the color cycle, so **the named color reached only half the members**.
- **A description asking for many colors is untouched.** When words such as "colorful" are present, the color cycle stays as it is. The same holds when the description names two or more colors.
- **The background color does not count as a mark color.** "Fill the background with black. Draw white lines" is read as a description naming one color, white.
- **`--trace` now works for a batch run with `--input-mode ddl`.** Until now that combination accepted the flag and returned no intermediates, doing nothing silently.
- **No operation was added.** Neither the way descriptions are written nor any flag changed.

## 2026-08-09 — v2.11.17 unreleased baseline (Web Build 873)

The 13 places that name a version were updated to v2.11.17 / Build 873. **No manual text changed** — no screen action, CLI flag, setting or response key moved.

- **The drawings do change.** The fray — the part of a stroke drawn only where the tool meets the paper — is computed differently, so **the edges of strokes drawn with the six tools that carry a material layer (pen, pencil, thick brush, crayon, chalk, thin brush) shift slightly**. The shape and position of the stroke itself do not move.
- **The same work now draws the same picture on any machine.** Until now the same input could differ **very slightly depending on the server's operating system**. Lengths are counted the same way everywhere, and that difference is gone.
- **Drawings made with the five tools that carry no material layer (rotring, drypoint, silverpoint, computer, burin) do not change by a byte.**
- **Nothing was added to the interface.** How you write a description, and every flag, are unchanged.

## 2026-08-09 — v2.11.16 unreleased baseline (Web Build 872)

Updated the 13 places that name a version to v2.11.16 / Build 872, and **added one sentence to "Input and output" in the `inku-cli` reference**.

- **The JSON artifacts the CLI writes now name the version of the DDL layer that drew the picture.** They carry `ddl_version` and `ddl_engine_version`, so **the JSON alone tells you which interpretation drew the picture**. Until now only the render engine was named.
- **Older works leave the values empty.** Exporting a work made before these versions were recorded gives you the keys with nothing in them.
- **⚠ `render-score` stops against an older server.** When the server will not say which versions it used, the CLI **stops rather than write an artifact that names no version**.
- **Nothing was added to the interface.** No flag and no screen step changed.

## 2026-08-09 — v2.11.15 unreleased baseline (Web Build 871)

The 13 places that name a version were updated to v2.11.15 / Build 871. **No manual text changed** — no screen action, CLI flag, setting or response key moved.

- **The drawings do change.** When a description names two or more colors, **how they are handed out** changes. Colors go to the elements one at a time in turn, so **there is no first color and no ranking**. Two kinds of order were being added anyway.
- **Mixing an old color with a new one no longer loses the new one.** Writing something like "red and yellow" — **any of white, black, blue, red, green, gray together with any of yellow, orange, purple — used to drop the latter entirely**. Both now arrive.
- **Naming the same color twice no longer gives it twice the elements.** How much extra weight it got **depended on how many colors happened to be in the cycle**, so it never meant what was written.
- **A color the description asks for reaches a primary stroke within the same drawing.** It used to need a second pass over the same description, so **one input produced two different results.**
- **Nothing was added to the interface.** How you write a description is unchanged.

## 2026-08-09 — v2.11.14 unreleased baseline (Web Build 870)

Updated the 13 places that name a version to v2.11.14 / Build 870, and **added two flags to "Input and output" in the `inku-cli` reference**.

- **`--ddl-text DDL` and `--ddl-file PATH`** — both are `render-score` only and **hand the instructions to coerce**. With them, the same repairs that run in paint (a stated count, a stated relation) run here too. `--ddl-file -` reads standard input, and naming both is an error. **Omit them and nothing changes.**
- **Redrawn pictures change.** "Change the touch by words" and "redraw with another catalog" **were already sending the description to the server, which was not reading it**. Now it does, so **a redraw is repaired the same way the first drawing was**.
- **Nothing was added to the interface.** The Web UI steps are unchanged.

## 2026-08-09 — v2.11.13 unreleased baseline (Web Build 869)

The 13 places that name a version were updated to v2.11.13 / Build 869. **No manual text changed** — no screen action, CLI flag, setting or response key moved.

- **The drawings do change.** Render engine 28 makes **the sway of a line and the tool's tone read how thick that tool's mark is**.
- **How far a line sways no longer depends on how large the figure is.** It used to be a fraction of the figure's representative size, so **a thin pen drawing a large arc left its own line by eleven times its width, and the arc stopped looking like an arc**. It is now **a multiple of that line's width** (0.35 fine, 0.6 medium, 2.0 broad). **A small figure and a large one both sway by about as much as they are thick.**
- **The tool's tone (the material outline) now follows the ink that was drawn.** It used to be taken from where the figure was meant to be, so when the ink swayed the tone was left behind. **The distance from the tone to the ink falls from 16.1 px to 3.2 px on a large arc.**
- **The fray looks different.** It used to be an evenly spaced dashed line; now the stroke is drawn **only where it crosses a field standing for the paper's tooth**. **How much of a stroke each tool touches is unchanged** — a pen stays nearly continuous and a pencil keeps its gaps.
- **The tone's weight was fitted to the tool.** A layer is **never thicker than 0.33 of that tool's mark** and **never sits inside the mark**. The heaviness seen with the thicker brush settles down.
- **Nothing was added to the interface.** How you write a description is unchanged.
- **Redrawing the same description with the same seed changes the drawings made with the six hand tools** (pencil, pen, crayon, chalk, thin brush, thick brush). The other five — rotring, silverpoint, computer, burin and drypoint — carry no material outline and do not change by a pixel.

## 2026-08-09 — v2.11.12 unreleased baseline (Web Build 868)

Updated the 13 places that name a version to v2.11.12 / Build 868, and **corrected the logging guidance and the bundled templates**.

- **Rewrote the logging section of `Server configuration`.** The log policy in the admin UI (enabled / retention days / interval / compression) is **executed by the application itself**. Files are written under `INKU_LOG_DIR` (`~/.local/share/inku/logs` by default, `/data/logs` in the container distribution), and the application rotates, compresses and prunes them. **No logrotate configuration is needed any more.**
- **Removed the two `StandardOutput=journal+append:` lines from the two bundled systemd templates.** **That specifier does not exist in systemd**; it was ignored on every start. File output is the application's job now, so no systemd directive is required.
- **Retired the `logrotate example` template and removed its link from `README`.**
- **Output to stdout is unchanged.** `journalctl` and `docker logs` work as before. In the container distribution, `compose.yaml` now caps what the daemon collects from stdout.

## 2026-08-09 — v2.11.11 unreleased baseline (Web Build 867)

The 13 places that name a version were updated to v2.11.11 / Build 867, and **two passages changed**.

- **One paragraph was added to `Creating Images` §7.** **Redrawing an older work now draws it in the colors it was drawn in, not in today's definition of its catalog.** It still draws if the catalog has been renamed, and it still draws if the catalog has been retired. The catalog name in the status area carries `Retired` when the catalog is gone, and `No record of its colors` for an older work that has none.
- **One flag was added to "Performance and color" in the `inku-cli Reference`** — `--from-work WORK_ID`. It is for `render-score` only and draws in the colors that work was drawn in. It cannot be combined with `--color-catalog` / `--catalog-id`.
- **Nothing changed in how a new work is painted.** Only the source of the colors for a redraw moved.

## 2026-08-09 — v2.11.10 unreleased baseline (Web Build 866)

The 13 places that name a version were updated to v2.11.10 / Build 866. **No manual text changed** — no screen action, CLI flag, setting or response key moved.

- **The drawings do change.** Render engine 27 **widens the swing within a group drawn with a hand tool**. Each member's size now varies by 35% either way instead of 25%, and each member's angle by **27 degrees** either way instead of 12. **No rule changed** — only how far the hand swings.
- **Rotring and computer stay exactly as they were.** A machine repeating itself precisely is kept deliberately, as those two tools' signature.
- **What did not turn still does not turn:** lines and circles, grids, single-member groups, and any group whose angle the description states. **A circle looks the same turned.**
- **Nothing was added to the interface.** How you write a description is unchanged.
- **Redrawing the same description with the same seed changes only groups that state repetition and are drawn with a hand tool.** A work that states no repetition is identical to the pixel.

## 2026-08-09 — v2.11.9 unreleased baseline (Web Build 865)

The 13 places that name a version were updated to v2.11.9 / Build 865. **No manual text changed** — no screen action, setting or response key moved.

- **Eight older works could take the whole server down when exported as PNG.** A fault in the rasterizer used for drawing (resvg) **stopped the server the moment the export was requested, taking any other work in progress with it.** This is fixed.
- **Eight of 2,769 works were affected, all of them painted long ago.** None of the 1,065 works painted by recent drawing engines are affected. **It was never a problem for pictures you paint today.**
- **No picture changes by a single pixel.** The same works were burned before and after the fix, and the images are identical — on the development server and on the Mac alike.

## 2026-08-09 — `rasterize` was added to the CLI (still v2.11.8 / Web Build 864)

**The 13 places that name a version were not touched.** Nothing in the web interface or the server's responses changed, and no version was numbered. **One line of manual text changed.**

- **`inku-cli rasterize` is available.** Point it at a folder of SVGs and it burns them all to PNG. `--width` sets the pixel width; leave it out and each SVG is burned at the width it declares. `--workers` sets how many run at once.
- **A file that cannot be burned leaves no output at all.** A truncated or 0-byte PNG would be counted and looked at like any other picture. **What could not be burned is printed, with a count and a reason.**
- **One process per file.** If a single picture fails, the rest are still burned to the end.
- **No drawing changes.** The rule for burning a picture is the same one as before, now kept in a single place. **The same SVG gives the same PNG** — across the development server and the Mac, all 24 test pictures matched to the byte.

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
