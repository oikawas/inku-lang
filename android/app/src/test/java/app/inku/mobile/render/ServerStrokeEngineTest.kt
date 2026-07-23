package app.inku.mobile.render

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ServerStrokeEngineTest {

    private fun readResource(name: String): String {
        val stream = javaClass.getResourceAsStream("/server_reference/$name")
            ?: error("Resource /server_reference/$name not found")
        return stream.bufferedReader().use { it.readText() }
    }

    @Test
    fun testPrimitivesParity() {
        val root = JSONObject(readResource("stroke_engine_primitives.json"))

        // 1. Grammars
        val grammarsObj = root.getJSONObject("grammars")
        assertEquals(GRAMMARS.size, grammarsObj.length())
        for (weight in GRAMMARS.keys) {
            val expected = grammarsObj.getJSONObject(weight)
            val actual = GRAMMARS[weight] ?: error("Missing grammar for $weight")
            assertEquals("stiffness for $weight", expected.getDouble("stiffness"), actual.stiffness, 1e-12)
            assertEquals("damping for $weight", expected.getDouble("damping"), actual.damping, 1e-12)
            assertEquals("energy_width for $weight", expected.getDouble("energy_width"), actual.energyWidth, 1e-12)
            assertEquals("energy_lateral for $weight", expected.getDouble("energy_lateral"), actual.energyLateral, 1e-12)
            assertEquals("event_rate for $weight", expected.getDouble("event_rate"), actual.eventRate, 1e-12)
            assertEquals("taper for $weight", expected.getDouble("taper"), actual.taper, 1e-12)
            assertEquals("bulge for $weight", expected.getDouble("bulge"), actual.bulge, 1e-12)
        }

        // 2. Closed envelope floor
        assertEquals(CLOSED_ENVELOPE_FLOOR, root.getDouble("closed_envelope_floor"), 1e-12)

        // 3. Unit hash (56 cases)
        val unitArr = root.getJSONArray("unit")
        assertEquals(56, unitArr.length())
        for (i in 0 until unitArr.length()) {
            val item = unitArr.getJSONObject(i)
            val seed = item.getLong("seed")
            val label = item.getString("label")
            val index = item.getInt("index")
            val expected = item.getDouble("value")
            val actual = ServerStrokeEngine.unitHash(seed, label, index)
            assertEquals("unitHash mismatch for seed=$seed label=$label index=$index", expected, actual, 1e-12)
        }

        // 4. Smooth noise (24 cases)
        val smoothArr = root.getJSONArray("smooth_noise")
        assertEquals(24, smoothArr.length())
        for (i in 0 until smoothArr.length()) {
            val item = smoothArr.getJSONObject(i)
            val t = item.getDouble("t")
            val seed = item.getLong("seed")
            val octave = item.getInt("octave")
            val expected = item.getDouble("value")
            val actual = ServerStrokeEngine.smoothNoise(t, seed, octave)
            assertEquals("smoothNoise mismatch for t=$t seed=$seed octave=$octave", expected, actual, 1e-12)
        }

        // 5. Event map (16 cases)
        val eventArr = root.getJSONArray("event_map")
        assertEquals(16, eventArr.length())
        for (i in 0 until eventArr.length()) {
            val item = eventArr.getJSONObject(i)
            val seed = item.getLong("seed")
            val rate = item.getDouble("rate")
            val count = item.getInt("count")
            val expectedEventsArr = item.getJSONArray("events")
            val actualEventsMap = ServerStrokeEngine.eventMap(seed, rate, count)

            assertEquals("event count mismatch for case $i", expectedEventsArr.length(), actualEventsMap.size)
            for (j in 0 until expectedEventsArr.length()) {
                val ev = expectedEventsArr.getJSONObject(j)
                val idx = ev.getInt("index")
                val kind = ev.getString("kind")
                assertEquals("event kind mismatch at index $idx for case $i", kind, actualEventsMap[idx])
            }
        }

        // 6. Centerline normals & arc length parameters (3 cases)
        val centerlineArr = root.getJSONArray("centerline")
        assertEquals(3, centerlineArr.length())
        for (i in 0 until centerlineArr.length()) {
            val item = centerlineArr.getJSONObject(i)
            val name = item.getString("name")
            val closed = item.getBoolean("closed")
            val ptsArr = item.getJSONArray("points")
            val pts = mutableListOf<Pair<Double, Double>>()
            for (j in 0 until ptsArr.length()) {
                val pt = ptsArr.getJSONArray(j)
                pts.add(Pair(pt.getDouble(0), pt.getDouble(1)))
            }

            val expectedNormals = item.getJSONArray("normals")
            val actualNormals = ServerStrokeEngine.centerlineNormals(pts, closed)
            assertEquals("normals count mismatch for $name", expectedNormals.length(), actualNormals.size)
            for (j in actualNormals.indices) {
                val exp = expectedNormals.getJSONArray(j)
                assertEquals("normal X mismatch for $name at $j", exp.getDouble(0), actualNormals[j].first, 1e-12)
                assertEquals("normal Y mismatch for $name at $j", exp.getDouble(1), actualNormals[j].second, 1e-12)
            }

            val expectedArc = item.getJSONArray("arc_length_parameters")
            val actualArc = ServerStrokeEngine.arcLengthParameters(pts, closed)
            assertEquals("arc length count mismatch for $name", expectedArc.length(), actualArc.size)
            for (j in actualArc.indices) {
                assertEquals("arc length mismatch for $name at $j", expectedArc.getDouble(j), actualArc[j], 1e-12)
            }
        }
    }

    @Test
    fun testLatentEnergyParity() {
        val root = JSONArray(readResource("stroke_engine_latent_energy.json"))
        assertEquals(3, root.length())
        for (i in 0 until root.length()) {
            val item = root.getJSONObject(i)
            val seed = item.getLong("seed")
            val samplesArr = item.getJSONArray("samples")
            assertEquals(21, samplesArr.length())
            for (j in 0 until samplesArr.length()) {
                val t = j / 20.0
                val expected = samplesArr.getDouble(j)
                val actual = ServerStrokeEngine.latentEnergy(t, seed)
                assertEquals("latentEnergy mismatch for seed=$seed t=$t", expected, actual, 1e-6)
            }
        }
    }

    @Test
    fun testSynthesizeStrokeParity() {
        val root = JSONArray(readResource("stroke_engine_synthesize_stroke.json"))
        assertEquals(9, root.length())
        for (caseIdx in 0 until root.length()) {
            val caseObj = root.getJSONObject(caseIdx)
            val name = caseObj.getString("name")
            val input = caseObj.getJSONObject("input")

            val startArr = input.getJSONArray("start")
            val start = Pair(startArr.getDouble(0), startArr.getDouble(1))
            val endArr = input.getJSONArray("end")
            val end = Pair(endArr.getDouble(0), endArr.getDouble(1))
            val baseWidth = input.getDouble("base_width")
            val weight = input.getString("weight")
            val seed = input.getLong("seed")
            val samplesCount = input.getInt("samples")

            val result = ServerStrokeEngine.synthesizeStroke(start, end, baseWidth, weight, seed, samplesCount)

            // Samples check
            val expectedSamples = caseObj.getJSONArray("samples")
            assertEquals("samples size for $name", expectedSamples.length(), result.samples.size)
            for (sIdx in result.samples.indices) {
                val expS = expectedSamples.getJSONObject(sIdx)
                val actS = result.samples[sIdx]
                assertEquals("sample $sIdx t for $name", expS.getDouble("t"), actS.t, 1e-6)
                assertEquals("sample $sIdx x for $name", expS.getDouble("x"), actS.x, 1e-6)
                assertEquals("sample $sIdx y for $name", expS.getDouble("y"), actS.y, 1e-6)
                assertEquals("sample $sIdx width for $name", expS.getDouble("width"), actS.width, 1e-6)
                assertEquals("sample $sIdx energy for $name", expS.getDouble("energy"), actS.energy, 1e-6)
                assertEquals("sample $sIdx lateral for $name", expS.getDouble("lateral"), actS.lateral, 1e-6)
                if (expS.isNull("event")) {
                    assertNull("sample $sIdx event for $name should be null", actS.event)
                } else {
                    assertEquals("sample $sIdx event for $name", expS.getString("event"), actS.event)
                }
            }

            // Outline check
            val expectedOutline = caseObj.getJSONArray("outline")
            assertEquals("outline size for $name", expectedOutline.length(), result.outline.size)
            for (oIdx in result.outline.indices) {
                val expPt = expectedOutline.getJSONArray(oIdx)
                val actPt = result.outline[oIdx]
                assertEquals("outline $oIdx X for $name", expPt.getDouble(0), actPt.first, 1e-6)
                assertEquals("outline $oIdx Y for $name", expPt.getDouble(1), actPt.second, 1e-6)
            }

            assertEquals("event_count for $name", caseObj.getInt("event_count"), result.eventCount)
            assertEquals("burr_side for $name", caseObj.getInt("burr_side"), result.burrSide)
            assertEquals("burr_opacity for $name", caseObj.getDouble("burr_opacity"), result.burrOpacity, 1e-9)
            assertEquals("path_d for $name", caseObj.getString("path_d"), ServerStrokeEngine.polygonPath(result.outline))
        }
    }

    @Test
    fun testSynthesizeAlongParity() {
        val root = JSONArray(readResource("stroke_engine_synthesize_along.json"))
        assertEquals(5, root.length())
        for (caseIdx in 0 until root.length()) {
            val caseObj = root.getJSONObject(caseIdx)
            val name = caseObj.getString("name")
            val input = caseObj.getJSONObject("input")

            val centerlineArr = input.getJSONArray("centerline")
            val centerline = mutableListOf<Pair<Double, Double>>()
            for (i in 0 until centerlineArr.length()) {
                val pt = centerlineArr.getJSONArray(i)
                centerline.add(Pair(pt.getDouble(0), pt.getDouble(1)))
            }

            val baseWidth = input.getDouble("base_width")
            val weight = input.getString("weight")
            val seed = input.getLong("seed")
            val closed = input.getBoolean("closed")
            val anchorsArr = input.getJSONArray("anchors")
            val anchors = mutableSetOf<Int>()
            for (i in 0 until anchorsArr.length()) {
                anchors.add(anchorsArr.getInt(i))
            }

            val result = ServerStrokeEngine.synthesizeAlong(centerline, baseWidth, weight, seed, closed, anchors)

            // Samples check
            val expectedSamples = caseObj.getJSONArray("samples")
            assertEquals("samples size for $name", expectedSamples.length(), result.samples.size)
            for (sIdx in result.samples.indices) {
                val expS = expectedSamples.getJSONObject(sIdx)
                val actS = result.samples[sIdx]
                assertEquals("sample $sIdx t for $name", expS.getDouble("t"), actS.t, 1e-4)
                assertEquals("sample $sIdx x for $name", expS.getDouble("x"), actS.x, 1e-4)
                assertEquals("sample $sIdx y for $name", expS.getDouble("y"), actS.y, 1e-4)
                assertEquals("sample $sIdx width for $name", expS.getDouble("width"), actS.width, 1e-4)
                assertEquals("sample $sIdx energy for $name", expS.getDouble("energy"), actS.energy, 1e-4)
                assertEquals("sample $sIdx lateral for $name", expS.getDouble("lateral"), actS.lateral, 1e-4)
                if (expS.isNull("event")) {
                    assertNull("sample $sIdx event for $name should be null", actS.event)
                } else {
                    assertEquals("sample $sIdx event for $name", expS.getString("event"), actS.event)
                }
            }

            // Left bank check
            val expectedLeft = caseObj.getJSONArray("left")
            assertEquals("left bank size for $name", expectedLeft.length(), result.left.size)
            for (lIdx in result.left.indices) {
                val expPt = expectedLeft.getJSONArray(lIdx)
                val actPt = result.left[lIdx]
                assertEquals("left $lIdx X for $name", expPt.getDouble(0), actPt.first, 1e-4)
                assertEquals("left $lIdx Y for $name", expPt.getDouble(1), actPt.second, 1e-4)
            }

            // Right bank check
            val expectedRight = caseObj.getJSONArray("right")
            assertEquals("right bank size for $name", expectedRight.length(), result.right.size)
            for (rIdx in result.right.indices) {
                val expPt = expectedRight.getJSONArray(rIdx)
                val actPt = result.right[rIdx]
                assertEquals("right $rIdx X for $name", expPt.getDouble(0), actPt.first, 1e-4)
                assertEquals("right $rIdx Y for $name", expPt.getDouble(1), actPt.second, 1e-4)
            }

            assertEquals("event_count for $name", caseObj.getInt("event_count"), result.eventCount)
            assertEquals("burr_side for $name", caseObj.getInt("burr_side"), result.burrSide)
            assertEquals("burr_opacity for $name", caseObj.getDouble("burr_opacity"), result.burrOpacity, 1e-9)
            assertEquals("path_d for $name", caseObj.getString("path_d"), ServerStrokeEngine.contourStrokePath(result))
        }
    }
}
