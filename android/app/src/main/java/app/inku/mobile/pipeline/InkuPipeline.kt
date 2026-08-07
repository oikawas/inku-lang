package app.inku.mobile.pipeline

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
)

data class InterpretResult(
    val originalInput: String,
    val normalizedDdl: String,
    val expandedDdl: String,
    val ddlForDisplay: String,
    val tokensIn: Int? = null,
    val tokensOut: Int? = null,
    val fallbackUsed: Boolean = false,
    val fallbackReasons: List<String> = emptyList(),
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
)
