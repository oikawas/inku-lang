package app.inku.mobile.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class RenderTabCopyTest {

    @Test
    fun copyTextMatchesTheVisibleRenderTabText() {
        val prompt = "Stage 1 input:\n雲を描く\n\nStage 2 input:\n雲"
        val json = "{\n  \"score\": {\"commands\": []}\n}"

        assertNull(renderTabCopyText(RenderTab.Artwork, prompt, json))
        assertEquals(prompt, renderTabCopyText(RenderTab.Prompt, prompt, json))
        assertEquals(json, renderTabCopyText(RenderTab.Json, prompt, json))
    }
}
