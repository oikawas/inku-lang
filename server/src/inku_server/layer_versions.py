"""Independent versions for deterministic DDL layers and the DDL language."""

# 17 (2026-08-13): a pair leaves the expansion layer as one unit, not as six
# marks. `Arrangement.group_size` says how many consecutive instructions one
# repeated unit spans, and the document plugin now hands the API one prototype
# pair plus `count=N / group_size=2` where it used to hand over every resolved
# pair in full. The public expansion is untouched -- `instructions` still holds
# all six, and the DDL text is byte-identical -- so the change lives entirely in
# the form the render route consumes, which is why `score_instructions` joins
# the frozen part C: a record holding only the public expansion would freeze a
# version whose change it never reaches, the mistake ddl-engine 15 wrote down
# rather than repeat. The ceiling learned the same arithmetic: the whole-work
# budget counts `count * group_size`, and the instruction ceiling stops at a
# span boundary instead of cutting a unit in half. Where no span fits at all it
# dissolves the span rather than the marks -- an earlier reading emptied the
# instruction list, and a work with nothing in it is not a smaller work. The
# limits are settings, so what the ceiling drops at the merge point is recorded
# in the notes the response already carries. `group_size=1` is excluded from
# serialization, so every Score written before this reads and draws exactly as
# it did.
# 16 (2026-08-13): a mark the description called small is small whoever wrote it.
# Stage 2 writes a circle and leaves the radius empty often enough to matter --
# 115 of 2,972 production works carry a mark at coerce's default size -- and
# `_coerce_instruction` then fills it from `PRIMITIVE_SPECS` with 0.15, a number
# that reads not one character of the description. When coerce writes the mark
# itself it does read the clause and answers 0.038, so the same description
# produced marks four times apart depending on which layer wrote them.
# `_with_stated_size` runs on the instruction the model handed over, before the
# defaults erase the difference between a size omitted and a size stated, and
# fills an empty radius or ellipse size from the one clause that names that
# primitive with a size word in it. It borrows both the values and the two
# readers from `_fallback_instruction_from_clause` rather than writing a second
# table, which is the whole claim: the answer cannot drift apart again without
# both paths drifting together. It fills nothing where two clauses fit (the
# description does not say which one the mark answers) and overrules nothing the
# model stated. Both exits run it, the `INKU_COERCE_DISABLE` one included: being
# faithful to a size the description stated is not a matter of style, for the
# same reason the two grid branches already run there. Four cases are new and
# they are the whole of `changed_from_previous` -- no branch name was added to
# the report, so the 26 carried-over cases are byte-identical, unlike engines 11
# and 15.
# 15 (2026-08-12): a shape can say how its surface is. The saijiki gains おもて /
# surfaces -- eleven state nouns for how the inside of a closed shape is, beside
# つらなり, which says the same about a line. The vocabulary grew, so the version
# rises, exactly as it did for yellow, orange, and purple at 3 and 4. The reason
# for the category is that the lower layers had the mechanism and the upper layer
# had no word: a fill was asked for in words in 1.3% of the works holding a
# closed shape, 96.7% of the works that came out filled had never been asked to
# be, and five descriptions that stated a fill outright reached `filled` zero
# times out of five -- because Stage 1 could write 埋める while Stage 2 read 塗る,
# an intersection that was empty in Japanese. The word is the noun 塗り and not
# the verb 塗る (author's ruling, 2026-08-12): principle 5 and the pruning of 描く
# in v1.92 both say a saijiki word names a state, not a hand's action.
# The transform this version moves is one branch, because the vocabulary and the
# two prompt tables are read by an LLM and the frozen corpus calls none. A
# surface attached to a primitive with no interior is moved to the nearest closed
# shape before it, and dropped where there is none or where that shape already
# carries one. Measured on production, 53.4% of every surface written sat on a
# `line` (739) or an `arc` (59) -- `wash` 453, `grain` 251, `bleed` 83,
# `paper_grain` 9, `hatch` 2 -- and the renderer draws none of them: both
# `_has_surface_texture` and the surface group require a closed shape. Stage 2
# attaches a 「面: ...」 sentence to whatever instruction precedes it, and where a
# line came between the sentence and its shape the request was lost whole. The
# repair corrects the attachment and never guesses an interior into being.
# Three cases join the coerce corpus. Not one of the 42 inputs frozen at
# ddl-engine 14 carried a 「面:」 clause -- the two files that hold one are plugin
# output -- so refreezing without them would have recorded a version whose change
# the corpus never traversed, and left T-11 green for having looked at nothing.
# 14 (2026-08-12): every count reader follows the same rules. The language of the
# description decides whether CJK beside an Arabic numeral excludes that numeral;
# a reference phrase that states no count may widen the search to its sentence,
# while a count already stated in the phrase wins; and a bare Arabic numeral in a
# Japanese reference phrase is now a count. The separate English scan and noun
# table were removed, and axis words and member indices are excluded because they
# say which one, not how many. Android adopted the same server semantics. The DDL
# reference corpus grew to 42 cases: two new cases cover widening beyond the phrase
# and a bare numeral inside it, while the English numeral beside CJK case changed
# from one unit to twelve.
# 13 (2026-08-11): a plugin hands over one whole unit, and the count stated in
# the phrase that names it says how many of those units to place. The document
# plugin layer placed the unit once and read nothing, so `Nature.青葉を三つ置く。`
# came back as one leaf group -- the body could ask for a macro, but not for
# three of it. The count is read by one reader now: the twelve definitions coerce
# used moved to `counts.py`, and the expansion layer reads the same words rather
# than a second table of its own. The count belongs to the phrase, not the
# sentence: five of seven production works stating a count beside a reference
# carry another number in the same sentence, and reading by sentence left them
# all at one unit. A count the work has no room for is declined whole rather than
# trimmed -- `N x unit` over the ceiling leaves the single unit standing and
# writes a line into `plugin_warnings` -- because a trimmed number is neither
# what the body asked for nor a number anybody chose. The English side of the
# reader also stops requiring a noun from a 32-word table and reads Arabic
# numerals, which is why `Draw 12 circles.` was invisible to it; numerals inside
# another number (decimals, fractions, ratios, percentages) are not counts, and a
# numeral with CJK beside it stays with the Japanese path. The Japanese path is
# untouched: a bare numeral with no counter is still not read, and whether it
# should be is undecided. Measured on the seven works: three now expand to the
# stated number, where none did. Part C of the DDL reference corpus is new --
# this layer carried a version number from the start and never a frozen output.
# 12 (2026-08-10): the stated number holds past what the eye can count. Engine 11
# stopped the repair at eleven, on the reading that a larger number is density
# rather than a promise. Measured on 1,346 production works that is not what the
# band above it holds: of the counts stated in 12..239 that never reached the
# Score, lifting the band makes 203 of 341 true, and the works whose branch fires
# go from 30 to 198. Thirty circles drawn as two is not a matter of density; it
# is the description not being read. The band is no longer a number of its own --
# it is `literal_count_threshold - 1`, the literal side of the line SPEC already
# draws between drawing a number and showing a group, so the boundary cannot move
# in one place and stay in the other. Above that line nothing changed. What did
# change is that the branch now declines a number it cannot deliver whole: it
# runs after both density budgets and before the hard ceiling at the exit, and
# that ceiling trims, so a forced 233 in a work with room for five came out as
# 200 -- neither the stated number, nor Stage 2's, nor a representative count.
# Two synthetic cases join the coerce corpus, which had no stated count above
# eleven in it and would otherwise have frozen a record of a layer this change
# never traversed.
# 11 (2026-08-10): the number the description states in plain words is the number
# that gets drawn. One branch made a stated count true and it answered only to
# "だけ / のみ / only / just"; a plain 「三つ」 was protected from thinning and
# nothing more, so a count Stage 2 had already missed stayed missed -- measured
# on 1,346 production works, a fifth of the counts in the band a reader can
# count by eye never reached the Score, and in 88.8% of those the group was
# there with the wrong number on it. `with_stated_count_fidelity` pairs a clause
# with the single group carrying its (primitive, color, weight) -- read through
# the same DDL hints the instructions themselves went through, or the material
# word in a neighbouring clause makes a matching group look like a stranger --
# and failing that with the single group carrying its figure. A clause matching
# two groups or none is left alone: a number pushed onto a guess changes the
# count of a group the clause never named. It sits after both budgets and after
# the strict road, so a repaired count is not thinned again and 「だけ」 keeps the
# last word, and it stops at 11, because above the band a number is read as
# density and which of density and the total budget wins there is not ruled on.
# It signs a note of its own so a stored Score still says which branch honoured
# the count. `_primitive_from_clause` also gained the 雲形 / cloudform branch it
# never had -- the one shape word no other test caught, which fell through to
# the `line` default and would have handed a cloud's count to a line.
# 10 (2026-08-10): a description that names one color is drawn in one color. The
# cycle hands `cycle[i % len(cycle)]` to each member, so a two-color cycle gave
# the named color half the group and an unnamed color the other half. Engine 8
# removed the order coerce was writing into the cycle; the cycle itself carrying
# a color the description never named survived that, and is what this removes.
# The rule reads the DDL with its background clauses dropped, fires only when
# exactly one color is named and no "colorful" phrase is present, and only on a
# cycle that carries the named color alongside another -- a cycle without it is
# a delivery failure, which is a different layer's work. The cycle is reduced to
# the one named color rather than emptied: `_apply_color_cycle` rebuilds
# `color_hint` and returns early on an empty cycle, so emptying it also skips
# that rebuild, and a stored Score whose `color_hint` still carries an old
# machine note ("black restored in color_cycle...") then hands the renderer a
# color the description never named -- measured, 58 of 100 cycled instructions
# in the [I-173] sample carry such a note. Both exits run the branch, including
# the `INKU_COERCE_DISABLE` one: that flag turns off style repair, not the ban
# on inventing.
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
DDL_ENGINE_VERSION = "17"
# 4 (2026-07-30): yellow, orange, and purple become abstract Score colors, and
# coerce recognizes the corresponding Japanese and English DDL markers.
# 3 (2026-07-30): 黄 / 橙 / 紫 joined the saijiki color words, so an author can write
# them and Stage 1 offers them. This follows the same rule version 2 followed for the
# thinness word: the language version rises when its vocabulary grows, not when its
# grammar changes. Works saved earlier keep the version they were written under.
DDL_VERSION = "3"
