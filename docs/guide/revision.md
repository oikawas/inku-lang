# Revision, in detail

This continues "Pursuing the work through revision" in [README.md](../../README.md). The strength
settings of **variation**, the two ways of handing the work to the AI, and the handling of lineage
and editions are collected here.

## Variation strength

*Variation* is the one where you say how far to go, in three steps. After it runs, the axes that actually moved are listed, so you never have to guess what changed.

| Strength | Axes that move | Axes that hold |
|---|---|---|
| Small | One among type swap and count | Focus, color, composition |
| Medium | The small axes plus touch, focus, main and contrast color (one or two) | Composition family, type family |
| Large | The medium axes plus composition family and type family (two to four) | — the structure of the picture moves too |

## Letting the AI carry it

Instead of picking the axis yourself, you can hand the act of accumulating generations to the AI. There are two modes.

- **Random automatic refinement** — each generation picks an axis at random from the ones you allowed
- **AI Vision automatic refinement** — each image is actually observed, and one direction is passed to the next generation

Either mode accepts a direction of your own (a sentence such as "festive, and yet cool"). Everything born while the AI runs is still recorded in the lineage, so you can pick a drawing from the middle of the run and go back to redrawing it by hand.

## Accumulating generations

Candidates can be made one at a time or as a grid of four. Keep the ones you like (multiple selection is allowed) and **attach a short note about why you chose them**. **Choosing is part of the work, alongside writing.**

<table><tr><td><img src="../assets/ui/lineage-dark.en.png" width="900" alt="The lineage tab: two arrows descend from the first-generation work card to two second-generation candidates, while the description and instructions remain on the left"></td></tr></table>

What you keep becomes the next parent. Another performance from there, another catalog, a variation — the whole back and forth is recorded in the **lineage**, so you can trace later which generation you redrew what from to arrive at the drawing in front of you. History stores seeds and an edition ID, so any generation along the way can be reproduced exactly as it was.
