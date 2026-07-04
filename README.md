# inku

**A small, deliberately limited language for designing the visual — usable by anyone.**

`inku` is a description-based drawing language that turns short, writable-by-anyone descriptions into abstract vector graphics. It is rooted in three traditions:

- **Sol LeWitt's instruction-based art** — where the description itself is the artwork
- **The Japanese practice of bonsai** — where strict constraints on space and material do not limit expression, but concentrate it
- **The form of tanka** — where the type silences the self, and presentation replaces assertion

Constraints on vocabulary, primitives, and coordinate space are not limitations. They are the instruments by which intention becomes visible.

---

## Concept

```
description  →  normalized DDL  →  expanded DDL  →  score (JSON)  →  performance (SVG)
human           Stage 1             Stage 1.5        Stage 2          Renderer
```

The description is permanent. The performance is one-time. The output varies slightly each time — by design. The evolution and variance of models themselves become a source of this variation.

Computation is used as a medium, yet the same description yields something a little — or even greatly — different on each rendering.

---

## Example

**Description:**

```
A dashed pencil line, trembling finely, crossing the canvas — three of them.
```

**Normalized DDL (after first-stage interpretation):**

```
pencil dashed line, horizontal, 3 lines, placed
movement: fine tremble
```

**JSON Score (after second-stage structuring):**

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

The renderer then performs (draws) this score — slightly differently each time.

Someone else's instruction (song) can be rewritten, and since the output is vector, it can be stretched onto a wall, framed on paper, or displayed on a phone. There is no physical size constraint.

---

## Architecture

inku uses a **Stage 1 / Stage 1.5 / Stage 2 / Renderer** pipeline:

1. **Stage 1: Interpretation** — reads free-form descriptions in the author's native language and produces a normalized DDL using only core vocabulary
2. **Stage 1.5: Intermediate filter** — a deterministic expander that selects composition families and attaches observable relations instead of injecting fixed recipe layers
3. **Stage 2: Structuring** — converts normalized DDL into a valid JSON Score, including optional region and relation fields
4. **Renderer: Performance** — renders the JSON Score as SVG, resolving regions, relations, and performance seed variation

This separation lets natural-language interpretation, expression expansion, structure generation, and rendering be tuned independently. API models, local LLMs, and NVIDIA NIM-style endpoints can be selected per stage.

In the web UI, each result can be regenerated as **another performance** or **another composition**. Another performance rerenders the same JSON Score with a new performance seed and does not call an LLM. Another composition uses an explicit vary seed to reselect Stage 1.5 composition family, focus, and technique candidates while keeping the default path deterministic.

---

## Core Vocabulary (Saijiki / 歳時記)

The reference vocabulary dictionary is called **Saijiki**（歳時記）— a term borrowed from haiku practice, where it refers to a book of seasonal words. It is consulted, not always open.

| Category (EN) | Category (JA) | Vocabulary |
|---|---|---|
| forms | かたち | circle, ellipse, triangle, square, line, arc |
| touches | てざわり | pen, pencil, rotring, fine brush, thick brush, crayon, chalk, rope |
| motions | うごき | place, align, fill, scatter |
| places | ばしょ | top, bottom, center, edge, corner |
| continuity | つらなり | solid, dashed, dotted, dot-dashed |
| movements | ゆらぎ | fine, broad, quick, slow, wobble, undulate, tremble, blur |
| colors | いろ | white, black, blue, red, green, gray |
| rotation | かたむき | horizontal, vertical, diagonal, rotated |
| proportions | わりあい | tall, wide, full-width, half-width, semicircle, first-quarter, last-quarter, crescent |
| relations | あいだ | along, not touching, cutting, between |

Only physical and observational words are allowed. Emotional evaluation — "beautifully," "delicately," "powerfully" — is not part of the core.

---

## Design Principles

1. Descriptions are human-readable, between natural language and code
2. Variation is a feature, not a bug
3. Emotional vocabulary is excluded; physical and motion vocabulary is embraced
4. No fixed canvas — coordinates are ratios from 0.0 to 1.0, scalable to any medium
5. Output is still — the viewer moves, not the image
6. Input is a constrained DSL, not free-form natural language

For the public English specification, see [SPEC.md](SPEC.md).  The canonical
Japanese source is [SPEC.ja.md](SPEC.ja.md).

---

## Capabilities

The web version is operational. Current features:

- **Multi-stage pipeline** — Stage 1 / 1.5 / 2 / Renderer, with model, token, and elapsed-time metadata
- **Primitives** — line, circle, ellipse, arc, square, triangle; each can carry material, color, style, variation, rotation, and arrangement
- **Arrangement** — horizontal, vertical, radial, scatter, plus paths such as wave, diagonal band, top-to-bottom, left-to-right, and right-half
- **Regions and relations** — scores can leave placement to renderer-resolved regions and express relations such as along, not touching, cutting, and between previous elements
- **Material rendering** — pencil, rotring, crayon, chalk, brushes, and rope are rendered with texture filters, particles, secondary strokes, or twist marks, not only stroke width
- **Robust rendering** — invisible colors, over-dense arrangements, duplicate instructions, empty instructions, and slow LLM responses are corrected or routed to deterministic fallback
- **Batch / Demo / CLI** — single drawing, batch drawing, demo loop, and `inku-cli` login/paint/batch/benchmark workflows are supported
- **Diversity analysis** — CLI summaries include composition diversity, replay divergence, relation use, and relation drop metrics
- **History** — DB-backed per-user history with pagination, search, stars, thumbnails, model/color-catalog metadata, and token counts
- **UI** — Saijiki drawer, JSON/prompt views, light/dark mode, collapsible history strip, and zoom/pan canvas

---

## Status

Current implementations:

- **Web version** — operational (Python FastAPI + SvelteKit, runs locally or on a server)
- **CLI** — implemented as an independent `cli/` project; controls the API for login, drawing, batch generation, and benchmark output
- **Android app** — an older DDL demo has been verified on Pixel 9, but an Android version for the current inku-lang specification is not prepared yet

---

## Ecosystem

Related packages follow the `inku-` prefix convention:

- `inku-core` — core library
- `inku-saijiki` — vocabulary dictionary
- `inku-nature` — Nature plugin (wind, ripple, etc.)
- `inku-web` — web UI implementation
- `inku-android` — Android implementation
- `inku-cli` — command-line tool

---

## Language Versions

The author maintains the **Japanese** and **English** versions of inku. Other language implementations are welcomed from the community as open-source contributions.

The internal JSON Score layer is language-neutral (English keys), so only the surface description layer needs translation.

---

## License

MIT License. See [LICENSE](LICENSE).

---

## Origin

Conceived on April 2, 2026, at the Museum of Contemporary Art Tokyo, during the final day of the *Sol LeWitt: Open Structures* exhibition.

The experience of reaching into one's own mind with words, and finding in the return something that was always there — this is what inku attempts to make available in a visual form.

> *The fog of the mind is brushed away, and what was always there comes into view.*

---

## Other Languages

- [日本語 README](README.ja.md)
