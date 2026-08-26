package app.inku.mobile.ui

import app.inku.mobile.pipeline.InstructionLanguages
import app.inku.mobile.pipeline.PaintRequest
import app.inku.mobile.ui.i18n.UiLanguage
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import java.io.File
import org.junit.Test

/**
 * Acceptance for stage 3 of the-interface-speaks-both-languages (2026-08-09, [I-065]).
 *
 * The contract's stage 3 says three things change together when the reader
 * switches: the wording, the saijiki words, and which language a work is drawn
 * in. The third one is the one that can be wired and still do nothing, so it is
 * checked at the condition that makes it readable rather than at the call.
 */
class UiLanguageSettingTest {

    private fun source(relative: String): String {
        var file = File("src/$relative")
        if (!file.exists()) {
            file = File("app/src/$relative")
        }
        assertTrue("source not found (searched in ./src and ./app/src): $relative", file.exists())
        return file.readText()
    }

    /** T1: the default is Japanese, and an unknown stored code is Japanese too. */
    @Test
    fun testDefaultIsJapaneseAndAnUnknownCodeIsNotAnError() {
        assertEquals(UiLanguage.Ja, UiLanguage.DEFAULT)
        assertEquals(UiLanguage.Ja, UiLanguage.fromCode(null))
        assertEquals(UiLanguage.Ja, UiLanguage.fromCode(""))
        // The server does not reject an unrecognised `ui_lang`; it reads it as
        // Japanese (`api_core/common.py:68-70`). Rejecting here would be the
        // client deciding something the server decided otherwise.
        assertEquals(UiLanguage.Ja, UiLanguage.fromCode("fr"))
        assertEquals(UiLanguage.En, UiLanguage.fromCode("en"))
    }

    /**
     * T2 (contract's stage 3 ②): the saijiki words follow the setting.
     *
     * Named words, not a count: a build that returned the Japanese list under
     * both languages would still have 73 words in each.
     */
    @Test
    fun testSwitchingTheLanguageSwitchesTheSaijikiWords() {
        val ja = saijikiGroups(UiLanguage.Ja).flatMap { it.words }
        val en = saijikiGroups(UiLanguage.En).flatMap { it.words }
        assertTrue("ja shows 円", "円" in ja)
        assertFalse("ja must not show circle", "circle" in ja)
        assertTrue("en shows circle", "circle" in en)
        assertFalse("en must not show 円", "円" in en)
        assertNotEquals("the two languages show the same words", ja, en)
    }

    /**
     * T3 (contract's stage 3 ③): the setting decides what a work asking for
     * `auto` is drawn in.
     *
     * The text here names NEITHER script, which is the only case where the
     * answer is the ui language's to give: `resolve` reads the Japanese probe,
     * then the Latin one, and only then the fallback (`registry.py:31-40`). A
     * test written with English prose would pass on the Latin probe alone and
     * say nothing about this wire.
     */
    @Test
    fun testTheUiLanguageDecidesAnAutoRequestWhenTheTextNamesNoScript() {
        val neitherScript = "1234 5678"
        assertEquals(
            "ja",
            InstructionLanguages.resolveWithUiLang(neitherScript, InstructionLanguages.AUTO, "ja"),
        )
        assertEquals(
            "en",
            InstructionLanguages.resolveWithUiLang(neitherScript, InstructionLanguages.AUTO, "en"),
        )
    }

    /**
     * T4: the text still outranks the setting.
     *
     * The order of the two probes is the judgement, not a detail. A reader in
     * English who writes Japanese gets a Japanese work, because that is what the
     * server answers for the same request.
     */
    @Test
    fun testTheTextOutranksTheSettingAndAnExplicitRequestOutranksBoth() {
        assertEquals(
            "ja",
            InstructionLanguages.resolveWithUiLang("夕暮れの水面", InstructionLanguages.AUTO, "en"),
        )
        assertEquals(
            "en",
            InstructionLanguages.resolveWithUiLang("a quiet river", InstructionLanguages.AUTO, "ja"),
        )
        // An explicit request never reads the text or the setting.
        assertEquals("ja", InstructionLanguages.resolveWithUiLang("a quiet river", "ja", "en"))
        assertEquals("en", InstructionLanguages.resolveWithUiLang("夕暮れの水面", "en", "ja"))
    }

    /**
     * T5: the value the screen sends is carried, and the pipeline reads it.
     *
     * `PaintRequest.uiLang` has a default of `null`, so a call site that forgot
     * it compiles. This reads the two resolution sites and the five screen
     * calls instead of trusting the default.
     */
    @Test
    fun testEveryResolutionSiteReadsTheCarriedUiLanguage() {
        val pipeline = source("main/java/app/inku/mobile/pipeline/LocalFallbackPipeline.kt")
        val calls = Regex("""resolveWithUiLang\(""").findAll(pipeline).count()
        assertEquals("resolution sites in LocalFallbackPipeline", 2, calls)
        assertEquals(
            "every resolution site must be handed request.uiLang",
            calls,
            Regex("""request\.uiLang""").findAll(pipeline).count(),
        )

        val viewModel = source("main/java/app/inku/mobile/ui/InkuViewModel.kt")
        val uiLanguageCalls = Regex(
            """uiLang = (?:(?:current|cycle)\.uiLanguage\.code|input\.uiLanguageCode)""",
        ).findAll(viewModel).count()
        assertEquals(
            "every screen call that starts a drawing must send the ui language",
            7,
            uiLanguageCalls,
        )
        // Without `auto` the resolution never reaches the fallback, so the wire
        // above would be carrying a value nothing ever reads. The web sends a
        // constant `instruction_lang: 'auto'` on every paint (`+page.svelte:329`).
        assertEquals(
            "every one of those calls must also request auto",
            uiLanguageCalls,
            Regex("""instructionLang = InstructionLanguages\.AUTO""").findAll(viewModel).count(),
        )
    }

    /**
     * T6 (contract's stage 3, persistence): the choice is written to the
     * settings table under the server's key name, and read back at startup.
     */
    @Test
    fun testTheChoiceIsPersistedAndRestored() {
        val viewModel = source("main/java/app/inku/mobile/ui/InkuViewModel.kt")
        assertEquals("the key must be the server's name", "ui_lang", SETTING_KEY_UI_LANGUAGE)
        assertTrue(
            "setUiLanguage must persist the choice",
            Regex("""fun setUiLanguage\([\s\S]{0,400}?persistSetting\(SETTING_KEY_UI_LANGUAGE""")
                .containsMatchIn(viewModel),
        )
        assertTrue(
            "restorePersistedSettings must read the key back",
            Regex("""settings\[SETTING_KEY_UI_LANGUAGE\]""").containsMatchIn(viewModel),
        )
        assertTrue(
            "the restored value must reach the state",
            Regex("""uiLanguage = uiLanguage,""").containsMatchIn(viewModel),
        )
    }

    /** T7: the reader can reach the choice, and it is provided to the tree once. */
    @Test
    fun testTheSettingsScreenOffersTheChoiceAndTheTreeIsProvided() {
        val app = source("main/java/app/inku/mobile/ui/InkuApp.kt")
        assertTrue(
            "the Misc settings pane must offer setUiLanguage",
            Regex("""viewModel\.setUiLanguage\(""").containsMatchIn(app),
        )
        // Both locals are provided from the SAME state field. Asserting only the
        // language would let the pack be provided from a constant, and then the
        // saijiki would follow the setting while the wording never moved.
        assertTrue(
            "the tree must be given the state's language",
            Regex("""CompositionLocalProvider\([\s\S]{0,200}?LocalUiLanguage provides state\.uiLanguage,""")
                .containsMatchIn(app),
        )
        assertTrue(
            "the tree must be given the pack for that same language",
            Regex("""LocalStrings provides stringsFor\(state\.uiLanguage\),""").containsMatchIn(app),
        )
    }

    /** T8: the carried field exists and defaults to "the caller did not say". */
    @Test
    fun testTheRequestCarriesTheUiLanguage() {
        assertEquals(null, PaintRequest(
            description = "x",
            originalText = "x",
            stage1Model = "m",
            stage2Model = "m",
            colorCatalogId = "default",
            canvasAspect = "square",
            autoRepair = true,
        ).uiLang)
        assertEquals("en", PaintRequest(
            description = "x",
            originalText = "x",
            stage1Model = "m",
            stage2Model = "m",
            colorCatalogId = "default",
            canvasAspect = "square",
            autoRepair = true,
            uiLang = "en",
        ).uiLang)
    }
}
