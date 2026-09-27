package app.inku.mobile.pipeline

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class RenderWarningTest {
    @Test
    fun readsKindsAndNamesAndSkipsWhatItCannotRead() {
        val metadata = JSONObject(
            """{"render_warnings":[{"kind":"invalid_color","name":"black"},{"kind":"future_kind"},{"name":"no kind"},"text"]}""",
        )
        assertEquals(
            listOf(RenderWarning("invalid_color", "black"), RenderWarning("future_kind", null)),
            RenderWarning.listFrom(metadata),
        )
        assertEquals(emptyList<RenderWarning>(), RenderWarning.listFrom(JSONObject("{}")))
    }
}
