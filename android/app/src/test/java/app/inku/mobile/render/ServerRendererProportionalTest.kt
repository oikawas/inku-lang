package app.inku.mobile.render

import app.inku.mobile.ReferenceCorpus
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class ServerRendererProportionalTest {

    private fun parseShapeInstruction(shapeName: String): JSONObject {
        val ins = JSONObject()
        when (shapeName) {
            "circle_r020" -> ins.put("primitive", "circle").put("radius", 0.20)
            "circle_r005" -> ins.put("primitive", "circle").put("radius", 0.05)
            "ellipse_06x03" -> ins.put("primitive", "ellipse").put("size", JSONArray().put(0.6).put(0.3))
            "square_04" -> ins.put("primitive", "square").put("size", JSONArray().put(0.4).put(0.4))
            "line_diagonal" -> ins.put("primitive", "line").put("from", JSONArray().put(0.1).put(0.1)).put("to", JSONArray().put(0.9).put(0.9))
            "arc_r030" -> ins.put("primitive", "arc").put("radius", 0.30)
            "tiny_dot" -> ins.put("primitive", "circle").put("radius", 0.001)
            else -> error("Unknown shape: $shapeName")
        }
        return ins
    }

    @Test
    fun testProportionalReferenceParity() {
        val root = ReferenceCorpus.json("renderer_proportional.json")

        val canvases = root.getJSONObject("canvases")

        // 1. representative_size_px
        val repArr = root.getJSONArray("representative_size_px")
        for (i in 0 until repArr.length()) {
            val item = repArr.getJSONObject(i)
            val aspect = item.getString("aspect")
            val shapeName = item.getString("shape")
            val expRaw = item.getDouble("raw")
            val expClamped = item.getDouble("clamped")

            val cObj = canvases.getJSONObject(aspect)
            val w = cObj.getDouble("width")
            val h = cObj.getDouble("height")
            val u = cObj.getDouble("unit")
            val ins = parseShapeInstruction(shapeName)

            val actRaw = ServerRendererGeometry.representativeSizePx(ins, w, h, u)
            val actClamped = ServerRendererGeometry.clampedRepresentativePx(ins, w, h, u)

            assertEquals("representativeSizePx raw mismatch for ($aspect, $shapeName)", expRaw, actRaw, 1e-9)
            assertEquals("clampedRepresentativePx mismatch for ($aspect, $shapeName)", expClamped, actClamped, 1e-9)
        }

        // 2. amplitude_px
        val ampArr = root.getJSONArray("amplitude_px")
        for (i in 0 until ampArr.length()) {
            val item = ampArr.getJSONObject(i)
            val aspect = item.getString("aspect")
            val shapeName = item.getString("shape")
            val amplitudeStr = item.getString("amplitude")
            val expAmp = item.getDouble("value")

            val cObj = canvases.getJSONObject(aspect)
            val w = cObj.getDouble("width")
            val h = cObj.getDouble("height")
            val u = cObj.getDouble("unit")
            val ins = parseShapeInstruction(shapeName)
            val variation = JSONObject().put("amplitude", amplitudeStr)

            val actAmp = ServerRendererGeometry.amplitudePx(variation, ins, w, h, u)
            assertEquals("amplitudePx mismatch for ($aspect, $shapeName, $amplitudeStr)", expAmp, actAmp, 1e-9)
        }

        // 3. blur_std_px
        val blurArr = root.getJSONArray("blur_std_px")
        for (i in 0 until blurArr.length()) {
            val item = blurArr.getJSONObject(i)
            val aspect = item.getString("aspect")
            val shapeName = item.getString("shape")
            val amplitudeStr = item.getString("amplitude")
            val expStd = item.getDouble("value")

            val cObj = canvases.getJSONObject(aspect)
            val w = cObj.getDouble("width")
            val h = cObj.getDouble("height")
            val u = cObj.getDouble("unit")
            val ins = parseShapeInstruction(shapeName)
            val variation = JSONObject().put("amplitude", amplitudeStr)

            val actStd = ServerRendererGeometry.blurStdPx(variation, ins, w, h, u)
            assertEquals("blurStdPx mismatch for ($aspect, $shapeName, $amplitudeStr)", expStd, actStd, 1e-9)
        }

        // 4. segment_count
        val segArr = root.getJSONArray("segment_count")
        for (i in 0 until segArr.length()) {
            val item = segArr.getJSONObject(i)
            val aspect = item.getString("aspect")
            val pathLenPx = item.getDouble("path_len_px")
            val expCount = item.getInt("value")

            val cObj = canvases.getJSONObject(aspect)
            val u = cObj.getDouble("unit")

            val actCount = ServerRendererGeometry.segmentCount(pathLenPx, u)
            assertEquals("segmentCount mismatch for ($aspect, $pathLenPx)", expCount, actCount)
        }

        // 5. stroke_sample_count
        val sampleArr = root.getJSONArray("stroke_sample_count")
        for (i in 0 until sampleArr.length()) {
            val item = sampleArr.getJSONObject(i)
            val aspect = item.getString("aspect")
            val lengthPx = item.getDouble("length_px")
            val expCount = item.getInt("value")

            val cObj = canvases.getJSONObject(aspect)
            val u = cObj.getDouble("unit")

            val actCount = ServerRendererGeometry.strokeSampleCount(lengthPx, u)
            assertEquals("strokeSampleCount mismatch for ($aspect, $lengthPx)", expCount, actCount)
        }

        // 6. stroke_width_px
        val widthArr = root.getJSONArray("stroke_width_px")
        for (i in 0 until widthArr.length()) {
            val item = widthArr.getJSONObject(i)
            val aspect = item.getString("aspect")
            val weight = item.getString("weight")
            val expWidth = item.getDouble("value")

            val cObj = canvases.getJSONObject(aspect)
            val u = cObj.getDouble("unit")

            val actWidth = ServerRendererStyle.strokeWidth(weight, u)
            assertEquals("strokeWidthPx mismatch for ($aspect, $weight)", expWidth, actWidth, 1e-9)
        }

        // 7. speck_count
        val speckArr = root.getJSONArray("speck_count")
        for (i in 0 until speckArr.length()) {
            val item = speckArr.getJSONObject(i)
            val aspect = item.getString("aspect")
            val baseCount = item.getInt("base")
            val pathLenPx = item.getDouble("path_len_px")
            val expCount = item.getInt("value")

            val cObj = canvases.getJSONObject(aspect)
            val u = cObj.getDouble("unit")

            val actCount = ServerRendererMaterial.speckCount(baseCount, pathLenPx, u)
            assertEquals("speckCount mismatch for ($aspect, $baseCount, $pathLenPx)", expCount, actCount)
        }
    }
}
