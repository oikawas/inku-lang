package app.inku.mobile.pipeline

import app.inku.mobile.data.model.WorkColorSnapshot

import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.render.SvgRenderer

class InkuPipeline(
    private val stage1Provider: ModelProvider,
    private val stage2Provider: ModelProvider,
    private val renderer: SvgRenderer,
) {
    suspend fun paint(request: PaintRequest): PaintResult {
        val normalizedDdl = interpret(request)
        val expandedDdl = expand(normalizedDdl)
        val scoreJson = compose(request, expandedDdl)
        val render = renderer.render(
            RenderRequest(
                scoreJson = scoreJson,
                colorCatalogId = request.colorCatalogId,
                canvasAspect = request.canvasAspect,
                svgProfile = "display",
                compositionSeed = request.compositionSeed,
                wild = request.renderWild,
            ),
        )
        return PaintResult(
            originalInput = request.description,
            normalizedDdl = normalizedDdl,
            expandedDdl = expandedDdl,
            scoreJson = scoreJson,
            displaySvg = render.svg,
            renderMetadataJson = render.metadataJson,
            renderHash = render.renderHash,
            renderHashShort = render.renderHash.takeLast(4).uppercase(),
        )
    }

    private suspend fun interpret(request: PaintRequest): String {
        return stage1Provider.generate(
            app.inku.mobile.llm.ModelRequest(
                modelId = request.stage1Model,
                prompt = request.description,
                temperature = 0.2,
                maxTokens = 1200,
            ),
        ).text
    }

    private fun expand(normalizedDdl: String): String {
        return normalizedDdl
    }

    private suspend fun compose(request: PaintRequest, expandedDdl: String): String {
        return stage2Provider.generate(
            app.inku.mobile.llm.ModelRequest(
                modelId = request.stage2Model,
                prompt = expandedDdl,
                temperature = 0.1,
                maxTokens = 4000,
            ),
        ).text
    }
}

/**
 * The five seeds are the server's, with its names and its types
 * (`api_core/models.py:14-15`, `:42-45`): `interpretation_seed` is a string,
 * `variation_amplitude` is a string, the other three are numbers. `null` means
 * "not given" for every one of them, which is the server's `None`; a caller that
 * wants a specific value says so.
 *
 * `Long` rather than `Int` because the server's own values do not fit one:
 * `new_render_seed()` is `secrets.randbits(53)`, and a touch seed derived from
 * words (`_render_seed_from_text`, `rendering.py:324`) is a full unsigned 64-bit
 * integer. That one is held here as the same 64 bits, and printed unsigned
 * wherever it becomes part of a hash key, so it agrees with Python's int.
 */
data class PaintRequest(
    val description: String,
    val originalText: String = description,
    val stage1Model: String,
    val stage2Model: String,
    val colorCatalogId: String,
    val canvasAspect: String,
    val autoRepair: Boolean,
    val litertStage1PromptOptimization: Boolean = false,
    val renderSeed: Long? = null,
    val compositionSeed: Long? = null,
    val interpretationSeed: String? = null,
    val variationAmplitude: String? = null,
    val variationSeed: Long? = null,
    val seedText: String? = null,
    /**
     * The instruction language the caller asks for, with the server's key name
     * (`instruction_lang`) and the server's three requestable words: `ja`, `en`
     * or `auto`. `null` is "the caller did not say", which is the server's
     * `None` -- `normalize_instruction_lang` turns both into the default.
     *
     * This is the request, not the answer: what the drawing was made in comes
     * back as [PaintResult.instructionLangResolved], because those are two
     * quantities and the server stores them in two columns.
     */
    val instructionLang: String? = null,
    /**
     * The language the interface is speaking, with the server's key name
     * (`ui_lang`).
     *
     * It is not the language the work is drawn in and it does not override
     * [instructionLang]: the server only consults it when the request asked for
     * `auto` and the text names neither script, and then it stands in as the
     * fallback (`api_core/common.py:68-70`). The web sends it on every paint
     * (`+page.svelte:2840`) alongside a constant `instruction_lang: 'auto'`
     * (`:329`). `null` is "the caller did not say", which the server reads the
     * same way it reads `"fr"` -- as Japanese.
     */
    val uiLang: String? = null,
    /**
     * 写生 (Stage 0.5). The server's three request fields in one value
     * (`render.py:333-336`). The default is the layer switched off, which is
     * `sketch: bool = Field(default=False)` there: a caller that says nothing
     * gets the plain path, and it is the screen that carries the author's
     * default of `fine`.
     */
    val sketch: SketchInput = SketchInput(),
    val workColorSnapshot: WorkColorSnapshot? = null,
    val renderWild: Boolean? = null,
)

/**
 * [renderSeed] is what the drawing was actually performed with, not what was
 * asked for: the request may leave it out, and the layer above the renderer
 * allocates one, the way `_render_with_metadata` does (`rendering.py:294`). The
 * other four are carried back unchanged so the save can record them.
 */
data class PaintResult(
    val originalInput: String,
    val normalizedDdl: String,
    val expandedDdl: String,
    val scoreJson: String,
    val displaySvg: String,
    val renderMetadataJson: String,
    val renderHash: String,
    val renderHashShort: String,
    val renderSeed: Long? = null,
    val compositionSeed: Long? = null,
    val interpretationSeed: String? = null,
    val variationAmplitude: String? = null,
    val variationSeed: Long? = null,
    val seedText: String? = null,
    /**
     * What was asked for and what it resolved to, carried back so the save can
     * write both columns (`db.py:2088-2089`). The requested one is the word the
     * caller used -- `auto` stays `auto` here -- and the resolved one is the
     * language the prompts were actually chosen with.
     *
     * Both are `null` on a path that read no prompt at all. The server resolves
     * the language at exactly the three endpoints that run a stage plus the demo
     * one (`render.py:1317`, `:1486`, `:1735`, `public.py:241`); replaying a
     * Score is not among them, and its columns are NULL rather than a language
     * nobody chose.
     */
    val instructionLangRequested: String? = null,
    val instructionLangResolved: String? = null,
    /**
     * 写生 (Stage 0.5), as the row records it (`render.py:1917-1922`,
     * `:1975-1977`).
     *
     * [sketchText] and [sketchGrain] are what the *layer produced*, and they are
     * absent when the layer fell back: a fallback carries the description
     * itself, and writing that into the prose column would make a work that
     * never went through the layer indistinguishable from one that did.
     * [sketchState] is present on every path, and it is the only trace a
     * fallback leaves -- which is the point of having a state column at all.
     */
    val sketchText: String? = null,
    val sketchGrain: String? = null,
    val sketchState: String? = null,
)

data class InterpretResult(
    val originalInput: String,
    val normalizedDdl: String,
    val expandedDdl: String,
    val ddlForDisplay: String,
    val instructionLangRequested: String? = null,
    val instructionLangResolved: String? = null,
    val tokensIn: Int? = null,
    val tokensOut: Int? = null,
    val fallbackUsed: Boolean = false,
    val fallbackReasons: List<String> = emptyList(),
    /**
     * 写生 (Stage 0.5), which runs here and nowhere else on a describe-screen
     * submit: this is the step that reads the description. The server's
     * `/api/interpret` answers the same way (`render.py:1558-1560`), and the
     * caller hands these straight to the composing step so the layer is not
     * asked twice for a prose it cannot reproduce.
     *
     * [sketchText] and [sketchGrain] are absent when the layer fell back;
     * [sketchState] is always present and is the only trace that leaves.
     */
    val sketchText: String? = null,
    val sketchGrain: String? = null,
    val sketchState: String? = null,
)

/**
 * [renderSeed] is the seed the performance is drawn with. The server passes it
 * as an argument to `renderer.render` (`renderer.py:2990`) rather than hiding it
 * in the Score, and the caller has already decided on a value by then; a `null`
 * here falls back to a seed the Score carries, which is how a saved work replays.
 */
data class RenderRequest(
    val scoreJson: String,
    val colorCatalogId: String,
    val canvasAspect: String,
    val svgProfile: String,
    val renderSeed: Long? = null,
    // engine 23: the seed the placement follows, split off the performance
    // seed. It travels beside the score rather than inside it, the way
    // `renderer.render(..., composition_seed=...)` takes it on the server.
    val compositionSeed: Long? = null,
    val workColorSnapshot: WorkColorSnapshot? = null,
    /** Explicit host render option. `null` keeps historical Score fallback semantics. */
    val wild: Boolean? = null,
)
