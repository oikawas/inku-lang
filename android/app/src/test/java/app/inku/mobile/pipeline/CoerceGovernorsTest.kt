package app.inku.mobile.pipeline

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class CoerceGovernorsTest {

    private val pipeline = LocalFallbackPipeline()

    private val backgroundDominanceGovernorMethod = LocalFallbackPipeline::class.java.getDeclaredMethod(
        "backgroundDominanceGovernor",
        String::class.java,
        String::class.java,
    ).apply { isAccessible = true }

    private val hasExplicitBackgroundIntentMethod = LocalFallbackPipeline::class.java.getDeclaredMethod(
        "hasExplicitBackgroundIntent",
        String::class.java,
    ).apply { isAccessible = true }

    private val buildStage2UserMessageMethod = LocalFallbackPipeline::class.java.getDeclaredMethod(
        "buildStage2UserMessage",
        String::class.java,
    ).apply { isAccessible = true }

    private val temperQuietSymbolicShapeMethod = LocalFallbackPipeline::class.java.getDeclaredMethod(
        "temperQuietSymbolicShape",
        JSONObject::class.java,
        String::class.java,
    ).apply { isAccessible = true }

    private val temperQuietSingleShapeMethod = LocalFallbackPipeline::class.java.getDeclaredMethod(
        "temperQuietSingleShape",
        JSONObject::class.java,
        String::class.java,
    ).apply { isAccessible = true }

    private val temperUnintentionalFilledShapeMethod = LocalFallbackPipeline::class.java.getDeclaredMethod(
        "temperUnintentionalFilledShape",
        JSONObject::class.java,
        String::class.java,
    ).apply { isAccessible = true }

    private fun copyJsonObject(item: JSONObject): JSONObject = JSONObject(item.toString())

    @Test
    fun testCoerceGovernorsReference() {
        val stream = javaClass.getResourceAsStream("/server_reference/coerce_governors.json")
            ?: error("Resource /server_reference/coerce_governors.json not found")
        val json = JSONObject(stream.bufferedReader().use { it.readText() })

        val bgCases = json.getJSONArray("background_cases")
        for (i in 0 until bgCases.length()) {
            val caseObj = bgCases.getJSONObject(i)
            val caseId = caseObj.getString("case_id")
            val ddl = caseObj.getString("ddl")
            val bgIn = caseObj.getString("background_in")
            val expectedBg = caseObj.getString("expected")
            val expectedIntent = caseObj.getBoolean("explicit_background_intent")

            val actualBg = backgroundDominanceGovernorMethod.invoke(pipeline, bgIn, ddl) as String
            assertEquals("Background mismatch in case $caseId", expectedBg, actualBg)

            val actualIntent = hasExplicitBackgroundIntentMethod.invoke(pipeline, ddl) as Boolean
            assertEquals("Explicit background intent mismatch in case $caseId", expectedIntent, actualIntent)
        }

        val temperCases = json.getJSONArray("tempering_cases")
        for (i in 0 until temperCases.length()) {
            val caseObj = temperCases.getJSONObject(i)
            val caseId = caseObj.getString("case_id")
            val ddl = caseObj.getString("ddl")
            val ins = caseObj.getJSONObject("instruction")
            val expectedIns = caseObj.getJSONObject("expected")

            val step1 = temperUnintentionalFilledShapeMethod.invoke(pipeline, copyJsonObject(ins), ddl) as JSONObject
            val step2 = temperQuietSymbolicShapeMethod.invoke(pipeline, copyJsonObject(step1), ddl) as JSONObject
            val step3 = temperQuietSingleShapeMethod.invoke(pipeline, copyJsonObject(step2), ddl) as JSONObject
            val actualIns = temperUnintentionalFilledShapeMethod.invoke(pipeline, copyJsonObject(step3), ddl) as JSONObject

            assertEquals("Tempered instruction mismatch in case $caseId", expectedIns.toString(), actualIns.toString())
        }

        val s2Msg = json.getJSONObject("stage2_user_message")
        val ddl = s2Msg.getString("ddl")
        val expectedMsg = s2Msg.getString("expected")
        val actualMsg = buildStage2UserMessageMethod.invoke(pipeline, ddl) as String
        assertEquals("Stage 2 user message mismatch", expectedMsg, actualMsg)
    }
}
