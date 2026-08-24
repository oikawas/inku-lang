package app.inku.mobile.pipeline

import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import app.inku.mobile.render.DeterministicTestSvgRenderer
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * T-4, T-4b and T-5 of 契約 android-compares-models-and-languages.
 *
 * These walk the real `interpret` and `composeFromDdl`, because the thing being
 * checked is the wire and not the chooser: a test that asked
 * `stage2SystemPromptFor` directly would stay green with the wire cut. What the
 * stages hand a model is captured by standing in for the model.
 */
class InstructionLanguageWiringTest {

    private fun pipeline(provider: ModelProvider) = LocalFallbackPipeline(
        renderer = DeterministicTestSvgRenderer(),
        modelProvider = provider,
    )

    /**
     * Records every system prompt a stage sends, in order, and answers Stage 1
     * with a usable DDL: a LiteRT id is an explicit provider, and an explicit
     * provider that returns nothing usable raises rather than falling back.
     */
    private class CapturingProvider(
        private val reply: (ModelRequest) -> String = { request ->
            if (request.tool == null) "細い線を五本、中央付近に置く。" else ""
        },
    ) : ModelProvider {
        override val providerId: String = "test"
        val systemPrompts = mutableListOf<String>()
        val ddlSent = mutableListOf<String>()

        override suspend fun generate(request: ModelRequest): ModelResponse {
            systemPrompts += request.systemInstruction.orEmpty()
            ddlSent += request.prompt
            return ModelResponse(text = reply(request), modelId = request.modelId)
        }
    }

    /**
     * A model id with no provider prefix, so an unusable reply falls back to the
     * deterministic path instead of throwing: the prompt has already been sent
     * by then, which is all these tests read.
     */
    private fun request(text: String, lang: String?) = PaintRequest(
        description = text,
        originalText = text,
        stage1Model = "test-model",
        stage2Model = "test-model",
        colorCatalogId = "default",
        canvasAspect = "square",
        autoRepair = true,
        instructionLang = lang,
    )

    private val japanese = "夕暮れの水面に細い線を五本引く"
    private val english = "draw five thin lines across a quiet river at dusk"

    // ── T-4: Stage 1 ──────────────────────────────────────────

    /**
     * `en` reaches Stage 1: the English prefix and the English example pool are
     * what the model is handed (`WebDdlSpec.kt:141`, `:152`). The prompt text
     * itself is compared -- not a flag, and not the fact that two prompts
     * differ.
     */
    @Test
    fun `an english request reaches stage 1's english prompt`() {
        val provider = CapturingProvider()
        val pipeline = pipeline(provider)

        runBlocking { pipeline.interpret(request(english, "en")) }

        val sent = provider.systemPrompts.first()
        assertEquals(WebDdlSpec.buildStage1SystemPrompt(english, "en"), sent)
        assertNotEquals(WebDdlSpec.buildStage1SystemPrompt(english, "ja"), sent)
        assertTrue(sent.startsWith(WebDdlSpec.stage1SystemPromptForDisplay("en")))
        assertTrue(sent.contains("# Examples"))
    }

    @Test
    fun `a japanese request reaches stage 1's japanese prompt`() {
        val provider = CapturingProvider()
        val pipeline = pipeline(provider)

        runBlocking { pipeline.interpret(request(japanese, "ja")) }

        val sent = provider.systemPrompts.first()
        assertEquals(WebDdlSpec.buildStage1SystemPrompt(japanese, "ja"), sent)
        assertTrue(sent.startsWith(WebDdlSpec.stage1SystemPromptForDisplay("ja")))
    }

    /**
     * `auto` is resolved from the author's own words before Stage 1 is asked, so
     * an English description reaches the English prompt without anyone saying
     * `en`. This is the whole path -- resolve, then select -- in one assertion.
     */
    @Test
    fun `auto resolves from the text and stage 1 follows`() {
        val provider = CapturingProvider()
        val pipeline = pipeline(provider)

        val result = runBlocking { pipeline.interpret(request(english, "auto")) }

        assertEquals("auto", result.instructionLangRequested)
        assertEquals("en", result.instructionLangResolved)
        assertEquals(WebDdlSpec.buildStage1SystemPrompt(english, "en"), provider.systemPrompts.first())
    }

    /** A caller that says nothing gets the default, not an error and not English. */
    @Test
    fun `an unstated language is the default`() {
        val provider = CapturingProvider()
        val pipeline = pipeline(provider)

        val result = runBlocking { pipeline.interpret(request(english, null)) }

        assertEquals("ja", result.instructionLangRequested)
        assertEquals("ja", result.instructionLangResolved)
        assertEquals(WebDdlSpec.buildStage1SystemPrompt(english, "ja"), provider.systemPrompts.first())
    }

    // ── T-5: Stage 2 ──────────────────────────────────────────

    /**
     * The twin of T-4. `STAGE2_SYSTEM_PROMPT_EN` had no reader in the product
     * before this contract; a test on Stage 1 alone would pass an
     * implementation that wired one stage and left the other in Japanese.
     */
    @Test
    fun `an english request reaches stage 2's english prompt`() {
        val provider = CapturingProvider()
        val pipeline = pipeline(provider)

        runBlocking { pipeline.composeFromDdl("draw five thin lines.", request(english, "en")) }

        val sent = provider.systemPrompts.first()
        assertEquals(WebDdlSpec.STAGE2_SYSTEM_PROMPT_EN, sent)
        assertNotEquals(WebDdlSpec.STAGE2_SYSTEM_PROMPT_JA, sent)
    }

    @Test
    fun `a japanese request reaches stage 2's japanese prompt`() {
        val provider = CapturingProvider()
        val pipeline = pipeline(provider)

        runBlocking { pipeline.composeFromDdl("細い線を五本引く。", request(japanese, "ja")) }

        assertEquals(WebDdlSpec.STAGE2_SYSTEM_PROMPT_JA, provider.systemPrompts.first())
    }

    /**
     * The two stages can be asked in two different languages, which is what the
     * language inspection does. Stage 1 in Japanese, Stage 2 in English, one
     * after the other, through the same two entry points web uses.
     */
    @Test
    fun `the two stages take their languages separately`() {
        val provider = CapturingProvider()
        val pipeline = pipeline(provider)

        runBlocking {
            val interpreted = pipeline.interpret(request(japanese, "ja"))
            pipeline.composeFromDdl(interpreted.ddlForDisplay, request(japanese, "en"))
        }

        assertEquals(WebDdlSpec.buildStage1SystemPrompt(japanese, "ja"), provider.systemPrompts.first())
        assertEquals(WebDdlSpec.STAGE2_SYSTEM_PROMPT_EN, provider.systemPrompts[1])
    }

    // ── T-4b: Stage 1.5 ───────────────────────────────────────

    /**
     * Stage 1.5 is chosen by the same resolved language the stages around it are
     * (`expand_intermediate_for_lang`, `render.py:889` / `:1542`). The expander
     * on this client already had both branches; only the wire was missing, and
     * this reads the DDL that reaches Stage 2 to see which branch ran.
     *
     * `avoidGrayBackground` is the visible half: the English branch rewrites a
     * grey background in English words, the Japanese branch in Japanese ones, so
     * the expanded DDL says which language expanded it.
     */
    @Test
    fun `stage 1 point 5 expands in the resolved language`() {
        val ddl = "Fill background with gray. Draw five thin lines."
        val provider = CapturingProvider()
        val pipeline = pipeline(provider)

        runBlocking { pipeline.composeFromDdl(ddl, request(english, "en")) }
        val expandedInEnglish = provider.ddlSent.first()

        assertEquals(
            WebDdlExpander.expandIntermediateDdl(ddl, lang = "en", contextText = english),
            expandedInEnglish,
        )
        assertNotEquals(
            WebDdlExpander.expandIntermediateDdl(ddl, lang = "ja", contextText = english),
            expandedInEnglish,
        )
    }

    @Test
    fun `stage 1 point 5 expands in japanese for a japanese work`() {
        val ddl = "背景を灰色で塗りつぶす。細い線を五本引く。"
        val provider = CapturingProvider()
        val pipeline = pipeline(provider)

        runBlocking { pipeline.composeFromDdl(ddl, request(japanese, "ja")) }

        assertEquals(
            WebDdlExpander.expandIntermediateDdl(ddl, lang = "ja", contextText = japanese),
            provider.ddlSent.first(),
        )
    }

    // ── The LiteRT crossing (段 1 の判断) ───────────────────────

    /**
     * The Android-only hole: `STAGE2_SYSTEM_PROMPT_JA_LITERT` has no English
     * twin. A LiteRT model asked for English gets the English prompt rather than
     * the shortened Japanese one -- the shortening is a size choice, and serving
     * it here would drop the language the author asked for.
     */
    @Test
    fun `a litert model asked for english gets the english prompt`() {
        val provider = CapturingProvider()
        val pipeline = pipeline(provider)
        val litert = request(english, "en").copy(
            stage1Model = "local-litert-lm:gemma",
            stage2Model = "local-litert-lm:gemma",
            litertStage1PromptOptimization = true,
        )

        runBlocking { pipeline.composeFromDdl("draw five thin lines.", litert) }

        assertEquals(WebDdlSpec.STAGE2_SYSTEM_PROMPT_EN, provider.systemPrompts.first())
    }

    /** In Japanese the shortened LiteRT prompts are still the ones that go. */
    @Test
    fun `a litert model in japanese keeps the shortened prompts`() {
        val provider = CapturingProvider()
        val pipeline = pipeline(provider)
        val litert = request(japanese, "ja").copy(
            stage1Model = "local-litert-lm:gemma",
            stage2Model = "local-litert-lm:gemma",
            litertStage1PromptOptimization = true,
        )

        runBlocking { pipeline.interpret(litert) }
        assertEquals(WebDdlSpec.buildStage1LiteRtSystemPrompt(japanese), provider.systemPrompts.first())

        runBlocking { pipeline.composeFromDdl("細い線を五本引く。", litert) }
        assertEquals(WebDdlSpec.STAGE2_SYSTEM_PROMPT_JA_LITERT, provider.systemPrompts[1])
        assertFalse(provider.systemPrompts[1] == WebDdlSpec.STAGE2_SYSTEM_PROMPT_JA)
    }
}
