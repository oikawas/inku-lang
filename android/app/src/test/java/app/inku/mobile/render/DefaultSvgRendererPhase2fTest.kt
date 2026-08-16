package app.inku.mobile.render

import app.inku.mobile.ReferenceCorpus
import app.inku.mobile.data.model.CanvasSize
import app.inku.mobile.data.model.CompatibilityConstants
import app.inku.mobile.pipeline.RenderRequest
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

    private fun renderSvgForReference(key: String): String {
        val indexJson = readReferenceIndex()
        val entry = indexJson.getJSONObject(key)
        val scoreObj = entry.getJSONObject("score")
        // The corpus keeps the seed beside the Score; so does the server.
        val renderSeed = if (entry.isNull("render_seed")) null else entry.getLong("render_seed")
        if (entry.has("wild") && !entry.isNull("wild")) {
            scoreObj.put("render_wild", entry.getBoolean("wild"))
        }

        val canvasOpt = scoreObj.opt("canvas")
        val aspect = when {
            entry.has("canvas_aspect") -> entry.getString("canvas_aspect")
            canvasOpt is String -> canvasOpt
            canvasOpt is JSONObject -> canvasOpt.optString("aspect", "square")
            else -> "square"
        }
        // engine 23: the composition seed travels beside the score, so the
        // corpus keeps it beside the score too. A walk that dropped it would
        // draw the one case that states one at the performance seed's placement
        // and compare it against a picture laid out at another.
        val compositionSeed = if (entry.has("composition_seed") && !entry.isNull("composition_seed")) {
            entry.getLong("composition_seed")
        } else {
            null
        }
        val renderer = DefaultSvgRenderer()
        val result = renderer.render(
            RenderRequest(
                scoreJson = scoreObj.toString(),
                colorCatalogId = "default",
                canvasAspect = aspect,
                svgProfile = "editable",
                renderSeed = renderSeed,
                compositionSeed = compositionSeed,
            )
        )
        return result.svg
    }

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

    private fun countElements(svg: String): Map<String, Int> {
        val counts = mutableMapOf<String, Int>()
        val tags = listOf("path", "circle", "rect", "polygon", "polyline", "line")
        for (tag in tags) {
            val openCount = svg.split("<$tag ").size - 1 + svg.split("<$tag>").size - 1
            if (openCount > 0) counts[tag] = openCount
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

    @Test
    fun test03SquareFilledExactParity() {
        val expectedSvg = readReferenceResource("03_square_filled.svg")
        val actualSvg = renderSvgForReference("03_square_filled")

        val expectedFillPaths = extractGroupPathDList(expectedSvg, "fill-stroke-v1")
        val actualFillPaths = extractGroupPathDList(actualSvg, "fill-stroke-v1")

        assertEquals("fill-stroke-v1 path count for 03_square_filled.svg must match", expectedFillPaths.size, actualFillPaths.size)
        for (i in expectedFillPaths.indices) {
            assertEquals("fill-stroke-v1 path d #$i for 03_square_filled.svg must match", expectedFillPaths[i], actualFillPaths[i])
        }
    }

    @Test
    fun test04ArcCrayonExactParity() {
        val expectedSvg = readReferenceResource("04_arc_crayon.svg")
        val actualSvg = renderSvgForReference("04_arc_crayon")

        val expectedArcPaths = extractGroupPathDList(expectedSvg, "arc-stroke-v1")
        val actualArcPaths = extractGroupPathDList(actualSvg, "arc-stroke-v1")

        assertEquals("arc-stroke-v1 path count for 04_arc_crayon.svg must match", expectedArcPaths.size, actualArcPaths.size)
        for (i in expectedArcPaths.indices) {
            assertEquals("arc-stroke-v1 path d #$i for 04_arc_crayon.svg must match", expectedArcPaths[i], actualArcPaths[i])
        }
    }

    @Test
    fun test06SurfaceHatchExactParity() {
        val expectedSvg = readReferenceResource("06_surface_hatch.svg")
        val actualSvg = renderSvgForReference("06_surface_hatch")

        val expectedHatchPaths = extractGroupPathDList(expectedSvg, "surface-stroke-v1")
        val actualHatchPaths = extractGroupPathDList(actualSvg, "surface-stroke-v1")

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
     */
    @Test
    fun test21HatchComputerExactParity() {
        val expectedSvg = readReferenceResource("21_hatch_computer.svg")
        val actualSvg = renderSvgForReference("21_hatch_computer")

        val expectedHatchPaths = extractGroupPathDList(expectedSvg, "surface-stroke-v1")
        val actualHatchPaths = extractGroupPathDList(actualSvg, "surface-stroke-v1")

        assertEquals("surface-stroke-v1 path count for 21_hatch_computer.svg must match", expectedHatchPaths.size, actualHatchPaths.size)
        assertTrue("21_hatch_computer.svg must hold rows to compare", expectedHatchPaths.isNotEmpty())
        for (i in expectedHatchPaths.indices) {
            assertEquals("surface-stroke-v1 path d #$i for 21_hatch_computer.svg must match", expectedHatchPaths[i], actualHatchPaths[i])
        }
    }

    @Test
    fun test10ArcWaveExactParity() {
        val expectedSvg = readReferenceResource("10_arc_wave.svg")
        val actualSvg = renderSvgForReference("10_arc_wave")

        val expectedArcPaths = extractGroupPathDList(expectedSvg, "arc-stroke-v1")
        val actualArcPaths = extractGroupPathDList(actualSvg, "arc-stroke-v1")

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

    @Test
    fun testAllReferenceSvgStructureParity() {
        val keys = listOf(
            "01_circle_pen", "02_line_brush", "03_square_filled", "04_arc_crayon",
            "05_circle_rotring", "06_surface_hatch", "07_circle_wave", "08_circle_perlin",
            "09_line_white", "10_arc_wave"
        )
        for (key in keys) {
            val expectedSvg = readReferenceResource("$key.svg")
            val actualSvg = renderSvgForReference(key)

            val expectedClasses = extractClassAttrs(expectedSvg)
            val actualClasses = extractClassAttrs(actualSvg)
            assertEquals("Class attributes list for $key.svg must match", expectedClasses, actualClasses)

            val expectedElements = countElements(expectedSvg)
            val actualElements = countElements(actualSvg)
            assertEquals("Element counts map for $key.svg must match", expectedElements, actualElements)
        }
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
