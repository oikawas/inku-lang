package app.inku.mobile.pipeline

import app.inku.mobile.ReferenceCorpus
import java.security.MessageDigest
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The port runs the whole pipeline on the device, so it duplicates the server's prompts as
 * Kotlin constants. CI never runs the Android tests against the server, so that duplicate
 * goes quietly stale - and had: the Stage 1 Japanese prefix still listed 描く among the
 * permitted verbs and knew nothing of 銀筆, 敷き詰める or the mandatory-texture rule.
 *
 * `server_reference/prompts.json` carries the byte length and SHA-256 of the server's four
 * prompts. Matching them is the whole check. When this fails, the fix is on this side:
 * copy the server constant over wholesale rather than patching line by line, because the
 * versions drift by more than any one edit.
 *
 * The two `*_LITERT` constants are deliberately absent. They are shortened on purpose for
 * the small on-device model and have no server counterpart, so there is nothing to pin.
 */
class PromptFingerprintTest {

    private fun expectations(): JSONObject =
        ReferenceCorpus.json("prompts.json").getJSONObject("prompts")

    private fun sha256(text: String): String =
        MessageDigest.getInstance("SHA-256")
            .digest(text.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }

    private fun actualPrompts(): Map<String, String> = mapOf(
        "STAGE1_PROMPT_PREFIX_JA" to WebDdlSpec.stage1SystemPromptForDisplay("ja"),
        "STAGE1_PROMPT_PREFIX_EN" to WebDdlSpec.stage1SystemPromptForDisplay("en"),
        "STAGE2_SYSTEM_PROMPT_JA" to WebDdlSpec.stage2SystemPromptForDisplay("ja"),
        "STAGE2_SYSTEM_PROMPT_EN" to WebDdlSpec.stage2SystemPromptForDisplay("en"),
    )

    @Test
    fun testEveryDuplicatedPromptMatchesTheServerFingerprint() {
        val expected = expectations()
        for ((name, text) in actualPrompts()) {
            val entry = expected.getJSONObject(name)
            val bytes = text.toByteArray(Charsets.UTF_8).size
            assertEquals("$name byte length must match the server", entry.getInt("bytes"), bytes)
            assertEquals("$name SHA-256 must match the server", entry.getString("sha256"), sha256(text))
        }
    }

    @Test
    fun testEveryFingerprintInTheManifestIsChecked() {
        // A guard that only walks the constants it happens to know about leaves a hole:
        // a prompt added to the manifest would go unchecked and nothing would say so.
        val expected = expectations()
        val declared = expected.keys().asSequence().toSet()
        assertEquals("Every prompt in the manifest must be checked", declared, actualPrompts().keys)
    }

    @Test
    fun testTheLiteRtPromptsAreNotPinnedToTheServer() {
        // Shortened on purpose for the on-device model; pinning them to the server would
        // be wrong, not merely red.
        val litert = WebDdlSpec.stage2LiteRtSystemPromptForDisplay()
        assertTrue("The LiteRT prompt must exist", litert.isNotEmpty())
        val serverStage2 = WebDdlSpec.stage2SystemPromptForDisplay("ja")
        assertTrue("The LiteRT prompt is the short one", litert.length < serverStage2.length)
    }
}
