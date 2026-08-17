package app.inku.mobile.render

import app.inku.mobile.ReferenceCorpus
import app.inku.mobile.data.model.CanvasSize
import app.inku.mobile.data.model.CompatibilityConstants
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DefaultSvgRendererPhase2fTest {

    private fun readReferenceResource(filename: String): String = ReferenceCorpus.text(filename)

    private fun readReferenceIndex(): JSONObject {
        return JSONObject(readReferenceResource("svg_index.json"))
    }

    private fun readFillAndArcReference(): JSONObject {
        return JSONObject(readReferenceResource("renderer_fill_and_arc.json"))
    }

    /**
     * The drawing this guard compares against the reference.
     *
     * The seed beside the Score, the `wild` toggle, the canvas aspect, the
     * composition seed (engine 23) and -- since this cycle -- the colour catalog
     * the index declares all live on one road in [ReferenceRendering], which is
     * also where a perturbation can reach them.
     */
    private fun renderSvgForReference(key: String): String = ReferenceRendering.svg(key)

    private fun extractGroupPathDList(svg: String, groupClassPrefix: String): List<String> {
        val result = mutableListOf<String>()
        var searchIdx = 0
        while (true) {
            val groupIdx = svg.indexOf("class=\"$groupClassPrefix", searchIdx)
            if (groupIdx == -1) break
            val groupEndIdx = svg.indexOf("</g>", groupIdx)
            val searchRegion = if (groupEndIdx != -1) svg.substring(groupIdx, groupEndIdx) else svg.substring(groupIdx)
            
            var dIdx = 0
            while (true) {
                val match = searchRegion.indexOf(" d=\"", dIdx)
                if (match == -1) break
                val start = match + 4
                val end = searchRegion.indexOf("\"", start)
                result.add(searchRegion.substring(start, end))
                dIdx = end + 1
            }
            searchIdx = if (groupEndIdx != -1) groupEndIdx + 4 else svg.length
        }
        return result
    }

    private fun extractClassAttrs(svg: String): List<String> {
        val classes = mutableListOf<String>()
        var idx = 0
        while (true) {
            val match = svg.indexOf("class=\"", idx)
            if (match == -1) break
            val start = match + 7
            val end = svg.indexOf("\"", start)
            classes.add(svg.substring(start, end))
            idx = end + 1
        }
        return classes
    }

    /**
     * The element names the corpus itself counts, read out of `svg_index.json`.
     *
     * Written down by hand this list said path, circle, rect, polygon, polyline
     * and line, while the index counts those plus `ellipse` and `g`. The 24
     * ellipses across two drawings were therefore compared by nobody, and a
     * hand-kept list would go blind again the next time the index learns a tag.
     */
    private fun countedTags(index: JSONObject): List<String> {
        val tags = sortedSetOf<String>()
        for (key in index.keys()) {
            val counts = index.getJSONObject(key).getJSONObject("counts")
            for (tag in counts.keys()) tags.add(tag)
        }
        return tags.toList()
    }

    /**
     * The element names compared between the reference and the port.
     *
     * `g` is held back, and only `g`. The reference wraps its marks in named
     * groups (`inku_artboard`, `layer_10_content`, `instruction_000_...`,
     * `mark_000_000_...`) and the port groups differently: measured on this
     * corpus, all 51 drawings disagree on the number of `<g>` and no drawing
     * disagrees on anything else. Comparing it here would not be widening a
     * guard's reach, it would be asserting a divergence this contract is not
     * allowed to fix -- the picture itself is not moved by any of it, since the
     * groups carry no geometry. It is raised for the ledger instead. Every
     * other tag the index counts, `ellipse` included, is compared.
     */
    private fun comparedTags(index: JSONObject): List<String> = countedTags(index).filter { it != "g" }

    private fun countElements(svg: String, tags: List<String>): Map<String, Int> {
        val counts = mutableMapOf<String, Int>()
        for (tag in tags) {
            counts[tag] = svg.split("<$tag ").size - 1 + svg.split("<$tag>").size - 1
        }
        return counts
    }

    @Test
    fun testFillAndArcConstantsAndSeeds() {
        val ref = readFillAndArcReference()
        val seedsRef = ref.getJSONArray("fill_stroke_seed")
        for (i in 0 until seedsRef.length()) {
            val item = seedsRef.getJSONObject(i)
            val seedInput = item.get("seed")
            val index = item.getInt("index")
            val expectedSeedStr = item.optLong("value").toULong().toString()
            val actualSeedLong = ServerRendererGeometry.fillStrokeSeed(seedInput, index)
            val actualSeedStr = actualSeedLong.toULong().toString()
            assertEquals("fill_stroke_seed for seed=$seedInput index=$index must match", expectedSeedStr, actualSeedStr)
        }
    }

    @Test
    fun testScanlineSegmentsReferenceParity() {
        val ref = readFillAndArcReference()
        val scanlinesRef = ref.getJSONArray("scanline_segments")
        for (i in 0 until scanlinesRef.length()) {
            val item = scanlinesRef.getJSONObject(i)
            val contourArr = item.getJSONArray("contour_points")
            val contour = (0 until contourArr.length()).map { idx ->
                val pt = contourArr.getJSONArray(idx)
                pt.getDouble(0) to pt.getDouble(1)
            }
            val angle = item.getDouble("angle")
            val spacing = item.getDouble("spacing")
            val seedInput = item.get("seed")

            val expectedSegs = item.getJSONArray("segments")
            val actualSegs = ServerRendererGeometry.scanlineSegments(contour, angle, spacing, seedInput)

            assertEquals("Segment count for item $i must match", expectedSegs.length(), actualSegs.size)
            for (j in 0 until expectedSegs.length()) {
                val expSeg = expectedSegs.getJSONObject(j)
                val actSeg = actualSegs[j]
                assertEquals("Index for seg $j item $i must match", expSeg.getInt("index"), actSeg.first)
                
                val expP0 = expSeg.getJSONArray("start")
                val expP1 = expSeg.getJSONArray("end")
                assertEquals("p0.x for seg $j item $i", expP0.getDouble(0), actSeg.second.first, 1e-5)
                assertEquals("p0.y for seg $j item $i", expP0.getDouble(1), actSeg.second.second, 1e-5)
                assertEquals("p1.x for seg $j item $i", expP1.getDouble(0), actSeg.third.first, 1e-5)
                assertEquals("p1.y for seg $j item $i", expP1.getDouble(1), actSeg.third.second, 1e-5)
            }
        }
    }

    /**
     * The number of marks a group's own class declares, read out of `marks-N`.
     *
     * Reading the declaration beats writing the number down here: the server
     * writes `marks-` out of the same `points` list it then draws (`class_` in
     * `_fill_texture`, `marks-` in [DefaultSvgRenderer]), so the declaration and
     * the drawing are one quantity and a hand-copied constant would start
     * guarding a stale copy the day the corpus moves. -1 when the group is not
     * in the drawing at all, so an absent group fails the comparison instead of
     * quietly agreeing with an empty extraction.
     */
    private fun declaredMarkCount(svg: String, groupClassPrefix: String): Int {
        val match = Regex("""class="$groupClassPrefix marks-(\d+)"""").find(svg) ?: return -1
        return match.groupValues[1].toInt()
    }

    /**
     * T-244: the fill guard compares a group the reference actually holds, and says
     * how many marks it compared.
     *
     * It used to take `fill-stroke-v1` out of both sides. `03_square_filled.svg`
     * holds no such group -- the drawing is a pen square, and since engine 22 that
     * is an underlay with a rubbed texture on it, not ruled bands -- so both sides
     * came back empty and the guard was green whatever the port wrote. What the
     * reference does hold is `fill-texture-v1 marks-34`.
     *
     * The 34 is not written here; the group's class declares it, and the guard holds
     * the extraction against the declaration. An empty extraction fails, and so does
     * a group whose class says one number while another number of paths sits inside
     * it.
     *
     * The `d` values themselves are also compared corpus-wide, by
     * [testEveryReferenceSvgMatchesOnPathsPointsAndDashes], which walks the whole
     * file in order and never looks at what encloses them. What this adds is the
     * enclosure: that these paths are the ones inside `fill-texture-v1`.
     */
    @Test
    fun test03SquareFilledExactParity() {
        val expectedSvg = readReferenceResource("03_square_filled.svg")
        val actualSvg = renderSvgForReference("03_square_filled")

        val expectedFillPaths = extractGroupPathDList(expectedSvg, "fill-texture-v1")
        val actualFillPaths = extractGroupPathDList(actualSvg, "fill-texture-v1")
        val declaredByReference = declaredMarkCount(expectedSvg, "fill-texture-v1")
        val declaredByPort = declaredMarkCount(actualSvg, "fill-texture-v1")

        assertTrue(
            "03_square_filled.svg must hold fill-texture-v1 marks to compare, found ${expectedFillPaths.size}",
            expectedFillPaths.isNotEmpty(),
        )
        assertEquals(
            "the reference group holds the number of marks its own class declares",
            declaredByReference,
            expectedFillPaths.size,
        )
        assertEquals(
            "fill-texture-v1 path count for 03_square_filled.svg must match",
            expectedFillPaths.size,
            actualFillPaths.size,
        )
        assertEquals(
            "and the port's group must declare that same number",
            declaredByReference,
            declaredByPort,
        )
        for (i in expectedFillPaths.indices) {
            assertEquals("fill-texture-v1 path d #$i for 03_square_filled.svg must match", expectedFillPaths[i], actualFillPaths[i])
        }
    }

    /**
     * T-256: and this guard says how many it compared.
     *
     * Same shape as the fill guard above, and for the same reason: a group taken out
     * of both sides that neither side holds compares nothing and stays green whatever
     * the port writes. What cannot be repeated here is the second half of that guard.
     * `03_square_filled.svg` declares `marks-34`, the count itself, so the extraction
     * can be held against a declaration. This group declares `controls-N events-M`,
     * which counts the stroke's control points and its events, not the paths the
     * group holds -- so there is no number in the class to hold anything against, and
     * writing the count here by hand would be a copy of the reference that goes stale
     * the moment the corpus is rebaked. The claim is therefore the extraction being
     * non-empty and the two sides agreeing, which is what the vacuous case broke.
     */
    @Test
    fun test04ArcCrayonExactParity() {
        val expectedSvg = readReferenceResource("04_arc_crayon.svg")
        val actualSvg = renderSvgForReference("04_arc_crayon")

        val expectedArcPaths = extractGroupPathDList(expectedSvg, "arc-stroke-v1")
        val actualArcPaths = extractGroupPathDList(actualSvg, "arc-stroke-v1")

        assertTrue(
            "04_arc_crayon.svg must hold arc-stroke-v1 marks to compare, found ${expectedArcPaths.size}",
            expectedArcPaths.isNotEmpty(),
        )
        assertEquals("arc-stroke-v1 path count for 04_arc_crayon.svg must match", expectedArcPaths.size, actualArcPaths.size)
        for (i in expectedArcPaths.indices) {
            assertEquals("arc-stroke-v1 path d #$i for 04_arc_crayon.svg must match", expectedArcPaths[i], actualArcPaths[i])
        }
    }

    /**
     * T-256: the hatch guard says how many rows it compared.
     *
     * The rows of this drawing are not one group but one group per row, each spelt
     * `surface-stroke-v1 hatch-spacing-N` -- a spacing, not a count -- so as with
     * the arc there is nothing in the class to hold the extraction against. The
     * extraction being non-empty is the part that matters: it is what the fill guard
     * lacked when both of its sides came back empty.
     */
    @Test
    fun test06SurfaceHatchExactParity() {
        val expectedSvg = readReferenceResource("06_surface_hatch.svg")
        val actualSvg = renderSvgForReference("06_surface_hatch")

        val expectedHatchPaths = extractGroupPathDList(expectedSvg, "surface-stroke-v1")
        val actualHatchPaths = extractGroupPathDList(actualSvg, "surface-stroke-v1")

        assertTrue(
            "06_surface_hatch.svg must hold surface-stroke-v1 rows to compare, found ${expectedHatchPaths.size}",
            expectedHatchPaths.isNotEmpty(),
        )
        assertEquals("surface-stroke-v1 path count for 06_surface_hatch.svg must match", expectedHatchPaths.size, actualHatchPaths.size)
        for (i in expectedHatchPaths.indices) {
            assertEquals("surface-stroke-v1 path d #$i for 06_surface_hatch.svg must match", expectedHatchPaths[i], actualHatchPaths[i])
        }
    }

    /**
     * T-76: the machine's own hatch, compared row by row against the reference.
     *
     * Nothing in this suite looked at this file's rows before. The corpus-wide
     * `d` gate does reach it, but it asserts on the first case that differs and
     * 06 comes first, so a break here was only ever reported as a break there.
     *
     * The contract asks for `<line>` elements and their four coordinates. There
     * are none: `computer` is a hand-stroke weight, so its rows go through the
     * material engine and come out as paths, in the reference as well as here.
     * The rows are therefore compared as paths, which is the stronger reading of
     * the same claim -- it sees the whole travelled row, not just its two ends.
     *
     * T-256: this is the one of the four that already refused an empty extraction.
     * The assertion was written after the count comparison, where the count would
     * have reported the break first; it is stated before it now, so the four guards
     * fail the same way and say the same thing when the group goes missing.
     */
    @Test
    fun test21HatchComputerExactParity() {
        val expectedSvg = readReferenceResource("21_hatch_computer.svg")
        val actualSvg = renderSvgForReference("21_hatch_computer")

        val expectedHatchPaths = extractGroupPathDList(expectedSvg, "surface-stroke-v1")
        val actualHatchPaths = extractGroupPathDList(actualSvg, "surface-stroke-v1")

        assertTrue(
            "21_hatch_computer.svg must hold surface-stroke-v1 rows to compare, found ${expectedHatchPaths.size}",
            expectedHatchPaths.isNotEmpty(),
        )
        assertEquals("surface-stroke-v1 path count for 21_hatch_computer.svg must match", expectedHatchPaths.size, actualHatchPaths.size)
        for (i in expectedHatchPaths.indices) {
            assertEquals("surface-stroke-v1 path d #$i for 21_hatch_computer.svg must match", expectedHatchPaths[i], actualHatchPaths[i])
        }
    }

    /**
     * T-256: the wobbling arc's guard says how many it compared.
     *
     * The thinnest of the four -- this group holds a single path, so an extraction
     * that comes back empty and one that comes back right differ by one element, and
     * without the assertion below the guard would compare nothing and say so nowhere.
     * Its class reads `controls-N events-M`, again a control-point count and not a
     * mark count.
     */
    @Test
    fun test10ArcWaveExactParity() {
        val expectedSvg = readReferenceResource("10_arc_wave.svg")
        val actualSvg = renderSvgForReference("10_arc_wave")

        val expectedArcPaths = extractGroupPathDList(expectedSvg, "arc-stroke-v1")
        val actualArcPaths = extractGroupPathDList(actualSvg, "arc-stroke-v1")

        assertTrue(
            "10_arc_wave.svg must hold arc-stroke-v1 marks to compare, found ${expectedArcPaths.size}",
            expectedArcPaths.isNotEmpty(),
        )
        assertEquals("arc-stroke-v1 path count for 10_arc_wave.svg must match", expectedArcPaths.size, actualArcPaths.size)
        for (i in expectedArcPaths.indices) {
            assertEquals("arc-stroke-v1 path d #$i for 10_arc_wave.svg must match", expectedArcPaths[i], actualArcPaths[i])
        }
    }

    @Test
    fun test05CircleRotringNoStrokeBands() {
        val actualSvg = renderSvgForReference("05_circle_rotring")

        assertFalse("rotring should not produce fill-stroke-v1", actualSvg.contains("fill-stroke-v1"))
        assertFalse("rotring should not produce arc-stroke-v1", actualSvg.contains("arc-stroke-v1"))
        assertFalse("rotring should not produce contour-stroke-v1", actualSvg.contains("contour-stroke-v1"))
    }

    @Test
    fun testArcIntentElementCount() {
        val svg04 = renderSvgForReference("04_arc_crayon")
        val svg10 = renderSvgForReference("10_arc_wave")

        val intent04Count = svg04.split("fill=\"none\" stroke=\"none\"").size - 1 + svg04.split("stroke=\"none\" fill=\"none\"").size - 1
        val intent10Count = svg10.split("fill=\"none\" stroke=\"none\"").size - 1 + svg10.split("stroke=\"none\" fill=\"none\"").size - 1

        assertEquals("04_arc_crayon must have exactly 1 intent element", 1, intent04Count)
        assertEquals("10_arc_wave must have exactly 1 intent element", 1, intent10Count)
    }

    /**
     * T-147: the structure comparison walks every drawing in the index.
     *
     * It used to name ten drawings. The element counts are the only place the
     * arc's powder is measured at all, and ten drawings hold 147 of the corpus's
     * 790 circles, so 643 grains were compared by nobody -- 12.8% of all
     * elements were reached. Neither the count nor any drawing's name is
     * written here: the index decides, so a drawing added to the corpus is
     * walked the day it arrives.
     */
    @Test
    fun testAllReferenceSvgStructureParity() {
        val index = readReferenceIndex()
        val tags = comparedTags(index)
        assertTrue("the index must declare the element names it counts", tags.isNotEmpty())
        assertTrue("the powder the arcs drop must be among them", "circle" in tags)
        assertTrue("and so must the ellipse only two drawings hold", "ellipse" in tags)
        var drawings = 0
        for (key in index.keys()) {
            val expectedSvg = readReferenceResource("$key.svg")
            val actualSvg = renderSvgForReference(key)

            val expectedClasses = extractClassAttrs(expectedSvg)
            val actualClasses = extractClassAttrs(actualSvg)
            assertEquals("Class attributes list for $key.svg must match", expectedClasses, actualClasses)

            val expectedElements = countElements(expectedSvg, tags)
            val actualElements = countElements(actualSvg, tags)
            assertEquals("Element counts map for $key.svg must match", expectedElements, actualElements)
            drawings++
        }
        assertEquals("every drawing in the index must be walked", index.length(), drawings)
    }

    /**
     * T-148: the drawings the guard read are the drawings the index describes.
     *
     * This measures the guard, not the port. [testAllReferenceSvgStructureParity]
     * compares the reference against the port, and would be just as green if the
     * reference resource it loaded were the wrong file or a truncated one -- the
     * two sides would simply agree on less. The index states each drawing's
     * element counts independently of the drawing, so comparing the expected
     * side against them says the guard is reading the picture it thinks it is.
     */
    @Test
    fun testTheExpectedCountsAgreeWithTheIndex() {
        val index = readReferenceIndex()
        val tags = countedTags(index)
        var drawings = 0
        for (key in index.keys()) {
            val declared = index.getJSONObject(key).getJSONObject("counts")
            val counted = countElements(readReferenceResource("$key.svg"), tags)
            for (tag in tags) {
                assertEquals(
                    "$key.svg holds the number of <$tag> its index entry declares",
                    declared.optInt(tag, 0),
                    counted[tag],
                )
            }
            drawings++
        }
        assertEquals("every drawing in the index must be walked", index.length(), drawings)
    }

    @Test
    fun testWildPairingDivergenceAndIdentity() {
        val svg02 = renderSvgForReference("02_line_brush")
        val svg15 = renderSvgForReference("15_line_brush_wild")
        org.junit.Assert.assertNotEquals("15_line_brush_wild must diverge from 02_line_brush", svg02, svg15)

        val svg01 = renderSvgForReference("01_circle_pen")
        val svg16 = renderSvgForReference("16_circle_pen_wild")
        org.junit.Assert.assertNotEquals("16_circle_pen_wild must diverge from 01_circle_pen", svg01, svg16)

        val svg04 = renderSvgForReference("04_arc_crayon")
        val svg22 = renderSvgForReference("22_arc_crayon_wild")
        org.junit.Assert.assertNotEquals("22_arc_crayon_wild must diverge from 04_arc_crayon", svg04, svg22)

        val svg03 = renderSvgForReference("03_square_filled")
        val svg23 = renderSvgForReference("23_square_filled_wild")
        org.junit.Assert.assertNotEquals("23_square_filled_wild must diverge from 03_square_filled", svg03, svg23)

        // engine 15 put cloudform on the shared closed-contour road, so the wild toggle
        // reaches it now. The two frozen references differ; the exemption is down to the
        // machine poles alone (25_line_computer_wild below still matches 17).
        val svg11 = renderSvgForReference("11_cloudform_pencil")
        val svg24 = renderSvgForReference("24_cloudform_pencil_wild")
        org.junit.Assert.assertNotEquals("24_cloudform_pencil_wild must diverge from 11_cloudform_pencil", svg11, svg24)

        val svg17 = renderSvgForReference("17_line_computer")
        val svg25 = renderSvgForReference("25_line_computer_wild")
        org.junit.Assert.assertEquals("25_line_computer_wild must be identical to 17_line_computer", svg17, svg25)
    }

    /**
     * Every polyline whose class begins with material-outline, whichever order
     * the attributes arrive in.
     *
     * The reference sorts its attributes alphabetically (`class` before
     * `points`) and the port writes `points` first, so both readings have to
     * stay. What is new is the prefix: engine 28 split the layer into contact
     * fragments and the class became `material-outline stratum-N`, which the
     * old exact match reached in none of the 51 drawings. The prefix is matched
     * rather than the stratum spelled out, so the day the strata are numbered
     * some other way this does not go blind again.
     */
    private fun extractMaterialOutlinePoints(svg: String): List<String> {
        val result = mutableListOf<String>()
        val regex = Regex("""<polyline[^>]*points="([^"]+)"[^>]*class="material-outline[^"]*"|<polyline[^>]*class="material-outline[^"]*"[^>]*points="([^"]+)"""")
        regex.findAll(svg).forEach { match ->
            val pts = match.groupValues[1].ifEmpty { match.groupValues[2] }
            result.add(pts)
        }
        return result
    }

    /**
     * The same widening as [extractMaterialOutlinePoints], for the dash side.
     *
     * Engine 35 writes no `stroke-dasharray` at all -- engines 21 to 25 held
     * 252 across the corpus, 26 and 27 held 640, and 28 onwards hold none --
     * so this comes back empty from both sides today. It is widened anyway:
     * were it left on the exact match, a port that started writing a dash on a
     * stratum would be caught by the count guard (T-145) as a extraction
     * failure rather than as the divergence it is.
     */
    private fun extractMaterialOutlineDashArrays(svg: String): List<String> {
        val result = mutableListOf<String>()
        val regex = Regex("""<polyline[^>]*stroke-dasharray="([^"]+)"[^>]*class="material-outline[^"]*"|<polyline[^>]*class="material-outline[^"]*"[^>]*stroke-dasharray="([^"]+)"""")
        regex.findAll(svg).forEach { match ->
            val dash = match.groupValues[1].ifEmpty { match.groupValues[2] }
            result.add(dash)
        }
        return result
    }

    @Test
    fun testEveryReferenceSvgMatchesOnPathsPointsAndDashes() {
        val index = readReferenceIndex()
        for (key in index.keys()) {
            val expectedSvg = readReferenceResource("$key.svg")
            val actualSvg = renderSvgForReference(key)
            assertEquals(
                "path d list for $key.svg must match",
                Regex(" d=\"([^\"]*)\"").findAll(expectedSvg).map { it.groupValues[1] }.toList(),
                Regex(" d=\"([^\"]*)\"").findAll(actualSvg).map { it.groupValues[1] }.toList(),
            )
            assertEquals(
                "points list for $key.svg must match",
                Regex(" points=\"([^\"]*)\"").findAll(expectedSvg).map { it.groupValues[1] }.toList(),
                Regex(" points=\"([^\"]*)\"").findAll(actualSvg).map { it.groupValues[1] }.toList(),
            )
            assertEquals(
                "stroke-dasharray list for $key.svg must match",
                Regex(" stroke-dasharray=\"([^\"]*)\"").findAll(expectedSvg).map { it.groupValues[1] }.toList(),
                Regex(" stroke-dasharray=\"([^\"]*)\"").findAll(actualSvg).map { it.groupValues[1] }.toList(),
            )
        }
    }

    /** The drawings whose material layer is compared element by element. */
    private val materialOutlineKeys =
        listOf("02_line_brush", "09_line_white", "14_region_then_relation", "15_line_brush_wild")

    /**
     * The attributes of one element, read one at a time.
     *
     * Deliberately not a second copy of the extraction's regex: this walks the
     * element and reads whatever attributes are on it, so it stays right when
     * the extraction stops matching -- which is the whole point of the count
     * guards below.
     */
    private fun attributeMap(fragment: String): Map<String, String> {
        val attrs = mutableMapOf<String, String>()
        var idx = 0
        while (true) {
            val eq = fragment.indexOf("=\"", idx)
            if (eq == -1) break
            var nameStart = eq
            while (nameStart > 0 && !fragment[nameStart - 1].isWhitespace()) nameStart--
            val valueEnd = fragment.indexOf("\"", eq + 2)
            if (valueEnd == -1) break
            attrs[fragment.substring(nameStart, eq)] = fragment.substring(eq + 2, valueEnd)
            idx = valueEnd + 1
        }
        return attrs
    }

    /**
     * How many material-outline polylines a drawing actually holds, counted by
     * walking the elements rather than by matching the extraction's pattern.
     */
    private fun countMaterialOutlinePolylines(svg: String, requireDash: Boolean = false): Int {
        var idx = 0
        var found = 0
        while (true) {
            val start = svg.indexOf("<polyline", idx)
            if (start == -1) break
            val end = svg.indexOf(">", start)
            if (end == -1) break
            val attrs = attributeMap(svg.substring(start, end))
            val cls = attrs["class"] ?: ""
            if (cls == "material-outline" || cls.startsWith("material-outline ")) {
                if (!requireDash || attrs.containsKey("stroke-dasharray")) found++
            }
            idx = end + 1
        }
        return found
    }

    /**
     * T-143: the guard says how many elements it compared.
     *
     * A guard that only compares two extractions is green when both come back
     * empty, and that is exactly what happened here from engine 28 until this
     * cycle: the parity test below names four drawings and compared not one
     * byte of any of them. So the extraction is now measured against the number
     * of material-outline polylines the drawing really holds, counted by
     * walking the elements -- a way of counting that cannot fail in the same
     * direction as the pattern it is checking.
     *
     * The numbers themselves (42, 40, 50, 60 in engine 35) are deliberately not
     * written down: a hand-copied count is green the day after the corpus moves
     * and goes on guarding the stale figure.
     */
    @Test
    fun testTheMaterialOutlineGuardSaysHowManyItCompared() {
        for (key in materialOutlineKeys) {
            val expectedSvg = readReferenceResource("$key.svg")
            val actualSvg = renderSvgForReference(key)

            val expectedPresent = countMaterialOutlinePolylines(expectedSvg)
            assertTrue("$key.svg must hold material outlines worth comparing", expectedPresent > 0)
            assertEquals(
                "the guard must reach every material outline the reference holds for $key.svg",
                expectedPresent,
                extractMaterialOutlinePoints(expectedSvg).size,
            )

            val actualPresent = countMaterialOutlinePolylines(actualSvg)
            assertTrue("the port must draw material outlines for $key.svg", actualPresent > 0)
            assertEquals(
                "the guard must reach every material outline the port draws for $key.svg",
                actualPresent,
                extractMaterialOutlinePoints(actualSvg).size,
            )
        }
    }

    /**
     * T-145: the same claim for the dash side.
     *
     * Both sides are zero in engine 35 and that is today's right answer, not a
     * hole: the corpus held 252 dasharrays in engines 21 to 25 and 640 in 26
     * and 27, and none since 28. The gate is here for the day a dash comes
     * back, and it is stated as a relation between two counts so it needs no
     * number of its own to stay true across that day.
     *
     * No single perturbation can redden it while the corpus holds no dash: the
     * extraction and the walk both answer zero, and breaking either leaves
     * 0 == 0. It goes red when a dash exists and the extraction misses it,
     * which takes two changes at once.
     */
    @Test
    fun testTheMaterialOutlineDashGuardSaysHowManyItCompared() {
        for (key in materialOutlineKeys) {
            val expectedSvg = readReferenceResource("$key.svg")
            val actualSvg = renderSvgForReference(key)

            assertEquals(
                "the dash guard must reach every dashed material outline the reference holds for $key.svg",
                countMaterialOutlinePolylines(expectedSvg, requireDash = true),
                extractMaterialOutlineDashArrays(expectedSvg).size,
            )
            assertEquals(
                "the dash guard must reach every dashed material outline the port draws for $key.svg",
                countMaterialOutlinePolylines(actualSvg, requireDash = true),
                extractMaterialOutlineDashArrays(actualSvg).size,
            )
        }
    }

    /**
     * T-146: neither the corpus nor the port writes a `stroke-dasharray`.
     *
     * This states the asymmetry rather than hiding it. The corpus-wide dash
     * comparison in [testEveryReferenceSvgMatchesOnPathsPointsAndDashes] is
     * empty against empty on all 51 drawings, so the direction "the port drops
     * a dash the reference has" is dead. The other direction is alive -- a port
     * that wrote one extra dash would break the comparison -- and this says so
     * in one place instead of leaving it to be re-derived.
     *
     * The claim is tied to the render engine version. It has to be measured
     * again in the cycle that raises `renderEngineVersion`.
     */
    @Test
    fun testTheCorpusAndThePortBothHoldNoDashArray() {
        val index = readReferenceIndex()
        var drawings = 0
        for (key in index.keys()) {
            val expectedSvg = readReferenceResource("$key.svg")
            val actualSvg = renderSvgForReference(key)
            assertEquals(
                "engine ${CompatibilityConstants.renderEngineVersion}'s $key.svg must hold no stroke-dasharray",
                0,
                expectedSvg.split("stroke-dasharray").size - 1,
            )
            assertEquals(
                "the port must not write a stroke-dasharray for $key that the reference does not have",
                0,
                actualSvg.split("stroke-dasharray").size - 1,
            )
            drawings++
        }
        assertEquals("every drawing in the index must be walked", index.length(), drawings)
    }

    @Test
    fun testMaterialOutlinePointsAndDashArrayExactParity() {
        for (key in materialOutlineKeys) {
            val expectedSvg = readReferenceResource("$key.svg")
            val actualSvg = renderSvgForReference(key)

            val expectedPoints = extractMaterialOutlinePoints(expectedSvg)
            val actualPoints = extractMaterialOutlinePoints(actualSvg)
            assertEquals(
                "Material outline element count for $key.svg must match exact reference",
                expectedPoints.size,
                actualPoints.size,
            )
            for (i in expectedPoints.indices) {
                assertEquals(
                    "Material outline points #$i for $key.svg must match exact reference",
                    expectedPoints[i],
                    actualPoints[i],
                )
            }

            val expectedDashes = extractMaterialOutlineDashArrays(expectedSvg)
            val actualDashes = extractMaterialOutlineDashArrays(actualSvg)
            assertEquals("Material outline dasharrays list for $key.svg must match exact reference", expectedDashes, actualDashes)
        }
    }

    @Test
    fun testComputerRasterBleedLatticeParity() {
        val keys = listOf("17_line_computer", "18_line_computer_short", "19_circle_computer", "20_line_computer_wide", "21_hatch_computer")
        val regexRect = Regex("""<rect x="([^"]+)" y="([^"]+)" width="([^"]+)" height="([^"]+)"[^>]*class="raster-bleed"/>""")
        for (key in keys) {
            val svg = renderSvgForReference(key)
            val matches = regexRect.findAll(svg).toList()
            assertTrue("raster-bleed cells in $key.svg must not be empty", matches.isNotEmpty())
            for (m in matches) {
                val x = m.groupValues[1].toDouble()
                val y = m.groupValues[2].toDouble()
                val w = m.groupValues[3].toDouble()
                val h = m.groupValues[4].toDouble()
                val step = w
                assertEquals("cell width must equal height in $key.svg", w, h, 1e-6)
                val cx = x + step / 2.0
                val cy = y + step / 2.0
                val modX = Math.abs(cx % step)
                val modY = Math.abs(cy % step)
                assertTrue("cx mod step must be 0 for $key.svg at cx=$cx, step=$step", modX < 1e-5 || Math.abs(modX - step) < 1e-5)
                assertTrue("cy mod step must be 0 for $key.svg at cy=$cy, step=$step", modY < 1e-5 || Math.abs(modY - step) < 1e-5)
                if (key == "20_line_computer_wide") {
                    assertEquals("20_line_computer_wide step must be 18.0", 18.0, step, 1e-6)
                }
            }
        }
    }

    @Test
    fun testArrangementExactParity() {
        val arrRefStr = readReferenceResource("renderer_arrangement.json")
        val arrRefObj = JSONObject(arrRefStr)
        val renderSeed = arrRefObj.getLong("render_seed")
        val cases = arrRefObj.getJSONArray("cases")

        val renderer = DefaultSvgRenderer()
        var gridRegionEdgeAnchorInRegion = false
        var gridEdgeAnchorInRegion = false

        for (i in 0 until cases.length()) {
            val caseObj = cases.getJSONObject(i)
            val caseId = caseObj.getString("case_id")
            val ins = caseObj.getJSONObject("instruction")
            val expectedCount = caseObj.getInt("count")
            val expectedAnchors = caseObj.getJSONArray("anchors")
            // The placement seed is the composition seed's when the case states
            // one, and the render seed's when it does not -- read with "is it
            // stated", never with a falsy test, because 0 is a seed a caller can
            // legitimately give.
            val placementSeed = if (caseObj.has("composition_seed") && !caseObj.isNull("composition_seed")) {
                caseObj.getLong("composition_seed")
            } else {
                renderSeed
            }

            val expanded = renderer.expandArrangement(ins, placementSeed, null, renderSeed)

            assertEquals("Case $caseId count must match", expectedCount, expanded.size)

            // The renderer's own `anchor`, not a second reading of the same
            // rule: the expected values come from the server's `_anchor`, so
            // comparing against the production one is still a real gate, and a
            // copy here would drift. The copy this replaced knew only about
            // `circle` and `line` and answered (0.5, 0.5) for everything else,
            // which was right for every group the corpus held until the angle
            // cases arrived and silently wrong the day they did.
            val actualAnchors = expanded.map { mark ->
                val (ax, ay) = renderer.anchor(mark)
                listOf(ax, ay)
            }

            assertEquals("Case $caseId anchors count must match", expectedAnchors.length(), actualAnchors.size)
            for (j in 0 until expectedAnchors.length()) {
                val expPt = expectedAnchors.getJSONArray(j)
                val actPt = actualAnchors[j]
                assertEquals("Case $caseId mark $j x must match exactly", expPt.getDouble(0), actPt[0], 0.0)
                assertEquals("Case $caseId mark $j y must match exactly", expPt.getDouble(1), actPt[1], 0.0)
            }

            if (caseId == "G-grid-region-edge") {
                val allInRegion = actualAnchors.all { (x, y) -> x in 0.55..0.95 && y in 0.05..0.45 }
                gridRegionEdgeAnchorInRegion = allInRegion
            }
            if (caseId == "G-grid-edge") {
                val allInRegion = actualAnchors.all { (x, y) -> x in 0.55..0.95 && y in 0.05..0.45 }
                gridEdgeAnchorInRegion = allInRegion
            }
        }

        assertTrue("G-grid-region-edge anchors must stay inside declared region", gridRegionEdgeAnchorInRegion)
        assertFalse("G-grid-edge anchors must not stay inside declared region of grid-region-edge", gridEdgeAnchorInRegion)
    }
}
