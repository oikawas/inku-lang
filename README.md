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
description (DDL text)  →  score (JSON)  →  performance (SVG)
written by a human         interpreted by LLM   rendered by machine
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

inku uses a **two-stage conversion pipeline**:

1. **Interpretation stage** (designed for advanced, frontier-class models — accessed via API or local GPU environments) — reads free-form descriptions in the author's native language and produces a normalized DDL using only core vocabulary
2. **Structuring stage** (designed for lightweight, mature models — typically local LLMs) — converts the normalized DDL into a valid JSON Score

This separation lets each stage focus on what it does best. The interpretation stage handles the creative, associative reading of natural language. The structuring stage handles the rule-following generation of structured output.

---

## Core Vocabulary (Saijiki / 歳時記)

The reference vocabulary dictionary is called **Saijiki**（歳時記）— a term borrowed from haiku practice, where it refers to a book of seasonal words. It is consulted, not always open.

| Category (EN) | Category (JA) | Vocabulary |
|---|---|---|
| forms | かたち | circle, ellipse, triangle, square, line, arc |
| touches | てざわり | pen, brush, crayon, chalk, rope |
| motions | うごき | place, align, fill, scatter |
| places | ばしょ | top, bottom, center, edge, corner |
| continuity | つらなり | solid, dashed, dotted, dot-dashed |
| movements | ゆらぎ | fine, broad, quick, slow, wobble, undulate, tremble, blur |
| colors | いろ | white, black, blue, red, green, gray |
| proportions | わりあい | tall, wide, full-width, half-width, semicircle, first-quarter, last-quarter, crescent |

Only physical and observational words are allowed. Emotional evaluation — "beautifully," "delicately," "powerfully" — is not part of the core.

---

## Design Principles

1. Descriptions are human-readable, between natural language and code
2. Variation is a feature, not a bug
3. Emotional vocabulary is excluded; physical and motion vocabulary is embraced
4. No fixed canvas — coordinates are ratios from 0.0 to 1.0, scalable to any medium
5. Output is still — the viewer moves, not the image
6. Input is a constrained DSL, not free-form natural language

For the full design rationale, see [SPEC.md](./SPEC.md).

---

## Capabilities (v1.2)

The web version is operational. Current features:

- **Two-stage pipeline** — interpretation (frontier LLM) + structuring (lightweight LLM), with live stage display during rendering
- **Primitives** — line, circle, ellipse, arc, square, triangle; all with weight, color, style, and variation
- **Arrangement** — horizontal, vertical, radial, scatter layouts; count up to 1,000; color cycle
- **Variation (揺らぎ)** — perlin, wave, pink, white noise applied to position axes
- **Background color** — canvas background controllable per drawing
- **Closed-shape fill** — circle, ellipse, square, triangle fill automatically when color is specified
- **Proportions vocabulary (わりあい)** — tall/wide rectangles, full/half-width lines, arc-based moon shapes
- **Batch mode** — enter multiple descriptions line-by-line; processed sequentially with progress display
- **History** — server-side, unlimited, paginated; thumbnail strip with model info
- **Saijiki panel** — vocabulary reference, click-to-insert

---

## Status

Current implementations:

- **Web version** — operational (Python FastAPI + SvelteKit, runs locally or on a server)
- **Android app** — end-to-end working demo on Pixel 9 with Gemma 4 running locally

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

MIT License. See [LICENSE](./LICENSE).

---

## Origin

Conceived on April 2, 2026, at the Museum of Contemporary Art Tokyo, during the final day of the *Sol LeWitt: Open Structures* exhibition.

The experience of reaching into one's own mind with words, and finding in the return something that was always there — this is what inku attempts to make available in a visual form.

> *The fog of the mind is brushed away, and what was always there comes into view.*

---

## Other Languages

- [日本語 README](./README.ja.md)
