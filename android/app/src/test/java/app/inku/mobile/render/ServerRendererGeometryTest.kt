package app.inku.mobile.render

import app.inku.mobile.ReferenceCorpus
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ServerRendererGeometryTest {

    @Test
    fun testWavePhaseIsSeedDependent() {
        val seed1 = 111
        val seed2 = 222

        val phase1 = ServerRendererGeometry.wavePhase(seed1)
        val phase2 = ServerRendererGeometry.wavePhase(seed2)

        // Wave phase should be in range [0, 2pi)
        assertTrue("phase1 should be >= 0", phase1 >= 0.0)
        assertTrue("phase1 should be < 2pi", phase1 < 2.0 * Math.PI)
        assertTrue("phase2 should be >= 0", phase2 >= 0.0)
        assertTrue("phase2 should be < 2pi", phase2 < 2.0 * Math.PI)

        // Phase must differ between different seeds
        assertNotEquals("Wave phase must depend on seed", phase1, phase2, 1e-4)

        // Phase must be deterministic for the same seed
        assertEquals("Wave phase must be deterministic for same seed", phase1, ServerRendererGeometry.wavePhase(seed1), 1e-9)
    }

    @Test
    fun testWaveSampleOffsetDependsOnSeed() {
        val variation = JSONObject()
            .put("amplitude", "medium")
            .put("frequency", "medium")
            .put("quality", "wave")
            .put("dimensions", JSONArray().put("position_x").put("position_y"))

        val seed1 = 101
        val seed2 = 202
        val t = 0.25
        val segment = 1
        val amp = ServerRendererGeometry.amplitudePx(variation, JSONObject(), 1000.0, 1000.0, 1000.0)

        val offset1 = ServerRendererGeometry.sampleOffset(t, variation, seed1, segment, amp)
        val offset2 = ServerRendererGeometry.sampleOffset(t, variation, seed2, segment, amp)

        // Wave offset at t=0.25 must differ between seeds due to phase shift
        assertNotEquals("Wave offset must differ across different seeds at t=$t", offset1, offset2, 1e-4)

        // Determinism check for same seed
        assertEquals("Wave offset must be deterministic", offset1, ServerRendererGeometry.sampleOffset(t, variation, seed1, segment, amp), 1e-9)
    }

    @Test
    fun testVariedCirclePointsDeterminismAndVariation() {
        val variation = JSONObject()
            .put("amplitude", "medium")
            .put("frequency", "medium")
            .put("quality", "wave")
            .put("dimensions", JSONArray().put("position_x").put("position_y"))

        val cx = 500.0
        val cy = 500.0
        val r = 200.0
        val seed1 = 12345
        val seed2 = 67890

        val pts1 = ServerRendererGeometry.variedCirclePoints(cx, cy, r, r, variation, seed1, count = 30)
        val pts2 = ServerRendererGeometry.variedCirclePoints(cx, cy, r, r, variation, seed2, count = 30)
        val ptsDeterministic = ServerRendererGeometry.variedCirclePoints(cx, cy, r, r, variation, seed1, count = 30)

        // 1. Same seed must produce exact same points
        assertEquals(pts1.size, ptsDeterministic.size)
        for (i in pts1.indices) {
            assertEquals("Point $i X match", pts1[i].first, ptsDeterministic[i].first, 1e-9)
            assertEquals("Point $i Y match", pts1[i].second, ptsDeterministic[i].second, 1e-9)
        }

        // 2. Different seeds must produce different points
        var maxDiff = 0.0
        for (i in pts1.indices) {
            val dx = pts1[i].first - pts2[i].first
            val dy = pts1[i].second - pts2[i].second
            val diff = kotlin.math.hypot(dx, dy)
            if (diff > maxDiff) maxDiff = diff
        }
        assertTrue("Different seeds should yield varied circle geometry", maxDiff > 0.1)
    }

    /** The varied arc is a run of points now, the way the server writes it -- the
     * `d` string this used to read went away with `variedArcPathD`. */
    @Test
    fun testVariedArcPointsGeneration() {
        val variation = JSONObject()
            .put("amplitude", "fine")
            .put("frequency", "high")
            .put("quality", "perlin")
            .put("dimensions", JSONArray().put("position_x").put("position_y"))

        val pts1 = ServerRendererGeometry.variedArcPoints(500.0, 500.0, 180.0, 20.0, 300.0, variation, 12345)
        val pts2 = ServerRendererGeometry.variedArcPoints(500.0, 500.0, 180.0, 20.0, 300.0, variation, 12345)
        val ptsOtherSeed = ServerRendererGeometry.variedArcPoints(500.0, 500.0, 180.0, 20.0, 300.0, variation, 99999)

        assertTrue("An arc must be sampled at more than its two ends", pts1.size > 2)
        assertEquals("Points must be deterministic for same seed", pts1, pts2)
        assertNotEquals("Points should differ for different seeds", pts1, ptsOtherSeed)
    }

    @Test
    fun testReferencePrimitivesExactParity() {
        val root = ReferenceCorpus.json("renderer_variation_primitives.json")

        // 1. Frequency cycles
        val freqObj = root.getJSONObject("frequency_cycles")
        assertEquals(2.0, ServerRendererGeometry.getFrequencyCycles(JSONObject().put("frequency", "slow")), 1e-9)
        assertEquals(6.0, ServerRendererGeometry.getFrequencyCycles(JSONObject().put("frequency", "medium")), 1e-9)
        assertEquals(14.0, ServerRendererGeometry.getFrequencyCycles(JSONObject().put("frequency", "high")), 1e-9)
        assertEquals(2.0, freqObj.getDouble("slow"), 1e-9)
        assertEquals(6.0, freqObj.getDouble("medium"), 1e-9)
        assertEquals(14.0, freqObj.getDouble("high"), 1e-9)

        // 2. Wave phase
        val wavePhaseArr = root.getJSONArray("wave_phase")
        for (i in 0 until wavePhaseArr.length()) {
            val item = wavePhaseArr.getJSONObject(i)
            val seed = item.getInt("seed")
            val expected = item.getDouble("value")
            assertEquals("wave_phase mismatch for seed $seed", expected, ServerRendererGeometry.wavePhase(seed), 1e-9)
        }

        // 3. hash01
        val hash01Arr = root.getJSONArray("hash01")
        for (i in 0 until hash01Arr.length()) {
            val item = hash01Arr.getJSONObject(i)
            val idx = item.getInt("i")
            val seed = item.getInt("seed")
            val salt = item.getString("salt")
            val expected = item.getDouble("value")
            val actual = ServerRendererGeometry.hash01(idx, seed, salt)
            assertEquals("hash01 mismatch for ($idx, $seed, $salt)", expected, actual, 1e-9)
        }

        // 4. hash_to_unit
        val hashToUnitArr = root.getJSONArray("hash_to_unit")
        for (i in 0 until hashToUnitArr.length()) {
            val item = hashToUnitArr.getJSONObject(i)
            val idx = item.getInt("i")
            val seed = item.getInt("seed")
            val expected = item.getDouble("value")
            assertEquals("hashToUnit mismatch for ($idx, $seed)", expected, ServerRendererGeometry.hashToUnit(idx, seed), 1e-9)
        }

        // 5. value_noise_1d
        val valueNoiseArr = root.getJSONArray("value_noise_1d")
        for (i in 0 until valueNoiseArr.length()) {
            val item = valueNoiseArr.getJSONObject(i)
            val x = item.getDouble("x")
            val seed = item.getInt("seed")
            val expected = item.getDouble("value")
            assertEquals("valueNoise1D mismatch for ($x, $seed)", expected, ServerRendererGeometry.valueNoise1D(x, seed), 1e-9)
        }

        // 6. periodic_value_noise_1d
        val periodicNoiseArr = root.getJSONArray("periodic_value_noise_1d")
        for (i in 0 until periodicNoiseArr.length()) {
            val item = periodicNoiseArr.getJSONObject(i)
            val x = item.getDouble("x")
            val seed = item.getInt("seed")
            val period = item.getInt("period")
            val expected = item.getDouble("value")
            assertEquals("periodicValueNoise1D mismatch for ($x, $seed, $period)", expected, ServerRendererGeometry.periodicValueNoise1D(x, seed, period), 1e-9)
        }

        // 7. sample_offset & sample_offset_periodic
        val sampleOffsetArr = root.getJSONArray("sample_offset")
        for (i in 0 until sampleOffsetArr.length()) {
            val group = sampleOffsetArr.getJSONObject(i)
            val quality = group.getString("quality")
            val frequency = group.getString("frequency")
            val seed = group.getInt("seed")
            val amp = group.getDouble("amp")
            val samples = group.getJSONArray("samples")

            val variation = JSONObject()
                .put("quality", quality)
                .put("frequency", frequency)

            for (j in 0 until samples.length()) {
                val item = samples.getJSONObject(j)
                val t = item.getDouble("t")
                val segment = item.getInt("segment")
                val expectedOpen = item.getDouble("open")
                val expectedPeriodic = item.getDouble("periodic")

                val actualOpen = ServerRendererGeometry.sampleOffset(t, variation, seed, segment, amp)
                assertEquals("sampleOffset mismatch at group $i sample $j (q=$quality, f=$frequency, t=$t)", expectedOpen, actualOpen, 1e-9)

                val actualPeriodic = ServerRendererGeometry.sampleOffsetPeriodic(t, variation, seed, segment, amp)
                assertEquals("sampleOffsetPeriodic mismatch at group $i sample $j (q=$quality, f=$frequency, t=$t)", expectedPeriodic, actualPeriodic, 1e-9)
            }
        }
    }

    @Test
    fun testRendererSeedRangeParity() {
        val root = ReferenceCorpus.json("renderer_seed_range.json")

        // 1. stroke_engine_unit
        if (root.has("stroke_engine_unit")) {
            val arr = root.getJSONArray("stroke_engine_unit")
            for (i in 0 until arr.length()) {
                val item = arr.getJSONObject(i)
                val seedStr = item.get("seed").toString()
                val seedULong = seedStr.toULong()
                val idx = item.getInt("index")
                val label = item.getString("label")
                val expected = item.getDouble("value")
                val actual = ServerStrokeEngine.unitHash(seedULong.toLong(), label, idx)
                assertEquals("stroke_engine_unit mismatch for label=$label, seed=$seedULong, index=$idx", expected, actual, 1e-12)
            }
        }

        // 2. renderer_hash01
        if (root.has("renderer_hash01")) {
            val arr = root.getJSONArray("renderer_hash01")
            for (i in 0 until arr.length()) {
                val item = arr.getJSONObject(i)
                val seedStr = item.get("seed").toString()
                val idx = item.getInt("i")
                val salt = item.optString("salt", "")
                val expected = item.getDouble("value")
                val actual = ServerRendererGeometry.hash01(idx, seedStr, salt)
                assertEquals("renderer_hash01 mismatch for seed=$seedStr, index=$idx, salt=$salt", expected, actual, 1e-12)
            }
        }

        // 3. renderer_hash_to_unit
        if (root.has("renderer_hash_to_unit")) {
            val arr = root.getJSONArray("renderer_hash_to_unit")
            for (i in 0 until arr.length()) {
                val item = arr.getJSONObject(i)
                val seedStr = item.get("seed").toString()
                val idx = item.getInt("i")
                val expected = item.getDouble("value")
                val actual = ServerRendererGeometry.hashToUnit(idx, seedStr)
                assertEquals("renderer_hash_to_unit mismatch for seed=$seedStr, index=$idx", expected, actual, 1e-12)
            }
        }

        // 4. instruction_seed
        if (root.has("instruction_seed")) {
            val arr = root.getJSONArray("instruction_seed")
            for (i in 0 until arr.length()) {
                val item = arr.getJSONObject(i)
                val name = item.optString("name", "item-$i")
                val ins = item.getJSONObject("instruction")
                val renderSeed = if (item.has("performance_seed") && !item.isNull("performance_seed")) item.getLong("performance_seed") else null
                val expectedSeedStr = item.get("seed").toString()
                val actualSeedStr = DefaultSvgRenderer_seedForInstructionHelper(ins, renderSeed)
                assertEquals("instruction_seed mismatch for name=$name", expectedSeedStr, actualSeedStr)
            }
        }
    }

    @Test
    fun testCloudformContourDeterminismAndGeneration() {
        val center = 0.5 to 0.5
        val size = 0.4 to 0.3
        val seed = 12345L
        val contour1 = ServerRendererGeometry.generateCloudformContour(
            center = center,
            size = size,
            performanceSeed = seed,
            instructionIndex = 0,
            markIndex = 0
        )
        val contour2 = ServerRendererGeometry.generateCloudformContour(
            center = center,
            size = size,
            performanceSeed = seed,
            instructionIndex = 0,
            markIndex = 0
        )

        assertEquals(49, contour1.points.size)
        assertEquals(contour1.points.size, contour2.points.size)

        for (i in contour1.points.indices) {
            assertEquals("Point $i X match", contour1.points[i].first, contour2.points[i].first, 1e-9)
            assertEquals("Point $i Y match", contour1.points[i].second, contour2.points[i].second, 1e-9)
        }
        assertEquals("Path D match", contour1.pathD, contour2.pathD)
        assertTrue("Path D starts with M", contour1.pathD.startsWith("M "))
        assertTrue("Path D ends with Z", contour1.pathD.endsWith(" Z"))
    }

    private fun DefaultSvgRenderer_seedForInstructionHelper(ins: JSONObject, renderSeed: Long?): String {
        val renderer = DefaultSvgRenderer()
        val method = DefaultSvgRenderer::class.java.getDeclaredMethod("seedForInstruction", JSONObject::class.java, java.lang.Long::class.java)
        method.isAccessible = true
        return method.invoke(renderer, ins, renderSeed) as String
    }
}
