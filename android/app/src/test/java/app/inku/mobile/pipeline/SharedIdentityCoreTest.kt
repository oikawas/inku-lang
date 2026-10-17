package app.inku.mobile.pipeline

import java.io.File
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** The server fixture is consumed in place so host and core check identical identity cases. */
class SharedIdentityCoreTest {
    private val cases: JSONObject
        get() = JSONObject(File(requireNotNull(System.getProperty("inku.identityCases"))).readText())

    @Test
    fun everySharedDescriptionHashCaseMatches() {
        val rows = cases.getJSONArray("description_hash")
        for (index in 0 until rows.length()) {
            val row = rows.getJSONObject(index)
            assertEquals(row.getString("why"), row.getString("dh1"),
                NativePipelineBridge.descriptionHash(row.getString("text")))
        }
    }

    @Test
    fun everySharedPythonSpaceIsStripped() {
        val baseHash = NativePipelineBridge.descriptionHash("花")
        val spaces = cases.getJSONArray("python_space")
        for (index in 0 until spaces.length()) {
            val space = String(Character.toChars(spaces.getInt(index)))
            assertEquals("U+${spaces.getInt(index).toString(16)}", baseHash,
                NativePipelineBridge.descriptionHash("${space}花${space}"))
        }
    }

    @Test
    fun everySharedCanonicalJsonCaseMatchesFromRawInput() {
        val rows = cases.getJSONArray("canonical_json")
        for (index in 0 until rows.length()) {
            val row = rows.getJSONObject(index)
            assertEquals(row.getString("why"), row.getString("canonical"),
                NativePipelineBridge.canonicalJson(row.getString("input")))
        }
    }

    @Test
    fun everySharedRenderHashCaseMatchesFromRawInput() {
        val rows = cases.getJSONArray("render_hash")
        for (index in 0 until rows.length()) {
            val row = rows.getJSONObject(index)
            assertEquals(row.getString("why"), row.getString("rh3"),
                NativePipelineBridge.renderHash(row.getString("item")))
        }
    }

    @Test
    fun invalidJsonAndNonObjectHistoryReturnNullAcrossJni() {
        assertNull(NativePipelineBridge.canonicalJson("[1,]"))
        assertNull(NativePipelineBridge.renderHash("{"))
        assertNull(NativePipelineBridge.renderHash("[]"))
        assertNull(NativePipelineBridge.normalizeInstructionLanguage("fr", "ja"))
        assertNull(NativePipelineBridge.resolveInstructionLanguage("円", "fr", "ja"))
    }
}
