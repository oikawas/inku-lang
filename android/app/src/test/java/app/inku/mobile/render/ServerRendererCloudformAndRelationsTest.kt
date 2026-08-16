package app.inku.mobile.render

import app.inku.mobile.ReferenceCorpus
import app.inku.mobile.data.model.CanvasAspects
import app.inku.mobile.data.model.CanvasSize
import app.inku.mobile.pipeline.RenderRequest
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ServerRendererCloudformAndRelationsTest {

    private fun readResourceText(name: String): String = ReferenceCorpus.text(name)

    private fun readResourceJson(name: String): JSONObject = ReferenceCorpus.json(name)

    @Test
    fun testToolEnergyLateralParity() {
        val json = readResourceJson("renderer_cloudform_and_relations.json")
        val list = json.getJSONArray("tool_energy_lateral")
        for (i in 0 until list.length()) {
            val item = list.getJSONObject(i)
            val weight = item.getString("weight")
            val expectedEnergy = item.getDouble("energy_lateral")
            val expectedTouchGain = item.getDouble("touch_gain")

            val grammar = GRAMMARS[weight]
                ?: throw AssertionError("Missing grammar for weight=$weight")
            assertEquals("energy_lateral mismatch for weight=$weight", expectedEnergy, grammar.energyLateral, 1e-9)
            assertEquals("touch_gain mismatch for weight=$weight", expectedTouchGain, grammar.energyLateral * 0.018, 1e-9)
        }
    }

    @Test
    fun testCloudformSeedParity() {
        val json = readResourceJson("renderer_cloudform_and_relations.json")
        val list = json.getJSONArray("cloudform_seed")
        for (i in 0 until list.length()) {
            val item = list.getJSONObject(i)
            val perfSeed = if (item.has("performance_seed") && !item.isNull("performance_seed")) item.get("performance_seed") else null
            val ii = item.getInt("instruction_index")
            val mi = item.getInt("mark_index")
            val expectedValStr = item.getString("value")

            val seedLong = ServerRendererGeometry.cloudformSeed(perfSeed, ii, mi)
            val actualValStr = seedLong.toULong().toString()
            assertEquals("cloudform_seed mismatch at index=$i", expectedValStr, actualValStr)
        }
    }

    @Test
    fun testBaseRadiusParity() {
        val json = readResourceJson("renderer_cloudform_and_relations.json")
        val list = json.getJSONArray("base_radius")
        val baseRadiusMethod = ServerRendererGeometry::class.java.getDeclaredMethod(
            "baseRadius",
            Double::class.javaPrimitiveType,
            Long::class.javaPrimitiveType,
            JSONObject::class.java,
            String::class.java
        ).apply { isAccessible = true }

        for (i in 0 until list.length()) {
            val item = list.getJSONObject(i)
            val weight = item.getString("weight")
            val seedULongStr = item.getString("seed")
            val seedLong = seedULongStr.toULong().toLong()
            val theta = item.getDouble("theta")
            val expected = item.getDouble("value")

            val actual = baseRadiusMethod.invoke(ServerRendererGeometry, theta, seedLong, null, weight) as Double
            assertEquals("base_radius mismatch for weight=$weight theta=$theta", expected, actual, 1e-9)
        }
    }

    @Test
    fun testBaseRadiusVariedParity() {
        val json = readResourceJson("renderer_cloudform_and_relations.json")
        val list = json.getJSONArray("base_radius_varied")
        val baseRadiusMethod = ServerRendererGeometry::class.java.getDeclaredMethod(
            "baseRadius",
            Double::class.javaPrimitiveType,
            Long::class.javaPrimitiveType,
            JSONObject::class.java,
            String::class.java
        ).apply { isAccessible = true }

        val variedJson = JSONObject("""{"amplitude": "broad", "frequency": "medium", "quality": "wave"}""")

        for (i in 0 until list.length()) {
            val item = list.getJSONObject(i)
            val weight = item.getString("weight")
            val seedULongStr = item.getString("seed")
            val seedLong = seedULongStr.toULong().toLong()
            val theta = item.getDouble("theta")
            val expected = item.getDouble("value")

            val actual = baseRadiusMethod.invoke(ServerRendererGeometry, theta, seedLong, variedJson, weight) as Double
            assertEquals("base_radius_varied mismatch for weight=$weight theta=$theta at index=$i", expected, actual, 1e-9)
        }
    }

    @Test
    fun testCloudformContourParity() {
        val json = readResourceJson("renderer_cloudform_and_relations.json")
        val list = json.getJSONArray("cloudform_contour")
        for (i in 0 until list.length()) {
            val item = list.getJSONObject(i)
            val name = item.optString("case", "case-$i")
            val center = 0.5 to 0.5
            val size = 0.5 to 0.34
            val perfSeed = if (item.has("performance_seed") && !item.isNull("performance_seed")) item.get("performance_seed") else null
            val ii = item.optInt("instruction_index", 0)
            val mi = item.optInt("mark_index", 0)
            val variation = if (item.has("variation") && !item.isNull("variation")) item.getJSONObject("variation") else null
            val weight = item.optString("weight", "pen")
            val pointCount = item.optInt("point_count", 49)
            val expectedPathD = item.getString("path_d")
            val expectedPoints = item.getJSONArray("points")

            val contour = ServerRendererGeometry.generateCloudformContour(
                center = center,
                size = size,
                performanceSeed = perfSeed,
                instructionIndex = ii,
                markIndex = mi,
                variation = variation,
                weight = weight,
                pointCount = pointCount
            )

            assertEquals("Point count mismatch for $name", expectedPoints.length(), contour.points.size)
            for (pIdx in 0 until expectedPoints.length()) {
                val ptArr = expectedPoints.getJSONArray(pIdx)
                val exX = ptArr.getDouble(0)
                val exY = ptArr.getDouble(1)
                assertEquals("Point $pIdx X mismatch for $name", exX, contour.points[pIdx].first, 1e-9)
                assertEquals("Point $pIdx Y mismatch for $name", exY, contour.points[pIdx].second, 1e-9)
            }
            assertEquals("path_d mismatch for $name", expectedPathD, contour.pathD)
        }
    }

    @Test
    fun testMinorArcDeltaParity() {
        val json = readResourceJson("renderer_cloudform_and_relations.json")
        val list = json.getJSONArray("minor_arc_delta")
        for (i in 0 until list.length()) {
            val item = list.getJSONObject(i)
            val start = item.getDouble("angle_start")
            val end = item.getDouble("angle_end")
            val expected = item.getDouble("value")

            val actual = ServerRendererGeometry.minorArcDelta(start, end)
            assertEquals("minor_arc_delta mismatch at index=$i ($start -> $end)", expected, actual, 1e-9)
        }
    }

    @Test
    fun testArcFromEndpointsAndSagittaParity() {
        val json = readResourceJson("renderer_cloudform_and_relations.json")
        val list = json.getJSONArray("arc_from_endpoints_and_sagitta")
        for (i in 0 until list.length()) {
            val item = list.getJSONObject(i)
            val startArr = item.getJSONArray("start")
            val start = startArr.getDouble(0) to startArr.getDouble(1)
            val endArr = item.getJSONArray("end")
            val end = endArr.getDouble(0) to endArr.getDouble(1)
            val sagitta = item.getDouble("sagitta")

            val expectedCenterArr = item.getJSONArray("center")
            val expectedCenter = expectedCenterArr.getDouble(0) to expectedCenterArr.getDouble(1)
            val expectedRadius = item.getDouble("radius")
            val expectedStartAngle = item.getDouble("angle_start")
            val expectedEndAngle = item.getDouble("angle_end")

            val actual = ServerRendererGeometry.arcFromEndpointsAndSagitta(start, end, sagitta)
            assertEquals("center X mismatch at index=$i", expectedCenter.first, actual.center.first, 1e-9)
            assertEquals("center Y mismatch at index=$i", expectedCenter.second, actual.center.second, 1e-9)
            assertEquals("radius mismatch at index=$i", expectedRadius, actual.radius, 1e-9)

            fun normDeg(deg: Double): Double {
                var d = deg % 360.0
                if (d < 0) d += 360.0
                return d
            }
            assertEquals("angle_start mismatch at index=$i", normDeg(expectedStartAngle), normDeg(actual.angleStart), 1e-6)
            assertEquals("angle_end mismatch at index=$i", normDeg(expectedEndAngle), normDeg(actual.angleEnd), 1e-6)
        }
    }

    @Test
    fun testResolvePerformanceScoreParity() {
        val json = readResourceJson("renderer_cloudform_and_relations.json")
        val list = json.getJSONArray("resolve_performance_score")
        val renderer = DefaultSvgRenderer()
        val resolveMethod = DefaultSvgRenderer::class.java.getDeclaredMethod(
            "resolvePerformanceScore",
            JSONArray::class.java,
            java.lang.Long::class.java,
            CanvasSize::class.java,
        ).apply { isAccessible = true }

        for (i in 0 until list.length()) {
            val item = list.getJSONObject(i)
            val name = item.getString("case")
            val scoreIn = item.getJSONObject("score_in")
            val perfSeed = if (item.has("performance_seed") && !item.isNull("performance_seed")) item.getLong("performance_seed") else null
            val expectedScoreOut = item.getJSONObject("score_out")

            val instructionsIn = scoreIn.getJSONArray("instructions")
            val actualResolvedIns = resolveMethod.invoke(
                renderer,
                instructionsIn,
                perfSeed,
                CanvasAspects.sizeFor("square"),
            ) as JSONArray

            val expectedInstructionsOut = expectedScoreOut.getJSONArray("instructions")
            assertEquals("Resolved instruction count mismatch for $name", expectedInstructionsOut.length(), actualResolvedIns.length())

            for (insIdx in 0 until expectedInstructionsOut.length()) {
                val expIns = expectedInstructionsOut.getJSONObject(insIdx)
                val actIns = actualResolvedIns.getJSONObject(insIdx)

                if (expIns.has("center") && !expIns.isNull("center")) {
                    val expC = expIns.getJSONArray("center")
                    val actC = actIns.getJSONArray("center")
                    assertEquals("Center X mismatch for $name ins $insIdx", expC.getDouble(0), actC.getDouble(0), 1e-6)
                    assertEquals("Center Y mismatch for $name ins $insIdx", expC.getDouble(1), actC.getDouble(1), 1e-6)
                }
            }
        }
    }

    @Test
    fun testReferenceSvgParity11To14() {
        val renderer = DefaultSvgRenderer()

        val svg13Ref = readResourceText("13_touching_arcs.svg")
        val svg14Ref = readResourceText("14_region_then_relation.svg")

        val indexJson = readResourceJson("svg_index.json")

        fun renderFromIndexEntry(entryName: String): String {
            val entry = indexJson.getJSONObject(entryName)
            val scoreObj = JSONObject(entry.getJSONObject("score").toString())
            // The corpus keeps the seed beside the Score; so does the server.
            val renderSeed = if (entry.isNull("render_seed")) null else entry.getLong("render_seed")
            return renderer.render(
                RenderRequest(
                    scoreJson = scoreObj.toString(),
                    colorCatalogId = ReferenceRendering.catalogId(entry),
                    canvasAspect = "square",
                    svgProfile = "editable",
                    renderSeed = renderSeed,
                )
            ).svg
        }

        fun extractPathD(svg: String): List<String> {
            return Regex("""\bd="([^"]+)"""").findAll(svg).map { it.groupValues[1] }.toList()
        }

        fun extractClassAttr(svg: String): List<String> {
            return Regex("""\bclass="([^"]+)"""").findAll(svg).map { it.groupValues[1] }.toList()
        }

        val svg13Actual = renderFromIndexEntry("13_touching_arcs")
        println("=== 13_touching_arcs Actual SVG ===")
        println(svg13Actual)
        assertEquals("13_touching_arcs class match", extractClassAttr(svg13Ref), extractClassAttr(svg13Actual))
        assertEquals("13_touching_arcs path d exact match", extractPathD(svg13Ref), extractPathD(svg13Actual))

        val svg14Actual = renderFromIndexEntry("14_region_then_relation")
        assertEquals("14_region_then_relation class match", extractClassAttr(svg14Ref), extractClassAttr(svg14Actual))
        assertEquals("14_region_then_relation path d exact match", extractPathD(svg14Ref), extractPathD(svg14Actual))

        val svg11Ref = readResourceText("11_cloudform_pencil.svg")
        val svg12Ref = readResourceText("12_cloudform_rotring.svg")
        val svg11Actual = renderFromIndexEntry("11_cloudform_pencil")
        val svg12Actual = renderFromIndexEntry("12_cloudform_rotring")

        assertEquals("11_cloudform_pencil class match", extractClassAttr(svg11Ref), extractClassAttr(svg11Actual))
        assertEquals("11_cloudform_pencil path d exact match", extractPathD(svg11Ref), extractPathD(svg11Actual))
        assertEquals("12_cloudform_rotring class match", extractClassAttr(svg12Ref), extractClassAttr(svg12Actual))
        assertEquals("12_cloudform_rotring path d exact match", extractPathD(svg12Ref), extractPathD(svg12Actual))

        assertNotEquals("Pencil and Rotring cloudform SVG bytes must differ", svg11Actual.length, svg12Actual.length)
    }
}
