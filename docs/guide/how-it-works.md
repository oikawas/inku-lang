# How it works, in detail

This continues "How it works — score and performance" in [README.md](../../README.md). The score
itself, the vocabulary of each layer, the whole pipeline, surface and ground texture, and plugin
vocabulary are collected here.

## Vocabulary and layers

| Term | Layer / act |
|---|---|
| **Description** | The poem-like input the author writes. The top layer of the work (inku-specific; no LeWitt counterpart) |
| **Interpret** | Stage 1's act of reading the description into an underdrawing (LLM) |
| **Underdrawing** | The design of the picture that interpretation returns: which shape, in which material and color, placed where and how, filled into fixed fields using only Saijiki words. It is transient; what the work keeps are the instructions and the score |
| **Instructions (Normalized DDL)** | The executable specification written out deterministically from the underdrawing. Corresponds to LeWitt's instruction sheet. The author can also write and edit them by hand |
| **Score (JSON Score)** | The intermediate form the Typed Compiler writes out from the instructions. Stored deterministically |
| **Performance (SVG)** | The one-time result of playing the score |
| **Headnote** | The description raised beside the finished work — kotobagaki, the note set beside a poem |
| **Reading** | Rebuilding candidates by re-reading the words (another interpretation) |

## One work, followed through the layers

Take the second piece in the README gallery, the silver of the shoal. It was drawn on Build 667, when Stage 1 wrote the instructions directly and an LLM in Stage 2 built the score. Today the instructions are written out from an underdrawing, and the Typed Compiler builds the score; what each layer holds is the same. The description was this sentence:

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

Structuring writes those instructions down as a score (JSON Score). This is the excerpt actually stored at the time (Score 0.1.0) — the second of three instructions, the shoal itself, with `null` fields omitted.

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

"Shoal" landed in `count` and `cluster_count: 7`; "along an undulating path" landed in `path: wave`; "silver" landed in `color_cycle` and `surface.texture: wash`. The "opposite bank" became the single vertical line at the right edge. The renderer performs this score — slightly differently each time. Because the output is vector, it holds up framed on paper, stretched across a wall, or viewed on a phone. There is no physical size constraint. Today's scores (0.10 and later) do not write out the placement of each repeated element one by one; they keep a recipe that performs the same placement again.

## The pipeline as a whole

From description to SVG, the layers run in this order. Only the layers marked use an LLM; everything else is deterministic.

| Layer | What it does | LLM |
|---|---|---|
| Sketch from life (optional) | Adds notes on the breadth of the place and the light of the season and hour to the description, without rewriting it | ● |
| Automatic color catalog selection (optional) | Chooses a color catalog that suits the description | ● |
| Stage 1 interpretation | Reads the description into an underdrawing | ● |
| Printing | Writes the underdrawing out as instructions (normalized DDL) | |
| Typed Compiler | Turns the instructions into verified meaning; plugin words expand into core vocabulary here | |
| Stage 2 completion (only when needed) | Proposes a completion for a phrase that cannot be read through, and waits for the author's approval | ● |
| Stage 1.5 focus and variation | Chooses the focus for elements placed at the center from six fixed candidates, and moves it only for an explicit variation | |
| Scoring | Checks the resource limits and makes the score (JSON Score) | |
| Renderer performance | Draws the score as SVG according to the seed, resolving sway, regions, and relations | |

A failed Sketch from life or color catalog selection never stops the drawing. Painting from instructions you write yourself starts at the Typed Compiler. These decisions live in the shared Rust core, which the server and the Android app both use. The path of each decision is in [description to SVG](../architecture/description-to-svg.md).

## Surface and ground texture

Scores may also carry surface and ground texture. The quality of a shape's surface (the Saijiki's "surfaces": flat, pale ink wash, stipple, hatch, crosshatch, aquatint, and more) goes into `instruction.surface`; a support such as washi, charcoal ground, canvas, or mezzotint (the Saijiki's "grounds") goes into `canvas.ground`. In the instructions, a surface quality is written as a modifier of the shape, as in "a pale-ink-wash circle," and a ground as a sentence of its own, such as "Washi." Those fields stay abstract. The renderer decides whether to perform them as SVG filters, clipped vector marks, or simplified compat output.

## Plugin vocabulary

Outside the core live namespaced **plugin words** such as `Nature.YoungLeaves` (in Japanese, its alias `Nature.若葉`). A plugin is a validated `.inku-plugin.md` document, not code: it names a phenomenon and expands deterministically to core DDL. It cannot add shapes, Score fields, or executable code. A saved work keeps the definitions it used, with their versions and digests, so updating or removing a plugin still draws the same picture. When a description names one of its words, the underdrawing can choose it. Instructions that use an unregistered plugin draw everything else and give the reason on that sentence alone (not installed, disabled, misnamed, or a different version). A work can be exported with its plugin definitions (`inku.ddl-export.v1`) and imported elsewhere as new DDL. Settings exposes load/rejection status, Saijiki shows qualified words with notes, and `inku-cli plugin list / validate / reload` provides administration.
