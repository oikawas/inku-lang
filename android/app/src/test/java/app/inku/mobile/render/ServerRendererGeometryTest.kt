package app.inku.mobile.render

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
        val amp = ServerRendererGeometry.getAmplitudePx(variation)

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

    @Test
    fun testVariedArcPathDGeneration() {
        val variation = JSONObject()
            .put("amplitude", "fine")
            .put("frequency", "high")
            .put("quality", "perlin")
            .put("dimensions", JSONArray().put("position_x").put("position_y"))

        val path1 = ServerRendererGeometry.variedArcPathD(500.0, 500.0, 180.0, 20.0, 300.0, variation, 12345)
        val path2 = ServerRendererGeometry.variedArcPathD(500.0, 500.0, 180.0, 20.0, 300.0, variation, 12345)
        val pathOtherSeed = ServerRendererGeometry.variedArcPathD(500.0, 500.0, 180.0, 20.0, 300.0, variation, 99999)

        assertTrue("Path should start with M", path1.startsWith("M "))
        assertTrue("Path should contain L segments", path1.contains(" L "))
        assertEquals("Path must be deterministic for same seed", path1, path2)
        assertNotEquals("Path should differ for different seeds", path1, pathOtherSeed)
    }
}
