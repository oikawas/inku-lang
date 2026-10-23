# DDL grammar and Saijiki reference

DDL (Drawing Description Language) writes forms, tools, positions, and their relationships as sentences. This chapter explains how to assemble those sentences and which spellings the compiler accepts, for authors writing directly and for AI producing DDL. [Japanese is canonical](../ja/ddl-reference.md); this English adaptation describes the same meanings through English grammar.

The subject here is **visible DDL**. Interpreting a free description and compiling DDL are separate stages. A description may say “like dusk,” but that phrase does not thereby become a DDL modifier. Direct DDL must express its meaning with accepted words and finite constructions.

Meaning follows [SPEC.md](../../SPEC.md), vocabulary follows the shared core's [Saijiki asset](../../core/crates/inku-ddl/assets/saijiki-v2.json), and numeric and phrase attachment follows the [parser](../../core/crates/inku-ddl/src/parser.rs) and [shared grammar](../../core/crates/inku-pipeline/src/prompts.rs). The reference source is `97b50a52367554a94e9f364b90dc538d0f6b68bc`. “Accepted” below describes that source's grammar and implementation boundaries. Executed counts also depend on resource limits, and actual colors depend on the work's color conditions.

## 1. Grammar principles

### 1.1 Say what to place and how

The ordinary English standalone form is:

```text
<action> [quantity] [modifiers] <shape> [line-up direction] [position] [relation].
```

Square brackets indicate optional parts and do not belong in the DDL. In `place one red circle at center`, `place` is the action, `one` the count, `red` a modifier, `circle` the drawing head, and `at center` the position. Secure a head and an action first. A color, tool, width, or surface alone is not a drawing subject.

Japanese usually puts the action last:

```text
[位置句] [修飾句] 図形を [配置方向] [数量句] 動作。
```

### 1.2 Attach each modifier to its shape

English places attributes before the drawing head: `red pen solid empty circle`. A modifier phrase excludes the head itself. Numeric dimensions and numeric rotation also have dedicated post-head constructions.

Japanese joins noun modifiers with `の` and uses accepted adjective forms for adjectives.

| Role | Japanese modifier phrase | Following head |
|---|---|---|
| Color, tool, continuity, surface | `赤いペンの実線の空の` | `円` |
| Color, tool, surface | `青いクレヨンの塗りの` | `四角` |
| Sway, color, width | `細かく揺れる黒い細い` | `線` |

Japanese accepts color adjectives `赤い`, `青い`, `白い`, and `黒い`. Colors also attach as nouns, including `灰の`, `黄の`, `橙の`, `紫の`, and `緑の`. Use the listed surface forms rather than inventing compound vocabulary.

### 1.3 A word list does not permit every combination

Words have roles. `semicircle` specifies an arc form; it is not an independent drawing head. `brushmarks` describes a closed face and cannot texture a line. Start, end, and partway select a target location in the connection grammar.

DDL does not guess unknown synonyms or ambiguous ownership. Expressions such as “beautifully,” “nestling,” or “randomly” do not become direct-DDL attributes merely because a free description can contain them. State the intended color, form, position, sway, or finite relation instead.

### 1.4 Distinguish omission from an explicit normal value

An explicit `normal-sized` and an omitted size are different inputs. Unwritten tools, colors, surfaces, and positions likewise remain unspecified in source meaning. The parser does not insert pen or black into the author's sentences.

Performance resolves supported omissions through shared rules. An omitted tool resolves to pen, omitted continuity to solid, and an omitted surface on a closed shape to a flat fill. An omitted color compares the actual work background with the work's black and white, chooses the larger lightness distance, and chooses black on a tie. Charcoal ground and mezzotint use the color the ground shows over the background. Omission therefore does not mean “always black.”

### 1.5 Sentence order has meaning

Independent commands retain source order. “The previous shape” refers backward, and a sequence begins again at the start of each placement. Reordering sentences can change references, drawing order, and composition seeds.

A uniquely resolved marked subject, such as `the circle red.`, instead continues an existing subject. It differs from introducing another circle. See §3.3.

### 1.6 Separate core words from registered names

Core forms, colors, grounds, and grammar require no plugin. A name such as `Nature.若葉` requires a registered definition or a definition carried by the work or DDL export. Knowing the name does not make it available. Standard examples in this chapter use core DDL without plugins.

## 2. Start with simple examples

These forms follow existing successful shared-core examples. Enter an English block as English DDL or a Japanese block as Japanese DDL. Explanations and code fences are not part of the input.

### 2.1 Place one circle

```ddl-en
place one red circle at center.
```

```ddl-ja
赤い円を中心に置く。
```

The Japanese sentence omits count, which resolves to one for place. Named center is a central region. For exactly `(0.5, 0.5)`, use a numeric position.

### 2.2 Specify size and position numerically

```ddl-en
place one red circle radius 0.1 at horizontal 0.5, vertical 0.5.
```

```ddl-ja
画面の横0.5、縦0.5の位置に、半径0.1の赤い円を1個置く。
```

Horizontal and vertical position are fractions of canvas width and height respectively. Radius is a fraction of the canvas's short side.

### 2.3 Specify line width

```ddl-en
draw three thin black lines.
```

```ddl-ja
細い三本の黒い線を引く。
```

This draws three thin black lines. Width and tool identity are separate attributes.

### 2.4 Alternate red and gray

```ddl-en
Line up five circles, alternating red and gray.
```

```ddl-ja
赤と灰を交互にして、円を五つ並べる。
```

Five is the total count: red, gray, red, gray, red. It does not mean five of each color.

### 2.5 Fill a circle with points

```ddl-en
fill a circle diameter 0.5 at the bottom with 3 red points.
```

```ddl-ja
下に、直径0.5の円を三つの赤い点で埋める。
```

The circle is the target region and the points are its contents. Three points are placed and clipped to the circle. This differs from giving the circle a red flat fill.

## 3. Grammar reference

### 3.1 Language, case, and punctuation

DDL has two resolved languages, `ja` and `en`. If the host requests `auto`, Japanese script takes priority; otherwise ASCII letters select English. If neither occurs, a valid language fallback applies, with Japanese as the final default. This selects a language for the document, rather than allowing arbitrary mixing of both vocabularies in one sentence.

English core words and grammar are ASCII case-insensitive. `Place` and `place`, or `THE BACKGROUND WITH` and `the background with`, have the same grammar. Plugin names have separate identity rules and do not inherit that behavior.

`。`, `.`, and line breaks delimit clauses. `!`, `?`, and their full-width counterparts also close sentences. Decimal points and dots inside recognized qualified plugin names remain inside their tokens. Commas, Japanese commas, and middle dots aid reading; they do not freely alter ownership or references.

Keep each command on one line. Close separate commands with a sentence terminator before a line break. Parentheses do not introduce command blocks or nested programs. Numeric-range annotations and noun-phrase groups have their own constructions.

### 3.2 Standalone shapes, modifiers, and counts

A reliable Japanese skeleton is:

```text
<位置>に、<修飾句><図形>を<数量句><動作>。
<修飾句><図形>を<位置>に<動作>。
```

Accepted ownership can also place a position after its shape. Color, tool, continuity, shape angle, surface, handling, fineness, underlayer, sway, proportion, relative size, width, regularity, and sides must each have a clear owner.

Japanese accepts both `円を四つ置く` and `四つの円を置く`. Prenominal modifiers may appear before or after a complete count phrase.

```ddl-ja
大きな四つの赤い円を置く。
```

This has the same ownership as `四つの大きな赤い円を置く。`, `赤い大きな四つの円を置く。`, and `大きな赤い円を四つ置く。` Do not add a second counter to a count phrase that already contains one.

Modifiers can also stand before a numeric dimension:

```ddl-ja
赤い太筆の長さ0.6の線を1本引く。
```

It means the same as `長さ0.6の赤い太筆の線を1本引く。` A modifier does not travel past another drawing head: `赤い円の長さ0.6の線` is not a standard way to say “red line.”

### 3.3 Subject continuation

```ddl-en
place a circle at center. the circle red.
```

```ddl-ja
円を中心に置く。円は赤い。
```

The second sentence makes the first circle red instead of introducing another circle. Japanese reintroduces a canonical head with `は` or `が`; English uses the corresponding definite noun-phrase topology. The predicate supplies accepted attributes or an action.

Continuation requires exactly one candidate and a clear clause boundary and predicate owner.

| Situation | Result |
|---|---|
| A continued line has no prior line | Missing target |
| Two independent lines precede a continued line | Ambiguous target |
| An unread clause prevents a clear continuation boundary | Boundary diagnostic |
| A predicate conflicts with an established field | Conflict diagnostic |
| Definite continuation and new coordinated subjects share an ambiguous scope | Ownership diagnostic |

The compiler does not select the nearest or last matching head. With several similar subjects, keep attributes in their introducing commands. Explicit previous-object relations are separate from subject continuation.

### 3.4 Counts

| Form | Examples and limits |
|---|---|
| ASCII integer | `1`, `12`, `233`; Japanese `1個`, `12本` |
| Full-width integer in Japanese | `９つ` |
| Japanese kanji | `三本`, `十個`, `二百三十三本` |
| Japanese native counts | `ひとつ`, `ふたつ`, `みっつ`, `よっつ`, `いつつ`, `むっつ`, `ななつ`, `やっつ`, `ここのつ`, `とお` |
| Japanese counters | `本`, `個`, `枚`, and `つ` for one through nine |
| English number words | Finite cardinal forms through 999, including `one` through `nineteen`, `twenty-one`, and `one hundred and five` |

Do not write Japanese `10つ` or `11つ`. Ten may be `10`, `十`, `とお`, `10個`, or `十個`. Spelling does not alter the exact count. Negative numbers, decimals, and fractions are not counts. An explicit zero receives a diagnostic instead of becoming a successful zero-mark command.

`a few`, `several`, `many`, `numerous`, and `countless`, and Japanese `少し`, `数個`, `いくつか`, `たくさん`, `多数`, and `無数`, are recognized as qualitative quantity candidates. They do not supply an exact direct-DDL count. Use an integer when specifying how many marks to draw.

| Structure | Omitted-count resolution |
|---|---|
| Standalone place or draw | One |
| Standalone line-up, scatter, or tile | Eight |
| Coordinated place or line-up | One for each omitted member |
| Coordinated scatter or tile | Preserve explicit counts; distribute the remainder up to eight among omitted members, equally, with source-order remainders and at least one per omitted member |
| Fill | Resolve from target area and reference mark size, rather than a fixed eight |
| A plugin word accepting count | Follow that definition's declaration |

The original DDL and meaning retain a requested count that exceeds resources. A standalone primitive can execute a safe source-order prefix and report requested and executed counts. A group or plugin whose structure cannot be partly executed may instead lose its outer placement as one unit. This is not a language rule for silently replacing large counts with representative counts.

### 3.5 Forms and finite shape modifiers

Ordinary drawing heads are circle, ellipse, triangle, square, line, arc, free line, point, and cloudform. Direct DDL also accepts the hidden finite `polygon` head. Declared parser spellings such as `rectangle`, 三角形, 四角形, and 長方形 appear in the vocabulary tables below.

| Construction | Meaning and boundary |
|---|---|
| `regular` / 正形 | A finite regularity constraint on triangle, square, or polygon |
| `equilateral triangle` / 正三角形 | A regular triangle; use side length for numeric dimensions |
| `regular square` / 正方形, 正四角形 | A regular square; unequal explicit width and height are invalid |
| `pentagon` through `octagon` / 五角形 through 八角形 | Regular polygons with five through eight sides |
| `polygon` with `sides 5` / 辺数5の多角形 | Current side counts are five through eight; omitted sides resolve to five |
| `tall` / 縦長, 縦に長い, 細長い | Tall triangle, square, ellipse, or cloudform |
| `wide` / 横長, 横に長い | Wide variants of the same four forms |

Without numeric dimensions, tall and wide have a 2:1 long-to-short ratio. With explicit width and height, those values remain and their ordering is checked. A tall form whose width is at least its height is invalid, as is combining aspect with regularity. Tall circle does not silently change primitive identity to ellipse.

A free line has two ends like a line; performance decides the path between them. DDL does not provide arbitrary control points or an SVG path. The same conditions and seed reproduce its path. Use arc for a defined circular arc.

### 3.6 Line width and relative size

| English | Japanese |
|---|---|
| extra-fine | ごく細い |
| thin | 細い |
| thick | 太い |
| extra-thick | ごく太い |

Width is separate from tool identity. `thick-brush` names a tool; `thick` modifies its mark. `faint` controls handling rather than making a line thin.

Relative size is finite core grammar, rather than a Saijiki category. Its factor applies to normal geometry independently of count.

| English | Accepted Japanese forms | Factor |
|---|---|---|
| very small | とても小さな, とても小さい | 3/8 |
| small | 小さな, 小さい | 1/2 |
| slightly small | 小さめ | 3/4 |
| normal-sized | 普通の大きさ | 1 |
| slightly large | 大きめ | 5/4 |
| large | 大きな, 大きい | 3/2 |
| very large | とても大きな, とても大きい | 7/4 |
| extra-large | 特大の | 2 |
| huge | 巨大な | 8/3 |

The factor changes line/free-line length, ordinary arc chord and sagitta together, and point diameter. Increasing count does not automatically shrink individual shapes. Fitting does not authorize inferred changes to count or dimensions.

**Multiple size specifications:** Numeric dimensions, relative sizes, and full/half width remain independent candidates. The current implementation reports `ConflictingSizeSpecifications` and draws at the smallest reference extent while preserving aspect. It does not multiply `small` into an explicit radius. Use one size specification to state one unambiguous intention.

### 3.7 Numeric dimensions

Dimensions use the canvas's short side as one unit. On a 1,000-pixel short side, radius 0.1 is equivalent to 100 pixels. The paper (canvas format) and output resolution are host choices. A DDL declares only the ratio it was laid out in, with `Aspect ratio W:H.` ([3.27](#327-aspect-ratio-declare-the-ratio-the-ddl-was-laid-out-in)).

| Owner | English | Japanese |
|---|---|---|
| Circle, point | `radius N`, `diameter N` | 半径N, 直径N |
| Ellipse, cloudform | `width W, height H` | 幅W、高さH |
| Square, ordinary triangle | `width W, height H` | 幅W、高さH |
| Square, equilateral triangle | `side length N` | 一辺N |
| Polygon | `radius N`, `diameter N` of its circumcircle | 半径N, 直径N |
| Line, free line | `length N` | 長さN |
| Ordinary arc | `chord C, sagitta S` | 弦長C、矢高S |

English may place dimensions after the head, as in `circle radius 0.1`. Japanese attaches them before it: `半径0.1の円`. Paired dimensions require both members; width alone, height alone, or chord alone is incomplete.

Arc sagitta is the bulge from its chord midpoint, positive and no larger than half the chord. A circle radius does not implicitly supply an arc chord.

Use positive integer or decimal dimensions without `px`, `mm`, `%`, or exponent notation. Decimal meaning is exact base ten until the final numeric drawing boundary, while original spelling remains provenance. Fractions such as `1/3` in numeric ranges do not extend the general dimension grammar.

| Form | Normal dimensions, short side = 1 |
|---|---|
| Circle, square, ordinary triangle, polygon | Diameter, side, or reference width 6/25 = 0.24 |
| Ellipse, cloudform | Width 0.24, height 0.144; aspect 5:3 |
| Line | Length 0.24 |
| Free line | Length 11/20 = 0.55 |
| Arc | Chord 0.24, sagitta 0.06 |
| Point | Diameter 3/250 = 0.012 |

### 3.8 Named positions, numeric points, and numeric ranges

| Authority | Construction | Meaning |
|---|---|---|
| Named position | `at center`, `at top`, `at left-edge` | A defined region |
| Numeric point | `at horizontal X, vertical Y` | An exact anchor |
| Numeric range | `in the range horizontal a to b, vertical c to d` | A distribution or fill region |

X runs left 0 to right 1; Y runs top 0 to bottom 1. Write both axes. Japanese uses `画面の横X、縦Yの位置に`. Position measures each canvas axis separately, unlike short-side dimensions.

| Name | Horizontal range | Vertical range |
|---|---|---|
| top / 上 | 0–1 | 0–1/3 |
| bottom / 下 | 0–1 | 2/3–1 |
| center / 中心 | 1/3–2/3 | 1/3–2/3 |
| left-edge / 左端 | 0–1/10 | 0–1 |
| right-edge / 右端 | 9/10–1 | 0–1 |
| top-edge / 上端 | 0–1 | 0–1/10 |
| bottom-edge / 下端 | 0–1 | 9/10–1 |
| corner / 隅 | One corner, with each edge one fifth long | Composition seed selects the corner |

For a placed shape, performance chooses inside the named range shrunk to two thirds about its center. Named center is not fixed at `(0.5,0.5)`. Omitted place/draw position likewise uses the shrunken center cell, `7/18–11/18` on both axes. Omitted position for line-up or scatter with at least two marks, and for tile, uses the whole canvas. A one-mark line-up or scatter is treated as place and uses the same shrunken center cell when position is omitted.

An exact numeric anchor must be in 0–1, and the rotated declared geometry must fit the canvas. It is not silently shrunk or moved. Named and range placement preserve size and may allow contours to cross the canvas edge.

For a numeric range, each start must be below its end, and all bounds must lie in 0–1. Decimals allow at most six digits after the decimal point; fraction denominators must be 1–1,000,000. Two-point coordinates have the same precision limits.

```ddl-en
fill small red circles at the bottom (horizontal 0 to 1, vertical 2/3 to 1).
```

```ddl-ja
下（横0〜1、縦2/3〜1）に、赤い小さな円を埋める。
```

Place wording absent from the named vocabulary, such as “bottom right,” may be retained immediately before a parenthesized range. Those words are preserved as an annotation; **the numeric bounds determine placement**. This does not add arbitrary natural-language position interpretation. If the annotation includes an accepted position word, keep the numeric range within that word's region.

Do not give one object separate numeric, range, and named position authorities. A numeric clause whose owner cannot be uniquely determined among several shapes receives a diagnostic.

### 3.9 Two points: row ends and line ends

```ddl-en
Line up 5 blue rotring empty circles radius 0.03 from horizontal 0.118, vertical 0.5 to horizontal 0.882, vertical 0.5.
```

```ddl-ja
画面の横0.118、縦0.5から横0.882、縦0.5まで、半径0.03の青のロットリングの空の円を5個並べる。
```

The first and last mark centers land on those two points, with equal steps between them. Points may run right to left, bottom to top, or diagonally. The first written point owns the first occurrence.

Two points may also specify the ends of one line or free line:

```ddl-en
draw one gray pencil line from horizontal 0.118, vertical 0.118 to horizontal 0.882, vertical 0.882.
```

```ddl-ja
画面の横0.118、縦0.118から横0.882、縦0.882まで、灰の鉛筆の線を1本引く。
```

Points must differ and all four coordinates must lie in 0–1. As in 3.8, decimals allow at most six fractional digits and fraction denominators must be 1–1,000,000. This is not the construction for an arc, a one-mark row, scatter, tile, or fill. A two-point line already has length and direction: do not add length, full width, or angle. A two-point row already has its direction: do not add another row direction. Appending two points to a group or plugin call does not provide a general endpoint operation.

### 3.10 Shape angle and row direction

Shape angle precedes the head; line-up direction follows it. English distinguishes adjectives and adverbs, while Japanese places the two specifications on opposite sides of the head.

```ddl-en
arrange three horizontal lines vertically at center.
```

```ddl-ja
中心に、横線を縦に三本並べる。
```

These are three horizontal lines in a vertical row. Japanese 横 and 縦 also occur as numeric axes, so keep numeric axis clauses distinct from shape modifiers.

Angles include horizontal, vertical, diagonal, rising, falling, and rotated. Direct DDL additionally recognizes hidden left-rising and left-falling; ordinary vocabulary display and interpretation projections omit them. Qualitative angle words make finite seed-based choices. Use a numeric angle for exact degrees.

```ddl-en
Place one red square side length 0.1 rotated 30 degrees at horizontal 0.5, vertical 0.5.
```

```ddl-ja
画面の横0.5、縦0.5の位置に、一辺0.1の回転30度の赤い四角を1個置く。
```

Numeric rotation is clockwise on the canvas, `0 <= angle < 360`, with up to six decimal places. Japanese also accepts full-width digits. English uses `1 degree` and otherwise `degrees`. Fractions, negative angles, and values of 360 or more are invalid. Bare `rotated` still selects a seeded angle. A numeric angle plus another angle word conflicts. A point does not accept an angle.

Omitted row direction is normally horizontal left to right, becoming vertical for a named or numeric region that is taller than it is wide. A multi-mark row over a range follows the segment cut across the canvas by a line through the range center in the row's direction; marks occupy equal cell centers. A narrow range therefore does not fix the first and last marks at its edges. Use §3.9 for explicit row endpoints.

### 3.11 Actions

| Action | Meaning |
|---|---|
| place / 置く | Place at one location; multiple marks form a bounded bundle around it |
| draw / 引く | Draw a line, arc, or free line, rather than a general command for every primitive |
| line-up, line up, arrange / 並べる | Place in one row, optionally with explicit row direction |
| scatter / 散らす | Distribute over an area, distinct from a grid or fill |
| tile / 敷き詰める | Arrange on a grid according to the area's aspect |
| fill / 埋める | Place marks inside a region and clip them to its contour |

Japanese 描く is retired as a DDL action. 塗る is not a surface construction: use the noun 塗り in a phrase such as `塗りの円`.

Line-up, scatter, and tile retain explicit counts and per-mark dimensions. Crowding or overlap does not authorize silently reducing either. A tile preserves its grid rather than inheriting scatter-specific fading or clustering.

### 3.12 Fill target and contents

```text
fill <one target shape> with <marks>.
fill <marks> at <named area>.
<領域を表す形>を<痕の名詞句>で埋める。
<名前付き領域>を<痕の名詞句>で埋める。
<痕の名詞句>で埋める。
```

An omitted fill target is the whole canvas. In “fill a circle with red points,” the circle is the region and points are the contents. The target does not automatically receive an independent outline or flat fill.

A shape target must be one accepted closed contour with area. A line or point has no target area. Multiple circles as one target and a numeric point as the region are invalid. The target shape itself may have a numeric or named position.

Explicit contents count and size are preserved. Omitted count uses shared rules based on target area divided by reference mark extent squared, rounded up. Empty versus flat surface, tool, or handling does not change that count. Filling a large area with tiny points can require substantial resources.

Filling the background with a color is the separate background-color construction in §3.21. Filling it with red points instead puts marks over the canvas; it does not change its background color to red.

### 3.13 Coordination, groups, and sequences

Coordinate subjects with `and` or Japanese と, attaching each subject's modifiers to that subject.

```ddl-ja
赤い円と青い四角を中心に並べて置く。
```

A coordinated place with no internal layout aligns member centers as an overlap. Japanese 重ねて置く makes overlap explicit; 並べて置く arranges a group horizontally in source order. Each member retains its own count.

A **group** is a noun phrase that can serve as one repeated unit:

```text
a group of <shape A> and <shape B>
<図形A>と<図形B>の組
```

Do not define it with parenthesized commands. Internal primitive count and outer occurrence count remain separate.

**Alternation takes exactly two entries.**

```ddl-ja
鉛筆と太筆を交互にして、線を五本並べる。
```

A field sequence can alternate colors or tools from one attribute category. Do not mix different categories as if a color and a tool were two equivalent entries. Listing multiple colors or tools without order does not imply alternation.

**An ordered finite sequence** must be nonempty. Order and duplicate entries are preserved.

```ddl-en
Line up eight, repeating a small red circle, a small blue line, and a small gray arc in order.
```

```ddl-ja
赤い小さな円・青い小さな線・灰の小さな弧の順に繰り返して、八つ並べる。
```

The eight units are circle, line, arc, circle, line, arc, circle, line. The same sequence structure applies to line-up, scatter, tile, and fill. List length does not multiply the total count.

```ddl-en
Line up five, alternating a group of a red circle and a blue line with a gray arc.
```

```ddl-ja
赤い円と青い線の組を、灰の弧と交互に5つ並べる。
```

This has three circle-and-line groups and two arcs: five outer units, containing three circles, three lines, and two arcs. Group and plugin internals also contribute to resource demand.

### 3.14 Color shift and fading

Repeating a color sequence cycles it; shifting through it assigns it once along the placement.

```ddl-en
Line up 9 small circles in the range horizontal 0.1 to 0.9, vertical 0.45 to 0.55, shifting through yellow, orange, and red in order.
```

```ddl-ja
画面の横0.1〜0.9、縦0.45〜0.55の範囲に、黄・橙・赤の順に段々に移して、小さな円を9個並べる。
```

The result is three yellow, three orange, and three red marks. This is a finite color assignment, not continuous color interpolation. Ten marks would be four yellow, three orange, and three red. Shift supports line-up and tile, with at least as many marks as colors. It does not support scatter or shifting a sequence of shapes.

Five fading constructions are accepted:

| English | Japanese | Supported placement |
|---|---|---|
| fading from left to right | 左から右へ薄れさせて | A row of at least two with a horizontal component |
| fading from right to left | 右から左へ薄れさせて | The same |
| fading from top to bottom | 上から下へ薄れさせて | A row of at least two with a vertical component |
| fading from bottom to top | 下から上へ薄れさせて | The same |
| fading outward from the center | 中心から外へ薄れさせて | A row or scatter of at least two |

English appends `, fading …` to the command. Japanese puts `…薄れさせて、` before placement. Positions stay fixed while marks fade from the named end. A left-to-right fade on a vertical row is off-axis and invalid. Tile, one mark, and directional fading on scatter are unsupported. Do not combine two fades on one command.

Handling `faint` still sets each mark's base intensity and may accompany a fade across several marks.

### 3.15 Relations to earlier subjects

Use the **complete fixed literals** below. Recognition of a short relation word alone does not establish a drawable reference.

| Relation | English fixed phrase | Japanese fixed phrase |
|---|---|---|
| Along | along the previous line | 前の線に沿って |
| Not touching | not touching the previous shape | 前の形に触れない |
| Touching | touching the previous line | 前の線に触れる |
| Touching an arc at both ends | touching the previous arc at both ends | 前の弧に両端で触れる |
| Cutting | cutting the previous line | 前の線を切る |
| Between | between the previous two | 前の二つの間に |
| Connected | connected to the previous shape | 前の形につながる |
| Resting on | resting on the previous shape | 前の形に載る |
| Inside | inside the previous shape | 前の形の中に |
| Overlapping | overlapping the previous shape | 前の形に重なる |
| Crossing | crossing the previous shape | 前の形を横切る |
| Mirrored | mirrored with the previous shape | 前の形と鏡写し |

References follow source order; between alone uses two prior subjects. DDL does not add arbitrary IDs or forward references. If a referenced subject is omitted, the relation is not silently rebound to a different earlier subject.

English can append the complete relation phrase to the same command. Japanese may attach it as a modifier or retain it as a following clause within that command.

```ddl-en
Place a diagonal red arc at left-edge. Place a blue arc at right-edge, mirrored with the previous shape.
```

```ddl-ja
左端に斜めの赤い弧を置く。右端に前の形と鏡写しの青い弧を置く。
```

Relations also constrain primitive combinations. Inside needs a closed target area and enough room. Touching matches endpoints of supported lines and arcs rather than saying arbitrary proximity. Explicit dimensions, direction, and numeric position are not freely changed to satisfy a relation. An unsuccessful relation is diagnosed and removed on its own, retaining the shape at its original placement.

Cutting makes a visual interruption; crossing places the mark across the target from one edge past the other. Overlapping is a relation to an earlier subject, while a coordinated group's overlapping layout describes its own internal placement.

### 3.16 Connecting to a start, end, or interior

Connected to the previous shape aligns the current canonical start with the previous end. Closed targets are limited to circle, ellipse, square, triangle, and polygon; these use a nearby contour point. Cloudform and crescent cannot be connection targets. For a prior line or arc, target-side location may be explicit:

```text
connected to the start of the previous line
connected to the end of the previous arc
connected partway along the previous line
connected partway along the previous arc

[前の]線の始点につながる
[前の]線の終点につながる
[前の]弧の始点につながる
[前の]弧の終点につながる
前の線の途中につながる
前の弧の途中につながる
```

The current side stays its canonical start. Adding wording such as 終点を引く does not provide a general self-endpoint selector. An unrotated ordinary line or arc starts on the left and ends on the right; rotation and mirroring preserve those endpoint identities.

Partway excludes both ends and is not fixed at the center. Performance chooses the interior point on the actual swayed centerline and carries outer transforms with it. Do not write Score fields such as `target_path_position` into ordinary DDL. Partway does not align tangents or correct dimensions.

A current free line supports endpoint-connected and touching relationships. A complete touching phrase names a prior line or ordinary arc; ordinary DDL has no touching phrase naming a prior free line. To refer to a prior free line in ordinary DDL, use connected to the previous shape for its end. Connections to a free line's interior, along, not touching, cutting, between, resting on, inside, overlapping, crossing, and mirrored are diagnosed and removed as relations.

### 3.17 Tools, continuity, surfaces, and handling

Tools are independent modifiers, such as `pencil` and `thick-brush`, or Japanese 鉛筆の and 太筆の. Omitted tool resolves to pen during execution; a texture or bleeding word does not silently make thick-brush explicit.

Continuity is solid, dashed, dotted, or dash-dot. It describes the continuity of a mark's line, separately from a surface. English `solid` is continuity, while `flat` names the filled surface.

Surfaces are empty, flat, sweep, brushmarks, grain, stipple, hatch, crosshatch, and aquatint. On a closed form, a named texture supplies the face itself, without a silently added flat base. Underpainted explicitly adds the tool's fill below it.

| Combination | Current behavior |
|---|---|
| Closed form with empty | Unfilled |
| Closed form with flat or omitted surface | Filled |
| Closed form with named texture | Texture belongs to that face |
| Line, ordinary arc, or free line with sweep | A band three times the tool width (thick and extra-thick: three default widths plus what the thinness word adds), at 0.8 times its opacity |
| Line, ordinary arc, or free line with grain | Increased ground tooth for that mark |
| Line, ordinary arc, or free line with stipple, hatch, crosshatch, or aquatint | Accepted and retained in Score, but the current renderer paints no open-mark texture face; it does not transfer the texture to another shape |
| Line, ordinary arc, or free line with brushmarks | `unsupported_surface_brushmarks`; only the word is omitted |
| Point with an explicit surface | Unsupported surface diagnostic; omit that field |
| Crescent arc with flat | A filled crescent face |
| Crescent arc with another surface | Unsupported combination diagnostic |

Stipple is a surface technique; point is a drawing head. Placing many points differs from giving a circle a stipple face. Do not use the retired Japanese 点 spelling for stipple.

Handling is dense, temperate, or faint: 濃い, 程よい, 薄い. It controls intensity relative to each tool. Temperate means the tool's native intensity and performs like omitted handling. Multiple intensity words on one mark conflict.

### 3.18 Fineness and underpainting

| English | Japanese | Meaning |
|---|---|---|
| fine-grained | 細かい | Smaller texture marks |
| coarse-grained | 粗い | Larger texture marks |
| packed | 密な | Closer texture marks |
| sparse | 疎な | More widely spaced texture marks |
| underpainted | 下塗り | The tool's fill beneath the texture |

```ddl-ja
中心に、赤の太筆の下塗りの密な交差線の薄い四角を1個置く。
```

These apply to the seven named textures of closed forms: sweep, brushmarks, grain, stipple, hatch, crosshatch, and aquatint. They do not apply to line, arc, free line, point, empty, flat, or an omitted surface. Invalid combinations retain the mark and omit the modifier with `unsupported_surface_fineness` or `unsupported_surface_underlayer`.

Choose one of the four fineness words per mark and optionally one underlayer word. Fine-grained plus packed occupies the same fineness field twice; both are diagnosed and omitted. This is not an independent arbitrary size-and-density parameter syntax. External fineness or underpainting does not override marks emitted by a plugin.

Japanese 細かい is fineness, while 細かく is sway amplitude. 大きな is shape size, while 大きく is sway amplitude.

### 3.19 Sway and bleeding

| Dimension | English | Japanese |
|---|---|---|
| Amplitude | narrowly, broadly | 細かく, 大きく |
| Frequency | loosely, tightly | ゆるやかに, 小刻みに |
| Quality | swaying, undulating | 揺れる, 波打つ |
| Ink spread | bleeding | にじみ |

Attach sway before a drawing head or in a uniquely resolved subject continuation. Swaying makes irregular motion; undulating makes a wave-like path.

Amplitude alone does not make a sway. Without swaying or undulating, narrowly and broadly are omitted with `fluctuation_amplitude_without_quality`. The existing behavior for a frequency word alone is separate.

Bleeding is independent of sway quality and can combine with it. Bleeding alone does not add irregular path motion. A point does not support explicit path sway. Tool-specific mark character and ground response remain separate from explicit sway.

Do not use retired words such as finely, slowly, trembling, blurring, ゆっくり, 震える, or 滲む in current DDL. Migrating older stored text to current words does not make the old spellings accepted in new DDL.

### 3.20 Full width, half width, and arc forms

Full-width and half-width size a form to the canvas width or half of it before rotation. Unlike relative size, they do not start from the normal 0.24-short-side geometry. Aspect is preserved; for line and free line the extent is length, and for an ordinary arc it is chord. They do not restore the rotated horizontal silhouette to a canvas-wide extent.

Arc-form words modify an arc head:

```text
semicircle arc / 半円の弧
waxing arc / 上弦の弧
waning arc / 下弦の弧
crescent arc / 三日月の弧
```

Semicircle is an upper open 180-degree arc; waxing and waning give right- and left-side open arcs. Waxing/waning add their quarter-turn offsets, and numeric rotation may add to those. Explicit chord and sagitta for a semicircle form must have sagitta equal to half the chord.

A crescent has a specific closed face between two curves, unlike an ordinary open arc. Tall, wide, regularity, and arbitrary chord/sagitta do not transfer to a crescent. Explicit width and height must match its defined aspect.

### 3.21 Ground and background color

Write a ground noun as its own sentence.

```ddl-en
washi.
```

```ddl-ja
和紙。
```

The seven grounds are paper, washi, ink wash ground, charcoal ground, canvas, drawing paper, and mezzotint. Ground belongs to the canvas, not a shape's surface. Do not use `Ground: washi`, `Surface: stipple`, 地: 和紙, or 面: 点描 as DDL headings. Ground alone is drawable content.

Background color has a fixed form:

```text
fill the background with <color>.
背景を<色>で埋める。
```

Ground and background color may coexist. Background alone is drawing context rather than a shape; if omissions leave nothing but a background, the result does not count as a successful surviving drawing. Filling the canvas with points or circles instead uses §3.12.

Write one of the nine abstract colors and let the work's color catalog resolve it. Arbitrary hex or RGB expressions are not color-name syntax. Catalog ID, catalog mode, canvas format (the paper), output size, and seeds are host settings rather than visible DDL grammar. The ratio a DDL was laid out in is declared with `Aspect ratio W:H.` ([3.27](#327-aspect-ratio-declare-the-ratio-the-ddl-was-laid-out-in)).

### 3.22 Plugin invocation

A plugin is a data-only macro naming a composition of core meanings. It adds neither a primitive nor unrestricted plugin-specific natural grammar.

```text
Namespace.Heading
Namespace.宣言済み別名
```

Use an ASCII dot between namespace and heading. Only the formal heading and declared aliases in that namespace resolve. For an environment declaring `Nature.YoungLeaves` and `Nature.若葉` as the formal name and alias of one definition, either names that definition. This does **not** make Nature a fixed plugin available everywhere.

Check the exact registered name and its public parameter types and bounds, and normally make a call one sentence. Versions, digests, locks, definition bodies, and transcribed output are not author-written DDL metadata. Do not invent function syntax such as `Name(count=3)`.

Parameters bind uniquely to compatible recognized facts in the same clause. A fixture definition declaring one integer can bind these forms:

```text
Bind.Integer with 8
Bind.Integerを八つ置く
```

They require that explanatory `Bind.Integer` definition; they are not core examples for an ordinary installation. Parameter names imply no meaning. Two same-type parameters with two possible assignments are ambiguous. A number in another sentence cannot supply a missing parameter.

Declared parameters are required except for the special word-count declaration whose definition controls omitted count. Undeclared external colors, tools, angles, sizes, and positions do not become general whole-output overrides. Do not delete an unbindable explicit specification merely to make the call succeed.

As a group or sequence member, a macro retains its internal counts, positions, and transforms while taking one outer placement slot. Keep outer count distinct from internal primitive demand.

| Diagnostic | Meaning |
|---|---|
| plugin_not_installed | No matching definition |
| plugin_disabled | Installed but disabled |
| plugin_name_mismatch | Name, alias, namespace, or case differs from registration |
| plugin_version_mismatch | Same name, different pinned definition content |
| plugin_count_out_of_range | Count outside that word's range |

An unresolved plugin clause is omitted with its reason while other drawing continues. An LLM does not silently substitute another form. Saved works retain the definitions they used. Plain visible-text copying does not carry those definitions across environments; use DDL export when needed. Exported definitions can serve new works without installing them into the host catalog. See [PLUGIN.md](../../PLUGIN.md) for definition authoring.

### 3.23 Unspecified values, conflicts, and local recovery

Recognizing a word, assigning its meaning to an owner, and performing it are separate stages. A listed attribute still needs its subject. A valid placement or relation can also exceed resources.

| Common issue | Resolution |
|---|---|
| Unknown adjective or action | Express the meaning with accepted Saijiki words and finite modifiers |
| Two unordered colors on one shape | Choose one color or explicitly state alternation/order |
| Several size specifications | Inspect recovery to the smaller extent and retain the intended size alone |
| Numeric and named position together | Choose one position authority |
| A continued line after two independent lines | Move attributes into the introducing commands |
| Fineness on an empty surface | Choose a supported texture or remove fineness |
| Brushmarks on a line | Use a closed face or another accepted surface |
| Numeric point as a fill region | Specify an area or target shape |
| Missing or incompatible relation target | Check sentence order, target form, and complete literal |

Recoverable problems are diagnosed at the smallest field, relation, command, group, or macro unit that preserves independent drawing. Omitting one relation differs from omitting its entire outer placement. If every drawable target is omitted, or source, lock, or ownership integrity fails, the result stops.

AI writing DDL must not conceal these diagnostics. Removing requested subjects, counts, dimensions, colors, tools, or relationships merely to obtain formal acceptance does not preserve the author's specifications.

### 3.24 Before finishing

1. Does every drawing subject have an accepted head and action?
2. Does each attribute, count, and position have one clear owner?
3. Are shape angle and row direction in their separate grammatical positions?
4. Does the intention need an exact point, a range, or two endpoints?
5. Is each count one complete expression, without multiplying sequence or group internals?
6. Does each relation use a complete literal and have its required prior targets?
7. Can that form accept its surface, fineness, underlayer, and sway?
8. Do plugin names and parameters exist in the current environment?
9. Is explanatory prose, Score data, configuration, or metadata absent from the DDL?

### 3.25 Sources for implementation comparison

These are sources for the accepted boundaries above, rather than a list of language extensions.

| Subject | Source and existing examples |
|---|---|
| Language, finite spellings, numbers, shape constraints | [language.rs](../../core/crates/inku-ddl/src/language.rs), [parser.rs](../../core/crates/inku-ddl/src/parser.rs), [shape_constraint.rs](../../core/crates/inku-ddl/src/shape_constraint.rs) |
| Shared grammar and standalone skeleton | [prompts.rs](../../core/crates/inku-pipeline/src/prompts.rs) |
| Clauses, continuation, ownership | [clause.rs](../../core/crates/inku-ddl/src/clause.rs), [semantic_document.rs](../../core/crates/inku-ddl/src/semantic_document.rs), [continuation examples](../../core/crates/inku-ddl/tests/semantic_document.rs) |
| Modifiers before counts and dimensions | [pre_count_modifiers.rs](../../core/crates/inku-ddl/tests/pre_count_modifiers.rs), [pre_size_modifiers.rs](../../core/crates/inku-ddl/tests/pre_size_modifiers.rs) |
| Normal sizes, regions, omission, size recovery | [geometry.rs](../../core/crates/inku-ddl/src/geometry.rs), [score_lowering.rs](../../core/crates/inku-ddl/src/score_lowering.rs) |
| Numeric range, segment, rotation | [numeric_range.rs](../../core/crates/inku-ddl/src/numeric_range.rs), [numeric_segment.rs](../../core/crates/inku-ddl/tests/numeric_segment.rs), [numeric_angle.rs](../../core/crates/inku-ddl/tests/numeric_angle.rs) |
| Rows over regions | [line_up_chord.rs](../../core/crates/inku-ddl/tests/line_up_chord.rs) |
| Sequences, groups, color shift, fading | [ordinary_member_sequence.rs](../../core/crates/inku-ddl/tests/ordinary_member_sequence.rs), [fade_and_shift.rs](../../core/crates/inku-ddl/tests/fade_and_shift.rs) |
| Fill | [fill_region.rs](../../core/crates/inku-ddl/tests/fill_region.rs), [fill_numeric_range.rs](../../core/crates/inku-ddl/tests/fill_numeric_range.rs) |
| Surfaces, fineness, underpainting, bleeding | [brushmarks.rs](../../core/crates/inku-ddl/tests/brushmarks.rs), [texture_words.rs](../../core/crates/inku-ddl/tests/texture_words.rs), [endpoint_spread.rs](../../core/crates/inku-ddl/tests/endpoint_spread.rs) |
| Plugin binding | [macro_parameter_binding.rs](../../core/crates/inku-ddl/src/macro_parameter_binding.rs), [parameter fixtures](../../core/crates/inku-ddl/tests/fixtures/macro-parameter-binding-v1.json) |

### 3.26 Enter DDL through the CLI

Save only the DDL text as UTF-8 in `example.ddl` and use the CLI's existing connection settings.

```sh
inku-cli paint --file example.ddl --input-mode ddl \
  --stage1-model chatgpt:gpt-6-luna --instruction-lang ja \
  --no-save-artifacts -o ./out
```

Use `--instruction-lang en` for English text. `--input-mode ddl` skips free-description interpretation and sends visible DDL to the shared compiler. Complete accepted DDL needs no LLM call, so naming a model with `--stage1-model` does not prove that the model was called. Distinguish this from a path that actually needs an LLM, such as a proposed completion for unread wording.

`--no-save-artifacts` suppresses the server's derivative-file saving; `-o ./out` selects the CLI's output location. A library history entry is saved only when `--save-history` is supplied. See the [CLI reference](cli-reference.md) for connection, authentication, output, and saving details.

### 3.27 Aspect ratio: declare the ratio the DDL was laid out in

A DDL declares the paper ratio it was laid out in with a sentence of its own (DDL 26).

```ddl-en
Aspect ratio 16:9.
place one red circle radius 0.1 at horizontal 0.5, vertical 0.5.
```

```ddl-ja
画面比16:9。
画面の横0.5、縦0.5の位置に、半径0.1の赤い円を1個置く。
```

- The terms are integers from 1 to 10,000, width first. Japanese also accepts full-width digits and `：`. `Aspect ratio 32:18.` declares the same ratio as `16:9`. A sentence with a decimal, a zero or any other word is not a declaration.
- The declaration makes no instruction and is not counted among the sentences. Adding or removing it changes how no other sentence is read, and on a paper of the same ratio it changes no drawing.
- Only the first declaration is read. A later one is left out as an unread sentence, with its diagnostic.
- The app writes the paper's ratio first into a new DDL (one drawn from a description and one newly written). A declaration the author wrote is kept, and an edit or a redraw adds none.
- The declaration does not bind the paper. Drawn on a paper of another ratio, the app asks whether to fit it in or to draw it to the paper. Fitted, the composition keeps its ratio in a frame in the middle of the paper, and the ground and background fill the margins. Marks reaching out of the frame are drawn to the paper's edges.
- A format name (`square` and the like) is not written; the ratio is written in numbers. Golden is `809:500`, and A4 and B4 are `500:707`.

## 4. Saijiki: complete vocabulary and accepted spellings

Japanese is canonical. Spellings follow `inku.saijiki.v2` in `core/crates/inku-ddl/assets/saijiki-v2.json`. This section covers all 102 rows in its 15 categories and all 11 rows in the separate relations table. The 102 include 98 displayed rows, three hidden rows accepted in direct DDL, and one retired row that is not accepted. The interface shows relations as the sixteenth category.

### Reading and writing the words

The Japanese and English columns give the canonical spellings of the same word. Use the spelling for the instructions' language. Spaces and hyphens belong to the English word: `free line`, `oil paint`, `fine-brush`, and `left-edge`. The examples show short ways to use a word; they do not fix the appearance of a work. Omitted positions and sizes follow the resolution rules below and the performance.

Use a form as the head noun, attach attributes to it, and join it to an action. For example: `赤の鉛筆の薄い点描の円を置く。` A ground is a separate sentence, such as `和紙。` / `Washi.`, rather than an attribute of a form. Do not use headings such as `地: 和紙` or `面: 点描`. Write a surface as a modifier: `点描の円を置く。` / `Place a stipple circle.`

Several words for the same attribute on one mark can conflict. Fine-grained and packed occupy the same fineness field, so do not specify both. Underpainted occupies a separate field and can be combined with packed: `下塗りの密な点描の円` / `an underpainted packed stipple circle`. An invalid attribute or relation is omitted with a diagnostic while independently drawable content continues. Recognition of a word, acceptance into the Score, and a visible effect on that form are separate facts.

The `default=true` flags on pen, solid, empty, and black annotate the reference data. `（既定）` and `(default)` are not part of a DDL word. An unwritten attribute remains unspecified during reading; do not insert the table's annotations into the instructions. Current Score resolution uses pen for an omitted tool, solid for omitted continuity, and a flat fill for an omitted surface on a closed form. It chooses an omitted color from black and white by lightness contrast with the actual background or ground. The empty row's annotation therefore does not mean an omitted surface becomes empty.

### Categories

| Key | Japanese | English | Asset rows | Status |
|---|---|---|---:|---|
| `katachi` | かたち | forms | 10 | Nine public, one hidden accepted word |
| `katamuki` | かたむき | angles | 8 | Six public, two hidden accepted words |
| `tezawari` | てざわり | touches | 12 | Public |
| `tsuranari` | つらなり | continuity | 4 | Public |
| `omote` | おもて | surfaces | 9 | Public |
| `sabaki` | さばき | handling | 3 | Public |
| `kime` | きめ | fineness | 4 | Public |
| `shitaji` | したじ | underlayer | 1 | Public |
| `ji` | じ | grounds | 7 | Public |
| `iro` | いろ | colors | 9 | Public |
| `yuragi` | ゆらぎ | movements | 7 | Public |
| `basho` | ばしょ | places | 11 | Public; endpoint words belong in relation phrases |
| `ugoki` | うごき | motions | 7 | Six public, one retired |
| `jun` | じゅん | order | 2 | Public |
| `wariai` | わりあい | proportions | 8 | Public |
| `gamen` | がめん | aspect | 0 | Displays the aspect ratio declaration (3.27); not a Saijiki word |
| `aida` | あいだ | relations | 11 | Displayed from the separate `relations` table |

### 4.1. Forms — かたち

These are form nouns. A closed form below means circle, ellipse, triangle, square, cloudform, or polygon. An open mark means line, arc, or free line. Point and the crescent form of an arc have their own restrictions.

| Japanese | English | Meaning and acceptance | Short usage |
|---|---|---|---|
| 円 | `circle` | A true circle; a closed form. Accepts a radius or diameter. | `赤い円を置く。` / `Place a red circle.` |
| 楕円 | `ellipse` | A circle stretched along an axis; a closed form. Accepts tall, wide, width, and height. | `横長の楕円を置く。` / `Place a wide ellipse.` |
| 三角 | `triangle` | A closed form with three vertices. Accepts tall, wide, width, and height. An equilateral triangle uses the separate shape constraint grammar. | `上に三角を置く。` / `Place a triangle at top.` |
| 四角 | `square` | A closed rectangle. Accepts tall and wide. Its canonical English word is square; a rectangle is not a separate primitive. | `横長の四角を置く。` / `Place a wide square.` |
| 線 | `line` | A straight line from its start to its end. Accepts draw, place, and the distribution actions. | `水平の線を引く。` / `Draw a horizontal line.` |
| 弧 | `arc` | A circular arc, normally open. Semicircle, waxing, waning, and crescent modify this noun. | `半円の弧を引く。` / `Draw a semicircle arc.` |
| 自由線 | `free line` | A path between its ends, assembled for each performance from straight parts, arcs, and free bends. Accepts only connected and touching relations. | `右上がりの自由線を引く。` / `Draw a rising free line.` |
| 点 | `point` | A small, round, filled mark with its own identity, separate from circle. Accepts no surface, mark angle, or sway. Bleeding is allowed. | `緑の点を置く。` / `Place a green point.` |
| 雲形 | `cloudform` | A closed irregular form whose contour is decided for each performance. Accepts tall and wide. | `横長の雲形を置く。` / `Place a wide cloudform.` |
| 多角形 | `polygon` | **Hidden accepted word.** `prompt=false`, `display=false`, `marker=true`. Valid in direct DDL. Currently accepts five to eight sides, with five when omitted. | `多角形を置く。` / `Place a polygon.` |

Direct DDL also reads 三角形 as 三角, 四角形 and 長方形 as 四角, `rectangle` as `square`, and `lines` as `line`. These are parser spellings of the same rows. Registered English form nouns also accept regular plurals, such as `circles` and `free lines`; a plural alone does not establish a count.

正三角形, 正方形, 正四角形, and 五角形 through 八角形 (`equilateral triangle`, `regular square`, and `pentagon` through `octagon`) belong to a finite grammar that adds regularity or a side count to a form identity. They are not additional Saijiki rows. Do not combine a regular form with tall or wide.

### 4.2. Angles — かたむき

An angle turns the mark itself. A point has no direction and cannot take an angle. The mark's direction and the row's direction can be separate: `水平の線を縦に並べる。` describes horizontal lines in a vertical row. The angles below are clockwise in canvas coordinates, with y increasing downward.

| Japanese | English | Meaning and acceptance | Short usage |
|---|---|---|---|
| 水平 | `horizontal` | 0 degrees. Also available as a row direction. | `水平の線を引く。` / `Draw a horizontal line.` |
| 垂直 | `vertical` | 90 degrees. Also available as a row direction. A tall form is turned a further 90 degrees. | `垂直の線を引く。` / `Draw a vertical line.` |
| 斜め | `diagonal` | Selects 45, 135, 225, or 315 degrees using the composition seed. For a row, selects one of two diagonal directions. | `斜めの四角を置く。` / `Place a diagonal square.` |
| 右上がり | `rising` | From lower left toward upper right; selects an integer from −37 through −23 degrees. Also a row direction in direct DDL. | `右上がりの線を引く。` / `Draw a rising line.` |
| 右下がり | `falling` | From upper left toward lower right; selects an integer from 23 through 37 degrees. Also a row direction in direct DDL. | `右下がりの線を引く。` / `Draw a falling line.` |
| 左上がり | `left-rising` | **Hidden accepted word.** Points from lower right toward upper left at 203–217 degrees. Retains an identity distinct from rising. | `左上がりの線を引く。` / `Draw a left-rising line.` |
| 左下がり | `left-falling` | **Hidden accepted word.** Points from upper right toward lower left at 143–157 degrees. Retains an identity distinct from falling. | `左下がりの線を引く。` / `Draw a left-falling line.` |
| 回転 | `rotated` | Selects an integer angle more than five degrees from each 45-degree boundary. Not a row direction. | `回転の四角を置く。` / `Place a rotated square.` |

Left-rising and left-falling both have `prompt=false`, `display=false`, and `marker=true`; direct DDL and Macro references accept them. 横 for horizontal and 縦 for vertical are parser spellings. English also accepts `horizontally`, `vertically`, and `diagonally` as grammatical forms of their rows. This does not allow arbitrary adverbs or synonyms for rotated.

`回転30度の四角` / `a square rotated 30 degrees` uses the separate numeric angle grammar. Keep it distinct from rotated without a number, and do not assign both an angle word and a numeric angle to one mark.

### 4.3. Touches — てざわり

Touches describe the tool's trace, rather than line width itself. All ten primitives accept them. The physical explanations below are prose about the words; the whole explanation is not DDL vocabulary. Specify width with separate finite modifiers such as 細い / `thin` and 太い / `thick`.

| Japanese | English | Meaning | Short usage |
|---|---|---|---|
| 銀筆 | `silverpoint` | A fine line trace with almost no sway. | `銀筆の線を引く。` / `Draw a silverpoint line.` |
| 鉛筆 | `pencil` | A continuously swaying trace with faint secondary lines and fine grain. | `鉛筆の線を引く。` / `Draw a pencil line.` |
| ペン | `pen` | A trace with slight ink variation. Carries the reference's default annotation. | `ペンの線を引く。` / `Draw a pen line.` |
| ロットリング | `rotring` | A hard drafting line with uniform width and square ends. | `ロットリングの線を引く。` / `Draw a rotring line.` |
| クレヨン | `crayon` | Wax rubbing with short breaks and granular gaps. | `クレヨンの線を引く。` / `Draw a crayon line.` |
| チョーク | `chalk` | Powdery scratchiness, fine gaps, and light blur. | `チョークの線を引く。` / `Draw a chalk line.` |
| 細筆 | `fine-brush` | A brush trace with ink-density changes and secondary lines. | `細筆の線を引く。` / `Draw a fine-brush line.` |
| 太筆 | `thick-brush` | Brush pressure, rubbed secondary traces, and light blur. | `太筆の線を引く。` / `Draw a thick-brush line.` |
| 油彩 | `oil paint` | Loaded paint traces with bristle ridges and overlapping strokes. | `油彩の線を引く。` / `Draw an oil paint line.` |
| ビュラン | `burin` | A hard engraved line with round ends. | `ビュランの線を引く。` / `Draw a burin line.` |
| ドライポイント | `drypoint` | Soft burr fuzz, bleeding, and scratchiness. | `ドライポイントの線を引く。` / `Draw a drypoint line.` |
| コンピュータ | `computer` | Line sway that repeats exactly at the same period. | `コンピュータの線を引く。` / `Draw a computer line.` |

### 4.4. Continuity — つらなり

Continuity describes a line or contour's breaks. Every primitive accepts these words, but a point remains one point; adding continuity does not turn it into a dotted row or supply a count. Stipple is a separate surface attribute.

| Japanese | English | Meaning | Short usage |
|---|---|---|---|
| 実線 | `solid` | An unbroken line. Carries the reference's default annotation. | `実線の線を引く。` / `Draw a solid line.` |
| 破線 | `dashed` | Short segments separated by gaps. | `破線の線を引く。` / `Draw a dashed line.` |
| 点線 | `dotted` | A contour made of a run of dots. | `点線の円を置く。` / `Place a dotted circle.` |
| 一点鎖線 | `dash-dot` | Alternating long dashes and dots. | `一点鎖線の線を引く。` / `Draw a dash-dot line.` |

`solid` is a continuity word. The English surface word for 塗り is `flat`; do not use the internal Score value `solid` as the surface word in the instructions.

### 4.5. Surfaces — おもて

Surfaces are state nouns describing a closed face or a trace. Handling describes opacity, fineness describes the texture's unit size and spacing, and grounds describe the canvas ground.

| Japanese | English | Meaning | Short usage |
|---|---|---|---|
| 空 | `empty` | Leaves the face untouched and retains the contour. Carries the reference's default annotation. | `空の四角を置く。` / `Place an empty square.` |
| 塗り | `flat` | Fills the face evenly. | `塗りの四角を置く。` / `Place a flat square.` |
| 刷き | `sweep` | Sweeps the face twice at slightly different angles, merging each pass's bands into one film. On an open mark, makes a broad band. | `刷きの四角を置く。` / `Place a sweep square.` |
| 刷毛目 | `brushmarks` | Lays bands one by one, leaving darker ridges where they overlap. Only on a closed form's face. | `刷毛目の四角を置く。` / `Place a brushmarks square.` |
| 粒 | `grain` | Fine grain and a scuffed roughness. On an open mark, increases the ground's tooth. | `粒の四角を置く。` / `Place a grain square.` |
| 点描 | `stipple` | Dots scattered across a face to build tone. Separate from the point form. | `点描の円を置く。` / `Place a stipple circle.` |
| 平行線 | `hatch` | Parallel lines filling a face; not a request for several line primitives. | `平行線の四角を置く。` / `Place a hatch square.` |
| 交差線 | `crosshatch` | A second set of lines crossing the first. | `交差線の四角を置く。` / `Place a crosshatch square.` |
| アクアチント | `aquatint` | Grain divided into tone steps, normally three. | `アクアチントの四角を置く。` / `Place an aquatint square.` |

| Target | Acceptance and performance restrictions |
|---|---|
| Circle, ellipse, triangle, square, polygon, cloudform | Accept all nine words and perform the face. The seven named textures, alone, do not add a flat fill underneath. |
| Line, ordinary arc, free line | Sweep and grain affect the trace. The compiler also accepts empty, flat, stipple, hatch, crosshatch, and aquatint into the Score, but an open mark has no closed face on which to perform these textures. They are not transferred to another closed form. Brushmarks is omitted with a diagnostic. |
| A point mark | Accepts none of the nine surface words. The point remains a round filled mark. |
| A crescent arc | Accepts only flat as an explicit surface. Empty and the seven textures are not accepted. |

Sweep has no faintness of its own. Add faint handling for `薄い刷き` / `faint sweep`. An open mark's sweep is a band three times the tool width at 0.8 of the tool opacity. A thick or extra-thick band adds to three default widths only what the thinness word adds to a round mark (for example, an extra-thick thick-brush sweep is 66 per 1000 of the short side, not 150). On a face, sweep makes two films at 0.6 opacity per pass; brushmarks layers each band at 0.5. The tool and handling also affect the result.

`塗りの弧` / `a flat arc` can also express the fill inside a closed contour made by two touching arcs. Adding flat to an ordinary arc or line alone does not invent another closed form.

### 4.6. Handling — さばき

Handling sets opacity relative to the tool; it does not change the number of dots or lines. Lines, arcs, free lines, closed faces, and points accept it. Do not put several handling words on one mark.

| Japanese | English | Meaning | Short usage |
|---|---|---|---|
| 濃い | `dense` | Lays the tool more densely than its own opacity. | `鉛筆の濃い点描の四角を置く。` / `Place a dense stipple pencil square.` |
| 程よい | `temperate` | Uses the tool's own opacity, as when handling is omitted, while retaining an explicit source word. | `鉛筆の程よい点描の四角を置く。` / `Place a temperate stipple pencil square.` |
| 薄い | `faint` | Lays the tool more faintly than its own opacity. | `鉛筆の薄い点描の四角を置く。` / `Place a faint stipple pencil square.` |

### 4.7. Fineness — きめ

Use fineness only on the seven named textures of the six closed forms: sweep, brushmarks, grain, stipple, hatch, crosshatch, and aquatint. It does not apply to empty, flat, an omitted surface, a line, arc, free line, point, or a mark emitted by a Macro. An invalid word is omitted with a diagnostic. Choose one word from this table for a mark; fine-grained and packed cannot be combined either.

| Japanese | English | Meaning | Short usage |
|---|---|---|---|
| 細かい | `fine-grained` | Makes each texture dot or line smaller and adds more, retaining the covered area. | `細かい点描の円を置く。` / `Place a fine-grained stipple circle.` |
| 粗い | `coarse-grained` | Makes each texture dot or line larger and lays fewer, retaining the covered area. | `粗い粒の楕円を置く。` / `Place a coarse-grained grain ellipse.` |
| 密な | `packed` | Packs more dots or lines of the same size into the texture. | `密な平行線の四角を置く。` / `Place a packed hatch square.` |
| 疎な | `sparse` | Lays fewer dots or lines of the same size in the texture. | `疎なアクアチントの雲形を置く。` / `Place a sparse aquatint cloudform.` |

細かい describes texture fineness, while 細かく describes sway amplitude. 密な describes packing, while 濃い describes opacity relative to the tool. Internally, fine-grained and coarse-grained set `scale` to 0.05 and 0.90; packed and sparse set `density` to 0.85 and 0.05. These numbers need not be written into DDL.

### 4.8. Underlayer — したじ

The acceptance range is the same as fineness: only the seven named textures of the six closed forms. It can be combined with one handling word and one fineness word.

| Japanese | English | Meaning | Short usage |
|---|---|---|---|
| 下塗り | `underpainted` | Lays the tool's color as a fill beneath the texture. | `下塗りの密な点描の円を置く。` / `Place an underpainted packed stipple circle.` |

This is a fill beneath the form's texture, rather than a canvas ground. On empty, flat, or an omitted texture, only the word is omitted and the reason is recorded.

### 4.9. Grounds — じ

A ground belongs to the whole canvas, separately from a form or its face. Write its name as a sentence. Do not select several grounds at once. Valid instructions containing only a ground still have drawable content.

| Japanese | English | Meaning | Short usage |
|---|---|---|---|
| 紙 | `paper` | A paper ground. | `紙。` / `Paper.` |
| 和紙 | `washi` | A washi ground. | `和紙。` / `Washi.` |
| 薄墨地 | `ink wash ground` | A pale gray ground swept with dilute ink. A current word distinct from the retired 薄墨. | `薄墨地。` / `Ink wash ground.` |
| 木炭地 | `charcoal ground` | A dark gray ground rubbed with charcoal. | `木炭地。` / `Charcoal ground.` |
| カンバス | `canvas` | A woven canvas ground, rather than a canvas format selection. | `カンバス。` / `Canvas.` |
| 画用紙 | `drawing paper` | A drawing paper ground. | `画用紙。` / `Drawing paper.` |
| メゾチント | `mezzotint` | A black ground covering the background with a plate's tone. | `メゾチント。` / `Mezzotint.` |

### 4.10. Colors — いろ

These are nine abstract colors, accepted by every primitive. The work's color catalog and saved record determine the actual colors; this table does not assign fixed RGB values. The same nine words can set a background through the grammar `背景を青で埋める。` / `Fill the background with blue.`

| Japanese | English | Meaning | Short usage |
|---|---|---|---|
| 白 | `white` | A white tone. | `白い円を置く。` / `Place a white circle.` |
| 黒 | `black` | A black tone. Carries the reference's default annotation. | `黒い円を置く。` / `Place a black circle.` |
| 青 | `blue` | A blue tone. | `青い線を引く。` / `Draw a blue line.` |
| 赤 | `red` | A red tone. | `赤い三角を置く。` / `Place a red triangle.` |
| 緑 | `green` | A green tone. | `緑の点を置く。` / `Place a green point.` |
| 灰 | `gray` | A gray tone. The canonical English spelling is gray. | `灰の四角を置く。` / `Place a gray square.` |
| 黄 | `yellow` | A yellow tone. | `黄の円を置く。` / `Place a yellow circle.` |
| 橙 | `orange` | An orange tone. | `橙の楕円を置く。` / `Place an orange ellipse.` |
| 紫 | `purple` | A purple tone. | `紫の三角を置く。` / `Place a purple triangle.` |

Japanese also accepts the い forms of white, black, blue, and red, and the 色 form of all nine colors, such as 白い, 赤色, and 灰色. 黒の円 is also valid. A list of colors or tools alone does not imply alternation or cycling.

### 4.11. Movements — ゆらぎ

Movements describe unevenness in a trace. One amplitude, one spacing, and one sway quality can be combined, with bleeding as a separate attribute. Lines, arcs, free lines, and the six closed forms accept sway. A point accepts bleeding, but no sway.

| Japanese | English | Meaning and combinations | Short usage |
|---|---|---|---|
| 細かく | `narrowly` | A smaller sway amplitude. Must accompany swaying or undulating. | `細かく揺れる線を引く。` / `Draw a narrowly swaying line.` |
| 大きく | `broadly` | A larger sway amplitude, separate from a form's size. Must accompany swaying or undulating. | `大きく波打つ線を引く。` / `Draw a broadly undulating line.` |
| ゆるやかに | `loosely` | More space between waves; not drawing time or speed. | `ゆるやかに波打つ線を引く。` / `Draw a loosely undulating line.` |
| 小刻みに | `tightly` | Less space between waves; not drawing time or speed. | `小刻みに揺れる線を引く。` / `Draw a tightly swaying line.` |
| 揺れる | `swaying` | Continuous irregular sway. | `揺れる線を引く。` / `Draw a swaying line.` |
| 波打つ | `undulating` | Regular wave-shaped undulation. | `波打つ線を引く。` / `Draw an undulating line.` |
| にじみ | `bleeding` | Uneven spread at the ink's edge, independent of sway. Alone, adds no sway. | `にじみの円を置く。` / `Place a bleeding circle.` |

Narrowly or broadly without a sway quality is omitted alone with `fluctuation_amplitude_without_quality`. Loosely and tightly have no such restriction: when quality is omitted, they use irregular sway. Other omitted components of an explicit sway resolve to medium. This does not add an explicit sway to a mark with no movement words at all.

English `sways` and `undulates` are permitted grammatical forms of their rows. `fine` and `large` are not amplitude aliases. Current `large` belongs to the separate size modifier grammar.

### 4.12. Places — ばしょ

A place can name a region, rather than a fixed point. Coordinates below run from the canvas's top left at (0,0) to its bottom right at (1,1). Place and draw select an anchor after shrinking the region to two thirds about its center. Line-up, scatter, and tile distribute marks using the region. Start, end, and partway are not independent canvas placement regions.

| Japanese | English | Meaning and acceptance | Short usage |
|---|---|---|---|
| 上 | `top` | The upper third: `[0,0,1,1/3]`. | `上に円を置く。` / `Place a circle at top.` |
| 下 | `bottom` | The lower third: `[0,2/3,1,1]`. | `下に円を置く。` / `Place a circle at bottom.` |
| 中心 | `center` | The middle cell: `[1/3,1/3,2/3,2/3]`, rather than one fixed point. | `中心に円を置く。` / `Place a circle at center.` |
| 左端 | `left-edge` | The left tenth: `[0,0,1/10,1]`. | `左端に円を置く。` / `Place a circle at left-edge.` |
| 右端 | `right-edge` | The right tenth: `[9/10,0,1,1]`. | `右端に円を置く。` / `Place a circle at right-edge.` |
| 上端 | `top-edge` | The upper tenth: `[0,0,1,1/10]`. | `上端に線を引く。` / `Draw a line at top-edge.` |
| 下端 | `bottom-edge` | The lower tenth: `[0,9/10,1,1]`. | `下端に線を引く。` / `Draw a line at bottom-edge.` |
| 始点 | `start` | Selects the start of a preceding line or arc as the connection target. Not an independent canvas location. | `前の線の始点につながる弧を引く。` / `Draw an arc connected to the start of the previous line.` |
| 終点 | `end` | Selects the end of a preceding line or arc as the connection target. Not an independent canvas location. | `前の弧の終点につながる線を引く。` / `Draw a line connected to the end of the previous arc.` |
| 途中 | `partway` | Selects a point other than the two ends of a preceding line or arc, chosen during performance. A free line's interior is not a target. | `前の線の途中につながる弧を引く。` / `Draw an arc connected partway along the previous line.` |
| 隅 | `corner` | Selects one of four corner regions, each one fifth of the canvas in width and height, using the composition seed. | `隅に円を置く。` / `Place a circle in a corner.` |

English `left edge`, `right edge`, `top edge`, and `bottom edge` are parser spellings of the same rows. A named place conflicts with a numeric position, range, or pair of endpoints on the same mark. With no place, place and draw use the center region; line-up, scatter, tile, and fill use the whole canvas.

The table's start, end, and partway examples require a target drawn by the preceding sentence. Precede the start and partway examples with `赤い線を引く。` / `Draw a red line.`, and the end example with `赤い弧を引く。` / `Draw a red arc.` Pasting a relation phrase alone into empty instructions reports a missing preceding target.

### 4.13. Motions — うごき

Motions describe placement in a still work, rather than animation. All five public words other than draw accept all ten primitives. Draw accepts only line, arc, and free line.

| Japanese | English | Meaning and acceptance | Short usage |
|---|---|---|---|
| 置く | `place` | Places at one location. Omitted count is one. | `中心に円を置く。` / `Place a circle at center.` |
| 並べる | `line-up` | Lines up forms or groups in one row. Row direction is distinct from each form's angle. Omitted count is eight. | `円を五つ並べる。` / `Line up five circles.` |
| 引く | `draw` | Places a line, arc, or free line. Not a general action for a closed form or point. | `線を三本引く。` / `Draw three lines.` |
| 描く | None | **Retired row.** `prompt=false`, `display=false`, `marker=false`; not a current parser candidate. English draw belongs to 引く, rather than this row. | Use `円を置く。` / `Place a circle.` in current DDL. |
| 散らす | `scatter` | Distributes irregularly, without changing the meaning to fill or regular tiling. Omitted count is eight. | `点を五つ散らす。` / `Scatter five points.` |
| 埋める | `fill` | Densely distributes marks irregularly inside a target region and clips to its boundary. | `三つの赤い円と四つの青い点で埋める。` / `Fill with three red circles and four blue points.` |
| 敷き詰める | `tile` | Places marks in a regular repeating grid. Omitted count is eight. | `四角を九つ敷き詰める。` / `Tile nine squares.` |

`line up` and `arrange` are parser spellings of line-up. The English closure marker retains `arrange` for compatibility; the canonical Saijiki word remains `line-up`.

Fill targets can be the whole canvas, a named region, or one inline closed primitive. A target form is not an additional independent mark. An explicit count is retained; an omitted count is resolved from the target area and mark dimensions. Targets without area and unsupported geometry produce diagnostics. Resource limits apply to large counts, so a short example does not promise unlimited execution or delivery.

### 4.14. Order — じゅん

Connect a finite sequence of one attribute, forms, or groups to line-up, scatter, tile, or fill. The count is the total number of placement units, rather than the sequence length. A group's internal form count is not multiplied into the outer count.

| Japanese | English | Meaning and restrictions | Short usage |
|---|---|---|---|
| 交互に | `alternating` | Cycles exactly two items. Three or more items are not alternating. | `赤と灰を交互にして、円を五つ並べる。` / `Line up five circles, alternating red and gray.` |
| 順に | `in order` | Cycles a nonempty finite sequence in written order, retaining repeated items. | `赤・赤・青の順に繰り返して、円を八つ並べる。` / `Line up eight circles, repeating red, red, and blue in order.` |

繰り返して and 組 belong to grammar, rather than additional Saijiki rows. An in-order color sequence can also run once through its colors: `黄・橙・赤の順に段々に移して、円を九つ並べる。` This shift applies only to line-up and tile; it does not continuously morph a sequence of forms, groups, or tools.

### 4.15. Proportions — わりあい

Proportions specify aspect, size relative to the canvas, or an arc form. These are separate dimensions. Full-width and half-width do not mean a horizontal direction.

| Japanese | English | Meaning and acceptance | Short usage |
|---|---|---|---|
| 縦長 | `tall` | Makes triangle, square, ellipse, or cloudform taller; the normal ratio is 2:1. Not combined with a regular form. | `縦長の四角を置く。` / `Place a tall square.` |
| 横長 | `wide` | Makes the same four forms wider; the normal ratio is 2:1. Not combined with a regular form. | `横長の楕円を置く。` / `Place a wide ellipse.` |
| 全幅 | `full-width` | Sets the mark's reference extent to the canvas width; for a free line, this is chord length. Does not prevent overflow after rotation or named placement. | `全幅の線を引く。` / `Draw a full-width line.` |
| 半幅 | `half-width` | Sets the reference extent to half the canvas width. | `半幅の線を引く。` / `Draw a half-width line.` |
| 半円 | `semicircle` | Makes an arc's sagitta half its chord length, producing an open 180-degree arc. Only modifies arc. | `半円の弧を引く。` / `Draw a semicircle arc.` |
| 上弦 | `waxing` | An open 180-degree arc bulging right. Adds 90 degrees to its specified angle. | `上弦の弧を引く。` / `Draw a waxing arc.` |
| 下弦 | `waning` | An open 180-degree arc bulging left. Adds 270 degrees to its specified angle. | `下弦の弧を引く。` / `Draw a waning arc.` |
| 三日月 | `crescent` | Turns an arc into a thin closed moon form. Accepts flat as its only surface, and accepts neither fineness nor underlayer. | `三日月の弧を引く。` / `Draw a crescent arc.` |

縦に長い and 細長い are parser spellings of tall; 横に長い is a spelling of wide. When numeric width and height are also written, those numbers are retained and checked: height must exceed width for tall, and width must exceed height for wide.

Full-width and half-width apply to all ten ordinary primitives. Several size candidates, including numeric dimensions, size words, and width extents, retain a diagnostic and use the smaller candidate. A single line or free line defined by two numeric endpoints cannot also take full-width or half-width because its endpoints determine the length. Semicircle, waxing, waning, and crescent must modify arc; they are not independent head nouns.

### 4.16. Relations — あいだ

A short word names a relation without establishing a preceding target. Use a full phrase from the table to write the relation. The current mark refers to the immediately preceding mark; between refers to the preceding two. An omitted target is never replaced by a different surviving mark. One instruction takes at most one relation.

| Japanese | English short word | Full Japanese phrase | Full English phrase | Meaning and acceptance |
|---|---|---|---|---|
| 沿う | `along` | `前の線に沿って` | `along the previous line` | Current and target must both be lines. Makes an unspecified direction parallel; retains dimensions and explicit direction. |
| 触れない | `not touching` | `前の形に触れない` | `not touching the previous shape` | Leaves a gap from the preceding mark. Unavailable when a free line participates. |
| 触れる | `touching` | `前の線に触れる` / `前の弧に両端で触れる` | `touching the previous line` / `touching the previous arc at both ends` | Matches both ends. Current may be a line, ordinary arc, or free line. The target must be the line or ordinary arc named by the complete phrase; no complete phrase names a prior free line. |
| 切る | `cutting` | `前の線を切る` | `cutting the previous line` | Current and target must both be lines. Crosses them while retaining dimensions and explicit direction. |
| 間に | `between` | `前の二つの間に` | `between the previous two` | Places between the bounding-box centers of the preceding two marks. Unavailable when a free line participates. |
| つながる | `connected` | `前の形につながる` | `connected to the previous shape` | Joins the current start to the target end. Current: line, ordinary arc, free line, or point. Target: those forms, or the outline of a circle, ellipse, triangle, square, or polygon; excludes cloudform and crescent targets. |
| 載る | `resting on` | `前の形に載る` | `resting on the previous shape` | Aligns the current bottom with the target top using bounding boxes. Excludes a prior point and a free line on either side. |
| 中に | `inside` | `前の形の中に` | `inside the previous shape` | Fits the current mark inside a preceding circle, ellipse, triangle, square, polygon, or cloudform. An open mark, point, or crescent cannot be the container; a mark that does not fit fails the relation. Excludes free line. |
| 重なる | `overlaps` | `前の形に重なる` | `overlapping the previous shape` | Partly overlaps bounding boxes. Excludes a prior point and a free line on either side. Retains the distinct spellings of the English short word and full phrase. |
| 横切る | `crossing` | `前の形を横切る` | `crossing the previous shape` | Extends past opposite sides of the target. Fails if the current mark is too short. Excludes free line. |
| 鏡写し | `mirrored` | `前の形と鏡写し` | `mirrored with the previous shape` | Reflects positions and orientations across an axis between two forms or groups. Does not copy color or tool. Incompatible bodies and free lines lose the relation. |

A complete short example is `赤い線を引く。前の線に沿って青い線を引く。` / `Draw a red line. Draw a blue line along the previous line.` Writing only along does not select a nearby line automatically.

Connected also has the following finite phrases for a line or arc target.

| Selection | Japanese | English |
|---|---|---|
| Start connection | `[前の]線/弧の始点につながる` | `connected to the start of the previous line/arc` |
| End connection | `[前の]線/弧の終点につながる` | `connected to the end of the previous line/arc` |
| Interior connection | `[前の]線/弧の途中につながる` | `connected partway along the previous line/arc` |

Brackets and slashes explain alternatives here; do not type them into the instructions. English also accepts `connects to` and `connects partway along` in this finite grammar, and permits omission of `the` and `previous`. The current side remains its start. For a preceding free line in ordinary DDL, use `前の形につながる` / `connected to the previous shape`; do not select its interior.

A numeric position is never moved to satisfy a relation. If the required movement conflicts, only the relation is omitted with a diagnostic. Explicit dimensions, size words including normal, and angles also constrain Touching; the mark is not silently stretched or turned to touch. Macro Emits currently carry along, cutting, touching, connected, not touching, and between; resting on, inside, overlaps, and crossing do not extend to Emit internals. Mirroring a whole Macro or group is a separate external relation in the instructions.

Mirroring requires matching primitive sequences and instance counts, arc forms, and side counts, with one rigid pose that also matches the internal composition. Coincident anchors cannot establish an axis and fail the relation. A single follower with omitted dimensions may take the target geometry. Explicit dimensions, size, proportions, angles, and the internal forms of a group or Macro remain fixed constraints.

### Parser spellings, retired words, and internal values

Each canonical word appears in one row above. The current asset has no configured `semantic_alias` rows; alternative spellings belong to the same row's parser surfaces. They do not add displayed words or underdrawing enum choices.

| Class | Words or examples | Treatment |
|---|---|---|
| Current parser spellings | 三角形, 四角形, 長方形, `rectangle`, `lines`, 横, 縦, the four English edge words with spaces, `arrange`, `line up`, 縦に長い, 細長い, 横に長い | The same identities as their canonical rows; public spellings remain those in the tables. |
| Current grammatical forms | 白い, 赤色, regular English form plurals, `horizontally`, `vertically`, `diagonally`, `sways`, `undulates` | Permitted grammar changes, rather than additional words or counts. |
| Hidden accepted words | 多角形, 左上がり, 左下がり | Absent from `prompt` and display projections, but recognized in direct DDL because their markers are enabled. |
| Retired row | 描く | Remains as a tombstone in the asset; not a parser candidate. Has no English surface. |
| Words used only in v1 migration | 薄墨 / `pale ink wash`, ゆっくり / `slowly`, 速く / `quickly`, 震える / `trembling`, `trembles`, 滲む / `blurring`, 中央 / `middle`, and 点 meaning stipple | Not aliases in new v2 instructions. Saved documents migrate to the current words. The point form and ink wash ground remain distinct current words. |
| v1 amplitude spellings | `fine`, `finely`, `large`, `largely` | Migrate to `narrowly` and `broadly` when they mean amplitude. Current `large` has the separate grammatical role of form size. |
| Internal values | `brush_thin`, `brush_thick`, `oil_paint`, surface `none` and `solid`, `fine_grained`, `line_up`, `not_touching` | Score, typed meaning, or underdrawing identifiers. Keep them distinct from written DDL such as `fine-brush`, `flat`, `fine-grained`, and `line-up`. |
| Word annotations | `（既定）`, `(default)`, and tool guidance sentences | Explanations for readers or the underdrawing, rather than the DDL words themselves. |

### Finite grammar outside the Saijiki

The following constructions are available grammar, rather than new rows in the 15 categories or relations. Do not add them to the Saijiki word count.

| Grammar owner | Representative surfaces | Distinction |
|---|---|---|
| Line width | ごく細い, 細い, ごく太い, 太い / `extra-fine`, `thin`, `extra-thick`, `thick` | Separate from touches. Current English `fine` is neither the canonical width surface nor an amplitude alias. |
| Relative size | とても小さな, 普通の大きさ, とても大きな, 特大の, 巨大な, 小さめ, 小さな, 大きめ, 大きな and their permitted adjective forms / `slightly small`, `small`, `very small`, `normal-sized`, `slightly large`, `large`, `very large`, `extra-large`, `huge` | Nine finite local sizes, separate from broadly. Does not allow arbitrary degree adverbs. |
| Shape constraints | 正三角形, 正方形, 五角形 through 八角形, `regular` | Regularity and side count, without new Saijiki primitive identities. |
| Counts and counters | Japanese つ counts one through nine; 十, 10, とお, 本, 個, 枚; English `one`, `five`, and other counts | Quantity belongs to grammar. 少し, 数個, いくつか, たくさん, 多数, 無数, `a few`, `several`, `many`, `numerous`, and `countless` are also parser quantity candidates, rather than Saijiki words or exact counts. |
| Numeric geometry | Radius, diameter, length, side, width and height, chord and sagitta, numeric position, range, endpoints, and rotation in degrees | Finite constructions connecting numbers to dimensions and owners. Distinguish the rotated word from a numeric angle. |
| Groups, repetition, fading, color shift | 組, 繰り返して, 左から右へ薄れさせて, 順に段々に移して | Instructions about structure and distribution; no additional category or word chip. |
| Canvas formats | Host options such as `square`, `a4`, and `wide` | The paper, selected outside the DDL text; a format name is not written in DDL. What a DDL writes is the declaration of the ratio it was laid out in, `Aspect ratio W:H.` (3.27). Distinct from form and proportion words with the same spelling. |
| Vocabulary Macros | Qualified names such as `Nature.YoungLeaves` | A separate registered vocabulary catalog, outside the core Saijiki's 102 rows. |

### Sources and verification scope

Spellings, flags, and order come from `core/crates/inku-ddl/assets/saijiki-v2.json`. `src/saijiki.rs` defines recognition eligibility and projections; `src/parser.rs` and `src/shape_constraint.rs` define parser spellings and grammar. Acceptance was compared with `src/score_lowering.rs`, `src/geometry.rs`, `src/score_angle.rs`, `src/fluctuation.rs`, `assets/work-plan-capabilities-v2.json`, and the relevant existing fixture and test source. The distinction between accepted surfaces and visible performance was checked in `inku-render/src/surfaces.rs`, `marks.rs`, and `support.rs`. Short interface explanations also informed the text: `web/src/routes/+page.svelte` and `web/src/lib/saijiki-surface.ts`.

The reference commit is `97b50a52367554a94e9f364b90dc538d0f6b68bc`. Spellings and acceptance boundaries follow that source version. Actual performance also requires the prior objects a relation names, the work's drawing conditions, and sufficient resources.

## 5. Fifty complex DDL examples

Each example is an independent set of DDL sentences that can be entered on its own. Copy the entire English block, or its corresponding Japanese block. All 50 examples use standard vocabulary and ordinary grammar; they need no registered plugin. Titles and aims are explanations and do not belong in the DDL input.

Numeric positions are fractions of the canvas's horizontal and vertical axes. Dimensions use the canvas's short side as one unit. Choose the canvas format (the paper) and seeds in the app. Drawn from the app, a new DDL begins with the paper's ratio declaration (`Aspect ratio 1:1.` and the like). Details can vary with those choices. These examples describe new drawings; they are not records of reproducing a saved SVG with the current engine.

### 5.01. Three kinds of dimensions

Aim: Use a radius, width and height, and a side length to place three shapes at numeric positions.

English DDL:

```text
Paper.
Fill the background with white.
Place one red empty circle radius 0.1 at horizontal 0.25, vertical 0.3.
Place one blue flat ellipse width 0.25, height 0.15 at horizontal 0.7, vertical 0.3.
Place one black empty square side length 0.2 at horizontal 0.5, vertical 0.7.
```

Japanese DDL (reference):

```text
紙。
背景を白で埋める。
画面の横0.25、縦0.3の位置に、半径0.1の赤の空の円を1個置く。
画面の横0.7、縦0.3の位置に、幅0.25、高さ0.15の青の塗りの楕円を1個置く。
画面の横0.5、縦0.7の位置に、一辺0.2の黒の空の四角を1個置く。
```

### 5.02. Read radius and diameter separately

Aim: Give two circles the same size using radius and diameter, then add a row of small points below.

English DDL:

```text
Drawing paper.
Place one blue rotring empty circle radius 0.12 at horizontal 0.3, vertical 0.4.
Place one red rotring empty circle diameter 0.24 at horizontal 0.7, vertical 0.4.
Line up 7 black points radius 0.01 from horizontal 0.2, vertical 0.75 to horizontal 0.8, vertical 0.75.
```

Japanese DDL (reference):

```text
画用紙。
画面の横0.3、縦0.4の位置に、半径0.12の青のロットリングの空の円を1個置く。
画面の横0.7、縦0.4の位置に、直径0.24の赤のロットリングの空の円を1個置く。
画面の横0.2、縦0.75から横0.8、縦0.75まで、半径0.01の黒の点を7個並べる。
```

### 5.03. Arc depth and line length

Aim: Set arcs by their chord and sagitta, and compare them with a line of the same length.

English DDL:

```text
Paper.
Draw one blue pen arc chord 0.4, sagitta 0.05 at horizontal 0.5, vertical 0.25.
Draw one red pen arc chord 0.4, sagitta 0.15 at horizontal 0.5, vertical 0.5.
Draw one black horizontal line length 0.4 at horizontal 0.5, vertical 0.75.
```

Japanese DDL (reference):

```text
紙。
画面の横0.5、縦0.25の位置に、弦長0.4、矢高0.05の青のペンの弧を1個引く。
画面の横0.5、縦0.5の位置に、弦長0.4、矢高0.15の赤のペンの弧を1個引く。
画面の横0.5、縦0.75の位置に、長さ0.4の黒の水平の線を1個引く。
```

### 5.04. Tall and wide forms

Aim: Combine proportion words with size words instead of fixing dimensions in numbers.

English DDL:

```text
Washi.
Place one large blue empty wide ellipse at the top.
Line up 3 small red flat tall ellipses at the bottom.
Draw one black fine-brush vertical line at left-edge.
```

Japanese DDL (reference):

```text
和紙。
上に、大きな青の空の横長の楕円を1個置く。
下に、小さな赤の塗りの縦長の楕円を3個並べる。
左端に、黒の細筆の垂直の線を1個引く。
```

### 5.05. White marks on a dark ground

Aim: Set the background and ground separately, then add white faces and lines over a charcoal ground.

English DDL:

```text
Charcoal ground.
Fill the background with black.
Place one large white chalk faint flat circle at the top.
Line up 5 small white pencil triangles at the bottom.
Draw one white fine-brush horizontal line at the center.
```

Japanese DDL (reference):

```text
木炭地。
背景を黒で埋める。
上に、白のチョークの薄い塗りの大きな円を1個置く。
下に、白の鉛筆の小さな三角を5個並べる。
中心に、白の細筆の水平の線を1個引く。
```

### 5.06. An ink wash ground and bleeding contours

Aim: Set the ground, bleeding contours, and faint faces as separate properties.

English DDL:

```text
Ink wash ground.
Fill the background with white.
Place one blue thick-brush faint sweep wide ellipse at the top.
Line up 3 red fine-brush bleeding empty circles at the bottom.
Draw one black pen dotted horizontal line at the center.
```

Japanese DDL (reference):

```text
薄墨地。
背景を白で埋める。
上に、青の太筆の薄い刷きの横長の楕円を1個置く。
下に、にじみの赤の細筆の空の円を3個並べる。
中心に、黒のペンの点線の水平の線を1個引く。
```

### 5.07. Four kinds of continuity

Aim: Keep the dimensions and tool of each line the same while writing solid, dashed, dotted, and dash-dot.

English DDL:

```text
Paper.
Draw one black rotring solid horizontal line length 0.6 at horizontal 0.5, vertical 0.2.
Draw one black rotring dashed horizontal line length 0.6 at horizontal 0.5, vertical 0.4.
Draw one black rotring dotted horizontal line length 0.6 at horizontal 0.5, vertical 0.6.
Draw one black rotring dash-dot horizontal line length 0.6 at horizontal 0.5, vertical 0.8.
```

Japanese DDL (reference):

```text
紙。
画面の横0.5、縦0.2の位置に、長さ0.6の黒のロットリングの実線の水平の線を1個引く。
画面の横0.5、縦0.4の位置に、長さ0.6の黒のロットリングの破線の水平の線を1個引く。
画面の横0.5、縦0.6の位置に、長さ0.6の黒のロットリングの点線の水平の線を1個引く。
画面の横0.5、縦0.8の位置に、長さ0.6の黒のロットリングの一点鎖線の水平の線を1個引く。
```

### 5.08. Alternating tools and a mirror

Aim: Alternate tools in a row, then relate only the following two arcs through a mirror.

English DDL:

```text
Paper.
Line up five black lines, alternating pencil and thick-brush.
Place a diagonal red arc at left-edge.
Place a blue arc at right-edge, mirrored with the previous shape.
```

Japanese DDL (reference):

```text
紙。
鉛筆と太筆を交互にして、黒い線を五本並べる。
左端に斜めの赤い弧を置く。
右端に前の形と鏡写しの青い弧を置く。
```

### 5.09. Three fine tools

Aim: Give separate marks silverpoint, burin, and drypoint tools.

English DDL:

```text
Drawing paper.
Line up 3 gray silverpoint thin horizontal lines at the top.
Line up 3 black burin empty circles at the center.
Line up 5 small red drypoint semicircle arcs at the bottom.
```

Japanese DDL (reference):

```text
画用紙。
上に、灰の銀筆の細い水平の線を3個並べる。
中心に、黒のビュランの空の円を3個並べる。
下に、赤のドライポイントの小さな半円の弧を5個並べる。
```

### 5.10. The film of sweep and the strokes of brushmarks

Aim: Give two squares made with the same tool different closed-face textures: sweep and brushmarks.

English DDL:

```text
Canvas.
Fill the background with gray.
Place one white thick-brush sweep square side length 0.3 at horizontal 0.3, vertical 0.5.
Place one white thick-brush brushmarks square side length 0.3 at horizontal 0.7, vertical 0.5.
```

Japanese DDL (reference):

```text
カンバス。
背景を灰で埋める。
画面の横0.3、縦0.5の位置に、一辺0.3の白の太筆の刷きの四角を1個置く。
画面の横0.7、縦0.5の位置に、一辺0.3の白の太筆の刷毛目の四角を1個置く。
```

### 5.11. Change the size of the texture

Aim: Use fine-grained stipple and coarse-grained grain to specify the size of the texture's marks.

English DDL:

```text
Paper.
Place one red pen fine-grained stipple circle at the top.
Place one blue pen coarse-grained grain ellipse at the bottom.
Draw one black rotring horizontal line at the center.
```

Japanese DDL (reference):

```text
紙。
上に、赤のペンの細かい点描の円を1個置く。
下に、青のペンの粗い粒の楕円を1個置く。
中心に、黒のロットリングの水平の線を1個引く。
```

### 5.12. Lines over an underpainted face

Aim: Specify underpainting, texture density, and faint intensity together.

English DDL:

```text
Canvas.
Place one red thick-brush faint underpainted packed crosshatch square at the top.
Place one blue pen underpainted sparse hatch ellipse at the bottom.
Line up 3 small black fine-brush empty circles at the center.
```

Japanese DDL (reference):

```text
カンバス。
上に、赤の太筆の下塗りの密な交差線の薄い四角を1個置く。
下に、青のペンの下塗りの疎な平行線の楕円を1個置く。
中心に、黒の細筆の小さな空の円を3個並べる。
```

### 5.13. Packed and sparse stipple

Aim: Set only density here, in contrast with the texture-mark sizes in example 11.

English DDL:

```text
Paper.
Place one red pen packed stipple circle diameter 0.3 at horizontal 0.3, vertical 0.5.
Place one red pen sparse stipple circle diameter 0.3 at horizontal 0.7, vertical 0.5.
Line up 7 small black pen points at the bottom.
```

Japanese DDL (reference):

```text
紙。
画面の横0.3、縦0.5の位置に、直径0.3の赤のペンの密な点描の円を1個置く。
画面の横0.7、縦0.5の位置に、直径0.3の赤のペンの疎な点描の円を1個置く。
下に、黒のペンの小さな点を7個並べる。
```

### 5.14. Aquatint and a cloudform

Aim: Use a cloudform as a standard closed shape, and combine texture with underpainting.

English DDL:

```text
Mezzotint.
Fill the background with white.
Place one red pen sparse aquatint cloudform at the top.
Line up 3 yellow thick-brush underpainted fine-grained aquatint triangles at the bottom.
```

Japanese DDL (reference):

```text
メゾチント。
背景を白で埋める。
上に、赤のペンの疎なアクアチントの雲形を1個置く。
下に、黄の太筆の下塗りの細かいアクアチントの三角を3個並べる。
```

### 5.15. Different amplitudes of sway

Aim: Specify sway amplitude with narrowly and broadly, keeping it distinct from shape size.

English DDL:

```text
Washi.
Draw one blue fine-brush narrowly swaying horizontal line at the top.
Draw one red fine-brush broadly swaying horizontal line at the bottom.
Line up 5 small black rotring empty circles at the center.
```

Japanese DDL (reference):

```text
和紙。
上に、細かく揺れる青の細筆の水平の線を1個引く。
下に、大きく揺れる赤の細筆の水平の線を1個引く。
中心に、黒のロットリングの小さな空の円を5個並べる。
```

### 5.16. Change the spacing of waves

Aim: Keep amplitude the same while combining loosely and tightly undulating marks.

English DDL:

```text
Drawing paper.
Draw one blue pen narrowly loosely undulating horizontal line at the top.
Draw one red pen narrowly tightly undulating horizontal line at the bottom.
Place one gray thick-brush faint flat wide ellipse at the center.
```

Japanese DDL (reference):

```text
画用紙。
上に、細かくゆるやかに波打つ青のペンの水平の線を1個引く。
下に、細かく小刻みに波打つ赤のペンの水平の線を1個引く。
中心に、灰の太筆の薄い塗りの横長の楕円を1個置く。
```

### 5.17. Semicircle and crescent arcs

Aim: Combine arc-form and width words, then add a row of small circles below.

English DDL:

```text
Paper.
Place one red pen half-width semicircle arc at the top.
Place one blue fine-brush full-width crescent arc at the center.
Line up 7 small gray pencil empty circles at the bottom.
```

Japanese DDL (reference):

```text
紙。
上に、赤のペンの半幅の半円の弧を1個置く。
中心に、青の細筆の全幅の三日月の弧を1個置く。
下に、灰の鉛筆の小さな空の円を7個並べる。
```

### 5.18. A waxing and waning pair

Aim: Give separate arcs waxing and waning forms, with a row of points between them.

English DDL:

```text
Washi.
Place one black fine-brush half-width waxing arc at the top.
Place one black fine-brush half-width waning arc at the bottom.
Line up 9 small red pen points at the center.
```

Japanese DDL (reference):

```text
和紙。
上に、黒の細筆の半幅の上弦の弧を1個置く。
下に、黒の細筆の半幅の下弦の弧を1個置く。
中心に、赤のペンの小さな点を9個並べる。
```

### 5.19. A free line between two points

Aim: Set both ends of a free line in numbers, using the same endpoint syntax as a straight line.

English DDL:

```text
Paper.
Draw one blue fine-brush free line from horizontal 0.15, vertical 0.2 to horizontal 0.85, vertical 0.7.
Draw one gray pencil dashed line from horizontal 0.15, vertical 0.8 to horizontal 0.85, vertical 0.3.
Line up 3 small red pen empty circles at the top.
```

Japanese DDL (reference):

```text
紙。
画面の横0.15、縦0.2から横0.85、縦0.7まで、青の細筆の自由線を1個引く。
画面の横0.15、縦0.8から横0.85、縦0.3まで、灰の鉛筆の破線の線を1個引く。
上に、赤のペンの小さな空の円を3個並べる。
```

### 5.20. From a closed shape to a free line

Aim: Refer to the previous shape in sequence to connect a circle, a free line, and a line.

English DDL:

```text
Washi.
Place one black pen circle at the center.
Draw one black fine-brush free line connected to the previous shape.
Draw one red pen line connected to the previous shape.
```

Japanese DDL (reference):

```text
和紙。
中心に、黒のペンの円を1個置く。
前の形につながる黒の細筆の自由線を1個引く。
前の形につながる赤のペンの線を1個引く。
```

### 5.21. Choose the start or the end

Aim: Distinguish connection targets by naming the start of the previous line and the end of the previous arc.

English DDL:

```text
Paper.
Draw a red line.
Draw a blue arc connected to the start of the previous line.
Draw a black line connected to the end of the previous arc.
```

Japanese DDL (reference):

```text
紙。
赤い線を引く。
青い弧を引く、前の線の始点につながる。
黒い線を引く、前の弧の終点につながる。
```

### 5.22. Marks branching partway along

Aim: Connect a different mark partway along an undulating line and the following arc.

English DDL:

```text
Paper.
Draw a red undulating line.
Draw a small diagonal blue arc connected partway along the previous line.
Draw a small black vertical line connected partway along the previous arc.
```

Japanese DDL (reference):

```text
紙。
赤い波打つ線を引く。
斜めの小さな青い弧を引く、前の線の途中につながる。
小さな黒い垂直の線を引く、前の弧の途中につながる。
```

### 5.23. Make a line and an arc touch

Aim: State touching explicitly as its own relation, then add independent shapes.

English DDL:

```text
Paper.
Place one red horizontal line at the center.
Place one blue arc at the center touching the previous line.
Line up 3 green empty circles at the bottom.
```

Japanese DDL (reference):

```text
紙。
中心に、赤の水平の線を1個置く。
中心に、前の線に触れる青の弧を1個置く。
下に、緑の空の円を3個並べる。
```

### 5.24. Along the previous line

Aim: Place a line along the previous line, then add a row of circles without a relation.

English DDL:

```text
Drawing paper.
Place one black pencil horizontal line at the center.
Place one blue fine-brush line at the center along the previous line.
Line up 5 small red empty circles at the bottom.
```

Japanese DDL (reference):

```text
画用紙。
中心に、黒の鉛筆の水平の線を1個置く。
中心に、前の線に沿って、青の細筆の線を1個置く。
下に、赤の小さな空の円を5個並べる。
```

### 5.25. Cut the previous line

Aim: State a cutting relation and combine a numeric line length with a separate row of points.

English DDL:

```text
Paper.
Place one black horizontal line at the center.
Place one red line length 0.2 at the center cutting the previous line.
Line up 7 small blue points at the top.
```

Japanese DDL (reference):

```text
紙。
中心に、黒の水平の線を1個置く。
中心に、長さ0.2の赤の線を1個置く、前の線を切る。
上に、青の小さな点を7個並べる。
```

### 5.26. Two shapes that do not touch

Aim: Keep an explicit not-touching relation while giving both shapes the same center region.

English DDL:

```text
Washi.
Place one red flat circle at the center.
Place one blue empty square at the center not touching the previous shape.
Line up 3 small black fine-brush arcs at the bottom.
```

Japanese DDL (reference):

```text
和紙。
中心に、赤の塗りの円を1個置く。
前の形に触れない青の空の四角を中心に1個置く。
下に、黒の細筆の小さな弧を3個並べる。
```

### 5.27. Place a shape between the previous two

Aim: Use the previous two instructions as the targets and place a small square between them.

English DDL:

```text
Paper.
Place one red empty circle radius 0.1 at horizontal 0.25, vertical 0.4.
Place one blue empty ellipse width 0.2, height 0.1 at horizontal 0.75, vertical 0.6.
Place one small green flat square at the center between the previous two.
```

Japanese DDL (reference):

```text
紙。
画面の横0.25、縦0.4の位置に、半径0.1の赤の空の円を1個置く。
画面の横0.75、縦0.6の位置に、幅0.2、高さ0.1の青の空の楕円を1個置く。
前の二つの間に、小さな緑の塗りの四角を中心に1個置く。
```

### 5.28. A group of points inside a shape

Aim: Apply an inside relation to an entire scatter of points inside a closed shape.

English DDL:

```text
Canvas.
Fill the background with black.
Place one large yellow thick-brush faint sweep square at the center.
Scatter 40 very small white pencil points inside the previous shape.
```

Japanese DDL (reference):

```text
カンバス。
背景を黒で埋める。
中心に、黄の太筆の薄い刷きの大きな四角を1個置く。
白の鉛筆のとても小さな点を40個散らす、前の形の中に。
```

### 5.29. A group of circles resting on a face

Aim: Draw a lower face first, then give the following scatter of circles a resting-on relation.

English DDL:

```text
Drawing paper.
Fill the background with white.
Place one large gray thick-brush faint flat wide square at the bottom.
Scatter 12 small yellow crayon dense flat circles resting on the previous shape.
Draw one black pen horizontal line at the top.
```

Japanese DDL (reference):

```text
画用紙。
背景を白で埋める。
下に、灰の太筆の薄い塗りの大きな横長の四角を1個置く。
黄のクレヨンの濃い塗りの小さな円を12個散らす、前の形に載る。
上に、黒のペンの水平の線を1個引く。
```

### 5.30. An overlap and a crossing

Aim: Give successive marks overlapping and crossing relations with different previous targets.

English DDL:

```text
Paper.
Place one red thick-brush faint flat square at the center.
Place one blue empty circle at the center overlapping the previous shape.
Draw one black diagonal line length 0.5 at the center crossing the previous shape.
```

Japanese DDL (reference):

```text
紙。
中心に、赤の太筆の薄い塗りの四角を1個置く。
前の形に重なる青の空の円を中心に1個置く。
前の形を横切る長さ0.5の黒の斜めの線を中心に1個引く。
```

### 5.31. A mirror with a different color

Aim: Mirror the geometry of the previous arc while keeping the color written for the next arc.

English DDL:

```text
Washi.
Place a diagonal red arc at left-edge.
Place a blue arc at right-edge, mirrored with the previous shape.
Line up 9 small black pencil points at the bottom.
```

Japanese DDL (reference):

```text
和紙。
左端に斜めの赤い弧を置く。
右端に前の形と鏡写しの青い弧を置く。
下に、黒の鉛筆の小さな点を9個並べる。
```

### 5.32. Place two shapes together

Aim: Place the shapes in one sentence as an overlapping group, then add separate placements.

English DDL:

```text
Paper.
Place a red circle and a blue square overlapping at the center.
Line up 3 small yellow triangles at the top.
Draw one black fine-brush half-width arc at the bottom.
```

Japanese DDL (reference):

```text
紙。
赤い円と青い四角を中心に重ねて置く。
上に、黄の小さな三角を3個並べる。
下に、黒の細筆の半幅の弧を1個引く。
```

### 5.33. Repeat three kinds of shapes

Aim: Specify a total row count and repeat a finite sequence of circles, lines, and arcs.

English DDL:

```text
Drawing paper.
Line up eight, repeating a small red circle, a small blue line, and a small gray arc in order.
Draw one black pen horizontal line at the top.
Scatter 5 small yellow points at the bottom.
```

Japanese DDL (reference):

```text
画用紙。
赤い小さな円・青い小さな線・灰の小さな弧の順に繰り返して、八つ並べる。
上に、黒のペンの水平の線を1個引く。
下に、黄の小さな点を5個散らす。
```

### 5.34. A pair of shapes alternating with an arc

Aim: Treat a circle and a line as one group, alternating it with an arc over five units.

English DDL:

```text
Paper.
Line up five, alternating a group of a red circle and a blue line with a gray arc.
Line up 7 small black pencil points at the top.
Place one green thick-brush faint flat square at the bottom.
```

Japanese DDL (reference):

```text
紙。
赤い円と青い線の組を、灰の弧と交互に5つ並べる。
上に、黒の鉛筆の小さな点を7個並べる。
下に、緑の太筆の薄い塗りの四角を1個置く。
```

### 5.35. Two alternating-color rows

Aim: Start each alternating sequence afresh in separate rows at the top and bottom.

English DDL:

```text
Paper.
Line up 5 small empty circles at the top, alternating red and gray.
Line up 7 small flat squares at the bottom, alternating blue and yellow.
Draw one black rotring horizontal line at the center.
```

Japanese DDL (reference):

```text
紙。
上に、赤と灰を交互にして、小さな空の円を5個並べる。
下に、青と黄を交互にして、小さな塗りの四角を7個並べる。
中心に、黒のロットリングの水平の線を1個引く。
```

### 5.36. Scatter a three-color cycle

Aim: Attach a finite color sequence to a scatter and keep a separate drawing a single color.

English DDL:

```text
Canvas.
Fill the background with black.
Scatter 30 very small points in the range horizontal 0.1 to 0.9, vertical 0.1 to 0.7, repeating red, orange, and yellow in order.
Place one white pen empty wide ellipse at the bottom.
```

Japanese DDL (reference):

```text
カンバス。
背景を黒で埋める。
画面の横0.1〜0.9、縦0.1〜0.7の範囲に、赤・橙・黄の順に繰り返して、とても小さな点を30個散らす。
下に、白のペンの空の横長の楕円を1個置く。
```

### 5.37. A two-color grid and a foreground

Aim: Draw a tiled field of squares first, then add a circle and a line with later sentences.

English DDL:

```text
Paper.
Tile 49 flat squares side length 0.142857 in the range horizontal 0 to 1, vertical 0 to 1, alternating white and blue.
Place one large red thick-brush empty circle at the center.
Draw one black pen half-width horizontal line at the bottom.
```

Japanese DDL (reference):

```text
紙。
画面の横0〜1、縦0〜1の範囲に、白と青を交互にして、一辺0.142857の塗りの四角を49個敷き詰める。
中心に、赤の太筆の空の大きな円を1個置く。
下に、黒のペンの半幅の水平の線を1個引く。
```

### 5.38. Fill the inside of a circle with points

Aim: Specify the target circle and the number of points inside it in one sentence.

English DDL:

```text
Paper.
Fill a circle diameter 0.5 at horizontal 0.5, vertical 0.5 with 3 red points.
Draw one blue pen half-width horizontal line at the top.
Line up 3 black empty triangles at the bottom.
```

Japanese DDL (reference):

```text
紙。
画面の横0.5、縦0.5の位置に、直径0.5の円を三つの赤い点で埋める。
上に、青のペンの半幅の水平の線を1個引く。
下に、黒の空の三角を3個並べる。
```

### 5.39. Fill a numeric range

Aim: Use the lower strip itself as the region to fill, separate from a scatter in the upper strip.

English DDL:

```text
Drawing paper.
Fill the background with white.
Fill small red circles at the bottom (horizontal 0 to 1, vertical 2/3 to 1).
Scatter 12 small blue points at the top (horizontal 0 to 1, vertical 0 to 1/3).
Draw one black pen horizontal line at the center.
```

Japanese DDL (reference):

```text
画用紙。
背景を白で埋める。
下（横0〜1、縦2/3〜1）に、小さな赤い円を埋める。
上（横0〜1、縦0〜1/3）に、青の小さな点を12個散らす。
中心に、黒のペンの水平の線を1個引く。
```

### 5.40. Give a range a name of your own

Aim: Use the words before the parentheses as a description and the numeric range inside them to determine placement.

English DDL:

```text
Washi.
Scatter 5 small red empty circles in the left window (horizontal 0.1 to 0.35, vertical 0.2 to 0.8).
Tile 6 small blue flat squares in the right window (horizontal 0.65 to 0.9, vertical 0.2 to 0.8).
Draw one black vertical line length 0.3 at horizontal 0.5, vertical 0.5.
```

Japanese DDL (reference):

```text
和紙。
左の小窓（横0.1〜0.35、縦0.2〜0.8）に、赤の小さな空の円を5個散らす。
右の小窓（横0.65〜0.9、縦0.2〜0.8）に、青の小さな塗りの四角を6個敷き詰める。
画面の横0.5、縦0.5の位置に、長さ0.3の黒の垂直の線を1個引く。
```

### 5.41. Write angles in numbers

Aim: Give a square, ellipse, and arc separate numeric rotations.

English DDL:

```text
Paper.
Place one red empty square side length 0.15 rotated 30 degrees at horizontal 0.25, vertical 0.3.
Place one blue flat ellipse width 0.25, height 0.1 rotated 75 degrees at horizontal 0.7, vertical 0.3.
Draw one black arc chord 0.3, sagitta 0.1 rotated 315 degrees at horizontal 0.5, vertical 0.7.
```

Japanese DDL (reference):

```text
紙。
画面の横0.25、縦0.3の位置に、一辺0.15の回転30度の赤の空の四角を1個置く。
画面の横0.7、縦0.3の位置に、幅0.25、高さ0.1の回転75度の青の塗りの楕円を1個置く。
画面の横0.5、縦0.7の位置に、弦長0.3、矢高0.1の回転315度の黒の弧を1個引く。
```

### 5.42. Row direction and mark angle

Aim: Specify the direction between a row's endpoints separately from each ellipse's rotation.

English DDL:

```text
Paper.
Line up 4 small black ellipses rotated 337.5 degrees from horizontal 0.2, vertical 0.3 to horizontal 0.8, vertical 0.3.
Line up 5 blue empty circles radius 0.03 from horizontal 0.8, vertical 0.8 to horizontal 0.2, vertical 0.5.
Scatter 3 small red points at the top.
```

Japanese DDL (reference):

```text
紙。
画面の横0.2、縦0.3から横0.8、縦0.3まで、回転337.5度の黒の小さな楕円を4個並べる。
画面の横0.8、縦0.8から横0.2、縦0.5まで、半径0.03の青の空の円を5個並べる。
上に、赤の小さな点を3個散らす。
```

### 5.43. Hexagons in a field and a row

Aim: State a polygon's sides in its shape name, combining tiling with a row between two endpoints.

English DDL:

```text
Paper.
Tile 9 black empty hexagon radius 0.06 in the range horizontal 0.1 to 0.9, vertical 0.3 to 0.9.
Line up 7 red flat hexagon radius 0.04 from horizontal 0.1, vertical 0.15 to horizontal 0.9, vertical 0.15.
Place one small blue fine-brush empty circle at the center.
```

Japanese DDL (reference):

```text
紙。
画面の横0.1〜0.9、縦0.3〜0.9の範囲に、半径0.06の黒の空の六角形を9個敷き詰める。
画面の横0.1、縦0.15から横0.9、縦0.15まで、半径0.04の赤の塗りの六角形を7個並べる。
中心に、青の細筆の小さな空の円を1個置く。
```

### 5.44. Small, normal, and large

Aim: Use the finite size modifiers on several shapes without numeric dimensions.

English DDL:

```text
Drawing paper.
Line up 7 very small red flat circles at the top.
Place one normal-sized blue empty square at the center.
Place one large gray faint sweep wide ellipse at the bottom.
```

Japanese DDL (reference):

```text
画用紙。
上に、とても小さな赤の塗りの円を7個並べる。
中心に、普通の大きさの青の空の四角を1個置く。
下に、大きな灰の薄い刷きの横長の楕円を1個置く。
```

### 5.45. Opposing horizontal fades

Aim: Give two rows opposite fades while keeping each row's endpoints in numbers.

English DDL:

```text
Paper.
Line up 9 red empty circles radius 0.03 from horizontal 0.1, vertical 0.3 to horizontal 0.9, vertical 0.3, fading from left to right.
Line up 9 blue empty circles radius 0.03 from horizontal 0.1, vertical 0.7 to horizontal 0.9, vertical 0.7, fading from right to left.
Draw one black pen horizontal line at the center.
```

Japanese DDL (reference):

```text
紙。
画面の横0.1、縦0.3から横0.9、縦0.3まで、左から右へ薄れさせて、半径0.03の赤の空の円を9個並べる。
画面の横0.1、縦0.7から横0.9、縦0.7まで、右から左へ薄れさせて、半径0.03の青の空の円を9個並べる。
中心に、黒のペンの水平の線を1個引く。
```

### 5.46. A vertical fade and a diagonal row

Aim: Fade a vertical row from top to bottom, and give a separate diagonal row only alternating colors.

English DDL:

```text
Washi.
Line up 9 red empty circles radius 0.025 from horizontal 0.3, vertical 0.1 to horizontal 0.3, vertical 0.9, fading from top to bottom.
Line up 7 small squares from horizontal 0.5, vertical 0.2 to horizontal 0.85, vertical 0.8, alternating blue and gray.
Draw one black pen half-width horizontal line at the bottom.
```

Japanese DDL (reference):

```text
和紙。
画面の横0.3、縦0.1から横0.3、縦0.9まで、上から下へ薄れさせて、半径0.025の赤の空の円を9個並べる。
画面の横0.5、縦0.2から横0.85、縦0.8まで、青と灰を交互にして、小さな四角を7個並べる。
下に、黒のペンの半幅の水平の線を1個引く。
```

### 5.47. Points fading outward from the center

Aim: Combine the outward fade supported by scatters with a repeating three-color cycle.

English DDL:

```text
Canvas.
Fill the background with black.
Scatter 30 very small points in the whole canvas (horizontal 0 to 1, vertical 0 to 1), repeating red, orange, and yellow in order, fading outward from the center.
Place one small white rotring empty circle at the center.
```

Japanese DDL (reference):

```text
カンバス。
背景を黒で埋める。
画面全体（横0〜1、縦0〜1）に、赤・橙・黄の順に繰り返して、中心から外へ薄れさせて、とても小さな点を30個散らす。
中心に、白のロットリングの空の小さな円を1個置く。
```

### 5.48. Colors that repeat and colors that shift once

Aim: Compare repeating colors with a single shift through the same colors in equal-length rows.

English DDL:

```text
Paper.
Line up 9 empty circles radius 0.03 from horizontal 0.1, vertical 0.3 to horizontal 0.9, vertical 0.3, repeating yellow, orange, and red in order.
Line up 9 empty circles radius 0.03 from horizontal 0.1, vertical 0.7 to horizontal 0.9, vertical 0.7, shifting through yellow, orange, and red in order.
Draw one black pencil horizontal line at the center.
```

Japanese DDL (reference):

```text
紙。
画面の横0.1、縦0.3から横0.9、縦0.3まで、黄・橙・赤の順に繰り返して、半径0.03の空の円を9個並べる。
画面の横0.1、縦0.7から横0.9、縦0.7まで、黄・橙・赤の順に段々に移して、半径0.03の空の円を9個並べる。
中心に、黒の鉛筆の水平の線を1個引く。
```

### 5.49. A color shift and a rotated grid

Aim: Combine a tiled field whose colors shift once with a separate grid at a fixed angle.

English DDL:

```text
Paper.
Tile 6 small squares in the upper band (horizontal 0.1 to 0.9, vertical 0.1 to 0.4), shifting through yellow, orange, and red in order.
Tile 9 small blue empty squares rotated 45 degrees in the lower band (horizontal 0.1 to 0.9, vertical 0.6 to 0.9).
Draw one black fine-brush half-width horizontal line at the center.
```

Japanese DDL (reference):

```text
紙。
上の帯（横0.1〜0.9、縦0.1〜0.4）に、黄・橙・赤の順に段々に移して、小さな四角を6個敷き詰める。
下の帯（横0.1〜0.9、縦0.6〜0.9）に、回転45度の青の空の小さな四角を9個敷き詰める。
中心に、黒の細筆の半幅の水平の線を1個引く。
```

### 5.50. Layer a ground, textures, a row, and a path

Aim: Combine a face in a numeric range, brushmarks, an alternating-color row, and a free line between explicit endpoints.

English DDL:

```text
Washi.
Fill the background with white.
Place one large gray thick-brush faint sweep wide square in the lower band (horizontal 0 to 1, vertical 2/3 to 1).
Place one red thick-brush underpainted fine-grained brushmarks cloudform width 0.35, height 0.2 at horizontal 0.5, vertical 0.35.
Line up 9 empty circles radius 0.025 from horizontal 0.1, vertical 0.7 to horizontal 0.9, vertical 0.7, alternating blue and yellow.
Draw one black fine-brush free line from horizontal 0.15, vertical 0.15 to horizontal 0.85, vertical 0.55.
```

Japanese DDL (reference):

```text
和紙。
背景を白で埋める。
下の帯（横0〜1、縦2/3〜1）に、灰の太筆の薄い刷きの横長の大きな四角を1個置く。
画面の横0.5、縦0.35の位置に、幅0.35、高さ0.2の赤の太筆の下塗りの細かい刷毛目の雲形を1個置く。
画面の横0.1、縦0.7から横0.9、縦0.7まで、青と黄を交互にして、半径0.025の空の円を9個並べる。
画面の横0.15、縦0.15から横0.85、縦0.55まで、黒の細筆の自由線を1個引く。
```
