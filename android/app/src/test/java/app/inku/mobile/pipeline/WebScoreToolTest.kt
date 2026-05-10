package app.inku.mobile.pipeline

import org.junit.Assert.assertEquals
import org.json.JSONObject
import org.junit.Test

class WebScoreToolTest {
    @Test
    fun extractJsonObjectRepairsLiteRtNumericWhitespaceAndTrimmedKeys() {
        val malformed = """
            {
              "instructions": [
                {
                  "primitive": "ellipse ",
                  "center": [0.5, 0. 0],
                  "size": [0. 01, 0.01],
                  "color": "white",
                  "arrangement ": {
                    " count ": 50 0,
                    " layout ": "vertical ",
                    "position\n\n_\n\nx": 0.25
                  }
                }
              ]
            }
        """.trimIndent()

        val repaired = WebScoreTool.repairLiteRtJsonText(malformed)
        assertEquals(false, repaired.contains("0. 0"))
        assertEquals(false, repaired.contains("0. 01"))
        assertEquals(false, repaired.contains("50 0"))
        JSONObject(repaired)

        val score = WebScoreTool.extractJsonObject(malformed)
        val item = score.getJSONArray("instructions").getJSONObject(0)
        val arrangement = item.getJSONObject("arrangement")

        assertEquals("ellipse", item.getString("primitive"))
        assertEquals(0.0, item.getJSONArray("center").getDouble(1), 0.0001)
        assertEquals(0.01, item.getJSONArray("size").getDouble(0), 0.0001)
        assertEquals(500, arrangement.getInt("count"))
        assertEquals("vertical", arrangement.getString("layout"))
        assertEquals(0.25, arrangement.getDouble("position_x"), 0.0001)
    }
}
