# How it works, in detail

This continues "How it works — score and performance" in [README.md](../../README.md). The score
itself, the vocabulary of each layer, the whole pipeline, surface and ground texture, and plugin
vocabulary are collected here.

## Vocabulary and layers

| Term | Layer / act |
|---|---|
| **Description** | The poem-like input the author writes. The top layer of the work (inku-specific; no LeWitt counterpart) |
| **Interpret** | Stage 1's act of reading the description into instructions |
| **Instructions (Normalized DDL)** | The executable specification the interpretation produces. Corresponds to LeWitt's instruction sheet |
| **Score (JSON Score)** | The structured intermediate form of the instructions. Stored deterministically |
| **Performance (SVG)** | The one-time result of playing the score |
| **Headnote** | The description raised beside the finished work — kotobagaki, the note set beside a poem |
| **Reading** | Rebuilding candidates by re-reading the words (another interpretation) |

## One work, followed through the layers

Take the second piece in the README gallery, the silver of the shoal. The description was this sentence:

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

## The pipeline as a whole

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

## Surface and ground texture

Scores may also carry surface and ground texture. A circle can say it is filled with wash or stipple through `instruction.surface`; the canvas can say it is off-white paper, washi, or ink-wash ground through `canvas.ground`. Those fields stay abstract. The renderer decides whether to perform them as SVG filters, clipped vector marks, or simplified compat output.

## Plugin vocabulary

Outside the core live namespaced **plugin words** such as `Nature.wind`. A plugin is a validated `.inku-plugin.md` document, not code: it names a phenomenon and expands deterministically to core DDL. It cannot add shapes, Score fields, or executable code, and removing it does not change saved replay or rh2. Settings exposes load/rejection status, Saijiki shows qualified words with notes, and `inku-cli plugin list / validate / reload` provides administration.
