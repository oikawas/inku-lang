# inku Changelog — v0.1 through v1.71 (2026-04-02 to 2026-05)

**Archive.** The current history is [../../CHANGELOG.md](../../CHANGELOG.md).
The canonical Japanese archive for the same range is
[changelog-v0.1-v1.71.ja.md](changelog-v0.1-v1.71.ja.md).

This archive holds **73 entries**, running from the first idea to the building
of Stage 1.5. **The origin note is here too, near the top.**

---

### v0.1 (2026-04-02)

- The initial concept (conceived at the Museum of Contemporary Art Tokyo, at the exhibition "Sol LeWitt: Open Structure")
- The design of the three-layer pipeline (description -> score -> performance)
- JSON Schema v0.1 drafted
- The first documentation recorded as DDL_concept.md

---

## Origin

Conceived: 2026-04-02, at the Museum of Contemporary Art Tokyo, "Sol LeWitt: Open Structure"
### v0.2 (2026-04-14)

- A first prototype, tested briefly in a client to see whether the concept could be made to run
- The state of the Android implementation recorded (split out into SPEC_v1.md)
- LiteRT-LM 0.10.0 API investigated and implemented
- End-to-end operation confirmed on a Pixel 9

### v0.3 (2026-04-21)

- The overall design as inku-lang begins
- The project name settled as `inku` (inku-lang)
- Section 4 "Plugin design principles" newly added (five principles for avoiding an Emacs Lisp)
- Section 12 "The role of Opus 4.7" substantially rewritten as "The two-stage architecture"
- Section 13 "The design of sway" newly added (motion words against emotion words; the three layers)
- The categories "connection" and "sway" added to Section 3 "What goes in the core"
- Responsibility made explicit in Section 5 "The Base Language question" (Japanese and English are the author's, other languages are the community's)
- Saijiki, interpretation feedback, and after-the-fact coloring added to Section 7 "UI design policy"
- The approach of Section 6 "Separating core from extension" tidied

### v0.4 (2026-04-23)

**Phase 1 implementation begins — the skeleton of the server backend**

- **Repository layout**
  - The `inku-lang` repository created on GitHub (`github.com/oikawas/inku-lang`)
  - Two slots, `server/` and `web/`. `server/` implemented first

- **The Python project: inku-server 0.1.0**
  - Package manager: `uv` (0.11.7) with a src layout
  - Dependencies: anthropic, fastapi, pydantic v2, svgwrite, uvicorn, python-dotenv
  - dev: pytest, ruff
  - Python 3.10+

- **The JSON Score schema (implemented in Pydantic v2)**
  - `extra="forbid"` rejects unknown fields and keeps the schema strict
  - `populate_by_name=True` with aliases avoids reserved words (`from` -> `from_`)
  - Primitives: `line | circle | ellipse | triangle | square | arc`
  - `rotation`: the rotation angle of the whole shape. 0 = horizontal, positive = clockwise, negative = counter-clockwise. Lines, ellipses, squares, triangles and arcs rotate about their center
  - 9 weights, 6 colors, 4 line styles, 4 variation fields (amplitude / frequency / quality / dimensions)
  - `Score.model_json_schema()` in a form that can be handed to an Anthropic tool `input_schema` unchanged

- **Renderer MVP (svgwrite, a 1000x1000 viewBox)**
  - Primitives implemented: line, circle, ellipse, triangle (isosceles), square (rectangle)
  - Coordinate conversion: the `0.0-1.0` ratio times `CANVAS_PX=1000` gives pixels
  - weight mapped to `stroke-width` (hair 0.5 through brush_thick 8.0)
  - color mapped to a hex palette (black #111111, blue #2c3e91, red #a2342a, green #2f6b3a, gray #888888, white #ffffff)
  - style mapped to `stroke-dasharray` (solid = none, dashed = 12,8, dotted = 2,6, dash_dot = 12,6,2,6)
  - Background color `#f7f5ef`, a pale yellow that sets off ink and recalls washi
  - Not yet implemented: arc (the schema has no angle fields) and the actual waveform generation for variation

- **The Stage 2 composer (normalized DDL -> JSON Score)**
  - Model: `claude-haiku-4-5-20251001` through Anthropic tool_use
  - A `submit_score` tool defined and forced with `tool_choice`
  - The system prompt carries a compressed Saijiki mapping, the coordinate system, and the output rules
  - `Score.model_json_schema()` injected directly as the tool `input_schema`

- **15 normalized-DDL fixtures**
  - input.txt and expected.json pairs under `server/tests/fixtures/stage2/{01..15}/`
  - Coverage: all 5 primitives, all 4 styles, several weights (pencil / pen / brush_thick), all 6 colors, 2 kinds of variation (fine + perlin, broad + wave), and multiple instructions (three circles side by side)

- **Tests**
  - `test_renderer.py`: 10 cases, all passing under pytest
  - `test_composer.py`: 15 parametrized fixtures plus tool-schema validation
  - Integration runs only when `ANTHROPIC_API_KEY` is present (`pytest.mark.skipif`)
  - `conftest.py` loads `.env` automatically (python-dotenv)

- **The two-stage architecture settled**
  - Decided as policy in v0.3; v0.4 implements Stage 2 (Haiku 4.5) first, back to front
  - Stage 1 (interpretation by Opus 4.7) not started
  - The `/api/compose` FastAPI implementation belongs to the next phase

### v0.5 (2026-04-23)

**Phase 1 continues — FastAPI and the web client come up**

- **FastAPI endpoints**
  - `POST /api/compose`: `{ddl}` -> `{score, svg}` (the Stage 2 composer joined vertically to the renderer)
  - `GET /health`: liveness (`{ok: true}`)
  - CORS: `http://localhost:*` and `127.0.0.1:*` allowed, by regex
  - Error handling: 502 when the composer fails, 500 when the render fails, 422 on bad input
  - Entry point: `uv run inku-server` starts `uvicorn` on `127.0.0.1:8000` with reload
  - Tests: `TestClient` with `monkeypatch` bypasses the composer, so 5 cases pass without an API key

- **The SvelteKit web client (`web/`)**
  - SvelteKit 2.57, Svelte 5.55 (runes mode), Vite 8, TypeScript
  - A single route `/`: a description textarea, the performance (SVG shown inline), and the score (JSON Score, collapsible)
  - Styling consistent with the renderer palette (background #f7f5ef, ink #111), Japanese fonts first
  - Name: `inku-web` v0.1.0
  - svelte-check: 0 errors, 0 warnings

- **Groundwork for the next stage**
  - `/api/compose` is Stage 2 only; the Stage 1 interpretation endpoint is not implemented
  - Interpretation feedback (after-the-fact coloring), the Saijiki reference window, and side-by-side prev/next are not started in the UI
  - The renderer's sway (perlin / wave) is not implemented either (11 of the 15 fixtures state a variation)

### v0.6 (2026-04-23)

**Phase 1 complete — the end-to-end pipeline runs, and the UI supports repetition**

- **Two LLM backends side by side**
  - After not being selected for the Claude Code hackathon, the implementation moved to a local LLM
  - Stage 2 (composer): `qwen-api` (Qwen2.5-7B) by default, with Anthropic Haiku 4.5 usable alongside
  - Stage 1 (interpreter): `qwen3-api` (Qwen3-8B) by default, with Anthropic Opus 4.7 usable alongside
  - Switched by the environment variable `INKU_LLM_BACKEND=openai|anthropic`
  - OVMS (`http://127.0.0.1:18000/v3`) is OpenAI-compatible, API key `none`
  - qwen3-api is used with a `/no_think` prefix to suppress the thinking trace
  - tool_use is native on Anthropic; on the OpenAI side a `<tool_call>` tag is embedded in the content and extracted by regular expression

- **The Stage 1 interpreter implemented**
  - `server/src/inku_server/interpreter.py`
  - Input: free natural language. Output: short Japanese using only Saijiki vocabulary (normalized DDL)
  - The system prompt carries 4 few-shot examples (emotion words replaced by physical words; screen coordinates as ratios)
  - A 5-case smoke test passes (4 overlap with the examples in the prompt, so there is a tendency to memorize)

- **API endpoints extended**
  - `POST /api/interpret`: free description -> normalized DDL
  - `POST /api/paint`: free description -> normalized DDL -> Score -> SVG (the full pipeline)
  - The existing `POST /api/compose` and `GET /health` are kept
  - Startup environment: `INKU_SERVER_HOST` and `INKU_SERVER_PORT` override the defaults

- **Stage 2 fidelity recorded (qwen-api, strict mode)**
  - 9 of 15 fixtures pass. The typical failures in the remaining 6:
    - confusing center (circle / ellipse) with position (triangle / square)
    - not applying the bounding-box top-left correction when "center" is stated
    - applying a field across all of several parallel instructions at once
  - JSON structural errors (closing `]` where `}` was needed, and the like) are resolved by going through the tool_use API
  - Moving to Haiku 4.5 should improve it, but running on a local LLM at all takes priority

- **Web UI: mode switching, Saijiki reference, and an attempt history**
  - Tabs: free description and normalized DDL (wired to `/api/paint` and `/api/compose` respectively)
  - In free-description mode the interpretation (the normalized DDL) is always shown at the bottom of the left column
  - The Saijiki drawer slides in from the right with 9 categories (forms, inclinations, touches, connections, colors, sways, places, motions, proportions); clicking a chip inserts the word at the caret in the textarea
  - The Saijiki dictionary is split out into `web/src/lib/saijiki.ts`
  - Attempt history: in memory, at most 20 entries, with `◀ N/M ▶` buttons restoring input, output and DDL to a past state
  - A thumbnail row: with two or more entries, 96px square miniature SVGs are laid out along the bottom, and clicking one jumps to it

### v0.7 (2026-04-24)

**Several LLM models supported, Stage 1's still-image rule strengthened, and thinking made visible**

- **The LLM model becomes switchable from the UI**
  - `POST /api/compose`: a `model` field
  - `POST /api/interpret`: a `model` field
  - `POST /api/paint`: `stage1_model` and `stage2_model` fields
  - A `model` keyword argument added to `compose()` and `interpret_detail()`, falling back to the environment default
  - UI (an `interpretation` and a `structuring` dropdown under the mode switch, persisted in localStorage): Qwen2.5-7B / Qwen3-8B / Gemma3-4B / Gemma3-12B

- **Default models**
  - Stage 1: `qwen3-api` (Qwen3-8B)
  - Stage 2: `qwen-api` (Qwen2.5-7B)
  - Gemma3-12B needs 6 hours for the 15 fixtures and is impractical (it stays in the list)
  - Gemma3-4B breaks down on the full Score schema combined with `tool_choice` (malformed brackets, chains of quoted whitespace); it works with a simplified prompt and schema, but the quality is unverified

- **The Stage 1 system prompt: the still-image principle strengthened (SPEC §2, principle 5)**
  - Forbidden verbs: move, set moving, spread, widen, flow, extend, rise, fall, scatter away, sink, paint over
  - Permitted action verbs: place, arrange, draw a line, draw, scatter, fill
  - 5 examples of rephrasing dynamic as static (the moon rises -> a circle in the upper right; petals fall -> scatter fine points)

- **Qwen3 thinking made visible**
  - `interpret_detail()` returns a `(ddl, thinking)` tuple
  - `include_thinking=True` drops `/no_think` and keeps the contents of `<think>…</think>` separately
  - `include_thinking` request field and `thinking` response field added to `POST /api/interpret` and `/api/paint`
  - UI: a "show thinking" checkbox when Stage 1 is a qwen3 model, with the internal thinking shown in the result panel as a faded amber `<details>` (making the author's thinking process visible)

### v0.8 (2026-04-24)

**The renderer performs sway, and the arc primitive**

- **A line's variation is generated in the renderer** (the heart of SPEC §13.8)
  - Converted to a polyline of 80 segments, seeded with SHA-256(model_dump_json)
  - 4 qualities: `wave` (sin), `perlin` (smoothstep 1D value noise), `pink` (two octaves combined), `white` (per-segment hash)
  - amplitude: fine = 4px / medium = 12px / broad = 30px (on a 1000px canvas)
  - frequency: slow = 2 / medium = 6 / high = 14 cycles per line length
  - dimensions: `position_x` or `position_y` alone sways along that axis; naming both sways perpendicular to the line
  - Deterministic: the same Score gives a byte-identical SVG (guaranteed by test)
- **The arc primitive properly implemented**
  - Schema: `angle_start` and `angle_end` (degrees, 0° = east, counter-clockwise positive)
  - Renderer: the arc is drawn with `<path d="M ... A r r 0 large sweep x y">`
  - large-arc-flag from `(end-start) % 360 > 180`; sweep-flag is 0 when `end > start` (counter-clockwise)
  - An arc line added to the composer prompt, with quarter- and half-circle angle examples
- **7 new tests** (arc quarter / half / missing angles; variation perlin / wave / deterministic / quality=none)

### v0.9 (2026-04-25)

**The prompt made non-linear, NVIDIA NIM supported, and arrangement implemented**

#### A structural improvement to the prompt design (the main change)

The problem that a prompt grows without limit as features are added is solved structurally, borrowing the separation of specification from corpus used in machine translation.

- **schema.py becomes the source of truth for the specification**
  - Every field is given a `description` containing the Japanese-to-value mapping
  - The LLM reads the descriptions in the tool schema directly, so SYSTEM_PROMPT no longer has to repeat the field explanations
  - Adding a new primitive means updating the schema only; SYSTEM_PROMPT does not change

- **composer.py: SYSTEM_PROMPT cut down to the procedure alone**
  - 3,942 chars -> 1,072 chars (-73%)
  - The conversion examples are narrowed to the 4 most important patterns (the schema descriptions carry the rest)

- **interpreter.py: EXAMPLE_POOL and dynamic example selection**
  - `EXAMPLE_POOL`: a list of `{keywords, input, output}` tuples (12 at present)
  - `_select_examples(text, k=3)`: scores by how many keywords match the input and takes the top k
  - `_build_system_prompt(text)`: PREFIX plus the k selected examples, built per inference
  - However many examples are added, the prompt length is fixed (PREFIX plus 3)
  - The SYSTEM_PROMPT module variable exposes only the prefix (`/api/prompts` compatibility)

- **The effect on latency**: 322.7s -> 21.5s for the same output (NVIDIA Gemma 4 31B, a 15x speed-up)

#### The NVIDIA NIM provider added

- `google/gemma-4-31b-it` set as the default model for both stages
- Automatic routing by model ID:
  - an `anthropic:<model>` prefix -> the Anthropic API
  - an ID containing `/` -> NVIDIA NIM (`https://integrate.api.nvidia.com/v1`)
  - anything else -> OVMS (the local OpenAI-compatible server)
- UI: a two-step dropdown, provider (NVIDIA NIM / Anthropic / local) then model, persisted in localStorage
- A `PROVIDER_GROUPS` structure added to `web/src/lib/models.ts`

#### The arrangement field (the JSON-size problem of counts)

Expanding N instructions makes the JSON N times larger. Expanding on the renderer side keeps the JSON at O(1).

- **schema.py**: an `Arrangement` model added (`count` / `layout` / `path` / `margin` / `center` / `radius`)
- **renderer.py**: `_anchor()`, `_shift()` and `_expand_arrangement()` expand to N on the renderer side
  - layout: `horizontal` / `vertical` / `radial` / `scatter` (the basic placements)
  - path: `none` / `diagonal` / `wave` / `top_to_bottom` / `left_to_right` / `right_half` (the trajectory)
  - `count=1` is returned as a single shape without expansion. `ge=2` changed to `ge=1` to prevent a validation error
- **interpreter.py EXAMPLE_POOL**: examples that put a quantity into one sentence, and an example of random placement
- **composer.py**: the use of arrangement is required by SYSTEM_PROMPT, and generating several instructions is forbidden

#### UI improvements

- The normalized-DDL tab removed (always free-description mode, `/api/paint`)
- The elapsed seconds shown on a history thumbnail (`elapsed_ms` added to `Iteration`)
- A `GET /api/prompts` endpoint added, so the "prompts (debug)" panel in the output area can show the Stage 1 and Stage 2 system prompts along with the actual input
- The canvas background changed to white (`#f7f5ef` -> `#ffffff`)
- A live timer during inference, and a breakdown after it finishes: "interpretation Xs + structuring Ys = Zs"

---

### v1.0 (2026-04-25)

**Drawing in bulk, a more robust renderer, Stage 1 keeping attributes, a learning mode, and server-side history**

#### Drawing many objects (count up to 500)

The algorithm is improved so that "a hundred lines" or "two hundred circles" can actually be drawn.

- **schema.py**: `Arrangement.count` raised from 50 to 500, and the `_clamp_count` validator with it
- **renderer.py**: the fixed ten-point `_SCATTER_POSITIONS` is dropped in favor of `_scatter_pos(i, seed, margin)`
  - deterministic random coordinates from a SHA-256 hash, for any N
  - the determinism of "same Score, same SVG" is preserved (the seed is the hash of the instruction)
- **interpreter.py**: the rule that rounded "100" or "200" down to about 30 is removed; a stated number passes through as written
- **composer.py**: the count limit in the explanation updated from 50 to 500

#### Renderer: a fallback when a line omits from and to

When the LLM generated a line with an arrangement it sometimes omitted `from` and `to`, which raised a `render failed` error. Fixed.

- `_ensure_line_coords(ins)` added: it infers the direction from the layout and fills in default coordinates
  - `layout="vertical"` -> a horizontal line (`[0.0, 0.5]` -> `[1.0, 0.5]`)
  - anything else (`horizontal` / `scatter` / `radial`) -> a vertical line (`[0.5, 0.0]` -> `[0.5, 1.0]`)
- Called at the entrance to `_expand_arrangement`, before the arrangement is expanded
- The same fallback is applied in `_render_instruction` to a line with no arrangement (the raise is removed)

#### Stage 1 keeps attributes

The problem of color, material, direction and sway dropping out during interpretation is fixed structurally.

- **An `# attributes are kept — dropping them is forbidden` section added**
  - It states that removing emotion words is what normalization means, and that omitting an attribute is an error
  - Colors, touches, thickness, direction and place, sway, and placement pattern are each named as things to keep
- **The quantity rule updated**: an example is added that fits the count into one sentence together with color, material and direction
- **EXAMPLE_POOL**: 12 entries -> 21 (+7)
  - Added: crayon with color and count, pencil with thinness, several trembling lines, right half with color and count, three hundred crayon lines, a horizon composition, chalk with bleeding
- **k: 3 -> 5** — more examples are consulted for an input carrying several attributes

#### The learning mode (an SSE stream)

A background learning feature that extends the corpus automatically.

- **`trainer.py` newly created**
  - `VARIATION_STYLES` (5 styles): poetic, colloquial, abstract, natural-phenomenon and onomatopoeic, in rotation
  - `generate_sample(style_idx, model)`: the LLM generates a description sample in the given style
  - `run_one_iteration(style_idx, model)`: generate, `interpret_detail`, then add to EXAMPLE_POOL
  - `add_learned_example(input, ddl)`: appends to EXAMPLE_POOL and persists to `INKU_LEARNED_FILE`
  - `load_learned_examples()`: injects the persisted corpus into EXAMPLE_POOL at startup
  - `clear_learned_examples()`: deletes only the auto entries, keeping the static examples
  - Backend dispatch: the same anthropic / nvidia / ovms routing as interpreter.py
- **New endpoints in `api.py`**
  - `GET /api/train?n=&model=` -> an SSE stream (`progress` / `result` / `error` / `done` events)
  - `GET /api/train/stats` -> `{"learned_count": N}`
  - `DELETE /api/train` -> clears the corpus
  - `asyncio.to_thread` makes the synchronous LLM call asynchronous
  - `request.is_disconnected()` detects a disconnected client and stops the loop
- **Web UI** (the learning-mode panel)
  - A collapsible panel with an iteration count and a model choice
  - A real-time progress bar (with a shimmer animation) and a log
  - A stop button closes the EventSource, and the server loop stops before its next iteration
  - `onMount` fetches the initial `learned_count`

#### Server-side history (unbounded, paginated)

The capacity limit of localStorage is lifted and history survives across sessions.

- **`api.py`**: `_history: list[dict]` is held in memory and persisted to `_HISTORY_FILE` (`/tmp/inku-history.json` by default)
- Endpoints: `GET /api/history?offset=&limit=` (newest first), `POST /api/history`, `DELETE /api/history`
- **Web UI**: `HISTORY_PAGE_SIZE=10`, `← newer` / `older →` page navigation, and the total count

#### UI improvements

- **The Saijiki button** moved from the header to the top right of the description area (`<div class="input-header">`)
- **The Saijiki token color**: `#111` -> `#2c3e91` (blue) when shown inline

---

### v1.1 (2026-04-25)

**The coerce layer, background color, a color cycle, filling, expanding non-Saijiki words, and UI improvements**

#### coerce.py — a table-driven structural repair layer (new)

`coerce.py` is created to repair automatically, before the renderer sees it, a Score in which the LLM omitted a required field.

- **The design principle**: no per-primitive if/elif. Requirements are declared in a `FieldSpec` dataclass and a `PRIMITIVE_SPECS` table, and applied by a generic loop. Adding a primitive means adding an entry to the table and nothing else
- **`FieldSpec`** declares `name / default / fallbacks (a cross-field substitute) / coerce (a type-normalizing function)`
- **`PRIMITIVE_SPECS`**: the required-field specification for 6 primitives (line / circle / ellipse / arc / square / triangle)
  - a fallback example: when a circle's `center` is missing, `position` stands in
  - type normalization: `_as_coord` / `_as_positive_float` / `_as_positive_size` / `_as_float`
- **`POST_COERCE`**: cross-field constraints (an arc whose `angle_start == angle_end` is corrected by +270°)
- **`api.py`**: `coerce_score()` is called before `render()` on both `/api/compose` and `/api/paint`

#### Closed shapes are filled automatically

- `_CLOSED_SHAPES = frozenset({"circle", "ellipse", "square", "triangle"})`
- `_stroke_attrs()`: `do_fill = ins.primitive in _CLOSED_SHAPES or ins.filled` — a closed shape is filled automatically once a color is stated
- An `Instruction.filled: bool = False` field added to schema.py, for stating a fill explicitly

#### Background color (Score.background)

- A `Score.background: Color = "white"` field added
- `renderer.render()` fills the whole canvas with `COLOR_MAP.get(score.background, BACKGROUND)`
- A background rule added to the Stage 2 prompt

#### A color cycle (Arrangement.color_cycle)

- An `Arrangement.color_cycle: list[Color]` field added (empty by default, meaning every element shares one color)
- `_apply_color_cycle(items, cycle)` overwrites the color by `i % len(cycle)` after the arrangement is expanded
- Applied for every layout (horizontal / vertical / radial / scatter)

#### count raised to 1000

- `Arrangement.count` raised from 500 to 1000, and the `_clamp_count` validator with it
- The prompt text in composer.py and interpreter.py updated to match

#### Stage 2: original_text passed through

- An argument added: `compose(ddl, *, original_text=None)`
- `_build_user_message(ddl, original_text)` builds the user message as `[original]…[normalized DDL]…` when the two differ
- `/api/paint` now passes `req.text` to Stage 2, so the LLM reflects the intent of the original description more accurately

#### Non-Saijiki words expanded by the LLM

- An `# expanding non-Saijiki words` section added to the Stage 1 `SYSTEM_PROMPT_PREFIX`
  - four ways in: shape, texture, structure, and motion turned into placement
  - examples: moon -> a circle; mist -> a bleeding ellipse; forest -> several vertical lines; scatter -> scatter at random
- The fixed-dictionary approach (`expansion.py`) is deleted — the policy turns to trusting the LLM's understanding of meaning
- 9 examples of natural phenomena and poetic vocabulary added to EXAMPLE_POOL (sun, starry sky, horizon with moon, mountain range, forest, snow, flame, city, petals)

#### Web UI improvements

- **Tabs**: three tabs — performance, score, prompts (previously stacked vertically). A new result returns to the performance tab automatically
- **Build number**: an increment mechanism based on a `.build-number` file added to `vite.config.ts`, shown as `#N` at the top left of the header
- **Endpoint and model labels**: "endpoint:" and "model:" stated explicitly
- **Prompt display order**: Stage 1 user input, Stage 1 system, Stage 2 user input, Stage 2 system (the order of the context)

---

### v1.2 (2026-04-25)

**Batch mode, the performance stage made visible, the learning mode retired, and the proportions vocabulary**

#### Batch description mode

- A "description / batch" tab added to the input area
- The batch tab takes several descriptions separated by newlines, with line numbers shown automatically down the left edge
- They are processed in order; during the performance the UI shows "performing N of M", and a stop button interrupts it
- Each result is saved to history, and the last one stays on the canvas

#### The stage made visible during a performance

- The frontend changes from one `/api/paint` call to two calls, `/api/interpret` and `/api/compose`
- During the performance, "interpreting…" and "structuring…" are shown as stage labels in real time, beside the elapsed seconds
- An `original_text` field added to `ComposeRequest`, so Stage 2 can consult the original description when filling attributes in

#### The learning mode retired

- The learning-mode panel removed from the web UI
- The `GET /api/train`, `GET /api/train/stats` and `DELETE /api/train` endpoints removed
- The startup routing that injected into EXAMPLE_POOL removed as well (`trainer.py` stays as an experimental utility)

#### Web UI improvements

- The output tab order changed to performance, prompts, score (it was performance, score, prompts)
- The prompt area enlarged: user input max-height 160px, system prompt 400px, outer frame 680px
- `stage1_model` and `stage2_model` recorded in history (visible in a thumbnail's title)

#### The Saijiki proportions category added

- A new category, `わりあい (proportions)`: tall, wide, full-width, half-width, semicircle, waxing, waning, crescent
- A `# proportions` rule section added to the Stage 1 `SYSTEM_PROMPT_PREFIX` (aspect ratio, line length, and the principle for turning a moon shape into an angle)
- 7 proportion-to-JSON mapping examples added to the Stage 2 `SYSTEM_PROMPT`
- 8 entries added to `EXAMPLE_POOL` (2 aspect ratio, 2 line length, 4 arc moons)
- The `わりあい` category added to `saijiki.ts`

---

### v1.3 (2026-04-26)

**Saijiki snapshots, token display, downloads, and i18n**

#### Saijiki snapshots

**Note**: this feature was removed in v1.11, when the v1 Saijiki specification was settled. What follows stays as the record of v1.3.

A feature for saving and recalling the state of the system prompt at a given moment, under a name.

- **`server/src/inku_server/snapshots.py` newly created**
  - `create_snapshot(name, stage1_prefix, stage2_prompt)` saves with a UUID and a timestamp
  - Storage: `/tmp/inku-saijiki-snapshots.json` (the `INKU_SNAPSHOTS_FILE` environment variable)
  - CRUD through `list_snapshots()` / `get_snapshot(id)` / `delete_snapshot(id)`
- **New API endpoints**
  - `GET /api/saijiki/snapshots` -> `list[SnapshotMeta]`
  - `POST /api/saijiki/snapshots` -> create
  - `DELETE /api/saijiki/snapshots/{id}` -> delete
- **Applying a snapshot**: a `snapshot_id` field added to `InterpretRequest`, `ComposeRequest` and `PaintRequest`; at inference time the matching snapshot's prompt overrides the current one
- **Design**: Stage 1 saves only the prefix (`SYSTEM_PROMPT_PREFIX`), and the dynamic example selection of EXAMPLE_POOL keeps running live. A snapshot captures changes to the prefix only
- **Web UI**: a collapsible snapshot panel added to the Saijiki area, showing the current settings and offering name entry, save, delete, and apply

#### Token tracking

The tokens an LLM consumes are shown while it works and recorded in history.

- **`interpreter.py`**: `interpret_detail()` now returns a 4-tuple, `(ddl, thinking, tokens_in, tokens_out)`
  - Anthropic: `resp.usage.input_tokens` / `output_tokens`
  - OpenAI and OVMS: `resp.usage.prompt_tokens` / `completion_tokens`
  - Both read through `getattr` for safety (`None` for a model that does not report them)
- **`composer.py`**: `compose()` now returns a 3-tuple, `(Score, tokens_in, tokens_out)`
- **`api.py`**: `tokens_in` and `tokens_out` fields added to `InterpretResponse`, `ComposeResponse` and `PaintResponse`
- **Web UI**: the token count is shown live on the "structuring…" label, and `{in}→{out}tok` appears on a history thumbnail

#### Downloads

A finished work can be saved as SVG and as PNG at several resolutions.

- **SVG download**: the original description text is embedded in a `<desc>` tag, inserted just after `<svg ...>` by the `svgWithDesc()` function
- **PNG download**: 4 resolutions (1080 / 2160 / 1024 / 2048px) converted through the browser Canvas API
  - `width` and `height` attributes are injected into the SVG, which is drawn into an `Image`, then a canvas, then `toBlob('image/png')`, then downloaded through an `<a>` element
  - The canvas is prefilled white (`#ffffff`) so the PNG is not transparent
- **UI**: a download bar added below the canvas — a `↓ SVG` button, a `PNG:` label, and `1080 / 2160 / 1024 / 2048` buttons

#### History: model name and token count shown

- A history thumbnail shows the shortened name of the Stage 2 model (`shortModel()`)
- `tokens_in` and `tokens_out` fields added to the `Iteration` type
- The same two added to `HistoryPostBody`, so they are recorded in the server-side history too

#### Hackathon text removed

Every mention of the hackathon is removed from the UI.

#### i18n — Japanese and English language packs

Switching the UI between Japanese and English is implemented, with future languages built into the design.

- **`web/src/lib/i18n/types.ts`**: the `LangPack` interface
  - plain string fields and function fields (`batchCount(n)`, `stageStructuring(tok)`, `tokenSummary(...)` and so on) mixed together
- **`web/src/lib/i18n/ja.ts`** and **`en.ts`**: the Japanese and English packs kept in separate files
- **`web/src/lib/i18n/index.svelte.ts`**: a language store built on Svelte 5 `$state`
  - a `t()` function returns the active pack (every string is referenced as `t().key` in a template)
  - `setLang(code)` with persistence in `localStorage`
  - adding a language means implementing a pack against `types.ts` and registering it in `PACKS`, and nothing more
- **`+page.svelte`**: every hard-coded string replaced by `t().xxx`, with compound derived values written as `$derived.by(() => t().tokenSummary(...))`
- **Header**: a language switch (`日本語` / `English`) placed at the top right

---

### v1.4 (2026-04-26)
A close review of the contents of SPEC.md.

### v1.5 (2026-04-26)


#### UI fixes

- **A canvas max-height added**: `.canvas { max-height: 480px }`. With `aspect-ratio: 1/1` alone the canvas grew to the viewport width (about 560px) and pushed the history strip off screen
- **The history `each` key fixed**: `{#each historyItems as it, i (it.at)}` -> `(it.id ?? it.at)`, resolving duplicate keys when several items shared a timestamp. An `id?: string` added to the `Iteration` type

### v1.6 (2026-04-27)

**The UI redesigned throughout, the color catalog system, and another performance**

#### The layout renewed

The old scrolling page (max-width 1200px) moves entirely to a two-pane layout in a fixed viewport.

```
[header]                            fixed
[left panel 440px] | [right panel flex]   flex: 1 / overflow: hidden
[history strip]                     fixed (bottom)
```

- **Left panel**: description / batch tabs, instructions, perform, vocabulary highlight, interpreted DDL, perform again, and a collapsible statistics section. It scrolls internally with `overflow-y: auto`
- **Right panel**: the tab bar (drawing / prompts / JSON), the canvas area, and the export bar
- **History strip**: 82px thumbnails scrolling horizontally, with `← newer / older →` pagination and a "displayed" badge on the current one

#### The connection-settings popover

The Stage 1 and Stage 2 model choices are gathered into a `⚙ connection settings` button and its popover. The old model row is gone. The snapshot selector was removed in v1.11, when the v1 Saijiki specification was settled.

#### Another performance

A `↺ perform again` button is added directly below the interpreted-DDL box. It calls `/api/compose` only, skipping Stage 1, for the case where the DDL has been edited by hand and is to be rendered again. It shows a progress bar.

#### The zoom UI

Fixed at the bottom center of the right panel's canvas: `−`, `＋` and `⊙` (reset). The range is 0.5x to 3x in steps of 0.25, applied to the canvas container as `transform: scale()`.

#### Navigation and export

- `‹` and `›` buttons placed absolutely at the left and right edges of the canvas (38px circles)
- The counter (N / total) sits under the `›` button, not over the image
- `↓ SVG` and `↓ PNG ▾` (a dropdown: 1080px / 2160px / 1024px / 2048px)

#### The Saijiki drawer renewed

A drawer sliding in from the right edge (width 0 to 280px, `cubic-bezier(0.4,0,0.2,1)` over 0.25s). Category headings are set in a Mincho face with Japanese and English side by side, and the vocabulary sits in minimal token buttons. It toggles from either the "Saijiki" text link in the header or the "Saijiki" button in the left panel.

#### The color catalog system

**Frontend**: the first implementation held the catalog definitions in `web/src/lib/colors.ts`. From v1.25 the server's `GET /api/color-catalogs` is canonical and the frontend uses the list it fetches for display and selection.

```typescript
type ColorMap = Record<'white'|'black'|'blue'|'red'|'green'|'gray', string>;
```

- `default` matches the existing COLOR_MAP of `renderer.py` exactly
- 10 more: Ink & Season / Fresco Study / Open-Air Light / Ink & Porcelain / Cool Material / Dye & Earth / Desert Mineral / Vivid Material / Weathered Heritage / Sea & Stone
- Each catalog holds a `map` (the six-color ColorMap), `swatches` (eight colors for display), and `palette` (eight named colors)
- `default` is treated as a neutral baseline rather than as a cultural standard. The `id`, display name and description of an added catalog are chosen from material, light, technique and drawing behavior, so that no catalog stands for a whole culture through a country, an ethnicity, a food, a festival, an empire or a tourist emblem
- A catalog's `map` puts first the meaning of `white / black / blue / red / green / gray` as abstract colors. A distinctive color is moved into `palette` instead, so that `blue` never becomes pink, `gray` never becomes terracotta, and `black` never becomes navy
- As of Build 265, `open_air_light`, `dye_earth` and `desert_mineral` let the background, the dark color, or a high-chroma accent dominate a work too easily. Future adjustment is to lower the lightness, chroma and background-forming tendency of the core colors rather than to optimize individual prompts
- Build 266 lightens the core colors of those three a little, reducing that dominance. `default.sub` becomes `neutral baseline` for the English UI, and the Japanese description moves to `sub_ja`
- A catalog's detail colors use `palette[].name` as the canonical English display name, with `palette[].name_ja` alongside where a Japanese name exists. The Japanese UI shows `English（日本語）` and the English UI shows `name` alone

The catalog is chosen from the "catalog settings" modal at the right end of the header, and the choice is persisted in `localStorage`.

**Backend**: a `color_map: dict[str, str] | None = None` parameter is added to `renderer.render()`. The first implementation received the selected catalog's color map per performance through a `color_map` field on `ComposeRequest` and `PaintRequest`. From v1.25 a `catalog_id` is received instead and the server resolves the rendering `color_map` from its own catalog definitions.

#### The color nuance `color_hint`

Every `instruction` in the JSON Score may carry an optional `color_hint`. `color` stays the abstract `white / black / blue / red / green / gray` as before, while `color_hint` keeps, briefly, the concrete nuance the instruction contained — "cherry-blossom pink", "a red close to vermilion", "a cold blue-green".

Stage 2 rounds a concrete color to an abstract one while keeping the original nuance in `color_hint`. The renderer receives the selected catalog's `map` and `palette` and, where a `color_hint` exists, uses the palette names and hue hints to choose a closer real color. With no hint, or where it cannot be resolved, the abstract `color` is used as before.

#### Other

- The build number display: `#N` -> `Build N`
- The progress bar: stage indicators (✓ done, ● a running animation), elapsed time, a stop button, and a phase label

### v1.7 (2026-04-27)

**Eight UI improvements — emotion-word hints injected, catalog_id saved in history, and navigation fixed**

#### Emotion words automatically injected as DDL hints

An emotion word is detected at Stage 1 interpretation time and a hint for converting it into DDL vocabulary is appended to the input.

- **`EMOTION_DDL_MAP`** (16 words): "beautiful", "violent", "quiet", "fleeting", "mysterious" and the rest, mapped to concrete weight / variation / color values
- `buildEmotionHint(text)`: `annotate()` extracts the entries with `kind === 'emotion'` and builds the hint string
- Just before the Stage 1 API call, `text + buildEmotionHint(text)` is sent as `augmented`; the displayed text does not change

#### catalog_id saved in history

The selected color catalog is persisted in the history record.

- **`db.py`**: a `catalog_id VARCHAR` column added to `HistoryRow`, applied by `_migrate_columns()` with `ALTER TABLE ADD COLUMN` (a harmless migration for an existing database)
- **`api.py`**: `catalog_id: str | None` added to `HistoryPostBody`
- **Frontend**: `catalog_id` added to the `PaintResult` type and to the `pushHistory` call, saved only when `selectedCatalog !== 'default'`

#### The Saijiki button removed from the header

The Saijiki button in the input area stays; the header link goes.

#### The in-input vocabulary box removed

The "vocabulary found in the input" section (`annot-box`), shown when `result && inputMode === 'single'`, is removed. Emotion words are put to use through hint injection, so showing them inline was judged unnecessary.

#### The history strip gets a dynamic width

`visibleThumbCount = Math.max(1, Math.floor((windowWidth - 40) / 89))` decides how many thumbnails to show from the window width. `windowWidth` is updated on the `window.resize` event (the listener is registered in `onMount` and cleaned up).

#### The direction of the navigation arrows fixed

`‹` (left) means newer and `›` (right) means older. In the old implementation the mapping between `‹`/`›` and `gotoPrev`/`gotoNext` was reversed.

#### Export filenames unified

From a `slugify(input)` basis to a date-and-time stamp.

- The form is `inku-YYYY-MM-DD-HH-MM[-size].ext`
- An `exportFilename(ext, size?)` helper added
- Applied to both SVG and PNG

#### CSS fixes

- `align-self: stretch; min-height: 0` added to `.prompt-area` and `.prompt-pre`, so the prompt tab scrolls vertically as it should
- `.thumb-strip` changed to `overflow: hidden` (horizontal scrolling is dropped; `visibleThumbCount` clips instead)

---

### v1.8 (2026-04-27)

**The touch-to-weight conversion fixed, and the bleeding SVG filter implemented**

#### The touch-to-weight conversion fixed (`composer.py`)

**The problem**: even when Stage 1 correctly produced "a blue crayon vertical line" in the normalized DDL, Stage 2 (composer.py) had no example or instruction at all for converting into the `weight` field, so it always emitted the default `pen`.

**The fix**:
- A "touch -> weight conversion (required)" section added to `SYSTEM_PROMPT` and `SYSTEM_PROMPT_EN`
  - a table matching the 10 material words (hair, pencil, pen, rotring, crayon, chalk, thin brush, thick brush, burin, drypoint) to their weight values
  - 4 conversion examples: crayon, pencil, chalk with bleeding, thick brush
- Touch examples added to `EXAMPLE_POOL`: thick brush, rotring, chalk, burin, drypoint in Japanese, and thick-brush, chalk, burin, drypoint in English

**Files touched**: `server/src/inku_server/composer.py`, `server/src/inku_server/interpreter.py`

**Next step**: add touch fixtures (16 through 20) under `server/tests/fixtures/stage2/` to prevent a regression.

#### Bleeding (quality=pink) implemented as an SVG feGaussianBlur (`renderer.py`)

**The problem**: even when `variation.quality = "pink"` was present in the JSON Score, the renderer generated no blur filter.

**The implementation**:
- A `BLUR_STD` dict: `{fine: 2.0, medium: 6.0, broad: 15.0}` (stdDeviation in pixels)
- `_needs_blur(v)`: returns True when the quality is pink
- `render()`: elements that need a blur are given an id, and `_inject_blur_filters()` injects the filter definitions into `<defs>` together
- `_inject_blur_filters()` handles all three forms `<defs />`, `<defs/>` and `<defs>`, absorbing the dialect differences in svgwrite's output

**The filter design**: one filter definition per amplitude (`blur-fine` and so on) is shared rather than one per element, keeping the SVG small.

---

### v1.9 (2026-04-29)

**The UI polish branch — the drawing experience tidied, history management strengthened, and operations made safer**

#### Terminology tidied

The wording for generating a work in the UI moves from "perform" toward "draw".

- The main action button is "draw"
- The button that re-runs Stage 2 only is "draw from the interpretation"
- The redraw button uses a blue coloring so it is distinguishable from the ordinary draw button
- The output tabs and the on-screen wording are updated to center on "draw"

#### Button placement tidied

- The header's "connection settings" renamed "settings"
- The Stage 1 and Stage 2 model choices become an independent "model selection" button
- "Model selection" shows the model choices and nothing else
- "Settings" shows database settings, plugins, user management, and other
- The "color catalog" button is placed in the instruction area
- The "Saijiki" button moves to the interpretation (normalized DDL) area, to the left of the edit button
- The "new" button is given a slightly more prominent warm coloring

#### The color catalog UI

- The color catalog dialog becomes two panes
- The catalog list on the left, the detail colors of the selected catalog on the right
- The name changes from "catalog settings" to "color catalog"

#### The bird animation

- Besides the small bird inside the progress bar, a bird now flies across the upper left of the screen while drawing or redrawing
- The bird is made larger, slower, and more unhurried
- A "show the bird" on/off switch added under settings > other

#### The settings dialog extended

- Database tab: an input UI for SQLite and PostgreSQL, and a connection-test display
- Plugins tab: a list, and add and remove controls
- User management tab: username, password and group, with add and remove for users and for groups
- Other tab:
  - show the bird, on or off
  - the alpha channel on a white background, on or off
  - save as a new version even when the interpretation is edited again, on or off

**Note**: as of v1.9 the database, plugin and user-management panels were prototype UI in the frontend. v1.10 connected user management to the database and API; changing the database settings and loading plugins remained unconnected.

#### The history strip and history management

- The history title becomes a pill, easier to see as a button
- Hovering a history thumbnail shows what was saved:
  - the Stage 1 and Stage 2 models
  - the time it was saved
  - the seconds it took
  - the color catalog
  - tokens in and out
  - a preview of the input
- The page-navigation wording becomes "N newer" and "N older", following the number of columns shown
- A history-management dialog added:
  - a thumbnail tab, tiled like the history strip
  - a list tab, as a table
  - search
  - multiple selection
  - move to trash, restore, and permanent deletion
- The dialog's height is fixed, so its vertical position no longer moves as the number of search results changes

#### The history database and API

- A `history.trashed` column added
- `GET /api/history?trashed=true` supported
- `POST /api/history/trash`
- `POST /api/history/restore`
- `POST /api/history/permanent-delete`
- Fetching everything for history management pages in units of 100, matching FastAPI's `limit <= 100`

#### PNG export

- The white-background prefill on PNG export follows the "alpha channel on a white background" switch under settings > other

#### The build number

- The automatic increment of `.build-number` is dropped
- `web/BUILD_NUMBER` becomes tracked by git
- The practice becomes to update `BUILD_NUMBER` explicitly whenever the application changes

#### The state of the known issues from the v1.9 review

- The database and plugin status in the settings dialog was connected to a read-only API in v1.11
- Saijiki snapshots were removed until the v1 Saijiki specification was settled
- History management moved to server-side search and paging in v1.11
- A failure to save an output file has been recorded in the server log since v1.11
- A per-line failure in batch drawing has been kept visible in the UI since v1.11

### v1.10 (2026-04-29)


#### Authentication and user management

The settings > user management tab moves from a prototype UI to an administration screen connected to the database and API.

- User accounts are persisted in the database
- Account attributes:
  - username
  - email address
  - password
  - user kind
  - the user group they belong to
- User kinds:
  - administrator: all settings, user management, and adding, removing and managing user groups
  - group lead: management of ordinary users within their own group
  - user: making works
- A user group is treated as a class or an event team. Sharing works within a group is a future feature
- Passwords are hashed with PBKDF2-SHA256, a 16-byte salt, and 310,000 iterations
- Only the SHA-256 hash of a session token is stored in the database
- At first startup, a bootstrap admin is created only when no user exists and `INKU_BOOTSTRAP_ADMIN_PASSWORD` is set
  - username: `admin`
  - email: `admin@local`
  - password: the value of `INKU_BOOTSTRAP_ADMIN_PASSWORD`, at least 8 characters
  - `INKU_BOOTSTRAP_ADMIN_USERNAME` and `INKU_BOOTSTRAP_ADMIN_EMAIL` override the username and email
  - with `INKU_BOOTSTRAP_ADMIN_PASSWORD` unset, no admin with a known default password is created
  - `INKU_ALLOW_INSECURE_BOOTSTRAP_ADMIN=1` must be stated explicitly to keep using the old `inku-admin` in local development

#### The user-management API

- `POST /api/auth/login`
- `GET /api/auth/me`
- `PATCH /api/auth/me/profile`
- `PATCH /api/auth/me/settings`
- `GET /api/auth/me/batch-prompt-history`
- `PUT /api/auth/me/batch-prompt-history`
- `POST /api/auth/logout`
- `GET /api/user-groups`
- `POST /api/user-groups`
- `DELETE /api/user-groups/{group_id}`
- `GET /api/users`
- `POST /api/users`
- `PATCH /api/users/{user_id}`
- `DELETE /api/users/{user_id}`

Role control:

- An admin can manage every user and every group
- A group lead or a user cannot use the user-management API
- Only an admin can use the plugin-storage update API

#### The user-management UI

- The login UI is shown while nobody is logged in
- Once logged in, the current user, role and group are shown
- The profile dialog opens from the user icon menu in the app rail, where one's own email address and password can be changed
- For an admin:
  - an add-user panel
  - a change-user panel
  - change and delete on the user list
  - add a group
  - delete a group
- The database tab is shown to admins only
- The user-management tab is shown to admins only
- The plugin tab is shown to everyone, but only an admin may change the settings

#### History saved per user

The history database is separated by user.

- A `history.user_id` column added
- A `history.starred` column added
- Existing history moves to the admin's ownership in a first-startup migration
- `GET /api/history` returns only the logged-in user's history
- `GET /api/history?starred=true` returns only that user's starred history
- `POST /api/history` saves as that user's history
- `PATCH /api/history/{item_id}/star` applies only to that user's history IDs
- `DELETE /api/history`, trash, restore and permanent-delete apply only to that user's history IDs
- Naming another user's history ID changes nothing
- Deleting a user who has history is refused, to prevent orphaned data
- Output files move to `outputs/{user_id}/YYYY-MM-DD/...`
- The migration script for the old `history.json` also takes it in as the admin's

### v1.11 (2026-04-29)

**The settings UI connected to real behavior**

Settings > database and plugins move from a prototype state to showing the server's state.

- `GET /api/settings/status` added
- Only an administrator can read the settings status
- The database tab shows the current SQLAlchemy backend, driver, masked URL and database
- It states explicitly that the database connection cannot be changed at runtime and that the server must be restarted after `INKU_DB_URL` changes
- The plugin tab reports, as server state, that the reference server has no loader implemented
- The prototype UI that added, removed and enabled plugins in the frontend alone is retired
- When nobody is logged in, or the saved session is invalid, a standalone login screen is shown instead of the application
- The password field in the login dialog can show or hide what is typed
- An inku-generated SVG is cropped and placed behind the login screen, improving it as a standalone page
- The login panel is adjusted to compact dimensions and restrained spacing, suited to use at work
- The password visibility toggle changes from a text button to an icon button
- A language switch added to the login screen, with the login form wording available in Japanese and English
- The history-management dialog stops loading all history and renders only the current page, through server-side search and paging in units of 100
- The Saijiki snapshot feature is removed until the v1 Saijiki specification is settled: the API, the frontend state and the `snapshot_id` wiring are all withdrawn, to be reimplemented under the later specification
- Saving output files separates SVG, JSON, input and DDL from the PNG conversion, and records a missing `cairosvg`, a filesystem error, or a PNG conversion error in the server log
- Batch drawing shows a per-line success and failure summary, so the user can see which input line failed and why
- The batch input area aligns the character settings of the line numbers and the textarea so they cannot drift apart, and a long line scrolls horizontally rather than wrapping
- The right panel's old "score" tab is renamed `JSON`. The JSON Score is shown with line numbers, coloring keys, strings, numbers, booleans and null differently
- The web UI runs as two processes, a SvelteKit frontend and a FastAPI backend, with the frontend proxying `/api/*` to the backend in development

### v1.12 (2026-04-29)

**History SVG saved on the server**

The path that saved the SVG sent by the web UI into the database at history-save time is retired.

- After Stage 1, Stage 2 and the SVG render, `/api/paint` saves to the history database itself where required
- `history_id` and `history_at` added to the `/api/paint` response
- Single and batch drawing in the web UI display the result and leave the history save to `/api/paint` on the server
- The web UI does not send the SVG back to `/api/history`
- `POST /api/history` is kept for compatibility, but the `svg` in the request is not trusted: the server re-renders the SVG from the JSON Score it received and saves that
- The color catalog was passed to the server as `color_map` in the first implementation. From v1.25 a `catalog_id` is passed and the server resolves `color_map` from its own canonical catalogs. The `color_map` itself is not saved as history metadata
- Build 71

### v1.13 (2026-04-29)

**Authentication required on the generating APIs**

The APIs that call an LLM or generate a drawing are limited to logged-in users.

- `/api/interpret` requires a valid Bearer session
- `/api/compose` requires a valid Bearer session
- `/api/paint` requires a valid Bearer session whether or not it saves
- The web UI's redraw call (`/api/compose`) goes through `apiFetch`, which carries the authentication header
- An unauthenticated call to a generating API returns 401
- Build 72

### v1.14 (2026-04-29)

**The session cookie made HttpOnly**

The web UI no longer stores the session token in localStorage.

- `/api/auth/login` does not return the token in the response body; it issues an `inku_session` cookie
- The `inku_session` cookie carries `HttpOnly`, `SameSite=Lax` and `Path=/`
- With `INKU_SESSION_COOKIE_SECURE=1` the cookie also carries `Secure`
- The cookie's max-age comes from `INKU_SESSION_COOKIE_MAX_AGE`, 30 days by default
- The database's `user_sessions` expire by the same `INKU_SESSION_COOKIE_MAX_AGE`
- An expired database session cannot authenticate and is deleted when it is touched
- Expired database sessions are also swept when a new session is created
- `/api/auth/me`, the generating APIs, the history APIs and the administration APIs all authenticate by cookie session
- An Authorization Bearer header is still accepted, for compatibility
- `/api/auth/logout` deletes the database session and the cookie
- The web UI holds no token value in JavaScript state or localStorage, even after login
- Build 73

### v1.15 (2026-04-29)

**The history database as canonical, and output files as by-products**

The policy is made explicit: the history database is canonical and output files are by-products.

- The `input`, `ddl`, JSON Score, SVG and metadata of a history entry are canonical in the database record
- The `output_path` is treated as a hint about where a by-product was written
- The SVG, JSON, input, DDL and PNG files are artifacts regenerable from the database history
- `POST /api/history/rebuild-output-files` added, regenerating the artifacts of a given history ID from the database
- A failure to save an artifact is not treated as a failure to save the history, and is recorded in the server log
- Build 74

### v1.16 (2026-04-29)

**The initial administrator account must be stated explicitly**

The bootstrap admin created with a new database exists only when an initial password is stated through an environment variable.

- With `INKU_BOOTSTRAP_ADMIN_PASSWORD` unset, no admin with a known default password is created
- `INKU_BOOTSTRAP_ADMIN_PASSWORD` must be at least 8 characters
- `INKU_BOOTSTRAP_ADMIN_USERNAME` and `INKU_BOOTSTRAP_ADMIN_EMAIL` are used only when the bootstrap admin is created
- `INKU_ALLOW_INSECURE_BOOTSTRAP_ADMIN=1` must be stated explicitly to keep using the old `inku-admin` in local development
- The guidance about a default password is removed from the bootstrap-admin explanation in the settings screen
- Build 75

### v1.17 (2026-04-29)

**The user-management tab reflects the current state**

The user-management tab is adjusted so that it follows the current state of the server database more readily.

- `/api/auth/me`, `/api/user-groups` and `/api/users` are refetched every time the tab is opened, switched to, or reloaded
- The tab fetches with `cache: no-store`, and a request ID prevents a stale response arriving late from overwriting the list
- A manual reload button added to the tab
- The user list and the logged-in user's role show the values `admin` / `group_lead` / `user` rather than a translated label
- pytest uses a temporary SQLite database under `/tmp` by default, leaving no test users or test groups in the real database
- Build 77

### v1.18 (2026-04-29)

**Saijiki vocabulary handling refined, and the right panel made easier to use**

Toward the v1 Saijiki specification, inserting vocabulary, previewing it, and editing the interpretation are tidied.

- Hovering or focusing a vocabulary button in the Saijiki drawer shows a preview of that word's drawing effect, an explanation of it, and a short example of use
- An "inclinations" category added to the Saijiki, shown below "motions" and above "proportions"
- A `rotation` field added to the JSON Score schema, so lines, ellipses, squares, triangles and arcs can rotate about their center
- Clicking a Saijiki word always inserts at the current caret in the interpretation (normalized DDL) box
- The interpretation box loses its edit button and becomes always editable
- Saijiki words inside the interpretation box are highlighted in a restrained per-category color
- The interpretation box's custom caret is thickened so it is not lost against a highlighted word
- "New" clears the instruction, interpretation, drawing, prompt and JSON views and shows a placeholder image on the drawing tab

The right panel and the header are tidied along with it.

- The old export bar is renamed the status bar and shows the Stage 1 and Stage 2 model names and the color catalog name
- While a history entry is displayed, the status bar shows the models, color catalog and canvas kind that entry used; changing the model or catalog selection makes the current selection take precedence
- The model-selection dialog shows the more formal model names, and its width is adjusted to the measured character count
- The color-catalog and model-selection dialogs lose their close button; cancel and confirm buttons make discarding or committing a change explicit
- A clipboard-copy icon added to the Stage 1 and Stage 2 user inputs on the prompt tab
- While the prompt or JSON view is shown, a safety margin keeps the left and right history-navigation buttons from overlapping the content
- Clicking the logged-in username in the header opens a menu offering log-off
- Build 100

### v1.19 (2026-04-30)

**The Stage 1.5 intermediate filter, and expansion from mathematical, musical and painterly technique**

A deterministic intermediate filter is added between Stage 1 and Stage 2.

- Stage 1's normalized DDL is converted into an expanded normalized DDL before it reaches Stage 2
- `ランダム` and `random` are treated as forbidden words in normalized DDL and replaced by an explicit placement
- `/api/paint` passes the expanded DDL to Stage 2 and keeps the same DDL in the response and in history
- When DDL is handed to `/api/compose` directly, it also goes through the intermediate filter before Stage 2
- Mathematical and geometric expansion:
  - the golden ratio
  - the rule of thirds
  - the silver ratio
  - a regular pentagon
  - Fibonacci-like quantities
  - radial placement, concentric circles, diagonals, undulating paths
- Expansion from musical technique:
  - contrary motion in counterpoint
  - the harmonic series
  - the displacement of a canon
- Expansion from painterly technique:
  - one-point perspective
  - perspective
  - light and shade
  - drawing
  - pointillism
  - the thick application of oil paint
  - watercolor
  - patchwork
  - fresco
  - sumi ink
- Rules and examples for landing these on existing JSON Score fields are added to the Stage 2 prompt
- `server/src/inku_server/ddl_expander.py` added and made a test subject as a deterministic converter
- As a follow-up within v1.19, putting every technique in every time is dropped in favor of selecting a few technique layers from a deterministic seed built from the input DDL
- As a follow-up within v1.19, `中心` and `中央` stop meaning the center of the canvas and are replaced by a dynamic focus per input DDL
- Build 103

### v1.20 (2026-04-30)

**Drawing texture strengthened, a contrast-preserving filter, and the UI context tidied**

The renderer stops expressing `weight` through stroke width alone and draws the difference between touches with SVG attributes, filters and multiple stroke layers.

- `pencil`: a low opacity and a fine dash express a pale pencil line
- `chalk`: a dash and a light blur filter express a powdery chalk line
- `crayon`: a rubbed secondary stroke laid over the main one expresses the grain of crayon
- `brush_thick`: a thick main stroke, a pale secondary one and a light blur give the brush its thickness
- `rotring`: angular line ends move it toward a drafting line
- `hair`: extremely fine and low in opacity, for a delicate line

A contrast-preserving rule is added to Stage 1 and Stage 2 to avoid a normalization in which the drawing color merges into the background and the drawing effectively disappears.

- When the background and the drawing share a color, the side with the smaller area is changed as a rule
- A white line on white, or a small white shape on white, moves the line or the small shape toward black, blue, red or green — whichever suits the context
- Even where white is the subject, as with snow or stars, a small element moves toward blue or another color rather than the background moving
- Only where a white subject shape dominates, as with a large white moon, may the background move to blue or black
- A gray background is not an easy refuge for contrast. Gray is allowed only where the input or the normalized DDL states it
- The same criterion is added to the Stage 2 prompt examples, so `background` and an instruction's `color` do not merge there either

To reduce the bias toward perfect circles in particles, points, grains, stars, snow, sand and petals are spread across ellipses, small squares and short lines, and `rotation` is given to ellipses and squares so they do not stay fixed to horizontal or vertical symmetry.

To relieve the concentration of the UI implementation in one enormous component, the main display units are split into components in stages.

- `AuthPanel`: the login panel shown while logged out
- `HistoryStrip`: the history strip along the bottom
- `HistoryManager`: the history-management dialog
- `SettingsModal`: settings, model selection, user management
- `ColorCatalogModal`: color catalog selection
- `SaijikiDrawer`: the Saijiki drawer
- `CanvasPanel`: the drawing, prompt and JSON panel
- `OutputTabsContent`: the prompt and JSON views
- `ConfirmDialog`: the confirmation dialog for deletion, restoration and the like
- `InputPanel`: the description / batch switch, the instruction input, and single-drawing progress
- `BatchPanel`: batch input, line numbers, the highlight on the current line, the in-progress interpretation, and the failure report
- `DdlEditor`: the interpretation box, the Saijiki button, the vocabulary highlight, and draw-from-interpretation
- `HistoryThumbnail`: the clipping of a history thumbnail's SVG and the difference in display size

The UI context of batch drawing and single description is tidied.

- The "interpretation in progress" field for the current line is shown only while a batch is running
- That field is read-only and carries the per-category Saijiki highlight
- The batch input is read-only while running, and the source line being processed is highlighted
- The batch panel does not show the ordinary interpretation-edit box, the Saijiki button, or the `draw from interpretation` button
- Clicking a history entry during a batch does not stop the batch; the entry's drawing and description can be viewed
- The batch's running state is separated from the displayed tab (`inputMode`), so the contents of the batch instruction box survive a switch to a history view
- When the batch ends, the in-progress interpretation field closes while the batch input and the failure report remain

Svelte's existing accessibility warnings are tidied until `npm run check` reports 0 errors and 0 warnings.

`web/src/routes/+page.svelte` splits its display units into child components, leaving the page itself responsible for orchestrating API calls, history, authentication, settings and run state.

The SVG clipping of a history thumbnail is gathered into `HistoryThumbnail`. Calling `clippedHistorySvg()` through the template of `+page.svelte` is retired in favor of a per-thumbnail `$derived` holding the processed SVG.

- Build 124

### v1.20 (2026-05-05)

**The rendering engine revised, hashes in the history UI, and control over automatic DDL repair**

The revision of the rendering engine takes the approach of converting the meaning of the input into general drawing parameters rather than branching on individual keywords.

- People, faces and animals are not drawn as objects but handled as `Score.presence` — `kind`, `intensity`, `center`, `symmetry`, `gaze_pressure`, `contour_density`
- `presence` does not turn eyes, nose, mouth, proportions, limbs, ears or a tail into instructions. It hands the renderer a sense of presence, a center of gravity, symmetry, the pressure of a gaze, a group, and contour density
- The renderer performs `presence` as faint arcs, line fragments, an edge-biased focus, and asymmetric contour density. It avoids fixed silhouettes such as a vertical line with a small ellipse, a stick figure, a head and body, wings and a tail, or a ring of identical ellipses
- A `polygon` primitive is added; polygonal vocabulary is gathered into `polygon` with `sides=5-8` rather than split into individual pentagon and hexagon primitives
- `motion_energy` restores movement by strengthening `trajectory`, `rotation`, `diagonal`, `wave` and `asymmetry` rather than by increasing count or density
- For quiet, presence, membrane, fog, memory and shadow inputs, density and symbolic shapes are held back so that dense vertical lines, large filled closed shapes, vertical rain lines, and large fallback squares or triangles do not overwrite the subject
- Context energies such as `leaf_grain`, `silence_layer`, `hard_edge` and `playful_motion` are treated as small auxiliary layers keyed to context words rather than to line numbers

The Stage 2 contract is strengthened as well.

- Adjectives, motion words and texture words apply to the main shape the DDL states
- No auxiliary line, auxiliary shape, or differently colored instruction absent from the DDL may be added because of 「震える」, 「揺れる」, 「滲む」, 「太い」 or 「細い」
- Because a prompt constraint alone recurs depending on the model, a deterministic contract guard is added to the composer
- The guard applies only where the DDL contains a single explicit primitive family together with a motion or texture modifier
- Where an explicit color is present, only the instructions matching that color and primitive are kept, and unrequested auxiliary lines, auxiliary shapes and differently colored instructions are dropped
- Where a line carries 「震える」 and Stage 2 has dropped the variation, `quality=perlin` and `dimensions=["position_x","position_y"]` are supplied on the main line instruction
- The guard is not applied to DDL with several motifs, so a rich layered output is not broken

The interpretation box and DDL redrawing are tidied.

- `auto_repair` added to `ComposeRequest` and `PaintRequest`, `true` by default
- An "automatic repair" checkbox added to the interpretation box in the web UI; when it is off, `coerce_score()` is not applied
- On the description tab, `new` shows an empty interpretation box while leaving the Saijiki, DDL editing, automatic repair and draw-from-DDL controls usable
- The `draw from DDL` button sits below the interpretation box, and the buttons above it are removed
- `draw from DDL` does not call Stage 1; it passes the DDL in the interpretation box to Stage 2 and the renderer, and does not reinterpret the natural-language instruction field

Hash display in history and the status bar is tidied.

- To the right of the star in the status bar, the displayed image's `render_hash_short` is shown, with a button that copies the full `render_hash`
- The hash button is disabled before anything is drawn, and where there is no hash
- After an ordinary drawing is saved to `/api/history`, the save response updates `result.render_hash`, `render_hash_short`, `history_id` and `history_at`
- The status bar just after a drawing therefore shows the same canonical database hash as the status bar after visiting another history entry and returning
- Clicking the image area in the history dialog selects that entry and returns to the main screen
- A "latest" button added to the history strip and the history-management dialog
- After looking at another tab or at history during a batch, returning to the batch tab shows the newest drawing automatically at the next completion

The confirming behavior of the color catalog UI changes.

- After the selection changes in the color catalog dialog, clicking outside it counts as "save"
- The cancel button still returns to the selection as it was when the dialog opened
- The color catalog button shows the name of the current catalog, abbreviating a long one

The main fixes confirmed by benchmark:

- Build 342 -> 345: the presence abstraction holds back the objectification of people and animals while keeping presence, center of gravity and contour density
- Build 346 -> 347: the quiet density governor and symbolic-shape tempering hold back dense vertical lines and the dominance of large fallback squares and triangles
- Build 348: `polygon` and `motion_energy` are introduced, restoring movement without increasing count
- Build 349-351: a five-case polygon bench confirms `polygon` output, and the context energy is adjusted for fallen leaves, a corridor, steel framing, and the shadow of a bicycle
- Build 351-355: following an investigation into recurring common shapes, the presence auxiliary layer is adjusted so it does not converge on a fixed silhouette or a ring-like mark
- Build 356-357: after investigating three unrequested horizontal lines appearing with automatic repair off, the policy of removing unrequested auxiliary instructions through the Stage 2 contract guard is added
- Build 386-395: quality improvement proceeds through quality metrics and general Score repair rather than per-case branching. `constraint_adherence`, `negative_space_pressure`, `motion_energy`, `color_resonance`, `visual_event` and `figurative_risk` are recorded in the bench summary, and fallback and timeout samples are separated from the quality judgment
- Build 386-391: the density and negative-space governors are strengthened for quiet, membrane, fog, memory, shadow and neon-blur inputs, holding back dense vertical lines, particles, large closed shapes and dominant background planes. A neon bleed is controlled to a density that reads as a transparent streak rather than a clump of grains
- Build 392-393: where a motion word arrives with no effective trajectory, a motion floor supplies a small group of directional `arc`s rather than increasing the count. A requested color present only in `color_cycle` is promoted to a main stroke, strengthening how the color reads
- Build 394: visual-event repair is not fixed to a small arc; where the existing Score lacks an angular element, a small `polygon` is used instead. This avoids fixing the vocabulary onto small red ellipses and pale auxiliary arcs
- Build 395: where repeated lines dominate the screen, the line group itself becomes the event through `rhythm_spacing=syncopated`, preserved negative space, directional fading and small gaps at the endpoints, without increasing the element count. The visual event improved for subjects such as a wind chime or neon, while low-chroma, curved and memory-like subjects such as a beach or the memory of waves tend to lose their negative space and remain the next thing to adjust
- Build 359

### v1.21 (2026-04-30)

**The app rail, dark mode, per-user UI state, starred history, and batch progress made visible**

The fixed header at the top of the screen is retired and gathered into a collapsible app rail on the left.

- The application name, build number, user actions, settings, language switch and theme switch are placed in the left rail
- The rail expands and collapses, widening the vertical working area in ordinary use
- For checking during development, the build number stays where it is always visible, even with the rail collapsed
- The application name reads `inku` when collapsed and `inku-lang` when expanded
- The `inku` part is shown at a fixed width so that its position and size do not change between the two states
- The username becomes a menu, from which log-off can be chosen
- Settings use a gear icon and user actions a person icon

The history area can be folded away.

- The history strip along the bottom can be collapsed when it is not needed
- With history closed, the drawing, description and batch areas have more room
- Showing history again keeps the current paging and star-filter context

Light and dark modes are added.

- The theme switches from the collapsible app rail on the left
- Dark mode changes the coloring of the background, panels, input fields, modals, history, status bar and buttons
- The SVG and PNG output of the drawing itself is unaffected by the theme; the Score's background color and drawing colors govern
- In dark mode the history-navigation buttons, zoom buttons, zoom-level display and the draw buttons on the description and batch panels keep their contrast
- The hover metadata popup in the history-management dialog also switches to dark-mode colors

The light or dark mode is saved on the server as part of the user's information.

- The UI theme is saved in `user_accounts.ui_theme`
- The current user's theme is read from `/api/auth/me` at login
- Switching the theme saves it with `PATCH /api/auth/me/settings`

The batch panel's instruction history moves to per-user storage on the server.

- Up to 20 instruction entries are saved in `user_accounts.batch_prompt_history`
- `GET /api/auth/me/batch-prompt-history` and `PUT /api/auth/me/batch-prompt-history` are added
- Choosing an entry from the dropdown restores it into the instruction box at that moment
- The restore button is retired
- Starting a new work clears the batch instruction box and any displayed error
- The batch sample is shown as three input examples, matching line numbers 1 to 3

Starring is added to history.

- A `history.starred` column is added, and the star state is saved in the database
- `PATCH /api/history/{item_id}/star` toggles it
- `GET /api/history?starred=true` returns starred entries only
- A star can be seen and toggled in the status bar, at the top right of a history-strip thumbnail, and at the top right of a thumbnail in the history-management dialog
- A filter showing starred entries only is added to the history strip and the history-management dialog

The history-management dialog is made easier to read.

- The dialog is widened, giving the thumbnail grid and the list more horizontal room
- The hover metadata popup becomes fixed-position and is clamped inside the viewport, so it is not cut off by a modal or a screen edge
- The popup colors are adjusted for dark mode
- The delay between hover and popup is lengthened

Progress during a batch is made clearer.

- The token count is shown in the batch panel too
- The current line's token count and the running total are shown separately
- A crab mascot appears on the batch progress row
- The crab moves left and right, raises a claw, moves its eyes, burrows into sand, and bows
- The crab is treated as a creature that moves sideways, so it is not mirrored to face its direction of travel

Stability in server operation is adjusted.

- `inku-server` starts FastAPI with reload disabled by default
- `uvicorn` reload is enabled only for `INKU_SERVER_RELOAD=1`, `true`, `yes` or `on`
- Running under systemd assumes an ordinary single `uvicorn` process with no reloader
- The `inku_session` cookie's max-age and the database session lifetime move together
- A database session becomes invalid once it passes `INKU_SESSION_COOKIE_MAX_AGE`, and is deleted when it is touched
- Expired sessions are also swept when a new session is created

- Build 151

### v1.22 (2026-05-01)

**Server save load controlled, history search made fast, history paging stabilized, state separated, and a demo tab**

Saving output files is separated from saving the database history, and the background save queue is bounded.

- `/api/paint` treats the save to the history database as canonical and the SVG, JSON and PNG artifact files as by-products
- The artifact-saving executor has a bounded worker count and queue length
- When the queue is full, the database history save takes priority and the artifact save alone can be skipped
- `/api/settings/status` returns the worker count, queue limit, slots in use and slots available under `output_save`

History search uses SQLite FTS5.

- A `history_fts` virtual table is created, indexing `input`, `ddl`, `stage1_prompt`, `stage2_prompt`, `model` and `catalog_id` from `history`
- Insert, update and delete triggers keep the FTS index in step with the history database
- A short search term, or an environment without FTS, falls back to the earlier `LIKE` search

Paging in the history-management dialog is stabilized.

- Page movement, search, view kind and star filtering each call `/api/history` with the conditions explicit at the time of the request
- A response that arrives late is not reflected in the display unless it belongs to the most recent request
- The search debounce effect calls fetch through `untrack`, so it does not race with the state updates of paging and star filtering
- The page size stays at 100
- History-management thumbnails use `content-visibility`, holding down the cost of rendering off-screen SVGs while still showing 100 at a time

To keep the page orchestration from growing, the state and effects specific to the history-management dialog are split out into `HistoryManagerState`.

- `web/src/lib/historyManagerState.svelte.ts` is added
- The active and trash views, paging, search, star filtering, selection, and the discarding of stale responses by request id are gathered into that state
- `+page.svelte` keeps as its main responsibility the cross-page connections: the history strip, the delete and restore confirmations, and reflecting changes into the displayed entry

A demo tab is added beside description and batch.

- `DemoPanel` is created, separating the demo UI into its own component
- The demo works by generating a short instruction from a seed phrase, drawing one work from it, waiting for the display interval, and repeating
- Demo settings are saved per user in `user_accounts.demo_settings`
- The settings are: whether to save to the database, whether to save artifact files, the model that generates the instruction, the seed phrase, and the display interval
- The defaults are no database save, no file save, and a 30-second interval
- `GET/PUT /api/auth/me/demo-settings` is added
- `POST /api/demo/instruction` is added, generating a demo instruction from a seed phrase
- While the demo runs, the generated instruction and the highlighted normalized DDL are shown
- Starting the demo clears the drawing, prompt and JSON views as "new" does, and shows a placeholder on the drawing tab
- The demo tab has no "new" button
- The prompt and JSON tabs remain readable during the demo, so the generated instruction and the normalized DDL can be inspected
- The history strip is locked while the demo runs, and the lock is shown visually
- If the demo's current drawing is worth keeping, a `save the current drawing to the database` button adds it to history without stopping the demo
- Until a demo drawing is saved by hand, the star control in the status bar does not star anything in history
- While the demo runs, the total elapsed time and total tokens are shown alongside the elapsed time and tokens of the instruction being drawn
- After the demo stops, the total time, total tokens and the number of drawings remain displayed
- `/api/history` accepts `save_artifacts`, controlling whether files are saved on a manual save
- The Stage 2 tool schema inlines `$defs` and `$ref` before it reaches the LLM API, so it works where the JSON grammar compiler cannot resolve references

- Build 162

### v1.23 (2026-05-01)

**The first implementation of inku-cli**

A CLI for operating `inku-api` from a macOS development machine. It is kept as a `cli/` project at the repository root, independent of `server/`.

- `inku-cli` is registered as a console script in `cli/pyproject.toml`
- The implementation lives in `cli/src/inku_cli/` and the tests in `cli/tests/`
- The CLI does not call the server's internal logic; it operates the same FastAPI API the web UI does
- `login` obtains the `inku_session` cookie from `/api/auth/login` and thereafter sends it as `Authorization: Bearer`
- The session settings are saved in `~/.config/inku-cli/config.json`, with file permissions set to `0600` where possible
- `me`, `logout`, `paint`, `batch`, `demo-instruction` and `history` are the first commands
- `paint` and `batch` can write SVG and JSON to files, and generate a PNG where required
- `paint` and `batch` can state the Stage 1 and Stage 2 models, whether to save history, whether to save artifacts, the language, and whether to fetch the thinking
- The `models` command reads and saves the CLI's default provider and model for Stage 1 and Stage 2
- The provider can be saved as `nvidia`, `anthropic` or `local`. What is sent to the API is the model ID; the provider is CLI-side metadata for the endpoint and for operations
- The timeout in seconds can also be saved in the CLI's local settings, resolved as command argument, then local setting, then 600 seconds
- `paint` and `batch` print the Stage 1 and Stage 2 provider and model to stderr as the drawing begins, and include them in the JSON summary
- The default timeout for drawing API calls is 600 seconds, so a long Stage 2 inference can be waited out
- While drawing, the elapsed seconds and a simple text animation on stderr confirm that nothing has stalled
- The first purpose is to build a feedback loop for tuning Stages 1, 1.5 and 2, by generating instructions and images from the CLI and combining them with an AI judgment of the resulting images
- The CLI does not import `inku_server`; it starts as a standalone API client
- In development it runs as `cd cli && uv run inku-cli ...`
- Connecting from macOS to pentala's `inku-api` over the LAN, `login`, `paint` and SVG / JSON / PNG output were confirmed to work
- The `cli/out/` produced while checking the CLI is a local artifact and is not tracked by git

### v1.23 (2026-05-01)

**LLM retry and failure handling for a free NVIDIA API, and Score repairs from a 100-case bench**

NVIDIA NIM is treated as a free API endpoint for development. There is no SLA, and under load it can return an `inference connection error`, a transient 5xx, or a slow response. On that assumption, reasonable retry and failure handling is added on the server.

- OpenAI-compatible LLM calls go through `call_with_llm_retry()`
- Retried:
  - `429 Too Many Requests`
  - `408 / 500 / 502 / 503 / 504`
  - `inference connection error`
  - transient connection reset, aborted, timeout and gateway errors
- Not retried:
  - a JSON grammar or schema compile error
  - a bad request
  - an authentication or authorization error
  - not found
  - any other permanent problem with the query or the schema itself
- The attempt count, base delay, maximum delay and jitter are adjustable by environment variable:
  - `INKU_LLM_RETRY_ATTEMPTS`
  - `INKU_LLM_RETRY_BASE_DELAY`
  - `INKU_LLM_RETRY_MAX_DELAY`
  - `INKU_LLM_RETRY_JITTER`
- The OpenAI-compatible client is given a request timeout so it does not wait indefinitely:
  - `INKU_LLM_REQUEST_TIMEOUT_SECONDS`
  - 120 seconds by default
- The CLI's HTTP timeout stays at 600 seconds for long drawing waits. The server's LLM request timeout and the CLI's HTTP timeout to the API are separate layers

Against the DDL-to-JSON losses found in a 100-case bench, the Score coerce layer is strengthened.

- Where Stage 2 duplicated an instruction carrying the same `arrangement.count`, the duplicates are merged before the renderer
- A ceiling is placed on the total primitive count after the renderer expands, holding back overcrowding and SVG bloat
- The current expanded-primitive ceiling is 400
- Above the ceiling, `arrangement.count` is reduced and a note about the density cap is left in `color_hint`
- The JSON Score's `weight` is filled in from the material words in the DDL:
  - rotring -> `rotring`
  - pencil -> `pencil`
  - crayon -> `crayon`
  - chalk -> `chalk`
  - thin brush / sumi / ink -> `brush_thin`
  - thick brush / oil paint / impasto -> `brush_thick`
- `variation` is filled in from the sway and bleed words in the DDL:
  - 「ゆっくり揺れる」 / 「ゆっくり波打つ」 -> `quality=wave`, `frequency=slow`
  - 「細かく揺れる」 / 「細かく震える」 / 「震える」 -> `quality=perlin`
  - 「滲む」 / 「境界が滲む」 -> `quality=pink`
- `/api/compose` and `/api/paint` call `coerce_score(score, ddl=...)`, so the material and sway information in the DDL informs the repair
- The deterministic fallback used after Stage 2 returns empty `instructions` keeps the DDL's counts and material words as far as it can

New tests:

- `test_llm_retry.py`
  - retry on a rate limit
  - retry on an inference connection error
  - no retry on a schema or grammar bad request
- `test_coerce.py`
  - merging duplicated arranged instructions
  - the ceiling on the expanded primitive count
  - filling material and variation in from the DDL
  - extracting a count hint from a Japanese counter word

Verification:

```sh
cd server
UV_CACHE_DIR=/tmp/inku-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/tmp/inku-uv-cache uv run pytest tests/test_api.py tests/test_composer.py tests/test_renderer.py tests/test_interpreter.py tests/test_ddl_expander.py tests/test_coerce.py tests/test_llm_retry.py -q
```

Results:

- `ruff`: all checks passed
- `pytest`: `103 passed, 30 skipped`

### v1.24 (2026-05-01)

**Sway made easier to see**

Stage 2 and the renderer are adjusted so that 「細かく揺れる」 and 「ゆっくり揺れる」 in the DDL are easier to see in the JSON Score and the SVG.

- The renderer's `fine` sway becomes 7px on a 1000px canvas, so a fine sway reads even in a thumbnail
- 「ゆっくり揺れる」 and `Swaying slowly` make Stage 2 prefer `variation.quality="wave"` with `frequency="slow"`
- 「震える」 and 「細かく揺れる」 take `quality="perlin"` as their basis, treated as a minute irregularity
- The sway of a short line prefers `dimensions=["position_x","position_y"]`, so it is not flattened on a short stroke
- The `variation.quality` description in `schema.py` is updated so the separate roles of `perlin` and `wave` are clear

### v1.24 (2026-05-02)

**Build 250: DDL quality tuning 2-5, and benchmark tooling**

What remained after the sensory retention of Builds 248 and 249 — degenerate fallback works, a bias toward black and gray, a narrow shape vocabulary, and the manual effort of organizing bench results — is addressed.

Improving the quality of the fallback score:

- Even where Stage 2 falls back to a deterministic Score on a timeout or empty instructions, the DDL's counts, placement, materials and scene tone are kept as far as possible
- 「散らす」, 「点々」, `scatter` and `dotted` are kept as an `arrangement` in the fallback too
- A repetition of 40 or more is given `density=medium`, `cluster_count`, `fade` and `preserve_space=true`, leaving negative space
- A repetition above 120 is represented by about 120 at most, and 300 or more becomes `density=high` with `cluster_count=9`, favoring how the group reads
- 「波打つ軌跡」, 「斜めの帯」, 「右半分」, 「上から下」 and 「左から右」 are reflected in `arrangement.path` in the fallback too
- The fallback primitive is not pushed toward line and square; it is spread across `triangle`, `arc`, `square`, `ellipse` and `line` according to the words in the DDL

Palette strategy:

- In Stage 1.5's deterministic expansion, a representative color is chosen from the scene's tone where few colors are stated
- Spring, flowers, buds and warm light prefer red, green and white
- Water, night, moon, rain, mist and cold prefer blue, white and gray
- Forest, leaves, grass and fragrance prefer green, white and gray
- The fallback uses `arrangement.color_cycle` for spring, water-and-night and multicolor scenes, avoiding a single-color result
- A nuance that does not fit an abstract color is kept in `color_hint` and put to use when the renderer resolves the color catalog

Shape vocabulary:

- `triangle`, `arc`, a rotated square and a thin ellipse are used more readily, within the existing schema
- A mountain, a roof and a sharp tip are expressed as a `triangle`
- A leaf, a petal, a feather, a scrap of paper, a fragment and a boat are abstracted as a thin ellipse or a rotated square
- A door, a window, a box, a town, a room and a lattice can be treated as a rotated square, a "section through the line of sight"
- Natural and material forms are kept in the existing primitives, without loss, at a stage where the natural-primitive plugin does not exist

Sensory visibility:

- 「柔らかな光」, 「五感」, 「透明な膜」 and 「気配」 on a white background avoid simple blackening and are kept as a pale blue with a `color_hint`
- 「香り」, 「匂い」, `fragrance` and `scent` on a white background are kept as a pale green with a `color_hint`
- Visibility comes first, while a sensory layer is kept from becoming a hard black line that destroys the work's resonance

CLI benchmark tooling:

- `inku-cli batch` saves the batch summary JSON to a given path when `--summary-json` is stated
- With `--out-dir`, the summary is saved to `OUT_DIR/analysis-summary.json` by default
- `review_sets` is added to the summary, classifying automatically:
  - `all_success_samples`: every sample that succeeded
  - `fallback_samples`: samples that used a Stage 1 or Stage 2 fallback
  - `slow_samples`: samples that took a long time
  - `normal_samples`: samples with no fallback that were not slow
- The summary carries diagnostics on color reach, negated colors, motif reach and mathematical-composition markers:
  - `color_trace`
  - `negated_color_markers`
  - `score_motif_hint_counts`
  - `score_motif_hint_lines`
  - `math_balance_markers`
  - `math_balance_marker_lines`
- The waiting time of the free NVIDIA API depends heavily on the chance state of the queue, so it is excluded from artistic evaluation and treated as diagnostic metadata only
- Every successful drawing is now included in quality evaluation, even a slow one
- `inku-cli contact-sheet` is added, generating a contact sheet from a directory of PNG output
- Pillow is stated as a CLI dependency so contact-sheet generation is reliably available

Verification:

- macOS:
  - `server`: `76 passed, 15 skipped`
  - `cli`: `11 passed`
  - `ruff`: all checks passed for both backend and CLI
- pentala:
  - `server`: `76 passed, 15 skipped`
  - `cli`: `11 passed`
  - `ruff`: all checks passed for both backend and CLI
  - `web`: `npm run check` 0 errors / 0 warnings
  - `web`: `npm run build` succeeds
  - `inku-api` and `inku-server` health check: HTTP 200

### v1.25 (2026-05-01)

**Choosing a touch, and rendering the physical material**

So that a DDL "touch" does not read as a difference in stroke width alone, the difference between materials is strengthened in Stage 1, Stage 1.5 and the renderer.

- A "choosing a touch" rule is added to Stage 1, so a material is chosen from context even where the input names none
  - pale, faint, a draft, a sketch -> pencil or thin brush
  - powder, scratchy, dry, a blackboard, a wall -> chalk
  - hand-drawn, rubbed, wax, a soft plane of color -> crayon
  - sumi, calligraphy, brushwork, gradation -> thin brush or thick brush
  - precise, mechanical, uniform, a drawing -> rotring
- Texture examples for pencil, chalk, crayon and rotring are added to the Stage 1 few-shot
- The renderer generates SVG attributes, a texture filter, secondary strokes, grains and twisted short strokes per `weight`
- Besides lines, the material treatment is applied to the contours of circle, ellipse, square and arc
- `pencil`, `crayon`, `chalk` and `brush_thick` use `feTurbulence` and `feDisplacementMap`, giving a difference in texture and not only in stroke width

### v1.25 (2026-05-03)

**The color catalog API canonical on the server, and version/build in the CLI**

The canonical color catalogs move from a static client-side definition to the server.

- `server/src/inku_server/color_catalogs.py` is canonical for the catalog definitions
- `GET /api/color-catalogs` returns the default catalog ID and the `map`, `swatches` and `palette` of every catalog
- The web UI and the CLI fetch the catalog list from the server API and hold no catalog definitions of their own
- `/api/paint`, `/api/compose` and `/api/history` accept a `catalog_id`, and the server resolves the rendering `color_map`
- The `color_map` request field is kept for compatibility but is no longer canonical for resolving a catalog
- History keeps saving `catalog_id` as before. In addition, the drawing response JSON and the output artifact JSON record the resolved `stage1_model` and `stage2_model` actually used, the `render_build_number` that actually rendered, `render_color_profile` stating that sRGB is the basis, the server-resolved `render_color_catalog_id`, `render_color_catalog_name` and `render_color_catalog_sub`, and `render_color_map` (the expansion from an abstract color name or `palette:<name>` to the actual `#RRGGBB`). A full `map` / `swatches` / `palette` snapshot of `render_color_catalog` is not saved, being redundant with `render_color_map`
- `GET /api/info` returns the server name, version and build number
- A `version` command is added to the CLI, showing the CLI's own version and build number alongside those of the server it is connected to
- Build 264

### v1.26 (2026-05-01)

**The trajectory field**

So that 「波打つ軌跡」, 「斜めの帯」, 「上から下」 and 「右半分」 are not buried in `scatter`, a `path` field is added to the JSON Score's `arrangement`.

- `arrangement.path` takes `none` / `diagonal` / `wave` / `top_to_bottom` / `left_to_right` / `right_half`
- Stage 2 emits "along an undulating path" as `path="wave"`, "a diagonal band" as `path="diagonal"`, and "the right half" as `path="right_half"`
- "Scatter from top to bottom" can state `path="top_to_bottom"` alongside `layout="vertical"`
- The renderer expands an arrangement carrying a `path` into deterministic trajectory coordinates
- For compatibility with existing JSON, `path` defaults to `none`

### v1.26 (2026-05-03)

**Build 257: the CLI benchmark diagnostic summary extended**

The focused small bench and the three-persona review of Build 256 made it clear that the reach of green, shape, motif and mathematical balance needed to be traceable more mechanically.

The CLI benchmark summary is treated as diagnostic data supporting the human evaluation and the implementation fixes that follow, not as an evaluation of a work's quality in itself.

- `color_trace` records negating contexts as well as color markers
  - for example 「緑には寄せず」, 「緑ではなく」, `not green`, `avoid green`
  - a negated color goes into `negated_color_markers` and is excluded from `requested_colors`
  - a sample where "no green" is the correct outcome is therefore not falsely warned as `green_requested_but_missing_in_score`
- `_score_metrics` returns `score_motif_hint_counts`
  - `leaf_cluster`
  - `paper_shard`
  - `ripple_knot`
  - `mountain_sign`
- The `inku-cli batch` summary lists the sample numbers where a motif or math marker appeared
  - `score_motif_hint_lines`
  - `math_balance_marker_lines`
- `math_balance_markers` tracks not only a count but which samples produced it
- The summary keeps its existing keys and extends by adding new ones, so existing consumers of the benchmark JSON are not broken
- Build 257

### v1.27 (2026-05-01)

**Handling an over-long Stage 2 response, and filling in DDL coverage**

In a 30-case bench after the fix, duplication and overcrowding improved, but Stage 2 still sometimes answered after a long delay and collapsed to a single instruction. Further diagnostics and repair are implemented.

- Where the Stage 2 result is empty, `tokens_out` is excessive, or it is both slow and a single instruction, one retry asks for compact drawing instructions
- The reason is kept in the API response as `empty_instructions`, `excessive_tokens_out` or `slow_single_instruction`
- `/api/compose` returns `retry_count`, `retry_reasons` and `fallback_used`
- `/api/paint` returns `compose_retry_count`, `compose_retry_reasons` and `compose_fallback_used`
- The summary JSON of `inku-cli paint` and `batch` includes the Stage 2 retry and fallback information
- Where Stage 2 has collapsed to one instruction, the Score coerce layer fills coverage in from the several visual phrases of the DDL, up to five instructions
- A ceiling is also placed on how far a single instruction expands, so one `arrangement` does not grow too large

New tests:

- `test_coerce.py`
  - the ceiling on a single arrangement count
  - filling DDL coverage in after a collapse to one instruction

Verification:

```sh
cd server
UV_CACHE_DIR=/tmp/inku-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/tmp/inku-uv-cache uv run pytest tests/test_api.py tests/test_composer.py tests/test_renderer.py tests/test_interpreter.py tests/test_ddl_expander.py tests/test_coerce.py tests/test_llm_retry.py -q

cd ../cli
UV_CACHE_DIR=/tmp/inku-uv-cache uv run pytest tests -q
```

Results:

- `ruff`: all checks passed
- server pytest: `105 passed, 30 skipped`
- cli pytest: `8 passed`

### v1.28 (2026-05-01)

**Hard timeouts on Stage 1 and Stage 2, with a deterministic fallback**

In a 30-case stress test of invalid, contradictory and ambiguous inputs, the API and the renderer did not fall over, but the Stage 1 and Stage 2 LLM responses sometimes took minutes. Separately from the LLM client's read timeout, a per-stage hard timeout is implemented in the API layer.

- Past `INKU_STAGE1_HARD_TIMEOUT_SECONDS`, Stage 1 generates a deterministic fallback DDL from the input text
- Past `INKU_STAGE2_HARD_TIMEOUT_SECONDS`, Stage 2 switches to a deterministic fallback Score without waiting for another retry
- Both default to 120 seconds
- `/api/interpret` returns `fallback_used` and `fallback_reasons` only when a fallback occurred
- `/api/paint` returns `interpret_fallback_used` and `interpret_fallback_reasons`
- The Stage 2 diagnostics of `/api/compose` and `/api/paint` record `stage2_hard_timeout` and `stage2_retry_hard_timeout`
- The summary JSON of `inku-cli paint` and `batch` includes the Stage 1 fallback information too
- Build number: 172

New tests:

- `test_api.py`
  - `/api/compose` returns a fallback Score on a Stage 2 hard timeout
  - `/api/paint` continues with a fallback DDL on a Stage 1 hard timeout

**Safety when several users draw at once**

When several users, or one user several times, run `/api/paint` simultaneously, shared resources must not grow without limit and no user's generation count may be lost.

- `user_accounts.image_generation_count` is incremented atomically by a single database `UPDATE`, as `image_generation_count = image_generation_count + amount`
- The Stage 1 and Stage 2 LLM calls run in a shared bounded executor
- The executor's worker count comes from `INKU_STAGE_WORKERS` and its limit including waiting from `INKU_STAGE_QUEUE_LIMIT`
- Even after a stage hard timeout, the underlying LLM call thread cannot be forcibly stopped from Python. A timed-out call therefore holds its stage capacity until it actually finishes, so later requests cannot pile up without limit
- Where stage capacity cannot be acquired, the same fallback path as a stage hard timeout is taken
- `/api/settings/status` returns the worker count, queue limit, and `submitted` / `completed` / `failed` / `timed_out` / `rejected` under `stage_execution`
- Saving, listing, starring, deleting and restoring history continue to filter by `user_id`, so history is never mixed between users

New tests:

- `test_api.py`
  - the final count is not lost when one user's generation count is updated in parallel
  - after a stage hard timeout, capacity is held until the underlying worker finishes and the next stage execution is refused at the limit
  - `/api/settings/status` returns the `stage_execution` state

Verification:

```sh
cd server
UV_CACHE_DIR=/tmp/inku-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/tmp/inku-uv-cache uv run pytest tests/test_api.py tests/test_composer.py tests/test_renderer.py tests/test_interpreter.py tests/test_ddl_expander.py tests/test_coerce.py tests/test_llm_retry.py -q

cd ../cli
UV_CACHE_DIR=/tmp/inku-uv-cache uv run pytest tests -q
```

Results:

- `ruff`: all checks passed
- server pytest: `107 passed, 30 skipped`
- cli pytest: `8 passed`

### v1.29 (2026-05-01)

**The first implementation of plugin support**

To separate the application's core from its non-core extensions, a canvas-size hook is introduced as the first plugin hook.

- A `canvas-aspect` reference plugin is added
- The canvas ratios supported are `square` / `golden` / `a4` / `b4` / `pillar` / `oban` / `wide` / `byobu` / `vertical`
- Per-user plugin settings are saved as JSON in the database's `plugin_storage`
- `/api/auth/me/plugin-storage` and `/api/auth/me/plugin-storage/{plugin_id}` are added
- `canvas_aspect` is passed on `/api/paint`, `/api/compose` and history save, and the renderer changes the SVG's `width`, `height` and `viewBox`
- A plugin button is added to the left of the model-selection button in the web UI
- Changing the canvas ratio clears the current drawing context and shows a placeholder at the chosen ratio
- The status bar shows the current or historical canvas kind, confirming that the plugin choice is part of the drawing context
- The plugin tab of the settings dialog is tidied, showing `canvas-aspect` as a system plugin with its description, version and an enable/disable toggle
- The UI for adding a user plugin is placed as a skeleton, to be enabled once an external loader exists
- In ordinary settings mode the dialog takes a fixed top edge and height, so switching tabs does not move it
- `PLUGIN.md` is added as a reference for writing a plugin
- Build number: 178

### v1.29 follow-up (2026-05-01)

**The canvas plugin reflected in the Score**

The canvas kind chosen through `canvas-aspect` is saved explicitly in the JSON Score and in history.

- The `canvas_aspect` passed on `/api/paint`, `/api/compose` and history save is reflected in `Score.canvas`
- The renderer prefers the request's `canvas_aspect` and, where none is given, consults `Score.canvas` to decide the SVG's `width`, `height` and `viewBox`
- In the history view and the JSON tab, the canvas kind used to generate a work can be seen as `score.canvas`
- Build number: 179

### v1.30 (2026-05-01)

**The status bar and panel controls tidied**

The status bar below the drawing panel is tidied into a place for quickly confirming the current generation context and acting on the result.

- Besides the Stage 1 and Stage 2 model names and the color catalog name, the status bar shows the canvas plugin's current canvas kind
- While a history entry is displayed, the JSON Score `canvas` inside that record takes precedence, showing the canvas kind that entry was generated at
- The `export:` label is removed from the SVG and PNG buttons, which now show a download icon and the format name
- The start buttons of description, batch and demo become a shared component, unifying their appearance and disabled state
- The interpretation box on the description panel is enlarged, with the highlighted view and the editing textarea at the same height
- Build number: 185

### v1.31 (2026-05-02)

**The description tab's progress mascot becomes a kiwi**

The mascot on the progress bar shown during a single drawing on the description tab, and during a redraw from the interpretation (normalized DDL), changes from a small bird to a kiwi.

- The kiwi always faces left; there is no mirroring and no intermediate frame for turning
- It pecks the ground with its long beak, snuffles, blinks, and dashes with its beak open
- Its legs grow from a fixed point under the body and only the feet move, so the joints do not wobble
- The feet move a little dynamically, so the change of step while walking can be read
- The body and the tail end are grouped separately, and it wiggles its rear now and then
- The kiwi ball keeps the head, body and beak in a curled-up form and stays in place for more than six seconds
- During the kiwi ball the eyes close and only the head nods slowly
- The progress mascot becomes a shared component, `KiwiMascot.svelte`, used from the description panel and the DDL redraw panel
- Build number: 199

### v1.32 (2026-05-02)

**The profile dialog**

Profile is added to the user icon menu in the app rail, so a logged-in user can change their own account information directly.

- The user icon menu offers profile and logout
- Choosing profile opens a profile dialog independent of the settings dialog
- The email address can be changed there
- Changing the password takes the current password and the new one
- The new password must be at least 8 characters, and the change is refused where the current password does not match
- `PATCH /api/auth/me/profile` is added as the self-profile update API
- It is separate from the administrator's user-management API and is limited to the logged-in user's own email address and password
- Build number: 206

### v1.33 (2026-05-02)

**Role-based display in the settings dialog**

What each role sees, and may change, in the settings dialog is tidied.

- The `database` tab is shown to the `admin` role only
- The `user management` tab is shown to the `admin` role only
- The `plugins` tab is shown to every logged-in user
- Changing plugin settings is allowed to the `admin` role only
- When a non-admin opens settings, a saved tab of `database` or `user management` falls back to `plugins`
- The plugin-storage update API is available to admins only
- Build number: 212

### v1.34 (2026-05-02)

**The plugin directory layout tidied**

Plugins are split into system and user placements, each plugin in its own directory.

- The server-side plugin implementation moves into the `server/src/inku_server/plugins/` package
- A system plugin lives at `server/src/inku_server/plugins/system/<plugin_name>/`
- The `server/src/inku_server/plugins/user/` namespace is reserved for user plugins
- The web-side implementation lives at `web/src/lib/plugins/system/<plugin-id>/`
- `web/src/lib/plugins/user/` is reserved for user plugins
- The existing `canvas-aspect` moves into its own directory as a system plugin
- `server/src/inku_server/plugins/__init__.py` re-exports the stable hook API that the API and the renderer refer to
- Build number: 213

### v1.35 (2026-05-02)

**Export templates**

An `export` tab is added to the settings dialog, so the PNG save format can be managed as a per-user template.

- The `export` tab is available to every logged-in user
- Templates are saved as per-user settings in the server database
- A template holds a name, a description, and a height in pixels along the y axis
- `PNG 1024px` and `PNG 2048px` are provided as the default templates
- The menu shown from the status bar's PNG button reads the saved templates
- PNG export takes the y-axis height as its basis and computes the width from the current canvas ratio
- `GET /api/auth/me/export-templates` and `PUT /api/auth/me/export-templates` are added
- Build number: 214

### v1.36 (2026-05-02)

**A canvas ratio: byobu**

`byobu` is added to the canvas ratio plugin.

- The ratio is `2.2:1`
- The display name is `Byobu`
- The description is "a Japanese folding screen; the wide format of one screen of a six-panel pair"
- It is ordered below `Wide` and above `Vertical`
- Build number: 215

### v1.37 (2026-05-02)

**Database backup settings**

The database file size and backup settings are added to the database tab.

- The database tab is still shown to the `admin` role only
- The size of the SQLite file database is shown
- The backup settings take an interval in days and a maximum number of generations to keep
- The defaults are an interval of 7 days and 4 generations
- When `/api/settings/status` is fetched and the interval has passed, an automatic backup is created
- Automatic backups delete the oldest according to the maximum generation count
- A `back up now` button creates a manual backup
- A manual backup does not count toward the maximum generation count
- For a database other than SQLite, the file-replica backup is shown as unsupported
- `PUT /api/settings/db-backup` and `POST /api/settings/db-backup/run` are added
- Build number: 216

### v1.38 (2026-05-02)

**The DDL edit dialog folded into the interpretation box**

Editing the DDL directly is folded into the interpretation (normalized DDL) box on the description tab, rather than living in a separate DDL edit tab.

- The DDL edit tab is retired, returning to three tabs: description, batch, demo
- The interpretation box shown after a generation on the description tab is a highlighted textarea and is directly editable
- `Saijiki` and `edit DDL` buttons sit side by side above the interpretation box
- `Saijiki` opens the Saijiki drawer from the right, and clicking a word inserts it at the current caret in the interpretation box
- `edit DDL` opens a large DDL edit dialog
- The dialog shows a numbered DDL editing area on the left and two columns of Saijiki vocabulary on the right
- A brief guide to the DDL and its grammar sits along the bottom of the dialog
- `draw from DDL` is not run from inside the dialog; drawing is gathered into the button directly below the interpretation box
- A `draw from DDL` button also sits below the interpretation box, redrawing from the current DDL without opening the dialog
- Pressing `draw` on the description tab after editing the DDL directly shows a confirmation, "the edits to the DDL will be lost — is that all right?", offering `cancel`, `OK` and `draw from DDL`. `OK` regenerates from Stage 1 as usual, and `draw from DDL` redraws through Stage 2 from the edited DDL
- While an ordinary drawing or a DDL redraw is running on the description tab, a running effect is shown there and the start buttons on batch and demo are suppressed
- During a DDL redraw the token count, elapsed seconds, stop button and kiwi progress mascot are shown
- The stop button aborts the `/api/compose` request
- So that any canvas ID a canvas-ratio plugin adds can be kept as the JSON Score's `canvas`, the Score schema treats `canvas` as a string rather than a static enumeration
- Build number: 246

### v1.39 (2026-05-03)

**SVG save profiles**

The SVG save format is separated into display, editable and compatibility-first.

- The database's `history.svg` keeps the display SVG as before
- Showing history, regenerating a PNG and regenerating artifacts all treat the stored display SVG as canonical
- The editable SVG is generated on demand at download time from the JSON Score and the server's color catalog information
- The compatibility-first SVG is likewise generated on demand
- The `display` profile favors compatibility with the current view and keeps the existing texture filters, blur and clipping
- The `editable` profile adds stable IDs and a group structure in the forms `layer_00_background`, `layer_10_content`, `instruction_###_*` and `mark_###_###_*`, so it is easy to edit in Illustrator or Affinity
- The `compat` profile favors not breaking in a general SVG viewer and uses no filter and no clip-path
- `POST /api/render-svg` and `GET /api/history/{item_id}/svg?profile=...` are added
- The web UI's SVG button offers `Display`, `Editable` and `Compat` from a menu
- The CLI's `paint` and `batch` choose the profile with `--svg-profile display|editable|compat`
- Build number: 267

### v1.40 (2026-05-03)

**A random color catalog per drawing in batch and demo**

An option to choose the color catalog at random for each drawing is added to batch mode and demo mode.

- In batch mode, `choose a color catalog at random for each drawing` is a temporary option per run
- In demo mode the same option is saved with the demo settings and restored per user
- The random choice is made over the catalog list already fetched from the server, and the chosen `catalog_id` is passed to `/api/paint` for each drawing
- On history save, the `render_color_catalog_id` actually rendered takes precedence
- The status bar's color catalog display reflects the result's `render_color_catalog_id` rather than only the current selection
- Build number: 271

### v1.41 (2026-05-03)

**A render hash in history, and CLI history export**

Every drawing in the history database is given a `render_hash` derived from its content.

- `render_hash` is a SHA-256 over the canonical JSON of `input`, `ddl`, `score`, `svg` and the render metadata, stored canonically in the database as 64 hex characters
- The history responses and the history-save response of `/api/paint` carry `render_hash` and `render_hash_short`, the last four characters in upper case
- Existing history is backfilled with a `render_hash` during the database migration
- The history-management dialog shows the four-character short hash as a `#ABCD` chip that does not break the layout, in both the thumbnail and the list views, and clicking it copies the canonical hash
- The dialog opens large, leaving roughly a 10% margin on all four sides of the current window, with the beginning of the instruction below each thumbnail and, under that, the star, the short hash, and the delete or restore controls
- Where the instruction begins with a number such as `#123`, that number is omitted from the line below the thumbnail
- The unstarred state in the thumbnail control row is given enough contrast to be seen at a small size, and the selection checkbox at the top left is made smaller with a thinner border
- When pages change in the dialog, several overlapping refetches always clear the loading state at the last completion
- The thumbnail view measures the columns and rows that fit the dialog's real display area and recalculates the page size dynamically, so no scrollbar appears
- The star in the control row separates its click from selecting the card, and the page size is recalculated from the card's measured size, closing the gap at the bottom
- The control row puts the star at the bottom left, and the hash drops its `#` and matches the button proportions of the delete control
- The starred state is stated explicitly, so that in dark mode its color is not overwritten by the ordinary state
- Thumbnails in the dialog do not show an enlarged preview on hover, keeping the positions and the selection stable
- The top of the dialog gathers the title, view switch, count and page movement into one row and the selection, filter and search into a second, widening the thumbnail area
- Recalculating the page size from the measured thumbnail keeps the page number, so moving to the next page does not return to the first
- The per-image delete control in the dialog is a small trash icon button rather than a text label
- The JSON tab, the drawing response and the artifact JSON at history-save time record the resolved `stage1_model` and `stage2_model` the server actually used
- Color management currently covers sRGB alone, and the JSON tab, drawing response, history and artifact JSON record `render_color_profile: { id: "srgb", name: "sRGB IEC61966-2.1", standard: "IEC 61966-2-1:1999" }`. A wide-gamut profile such as Adobe RGB is a candidate for later and is not implemented now
- The JSON tab shows the attribute metadata — model, build, color profile, color catalog and the rest — first, and the `score` after it
- Reopening an image from history also shows the saved `stage1_model` and `stage2_model` on the JSON tab
- A `model settings` tab for administrators is added to the settings dialog. The default provider and model for Stage 1 and Stage 2, and the base URL and API key per provider, are saved in the server database's app settings
- The built-in commercial LLM providers follow their official names — OpenAI API Platform, Claude API, Gemini API — while the non-commercial API provider is NVIDIA NIM and the local providers are Ollama (OpenAI-compatible) and Intel OVMS (OpenAI-compatible)
- An administrator can add and remove connection services on the model settings tab. An added service has a service ID, a display name, a connection form (`openai_compatible` / `anthropic` / `gemini`), a base URL, and optionally an initial API key. `add` in the add-service dialog saves to the server immediately, and there is no redundant save-everything button at the bottom of the service panel. The model list is not typed in at add time but fetched per service with `fetch model list`
- The service ID is the internal key of the connection settings in the database, the provider reference for Stage 1 and Stage 2, the provider decision at API call time, and the guard against duplicates; it cannot be edited after creation. The service name shown on screen can be edited later
- `fetch model list` can be run per connection service. The server calls the models API for the provider kind using the saved base URL and API key, and saves the list into that service's definition. Success or error is shown at the bottom of the published-model selection dialog. The API key is never sent to the browser
- An API key is stored on the server only, and the response of `GET /api/settings/models` tells the UI nothing more than whether one is set. No raw API key is returned to the browser; where one is set, the input reads `keep the saved key` and cannot be edited. A new key typed while none is set is saved with that service's save button
- Provider API keys in the database are encrypted in the form `enc:v1:`. The encryption key comes from `INKU_SECRET_KEY` where set, otherwise from `INKU_SECRET_KEY_FILE` or the local key at `~/.local/share/inku/secret.key`. An existing plaintext key stays readable and moves to the encrypted form at the next save
- `PUT /api/settings/models` is available to administrators only and distinguishes setting a new API key, keeping the current one, and deleting it explicitly
- An LLM call resolves its endpoint from the model ID's provider prefix (`openai:` / `anthropic:` / `gemini:` / `nvidia:` / `ollama:` / `ovms:`) and from the defaults on the settings tab. The older NVIDIA slash IDs and local OVMS IDs are still accepted for compatibility
- Model IDs the web UI sends to `/api/paint`, `/api/interpret` and `/api/compose` are normalized to a provider-qualified ID such as `openai:gpt-5.2` by joining the provider. Where the API receives a model ID with no provider prefix and that ID matches the user's configured Stage 1 or Stage 2 model, it is completed with the provider from the same user settings before dispatch
- Demo instruction generation uses the same provider resolution, going through the connection settings of OpenAI API Platform, Claude API, Gemini API, NVIDIA NIM, Ollama or Intel OVMS
- The LLM server connection settings are global administrator settings, while the Stage 1 and Stage 2 endpoint and model choices are saved per user in `user_accounts.model_settings`. Confirming the model-selection dialog saves them through `/api/auth/me/settings`, and they are restored at login
- On the model settings tab an administrator can turn individual models on or off for ordinary users, per provider. That selection happens in its own dialog rather than inside the service panel, and `fetch model list`, search, `select all` and `clear all` live in the same dialog. A checkbox change there is a draft, reaching the server only on `save` and discarded by `cancel` or by clicking outside. The model settings tab itself shows only a summary of what is published. `GET /api/models` returns only the published models to a logged-in user, and the model-selection dialog uses that list
- `history-export` is added to the CLI, accepting a `--from` and `--to` range in history order and individual hashes
- `history-export` writes a `contact-sheet.png` for benchmark evaluation, individual JSON, intermediate SVG and PNG files, and a `summary.json` from the selected history
- Where a four-character hash matches several candidates, the CLI treats it as ambiguous, errors, and asks for more characters
- Build number: 313

### v1.42 (2026-05-04)

**A server-wide automatic save setting**

Automatic saving of output artifact files becomes a server-wide administrator setting rather than a per-user one.

- An `other (server)` tab for admins is added to the settings dialog
- It sets automatic file saving on or off, the absolute path of the output folder, and the automatic PNG size
- The PNG size is chosen from `1080px` or `2160px`
- The server saves `enabled`, `output_dir` and `png_size` in `app_settings.output_save_settings`
- The initial destination comes from `INKU_OUTPUT_DIR` and the initial PNG size from `INKU_OUTPUT_PNG_SIZE`, falling back to `~/.local/share/inku/outputs` and `2160px`
- `PUT /api/settings/output-save` is available to admins only, accepts an absolute path only, and takes only `1080` or `2160` for the PNG size
- With automatic saving off, the history database is still saved as canonical; only the SVG, JSON, input, DDL and PNG artifact files are skipped
- Beneath the destination folder the layout stays `user_id/YYYY-MM-DD/YYYYMMDD_HHMMSS_<history_id>`
- The tab shows the save workers and queue, the save statistics, and the PNG size. The workers are the number of concurrent save jobs and the queue is the limit on waiting jobs; above the limit, the database history save takes priority and the artifact save is skipped
- The note on screen reads: "The history database is canonical. Output files are by-products saved in the background and can be regenerated from the database."
- Build number: 324

### v1.42 (2026-05-05)

**Render metadata, and what happens when a history entry is selected**

How the metadata of a result is shown, and how the UI selection behaves when a history entry is chosen, are tidied.

- The color catalog, canvas and creation time of the displayed drawing are shown at the top of the drawing panel
- The color catalog button shows the name of the current catalog rather than a fixed label. A long name is elided at the end, with the full name available from the hover title
- The order of the controls at the top of the input panel is canvas ratio, color catalog, model selection
- `render_canvas_aspect` is added to the drawing response, the history record, the JSON tab and the artifact JSON, recording the canvas ratio ID actually used to render
- `render_canvas_aspect_id` and `render_canvas_aspect_ratio` are added to the same four. The first is the explicit canvas-ratio identifier and the second the numeric width divided by height
- `render_canvas_aspect` is shown as part of the render metadata, just after `render_engine_version` and before the color catalog metadata
- `render_canvas_aspect_id` and `render_canvas_aspect_ratio` follow it
- The JSON Score's `score.canvas` remains the canvas stated on the score side, while `render_canvas_aspect` is the record on the artifact side. They usually agree; both are kept so that old data and external input can be checked
- `render_canvas_aspect` is kept for compatibility. New implementations treat `render_canvas_aspect_id` as the identifier and fill it in from `render_canvas_aspect` for old history
- `behavior when selecting from history` is added under settings > other
- The canvas size can either follow the history entry's canvas size into the UI selection, or keep whatever is currently selected in the UI
- The color catalog offers the same choice
- These choices are saved in the browser's localStorage
- They update the UI selection only; a stored history SVG is never re-rendered
- Build number: 340

### v1.43 (2026-05-05)

**The render engine boundary and engine metadata**

In preparation for accepting several drawing engines later, an internal boundary is added so the drawing core is called through a `RenderEngine` contract.

- `server/src/inku_server/render_engines/` is added, with the `RenderEngine` protocol and `RenderEngineResult` in `base.py`
- The current `renderer.py` is called from `render_engines/default.py` as the `default` engine
- Loading arbitrary external code, and a management UI for it, are not implemented. `current_render_engine()` returns the `default` engine statically
- `/api/compose`, `/api/paint` and the compatibility `/api/history` generate their SVG through the RenderEngine
- `render_engine_id` and `render_engine_version` are recorded in the drawing response, the history record, the JSON tab and the artifact JSON
- `render_engine_id` and `render_engine_version` columns are added to the `history` table, and an existing database follows through a startup migration
- The engine metadata joins the canonical payload of `render_hash`, so the same Score and SVG rendered by a different engine can be tracked as different content
- The current values are `render_engine_id: "default"` and `render_engine_version: "1"`
- Build number: 326

### v1.43 (2026-05-05)

**A log retention policy setting**

The application log retention policy of `inku-server` and `inku-api` becomes a server-wide administrator setting.

- A `log retention` tab for admins is added to the settings dialog
- It sets log retention and rotation on or off, the retention period in days, the rotation cycle, and whether rotated logs are compressed
- The default policy is on, `90` days, `daily`, and compression on
- The server saves `enabled`, `retention_days`, `rotate` and `compress` in `app_settings.log_retention_settings`
- The initial retention comes from `INKU_LOG_RETENTION_DAYS` and the initial cycle from `INKU_LOG_ROTATE`, falling back to `90` days and `daily`
- `GET /api/settings/status` returns the current policy along with a preview of the `logrotate` configuration and of the `systemd` drop-in
- `PUT /api/settings/log-retention` is available to admins only, accepts `1` to `3650` days, and takes only `daily`, `weekly` or `monthly`
- The note on screen states that the policy is saved in the application database but that applying it to `systemd` or `logrotate` requires permissions on the server's operating system
- The systemd drop-in preview uses `StandardOutput=journal+append:/var/log/inku/<service>.log` and `StandardError=journal+append:/var/log/inku/<service>.log`, recommending a form traceable both through `journalctl -fu <service>` and in the file log
- At startup, `inku-api` and `inku-server` print a banner framed by 60 `=` characters, carrying the service kind, the application version, the build number and the build date
- The banner also carries the minimum needed for operational checking: mode, listen host and port, runtime and platform, and where the logs go. The API side also shows the render engine ID and version
- The banner's emoji suit the service: `🧠 ⚙️ 🔌 🖌️ 🚀` for the API and `🎨 🖼️ 🌈 🪄 ✨ ... 🚀` for the web UI
- For operational verification, the systemd drop-ins for `inku-server` and `inku-api` and `/etc/logrotate.d/inku` were configured by hand, and `NeedDaemonReload=no`, the journal output, and `daily` / `rotate 90` / `maxage 90` / `compress` were all confirmed to take effect
- Build number: 336

### v1.44 (2026-05-05)

**PNG save templates, and a note about API keys in the model settings**

The PNG save menu and the model settings tab are adjusted to match how they are used.

- The default PNG save templates in the navigation bar change from `1024px` / `2048px` to `1080px` / `2160px` / `4320px`
- A template's size is the pixel count along the y axis
- In the Japanese UI the template description and the settings item are written `Y軸` and `Y軸の高さ` rather than `y-axis` or `y軸高さ`
- Where an existing user's saved PNG templates are exactly the old defaults `1024px` / `2048px`, they are replaced automatically by the new defaults. A template the user edited is kept
- Beside the `AI service connections` heading on the model settings tab, how API keys are handled is stated
- The text reads: "API keys are stored encrypted in the database and are never shown again. A key already set through an environment variable is treated as an initial value."
- The English UI shows a note of the same meaning
- Build number: 328

### v1.45 (2026-05-05)

**The render hash recorded in the JSON metadata**

Each drawing's server-side `render_hash` is recorded in the JSON metadata area as well as in history.

- `render_hash` is a 64-character SHA-256 hex computed from the drawing's content and the server-owned render metadata
- `render_hash_short` is a four-character upper-case suffix, easy to refer to in the UI and the CLI
- `/api/paint`, `/api/compose`, the JSON tab, the CLI's output JSON and the saved artifact JSON all carry `render_hash` and `render_hash_short`
- Regenerating an artifact JSON from the history database also expands the database's `render_hash` and `render_hash_short` into the metadata area
- The history database remains canonical and the output files remain by-products

### v1.46 (2026-05-07)

**A DDL input drawing mode in inku-cli**

So that a CLI comparison between server and Android can set aside the variation in Stage 1's LLM output and verify the differences from the normalized DDL onward.

- `--input-mode paint|ddl` is added to `inku-cli paint` and `inku-cli batch`
- The default `paint` passes natural-language input to `/api/paint` as before, running Stage 1, Stage 1.5, Stage 2 and the render
- `--input-mode ddl` treats the input text as normalized DDL and passes it to `/api/compose` without calling Stage 1
- With `--input-mode ddl --save-history`, the CLI saves the `/api/compose` result to the ordinary history database through `POST /api/history`
- `/api/compose` includes the effective DDL after Stage 1.5 in its response as `ddl`
- In the CLI's DDL mode, the output JSON and the history save use the effective DDL that `/api/compose` returned
- The Android headless comparison script `android/scripts/headless_render_compare.sh` propagates `INPUT_MODE=ddl` to the server-side `inku-cli paint --input-mode ddl` as well
- Where `ORIGINAL_TEXT` is given, both Android and the server treat it as the original input for the history display and as auxiliary context for Stage 2
- This mode is for benchmark and parity verification; the default behavior of the ordinary natural-language drawing flow is unchanged
- Build number: 352

### v1.47 (2026-05-07)

**History saved by an external client reflected automatically in the web UI**

A drawing saved to the history database by a client other than the open web UI — `inku-cli`, the Android headless CLI — can now appear in the web UI's history strip automatically.

- The history database remains canonical for drawing history, and the web UI does not guess at an external save from local state alone
- The web UI refetches the newest history page periodically while logged in, showing ordinary history, on the newest page, with the document visible
- The interval is about 12 seconds, avoiding too-frequent polling, and simultaneous refetches and repeats within 5 seconds are suppressed
- When the browser window regains focus, or a hidden tab becomes visible again, the newest history is refetched without waiting for the interval
- On a refetch for external-save detection, the currently selected history ID keeps its selection if it is still on the refetched newest page
- No automatic replacement happens while showing starred entries only, while searching, while on an older page, or while history is loading, so the user's reading context is not broken
- Where the history-management dialog is open and showing the first page of ordinary history, that page is quietly refetched too
- Build number: 361

### v1.48 (2026-05-09)

**The Android native implementation brought under management, and v1.48**

The Android version is organized as a native standalone application under git, and stated as a mobile implementation that follows the web and server reference implementation.

- Android is implemented in Kotlin with Jetpack Compose, with Room and SQLite as the formal local database layer
- The application assumes a single user, and the server-operations features of server and web — user management, database management, plugin management, log retention — are excluded from the Android UI
- The development master for Android is always `web/` and `server/`, and DDL interpretation, Stage 1.5 expansion, Score repair, SVG rendering and history / render metadata compatibility are verified against the server source
- LiteRT-LM is Android's local LLM provider, with Gemma 4 E2B as standard and E4B as the high-quality option. A GPU backend is required; there is no CPU fallback
- The license agreement, first download, re-download, SHA-256 verification and download state of Gemma 4 E2B and E4B are saved in Room
- For mobile usability, Android's model-selection UI treats Stage 1 and Stage 2 as a single drawing-model choice. The save format, history JSON and render metadata still keep `stage1_model` and `stage2_model`
- The model settings panel is an independent panel per endpoint, offering adding a service, editing its name, editing the base URL, adding and removing an API key, choosing the published models, and fetching the model list. The connection form is set when the service is added and is not changed in an existing panel
- Candidate models and published models are stored separately, and only published models appear in the drawing screen's model selection
- The drawing screen offers pinch zoom, panning, moving through history by horizontal swipe, and a presentation view on double tap, as Android-specific UI
- The presentation view hides everything but the image and matches the surrounding background to the image's background color: a dark surround for a white-background image and a light one for a black-background image
- The history screen uses a three-column thumbnail grid as standard. The server version's trash, list view and bulk selection are not offered on Android
- SVG and PNG export is implemented as a menu with the same profile and template structure as the `CanvasPanel` of server and web, handed to the share sheet on Android
- The PNG templates default to y-axis heights of `1080px`, `2160px` and `4320px`, with Room's `export_templates` canonical
- `render_canvas_aspect_id` and `render_canvas_aspect_ratio` are included in the render metadata, computed on Android too from values matching the server's canvas aspect definitions
- Android has headless render and comparison tooling, which combined with the server CLI's `--input-mode ddl` compares parity from the DDL onward and from the Score onward
- The Android version is canonical in `android/VERSION` and the Android build number in `android/BUILD_NUMBER`. The initial values for the v1.48 generation are `1.48.0-android.1` and `148001`
- The Android settings menu holds a version screen showing versionName, versionCode, build type, applicationId, source spec and render engine version
- Build number: 148001

### v1.49 (2026-05-11)

**A presentation mode for the drawing, and instruction subtitles**

Display aids for exhibiting and viewing are added to the web UI's drawing tab.

- A full-screen icon at the bottom right of the drawing tab opens presentation mode
- Presentation mode maximizes the displayed SVG and gathers history movement, jump to newest, star, subtitle toggle and close into controls along the bottom
- Presentation mode also closes with the Escape key
- An icon at the bottom left of the drawing tab shows the instruction as a subtitle
- In the ordinary view the subtitle takes a 10% margin on each side of the drawing tab's width and is clipped inside the tab
- In presentation mode the subtitle takes its 10% margins from the window width
- The text shown is the original — the user's input, the history `input`, the newest batch line, or the demo's generated instruction — not the internal prompt extended for Stage 1
- Internal auxiliary text such as `buildEmotionHint()` may stay in the prompt and debug views but is not shown in a subtitle meant for viewing
- Build number: 401

### v1.50 (2026-05-11)

**English instructions, and separating the instruction language from the UI language**

The language of a drawing instruction becomes selectable independently of the Japanese or English UI. Looking ahead to more languages, the display language and the interpretation language are separated at the API boundary.

- An `instruction language` selector is added to the input header, offering `auto`, `日本語` and `English`
- `/api/paint`, `/api/interpret`, `/api/compose` and `/api/demo/instruction` accept `instruction_lang` and `ui_lang`
- With `instruction_lang=auto` the server decides `ja` or `en` from the input text and passes it to Stage 1, Stage 1.5, Stage 2 and demo instruction generation
- `/api/paint`, `/api/compose`, the history save, the JSON tab and the saved artifact JSON record `instruction_lang_requested`, `instruction_lang_resolved` and `ui_lang`
- `instruction_lang_requested`, `instruction_lang_resolved` and `ui_lang` columns are added to the `history` table
- `inku-cli paint`, `batch` and `demo-instruction` send `--instruction-lang auto|ja|en` and an optional `--ui-lang`, replacing the old `--lang`
- To avoid breaking existing history and the hash references in `cli/tune_bench.md`, the language metadata is not part of the canonical payload of `render_hash`
- The Stage 1 prompt, the Stage 2 prompt and the Stage 1.5 expander and filter are registered in a registry as an `InstructionLanguageSupport`
- The vocabulary and context markers the Score coerce layer reads are separated into per-language `ja` and `en` files as `InstructionLanguageSupport.coerce_markers`
- The coerce algorithms themselves stay common, operating on JSON Score structure, and language differences are expressed in the marker sets
- The existing `ja` and `en` prompts and expanders go into the registry unchanged in content, so the drawings do not change
- A third party implementing another language adds the language code, prompts, expander and coerce markers to the registry first, and verifies that separately from any change to the JSON Score schema, the renderer, or the color catalogs
- Builds 403-427 separated the English Stage 1, Stage 1.5 and Stage 2 implementations from the Japanese at file level and added English-specific interpretation, markers and repair vocabulary
- The English path converts the temporal structure, repetition, before-and-after, gaze and the core of an event in an English sentence into abstract drawing parameters, rather than substituting words
- The English Stage 1.5 and coerce markers treat temporal connectives such as `before`, `after`, `again and again`, `as if` and `at once`, composition words such as `diagonal`, `same beat` and `shifted`, and visual-event words for transparency, reflection, fog, roads, sound and flocks as language-specific repair cues
- The Japanese and English paths share one JSON Score schema, renderer and color catalogs, and the language difference is confined to the prompt, expander, marker and repair-input stages
- To check the English quality, 30 pairs of equivalent Japanese and English instructions were drawn on a `square` canvas with the `default` color catalog and without saving history, and compared by three expert personas
- Over those 30 at Build 427, English reaches a quality close to Japanese. English is slightly higher on color resonance, Japanese slightly higher on constraint adherence and visual event
- What remains: in English, "too orderly, so the moment of the event sinks into the background"; in Japanese, "a poetic quiet compressed into a sign too small to carry". The next improvement strengthens the minimum visible size of the focal event, the contrast, and the neighboring reactions, without increasing density
- Build number: 427

### v1.51 (2026-07-02)

**The design of relation, and sway extended to the macro scale**

A specification revision following the analysis of the primary causes of the contraction in the output distribution observed at Build 436 — less variety in composition, density and planes of color. The primary causes were (A) sway assigned only to the micro layer, the tremble of a line, with the once-ness at the level of composition belonging to no layer at all; (B) Stage 1.5 having become a deterministic lottery over fixed recipes that always favored the diagonal and the one-sided focus; and (C3) the JSON Score having no predicate for the relation between instructions, so the grammar of composition existed only inside fixed recipes.

- The two scales of sway, micro and macro, are stated in §2, principle 2
- A "relations" category is added to the core vocabulary of §3.1 (along, not touching, cutting, between). It adds a predicate rather than a noun, so it does not contradict plugin principle 1
- The condition for coexisting with the once-ness of the output is stated in the cache policy of §12.10, measure B
- The composition rule of §12.11 changes from "always favor the diagonal and the one-sided focus" to "choose from a family of compositions, depending on the input". Focus coordinates change from fixed values to regions. The role shifts from "injecting a finished recipe" to "attaching a relation predicate"
- The two scales of the performance's freedom — micro variation and the sequential resolution of relations — are added to §13.8
- §14, "The design of relation", is newly written. The old §14 through §16 move down to §15 through §17
- Building a relation-repair governor is forbidden (§14.6). Coerce may not add a relation
- The implementation instructions are recorded in codex-task.md and the verification and acceptance criteria in tune_bench.md

### v1.52 (2026-07-04)

**Making the afterwards choice concrete (vary), and the prohibition on repair parts becoming a fingerprint**

A specification revision following the three-persona review of Build 441 (the first full bench after the v1.51 implementation, plus post-audit fixes). The review is detailed in `cli/tune_bench.md` under "Build 441 three-persona review" and the implementation instructions in `no-git-sync/codex-task-v1.52.md`. It addresses the two points all three personas raised: (1) coerce repair parts — an arc of adjacent reaction in 93%, a small pentagon at fixed coordinates in 33% — repeating across every work as "the system's fingerprint" and ruining the viewing of a series; and (2) the ceiling on the range of the output being low, with the design of handling an outlier — a surprise — through an afterwards choice (§8) never made concrete.

- §8.4, "Making the afterwards choice concrete: two stages of regeneration", is newly written. Regeneration is defined in two stages: "another performance" (a performance seed, no LLM) and "another composition" (varying Stage 1.5's selection seed, one Stage 2 call)
- §10.4, "Repair parts must not become a fingerprint", is newly written. Repair parts must (1) have their firing rate measured per part and watched from above, with no floor; (2) never hard-code fixed coordinates or fixed shapes; and (3) fire only under a limited condition, where the subject would otherwise break
- The vary rule for the selection seed is added to §12.11. The default keeps "the same input gets the same expansion", and the selection is redone only where vary is stated explicitly. Implicit non-determinism — an auto-increment or a clock seed — is forbidden
- codex-task.md P3-4, held over at v1.51, is settled as §8.4 and §12.11 of this revision
- The Version line in the header is corrected (it had been left at v1.49 through the v1.50 and v1.51 revisions)

Verification after the Build 442 implementation showed the `vary_seed` path (API, CLI, web UI) and the two stages of regeneration working. Five fixed prompts across `vary_seed` 0..4 gave 25 successes out of 25 with no fallback. Over 30 Japanese and 30 English samples, `adjacent_reaction` fell from 56/60 to 14/60, confirming the main effect of the fingerprint suppression.

The v1.52 quality acceptance, however, was not met at Build 442. `angular_pulse` at 14/60 and `vanishing_trace` at 26/60 missed their targets, and `vanishing_trace` was worse than Build 441's 21/60. The `visual_event` average also fell from Build 441's 93.0 to 77.8, failing the quality-regression guard.

Build 443 limited the firing of `vanishing_trace` to cases with a trace subject — footprints, white breath, a contour, a human shadow — rather than any "vanishing context", and changed the general `visual_event` repair from a small angular pulse to a compact mark at input-derived coordinates. A rerun over 30 Japanese and 30 English gave `adjacent_reaction` 11/60, `angular_pulse` 0/60 and `vanishing_trace` 2/60, meeting the acceptance criteria for the repair fingerprint. But the `visual_event` average was 77.93 and `negative_space_pressure` 88.97, still failing the quality-regression guard against Build 441. v1.52 was therefore treated as "the implementation and the fingerprint suppression are done; an audit of the quality-loss samples remains".

Build 444 carried out a targeted recovery of the low `visual_event` and `negative_space_pressure` from Build 443. The general compact visual event was given a `color_cycle` and an opposing center derived from the input hash; a temporary event that arrives and leaves was treated as `brief_arrival_departure`; and the color cycle and opposing placement were added to the existing `line of birds / river surface / another road` and `tatami / tilted quiet` recipes. In the targeted benchmark, EN #06 reached `visual_event` 98 and `negative_space_pressure` 100, EN #27 reached 70 and 76 on a single rerun, and JP #28 recovered to 76 and 86.

Build 444's full 30+30 benchmark (`cli/out/jp-en-30-equivalent-444/{jp,en}/`) gave 60 successes out of 60 with no fallback. The repair parts were `adjacent_reaction` 10/60 (16.7%), `angular_pulse` 0/60 and `vanishing_trace` 2/60 (3.3%), continuing to meet v1.52's repair-fingerprint criteria. The quality averages were `visual_event` 79.90, `negative_space_pressure` 89.97, `motion_energy` 94.57 and `constraint_adherence` 93.33 — against Build 441's baseline (`visual_event` 93.0, `negative_space_pressure` 96.23, `motion_energy` 97.7, `constraint_adherence` 86.0), `visual_event` and `negative_space_pressure` fail the guard of staying within -5. v1.52 was therefore treated as: the Phase A-D implementation, measurement, vary and repair-fingerprint acceptance are complete; the quality-regression guard is not met. Further fixes were to come from auditing the low-scoring rows individually (EN #21 at `visual_event` 40 and `negative_space_pressure` 26, JP #23 at `negative_space_pressure` 42, JP #02 and #03 at `visual_event` 48) and generalizing the placement, color cycle and opposition of the existing recipes, rather than from adding marker vocabulary or a new governor.

Build 445, following that audit, generalized the treatment of the small points, circles and ellipses of DDL coverage as compact focal marks. Sentence splitting for English DDL was improved, `circle` and `ellipse` were no longer treated as the same, and coverage from a stated `radius` or 「半径」 or from "a small dot" was kept as a small foreground mark at low density with an outward fade and preserved negative space. This adds no marker vocabulary and no new global governor; it corrects the shape, size and negative-space preservation of the existing coerce fallback against what the description says.

Build 445's full 30+30 benchmark (`cli/out/jp-en-30-equivalent-445/{jp,en}/`) gave 60 out of 60, though JP #27 and #28 hit a stage 2 timeout even on the final retry and used the stored fallback result (2/60). The repair parts were `adjacent_reaction` 8/60 (13.3%), `angular_pulse` 0/60 and `vanishing_trace` 2/60 (3.3%), so the repair-fingerprint gate still passed. The quality averages were `visual_event` 80.43, `negative_space_pressure` 91.47, `motion_energy` 93.73, `constraint_adherence` 94.17, `color_resonance` 96.83 and `figurative_risk` 1.33. Against Build 441, `negative_space_pressure`, `motion_energy` and `constraint_adherence` returned to within -5, but `visual_event` at 80.43 against 93.0 did not. The low rows were JP #02 (`visual_event` 40) and JP #21, EN #04, EN #20 and EN #21 (`visual_event` 48), narrowing what remained in v1.52 to recovering the semantic eventfulness of the visual event.

Builds 446 and 446-2 generalized further against the low `visual_event` rows that had stuck at Build 445, strengthening only the metadata of existing instructions and arrangements. In an event context the compact focal mark of a small point, circle or ellipse is treated as `visual event preserved as compact focal accent`, and an existing focal event is given an `arrangement.center` in the opposite quadrant, a `color_cycle`, preserved negative space, low density and an outward fade, making the counterweight explicit. Where an `inherited_memory` type is weak in eventfulness, an existing support instruction is given `visual event inherited memory trace preserved on existing support`. This adds no new drawing part; it strengthens the placement, color cycle and semantic label of what is already there.

Build 446-2's full 30+30 benchmark (`cli/out/jp-en-30-equivalent-446-2/{jp,en}/`) gave 60 out of 60. Only JP #09 hit a stage 2 timeout on the final retry and used a fallback result (1/60). The quality averages were `visual_event` 92.85, `negative_space_pressure` 94.30, `motion_energy` 96.95, `constraint_adherence` 95.50 and `color_resonance` 99.75, meeting the guard of staying within -5 of Build 441. The repair parts were `adjacent_reaction` 13/60 (21.7%), `angular_pulse` 0/60 and `vanishing_trace` 1/60 (1.7%), so v1.52's repair-fingerprint gate passed too. `inherited_memory_arc`, which fable5 named as a candidate successor fingerprint, was newly measured at 4/60 (6.7%).

The relation drop rate, however, was 15/53 (28.3%) for Japanese and 22/51 (43.1%) for English, 37/104 (35.6%) combined, above the 20% figure fable5 had referred to. Since v1.52's relation policy is drop-only, with no repair or completion of a relation in coerce, this was treated as an unresolved risk as of Build 446-2. Any countermeasure was to be limited to improving the Stage 2 prompt toward "emit only a relation you can place safely, and omit it when in doubt", with no repair in the validator and no completion of relations.

Build 447 treated the relation drop as blocking and strengthened the firing conditions in the Stage 2 prompt. It stated that ordinary placement phrases — along a diagonal band, along a swaying path, along a river, along a road — are not relations; that `between` is used only where the two preceding contour instructions are both present; and that a relation is omitted when in doubt. But Build 447's full 30+30 benchmark gave a relation drop of 13/55 for Japanese and 4/29 for English, 17/84 (20.2%) combined, slightly above the 20% figure fable5 had made blocking.

Build 448 limited relations to a post-Stage-2 gate: a relation survives only where the normalized DDL literally contains 「前の線に沿って」, 「前の形に触れない」, 「前の線を切る」 or 「前の二つの間に」, or the corresponding previous-object phrase in English. Phrases from natural sentences — "around", "the same beat", "leading or lagging", "not touching", "near or far" — are not relations and are expressed through position, path, rotation and spacing. The coerce policy is unchanged; relations are neither repaired nor completed.

Build 448's full 30+30 benchmark (`cli/out/jp-en-30-equivalent-448/{jp,en}/`) gave 60 out of 60. Only JP #01 hit a stage 2 timeout on the final retry and used a fallback result (1/60). The combined quality averages were `visual_event` 92.40, `negative_space_pressure` 95.87, `motion_energy` 97.77, `constraint_adherence` 92.00 and `color_resonance` 99.27, meeting the guard of staying within -5 of Build 441. The repair parts were `adjacent_reaction` 14/60 (23.3%), `angular_pulse` 0/60, `vanishing_trace` 2/60 (3.3%) and `inherited_memory_arc` 4/60 (6.7%), meeting v1.52's repair-fingerprint gate. The relation drop was 1/6 (16.7%) for Japanese and 0/2 for English, 1/8 (12.5%) combined, below the 20% figure fable5 had made blocking. The relation sample rate is low on a natural-sentence fable set, but that follows from returning relations to fixed previous-object phrases only, and it is consistent with the drop-only validator policy. With that, v1.52's remaining tasks — vary, the repair fingerprint, the quality guard and the relation blocking — are treated as complete.

**v1.52 closure (2026-07-07)**: Build 448 is confirmed as the accepted v1.52 and closed. Four reasons. (1) Every acceptance criterion was met — the three repair-fingerprint gates, the quality-regression guard, vary's backward compatibility, determinism and spread, and the relation-drop blocking. (2) A three-persona re-evaluation of Build 448's 60 Japanese and English works (see `cli/tune_bench.md`) confirmed by eye that both of the problems that had prompted v1.52 at Build 441 — repair parts becoming a fingerprint, and the ceiling on the range — were resolved. The repetition of stock parts is gone, outliers (surprises) now appear, and from a curator's point of view 20 to 25 of the 60 are selectable. (3) The contraction in the use of relation — samples carrying one fell from 21 or 22 out of 30 to 2 or 3 — is accepted as specification: a relation is only for an explicit previous-object phrase in the normalized DDL (「前の線に沿って」 / 「前の形に触れない」 / 「前の線を切る」 / 「前の二つの間に」, and the English equivalents), and proximity, beat and leading or lagging from natural sentences are expressed through position, path, rotation and spacing. This is not a temporary workaround but the settled definition of the relation predicate in §14, and it is consistent with the drop-only validator policy. (4) Because the judge metrics such as `visual_event` were found to diverge from human evaluation (JP #23 scored `visual_event` 28 yet was among the best by eye), they are henceforth a reference for detecting regression rather than an acceptance gate. The final judgment of quality belongs, as §8 intends, to a human choosing afterwards. The judge metrics themselves are not retuned, which would make them a governor. The axis of completion for the work that follows moves from asymptotic improvement of a quality gate to "a state in which someone else can write their own visual tanka" (1.0). That plan is managed separately as v1.6.


### v1.60 (2026-07-07)

**From a quality loop to a state one can play in alone**

With the engine quality gate closed at v1.52 Build 448, the axis of completion moves from improving a metric to a state in which a third party can set up from the README alone, write their own visual tanka, consult the Saijiki, see the interpretation feedback, choose with vary, and reproduce from history.

- `render_hash` is redefined as the work-edition ID `rh2:<sha256>`. It is computed from the saved JSON Score, `render_seed`, `vary_seed`, `render_build_number`, `render_color_catalog_id` and the render engine metadata; the SVG body, the input text, the normalized DDL and the LLM response body are not among its main ingredients. The existing 64-character hex hash stays for legacy display compatibility.
- `vary_seed` is saved in the history database, so the same work can be re-rendered from history management using the saved Score and seed.
- Interpretation feedback, approximated as post-processing, is added to the input area. The Stage 1 schema and prompts are unchanged; Saijiki words, emotion words and words left in the DDL are shown in shades of ink.
- The work view shows the headnote — the input description — from the start, treating the tension between description and picture as part of the display.
- Quick Start, provider and API key setup, the two stages of regeneration, the six-color Saijiki constraint, and reproduction from history are added to the Japanese and English READMEs.
- The Build 448 gallery candidates are recorded in `docs/gallery-candidates-build448.md`. The final selection remains a human choice made afterwards.
- The final gallery selection is carried over to v1.70 and later. v1.60 completes the recording of candidates; selecting the works themselves belongs to the evaluation and publication work of the next generation.
- Phase E (Stage 1.5 handling of sparse output) adopts approach E-2. No new dedicated metric or marker is created; it is observed through the existing `visual_event` and `negative_space_pressure` and by eye. Sparse output is not a blocking implementation target in v1.60.

### v1.70 (2026-07-08)

- The previous and current works placed side by side, with a diff of the descriptions, are added to the left pane, so the traces of refinement can be viewed.
- As LLM Model Inspection, a viewing pane is added that runs the same description through the current Stage 1 model and another Stage 1 model in parallel and compares the normalized DDL and the output side by side. No judge values are shown.
- As a reference implementation of the Nature plugin, `Nature.風`, `Nature.うねり` and `Nature.無風` are added to Stage 1.5 as vocabulary macros. They fire only on an explicit reference in the `Nature.` namespace; ordinary vocabulary without a namespace behaves as before.
- The Nature plugin only leads existing DDL expression into variation and arrangement; it adds no primitive, no Score field and no coerce. Macros sufficed, so plugin principles 1 and 5 hold.
- A Nature plugin category is added to the Saijiki, shown in a pale vermilion that distinguishes it from ordinary vocabulary.
- Generating four candidates at once, saving several of them, an optional note when starring, and recording an `interpretation_seed` for another interpretation are added, connecting §8's afterwards choice to the UI and to history.
- Where the current Stage 1 provider is a cloud provider, LLM Model Inspection first offers a local provider needing no API key as the comparison target. This is an implementation choice so that a viewing comparison does not depend too heavily on a quota or on a provider being unavailable; judge values are still not shown.
- Multilingual tooltips are added to the main controls — four candidates, include the interpretation, keep the selection, model comparison, automatic repair. The tooltip wording follows the main UI's language switch, keeping the existing separation of display language from input language.
- The left app rail expands from an explicit expand/collapse toggle at the top left rather than on mouseover, avoiding accidental expansion and letting the user fix the width of the working area.
- Build 458 was confirmed on the pentala machine, with screenshots of D-1 and D-2 recorded in `no-git-sync/screen-cap/` and the notes in `cli/tune_bench.md`.

### v1.71 (2026-07-08)

- An instruction-level `surface` and a canvas-level `canvas.ground` are added to the JSON Score, so the texture of a plane and the texture of the canvas ground can be kept as abstract attributes separated from the details of the SVG implementation.
- Texture performance per display, editable and compat profile is added to the renderer. Display uses filters and clipPath, editable uses vector groups with stable IDs, and compat produces simplified output avoiding filters and clip-path.
- The handling of 「面:」 and 「地:」 and the surface and ground mapping are added to the Stage 1 and Stage 2 prompts, so a texture word becomes an attribute of the instruction it belongs to rather than an injected auxiliary shape.
- `render_texture_version`, `render_texture_profile`, `render_canvas_ground`, `render_surface_textures` and `texture_degraded` are added to the render metadata.
- The texture seed is derived from the Score, the instruction, the texture kind and the performance seed, so paper grain at fixed coordinates and frequent unrequested texture injection do not become the renderer's fingerprint.
- Multilingual tooltips are added and extended across the buttons and tabs of the left app rail and the input and output panels, making the controls clearer.
