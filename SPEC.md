# inku — Drawing Description Language Specification

**Version: v1.92.0**
**Canonical source:** [SPEC.ja.md](SPEC.ja.md)

This document is the official English specification for public review, contest
submission, and non-Japanese readers.  It is adapted from `SPEC.ja.md`, which is
the canonical source because the author works in Japanese.  When the
specification changes, update `SPEC.ja.md` first, then refresh this English
version.

For ordinary development, start with [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)
and read only the specification sections relevant to the task. Chronological
release history is maintained separately in [CHANGELOG.md](CHANGELOG.md), with
more detailed canonical notes in [CHANGELOG.ja.md](CHANGELOG.ja.md).

---

## 1. What inku Is

`inku` is the reference implementation of DDL, the Drawing Description
Language.  DDL is a compact language for writing visual instructions that can be
interpreted by LLMs and rendered as abstract SVG drawings.

inku is not a drawing program in the usual sense.  It treats the written
description as the durable work, and the rendered SVG as one performance of that
work.  The same description may be rendered again later, with controlled
variation, while preserving the underlying score.

The project stands at the intersection of three traditions:

- Sol LeWitt's instruction-based art, where the instruction itself is part of
  the artwork.
- Bonsai, where constraint, scale, and material focus expression rather than
  reducing it.
- Tanka, where a fixed form makes presentation more important than assertion.

The name `inku` comes from the Japanese reading of "ink".  It also points to
the material nature of writing and to the sumi-ink world that informs the visual
palette.

---

## 2. Core Idea

DDL is designed as a language for writing visual tanka.

The author writes a short description.  The system interprets it into a
controlled DDL vocabulary, expands it through deterministic filters, structures
it as JSON, and renders it as SVG.

```text
description -> normalized DDL -> expanded DDL -> JSON Score -> SVG
human          Stage 1          Stage 1.5      Stage 2       Renderer
```

The description remains readable by humans.  The JSON Score remains structured
enough for machines.  The SVG is a performance.

In LeWitt's terms, the normalized DDL is the instruction sheet; Stage 1 stands
where LeWitt stood when he wrote the instructions.  inku adds one layer above
it: the author writes a poem-like description, and the machine transcribes it
into LeWitt-style instructions.

The vocabulary maps to the layers as follows.  This table matches the UI's
vocabulary dialog (App Info, "Vocabulary & Layers") and is the single source
of truth.

| Term (ja) | Term (en) | Layer / act |
|---|---|---|
| 記述 | Description | The poem-like input the author writes. The top layer of the work (inku-specific; no LeWitt counterpart) |
| 解釈 | Interpret | Stage 1's **act** of reading the description into instructions |
| 指示書（正規化DDL） | Instructions (Normalized DDL) | The executable specification the interpretation produces. **Corresponds to LeWitt's instruction sheet** |
| 楽譜（JSON Score） | Score (JSON Score) | The structured intermediate form of the instructions. Stored deterministically |
| 演奏（SVG） | Performance (SVG) | The one-time result of playing the score (the draftsman's realization) |
| 詞書 | Kotobagaki (caption) | The description re-presented beside the finished work (as in tanka) |
| 読み取り | Reading | Rebuilding candidates by re-reading the words (another interpretation) |

Variation is intentional.  DDL does not attempt to eliminate all model or
renderer variation.  It uses variation as part of the medium, while keeping the
score, schema, and renderer boundaries explicit.

The UI display language and the instruction language are separate metadata.
The writing tab does not ask users to choose a language: normal generation
always sends `instruction_lang: auto`. Users may run the Japanese UI while
writing English instructions, or use the English UI while writing Japanese
instructions. API requests retain explicit `ja` and `en` values for compatibility
and comparison runs, while `ui_lang` provides display context. With `auto`, the
server lightly detects Japanese or English from the input text and uses the UI
language only when the text itself has no language signal. The resolved language
is passed to Stage 1, Stage 1.5, Stage 2, and demo-instruction generation. Render metadata
records `instruction_lang_requested`, `instruction_lang_resolved`, and
`ui_lang` for audit and replay context.  These language metadata fields are not
part of the current canonical `render_hash` payload, so existing history hashes
and benchmark references remain stable.

Instruction-language implementation is organized through an internal
Instruction Language Registry.  Each registered language owns its language code,
Stage 1 prompt, Stage 2 prompt, Stage 1.5 expander/filter entry point, and
the language-specific marker set used by the Score coerce layer.
Japanese and English are registered by binding the existing prompts and
expanders without changing their text or behavior, while their coerce marker
sets live in separate language files.  The coerce algorithms remain common
because they operate on language-independent JSON Score structure; language
differences belong in the marker sets that map words such as motion,
visual-event, hard-edge, or dark-field cues to those shared repair policies.  A
third-party language such as Spanish should be added first as a new registry
entry with prompts, expander behavior, and coerce markers, keeping JSON Score
schema, renderer behavior, and color catalogs separate unless the new language
demonstrably needs a core extension.

Builds 403-427 extend the English instruction path beyond structural routing.
Japanese and English now live in separate language files for Stage 1 prompts,
Stage 1.5 expansion/filter behavior, Stage 2 prompts, and coerce marker sets.
They still share the same JSON Score schema, renderer, color catalogs, and
repair algorithms.  Language-specific behavior is therefore kept at the prompt,
expander, marker, and repair-input boundary.

The English path is tuned to preserve English-specific phrasing instead of
performing word-by-word translation.  Temporal and relational phrases such as
`before`, `after`, `again and again`, `as if`, and `at once`, along with
composition cues such as `diagonal`, `same beat`, `shifted`, reflection, fog,
road, sound, flock, and transparent-event language, are treated as cues for
abstract visual parameters and focal events.

Build 427 was checked with 30 Japanese/English equivalent prompt pairs rendered
with the same square canvas and default color catalog, without saving benchmark
history.  Expert review found the English path close to Japanese quality:
English tended to score slightly higher on color resonance, while Japanese
remained slightly stronger on constraint adherence and visual-event presence.
The remaining English risk is becoming too orderly and letting the event moment
sink into background structure.  The remaining Japanese risk is compressing
quiet poetic scenes into marks that are too small to carry a visible event.
Future tuning should strengthen focal-event size, contrast, and neighboring
reactions without increasing overall density.

---

## 3. Design Principles

1. Descriptions must remain human-readable.
2. Variation is part of the specification, not a bug. It exists at two scales: micro variation in line wobble, blur, grain, and texture; and macro variation in composition and placement resolved by the renderer.
3. Emotional adjectives are excluded from core vocabulary.
4. Physical, spatial, material, and motion words are preferred.
5. Coordinates are normalized ratios, not fixed pixels.
6. Output is still image SVG; the viewer moves, not the image.
7. The input language is constrained enough to support iteration.
8. Optional concrete worlds belong in plugins, not the core language.

DDL avoids words such as "beautifully" or "powerfully" in the core.  The system
should express such ideas through visible choices: number, placement, material,
line behavior, color, weight, and negative space.

---

## 4. Pipeline

### Stage 1: Interpretation

Stage 1 reads the user's natural-language description and produces normalized
DDL.  Its job is semantic.  It may choose a more visually effective
interpretation when the input is ambiguous, but it should remain within the
core vocabulary and preserve important user intent.

Stage 1 also carries tone, atmosphere, and context into the DDL when possible.
It should not simply extract nouns.  A quiet sentence, a ceremonial sentence,
and a turbulent sentence should lead to different density, focus, motion, and
material choices.

Every visible line, arc, or outline in normalized DDL names exactly one core
touch. Explicit material is preserved; otherwise Stage 1 chooses from texture
and context. A filled shape with no visible outline is not assigned a touch
mechanically. Burin and drypoint remain literal-input-only techniques. DDL must
not leave touchless phrases such as “thin black line” or “white horizontal
line.” Dynamic few-shot selection always includes at least one non-pen material
example.

Since v1.98 an empty Stage 1 output is treated as a failure rather than drawn
from nothing. A work drawn through a Stage 1 fallback path records an
`interpret_fallback` reason in history and is marked in the UI. Provider-side
failures are classified by HTTP status into model-gone, authentication,
rate-limit, and other kinds, reported with the failing stage and the provider's
original message (the legacy string-form error path is kept for compatibility).

### Stage 1.5: Deterministic Expansion Filter

Stage 1.5 sits between natural interpretation and strict JSON generation.  It
is deterministic and rule-guided.  It expands sparse DDL into richer visual
possibilities by selectively applying:

- mathematical and geometric laws
- spatial paths and non-central focus
- scene-tone palette choices
- music-derived structures such as counterpoint, canon, and harmonic ratios
- painting and material techniques such as perspective, chiaroscuro, drawing,
  pointillism, watercolor, oil-paint layering, patchwork, fresco, and sumi ink
- abstracted natural or material forms using the current primitive vocabulary

The filter must be selective.  It should not pack every technique into every
image.  It now favors composition-family selection and relation attachment over
fixed finished recipes.  The maintained composition families include diagonal
bands, vertical rhythm, horizontal strata, radial or concentric structures,
one-sided focus, central stillness, retreat to the edge, and dispersal.  Focus
points are represented as regions, not hard-coded coordinates.  Techniques such
as counterpoint, pointillist backgrounds, perspective lines, and canon-like
repetition should primarily become relations on existing instructions; separate
fixed auxiliary layers are used only when relation encoding cannot carry the
intent.

Any line or arc introduced by Stage 1.5 must also name one context-selected
touch. Composition-family rewrites must preserve expansion markers so the same
DDL is not expanded twice.

Since v1.98 history stores the input-side DDL (the user's text or the Stage 1
output, `ddl`) separately from the expanded DDL that Stage 2 consumes
(`expanded_ddl`); works saved before the split keep only the expanded form.
The explicit `focus` input added in v1.98 was retired in v2.0: the focus
defaults to a deterministic hash choice from the DDL text and moves only as a
variation axis (see below). The focus the expansion layer resolves is recorded
in the response and in `history.focus`.

Stage 1.5 is the application's own layer: it is deterministic, uses no LLM,
and the author does not intervene in its individual parameters — by design
principle, not by implementation convenience. The author's handles are the
input text, `vary_seed`, `tenkei`, and **variation** (強度/amplitude + seed).
The author writes, the application shakes, the author chooses.

Variation (v2.0, "hensou") shakes the expansion layer as a whole in one
explicit operation. Amplitude is discrete — small, medium, large. Which axes
move is decided by the seed; the same (amplitude, seed) always reproduces the
same expansion, and variation is never inherited along a lineage. The seven
official axis names are: focus, composition family, touch material, adopted
count, main/contrast colors, type swap, and type family. Axes are released by
weight: small moves one light axis (type swap, count); medium up to two
mid-weight axes (touch, focus, colors); large two to four including the heavy
axes (composition family, type family). Small never changes the picture's
skeleton (composition family, focus). An axis reported as moved is guaranteed
to produce a real difference in the expansion (visibility over axis count when
the description offers too few movable axes). Candidates come in ones or fours (same
amplitude, distinct server-issued seeds), each card showing what moved
(from → to in the official vocabulary). Variation is orthogonal to tenkei and
never exceeds its cap (under `none` only the focus axis moves). The four
existing refinement kinds keep their one-axis-chisel meaning; variation is a
distinct operation that shakes several axes at once, presented in the UI as
the fifth refinement radio. Terminology: variation (hensou) belongs to Stage 1.5 — a
deterministic variation of the score; yuragi (wobble) belongs to the renderer's
nondeterministic performance. The replay contract (same Score + same seed =
same work) is untouched, since variation happens before the Score exists and
is not an rh2 ingredient.

### Stage 2: Structuring

Stage 2 converts normalized and expanded DDL into JSON Score.  Its job is
structural, not poetic.  It must preserve DDL elements such as color, material,
movement, arrangement path, rotation, and canvas.  If an element exists in DDL,
Stage 2 should either encode it or fail clearly.

Adjectives, motion words, and texture words modify the primitive that the DDL
already names.  Stage 2 must not add unrequested support lines, support shapes,
or differently colored instructions merely because the DDL says "trembling",
"swaying", "blurring", "thick", "thin", or a similar modifier.  The server also
applies a narrow deterministic contract guard for single-primitive DDL with
motion or texture modifiers: it keeps only instructions matching the requested
primitive and explicit color, drops unrequested auxiliary marks, and applies
the missing motion as variation on the requested primitive when possible.  The
guard is intentionally not applied to multi-motif DDL.

When Stage 2 cannot return usable instructions because of timeout, empty output,
or transient model failure, the server may produce a deterministic fallback
Score.  This fallback is still expected to preserve the DDL's visible essentials:
quantity, placement path, material words, palette tone, and enough shape variety
to remain reviewable.

### Renderer: Performance

The renderer converts JSON Score into SVG.  It owns visual realization:

- coordinate normalization
- material-specific line and contour treatment
- motion and wobble realization
- primitive expansion
- SVG filters and texture effects
- canvas aspect handling

The renderer is allowed to produce controlled variation, but it must preserve
the JSON Score's intent.  Renderer performance has two scales: micro variation
(line wobble, blur, grain, material texture) and macro variation (seeded
resolution of regions and relations).  Each render may carry a `render_seed`;
providing the same seed makes replay reproducible while leaving the canonical
Score stable.

Since v1.99 variation is performed not only on lines but also on arcs and
closed shapes (circle, ellipse, triangle, square, polygon). The gate mirrors
the line gate: quality in {perlin, wave, white} and dimensions intersecting
{position_x, position_y, radius} (radius being a shape's natural axis). Closed
contours use seam-continuous periodic noise, polygonal shapes perform each edge
with fixed corners, and arcs keep both endpoints exactly fixed so the touching
contact contract holds. The pink (blur) and quality=none paths are unchanged.
Because the same Score and seed now render differently for affected works, the
render engine version was bumped to 5; saved SVGs are untouched.

v2.0.5 gave wave-quality variation a performance-seed-derived phase (it was a
fixed-phase sine before, so the waveform never changed across seeds). The phase
is derived deterministically from the seed; closure of closed contours at
integer frequencies, exact arc endpoints, and fixed polygon corners are all
preserved. Material outlines (pencil / crayon / chalk contours and specks) now
also follow the performance seed. With no performance seed the output stays
byte-identical to the previous behavior. Because the same Score and seed render
differently, the render engine version was bumped to 6.

v2.1.0 replaced absolute pixel values throughout rendering with proportional
systems. The amplitude vocabulary (fine / medium / broad) changed meaning from
absolute pixels on a 1000px canvas (7 / 12 / 30px) to **ratios of a shape's
representative size** (0.025 / 0.08 / 0.18): radius for circle / polygon / arc,
geometric mean of the radii for ellipse, half the short side for square /
triangle / cloudform, and line length for line. Small shapes now wobble finely
and large shapes broadly. Bleed (pink) stdDeviation was ratioed the same way
(0.009 / 0.03 / 0.07). Contour segment counts and stroke sample counts changed
from fixed values (80 / 49) to length-proportional with clamps. The material
layer (stroke widths, dasharrays, texture filters, material outlines, specks)
and the display filter became `canvas.unit`-relative, matching previous output
at `unit=1000` except for perimeter-proportional speck counts and
length-proportional stroke samples. Author calibration also raised material
outline and speck strength via floors (intensity level s1: floors on outline
offset / opacity and speck opacity / count; texture filters unchanged).
Material outlines now carry `class="material-outline"` so they can be
mechanically distinguished from primary lines. Because the same Score and seed
render differently, the render engine version was bumped to 7.

v2.2.0 draws closed-shape contours (circle / ellipse / square / triangle /
polygon) with hand strokes from the stroke engine. `synthesize_along` extends
stroke synthesis to arbitrary centerlines (same tool grammar as lines, only the
target path changes; the integrator feed-forwards the intended step and leaves
only the residual to the spring, eliminating radial distortion on curved
paths). The contour is drawn as a filled band of outer and inner banks
(`class="contour-stroke-v1"`, fill-rule evenodd). Corners are pinned to their
ideal positions as brush seams; cornerless closed contours close their seam
with a linear ramp. All hand-drawn weights participate; rotring keeps its
geometric contour. The band's centerline is the contour after variation is
performed, and material outlines and specks coexist with the band. Dashed and
dotted styles keep a thinned geometric contour since the line style itself is
the description. Body elements stay geometric (with `stroke="none"` for solid
style), so bbox and touching contracts are unchanged. Line and arc output is
byte-identical to v2.1 (arc stroke-ization awaits a redesign of the touching
test's arc extractor in a follow-up contract). Because the same Score and seed
render differently, the render engine version was bumped to 8.

v2.3.0 replaces the area fill of closed shapes with **stroke fill — the
material's brushwork filling the interior** — and restores the semantics of
`filled` (`True` = fill the interior with material strokes / `False` = contour
only; previously closed shapes were always filled regardless of `filled`, a
dead field). Fill strokes are built by intersecting scanlines with the closed
contour and passing each interior span — one span = one brush stroke — through
`synthesize_along` (no clipPath needed; concave cloudforms are handled as
intersection pairs, and endpoints are pulled half a stroke-width inside the
intersections so edges align with the contour). The group carries
`class="fill-stroke-v1"`. The scan angle derives from the render seed (uniform
over 0–180°) so it differs per shape; spacing is `max(stroke width × 1.5,
canvas.unit × 0.012)` with ±12% jitter per scanline. Full coverage is not the
goal — paper grain (gaps) remains. Rotring keeps area fill (`True` = solid
fill / `False` = contour only), and tiny shapes with fewer than three
scanlines degrade to area fill. When `surface` is specified the material fill
is suppressed (fill = the material's default way of covering; `surface` = an
explicit printmaking expression). Surface hatch / crosshatch lines also moved
from geometric lines to brushwork bands (`class="surface-stroke-v1"`;
centerline, angle, spacing, and count unchanged; rotring keeps geometric
lines). Variations that are not performed are now excluded from the seed key,
so the presence of an inactive variation no longer changes the rendered bytes
(per-primitive inactivity rules; for cloudform only `dimensions` is inactive
since its contour generator always consumes quality / amplitude / frequency).
Because the same Score and seed render differently, the render engine version
was bumped to 9.

v2.3.1 performs arcs as hand-drawn stroke bands too (`class="arc-stroke-v1"`),
closing the last exclusion left by v2.2.0. All hand-drawn weights participate;
rotring and non-hand-drawn weights keep the geometric arc. The band's
centerline is the arc after variation is performed, with both endpoints pinned
to their intended values. **The geometric arc remains as an invisible intent
element (`stroke="none"`)**: the touching (contact) contract is verified by
reading this intent arc back from the rendered SVG, so the arc extractor needs
no change (the band is a filled `M..L..Z` polygon with no arc command, so
nothing is double-counted). **Contact ends stay tapered**: the stroke
synthesis envelope converges to zero at both ends, and since the intent arc
guarantees the contact contract by coordinates, the band may fade out at
contact points just like free ends (leaf tips and bases fade softly). Dashed
and dotted styles make the intent arc itself visible as a thin dashed / dotted
line (the line style is the description, symmetric with lines and closed
shapes). Drypoint emits burr along the performed centerline, and material
outlines and specks coexist with the band. Because the same Score and seed
render differently, the render engine version was bumped to 10.

For literal `layout="grid"` tiling, performance composes three controlled layers: a deterministic seed-derived within-cell position jitter, the existing per-element `variation` with a distinct phase for every mark, and the existing material behavior of weights such as pencil, brush, and chalk. The same Score and render seed remain bit-identical. Because full-field repetition is explicit author intent, grid bypasses scatter-oriented bias, fade, clustering, preserved-space injection, and representative count reduction.

inku exposes this as the first half of two-step regeneration: **another
performance** rerenders the same JSON Score with a new explicit performance
seed. It does not call an LLM and does not change the interpretation or Score.

Human, face, animal, and group motifs are not drawn as literal objects.  Stage 2
and the coercion layer convert them into `Score.presence`: presence kind,
intensity, center of gravity, symmetry, gaze pressure, group behavior, and
contour density.  The renderer realizes presence as faint arcs, edge-biased
focus, asymmetric spacing, and contour-density pressure.  It avoids fixed
silhouettes such as stick figures, head/body pairs, wing/tail marks, or rings
of identical ellipses.

The primitive vocabulary includes `polygon` for polygonal language.  Individual
pentagon or hexagon primitives are not added; polygonal intent is represented
with `polygon` and `sides=5-8`.  Motion energy is handled by trajectory,
rotation, diagonal placement, wave paths, and asymmetry rather than simply
increasing count or density.

The score coercion layer also contains rendering-core quality repairs used by
the current default engine.  These repairs are deliberately generic rather than
prompt-specific, and must not become a visible system fingerprint.  Quiet, mist, memory, shadow, and neon-blur contexts apply
density and negative-space governors so vertical lines, particles, large filled
shapes, or background surfaces do not overwhelm the work.  Motion words that
arrive without an effective trajectory can receive a small directional motion
floor, and requested colors that appear only in a color cycle may be promoted to
a primary stroke so the color intent remains visible.  Visual events are
distributed across available vocabulary: when a scene lacks angular anchors,
the repair may add a small `polygon`; when repeated lines dominate, it shapes
the existing line group with syncopated spacing, preserved negative space,
directional fading, and slight endpoint gaps instead of increasing density.

Repair parts such as focal reactions, angular pulses, vanishing traces, and
rhythm offsets are measured by marker phrase in CLI analysis. Their firing rate
is monitored, but no new governor or floor may force them into every sample.
When such a part is necessary, fixed coordinates and fixed shape parameters are
resolved from the event anchor and input hash so repeated works do not reveal a
constant inserted component. Focal adjacent reactions are limited to isolated
visual events where omitting the reaction would weaken the subject.

The rendering core is exposed internally through a RenderEngine contract.  A
render engine receives JSON Score, render options, and server-owned color
metadata, then returns SVG plus render metadata.  The current `renderer.py`
implementation is wrapped as the static `default` engine.  inku does not load
arbitrary external engine code yet; this boundary exists so future engine packs
can be introduced without changing the API, history, JSON tab, CLI, or
benchmark metadata contracts.

SVG export has three profiles:

- `display`: the default server-rendered SVG used for web display, history,
  PNG generation, and artifact rebuilds.
- `editable`: generated on demand from JSON Score and server-owned color catalog
  metadata, with stable ASCII IDs and layer-like groups for Illustrator and
  Affinity editing.
- `compat`: generated on demand from JSON Score and server-owned color catalog
  metadata, avoiding filters and clip paths for broader SVG compatibility.

The DB stores only the `display` SVG in `history.svg`.  Editable and compatible
SVG files are regenerated at download time rather than stored as additional DB
payloads.

---

## 5. Core Vocabulary

The vocabulary dictionary is called Saijiki, following the haiku term for a
seasonal word dictionary.  In inku, Saijiki is consulted rather than kept open
at all times.

Since v1.92 the vocabulary has a single source of truth: the saijiki table on the server (`saijiki.py`). The Stage 1 prompt vocabulary block, the plugin closure markers, the Stage 2 relation phrases, the web Saijiki display (`GET /api/saijiki`), and reference §1 are all derived from that table. The machine-generated reference dump (`GET /api/reference` / `inku-cli reference`) always shows the current values; the table below is the v1.92 snapshot.

| English | Japanese | Vocabulary |
| --- | --- | --- |
| forms | かたち | circle, ellipse, triangle, square, line, arc, cloudform |
| touches | てざわり | pencil, pen (default), rotring, crayon, chalk, fine-brush, thick-brush, burin, drypoint |
| continuity | つらなり | solid (default), dashed, dotted, dash-dot |
| motions | うごき | place, line-up, draw, scatter, fill, tile |
| movements | ゆらぎ | fine, large, slowly, quickly, swaying, undulating, trembling, blurring |
| relations | あいだ | along, not touching, cutting, between, touching — with fixed phrases such as `along the previous line` and `touching the previous arc at both ends` |
| places | ばしょ | top, bottom, center, left-edge, right-edge, top-edge, bottom-edge, middle, corner |
| angles | かたむき | horizontal, vertical, diagonal, rising, falling, rotated |
| proportions | わりあい | tall, wide, full-width, half-width, semicircle, waxing, waning, crescent |
| colors | いろ | white, black (default), blue, red, green, gray |

In v1.92 the words 描く (ja draw) and 髪 / hair were pruned from the vocabulary by the author's decision; the Score `Weight` enum keeps `hair` so that saved works replay unchanged.

`Random` is not forbidden as an author word.  The restriction applies to internal normalized DDL and JSON Score: unordered placement must be interpreted into observable placement such as dotted across the whole canvas, scattered, varied, top-to-bottom, or along a trace.

The core color vocabulary is the six abstract colors that authors can write: white, black, blue, red, green, and gray. Color catalogs are server-owned metadata that change how those six colors are resolved at render time; they are not vocabulary extensions. Yellow and orange appear in some catalog palettes and can be reached through palette resolution or `color_hint`, but they are not added to the core color vocabulary.

Colors in JSON Score are abstract color names.  Rendering resolves them through
the selected color catalog.  The server is the source of truth for color
catalog definitions and exposes them through `/api/color-catalogs`; clients
select a `catalog_id` rather than owning their own catalog tables.  When user
instructions include color nuance, the system may preserve `color_hint` so
Stage 2 and rendering can resolve the best catalog color without losing intent.
The default catalog is a neutral baseline, not a cultural default.  Additional
catalog ids use material-, light-, and technique-based names to avoid presenting
a country, ethnicity, food, festival, empire, or tourism marker as a complete
palette identity: `ink_season`, `fresco_study`, `open_air_light`,
`ink_porcelain`, `cool_material`, `dye_earth`, `desert_mineral`,
`vivid_material`, `weathered_heritage`, and `sea_stone`.
Catalog `map` values must preserve the meaning of the abstract colors
`white / black / blue / red / green / gray`; stronger identity colors belong in
`palette` rather than replacing structural colors.  The Build 265 review leaves
`open_air_light`, `dye_earth`, and `desert_mineral` as known tuning targets:
their dark backgrounds, high-chroma accents, or paper/sand tones can dominate
quiet prompts, so future tuning should adjust core brightness and saturation
instead of branching into prompt-specific exceptions.
Build 266 lightens those three catalogs' core colors to reduce background and
dark-color dominance.  Catalog `sub` remains the English UI description, while
`sub_ja` carries the Japanese UI description.  Palette color names use `name` as
the English canonical label and may include `name_ja`; the Japanese UI displays
those entries as `English（日本語）`, while the English UI displays `name` only.

Render JSON produced by the server records the concrete render context.  Paint,
compose, the JSON tab, and saved artifact JSON include the resolved
`stage1_model` / `stage2_model` that were actually used, plus
`render_build_number`, `render_color_profile`, `render_engine_id`,
`render_engine_version`, `render_canvas_aspect`, `render_hash`,
`render_hash_short`, `render_color_catalog_id`, `render_color_catalog_name`,
`render_color_catalog_sub`, `render_color_map`,
`instruction_lang_requested`, `instruction_lang_resolved`, `ui_lang`, and `render_seed`, where
abstract colors and `palette:<name>` entries are expanded to the exact
`#RRGGBB` codes used for SVG rendering.  The current engine metadata is
`render_engine_id: "default"` and
`render_engine_version: "1"`.  The full catalog `map` / `swatches` / `palette`
snapshot is not duplicated in render JSON because `render_color_map` is the
concrete color record needed for replay and audit.
Starting in v1.60, `render_hash` is an edition identifier in `rh2:<sha256>` form. It is computed from the saved canonical JSON Score plus `render_seed`, `vary_seed`, `render_build_number`, `render_color_catalog_id`, and render-engine metadata. SVG text, input text, normalized DDL, and raw LLM responses are not part of the hash payload. Existing 64-character history hashes remain legacy display values; they are not rewritten by migration. `render_hash_short` is the four-character uppercase suffix used for UI and CLI references.
`score.canvas` remains the score-level canvas instruction, while
`render_canvas_aspect` records the canvas aspect actually used for this rendered
artifact.  In normal server-generated output they match, but both are retained
so render metadata remains visible even when old records or imported Scores are
inspected.
`render_canvas_aspect_id` is the explicit canvas aspect identifier for new
metadata, and `render_canvas_aspect_ratio` records the actual rendered
width/height ratio as a number.  `render_canvas_aspect` remains for
compatibility; old records can be backfilled in responses by deriving the new id
and ratio from it.

---

## 6. JSON Score

JSON Score is the machine-readable score produced by Stage 2.  It is not the
final artwork; it is the structure that the renderer performs.

Important score concepts:

- `canvas`: selected canvas aspect identifier, such as `square` or `golden`
- `instructions`: ordered drawing instructions
- primitive fields: line, circle, ellipse, triangle, square, polygon, arc, cloudform, and related process data
- `weight`: material / tool quality
- `variation`: visible wobble, blur, tremble, or motion behavior
- `arrangement`: count, distribution, paths, grouping, density, fade, and color cycles
- `rotation`: shape-level or group-level orientation
- `color_hint`: optional hint used when resolving catalog colors
- `at.region`: optional normalized placement region `[x0,y0,x1,y1]` resolved by the renderer seed
- `relation`: optional observable relation to the previous instruction: `along`, `not_touching`, `cutting`, `between`, or `touching`; touching currently requires `contact: both_ends`

Large repetitions should prefer group behavior over literal overload.  Dense
clusters use `arrangement.density`, `cluster_count`, `fade`, and
`preserve_space` so that negative space remains part of the composition.

Current scene-tone palette behavior uses abstract colors only:

- spring, flowers, buds, and warm light lean toward red / green / white
- water, night, moon, rain, mist, and cold air lean toward blue / white / gray
- forest, leaves, grass, moss, and fragrance lean toward green / white / gray

Nuance that cannot be represented by the six abstract colors is retained in
`color_hint` for catalog-based rendering.

Relations are sequential. `along`, `not_touching`, `cutting`, and `touching` refer to the immediately previous instruction; `between` refers to the previous two. There are no arbitrary ids, forward references, or repair governors for relations. Invalid relations are dropped by validation or coercion with a recorded warning, and the instruction is rendered normally without the relation. The coerce layer may remove invalid relations but must not add new ones. JSON Score `relation` is reserved for explicit previous-object phrases in normalized DDL: `前の線に沿って` / `along the previous line`, `前の形に触れない` / `not touching the previous shape`, `前の線を切る` / `cutting the previous line`, `前の二つの間に` / `between the previous two`, and the explicit contact phrases `前の線に触れる` / `touching the previous line` or `前の弧に両端で触れる` / `touching the previous arc at both ends`. Touching is never added spontaneously. Natural-language proximity, rhythm, ahead/behind, near, and far are represented with position, path, rotation, and spacing instead of relation.

An instruction that carries both a region (`at`) and a relation (such as plugin-member double arcs) is placed by its region first and then resolved by its relation (v1.94); for touching, the previous instruction’s endpoints decide the final position, so the region acts as chain-start information. Unresolvable relations discovered only at performance time (degenerate geometry, grid layouts, endpointless priors) are likewise dropped with a recorded warning.

For `touching` with `contact: both_ends`, both the current and previous instruction must be a line or arc. The renderer takes the previous instruction’s performed endpoints and pins the current endpoints to them. For an arc with chord length `c` and signed performed sagitta `b`, it reconstructs the minor arc with `r=c²/(8|b|)+|b|/2`; its center lies opposite the bulge, and a previous arc makes the new arc bulge to the opposite side by default. Minor-arc winding uses the same shared convention as SVG arc rendering. Variation and stroke performance keep both endpoints fixed and act only on the interior. Closed forms and endpointless targets are rejected drop-only with a recorded warning. Degenerate performed geometry also drops the relation at render time; no coordinate repair or governor is introduced.

Endpoint, tangent, and sagitta verification is performed in canvas coordinates after composing every drawing transform, including rotations on ancestor groups.

This fifth relation trades the former uniform family of loose distance constraints for one exact endpoint constraint. In return, it can write closed organic contours such as a two-arc leaf without freezing performed coordinates into the Score. The deferred `continuing` candidate remains outside this version; it is reconsidered only after cloudform surface/ground expression improves.

The system treats the DB history record as the source of truth.  SVG, JSON
files, PNG files, and other artifacts are derived outputs.

---

## Cloudform Design (v1.89.1)

Cloudform is the first closed form whose visible identity is decided by the performance rather than by a geometric definition. The Score stores only process parameters such as center, size, variation, touch, surface, relation, and placement. It never stores contour coordinates. The renderer derives the contour from the Score, instruction index, and performance seed, so the same seed reproduces the same contour while another performance produces another contour.

Cloudform does not imitate a meteorological cloud. The name refers to a family of irregular curves: a form with a grammar of irregularity, related to cloud rulers, yamato-e haze, suhama paper forms, and suminagashi. It extends the principle that the description persists and the rendering is a one-time performance from placement and touch into form itself.

### Contour performance

The renderer combines two deterministic periodic processes:

1. A seamless multi-octave 1/f signal modulates a closed polar radius. Existing variation words distribute energy across low lobes or fine high-frequency detail.
2. A second periodic signal runs along the base curve arc length and creates bays and waists. Its displacement is clamped by local radius and curvature. A strictly positive single-valued polar radius provides the structural self-intersection guarantee; this is geometry safety, not an aesthetic governor.

The contour uses the shared tool grammar, so pencil and rotring produce different edge qualities. Existing surface values such as wash, stipple, hatch, and aquatint fill its interior. Carve mode can cut an irregular light from a dark ground. Output follows the renderer point budget and closed Bezier fitting rules.

### Composition with existing vocabulary

Cloudform introduces no modifier category:

- variation controls octave distribution and contour behavior;
- proportion controls aspect, including tall, wide, and full-width haze-like bands;
- touch controls edge quality;
- surface and color control the interior;
- relations resolve against the performed contour and its bounding box;
- place, motion, and arrangement position it, and arranged instances receive distinct contours.

### Selection boundary

Stage 1 may select cloudform only when the author explicitly writes cloudform, or when the instructed subject itself is amorphous, such as cloud, smoke, haze, stain, island silhouette, or puddle. It is never a fallback for an unknown or unclear object. Unknown objects continue to be approximated with existing defined primitives. Stage 1.5 and coerce cannot inject cloudform. Stage 2 only transcribes the normalized form into primitive cloudform with center and size; it never asks an LLM for contour coordinates or control points.

Cloudform frequency and context are recorded by the motif ledger as a diagnostic mirror only. They do not create a governor, floor, generation gate, or automatic preference.

### Determinism and accounting

Contour synthesis uses the existing performance identity and does not change rh2 inputs. The Score remains the score and the contour remains a performed value.

What this version gains is a form without a fixed definition: variation becomes the form itself, and the contour can invite projection by the viewer. What it loses is the previous uniformity in which every core form was geometrically definable. The strict selection boundary makes it harder for cloudform to become an escape hatch for uncertain interpretation.

## 7. Canvas Model

Coordinates remain normalized from `0.0` to `1.0`. Canvas aspect changes do not
change DDL coordinates. Changing the aspect clears the rendered display and shows
a placeholder for the new aspect, but retains the displayed work as lineage context.
The next saved work is recorded as its child with `canvas_aspect_change`.

The built-in `canvas-aspect` plugin currently supports:

| Category | ID | Ratio | Purpose |
| --- | --- | --- | --- |
| Basic | `square` | 1:1 | default ordered canvas |
| Standard | `golden` | 1.618:1 | golden-ratio rectangle |
| Modern | `a4` | 1:1.414 | root rectangle / print standard |
| Modern | `b4` | 1:1.414 | root rectangle / print standard |
| Classic JP | `pillar` | 1:5 | Japanese pillar-picture format |
| Ukiyoe | `oban` | 2:3 | ukiyo-e oban proportion |
| Cinema | `wide` | 2.35:1 | cinematic panorama |
| Classic JP | `byobu` | 2.2:1 | Japanese folding screen format based on one half of a six-panel pair |
| Mobile | `vertical` | 9:16 | smartphone vertical format |

The selected aspect is stored per user in plugin storage and passed to
`/api/paint`, `/api/compose`, and history saving.  It is also written into
`Score.canvas`, so history and JSON display show which aspect produced a work.

The renderer uses the selected aspect to determine SVG `width`, `height`, and
`viewBox`.  Circle and arc radii are based on the shorter side to avoid
accidental stretching.

---

## 8. Plugin Model

Vocabulary plugins are UTF-8 declarative documents, not executable code. One `.inku-plugin.md` file contains a front-matter manifest and word entries. The manifest requires `namespace`, `name`, semantic `version`, `authors`, `languages`, `license`, and Japanese/English descriptions. Each entry provides namespaced identity, Japanese/English surfaces and `fires_on` nouns, optional bilingual Saijiki notes, and equivalent bilingual expansion templates. Arbitrary code, URLs, and file references are forbidden.

The pipeline order is **Stage 1 output -> plugin expansion -> core-only DDL -> Stage 1.5 -> Stage 2**. Templates may use core normalized DDL plus bounded expansion forms: deterministic `N to M` repetition (with unit-preserving singulars, and Build 591 multi-word English units such as `leaf forms`, `blades`, `cloudforms`, `spots`, `arcs`); a `member name: definition` local composite inlined at each member (Build 591; undefined references are rejected at load); `note:` comment lines that carry no expansion (Build 591); an `anchor` whose region determines separate member bands, including a Build 591 `anchor ... at N to M spots` nested repetition (spots x per-anchor members, depth two, each spot its own band); and symbolic `{region: ...}` translation, whose canonical key list is published by reference §3 and includes a `bottom band`, with an `upper-left to lower-right diagonal band` resolved as a computation (member sub-regions along a descending diagonal) rather than a rectangle. The same input chooses the same count, member regions, and rotations.

Core DDL with explicit numeric regions after expansion is already composition-resolved. Stage 1.5 still performs normalization but must not append a separate finished-work recipe or auxiliary shapes, and Stage 2 must not retain support instructions beyond the explicit region count. This cap applies to Score instruction count; it does not freeze `arrangement.count` inside each instruction. Visible multiplicity can therefore remain model-dependent: for the minimal twin-arcs fixture, Mistral stays at two arcs while Qwen may repeat the two instructions into more than two visible arcs. Build 590 accepts this as a known limitation.

The load-time validator rejects the whole document with explicit reasons for missing manifest fields, reserved namespace or qualified-word collisions, recursion or non-core plugin references, more than 48 instructions per word, repeated members stamped at fixed coordinates, and URL/file references. This is syntax validation before execution, not an artwork governor. Runtime closure or budget failure drops the expansion without repair, records a warning, and leaves a normal core approximation. Build 591 adds unknown region keys and undefined member references to the load-time rejections, exempts comment lines from the closure check, and removes the silent center fallback (an unknown key at runtime falls back to the default band with a recorded warning). Since v1.92 the closure marker table (shapes, verbs, relations, and the Saijiki modifier categories) is derived from the saijiki table; reference §1 and §3 always show the current values.

An explicit qualified term always fires. Stage 1 may resolve a `fires_on` noun only when it is the stated subject; it must not extend firing to metaphors, unclear subjects, or unknown objects. When several `fires_on` phrases match at the same position, only the longest wins (Build 591, removing substring mis-fires — e.g. the input "枯草" no longer also fires the "草" undergrowth word); phrases at different positions still fire independently. Only the loaded surface/trigger vocabulary is injected into Stage 1, never template bodies. Stage 1.5 and coerce cannot introduce plugin words. Input-term-to-qualified-term provenance is returned by the API and stored in ordinary derivation metadata, while plugin documents and dependencies remain absent from Score, canonical DB artwork data, and rh2.

`server/plugins/` is signature-checked so add/delete changes appear without a restart; management APIs and `inku-cli plugin list / validate / reload` expose status, rejection reasons, validation, and forced reload. Settings shows loaded/rejected documents, while Saijiki distinguishes qualified plugin words and bilingual notes. Removing a plugin must not change replay SVG or rh2 for a saved work because replay uses the already saved core Score and seeds.

The built-in `canvas-aspect` system plugin remains separate and uses its existing hook and per-user plugin storage. Vocabulary plugin documents do not gain that code-level hook.

---

## 8.6 Short-Form Guide

The writing surface carries only a non-blocking length hint. Japanese input uses roughly 31 characters as a tanka-like guide; English input uses roughly 12 words. The UI must not block longer text or display evaluative copy about length. It may show only a numeric counter and a subtle density change when the guide is exceeded, so the form is present without scolding the writer.

## 9. Web Application

The web app is the current reference interface. v1.72 makes refinement and model comparison first-class authoring surfaces. The `Refine` tab offers touch, layout, reading, color-catalog, and variation (§12.13) changes as a radio-style choice: exactly one intervention may be selected per refinement step, so each lineage edge remains attributable to one cause. Selecting variation reveals an amplitude choice (small/medium/large, default medium) directly under its radio; one candidate uses one fresh server-issued seed and four candidates use four, with no separate variation section or button. The chosen refine element is remembered in the browser. Reading is one upstream intervention whose downstream layout and touch are regenerated. One or four candidates vary only the selected element, use the same selection-and-save workflow, and are displayed in a two-column grid (a single candidate fills the full width) sized to fit within the dialog. Saving selected refinement candidates keeps them in ordinary history without automatically starring them; the save control distinguishes unsaved, saving, and saved states, and a saved candidate cannot be saved again. Candidate generation disables other generation and drawing actions; after three seconds it exposes the shared Stop control, backed by request abortion. Progress copy names the work actually being performed. Reading candidates expose normalized DDL on image hover. Render and vary seeds are independent JavaScript-safe random integers carried from initial generation through candidates, history, and replay. Display rendering makes touch-seed changes visible without changing canonical composition coordinates. A color-catalog refinement keeps DDL, Score, canvas, layout seed, and render seed fixed while applying a catalog other than the parent's; four options use distinct catalogs when possible. All non-color refinements inherit the displayed parent work's effective catalog and canvas rather than the next-drawing controls. Color edges use `catalog_change` and record the before/after catalog IDs. The caption visibility choice is persisted per user. Previous/next navigation preserves the active Adjust or Model comparison subview inside Refine and changes only its target work. Adjustment candidates are temporary state owned by their source work: explicitly selecting a work from history, lineage, nearby works, or navigation, or starting a new generation or DDL render, clears them. Merely switching between Adjust and Model comparison does not. A target change also resets the target-owned model-comparison results, reading diff, replay error, intermediate-lineage notice, and lineage fetch state. Any in-flight model comparison is aborted, and only the latest lineage request may update the view.

The web UI keeps direct operational labels while the specification retains the musical metaphor: performance is shown as touch, composition as layout, and interpretation as reading. Model comparison lives beside `Adjust` as a subview inside the Canvas-side `Refine` tab and shows no judge values. It provides three modes: `Shared Stage 1/2`, `Fixed Stage 1 + compare Stage 2`, and `Compare Stage 1 + fixed Stage 2`. Shared mode uses each selected model for both stages. Fixed modes select one model for the fixed stage and up to four for the compared stage. Only the exact Stage 1/2 combination used by the target work is prohibited; a model used by the target remains selectable when the fixed-stage pairing makes the combination different. A floating tooltip explains prohibited choices. Models are always selected explicitly, and no unselected fallback model is run. Changing the target clears stale comparison results and aborts any comparison still in flight. Saved comparison results record the actual Stage 1 and Stage 2 models and may be adopted or starred into history.

Each Lineage-card artwork menu offers, under the heading "Edit this artwork" and in this order: drawing elements, description, DDL, model, language, autonomous AI refinement, and moving the work to trash (item labels are shortened to the target noun). The dialogs opened by the three comparison actions are titled "Edit drawing elements", "Edit model", and "Edit language". Description and DDL editing open modal dialogs initialized from the selected work. Drawing saves a `description_edit` or `ddl_edit` child, returns to Lineage, and focuses the newest child together with its ancestors. The three comparison actions target the selected card and open the corresponding existing Refine subview in a modal dialog; they do not duplicate comparison logic. Closing the dialog returns to the originating Lineage view, while the regular top-level Refine tab retains its panel layout. The former Manual Refine modal has no menu entry. Trash is visually separated from comparison actions with an explicit high-contrast result label.

Major UI areas:

- App rail: compact navigation with an explicit expand/collapse toggle, user
  menu, profile, settings, language and theme controls
- Input panel: single drawing, batch drawing, and demo modes
- DDL editor: editable normalized DDL embedded in the single drawing flow, with
  Saijiki word highlighting and an expanded dialog editor
- Canvas panel: SVG display, zoom, pan, output tabs, status bar, export buttons
- History strip: recent works, hover metadata, star markers, pagination
- History manager: larger history view, trash, restore, permanent delete, star filter
- Settings modal: models, color catalogs, DB status, plugin status, export
  templates, users, theme

The status bar displays the current render context:

- Stage 1 model
- Stage 2 model
- color catalog
- canvas aspect
- star state for the current history item
- SVG / PNG export controls

For history display, model, catalog, and canvas values come from the history
item when available.  For active editing, they come from the current selections.
The canvas panel header also shows the selected work's color catalog, canvas,
and creation time.  The color catalog button in the input panel displays the
currently selected catalog name and truncates long names with an ellipsis.

The settings modal's "other" tab includes history-selection behavior controls.
Users can choose independently whether selecting a history item updates the UI's
current canvas aspect and color catalog to the history item's values, or keeps
the current UI selections.  This setting affects only the UI selection state;
the saved history SVG is displayed as stored and is not re-rendered.

The canvas panel also supports viewing-oriented controls.  A fullscreen icon in
the drawing tab opens presentation mode, which maximizes the current SVG and
shows a compact control bar for history navigation, latest item, star toggle,
instruction caption toggle, and close.  Escape closes presentation mode.  A
caption icon in the drawing tab toggles an instruction caption.  In normal
canvas view, the caption uses 10% left and right margins relative to the drawing
tab and is clipped inside that tab.  In presentation mode, the caption uses 10%
left and right margins relative to the window.  Captions display the original
user-facing instruction text, not the internally augmented Stage 1 prompt; this
keeps emotion-hint or system prompt material out of presentation captions.

The history DB remains the source of truth for renders saved by the web UI,
`inku-cli`, Android headless CLI, and other API clients.  The web UI periodically
refreshes the latest normal history page while the signed-in user is viewing the
latest non-filtered history.  It also refreshes when the browser window regains
focus or a hidden tab becomes visible.  This allows CLI-saved renders to appear
in the history strip without a manual reload, while preserving the currently
selected history item when it is still present.  The UI does not auto-replace
history while the user is viewing starred-only history, search results, older
history pages, or while a history request is already in flight.

PNG export options are managed as per-user templates in the settings modal's
export tab.  Each template has a name, description, and y-axis height in pixels.
The default templates are `PNG 1024px` and `PNG 2048px`.  The status bar PNG
menu is generated from these templates, and export width is computed from the
current canvas aspect ratio.

---

## 10. Modes

### Single Drawing

The user writes one instruction and runs the full pipeline.  The resulting DDL
can be edited directly.  Replaying from DDL skips Stage 1 and calls Stage 2 /
renderer again.

The normalized DDL appears as an interpretation box under the single drawing
input.  The box supports two editing paths:

- direct inline editing in the highlighted interpretation box
- the `Saijiki` toggle, placed on the canvas toolbar since v1.98, opens the
  side drawer as a browse-only vocabulary reference: clicking a word chip
  shows its preview instead of inserting it
- the `DDL editing` button opens a larger dialog with line numbers, a
  two-column Saijiki vocabulary panel, and a short DDL syntax guide; since
  v1.98 word insertion happens only through this dialog's inline Saijiki,
  which also lists loaded plugin vocabulary
- the `auto repair` checkbox controls whether the server applies deterministic
  JSON Score repair after Stage 2. It is enabled by default. When disabled,
  Stage 2 output is rendered without the broader `coerce_score()` repair pass,
  while hard contract guards may still remove instructions that violate the
  requested primitive/color contract.

The same `Draw from DDL` action is also available below the interpretation box
for quick replay without opening the dialog.  The single drawing flow also
includes v1.70 post-selection controls: a candidate grid for multiple
render/composition/interpretation variants, optional inclusion of an
interpretation candidate, multi-select saving, and an explicit `another
interpretation` action that shows the normalized-DDL diff.  Candidate metadata
shows the render, vary, and interpretation seeds where applicable.  The dialog itself does not start
drawing, so drawing actions remain concentrated in the main single-drawing
panel.

If the user edits DDL directly and then presses the normal `draw` button, inku
warns that the DDL edit will be lost.  The choices are `cancel`, `OK`, and
`draw from DDL`.  `OK` reruns Stage 1 from the natural-language prompt, while
`draw from DDL` preserves the edited DDL and runs Stage 2 / rendering only.
The natural-language prompt is not reinterpreted by `Draw from DDL`.

The drawing tab also exposes two explicit regeneration actions. **Another
performance** keeps the same Score and asks only the renderer for a new
performance seed. **Another composition** keeps the user-facing text as the
identity of the work but increments a `vary_seed` for Stage 1.5 selection, so
composition family, focus, and technique candidates can change without making
the default path nondeterministic. The same text plus the same `vary_seed` and
`render_seed` is reproducible from metadata.

Since v1.98 single drawing calls `POST /api/paint/stream` (NDJSON): a `stage1`
event is emitted as soon as interpretation completes (normalized DDL, models
used, token counts, elapsed time, fallback flag) so the UI can show the
interpretation while Stage 2 and rendering continue, and the final `done` event
carries the same `PaintResponse` as before. `POST /api/paint` remains a wrapper
over the same logic with an unchanged response shape, so the CLI and Android
need no changes.

DDL replay shows elapsed time, token information, a stop button, and the kiwi
progress mascot.  Stopping replay aborts the active `/api/compose` request.
During single drawing and DDL replay, the single tab shows a running effect and
the batch/demo start actions are suppressed.

During single drawing and DDL replay, the progress bar can show a kiwi mascot.
The kiwi faces left, walks slowly, pecks with a long beak, sniffs, blinks,
occasionally opens its beak during a quick dash, and sometimes curls into a
"kiwi ball".  In the curled state it keeps its head, body, and beak visible,
stays in place for more than six seconds, closes its eye, and gently nods its
head.  The legs are anchored at fixed body positions so the feet move without
the leg roots drifting.

### Batch Drawing

The batch panel accepts multiple instruction lines.  During execution, the
active line is highlighted and the current DDL interpretation is displayed
read-only.  Batch execution keeps failure reports until the next batch run, and
stores batch prompt history per user.

Batch mode can optionally choose a random server color catalog for each render.
The selected catalog is sent as `catalog_id` to `/api/paint`, and history records
store the catalog that was actually used.

In the color catalog dialog, clicking outside the dialog confirms the current
selection exactly like the save/confirm action. The cancel button still restores
the selection snapshot from when the dialog was opened.

The batch mascot is a small crab that walks slowly during progress, moves its
claws, watches the process, and occasionally dives under a water surface while
bubbles rise.

### Demo Drawing

Demo mode repeatedly generates an instruction from a seed phrase, renders it,
waits for the configured interval, and repeats.  Demo settings are stored per
user.  Demo results are not saved by default; the user can explicitly save a
current render to history.

Demo mode can also choose a random server color catalog for each render.  This
option is part of the per-user demo settings.  The status bar reflects the
catalog reported by the render result, not only the current global catalog
selection.

While demo is running, history interaction is restricted where it could confuse
context.

---

## 11. History and Data Integrity

History is stored in the server DB.  The DB record is the source of truth for:

- original input
- normalized DDL
- JSON Score
- SVG rendered by the server
- model metadata
- color catalog
- timing and token metadata
- star state
- trash state

The web UI does not send client-generated SVG back as trusted history content.
`/api/paint` generates and saves server-side history directly.  Compatibility
history endpoints re-render from JSON Score instead of trusting SVG sent by the
client.

For SVG download, the web UI exposes Display, Editable, and Compat variants.
Display downloads the stored SVG.  Editable and Compat call server render
endpoints so past history can benefit from the current export structure without
duplicating SVG blobs in the DB.

The CLI `paint` and `batch` commands also accept
`--svg-profile display|editable|compat` for saved SVG files.

Server-side output artifact saving is an admin-managed, server-wide setting.
The settings dialog includes an admin-only "other (server)" tab for:

- enabling or disabling automatic drawing file artifact saving
- setting the output folder as an absolute server path
- selecting the automatic PNG artifact size, either 1080px or 2160px

The server stores these values in `app_settings.output_save_settings` as
`enabled`, `output_dir`, and `png_size`.  `INKU_OUTPUT_DIR` and
`INKU_OUTPUT_PNG_SIZE` provide initial values; if unset, the defaults are
`~/.local/share/inku/outputs` and 2160px.  The API endpoint
`PUT /api/settings/output-save` is admin-only, accepts only absolute output
paths, and restricts PNG size to 1080 or 2160.

Disabling automatic artifact saving does not disable DB history saving.  The
history DB remains the source of truth, and only derived files such as SVG,
JSON, input text, normalized DDL, and PNG artifacts are skipped.  When enabled,
artifact files remain grouped by user and date under
`<output_dir>/<user_id>/YYYY-MM-DD/YYYYMMDD_HHMMSS_<history-id>...`.

The "other (server)" tab shows save worker and queue settings, save statistics,
and the PNG artifact size.  Save workers are concurrent file-save jobs; the
queue is the maximum number of pending artifact save jobs.  If the queue is
full, the server preserves DB history and skips only artifact file saving.

Server log retention is also an admin-managed, server-wide setting.  The
settings dialog includes an admin-only "log retention" tab for enabling or
disabling application log retention, setting the retention period in days,
choosing a daily / weekly / monthly rotation interval, and enabling compression
for rotated logs.  The default policy is enabled, rotates daily, keeps 90 days,
and compresses rotated logs.

The server stores this policy in `app_settings.log_retention_settings` as
`enabled`, `retention_days`, `rotate`, and `compress`.  `INKU_LOG_RETENTION_DAYS`
and `INKU_LOG_ROTATE` provide initial values.  `GET /api/settings/status`
returns the current policy with generated `logrotate` and `systemd` drop-in
previews for `inku-server` and `inku-api`; `PUT /api/settings/log-retention` is
admin-only and updates the stored policy.  Applying those generated files to the
host OS remains an operational task that requires server privileges.

The generated systemd preview uses
`StandardOutput=journal+append:/var/log/inku/<service>.log` and the matching
`StandardError` value so operators can follow logs through both
`journalctl -fu <service>` and retained file logs.  `inku-api` and `inku-server`
also print startup banners wrapped in 60-character `=` borders; the banners
include the service role, application version, build number, build date, mode,
listen host/port, runtime / platform, and log destination.  The API banner
includes the active render engine ID and version.  The API and web UI use
different emoji sets that match their roles.

---

## 12. Security and Operations

The web app includes authentication, user roles, sessions, per-user settings,
user profile editing, and user management.  Passwords are stored as salted
PBKDF2-SHA256 hashes.

The app rail user menu opens a profile dialog for the signed-in user.  The
dialog can update the user's email address and password through
`PATCH /api/auth/me/profile`.  Password changes require the current password,
and the endpoint is separate from admin user-management APIs.

Settings visibility is role-aware.  DB settings and user management are visible
only to the `admin` role.  The plugins tab is visible to all signed-in users,
but plugin setting changes and plugin-storage update APIs are restricted to
`admin`.

The DB settings tab also shows the current DB file size when the backend is a
SQLite file database.  Admin users can configure DB replica backups with an
interval in days and a maximum number of automatic generations.  The defaults
are seven days and four generations.  Scheduled backups are created when the
settings status endpoint is loaded after the interval has elapsed.  Manual
backups can be created immediately and are stored separately from the automatic
generation limit.  File-replica backups are reported as unavailable for
non-SQLite DB backends.

Concurrent drawing requests are bounded at the application layer. Stage 1 and
Stage 2 LLM calls share a bounded executor controlled by `INKU_STAGE_WORKERS`
and `INKU_STAGE_QUEUE_LIMIT`. If capacity cannot be acquired, or if a stage
exceeds its hard timeout, the request follows the same deterministic fallback
path used for stage hard timeouts. Timed-out LLM calls may continue in their
underlying Python thread until the provider call returns, so their capacity slot
is retained until that worker actually finishes. This prevents timed-out
provider calls from creating an unbounded backlog.

Per-user drawing counters are updated with a single database-side atomic
increment so simultaneous `/api/paint` requests for the same user do not lose
generation counts. History listing, retrieval, starring, trashing, restoring,
and deletion remain scoped by `user_id` so drawing history does not mix across
users. Admin status responses include `stage_execution` with Stage worker count,
queue limit, and submitted/completed/failed/timed_out/rejected counters.

Operational details for the author's local server are intentionally not part of
this public specification. They are consolidated in the untracked `AGENTS.md`
or under `no-git-sync/`.

The application is developed on macOS and verified on the deployment host after
rsync-based sync and systemd service restart. Production Docker Compose images
are verified at milestones such as release candidates rather than rebuilt for
every ordinary source change. Git is used for source history, not as a file
exchange mechanism with the local server.

### 12.1 Release Distribution (v2.4.0)

Releases are distributed as container images. Pushing a git tag `vX.Y.Z`
triggers a GitHub Actions workflow that builds and publishes
`ghcr.io/oikawas/inku-api` and `ghcr.io/oikawas/inku-web` as multi-arch
(amd64 / arm64) images. Users run them with the compose file and `.env.example`
under `deploy/` (`deploy/README.md` is the quickstart). Bundled plugins under
`server/plugins/` (currently Nature.leaves) ship inside the api image.

**Account premise:** there is no self-signup path. Accounts are created only by
an authenticated administrator via `POST /api/users`, so the first way in is the
bootstrap admin created on first start against a fresh database
(`INKU_BOOTSTRAP_ADMIN_PASSWORD`, 8 characters or more). A server started
without it is a box nobody can sign in to (set the value and restart to
recover; databases that already have accounts are left untouched). An empty
string is treated as unset (v2.4.0), and the distributed compose file refuses
to start without a value.

`/api/info` reports `version` as the server implementation version
(`server/pyproject.toml`, made the single source in v2.4.0 and stamped per
release). It is a separate namespace from the web display version
(`APP_VERSION`), but the numbers normally coincide because releases are
repo-wide.

**Developer mode (v2.4.3):** the `INKU_DEVELOPER_MODE` environment variable
decides only whether developer-facing options are shown. With it off, NVIDIA NIM
drops out of the display catalogs (`GET /api/models`, the administrator model
settings, and the provider model refresh), and the persistent Build number
disappears from the left rail, the sign-in screen, and the app info dialog.
**Only the display is gated: the execution path, stored model settings, the
model information on history entries, and each artwork's `render_build_number`
are unchanged when it is off** (if a stored setting points at a hidden provider,
only the on-screen selection falls back to the first public model). The
distributed compose file defaults it off; the development and bench compose file
defaults it on. `/api/info` reports `developer_mode`, and the web app reads it
before sign-in.

### 12.2 Reference Corpora (v2.4.4)

**Each version of a deterministic rendering layer has exactly one reference
corpus: the actual outputs, frozen, produced from fixed inputs.** A version
number carries only one bit — that something changed. What changed, and how, can
only be answered by comparing the outputs themselves.

- **Regenerating an existing case must be byte-identical.** If it is not, the
  drawing changed, and **the layer version must be incremented**.
- **A frozen version is never regenerated to absorb changed output.** Create the
  next version directory instead.
- **Case IDs are permanent.** They may not be renamed or removed; only added.
- **Corpora are never chained** — one layer's corpus output must not become
  another layer's corpus input.
- A corpus fixes **every dependency outside its own layer as a literal in the
  generator**: the color map and every Score field are written out rather than
  read from `COLOR_MAP` or the schema defaults. If output moves while none of the
  manifest identity fields (`corpus_format_version`, `engine_version`,
  `schema_version`, `color_map_digest`) move, **a dependency was left unfixed**.

The current instance is `server/reference/render-engine-10/` (220 cases).
**Outputs for render engines 1 through 9 were never preserved and cannot be
recovered**, so the corpus begins at engine 10. The operating procedure lives
next to the artifacts (`server/reference/README.md`), and CI
(`.github/workflows/reference-corpus.yml`) enforces byte-identical
regeneration. **The point is to move the versioning discipline from something
people remember to something the machine enforces.**

The corpus ships with no release: `server/reference/ export-ignore` in
`.gitattributes` keeps it out of `git archive`.

---

## 13. CLI

`inku-cli` is a command-line client for controlling the inku server through the
API.  Its initial purpose is to support automated prompt/image generation,
quality review, and feedback loops for tuning Stage 1, Stage 1.5, Stage 2, and
renderer behavior.

CLI configuration is local and editable.  It stores base URL, provider/model
selection, and timeout values outside the server DB.

`inku-cli paint` and `inku-cli batch` support `--input-mode paint|ddl`.
The default `paint` mode sends natural-language input to `/api/paint` and runs
the full Stage 1 -> Stage 1.5 -> Stage 2 -> render pipeline.  `--input-mode ddl`
treats the input text as already-normalized DDL, skips Stage 1, and sends it to
`/api/compose`.  When `--input-mode ddl --save-history` is used, the CLI saves
the compose result through `POST /api/history` so the output appears in normal
server history.  `/api/compose` returns the effective DDL after Stage 1.5
expansion, and CLI output/history use that effective DDL for DDL-to-render
benchmark parity.
The CLI sends instruction language through `--instruction-lang auto|ja|en`.
`auto` is the default and lets the server resolve Japanese or English from the
input text.  `--ui-lang` may be supplied as display-context metadata, but it
does not control interpretation.

`inku-cli batch` can write a benchmark summary JSON file.  When an output
directory is used, the default summary path is `analysis-summary.json` in that
directory.  The summary includes all successful samples and review groupings for
fallback, slow, and normal samples.  Slow samples are diagnostic only; successful
drawings remain part of quality review even when the free inference endpoint was
queued.

Benchmark summaries also include diagnostic traces used for tuning:

- `color_trace`, including requested colors, colors present in the Score,
  missing requested colors, warnings, and negated color markers.
- `negated_color_markers`, so phrases such as "not green" or Japanese
  equivalents such as `緑には寄せず` do not incorrectly count as missing green.
- `score_motif_hint_counts` and `score_motif_hint_lines` for compound motif
  repairs such as `leaf_cluster`, `paper_shard`, `ripple_knot`, and
  `mountain_sign`.
- `math_balance_markers` and `math_balance_marker_lines` for detected
  compositional markers such as radial Fibonacci counts, golden-like centers,
  rule-of-thirds-like centers, and counterweight-like opposite placements.

`inku-cli contact-sheet` builds a PNG contact sheet from a directory of PNG
outputs, making benchmark review less dependent on manual image assembly.

---

## 14. Testing and Evaluation

The project evaluates quality through several layers:

- backend tests for API, DB, schema, composer, interpreter, renderer, and
  deterministic fallback behavior
- frontend Svelte check and production build
- CLI-based benchmark generation
- saved benchmark summaries and contact sheets
- visual review of generated SVG/PNG output
- stress tests using invalid, ambiguous, emotional, conversational, and
  contradictory instructions

Benchmarks focus on:

- whether Stage 1 preserves the whole input context
- whether Stage 1.5 expands without overpacking techniques
- whether Stage 2 preserves all DDL elements in JSON Score
- whether deterministic fallback keeps enough DDL content to be reviewable
- whether the renderer makes DDL features visible
- whether the output has enough negative space, variation, and artistic focus

Current render-core tuning records explicit artwork-quality metrics in CLI benchmark summaries: `constraint_adherence`, `negative_space_pressure`, `motion_energy`, `color_resonance`, `visual_event`, and `figurative_risk`. These judge metrics are regression sensors, not final acceptance gates or substitutes for human selection. Build 448 confirmed divergence between machine scoring and human review, especially JP #23, so the metrics should not be retuned merely to raise preferred works. Fallback use, server hard timeouts, motif hints, presence counts, color traces, and compositional markers are recorded separately. Queue or retry duration is diagnostic only and is not treated as a primary quality metric, because free inference endpoints can be dominated by external queue behavior.

For NVIDIA free API testing, elapsed time is treated as operational metadata,
not as an artistic quality signal.  Queue delays can indicate service pressure,
but they do not exclude a successful work from aesthetic or structural review.

---

## 15. Current Implementation Status

The reference implementation currently includes:

- FastAPI backend
- SvelteKit frontend
- native Android app
- authenticated users and admin user management
- signed-in user profile editing
- role-aware settings visibility
- DB file size display and SQLite backup settings
- DB-backed history
- star and trash history management
- batch rendering
- demo rendering
- model/provider selection
- color catalog selection
- dark mode
- plugin storage, system/user plugin directories, and `canvas-aspect`
- SVG export and template-based PNG export
- CLI client foundation, benchmark summary output, and contact sheet generation
- CLI history export by render hash for benchmark review contact sheets,
  per-item JSON, and summary JSON
- CLI DDL input mode for DDL-to-render parity: `inku-cli paint --input-mode ddl`
  and `batch --input-mode ddl` call `/api/compose` directly and save through
  `/api/history` when `--save-history` is set
- CLI version/build reporting and server-owned color catalog lookup
- CLI benchmark diagnostics for color delivery, negated colors, motif hint
  arrival, and mathematical balance marker sample lines
- shared kiwi progress mascot for single drawing and DDL replay
- integrated DDL interpretation editor with Saijiki drawer, expanded dialog,
  token/time display, and cancellable `/api/compose` replay
- scene-tone palette strategy, richer fallback Scores, sensory visibility
  safeguards, and broader primitive use within the current schema
- renderer material effects, wobble, rotation, arrangement paths, density/fade,
  and canvas aspect support

The Android app is a Kotlin + Jetpack Compose native package with Room/SQLite
as its local data layer.  It is a single-user application package rather than a
multi-user server client.  Server/web remains the development master for DDL
interpretation, Stage 1.5 expansion, Score repair, SVG rendering, history
metadata, canvas aspect values, and render hash semantics.  Android-specific UI
decisions are allowed only when they are explicit mobile equivalents or
documented omissions.

Android local LLM support uses LiteRT-LM with Gemma 4 E2B as the standard local
model and Gemma 4 E4B as the higher-quality option.  Model license acceptance,
download state, re-download, checksum validation, and model file paths are
stored in Room.  The LiteRT-LM GPU backend is required; CPU fallback is not part
of the Android behavior.

Android simplifies model selection to one drawing model for instruction
generation, Stage 1, and Stage 2, while preserving server-compatible
`stage1_model` and `stage2_model` fields in settings, JSON display, exported
JSON, history records, and render metadata.  The Model Settings page exposes
provider panels for adding services, editing service names and base URLs,
adding or deleting API keys, fetching provider model lists, and choosing
published models.  Connection kind is set when a service is created and is not
edited from existing service panels.  Fetched candidate models are stored
separately from the published models shown in the drawing model picker.

The Android drawing view provides mobile-specific controls: pinch zoom, pan,
left/right image swipes for history navigation, and double-tap presentation
mode.  Presentation mode hides other UI, centers the image, rotates landscape
canvases for portrait phones, and chooses the surrounding background from the
rendered image background.  White-background images use the dark app
background; black-background images use a light background.

The Android history view intentionally differs from the server/web UI.  It uses
a three-column thumbnail grid and omits trash, list view, bulk selection, user
management, DB administration, plugin administration, and server log controls
because the Android package is single-user and mobile-first.

Android SVG/PNG export follows the server/web `CanvasPanel` intent.  SVG export
is a menu with display, editable, and compatibility profiles.  PNG export is a
menu backed by Room `export_templates`, with `1080px`, `2160px`, and `4320px`
Y-axis defaults.  Android opens the platform share sheet instead of browser
downloads.

Android render metadata includes `render_canvas_aspect_id` and
`render_canvas_aspect_ratio`, derived from the same canvas aspect definitions
ported from the server/web system plugin.  Android headless render and
comparison tooling can run without the Compose UI and is used with the server
CLI `--input-mode ddl` flow to compare DDL-to-render and Score-to-render
parity.

Android versioning is independent of the web build number.  `android/VERSION`
is the source for Android `versionName`, and `android/BUILD_NUMBER` is the
source for Android `versionCode`.  For the v1.48 generation, the Android values
start at `1.48.0-android.1` and `148001`.  The Android Settings menu exposes
version details including version name, version code, build type, application
id, source spec generation, and render engine version.

History records carry a server-side `render_hash`. New records use the `rh2:<sha256>` edition-id semantics from the render metadata section: saved Score plus explicit render conditions, not SVG text. Legacy 64-character hashes remain display-compatible. History APIs, paint/compose responses, the JSON tab, and saved artifact JSON expose both `render_hash` and the four-character uppercase `render_hash_short` for human reference.  The
history manager shows the short hash without changing the thumbnail layout;
clicking it copies the full hash.  The status bar also shows the current
render's short hash beside the star action and copies the full hash when
clicked.  After the web UI saves a render through the history API, it replaces
the active result hash with the DB history record's hash so the value shown
immediately after rendering matches the value shown when the same work is later
selected from history.  The CLI can resolve hash suffixes, reject ambiguous
short matches, and export selected or ranged history items for benchmark review.
The history manager opens at 80% of the current viewport, leaving 10% margins
on each side, and thumbnail cards show the prompt preview above a compact
star/hash/action row.
Prompt previews omit a leading numeric marker such as `#12`, and the compact
thumbnail controls keep visible contrast in both light and dark modes.
History manager pagination tracks overlapping fetches so the loading indicator
is cleared when the final request completes.
Thumbnail pagination measures the actual dialog thumbnail area and dynamically
uses only the number of items that fit without a thumbnail scrollbar.
The thumbnail star action is isolated from card selection, and page sizing uses
measured card height to reduce unused space at the bottom of the dialog.
The thumbnail action row places the star at the lower left, shows hash labels
without `#`, and aligns hash button typography with the delete action.
Starred thumbnails keep an explicit highlighted star state in dark mode.
History-manager thumbnails do not open an enlarged hover preview, keeping the grid and selection interaction stable.
The history manager header is compressed into two rows: title/view/count/pager
on the first row and selection/filter/search controls on the second row.
When thumbnail page size is recalculated from measured card dimensions, the
current page number is preserved instead of jumping back to the first page.
Per-item delete actions in the history manager use a compact trash icon button
instead of a text label.
The JSON tab, paint responses, history records, and saved artifact JSON include
the resolved `stage1_model` / `stage2_model` used by the server.
Current color management is intentionally limited to sRGB. The JSON tab,
paint/compose responses, history records, and saved artifact JSON include
`render_color_profile: { id: "srgb", name: "sRGB IEC61966-2.1", standard:
"IEC 61966-2-1:1999" }`. Adobe RGB and other wide-gamut profiles remain future
extension candidates and are not implemented in the current renderer.
The JSON tab displays render metadata first, including model, build, color
profile, render engine, canvas aspect, and color catalog fields, followed by the
`score` payload.
When a history item is reopened, the JSON tab displays the saved `stage1_model`
and `stage2_model` from that history record.
Paint, compose, history records, the JSON tab, and saved artifact JSON also
include render engine metadata.  `render_engine_id` identifies the rendering
core that performed the JSON Score, and `render_engine_version` identifies that
engine's contract version.  These fields are included in the canonical
`render_hash` payload so two works rendered with different engines remain
traceable even when their input Score is otherwise similar.
The settings dialog includes an admin-only Model Settings tab.  It stores the
default Stage 1 / Stage 2 provider and model plus per-provider base URL and API
key settings in server app settings.  The supported connection targets are
OpenAI API Platform, Claude API, Gemini API, NVIDIA NIM, Ollama's
OpenAI-compatible API, and Intel OVMS's OpenAI-compatible API. Admin users can
add and remove connection services from the model settings tab. Added services
carry a service ID, display name, connection kind (`openai_compatible`,
`anthropic`, or `gemini`), base URL, and optional initial API key. The add
service dialog saves the new service to the server immediately when Add is
pressed, so service panels do not include a redundant whole-panel save button.
Model lists are fetched later through each service's model-list fetch action
instead of being typed manually when the service is created.
The service ID is the stable internal key used for DB connection settings,
Stage 1 / Stage 2 provider references, API provider dispatch, and duplicate
protection, so it is not editable after creation. The user-facing service name
can be edited later.
Each service panel can fetch its model list through the server. The server uses
the saved base URL and API key to call the provider-specific models API and
saves the returned model list back into that service definition without sending
raw API keys to the browser. Fetch success or error messages are shown at the
bottom of the published-model picker dialog.
Raw API keys are kept server-side only. The UI uses
`GET /api/settings/models` only to know whether a key is configured. Raw keys
are never returned to the browser; when a key is already configured, the input
shows "keep saved key" and is read-only. Entering a new key for an unset
service changes that service action to save the key. `PUT /api/settings/models`
distinguishes preserving, replacing, and clearing a provider key. Provider API
keys are stored in the DB in encrypted `enc:v1:` form. The server uses
`INKU_SECRET_KEY` when set, otherwise `INKU_SECRET_KEY_FILE` or
`~/.local/share/inku/secret.key` as a local key file. Existing plaintext keys
remain readable for compatibility and are migrated to encrypted storage on the
next save. The Model Settings tab shows this rule next to the AI service
connections heading: API keys are encrypted in the DB, are never displayed
again, and keys configured through environment
variables are treated as initial values. LLM calls
resolve provider-prefixed model IDs such as
`openai:...`, `anthropic:...`, `gemini:...`, `nvidia:...`, `ollama:...`, and
`ovms:...`, while keeping compatibility for older NVIDIA slash IDs and local
OVMS model IDs.
The web UI normalizes model IDs sent to `/api/paint`, `/api/interpret`, and
`/api/compose` by combining the selected provider with the selected model, for
example `openai:gpt-5.2`. If an API request still sends a bare model ID and it
matches the current user's configured Stage 1 or Stage 2 model, the server
qualifies it with that user's configured provider before dispatching. Demo
prompt generation uses the same provider resolution path for OpenAI API
Platform, Claude API, Gemini API, NVIDIA NIM, Ollama, and Intel OVMS.
LLM server connection settings are global admin-managed settings.  Each user's
Stage 1 / Stage 2 provider and model selection is stored separately in
`user_accounts.model_settings`, saved from the model selection dialog through
`/api/auth/me/settings`, and restored on login.  Admin users can also toggle
which models are visible to users for each provider. Published-model selection
is handled in a separate dialog that also contains model-list fetch, search,
select-all, and clear-all controls. Checkbox changes inside that dialog are
drafted locally and are sent to the server only when Save is pressed; Cancel or
clicking outside the dialog discards them. The main settings tab summarizes
only the currently published models. `GET /api/models` returns only published
models for signed-in users, and the model selection dialog uses that filtered
catalog.
The status-bar PNG export templates default to Y-axis heights of `1080px`,
`2160px`, and `4320px`. Older saved defaults of `1024px` and `2048px` are
automatically replaced by the new defaults, while user-customized templates are
preserved. The Japanese UI labels this dimension as `Y軸` / `Y軸の高さ`.

### v1.51 (2026-07-02)

Version 1.51 adds the relation system, called `aida` in Japanese, and assigns
variation to both micro and macro scales.  JSON Score instructions may now carry
`at.region` for renderer-resolved placement and `relation` for observable
relationships to previous instructions: `along`, `not_touching`, `cutting`, and
`between`.  Renderer performances record `render_seed` so macro placement can
vary between performances while remaining reproducible when a seed is provided.

Stage 1.5 is redirected away from fixed finished recipes and toward
composition-family selection plus relation attachment.  Invalid relations are
dropped rather than repaired, and the coerce layer is forbidden from adding
relations.

Detailed implementation history remains in the canonical Japanese spec.

### v1.52 (2026-07-04)

Version 1.52 materializes post-selection through two explicit regeneration
paths. `render_seed` supports another performance without an LLM call.
`vary_seed` supports another composition by mixing an explicit counter into the
Stage 1.5 selection seed while preserving the default rule that the same input
produces the same expansion. The vary path changes composition-family, focus,
and technique selection; it does not intentionally change Stage 1
interpretation.

Version 1.52 also forbids repair parts from becoming a system fingerprint. CLI
diversity analysis now reports marker-based repair-part counts and sample
rates. Coerce repair parts use input-derived placement and shape variation
instead of fixed coordinates, and adjacent focal reactions fire only for
isolated visual events.

Build 442 verification confirmed that the `vary_seed` path is implemented
through the API, CLI, and web UI. A 5-prompt x 5-vary run succeeded 25/25 with
no fallback, and JP/EN 30-sample repair-part measurement reduced
`adjacent_reaction` from 56/60 to 14/60.

Build 442 did not satisfy the benchmark acceptance gate. `angular_pulse`
remained at 14/60, `vanishing_trace` rose from 21/60 to 26/60, and average
`visual_event` fell from the Build 441 baseline of 93.0 to 77.8.

Build 443 tightened `vanishing_trace` so it requires both a disappearance
context and a trace subject such as footprints, breath, outlines, figures, or
circles. It also changed the generic `visual_event` fallback from a small
angular pulse to an input-derived compact mark. The JP/EN 30+30 benchmark then
reported `adjacent_reaction` at 11/60, `angular_pulse` at 0/60, and
`vanishing_trace` at 2/60, satisfying the repair-fingerprint gate. Average
`visual_event` remained 77.93 and `negative_space_pressure` remained 88.97, so
the Build 441 quality-regression guard is still not satisfied. Version 1.52
should therefore be read as complete for feature delivery and repair-fingerprint
suppression, with low-quality sample investigation still remaining.

Build 444 targeted the remaining low-quality samples without adding a new
global floor. The generic compact visual event now carries a color cycle and an
input-derived opposing center; a `brief_arrival_departure` event type covers
temporary arrival-and-leaving moments; and the existing doubled-river-road and
tilted-room-drop recipes now carry color cycling and opposing placement. The
targeted benchmark recovered EN #06 to `visual_event` 98 /
`negative_space_pressure` 100, EN #27 to 70 / 76 on a single rerun, and JP #28
to 76 / 86.

The Build 444 JP/EN 30+30 full benchmark
(`cli/out/jp-en-30-equivalent-444/{jp,en}/`) completed 60/60 with no fallback.
Repair parts remained within the v1.52 fingerprint gate:
`adjacent_reaction` 10/60 (16.7%), `angular_pulse` 0/60, and
`vanishing_trace` 2/60 (3.3%). The quality averages were `visual_event` 79.90,
`negative_space_pressure` 89.97, `motion_energy` 94.57, and
`constraint_adherence` 93.33. Compared with the Build 441 guard baseline
(`visual_event` 93.0, `negative_space_pressure` 96.23, `motion_energy` 97.7,
`constraint_adherence` 86.0), `visual_event` and
`negative_space_pressure` still miss the within-5 regression guard. The current
v1.52 status is therefore: Phase A-D implementation, measurement, vary, and
repair-fingerprint acceptance are complete, but the quality-regression guard is
not yet accepted. Further work should inspect low-scoring rows such as EN #21
(`visual_event` 40 / `negative_space_pressure` 26), JP #23
(`negative_space_pressure` 42), and JP #02/#03 (`visual_event` 48), and improve
existing recipe placement, color cycling, and opposing relationships rather
than adding marker vocabulary or a new governor.

Build 445 generalized the Build 444 low-score fixes into DDL coverage handling
for small dots, circles, and ellipses. English DDL sentence splitting is now
more precise, `circle` and `ellipse` are no longer collapsed into one fallback
shape, and `radius` / `半径` plus small-mark coverage such as `small dot` is kept
as a compact, low-density foreground mark with outward fade and preserved
negative space. This is a shape, size, and spacing correction in the existing
coerce fallback path, not a new marker vocabulary or global governor.

The Build 445 JP/EN 30+30 full benchmark
(`cli/out/jp-en-30-equivalent-445/{jp,en}/`) completed 60/60. JP #27 and JP #28
still hit stage2 timeouts on the final server-timeout retry and used saved
fallback results, so fallback was 2/60. Repair parts remained accepted:
`adjacent_reaction` 8/60 (13.3%), `angular_pulse` 0/60, and
`vanishing_trace` 2/60 (3.3%). Quality averages were `visual_event` 80.43,
`negative_space_pressure` 91.47, `motion_energy` 93.73,
`constraint_adherence` 94.17, `color_resonance` 96.83, and
`figurative_risk` 1.33. Against the Build 441 guard baseline,
`negative_space_pressure`, `motion_energy`, and `constraint_adherence` are back
within the allowed -5 window, but `visual_event` is still below the required
threshold (`80.43` versus `93.0`). The remaining v1.52 work is now concentrated
on restoring semantic eventfulness for low rows such as JP #02 (`visual_event`
40) and JP #21 / EN #04 / EN #20 / EN #21 (`visual_event` 48).

Build 446 / 446-2 addresses those sticky low-event rows by strengthening only
existing instructions and arrangement metadata. Compact dot, circle, and ellipse
coverage can now be treated as a compact focal visual event in an event context.
Existing focal events receive an opposing arrangement center, color cycle,
preserved negative space, low density, and outward fade so that they read as
compositional counterweights. For inherited-memory scenes, an existing support
instruction can carry an inherited-memory trace instead of adding a new repair
part. This is not a new drawing primitive or global floor; it is a placement,
color-cycle, and semantic-hint correction on existing elements.

The Build 446-2 JP/EN 30+30 full benchmark
(`cli/out/jp-en-30-equivalent-446-2/{jp,en}/`) completed 60/60. JP #09 still
used a fallback result after the final stage2-timeout retry, so fallback was
1/60. Quality averages were `visual_event` 92.85,
`negative_space_pressure` 94.30, `motion_energy` 96.95,
`constraint_adherence` 95.50, and `color_resonance` 99.75, satisfying the
Build 441 -5 regression guard. Repair fingerprints also remain accepted:
`adjacent_reaction` 13/60 (21.7%), `angular_pulse` 0/60, and
`vanishing_trace` 1/60 (1.7%). The inherited-memory arc that fable5 identified
as a possible successor fingerprint is now measured as `inherited_memory_arc`;
it appeared in 4/60 samples (6.7%).

The remaining risk is relation drop rate. Build 446-2 measured JP 15/53
(28.3%), EN 22/51 (43.1%), and 37/104 combined (35.6%), above the 20% reference
used by fable5. v1.52 keeps relation validation drop-only: coerce must not
repair or complete relations. If this rate is treated as blocking, mitigation
should be limited to Stage 2 prompt guidance that emits relations only when they
are safe in output order and omits them when uncertain.

Build 447 treated relation drop rate as blocking and strengthened the Stage 2
prompt. Ordinary placement language such as along a diagonal band, along an
undulating trace, riverbank, and roadside must not become relation; `between`
requires two immediately previous outline instructions; and uncertain cases
must omit relation. The Build 447 JP/EN 30+30 benchmark still measured JP 13/55,
EN 4/29, and 17/84 combined dropped relations, or 20.2%, just over the 20%
reference used by fable5.

Build 448 adds a Stage 2 output gate that keeps relation only when the
normalized DDL literally contains one of the fixed previous-object phrases:
`前の線に沿って` / `along the previous line`, `前の形に触れない` / `not
touching the previous shape`, `前の線を切る` / `cutting the previous line`, or
`前の二つの間に` / `between the previous two`. Natural-language-derived ideas
such as around, same beat, ahead/behind, not touched, near, and far are expressed
with position, path, rotation, and spacing instead. Coerce remains drop-only for
relations and still does not repair or complete them.

The Build 448 JP/EN 30+30 full benchmark
(`cli/out/jp-en-30-equivalent-448/{jp,en}/`) completed 60/60. JP #01 still used
a fallback result after the final stage2-timeout retry, so fallback was 1/60.
Combined quality averages were `visual_event` 92.40,
`negative_space_pressure` 95.87, `motion_energy` 97.77,
`constraint_adherence` 92.00, and `color_resonance` 99.27, satisfying the Build
441 -5 regression guard. Repair fingerprints also remain accepted:
`adjacent_reaction` 14/60 (23.3%), `angular_pulse` 0/60, `vanishing_trace` 2/60
(3.3%), and `inherited_memory_arc` 4/60 (6.7%). Relation drop improved to JP
1/6 (16.7%), EN 0/2, and 1/8 combined (12.5%), below the blocking 20% reference.
The relation sample rate is intentionally low on the natural-language fable set
because relation is again reserved for fixed previous-object phrases. Version
1.52 is therefore accepted for vary, repair-fingerprint suppression, the quality
guard, and the relation-drop blocking item.


### v1.60 (2026-07-07)

Version 1.60 moves the project from quality-loop closure to a one-person playable 1.0 candidate: another person should be able to set up inku from the README, write a visual tanka, consult Saijiki, read interpretation feedback, choose with vary, save, and replay a result.

- `render_hash` is redefined as an `rh2:<sha256>` work-edition identifier computed from the saved JSON Score, `render_seed`, `vary_seed`, `render_build_number`, `render_color_catalog_id`, and render-engine metadata. SVG text, input text, normalized DDL, and raw LLM responses are excluded. Existing 64-character hashes remain legacy display-compatible values.
- History now stores `vary_seed`, and the history manager can replay a saved Score with its saved seed.
- The input panel shows approximate post-processing interpretation feedback using ink-density shading. This does not change the Stage 1 schema or prompt.
- The canvas displays the input text as a caption by default, treating the relation between words and image as part of the work.
- The English and Japanese READMEs now include Quick Start setup, provider/API-key guidance, two-stage regeneration, the six-color Saijiki constraint, and history replay.
- Final gallery selection is deferred to v1.70 or later. Version 1.60 is complete once the candidates are recorded; selecting works for publication belongs to the next evaluation and release cycle.
- Phase E sparse-output handling adopts the E-2 policy: use the existing `visual_event` / `negative_space_pressure` metrics and visual review only, without adding a dedicated metric or marker. Sparse outputs are not a blocking implementation target for v1.60.

### v1.70 (2026-07-08)

Version 1.70 implements the aesthetic-selection phase: it keeps judge metrics out of the acceptance gate and instead makes form, post-selection, and comparison visible in the product.

- The language/spec alignment pass clarifies that writer-facing words such as random scattering remain valid input, while unordered randomness is forbidden only as an internal Score representation. The core color vocabulary remains six abstract writer-facing colors; color catalogs are server-owned resolution metadata, not vocabulary expansion.
- The writing surface now carries only a quiet, non-blocking length hint: roughly 31 Japanese characters or roughly 12 English words.
- Saijiki relation entries keep poetic headings while examples show the reachable fixed previous-object phrases. Stage 1 only normalizes explicitly written element relationships into relation phrases; place or scene words such as riverbank-style "along" are not relation predicates.
- Post-selection is now concrete: a variation grid can produce four default candidates, optionally include a fresh interpretation candidate, allow multiple selections, and save selected works to history. Starred history items may carry a short optional note explaining the choice.
- Explicit interpretation variation records `interpretation_seed` and displays a normalized-DDL diff. Reproduction is anchored in the saved DDL/Score rather than in replaying the LLM nondeterministic text output.
- The `Nature` reference vocabulary plugin adds `Nature.wind`, `Nature.undulation`, and `Nature.stillness` as deterministic Stage 1.5 macros. The explicit `Nature.` namespace is required; plain natural-language words do not trigger the plugin. The implementation uses existing DDL/Score variation and arrangement only, so no new primitive, Score field, or coerce rule is added.
- Saijiki shows Nature plugin terms in a separate plugin category with distinct, subdued styling.
- The comparison area shows previous/current renders side by side, a subdued prompt diff, and an LLM Model Inspection view for two Stage 1 models. It is a viewing tool, not a judge surface, and displays no judge values.
- Localized tooltips were added to the main action controls, including the four-candidate grid, interpretation variation, save selected, model comparison, and DDL auto-repair controls. Tooltip text follows the main UI language switch.
- The left app rail no longer expands on mouse hover. Its width is controlled by an explicit top-left expand/collapse toggle, so the working area can remain stable while editing.
- Build 458 was verified on pentala for D-1/D-2; screenshots are stored under `no-git-sync/screen-cap/` and the local verification note is recorded in `cli/tune_bench.md`.

### v1.71 (2026-07-08)

- Added `instruction.surface` and `canvas.ground` to JSON Score for object-surface and canvas-ground texture.
- Added renderer support for display, editable, and compat texture profiles, including texture metadata and deterministic seed handling.
- Updated Stage 1 and Stage 2 prompts so texture words become score attributes instead of hidden helper shapes.
- Preserved backward compatibility: existing scores without surface or ground render as before.
- Expanded Svelte tooltip coverage across AppRail icons, Input panel tabs/buttons, and Canvas panel controls (zoom, vary, downloads, navigation) to improve usability.

---

## 15.8 Accounting for Refinement

inku treats convergence caused by accumulated quality repairs as part of its implementation history. Countermeasures belong only in human-facing mirrors, explicit user actions, and development practice; they must not become automatic control in the default generation path.

- Every minor release records at least one branch, word, component, or rule it removed, or explicitly says that nothing could be removed. This is an account, not a deletion KPI.
- Every release records what it made less likely, so the cost of refinement remains visible.
- Release review places the new JP30/EN30 contact sheets beside the preceding two releases and records any newly increased repetition together with the motif-census delta. Finding no increase is also recorded.
- Similarity features, motif frequency, vision observations, and coerce firing rates are audit mirrors. They never automatically control default-generation branches or suppression, acceptance gates, or optimization objectives. As an explicit exception, a user-started finite AI Vision autonomous-refinement run may feed non-scoring observational advice into the next generation. It never ranks, accepts, rejects, or discards a generation; every generation remains in lineage and the human makes the final decision.

v1.80 adds a deterministic Score-derived composition mirror shared by server and CLI, three unranked nearby history thumbnails, similarity ordering for contact sheets, a mechanical motif census over artifact sets or the current user's history, explicit renderer-only `seed_text`, a private unread-word ledger with `unread-words` and admin-only `unread-words --all` reporting, per-branch coerce observation, and an on-demand NIM vision review. Similarity never implies lineage: lineage remains the record of explicit creative causation. When drawing continues from an unsaved refinement candidate, that candidate is automatically materialized as the direct `lineage_only` ancestor without entering regular history; it can later be promoted explicitly from the lineage view.

The Canvas UI separates artwork facts from pending generation settings. The top row labels the models, color catalog, canvas, and creation time actually used by the displayed artwork as `Displayed`; the bottom status bar labels the currently selected models, color catalog, and canvas for the next run as `Next generation`. When Stage 1 and Stage 2 use the same model, the UI combines them as `Interpretation / rendering`. The generation-information inspector has `Details`, `Prompts`, and `JSON` views. Details contains the two stage models, color catalog, canvas, render/layout/interpretation seeds, render and description hashes, render engine and version, build, elapsed time, and input/output token counts. In the Prompts view, the initial heights of Stage 1 user input and Stage 2 system prompt are reduced by half without changing their content; Stage 1 system prompt and Stage 2 user input retain their existing heights.

Refinement account for v1.80: the proposed automatic statistics-to-generation “unexplored” path was removed from this release, and vision review remains manual rather than release-automatic. Existing default-path repair branches could not yet be removed. The release makes unnoticed self-repetition, unrecorded external performance seeds, and privacy-losing unread-word aggregation less likely; it deliberately does not make dissimilarity a goal.

### v1.81 Lineage-grouped history

History Manager offers `Timeline` and `By lineage` as an independent display choice alongside the thumbnail/list layout choice, and stores the display preference in the browser. The bottom history strip remains chronological because it serves rapid previous/next navigation. Each strip item shows its one-based generation depth, derived from saved parent edges, and its lineage-node state instead of render elapsed time. Selecting an item while the Lineage tab is open preserves that tab, reloads the selected work as the focus node, and centers it.

A history group is based only on persisted lineage nodes and edges, never similarity, identical text, or timestamps. Every lineage node has an immutable `root_node_id`: a root points to itself and a child inherits its parent's root. Existing nodes are backfilled by following persisted edges toward their ancestor. Groups are ordered by the latest matching regular-history artwork and paginated by group, so one lineage is never split merely by an artwork-page boundary.

Each group header shows a representative artwork, the regular-history artwork count under the current filter, starred count, and latest save time. Members are fetched only when expanded and retain the existing display, star, replay, individual/group selection, and trash operations. Search, starred-only, and active/trash filters include only matching artworks in group summaries and expanded members. `lineage_only` and tombstones remain outside regular history and its counts. An independent artwork forms a one-work lineage, and no root, artwork, or count may cross user boundaries.

Build 557 establishes the v1.81 foundation with lineage-root migration/backfill, lineage group/member APIs, and the Timeline/By lineage History Manager UI with lazy expansion.

### v1.82 Automatic instruction language and language comparison

The writing tab no longer asks the author to choose an instruction language. Normal generation always requests automatic detection from the entered text; when the text has no Japanese or Latin language signal, the UI display language is the fallback. Japanese UI with English writing, and English UI with Japanese writing, remain supported.

Normal Stage 1 and Stage 2 generation is LLM processing, while image-reading operations have a separate per-user Vision model setting. The model dialog separates Shared Stage 1/2, Stage 1, Stage 2, and Vision selection, and admin model settings identify whether each model is available for LLM, Vision, or both. `GET /api/models` retains the LLM `catalog` for older CLI clients and also returns `llm_catalog` and `vision_catalog`. Okugaki has its own per-user model choice, initially derived from the general Vision default and restored the next time Okugaki opens. An explicit API or CLI model remains authoritative for compatibility.

Each model may carry LLM/Vision purposes, per-purpose five-level recommendations (split into LLM and Vision values in v1.98; the old single value is read for compatibility only), Japanese and English evaluation comments, and a measured speed class and label. Administrators can edit this metadata, and both admin and user model selection expose it on hover. Speed values are observations from a particular measurement run, not a permanent performance guarantee or an acceptance gate for generation quality. Beyond normal generation, Batch has no image input, so it shows the current Stage 1/2 models and opens a model dialog without Vision. Demo separately selects its instruction-generation LLM and rendering Stage 1/2 models, while Okugaki selects from Vision cards grouped by provider. These cards expose the same evaluation metadata on hover using a theme-independent high-contrast tooltip.

Since v1.98 every model list is ordered with end-of-life (EOL) models last, then by the recommendation for the purpose at hand in descending order, with ties broken by label. EOL models stay in the catalog marked as retired and unselectable rather than being removed, so model references in saved works remain resolvable. The server does not reject requests naming an EOL model; the provider's failure is classified and explained by kind (model gone, authentication, rate limit, other).

Refine adds Language comparison beside Adjust and Model comparison. It uses the same three comparison modes: shared Stage 1/2 language, fixed Stage 1 with Stage 2 comparison, and Stage 1 comparison with fixed Stage 2. Japanese and English can be assigned per stage only for an explicit comparison run, without changing automatic detection for normal generation. The target's identical language combination is excluded, results show the Stage 1/2 language pair and normalized DDL, and an adopted result records the pair in lineage metadata. Changing the target clears results and aborts an in-flight language comparison.

Build 558 implements this boundary and the UI-language fallback. Adopted comparisons use a dedicated `language_variation` lineage edge.

Build 559 adds the effective Stage 1 and Stage 2 languages to Generation info / Details. Normal works show their shared resolved language, while adopted language comparisons show the per-stage values recorded in lineage metadata.

Build 560 aligns Generation info / JSON with Details by adding per-stage instruction languages, render/layout/interpretation seeds, description hash, elapsed time, input/output token counts, and derivation kind/metadata at the top level. The JSON Score, API and database schemas, and canonical render-hash payload remain unchanged.

### v1.85 Operational safety, complete CLI access, and containers

The existing non-container development setup remains supported. A root Compose configuration additionally runs a non-root FastAPI container, a production SvelteKit Node container, and a persistent data volume. The Web service proxies only same-origin API requests to the internal API service.

The server enforces a configurable request-body limit, per-user/IP login rate limiting, renderer concurrency, explicit additional CORS origins, and sanitized unexpected errors. SQLite foreign keys are enabled on every connection. Artwork, lineage node, and lineage edge writes remain atomic; permanent deletion is limited to trash and preserves content-free lineage tombstones.

Save endpoints accept a per-user Idempotency-Key. A retry with the same key returns the existing work without duplicating history, lineage nodes or edges, or generation counts. User-management scope is also enforced inside update and delete transactions. Group leads can manage only regular users in their own group, and no history, lineage root, or count crosses user scope. External identity providers remain future work and must preserve the current session, role, and scope boundary.

History lineage groups, item positions, and focused ancestor/descendant graphs use paginated or recursive database queries. Similarity ranking loads score candidates without hydrating every SVG and restores only the selected works. The UI aborts stale group requests.

inku-cli always provides help. Its api command supports GET, POST, PUT, PATCH, DELETE, query parameters, JSON body/file input, headers, and binary output, restricted to /api/... and /health on the configured server. It therefore exposes every public API under the same authentication and role permissions as the GUI.
Dedicated commands (`lineage`, `refine`, `inspect`, `review`) are added to inku-cli to fully support autonomous AI testing and quality improvement workflows (generating touch/layout/reading/color variations, evaluating visual aesthetics via Vision NIM, traversing the lineage tree, and submitting unread words). A dedicated guide (`cli-reference-for-ai.md`) is provided to outline standard testing procedures for AI agents.

Short English tabs, buttons, and labels use Title Case. At iPad-class widths the Canvas tabs and displayed Models/Color/Canvas/creation metadata wrap into two rows, and the left panel scales with the viewport rather than clipping the artwork metadata.

JSON Score remains a strict, versioned schema so unknown fields are never silently discarded. Additive database migrations remain idempotent and do not destructively rewrite existing render hashes, description hashes, or lineage identities. Build 564 (New CLI commands and AI testing guidelines are implemented in Build 565).

### v1.86 Lineage UI menu integration and autonomous AI refinement (2026-07-16)

- Added a contextual menu trigger (`...` button) to each card in the Lineage tab, letting users execute individual actions (AI Refine, Manual Refine, and Delete) directly from the card.
- Implemented the AI Refine modal, enabling users to enter a direction prompt, choose a generation depth (1 to 10), and select which elements (Reading, Colors, Composition, and Texture) to vary. Svelte drives an asynchronous, sequential generation loop (`paintOne` calls) in the frontend, providing real-time feedback including step progress, stage-resolved statuses, and previews of intermediate generated graphics. The lineage tree auto-refreshes to show the newly grown branch once completed.
- Implemented the Manual Refine modal, carrying over the displayed parent DDL structure and color catalog as defaults, and allowing fast, single-generation variations by specifying a derivation kind, color catalog, or additional Saijiki/prompt.
- Integrated individual deletion to instantly trash selected artworks directly from their card menu.
- Build 565.

### v1.86.1 — agy review reflection, security and performance optimization (2026-07-16)

- **Authentication Toggles and Guards**: Made the Google/local authentication settings dynamic and persistent in the database (`app_settings` table) and created a configuration API endpoint. Implemented a security guard to block login attempts with `403 Forbidden` if local authentication is disabled.
- **Robust Schema Validation**: Applied `ConfigDict(extra="forbid")` to all Pydantic schemas (e.g. `SurfaceSpec`, `CanvasSpec` models) to prevent silent discarding of unknown fields with unexpected parameters.
- **Svelte 5 Warnings & Recursion Fixes**: Introduced a 200ms debounce to ResizeObserver state updates in `HistoryManager.svelte` to prevent layout thrashing (infinite reflow loops). Also fixed reactive state bindings in `ManualRefineModal` to avoid compile warnings about copying prop values into local state.
- **Lineage Rendering Performance**: Replaced the expensive `getBoundingClientRect()` calls with recursive layout-pixel based offset calculations (`offsetLeft`/`offsetTop`), significantly reducing rendering overhead.
- **WebKit Layout Coordinates Fix**: Removed the non-standard CSS `zoom` property from the lineage layout (which causes arrow offset mismatches in iPad Safari/WebKit) in favor of standard `transform: scale` and `transform-origin`.
- **Management CLI Enhancements**: Added `user` (create, list, update, cascade delete), `group` (management), and `config` (settings status and change) admin subcommands to `inku-cli`. Built an automated script to parse parser definitions, format them, and write them directly into `cli/README.md`.
- **i18n and Responsive Upgrades**: Migrated all hardcoded strings in AI and manual refinement modals to the shared i18n dictionary `t()`. Applied `flex-wrap: wrap` and `text-overflow: ellipsis` to the canvas metadata section, preventing layout clipping at intermediate viewport widths.
- **Build 566**.



Build 561 removes the former “Use today's word as a seed” control from the writing tab and first generation, and moves it to Refine / Adjust as “Vary Touch with Words.” The entered words affect only the Renderer's deterministic performance seed, never the interpretation, DDL, JSON Score, or layout. Because the same words reproduce the same touch, this operation generates one candidate at a time. History, Generation info / JSON, and replay retain both the words and resolved seed. The first artwork remains the source work and never applies this word-based touch variation.

Build 562 removes the duplicated instruction preview below the writing field and places the normalized-DDL heading on the same row as Saijiki, DDL edit, and automatic repair. “Vary Touch with Words” moves to the end of the refinement choices; selecting it alone reveals an unlabeled input and copy explaining deterministic Seed behavior and the one-option limit. Writing-tab selectors now use action-target labels, “Canvas” and “Color catalog,” in both languages instead of showing the current values, and the canvas button no longer has a leading square icon.

Build 563 orders writing-tab actions as Color catalog, Model selection, Canvas, and New, and gives the Canvas selector the same outlined styling as the other ordinary buttons. The Prompt and Interpretation (normalized DDL) headings use a clearer 12px semibold treatment without increasing their row height.

Build 545 reorganizes the Canvas artwork facts and next-generation settings into separate groups and consolidates generation metadata into the Details / Prompts / JSON inspector. It changes only the visible height, not the content, of the Stage 1 user input and Stage 2 system prompt fields.

Build 546 moves the former top-level Compare tab into Refine and presents Adjust and Model comparison as sibling subviews. Switching subviews preserves their candidates and comparison results; changing the target artwork clears stale comparison results.

Build 547 adds a `First` button to the right of `Next` in History Manager. It jumps directly to the oldest page containing the earliest saved artwork and is disabled while loading or already on that page.

Build 548 fixes a History Manager page-size boundary where wrapper padding was counted as usable thumbnail space, making the calculated column count one larger than the actual CSS Grid. Columns now use the Grid's rendered width and rows use the wrapper height minus vertical padding, so only fully visible rows are fetched.

Build 549 aligns History Manager's bulk delete action with the lineage view: both use the same trash icon followed by the selected count. The action is disabled with no selection, while its name remains available through the tooltip and aria-label.

Build 550 stops using the fixed model catalog for Demo prompt generation. Its provider and model dropdowns now follow the configured, enabled list returned by `/api/models`; empty providers are omitted, a disabled saved choice is replaced and persisted with the first enabled model, and Demo start is disabled when no enabled model exists.

Build 551 fixes Demo random color catalogs updating only the paint request while leaving the visible catalog selection unchanged. Each draw now updates the UI selection, avoids the immediately previous catalog when at least two choices exist, and reconciles the selection with the catalog ID actually reported by the response.

Build 552 moves the authoritative Demo catalog draw into `/api/paint` after an observed run still rendered with `Ink & Season`. The backward-compatible `random_color_catalog` flag makes the server exclude the submitted current catalog ID, choose another catalog, and carry that one ID through render metadata, the color map, Renderer, history, and response. Demo updates its UI from the returned effective ID; ordinary paint requests keep their explicit catalog behavior.

Build 553 makes refinement a radio-style single intervention so every lineage edge corresponds to one kind of change, and adds color catalog as the fourth kind. Color candidates use a metadata-bearing rerender that fixes the parent's DDL, Score, seeds, and canvas, while `catalog_change` records before/after IDs. Touch, layout, and reading candidates now also inherit the displayed parent's effective catalog and canvas.

Build 554 fixes stale candidates from the previous source work remaining after a saved candidate or another work becomes the explicit refinement target. History, lineage, nearby-work and previous/next selection, new generation, and DDL rendering now reset candidate and progress state, while switching Refine subviews preserves it.

Build 555 unifies reset of target-owned transient UI state, including model-comparison results, reading diffs, replay errors, intermediate-lineage notices, and lineage fetch state. Model comparison uses request abortion plus a run ID, lineage fetching uses a latest-request ID, and comparison/refinement saves and replay rendering verify the target generation so delayed responses from an old work cannot populate the current one.

Build 556 fixes the stacking order that placed the lineage overview above its delete confirmation, making the trash action appear unresponsive. Confirmation dialogs now occupy the top interaction layer above full-screen overlays, so deletion can be confirmed or cancelled without closing the overview.

## 16. Licensing

The intended license direction is:

- core DDL specification: permissive license such as CC0 or MIT
- reference implementation: MIT or Apache-2.0
- Saijiki vocabulary data: CC BY or CC BY-SA, if community contribution begins

The language should remain reusable by other implementations while preserving
the reference implementation as one concrete path.

---

## Autonomous Refinement Methods

Lineage's autonomous refinement is a bounded run of 1–10 generations whose final judgment remains human. Before starting, the user chooses one method:

- `Random automatic refinement` randomly chooses each generation's variation kind from the enabled reading, color-catalog, layout, touch, and variation elements. It does not use Vision. Because the direction text only reaches the drawing text of reading generations, the random-method UI states that condition explicitly.
- `AI Vision automatic refinement` lets the user explicitly choose a Vision model from provider-grouped cards. The server rasterizes each saved generation to PNG and sends it with the original instruction, user direction, and allowed refinement kinds. Vision returns visible observations, one direction to try next, and one allowed variation kind; that advice becomes input to the next generation.

Either method may include variation (§12.13) among the enabled refinement elements (up to five). Only while variation is enabled, an amplitude choice (small/medium/large, default medium) is shown; the chosen amplitude applies to every variation generation in the run, and seeds are server-issued.

The Vision method is a finite advisory loop, not quality optimization or automatic acceptance. Vision must not score, rank, accept, reject, praise, condemn, or discard a generated work. Intermediate generations remain `lineage_only`, the final generation enters regular history, and all generations remain in lineage. Derivation metadata records the method, Vision model, observation, and next direction, while the modal shows the latest advice. The model may be changed between runs but remains fixed during one run. Only the human may save, promote, star, or finally choose a work.

## Okugaki: Reciting a Lineage

An okugaki is an append-only, first-person reading attached to one lineage branch from its root to the displayed artwork. It is neither a verdict nor a summary. It describes observable changes between generations and closes by verbalizing what remained invariant across the branch.

- Each generation is read sequentially. The request for generation i contains only generations 0 through i, so later works cannot turn earlier choices into steps toward an alleged final form.
- Inputs are existing lineage edge facts, captions, server-rasterized PNG pairs, and deterministic differences from the v1.80 feature mirror: composition family, primitives, colors, density, angles, and arrangement paths. No new quality metric is introduced. Vision images are bounded to a 512px single work or an aspect-correct 768×384 before/after pair.
- A successful generation response may be cached briefly by model, language, prefix, and image hashes so retrying after a timeout reuses completed work. Different works, models, or prefixes never share entries, and optimization must not combine all generations into one request that exposes later works to earlier observations.
- Invariants are computed mechanically as shared feature and retained-Score elements. The LLM only verbalizes those facts and may not add causality, authorial intent, scores, ranking, praise, or condemnation.
- Japanese and English evaluation terms are scanned as warnings only. A warning never forces rewriting, regeneration, or rejection.
- The server appends the reader model and date as a mechanical signature. Records store the target node, branch snapshot, model, time, language, body, warnings, and fact sheet in the current user's scope.
- Records can be appended or deleted, but never edited. Idempotency keys prevent duplicate saves, and lists are displayed oldest first.
- Okugaki is available only through the explicit Lineage action or `inku-cli okugaki`; `--dry-run` generates without saving. It never affects dh1, rh2, generation, variation, refinement selection, acceptance, quality functions, or branch recommendation.

v1.88 adds no automatic repair or generation branch. Its refinement accounting deliberately limits the new AI reading to a disconnected mirror, making teleological “best branch” narratives less likely to become application behavior.

## 17. Source of Truth

`SPEC.ja.md` is canonical.  This file is the maintained English public version.

When updating the specification:

1. Update `SPEC.ja.md` first.
2. Refresh this English `SPEC.md` to reflect the same intent.
3. Keep public English wording concise and readable.
4. Do not introduce English-only behavior that is absent from the Japanese
   source.
5. Keep current contracts in the specification and chronological implementation
   detail in the changelog.

---

## 18. Changelog

Chronological public release notes are maintained in [CHANGELOG.md](CHANGELOG.md). The more detailed Japanese history is in [CHANGELOG.ja.md](CHANGELOG.ja.md), and [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) is the short developer entry point.
