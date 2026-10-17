package app.inku.mobile.data.refinement

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SentPromptsTest {
    private fun record(prompts: JSONObject? = null, revision: String = "4"): String {
        val metadata = JSONObject()
        if (prompts != null) metadata.put("sent_system_prompts", prompts)
            .put("sent_system_prompt_stages", JSONArray(listOf("sketch", "stage1", "composition", "stage2")))
            .put("sent_prompt_execution_id", "execution-1")
            .put("sent_prompt_variation_id", "variation-1")
            .put("sent_prompt_revision", revision)
        return metadata.toString()
    }

    @Test
    fun exactHistoryExecutionAndRevisionExposeOnlySentStages() {
        val prompt = JSONObject().put("system", "sent system").put("message", "sent sketch text")
            .put("prompt_id", "sketch-v1").put("prompt_digest", "sha256:one")
            .put("instruction_language", "ja").put("attempt", 2)
        val savedRecord = record(JSONObject().put("sketch", prompt))
        val recorded = sentPromptsFromHistoryRecord(savedRecord, "execution-1", "variation-1", "4") as SentPrompts.Recorded
        assertEquals("sent system", recorded.prompts[PromptStage.Sketch]?.system)
        assertEquals("sent sketch text", recorded.prompts[PromptStage.Sketch]?.message)
        assertEquals(2, recorded.prompts[PromptStage.Sketch]?.attempt)
        assertNull(recorded.prompts[PromptStage.Stage1])
        assertTrue(recorded.stages.contains(PromptStage.Composition))
        assertEquals(SentPrompts.Unavailable, sentPromptsFromHistoryRecord(savedRecord, "execution-1", "variation-1", "3"))
        assertEquals(SentPrompts.Unavailable, sentPromptsFromHistoryRecord(savedRecord, "another", "variation-1", "4"))
    }

    @Test
    fun oldExecutionWithNoPromptRecordIsNotRecorded() {
        assertEquals(SentPrompts.NotRecorded,
            sentPromptsFromHistoryRecord(record(), "execution-1", "variation-1", "4"))
    }
}
