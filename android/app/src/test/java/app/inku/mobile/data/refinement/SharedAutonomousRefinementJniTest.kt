package app.inku.mobile.data.refinement

import app.inku.mobile.pipeline.CoreIdentityJson
import app.inku.mobile.pipeline.NativePipelineBridge
import java.io.File
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SharedAutonomousRefinementJniTest {
    @Test
    fun everySharedNextRecordGateAndRefusalCrossesTheAndroidJniBinding() {
        val cases = JSONObject(File(requireNotNull(System.getProperty("inku.identityCases")))
            .resolveSibling("autonomous-refine-cases.json").readText())
        for (section in listOf("next", "record", "invalid", "measure", "refused")) {
            val rows = cases.getJSONArray(section)
            assertTrue(rows.length() > 0)
            for (index in 0 until rows.length()) {
                val row = rows.getJSONObject(index)
                val request = row.getJSONObject("request")
                val answer = JSONObject(NativePipelineBridge.autonomousRefine(request.toString().encodeToByteArray())
                    .toString(Charsets.UTF_8))
                if (answer.optString("outcome") == "refused") assertTrue((answer.remove("detail") as String).isNotBlank())
                assertEquals("$section: ${row.getString("why")}", CoreIdentityJson.canonical(row.getJSONObject("answer")),
                    CoreIdentityJson.canonical(answer))
                if (answer.optString("outcome") == "ok") assertEquals(CoreIdentityJson.canonical(answer),
                    CoreIdentityJson.canonical(SharedAutonomousRefinement.call(request.getString("action"), request)))
            }
        }
    }
}
