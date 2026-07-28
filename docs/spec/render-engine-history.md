# Render engine version history

**An index of the performance (drawing) versions alone, newest first, one section per version.**
inku draws the same JSON Score a little differently every time. **The version of *how* it draws
is the render engine version**, counted separately from the product version (`v2.7.8` and so on).
**This document is the way in**; the detail lives where each section points.

**Until this file existed, nowhere held all versions in one place.** The record was spread across
four places — prose in `SPEC.md` (engines 5 through 10), `SPEC.ja.md` §15.9–15.11 (13 through 15),
`server/reference/README.md` (12 and 15), and the changelog entries.

## When the version goes up

`SPEC.ja.md` §15.6 rules it. **There are two reasons.**

1. **The performance changed** — the same Score with the same seed now draws differently
2. **The vocabulary that can be performed grew** — raise it even if not one byte of output moved

**A rename does not raise it.** Conversely, **raising it freezes a reference corpus**: only the SVGs
the version actually moved go into `server/reference/render-engine-<version>/`, while the manifest
carries the digest of every case.

**The block cannot be restored, but the prints can be kept.** Freezing is the proof print that makes
that possible: the **actual output** from a fixed set of inputs (the SVG, its element counts,
classes, and a coordinate digest) is stored, and CI fails if regenerating an existing case is not
byte-identical. When it differs, the drawing changed, and the engine version rises. **A version
number carries only one bit: that something moved. What moved, and how, can only be answered by
comparing the outputs themselves.**

## The versions

**"Moved" and "unchanged" are measured**, from the manifest's `changed_from_previous` and the number
of SVGs the directory holds.

| Version | Product version | Build | Frozen | Cases | Moved | Unchanged |
|---|---|---|---|---|---|---|
| **15** | v2.7.8 (v2.7.12 folded in) | 717 / 721 | 2026-07-27 | 350 | **318** | **32** |
| **14** | v2.7.0 | 709 | 2026-07-25 | 347 | **126** | **221** |
| **13** | v2.6.0 | 707 | 2026-07-25 | 228 | **8** | **220** |
| **12** | v2.5.0 | 706 | 2026-07-25 | 220 | **199** | **21** |
| **11** | v2.4.8 | 698 | 2026-07-24 | 220 | **220** | **0** |
| **10** | frozen by v2.4.4 | 694 | 2026-07-23 | 220 | (first) | — |
| 1–9 | — | — | before freezing | — | — | — |

**What stayed still is what explains the version.** The version where everything moved (11) says,
through its zero unchanged cases, that it changed how numbers are written and not what is drawn.

## engine 15 — remaking the seed and the mark (v2.7.8)

**Five changes landed as one version.** They sit in the same layer, and bumping four times would
have cost four Android follow-ups.

- **A mark's seed is built from an allowlist.** It used to be a hash of the instruction's whole
  dump, so **changing a value that never reaches the drawing still moved the drawing**
- **The ground's seed comes from the support**
- **`cloudform` goes through the hand-drawn path** (it had never entered `stroke_engine`)
- **Angular shapes and `pen` get a material layer**
- **Strength is not distance** — the offset gain of 2.8 and the 3.5px floor are gone

**318 moved, 32 unchanged. The 32 are `computer` and `rotring`** — the mechanical extreme
deliberately skips the performance, so it does not move. **Had those two moved, engine 15 would
have broken the mechanical extreme.**

v2.7.12 (Build 721) folded "the sheet says how it was made" into this version. **It moved 3 of 350.**

Detail: `SPEC.ja.md` §15.11 / "What engine 15 changed" in `server/reference/README.md` /
[changelog v2.7.8](../history/changelog-v1.72-v2.4.md)

## engine 14 — one lattice, and wild arriving (v2.7.0)

- **The quantized grid became one lattice per drawing**
- **Wild reaches contours, arcs, fills and hatches.** In engine 12 it reached only the line
  primitive, so **the description and the implementation disagreed** (circles and squares came out
  byte-identical with it on)

**126 moved, 221 unchanged.** The corpus grew from 228 to 347 cases (the new wild cases).

Detail: `SPEC.ja.md` §15.10 / [changelog v2.7.0](../history/changelog-v1.72-v2.4.md)

## engine 13 — the computer's touch (v2.6.0)

- **Added "computer" as a tool.** Its width and path fall onto fixed steps. **Repeating without
  error** is the core of it
- The repetition does not scatter with the seed; the material layer is straight lines, and every
  dash carries the same value

**8 moved, 220 unchanged. The 8 that moved are the new computer cases themselves** — **not one of
the 220 existing cases moved.** This is the record that adding a tool left the existing
performances alone.

Detail: `SPEC.ja.md` §15.9 / [changelog v2.6.0](../history/changelog-v1.72-v2.4.md)

## engine 12 — de-regularizing the performance, and wild (v2.5.0)

- **The width envelope was a fixed symmetric hump** — every stroke was fattest exactly at its middle
- **The correction event repeated with period 5**
- A closed contour carried a thin seam
- A gesture entered the centre line, and the wild toggle arrived

**199 moved, 21 unchanged. The unchanged are 12 `rotring` cases and 9 `cloudform` cases.**
`rotring` is the mechanical extreme, so that follows; **the 9 `cloudform` cases were still because
they never entered `stroke_engine`**, which was not fixed until engine 15.

Detail: "What engine 12 changed" in `server/reference/README.md` /
[changelog v2.5.0](../history/changelog-v1.72-v2.4.md)

## engine 11 — the master grid (v2.4.8)

- **Every emitted number is declared on one grid** (fixed to six decimal places)

**220 moved, 0 unchanged — everything moved.** The version changed how numbers are written rather
than what is drawn, so that is right. **Which also means that in a version where everything moves,
"what stayed still" explains nothing.** The discipline first did real work in engine 12.

This corpus **cannot be regenerated outside macOS and is excluded from CI** (a 1-ulp libm difference).

Detail: `SPEC.ja.md` §15.6 / [changelog v2.4.8](../history/changelog-v1.72-v2.4.md)

## engine 10 — the first frozen version (frozen by v2.4.4)

**Engine 10's content landed before the freeze.** v2.4.4 (Build 694) is the version that first
**froze the performance of that moment as a 220-case corpus**. Every version after it is explained
as a difference from those 220.

Detail: `SPEC.ja.md` §15.7 / [changelog v2.4.4](../history/changelog-v1.72-v2.4.md)

## engines 1–9 — before the freeze

**With no reference corpus, there is no mechanical answer to "what moved".**
The record is in the changelog archives and in the prose of `SPEC.md`, which states the reason for
each bump inline (the lines in `SPEC.md`: 5 → 301, 6 → 310, 7 → 329, 8 → 347, 10 → 391).

**For this range you can tell that the drawing changed, but not which drawings changed or by how
much.** That the freezing began at engine 10 is itself the reason for the gap.

## How this document is kept

- **Do not hand-write the numbers in the table.** Take them from `changed_from_previous` in
  `server/reference/render-engine-*/manifest.json` and from the number of SVGs in that directory
- **When the version goes up, add a section here.** Every section must say **what stayed still**
- **There are two language versions.** `render-engine-history.ja.md` is the original and the English
  one follows it. `server/scripts/check_docs.py` checks that their headings correspond
