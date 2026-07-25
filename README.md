# inku

**One sentence becomes a picture.**

<table align="center">
<tr>
<td width="33%"><img src="docs/assets/gallery/ballroom-current-waltz.png" width="100%" alt="A deep blue field crossed by dense bundles of thin white and gray lines running diagonally in two directions, with flocks of short dashes scattered between them"></td>
<td width="33%"><img src="docs/assets/gallery/armistice-morning-silver-shoal.png" width="100%" alt="On a white ground, gray wavy lines run in layered bands with small black ellipses shoaling across them, and a single red line descends at the right edge"></td>
<td width="33%"><img src="docs/assets/gallery/blackout-candle-lattice.png" width="100%" alt="On a black ground, dozens of white crayon-scrubbed squares overlap into an uneven mass with gaps left open, a small red mark near the center"></td>
</tr>
</table>

`inku` is the reference implementation of DDL (Drawing Description Language) — a description-based drawing language that turns a short written line into an abstract vector graphic. No drawing skill or tools are required to give your image a form. Writing down one scene that stayed with you, briefly, is the start — and from there you build the image up.

```
A blue line slowly loosens across the night water.
```

That sentence is interpreted, written into a score (drawing data in JSON), and performed (by inku's own rendering engine) into a picture. Generate again from the same sentence — not by AI, but by seeded variation — and a slightly different picture comes back. Every work you generate is kept under generational management as lineage: build variations on a work (by hand or through AI-assisted refinement), choose from the candidates lined up before you, and a new generation is born. **The back-and-forth of writing and choosing** is how creation works in inku.

inku stands at the crossing of ideas learned from three cultural traditions — and it is the result, or perhaps the ongoing process, of thinking about how generative-AI technology should be applied at that crossing.

| Tradition | What it gives inku |
|---|---|
| **Sol LeWitt's instruction art** | The idea that the description itself is the work; the concept from which this application began |
| **Bonsai** | The practice that constraint is not limitation but concentration |
| **Tanka** | The form in which the type silences the self, and presentation replaces assertion |

As of 2026, generative image and picture making hides its own process from the creator; it might fairly be called incantatory — write a prompt, then pray, and repeat. The DDL concept takes the opposite path: it splits the generation process into layers, and the human interprets, selects, and edits the AI's interventions at each layer while finishing the work.

inku is built on LLMs, but each layer is placed under strict constraints. Constraints on vocabulary, primitives, and coordinates are not limits on what can be made. They are the instruments by which you make a work and render your intention visible.

---

## Works — a description becoming a picture

The pieces below were drawn by inku. **Under each picture is the sentence that was written (the headnote) and the instructions (normalized DDL) that grew out of it.** The correspondence between words and picture is what this language is about.

These works were written in Japanese; the original text is given with an English rendering.

<table><tr><td><img src="docs/assets/gallery/ballroom-current-waltz.png" width="480" alt="A deep blue field crossed by dense bundles of thin white and gray lines running diagonally in two directions, with flocks of short dashes scattered between them"></td></tr></table>

> *In the ballroom of the sunken liner, only the current kept the time of the last waltz.*
>
> 沈んだ客船の舞踏室で、海流だけが、最後のワルツの拍子を守っていた。

<details>
<summary>Instructions (normalized DDL) and source SVG</summary>

```
背景を青で塗りつぶす。
青い細筆の波打つ線を左から右へ横に四十本並べる。
線はゆっくり揺れる。
```

> Fill the background with blue.
> Line up forty undulating blue fine-brush lines horizontally, from left to right.
> The lines sway slowly.

[ballroom-current-waltz.svg](docs/assets/gallery/ballroom-current-waltz.svg) — seed `7735827479582915` / color catalog inku Default

</details>

<table><tr><td><img src="docs/assets/gallery/armistice-morning-silver-shoal.png" width="480" alt="On a white ground, gray wavy lines run in layered bands with small black ellipses shoaling across them, and a single red line descends at the right edge"></td></tr></table>

> *On the morning the war ended, the sniper and the fisherman on opposite banks were watching the same silver of the shoal.*
>
> 戦争が終わった朝、対岸の狙撃手と漁師は、同じ魚群の銀色を見ていた。

<details>
<summary>Instructions (normalized DDL) and source SVG</summary>

```
背景を白で塗りつぶす。
画面下半分に灰色の細筆の横線を二十本並べる。
中央付近に白い小さな楕円を百二十個、波打つ軌跡に沿って散らす。
右端に黒い鉛筆の縦線を一本引く。
```

> Fill the background with white.
> Line up twenty gray fine-brush horizontal lines across the lower half.
> Scatter one hundred and twenty small white ellipses near the center, along an undulating path.
> Draw one black pencil vertical line at the right edge.

[armistice-morning-silver-shoal.svg](docs/assets/gallery/armistice-morning-silver-shoal.svg) — seed `1759981552357047` / color catalog inku Default

</details>

<table><tr><td><img src="docs/assets/gallery/blackout-candle-lattice.png" width="480" alt="On a black ground, dozens of white crayon-scrubbed squares overlap into an uneven mass with gaps left open, a small red mark near the center"></td></tr></table>

> *On the night of the blackout, candles were lit one by one in the windows of the housing block, and an uneven lattice surfaced in the dark.*
>
> 停電の夜、団地の窓にひとつずつ蝋燭が灯り、闇に不揃いな格子が浮かんだ。

<details>
<summary>Instructions (normalized DDL) and source SVG</summary>

```
背景を黒で塗りつぶす。
黄色いクレヨンの小さな四角を画面全体に点々と四十八個散らす。
四角は不揃いに並べる。
```

> Fill the background with black.
> Scatter forty-eight small yellow crayon squares across the whole canvas.
> Arrange the squares unevenly.

[blackout-candle-lattice.svg](docs/assets/gallery/blackout-candle-lattice.svg) — seed `6197114075822707` / color catalog inku Default

</details>

<table><tr><td><img src="docs/assets/gallery/whale-bones-low-tide-city.png" width="480" alt="An off-white ground: a large dull red circle at the upper right, a thin red arc opening downward at the upper left, and two tall frames in the lower half sprinkled with small blue and gray dots"></td></tr></table>

> *In the city after the sea withdrew, whale bones lay in the canyon between the buildings, combing the morning sun.*
>
> 海が引いたあとの街で、ビルの谷間に鯨の骨が横たわり、朝日を梳いていた。

<details>
<summary>Instructions (normalized DDL) and source SVG</summary>

```
背景を白で塗りつぶす。
黒いロットリングの縦長の四角を左右に三つずつ並べる。
白いビュランの太い弧を中央に一本引く。
白いビュランの短い線を弧に沿って二十本並べる。
右上に黄色い大きな円を置く。
```

> Fill the background with white.
> Line up three tall black rotring squares on each side, left and right.
> Draw one thick white burin arc through the center.
> Line up twenty short white burin lines along the arc.
> Place a large yellow circle at the upper right.

[whale-bones-low-tide-city.svg](docs/assets/gallery/whale-bones-low-tide-city.svg) — seed `7251697323642884` / color catalog Desert Mineral

</details>

<table><tr><td><img src="docs/assets/gallery/aquarium-jellyfish-phases.png" width="480" alt="On a navy ground, three translucent red and blue masses overlap into a bell-like form, ringed by thin white and blue loops, with a slender red thread trailing below"></td></tr></table>

> *In the aquarium with its lights out, the jellyfish waxed and waned slowly, in place of the moon.*
>
> 灯りを消した水族館で、くらげは月の代わりに、ゆっくりと満ち欠けした。

<details>
<summary>Instructions (normalized DDL) and source SVG</summary>

```
背景を黒で塗りつぶす。白い細筆の雲形を中央に三つ、大きさの異なる順に並べる。波打つ軌跡に沿ってゆっくり揺れる。
```

> Fill the background with black. Line up three white fine-brush cloudforms at the center, ordered by differing size. They sway slowly along an undulating path.

[aquarium-jellyfish-phases.svg](docs/assets/gallery/aquarium-jellyfish-phases.svg) — seed `2184785730279672` / color catalog Weathered Heritage

</details>

<table><tr><td><img src="docs/assets/gallery/silent-piano-dust-chord.png" width="480" alt="On an off-white ground, about ten pairs of gray vertical bars and thin frames step upward from lower left to upper right, with three pale red wavy lines crossing the empty space"></td></tr></table>

> *Inside the piano no one plays anymore, dust assembled a chord of light in the order of the keys.*
>
> 誰も弾かなくなったピアノの中で、埃が鍵盤の順番に、光の和音を組んでいた。

<details>
<summary>Instructions (normalized DDL) and source SVG</summary>

```
背景を黒で塗りつぶす。
白いロットリングの縦長の四角を横に二十本並べる。
白い鉛筆の小さな四角を、前の四角の上に一つずつ、画面全体に点々と散らす。
細かく震える。
```

> Fill the background with black.
> Line up twenty tall white rotring squares horizontally.
> Scatter small white pencil squares across the whole canvas, one on top of each previous square.
> They tremble finely.

[silent-piano-dust-chord.svg](docs/assets/gallery/silent-piano-dust-chord.svg) — seed `6064752967664899` / color catalog Dye & Earth

</details>

All six were generated on Build 667 with render engine 10, using `nvidia:google/gemma-4-31b-it` for both Stage 1 and Stage 2. The grounds differ from work to work because a different **color catalog** was selected: the same "white" or "black" in the instructions is translated into the gamut of the chosen catalog.

---

## How it works — score and performance

```
Your sentence (written in your native language)
     │  interpretation — the words are read into core vocabulary
     ▼
Instructions (Normalized DDL — a human-readable executable specification)
     │  structuring — written down as a score
     ▼
JSON Score (the score — saved deterministically)
     │  performance — drawn, with variation
     ▼
SVG (the performance — one-time)
```

**The description is permanent; the performance is one-time.** The score remains fixed, while each picture is born with its own variation. Just as LeWitt's instructions became a slightly different wall drawing under each craftsman's hand, the same score becomes a slightly different performance each time. Variation is not a bug here — it is the specification of the language.

### Vocabulary and layers

| Term | Layer / act |
|---|---|
| **Description** | The poem-like input the author writes. The top layer of the work (inku-specific; no LeWitt counterpart) |
| **Interpret** | Stage 1's act of reading the description into instructions |
| **Instructions (Normalized DDL)** | The executable specification the interpretation produces. Corresponds to LeWitt's instruction sheet |
| **Score (JSON Score)** | The structured intermediate form of the instructions. Stored deterministically |
| **Performance (SVG)** | The one-time result of playing the score |
| **Headnote** | The description raised beside the finished work — kotobagaki, the note set beside a poem |
| **Reading** | Rebuilding candidates by re-reading the words (another interpretation) |

### One work, followed through the layers

Take the second piece in the gallery, the silver of the shoal. The description was this sentence:

```
戦争が終わった朝、対岸の狙撃手と漁師は、同じ魚群の銀色を見ていた。
（On the morning the war ended, the sniper and the fisherman on opposite banks
 were watching the same silver of the shoal.）
```

Interpretation reads it into instructions (normalized DDL). Neither the sniper nor the fisherman nor the war survives — only shape, material, and motion.

```
背景を白で塗りつぶす。
画面下半分に灰色の細筆の横線を二十本並べる。
中央付近に白い小さな楕円を百二十個、波打つ軌跡に沿って散らす。
右端に黒い鉛筆の縦線を一本引く。
（Fill the background with white. Line up twenty gray fine-brush horizontal lines
 across the lower half. Scatter one hundred and twenty small white ellipses near
 the center, along an undulating path. Draw one black pencil vertical line at the
 right edge.）
```

Structuring writes those instructions down as a score (JSON Score). This is the excerpt actually stored — the second of three instructions, the shoal itself, with `null` fields omitted.

```json
{
  "version": "0.1.0",
  "canvas": "square",
  "background": "white",
  "instructions": [
    {
      "primitive": "ellipse",
      "center": [0.5, 0.5],
      "size": [0.02, 0.01],
      "rotation": 18.0,
      "filled": false,
      "weight": "pencil",
      "color": "black",
      "variation": {
        "amplitude": "medium",
        "frequency": "slow",
        "quality": "wave",
        "dimensions": ["position_x", "position_y"]
      },
      "arrangement": {
        "count": 110,
        "layout": "scatter",
        "path": "wave",
        "color_cycle": ["black", "white"],
        "density": "high",
        "cluster_count": 7,
        "fade": "outward",
        "rhythm_spacing": "loose"
      },
      "surface": {
        "texture": "wash",
        "opacity": 0.6,
        "tone_steps": 3
      }
    }
  ]
}
```

"Shoal" landed in `count` and `cluster_count: 7`; "along an undulating path" landed in `path: wave`; "silver" landed in `color_cycle` and `surface.texture: wash`. The "opposite bank" became the single vertical line at the right edge. The renderer performs this score — slightly differently each time. Because the output is vector, it holds up framed on paper, stretched across a wall, or viewed on a phone. There is no physical size constraint.

Scores may also carry surface and ground texture. A circle can say it is filled with wash or stipple through `instruction.surface`; the canvas can say it is off-white paper, washi, or ink-wash ground through `canvas.ground`. Those fields stay abstract. The renderer decides whether to perform them as SVG filters, clipped vector marks, or simplified compat output.

---

## Screens — the back-and-forth of writing and choosing

The description sits on the left, the work on the right, and the **instructions (normalized DDL)** in between, ink-shaded to show how each written word was read. History runs along the bottom.

<table><tr><td><img src="docs/assets/ui/describe-and-paint-dark.en.png" width="900" alt="The description input on the left with word-highlighted instructions (normalized DDL) beneath it, a large canvas on the right showing pale overlapping squares on a cream ground, and a strip of history thumbnails along the bottom"></td></tr></table>

Switching to Lineage lays out the generations that grew from that work. Whichever work is displayed becomes the parent of your next refinement. **Choosing is part of the work, alongside writing.**

<table><tr><td><img src="docs/assets/ui/lineage-dark.en.png" width="900" alt="The lineage tab: two arrows descend from the first-generation work card to two second-generation candidates, while the description and instructions remain on the left"></td></tr></table>

The instructions can be edited by hand and drawn again. Selecting a word in the Saijiki on the right returns a sample of that stroke and a note on what it does — so you write while looking, rather than after memorizing the vocabulary. Light and dark themes can be switched at any time.

<table><tr><td><img src="docs/assets/ui/edit-instructions-saijiki-light.en.png" width="900" alt="The instructions editor dialog: numbered instruction lines on the left, and the Saijiki on the right showing a stroke sample and explanation for the selected thick-brush, with vocabulary buttons grouped by forms, touches, angles and colors. Light theme"></td></tr></table>

---

## Pursuing the work through revision

The drawing that comes back from one sentence is not the finished piece. It is the **first generation**. You redraw from it, then redraw from what came back — **the work is made by accumulating generations**.

This is not pulling a lever until something good appears. Redrawing is split across five axes, and **you decide which one moves and which ones hold**. Then **you choose** among what comes back. That loop of variation and choice is what turns output into a work.

### Five ways to redraw

None of them breaks default reproducibility; each acts only on your explicit request.

| Operation | What is redrawn | What is kept | Cost |
|---|---|---|---|
| **Another performance** | Line tremor, placement phase | Interpretation and composition | Very fast, no LLM call |
| **Another catalog** | The color assignment | Interpretation, composition, performance | Very fast, no LLM call |
| **Another composition** | Composition family, focus, technique | Interpretation (how the words were read) | Medium, Stage 2 |
| **Variation** (let the app change Stage 1.5) | Axes of the expansion layer; the range depends on the strength | Your sentence, its reading, and the axes the strength leaves alone | Moderate, Stage 2 |
| **Another interpretation** | The reading of the words themselves | Your sentence | Slower, from Stage 1 |

With *another interpretation*, the old and new instructions are shown side by side as a diff. The moment your words are read differently — that gap itself becomes material for the next sentence.

*Variation* is the one where you say how far to go, in three steps. After it runs, the axes that actually moved are listed, so you never have to guess what changed.

| Strength | Axes that move | Axes that hold |
|---|---|---|
| Small | One among type swap and count | Focus, color, composition |
| Medium | The small axes plus touch, focus, main and contrast color (one or two) | Composition family, type family |
| Large | The medium axes plus composition family and type family (two to four) | — the structure of the picture moves too |

### Letting the AI carry it

Instead of picking the axis yourself, you can hand the act of accumulating generations to the AI. There are two modes.

- **Random automatic refinement** — each generation picks an axis at random from the ones you allowed
- **AI Vision automatic refinement** — each image is actually observed, and one direction is passed to the next generation

Either mode accepts a direction of your own (a sentence such as "festive, and yet cool"). Everything born while the AI runs is still recorded in the lineage, so you can pick a drawing from the middle of the run and go back to redrawing it by hand.

### Accumulating generations

Candidates can be made one at a time or as a grid of four. Keep the ones you like (multiple selection is allowed) and **attach a short note about why you chose them**. **Choosing is part of the work, alongside writing.**

What you keep becomes the next parent. Another performance from there, another catalog, a variation — the whole back and forth is recorded in the **lineage**, so you can trace later which generation you redrew what from to arrive at the drawing in front of you. History stores seeds and an edition ID, so any generation along the way can be reproduced exactly as it was.

**A piece is finished not when a generation happens to land, but when you decide to stop here.**

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

Only physical, observable words belong to the core. Emotional evaluation — "beautifully," "delicately," "boldly" — is excluded, because evaluation belongs to the viewer, not the writer. Read the gallery descriptions again and you will find not one evaluative word among them.

Outside the core live namespaced **plugin words** such as `Nature.wind`. A plugin is a validated `.inku-plugin.md` document, not code: it names a phenomenon and expands deterministically to core DDL. It cannot add shapes, Score fields, or executable code, and removing it does not change saved replay or rh2. Settings exposes load/rejection status, Saijiki shows qualified words with notes, and `inku-cli plugin list / validate / reload` provides administration.

---

## Architecture

```
 Your description (natural language, your native tongue)
      │
      ▼
┌──────────────────────────────────────┐
│ Stage 1   Interpretation (LLM)       │ free words → instructions, core vocabulary only
├──────────────────────────────────────┤
│ Plugin   Declarative expansion (det.) │ namespaced words → core-only instructions
├──────────────────────────────────────┤
│ Stage 1.5 Intermediate filter (det.) │ selects composition family and focus, attaches relations
├──────────────────────────────────────┤
│ Stage 2   Structuring (LLM)          │ instructions → JSON Score (the score)
├──────────────────────────────────────┤
│ Renderer  Performance (seed-driven)  │ score → SVG; resolves variation, regions, relations
└──────────────────────────────────────┘
      │
      ▼
 SVG (for a wall, a page, a screen)
```

Interpretation and structuring are separated because they demand different abilities: interpretation is associative and creative; structuring is mechanical and rule-abiding. Each stage can be tuned independently, and API models, local LLMs, and NVIDIA NIM-style endpoints can be selected per stage. **The choice of model is itself a creative variable.**

Non-determinism lives in exactly two places: the renderer's performance (performance seed) and your explicit operations (another composition, another interpretation). The default path is always deterministic, and history's `render_seed` / `vary_seed` / `render_hash` (work edition ID) let any saved work be reproduced exactly. That is why each gallery work above carries its seed.

---

## Design principles

1. Descriptions are human-readable, between natural language and code
2. Variation is a feature, not a bug
3. Emotional vocabulary is excluded; physical and motion vocabulary is embraced
4. No fixed canvas — coordinates are ratios from 0.0 to 1.0, scalable to any medium
5. Output is still — the viewer moves, not the image
6. Input is a constrained DSL, not free-form natural language
7. The engine does not go backwards — like a woodblock being carved, the drawing engine only moves in one direction

For the public English specification, see [SPEC.md](SPEC.md). The canonical Japanese source is [SPEC.ja.md](SPEC.ja.md).

---

## The engine as a woodblock

inku's drawing engine has **no past versions**. There is a tenth-generation engine and nothing else; the ninth cannot be selected. Its code is not kept either.

This is a choice, not an omission.

> The carving advances. The block only changes in one direction. The prints that came off it remain, but the block cannot be returned to what it was before the cut.
> **If the application itself is thought of as a work, this is the implementation that follows.**

A saved work is **a print**. The SVG itself persists, so the piece as it was can always be seen. The engine is **the block**, and only its carved-forward state exists. Redrawing pulls a fresh print from the current engine, and that is a new edition. Both are never warehoused at once.

### So proof prints are pulled before the next cut

The block cannot be restored. The prints can be kept.

When a generation of the engine rises, losing track of **what that generation drew and how** makes the change impossible to verify afterwards. So for each generation, the actual output from a fixed set of inputs is frozen (`server/reference/`) — 220 cases: ten tools against eight shapes as the base, plus variation, fills, canvas ratios, and boundary values.

| | |
|---|---|
| What is frozen | the **actual output** (the SVG, its element counts, classes, and a coordinate digest) |
| How it holds | CI fails if regenerating an existing case is not byte-identical |
| When it differs | the drawing changed — **increment the engine version** |

A version number carries only one bit: that something moved. **What moved, and how, can only be answered by comparing the outputs themselves.** Each time a generation rises, only the cases that moved are recorded. The number of directories is itself the record of how many times the engine changed.

**That cost has already been paid.** The output of generations 1 through 9 is gone — neither code nor pictures survive. That is why the reference corpus begins at the tenth. So the prints are pulled while a generation is still current.

---

## Quick Start

### 0. Docker (release images, fastest)

Releases are distributed as container images on GHCR (`ghcr.io/oikawas/inku-api` / `inku-web`, amd64 / arm64).

```sh
curl -fsSLO https://raw.githubusercontent.com/oikawas/inku-lang/main/deploy/compose.yaml
curl -fsSLO https://raw.githubusercontent.com/oikawas/inku-lang/main/deploy/.env.example
cp .env.example .env   # fill in your LLM API key and INKU_BOOTSTRAP_ADMIN_PASSWORD (8+ characters)
docker compose up -d   # → http://localhost:5173
```

See [`deploy/README.md`](deploy/README.md) for the first account, data persistence, version pinning, and HTTPS. The steps below run from source.

### 1. Backend

```sh
cd server
UV_CACHE_DIR=/tmp/inku-uv-cache UV_PYTHON_INSTALL_DIR=$HOME/.local/share/uv/python uv run inku-server
```

The default setup uses a local SQLite DB. There is no self-signup, so on a new DB nobody can sign in until you create the bootstrap admin with `INKU_BOOTSTRAP_ADMIN_PASSWORD` (8+ characters). Setting it later and restarting creates the account (an empty string is treated as unset, and DBs that already have accounts are left untouched).

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
- **Color catalogs** — the same "white" or "black" in the instructions is translated into the gamut of the selected catalog (this is why the gallery grounds differ)
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

## Documentation

Developers and AI agents should start with [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md). It summarizes the current architecture, contracts, and the smallest useful reading path without requiring a full specification reload.

- [SPEC.md](SPEC.md) — maintained public English specification (with excess detail trimmed)
- [SPEC.ja.md](SPEC.ja.md) — canonical Japanese specification (the author works Japanese-first, so the specification is authored in Japanese)
- [CHANGELOG.md](CHANGELOG.md) — public English release notes
- [CHANGELOG.ja.md](CHANGELOG.ja.md) — detailed canonical change history

Read the full specification for first-time onboarding, broad design changes, or consistency audits. For ordinary work, read the project context and only the relevant specification sections.

---

## Other Languages

- [日本語 README](README.ja.md)
