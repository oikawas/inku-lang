package app.inku.mobile.pipeline

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * T-1, T-2 and T-3 of 契約 android-compares-models-and-languages.
 *
 * The expected values are the server's, measured by running
 * `language_support/registry.py` itself on 2026-08-08 (契約 §3.0). They are
 * asserted here as a table rather than as a paraphrase of the code, so an
 * implementation that reaches the same answers a different way still passes and
 * one that reaches different answers cannot.
 */
class InstructionLanguageTest {

    // ── T-1: normalize ────────────────────────────────────────

    @Test
    fun `null and empty fall back to the default`() {
        assertEquals("ja", InstructionLanguages.normalize(null))
        assertEquals("ja", InstructionLanguages.normalize(""))
    }

    /**
     * The one case that tells `(value or default)` apart from a default-valued
     * read: a string of spaces is truthy in Python, so it is *not* replaced by
     * the default, and what reaches the membership test is `""`.
     */
    @Test
    fun `a string of only spaces is not the default and is rejected`() {
        val error = assertThrows(IllegalArgumentException::class.java) {
            InstructionLanguages.normalize("  ")
        }
        assertEquals("unsupported instruction language:   ", error.message)
    }

    @Test
    fun `the three requestable words pass through`() {
        assertEquals("ja", InstructionLanguages.normalize("ja"))
        assertEquals("en", InstructionLanguages.normalize("en"))
        assertEquals("auto", InstructionLanguages.normalize("auto"))
    }

    @Test
    fun `case and surrounding space are removed`() {
        assertEquals("ja", InstructionLanguages.normalize("JA"))
        assertEquals("en", InstructionLanguages.normalize(" En "))
        assertEquals("auto", InstructionLanguages.normalize("AUTO"))
    }

    @Test
    fun `an unsupported language is refused`() {
        listOf("fr", "ja-JP", "zh").forEach { value ->
            assertThrows(IllegalArgumentException::class.java) {
                InstructionLanguages.normalize(value)
            }
        }
    }

    /** A different default reaches only the two falsy values; nothing else moves. */
    @Test
    fun `the default only decides null and empty`() {
        assertEquals("en", InstructionLanguages.normalize(null, default = "en"))
        assertEquals("en", InstructionLanguages.normalize("", default = "en"))
        assertEquals("ja", InstructionLanguages.normalize("ja", default = "en"))
        assertEquals("auto", InstructionLanguages.normalize("auto", default = "en"))
    }

    // ── T-2: resolve ──────────────────────────────────────────

    private val japanese = "夕暮れの水面"
    private val english = "a quiet river at dusk"
    private val mixed = "夕暮れ at dusk"
    private val neither = "12345 !!! ---"

    @Test
    fun `an explicit language never reads the text`() {
        listOf(japanese, english, mixed, neither, "").forEach { text ->
            assertEquals("ja", InstructionLanguages.resolve(text, "ja"))
            assertEquals("en", InstructionLanguages.resolve(text, "en"))
        }
    }

    /**
     * The order of the two probes is the judgment: Japanese is asked first, so a
     * text carrying both scripts is Japanese. Swapping the probes turns this one
     * row -- and only this one -- red.
     */
    @Test
    fun `auto reads the text and asks for japanese first`() {
        assertEquals("ja", InstructionLanguages.resolve(japanese, "auto"))
        assertEquals("en", InstructionLanguages.resolve(english, "auto"))
        assertEquals("ja", InstructionLanguages.resolve(mixed, "auto"))
        assertEquals("ja", InstructionLanguages.resolve(neither, "auto"))
        assertEquals("ja", InstructionLanguages.resolve("", "auto"))
    }

    /**
     * The fallback is normalised on the way out, which is why `auto` becomes
     * `ja` there rather than being returned as a language nobody can select.
     */
    @Test
    fun `the fallback decides a text with no script and is itself normalised`() {
        assertEquals("ja", InstructionLanguages.resolve("12345", "auto", fallback = "ja"))
        assertEquals("en", InstructionLanguages.resolve("12345", "auto", fallback = "en"))
        assertEquals("ja", InstructionLanguages.resolve("12345", "auto", fallback = "auto"))
    }

    @Test
    fun `an unsupported request is refused before any text is read`() {
        assertThrows(IllegalArgumentException::class.java) {
            InstructionLanguages.resolve(japanese, "fr")
        }
    }

    /**
     * The wrapper the routers call: a `ui_lang` outside the supported set is not
     * an error, it simply is not used (`common.py:68-70`). This client passes
     * none today, and that case has to reach the same answer.
     */
    @Test
    fun `an unknown ui language falls back to japanese rather than raising`() {
        listOf(null, "ja", "fr", "de").forEach { uiLang ->
            assertEquals("ja", InstructionLanguages.resolveWithUiLang("12345", "auto", uiLang))
        }
        assertEquals("en", InstructionLanguages.resolveWithUiLang("12345", "auto", "en"))
    }

    // ── T-3: auto must be resolved first ──────────────────────

    @Test
    fun `selecting language support for auto is refused`() {
        val error = assertThrows(IllegalArgumentException::class.java) {
            InstructionLanguages.support("auto")
        }
        assertEquals("auto must be resolved before selecting language support", error.message)
    }

    /**
     * The other half of the pair. Without it, an implementation that refuses
     * every language passes the case above.
     */
    @Test
    fun `a resolved language selects its support`() {
        assertEquals(InstructionLanguage.Ja, InstructionLanguages.support("ja"))
        assertEquals(InstructionLanguage.En, InstructionLanguages.support("en"))
        assertTrue(InstructionLanguages.support(InstructionLanguages.resolve("a river", "auto")).isEnglish)
    }

    @Test
    fun `an unsupported language selects nothing`() {
        assertThrows(IllegalArgumentException::class.java) {
            InstructionLanguages.support("fr")
        }
    }
}
