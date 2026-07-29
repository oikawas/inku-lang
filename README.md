<p align="center">
  <img src="docs/assets/incu-icon-512.png" width="120" alt="The inku icon: small gray, black, blue, red and green squares set in a cross on a dark rounded square">
</p>

<p align="center">
  <a href="README.ja.md">日本語</a> ｜ <strong>English</strong>
</p>

# inku

**One sentence becomes a picture.**

> **一文が、絵になる。**
> `inku`（インク）は、短い記述から抽象的なベクターグラフィックを生み出す描画言語 DDL（Drawing Description Language）のリファレンスとなるアプリケーションです。絵画の経験や道具が無くても、自分のイメージを形に出来ます。心に残った光景をひとつ、短く書くことが始まりで、そこから作品を作っていくことが出来ます。
> **日本語の全文は [日本語版 README](README.ja.md) にあります。**

<table align="center">
<tr>
<td width="33%"><img src="docs/assets/gallery/ballroom-current-waltz.png" width="100%" alt="A deep blue field crossed by dense bundles of thin white and gray lines running diagonally in two directions, with flocks of short dashes scattered between them"></td>
<td width="33%"><img src="docs/assets/gallery/armistice-morning-silver-shoal.png" width="100%" alt="On a white ground, gray wavy lines run in layered bands with small black ellipses shoaling across them, and a single red line descends at the right edge"></td>
<td width="33%"><img src="docs/assets/gallery/blackout-candle-lattice.png" width="100%" alt="On a black ground, dozens of white crayon-scrubbed squares overlap into an uneven mass with gaps left open, a small red mark near the center"></td>
</tr>
</table>

`inku` is the reference application for DDL (Drawing Description Language) — a description-based drawing language that turns a short written line into an abstract vector graphic. No experience with drawing and no tools are required to give your image a form. Writing down one scene that stayed with you, briefly, is the beginning — and from there you build the work up.

```
A blue line slowly loosens across the night water.
```

That sentence is interpreted, becomes a score, and is performed into the form of a vector graphic until a picture appears. Draw again from the same sentence and the sway brings back a slightly different picture. Works are kept as lineage and saved generation by generation. You build variations on that first work, refine it, choose, and a new generation is born — **the back-and-forth of writing and choosing** is how creation works in inku. You may hold on to that first sentence and carry it all the way to a finished work, or forget it along the way. DDL implements no meaning and no feeling; what you make it carry is yours to decide.

inku began in a museum, standing in front of a Sol LeWitt exhibition and wondering whether such a mechanism was something one could build oneself. It starts mainly from the three ideas below.

| Culture / tradition | What it gives inku |
|---|---|
| **Sol LeWitt's instruction art** | The idea that the description itself is the work; the concept the application grew out of |
| **Bonsai** | The practice that constraint is not limitation but concentration |
| **Tanka** | The form in which the type silences the self, and presentation replaces assertion |

As of 2026, generative image making hides its process from the creator; it might fairly be called incantatory — write a prompt, then pray, and repeat. The DDL concept splits the generation process into layers, alternating generative AI with deterministically programmed algorithms.

inku is built on LLMs, but the elements an instruction is made of — vocabulary, primitives, coordinates — are placed under strict constraints, programmed to take up the author's intent while holding the form. Those constraints are not limits on what can be made. They are the instruments by which you make a work and render your intention visible.

---

## Works — a description becoming a picture

**Under each picture is the sentence that was written (the headnote) and the instructions (normalized DDL) that grew out of it.** The correspondence between words and picture is what this language is about.

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

All three were generated on Build 667 with render engine 10, using `nvidia:google/gemma-4-31b-it` for both Stage 1 and Stage 2. Only the third has a different ground, because a different **color catalog** was selected: the same "white" or "black" in the instructions is translated into the gamut of the chosen catalog.

**Three more works are in the [gallery](docs/guide/gallery.md).**

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

See [`deploy/README.md`](deploy/README.md) for the first account, data persistence, version pinning, and HTTPS.

### 1. Running from source

```sh
cd server && UV_CACHE_DIR=/tmp/inku-uv-cache uv run inku-server   # API (SQLite by default)
cd web && npm install && npm run dev                              # → http://localhost:5173
```

At least one LLM provider is needed for Stage 1 and Stage 2 (`INKU_LLM_BACKEND` plus an API key, or the model settings page in the web UI). **You can also start without an API key at all** — choose a local [Ollama](https://ollama.com) as the provider; the steps and the recommended models are in [SETUP.md](SETUP.md). There is no self-signup, so on a new DB nobody can sign in until you create the bootstrap admin with `INKU_BOOTSTRAP_ADMIN_PASSWORD` (8+ characters).

Once you are logged in, write a short description. After generating, consult the Saijiki, read the ink-shaded interpretation feedback to see how your words were read, and refine the description if you like.

The full environment variable list, per-provider configuration, and the CLI (`inku-cli`) are covered in [SETUP.md](SETUP.md).

---

## How it works — score and performance

```
Your sentence (written in your native language)
     │  interpretation — the words are read into core vocabulary (Stage 1, LLM)
     ▼
Instructions (Normalized DDL — a human-readable executable specification)
     │  structuring — written down as a score (Stage 2, LLM)
     ▼
JSON Score (the score — saved deterministically)
     │  performance — drawn, with sway (Renderer, seed-driven)
     ▼
SVG (the performance — one-time; for a wall, a page, a screen)
```

**The description is permanent; the performance — the rendering — is one-time.** The score remains fixed, while each picture is born with its own sway (technically speaking, the score is kept as JSON). Just as LeWitt's instructions became a slightly different wall drawing under each craftsman's hand, the same score becomes a slightly different performance each time. Sway is not a bug here — it is the specification of the language.

The words land in fields of the score. In the second work above, "shoal" landed in `count` and `cluster_count: 7`; "along an undulating path" landed in `path: wave`; "silver" landed in `color_cycle` and `surface.texture: wash`; and the "opposite bank" became the single vertical line at the right edge. **Neither the sniper nor the fisherman nor the war survives — only shape, material, and motion.**

Interpretation and structuring are separated because they demand different abilities: interpretation is associative and creative; structuring is mechanical and rule-abiding. Each stage can be tuned independently, and the LLM used can be selected per stage. In practice the model makes a large difference to the work that comes out. **The choice of model is itself a creative variable.**

Non-determinism lives in exactly two places: the renderer's performance (performance seed) and your explicit operations (another composition, another interpretation). The default path is always deterministic, and history's `render_seed` / `composition_seed` / `render_hash` (work edition ID) let any saved work be reproduced. The specification, though, keeps moving: what a newer inku draws is never quite what an older one drew. As the block is discarded, past Renderers live only in the git history.

**The score itself, the vocabulary of each layer, and how surface and ground texture are handled are in [how it works](docs/guide/how-it-works.md).**

---

## Screens — the back-and-forth of writing and choosing

The description sits on the left, the work on the right, and the **instructions (normalized DDL)** in between, ink-shaded to show how each written word was read. History runs along the bottom.

<table><tr><td><img src="docs/assets/ui/describe-and-paint-dark.en.png" width="900" alt="The description input on the left with word-highlighted instructions (normalized DDL) beneath it, a large canvas on the right showing pale overlapping squares on a cream ground, and a strip of history thumbnails along the bottom"></td></tr></table>

The instructions can be edited by hand and drawn again. Selecting a word in the Saijiki on the right returns a sample of that stroke and a note on what it does — so you write while looking, rather than after memorizing the vocabulary. Switching to Lineage lays out the generations that grew from that work, and whichever work is displayed becomes the parent of your next refinement.

<table><tr><td><img src="docs/assets/ui/edit-instructions-saijiki-light.en.png" width="900" alt="The instructions editor dialog: numbered instruction lines on the left, and the Saijiki on the right showing a stroke sample and explanation for the selected thick-brush, with vocabulary buttons grouped by forms, touches, angles and colors. Light theme"></td></tr></table>

---

## Pursuing the work through revision

The drawing that comes back from one sentence is not the finished piece. It is the **first generation**. You redraw from it, then redraw from what came back — **the work is made by accumulating generations**.

This is not pulling a lever until something good appears. Redrawing is split across five axes, and **you decide which one moves and which ones hold**. Then **you choose** among what comes back. That loop of variation and choice is what turns output into a work.

None of them breaks default reproducibility; each acts only on your explicit request.

| Operation | What is redrawn | What is kept | Cost |
|---|---|---|---|
| **Another performance** | Line tremor, placement phase | Interpretation and composition | Very fast, no LLM call |
| **Another catalog** | The color assignment | Interpretation, composition, performance | Very fast, no LLM call |
| **Another composition** | Composition family, focus, technique | Interpretation (how the words were read) | Medium, Stage 2 |
| **Variation** (let the app change Stage 1.5) | Axes of the expansion layer; the range depends on the strength | Your sentence, its reading, and the axes the strength leaves alone | Moderate, Stage 2 |
| **Another interpretation** | The reading of the words themselves | Your sentence | Slower, from Stage 1 |

With *another interpretation*, the old and new instructions are shown side by side as a diff. The moment your words are read differently — that gap itself becomes material for the next sentence. You can also hand the act of accumulating generations to the AI; everything born while it runs is still recorded in the lineage.

**A piece is finished not when a generation happens to land, but when you decide to stop here.**

**Variation strengths, AI-driven refinement, and the details of lineage and editions are in [revision](docs/guide/revision.md).**

---

## Core vocabulary (Saijiki)

The reference dictionary is called **Saijiki**（歳時記）— a word borrowed from haiku practice, where it names a book of seasonal words. It is not kept open while you write; it is something you go and consult when you hesitate.

| Category (EN) | Category (JA) | Vocabulary |
|---|---|---|
| forms | かたち | circle, ellipse, triangle, square, line, arc, cloudform |
| touches | てざわり | silverpoint, pencil, pen, rotring, crayon, chalk, fine-brush, thick-brush, burin, drypoint, computer |
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

---

## Design principles

1. Descriptions are human-readable, between natural language and code
2. Sway is a feature, not a bug
3. Emotional vocabulary is excluded; physical and motion vocabulary is embraced
4. No fixed canvas — coordinates are ratios from 0.0 to 1.0, scalable to any medium
5. Output is still — the viewer moves, not the image
6. Input is a constrained DSL, not free-form natural language
7. The engine does not go backwards — like a woodblock being carved, the drawing engine only moves in one direction

For the public English specification, see [SPEC.md](SPEC.md). The canonical Japanese source is [SPEC.ja.md](SPEC.ja.md).

---

## The engine as a woodblock

inku's drawing engine has **no past versions**. There is the current fifteenth generation and nothing else; the fourteenth cannot be selected. Its code is not kept either.

This is a choice, not an omission.

> The carving advances. The block only changes in one direction. The prints that came off it remain, but the block cannot be returned to what it was before the cut.
> **If the application itself is thought of as a work, this is the implementation that follows.**

A saved work is **a print**. The SVG itself persists, so the piece as it was can always be seen. The engine is **the block**, and only its carved-forward state exists. Redrawing pulls a fresh print from the current engine, and that is a new edition. Both are never warehoused at once.

The block cannot be restored, but the prints can be kept. Each time a generation rises, the actual output from a fixed set of inputs is frozen (`server/reference/`, currently 350 cases). **Which generation changed what is recorded in the [render engine history](docs/spec/render-engine-history.md).**

---

## Capabilities

- **Multi-stage pipeline** — Stage 1 / 1.5 / 2 / Renderer, with per-stage model selection; non-deterministic AI layers and deterministic algorithmic layers alternate
- **Primitives and arrangement** — line, circle, ellipse, arc, square, triangle, cloudform; horizontal, vertical, radial, scatter, and literal tiling grid layouts with paths such as waves and diagonal bands
- **Regions and relations** — scores can state relations between elements ("along the previous line," "not touching the previous shape") that the performance resolves
- **Material rendering** — pencil, rotring, crayon, chalk, brushes, burin, and drypoint, differentiated through the shared stroke engine's width, tracking, and sparse events plus tool-specific edges
- **Plugins** — namespaced vocabulary macros such as `Nature.wind`; they expand into core vocabulary only and cannot modify the core
- **History and editions** — per-user DB-backed history with stars, search, thumbnails, and exact reproduction via seeds and edition IDs
- **Batch / CLI** — `inku-cli` supports login, painting, batch generation, contact sheets, and diversity analysis

---

## Status

- **Web version** — operational (Python FastAPI + SvelteKit; runs locally or on a server)
- **CLI** — implemented as an independent `cli/` project; drives the API for login, drawing, batch generation, and benchmark output
- **Android app** — `2.1.2-android.1`; its drawing implements the same render engine 15 as the server, in Kotlin

The author maintains the **Japanese** and **English** versions of inku. Other language implementations are welcomed from the community as open-source contributions. The internal JSON Score layer is language-neutral (English keys), so only the surface description layer needs translation.

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
- [CHANGELOG.md](CHANGELOG.md) / [CHANGELOG.ja.md](CHANGELOG.ja.md) — release notes (earlier versions live in [`docs/history/`](docs/history/))
- [SETUP.md](SETUP.md) — installation and operation guide

---

## License

MIT License. See [LICENSE](LICENSE).

---

## Other Languages

- [日本語 README](README.ja.md)
