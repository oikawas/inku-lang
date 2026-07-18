# inku

**One sentence becomes a picture.**

`inku` is the reference implementation of DDL (Drawing Description Language) — a description-based drawing language that turns a short written line into an abstract vector graphic. No drawing skill or tools are required to give your image a form. Writing down one scene that stayed with you, briefly, is the start — and from there you build the image up.

```
A blue line slowly loosens across the night water.
```

That sentence is interpreted, written into a score (drawing data in JSON), and performed (by inku's own rendering engine) into a picture. Generate again from the same sentence — not by AI, but by seeded variation — and a slightly different picture comes back. Every work you generate is kept under generational management as lineage: build variations on a work (by hand or through AI-assisted refinement), choose from the candidates lined up before you, and a new generation is born. **The back-and-forth of writing and choosing** is how creation works in inku.

inku stands at the crossing of ideas learned from three cultural traditions — and it is the result, or perhaps the ongoing process, of thinking about how generative-AI technology should be applied at that crossing.

| Tradition | What it gives inku |
|---|---|
| **Sol LeWitt's instruction art** | The idea that the description itself is the artwork; the concept from which this application began |
| **Bonsai** | The practice that constraint is not limitation but concentration |
| **Tanka** | The form in which the type silences the self, and presentation replaces assertion |

As of 2026, generative image and artwork making hides its own process from the creator; it might fairly be called incantatory — write a prompt, then pray, and repeat. The DDL concept takes the opposite path: it splits the generation process into layers, and the human interprets, selects, and edits the AI's interventions at each layer while finishing the work.

inku is built on LLMs, but each layer is placed under strict constraints. Constraints on vocabulary, primitives, and coordinates are not limits on what can be made. They are the instruments by which you make a work and render your intention visible.

---

## Documentation

Developers and AI agents should start with [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md). It summarizes the current architecture, contracts, and the smallest useful reading path without requiring a full specification reload.

- [SPEC.md](SPEC.md) — maintained public English specification (with excess detail trimmed)
- [SPEC.ja.md](SPEC.ja.md) — canonical Japanese specification (the author works Japanese-first, so the specification is authored in Japanese)
- [CHANGELOG.md](CHANGELOG.md) — public English release notes
- [CHANGELOG.ja.md](CHANGELOG.ja.md) — detailed canonical change history

Read the full specification for first-time onboarding, broad design changes, or consistency audits. For ordinary work, read the project context and only the relevant specification sections.

---

## How it works — score and performance

```
Your sentence (written in your native language)
     │  interpretation — the words are read into core vocabulary
     ▼
Normalized DDL (a human-readable intermediate form)
     │  structuring — written down as a score
     ▼
JSON Score (the score — saved deterministically)
     │  performance — drawn, with variation
     ▼
SVG (the performance — one-time)
```

**The description is permanent; the performance is one-time.** The score remains fixed, while each picture is born with its own variation. Just as LeWitt's instructions became a slightly different wall drawing under each craftsman's hand, the same score becomes a slightly different performance each time. Variation is not a bug here — it is the specification of the language.

---

## Example

**Description:**

```
A dashed pencil line, trembling finely, crossing the canvas — three of them.
```

**Normalized DDL (after interpretation):**

```
Line up three dashed pencil horizontal lines vertically. The lines tremble finely.
```

**JSON Score (after structuring, excerpt):**

```json
{
  "instructions": [
    {
      "primitive": "line",
      "style": "dashed",
      "from": [0.0, 0.33],
      "to": [1.0, 0.33],
      "weight": "pencil",
      "variation": {
        "amplitude": "fine",
        "frequency": "high",
        "quality": "perlin",
        "dimensions": ["position_y"]
      }
    }
  ]
}
```

The renderer performs this score — slightly differently each time. Because the output is vector, it holds up framed on paper, stretched across a wall, or viewed on a phone. There is no physical size constraint.

Scores may also carry surface and ground texture. A circle can say it is filled with wash or stipple through `instruction.surface`; the canvas can say it is off-white paper, washi, or ink-wash ground through `canvas.ground`. Those fields stay abstract. The renderer decides whether to perform them as SVG filters, clipped vector marks, or simplified compat output.

---

## Three ways to say "again"

Every result offers three tiers of regeneration. None of them breaks default reproducibility; each acts only on your explicit request.

| Operation | What is redrawn | What is kept |
|---|---|---|
| **Another performance** | Line tremor, placement phase (no LLM call) | Interpretation and composition |
| **Another composition** | Composition family, focus, technique | Interpretation (how the words were read) |
| **Another interpretation** | The reading of the words themselves | Your sentence |

With *another interpretation*, the old and new normalized DDL are shown side by side as a diff. The moment your words are read differently — that gap itself becomes material for the next sentence.

You can also generate a grid of candidates and keep the ones you like (multiple selection is allowed), attaching a short note about why you chose them. **Choosing is part of the work, alongside writing.** History stores seeds and an edition ID, so anything you keep can be reproduced exactly as it was.

---

## Core vocabulary (Saijiki)

The reference dictionary is called **Saijiki**（歳時記）— a word borrowed from haiku practice, where it names a book of seasonal words. It is not kept open while you write; it is something you go and consult when you hesitate.

| Category (EN) | Category (JA) | Vocabulary |
|---|---|---|
| forms | かたち | circle, ellipse, triangle, square, line, arc, cloudform |
| touches | てざわり | pen, pencil, rotring, fine-brush, thick-brush, crayon, chalk, burin, drypoint |
| motions | うごき | place, line-up, draw, scatter, fill, tile |
| places | ばしょ | top, bottom, center, left-edge, right-edge, top-edge, bottom-edge, middle, corner |
| continuity | つらなり | solid, dashed, dotted, dash-dot |
| movements | ゆらぎ | fine, large, slowly, quickly, swaying, undulating, trembling, blurring |
| colors | いろ | white, black, blue, red, green, gray |
| angles | かたむき | horizontal, vertical, diagonal, rising, falling, rotated |
| proportions | わりあい | tall, wide, full-width, half-width, semicircle, waxing, waning, crescent |
| relations | あいだ | along, not touching, cutting, between, touching (used as "along the previous line") |

The saijiki table in the implementation is the source of truth for the current vocabulary; `inku-cli reference --md` produces a machine-generated listing at any time.

Only physical, observable words belong to the core. Emotional evaluation — "beautifully," "delicately," "boldly" — is excluded, because evaluation belongs to the viewer, not the writer.

Outside the core live namespaced **plugin words** such as `Nature.wind`. A plugin is a validated `.inku-plugin.md` document, not code: it names a phenomenon and expands deterministically to core DDL. It cannot add shapes, Score fields, or executable code, and removing it does not change saved replay or rh2. Settings exposes load/rejection status, Saijiki shows qualified words with notes, and `inku-cli plugin list / validate / reload` provides administration.

---

## Architecture

```
 Your description (natural language, your native tongue)
      │
      ▼
┌──────────────────────────────────────┐
│ Stage 1   Interpretation (LLM)       │ free words → normalized DDL, core vocabulary only
├──────────────────────────────────────┤
│ Plugin   Declarative expansion (det.) │ namespaced words → core-only normalized DDL
├──────────────────────────────────────┤
│ Stage 1.5 Intermediate filter (det.) │ selects composition family and focus, attaches relations
├──────────────────────────────────────┤
│ Stage 2   Structuring (LLM)          │ normalized DDL → JSON Score (the score)
├──────────────────────────────────────┤
│ Renderer  Performance (seed-driven)  │ score → SVG; resolves variation, regions, relations
└──────────────────────────────────────┘
      │
      ▼
 SVG (for a wall, a page, a screen)
```

Interpretation and structuring are separated because they demand different abilities: interpretation is associative and creative; structuring is mechanical and rule-abiding. Each stage can be tuned independently, and API models, local LLMs, and NVIDIA NIM-style endpoints can be selected per stage. **The choice of model is itself a creative variable.**

Non-determinism lives in exactly two places: the renderer's performance (performance seed) and your explicit operations (another composition, another interpretation). The default path is always deterministic, and history's `render_seed` / `vary_seed` / `render_hash` (work edition ID) let any saved work be reproduced exactly.

---

## Design principles

1. Descriptions are human-readable, between natural language and code
2. Variation is a feature, not a bug
3. Emotional vocabulary is excluded; physical and motion vocabulary is embraced
4. No fixed canvas — coordinates are ratios from 0.0 to 1.0, scalable to any medium
5. Output is still — the viewer moves, not the image
6. Input is a constrained DSL, not free-form natural language

For the public English specification, see [SPEC.md](SPEC.md). The canonical Japanese source is [SPEC.ja.md](SPEC.ja.md).

---

## Quick Start

### 1. Backend

```sh
cd server
UV_CACHE_DIR=/tmp/inku-uv-cache UV_PYTHON_INSTALL_DIR=$HOME/.local/share/uv/python uv run inku-server
```

The default setup uses a local SQLite DB. To create the first admin account on a new DB, set `INKU_BOOTSTRAP_ADMIN_PASSWORD` explicitly.

### 2. LLM provider

Configure at least one provider for Stage 1 and Stage 2. Common environment variables are:

```sh
export INKU_LLM_BACKEND=nvidia        # nvidia / anthropic / local, etc.
export NVIDIA_API_KEY=...
export ANTHROPIC_API_KEY=...
export INKU_OVMS_BASE_URL=http://127.0.0.1:8000/v3
```

The web UI model settings page can also store provider/model choices and API keys. Saved API keys are not displayed again and are stored in encrypted DB form.

### 3. Web UI

```sh
cd web
npm install
npm run dev
```

Open `http://localhost:5173`, log in, and write a short description. Example:

```text
A blue line slowly loosens across the night water.
```

After generating, consult the Saijiki, read the ink-shaded interpretation feedback to see how your words were read, and refine the description if you like. Widen the field with *another performance*, *another composition*, or *another interpretation*, and keep what you love in history. The history manager replays any saved work with its stored seed.

### 4. CLI smoke test

```sh
cd cli
uv run inku-cli login --base-url http://127.0.0.1:8100 -u admin
uv run inku-cli paint "A blue line slowly loosens across the night water." --base-url http://127.0.0.1:8100 -o out/quickstart --prefix first --png --full-json
```

---

## Capabilities

- **Multi-stage pipeline** — Stage 1 / 1.5 / 2 / Renderer, with per-stage model selection; non-deterministic AI layers and deterministic algorithmic layers alternate
- **Refinement through regeneration** — another performance (no LLM call), another composition (vary seed), another interpretation (Stage 1 re-reading), LLM reselection, and generation management through lineage
- **Primitives and arrangement** — line, circle, ellipse, arc, square, triangle, cloudform; horizontal, vertical, radial, scatter, and literal tiling grid layouts with paths such as waves and diagonal bands
- **Regions and relations** — scores can state relations between elements ("along the previous line," "not touching the previous shape") that the performance resolves
- **Material rendering** — pencil, rotring, crayon, chalk, brushes, burin, and drypoint, differentiated through the shared stroke engine's width, tracking, and sparse events plus tool-specific edges
- **Plugins** — namespaced vocabulary macros such as `Nature.wind`; they expand into core vocabulary only and cannot modify the core
- **Interpretation feedback** — ink-density shading shows how each written word was read
- **History and editions** — per-user DB-backed history with stars, search, thumbnails, and exact reproduction via seeds and edition IDs
- **Batch / CLI** — `inku-cli` supports login, painting, batch generation, contact sheets, and diversity analysis
- **UI** — Saijiki panel, caption display of the source sentence beside the work, JSON/prompt views, light/dark mode, zoom/pan canvas

---

## Status

- **Web version** — operational (Python FastAPI + SvelteKit; runs locally or on a server)
- **CLI** — implemented as an independent `cli/` project; drives the API for login, drawing, batch generation, and benchmark output
- **Android app** — an older DDL demo has been verified on Pixel 9, but an Android version for the current inku-lang specification is not prepared yet

---

## Ecosystem

Related packages follow the `inku-` prefix convention:

- `inku-core` — core library
- `inku-saijiki` — vocabulary dictionary
- `inku-nature` — Nature plugin (wind, etc.)
- `inku-web` — web UI implementation
- `inku-android` — Android implementation
- `inku-cli` — command-line tool

---

## Language versions

The author maintains the **Japanese** and **English** versions of inku. Other language implementations are welcomed from the community as open-source contributions.

The internal JSON Score layer is language-neutral (English keys), so only the surface description layer needs translation.

---

## License

MIT License. See [LICENSE](LICENSE).

---

## Origin

Conceived on April 2, 2026, at the Museum of Contemporary Art Tokyo, on the final day of the *Sol LeWitt: Open Structures* exhibition.

Reaching into your own mind with words, and finding in what returns something that was always there — this is the experience inku attempts to make available in visual form.

> *The fog of the mind is brushed away, and what was always there comes into view.*

---

## Other Languages

- [日本語 README](README.ja.md)
