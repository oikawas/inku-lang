"""Independent versions for deterministic DDL layers and the DDL language."""

# 9 (2026-08-09): coerce becomes a fixed point for a color it delivers. The
# promotion to a primary stroke ran before the repair that puts a color in a
# cycle, and it can only promote what a cycle already carries -- so a color the
# DDL asked for and this layer delivered could not be promoted until a second
# pass over the same DDL. Running the same input through coerce twice gave two
# different scores. The two now run repair-then-promote. Engine 8 made this
# visible rather than causing it: at engine 7 the six-word table dropped yellow
# before it could reach either stage, so only the older colors could show it.
# 8 (2026-08-09): the color cycle stops inventing an order. The cycle hands one
# color to each member in turn, so it has no head and no ranking, yet coerce was
# writing two kinds of order into it. It inserted the instruction's own color
# without looking, so a color already in the cycle took twice the members -- a
# weighting nobody asked for whose size depended on how long the cycle happened
# to be. And `_color_repair_order` ran the requested colors through a six-word
# table that predates yellow, orange, and purple, so a work naming an old color
# and a new one lost the new one entirely. The table is now a known order for
# determinism rather than a ranking, and colors it does not name follow it
# instead of falling out.
# 7 (2026-08-05): the staffage level was folded away. Stage 1.5 no longer appends
# candidate sentences of its own and coerce no longer runs the six branches that
# invented an instruction -- a visual event, a composition anchor, context energy,
# a motion floor, a surface tension mark, a focal-event reaction. Both layers now
# behave the way `tenkei=none` behaved, which is what 62% of the previous corpus
# moved to. The six cases that existed only to separate the three levels became
# copies of one another and were replaced.
# 6 (2026-08-04): coerce receives the DDL alone. The description used to be
# concatenated in front of it, so `_source_context` read the first line to get the
# description back and `_looks_like_generated_background_plan` judged that line's
# provenance. With no description left to judge, the guard only misfired on the
# ordinary shape of a DDL and was removed, and the context is now read whole.
# Three cases freeze the production input shape the corpus never carried.
# 5 (2026-08-03): `thinness` moved to sit immediately before `surface`, giving the
# last declaration slot back to `surface`. The deterministic layers behave exactly
# as before -- this is the declaration-order condition, the one the frozen corpora
# cannot catch, so ddl-engine-5 is byte-identical to ddl-engine-4 by design.
DDL_ENGINE_VERSION = "9"
# 4 (2026-07-30): yellow, orange, and purple become abstract Score colors, and
# coerce recognizes the corresponding Japanese and English DDL markers.
# 3 (2026-07-30): 黄 / 橙 / 紫 joined the saijiki color words, so an author can write
# them and Stage 1 offers them. This follows the same rule version 2 followed for the
# thinness word: the language version rises when its vocabulary grows, not when its
# grammar changes. Works saved earlier keep the version they were written under.
DDL_VERSION = "3"
