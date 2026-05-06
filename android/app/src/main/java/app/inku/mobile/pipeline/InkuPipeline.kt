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

data class PaintRequest(
    val description: String,
    val stage1Model: String,
    val stage2Model: String,
    val colorCatalogId: String,
    val canvasAspect: String,
    val autoRepair: Boolean,
)

data class PaintResult(
    val originalInput: String,
    val normalizedDdl: String,
    val expandedDdl: String,
    val scoreJson: String,
    val displaySvg: String,
    val renderMetadataJson: String,
    val renderHash: String,
    val renderHashShort: String,
)

data class RenderRequest(
    val scoreJson: String,
    val colorCatalogId: String,
    val canvasAspect: String,
    val svgProfile: String,
)
