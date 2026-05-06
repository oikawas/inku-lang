package app.inku.mobile.render

import app.inku.mobile.pipeline.RenderRequest

interface SvgRenderer {
    fun render(request: RenderRequest): RenderResult
}

data class RenderResult(
    val svg: String,
    val metadataJson: String,
    val renderHash: String,
)
