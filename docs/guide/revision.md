# Revision, in detail

This continues "Pursuing the work through revision" in [README.md](../../README.md). How
**variation** works, the two ways of handing the work to the AI, and the handling of lineage
and editions are collected here.

## Variation

*Variation* moves the focus to a different candidate. The focus is where the elements the instructions place at the center are actually drawn, chosen from six fixed candidates: upper right, upper left, lower right, lower left, upper edge, and right half. It does not move the instructions, the frame of the composition, technique, color, touch, or element count, and it calls no LLM.

The strength (Subtle, Moderate, Sweeping) tells the destinations apart: for the same variation seed, the three strengths each choose a different candidate. It is not a scale on which a larger strength moves further or moves more axes.

*Another composition* also rechooses the focus, and when the description has a slant or a corner it rechooses the concrete angle and the position in the corner as well. Variation keeps the angle and corner that another composition settled.

## Letting the AI carry it

Instead of picking the axis yourself, you can hand the act of accumulating generations to the AI. There are two modes.

- **Random automatic refinement** — each generation picks an axis at random from the ones you allowed
- **AI Vision automatic refinement** — each image is actually observed, and one direction is passed to the next generation

Either mode accepts a direction of your own (a sentence such as "festive, and yet cool"). Everything born while the AI runs is still recorded in the lineage, so you can pick a drawing from the middle of the run and go back to redrawing it by hand.

## Accumulating generations

Candidates can be made one at a time or as a grid of four. Keep the ones you like (multiple selection is allowed) and **attach a short note about why you chose them**. **Choosing is part of the work, alongside writing.**

<table><tr><td><img src="../assets/ui/lineage-dark.en.png" width="900" alt="The lineage tab: two arrows descend from the first-generation work card to two second-generation candidates, while the description and instructions remain on the left"></td></tr></table>

What you keep becomes the next parent. Another performance from there, another catalog, a variation — the whole back and forth is recorded in the **lineage**, so you can trace later which generation you redrew what from to arrive at the drawing in front of you. History stores seeds and an edition ID, so any generation along the way can be reproduced exactly as it was.
