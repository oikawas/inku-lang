package app.inku.mobile.pipeline

import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import app.inku.mobile.render.DeterministicTestSvgRenderer
import app.inku.mobile.render.RenderResult
import app.inku.mobile.render.SvgRenderer
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CameraNimDrawPipelineTest {
    @Test
    fun fixedSnapshotMakesExactlyOneStage1AndOneStage2Call() {
        val provider = SuccessfulProvider()
        val renderer = CapturingRenderer()
        val pipeline = LocalFallbackPipeline(renderer = renderer, modelProvider = provider)
        val request = cameraRequest()

        runBlocking { pipeline.paint(request) }

        assertEquals(2, provider.requests.size)
        assertEquals(listOf(request.stage1Model, request.stage2Model), provider.requests.map { it.modelId })
        assertEquals(1, provider.requests.count { it.tool == null })
        assertEquals(1, provider.requests.count { it.tool != null })
        assertEquals("vivid_material", renderer.request.colorCatalogId)
    }

    @Test
    fun explicitNimStage2DoesNotRetryOrFallBackWhenAutoRepairIsOff() {
        val provider = InvalidStage2Provider()
        val pipeline = LocalFallbackPipeline(
            renderer = DeterministicTestSvgRenderer(),
            modelProvider = provider,
        )
        val request = cameraRequest()

        val failure = runCatching {
            runBlocking { pipeline.composeFromDdl("赤い円を中央に置く。", request) }
        }.exceptionOrNull()

        assertTrue("invalid explicit Stage 2 must fail", failure != null)
        assertEquals("invalid explicit Stage 2 must make one provider call", 1, provider.calls)
    }

    private fun cameraRequest() = PaintRequest(
        description = "camera description",
        originalText = "camera description",
        stage1Model = "nvidia:google/gemma-4-31b-it",
        stage2Model = "nvidia:google/gemma-4-31b-it",
        colorCatalogId = "vivid_material",
        canvasAspect = "square",
        autoRepair = false,
        sketch = SketchInput(),
    )

    private class SuccessfulProvider : ModelProvider {
        override val providerId = "nvidia"
        val requests = mutableListOf<ModelRequest>()

        override suspend fun generate(request: ModelRequest): ModelResponse {
            requests += request
            val text = if (request.tool == null) {
                "赤い円を中央に置く。"
            } else {
                """{"canvas":"square","background":"white","instructions":[{"primitive":"circle","count":1}]}"""
            }
            return ModelResponse(text = text, modelId = request.modelId)
        }
    }

    private class InvalidStage2Provider : ModelProvider {
        override val providerId = "nvidia"
        var calls = 0

        override suspend fun generate(request: ModelRequest): ModelResponse {
            calls += 1
            return ModelResponse(text = "{}", modelId = request.modelId)
        }
    }

    private class CapturingRenderer : SvgRenderer {
        lateinit var request: RenderRequest

        override fun render(request: RenderRequest): RenderResult {
            this.request = request
            return RenderResult(
                svg = "<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>",
                metadataJson = """{"render_engine_id":"test","render_engine_version":"1","render_wild":false}""",
                renderHash = "camera-nim-test",
            )
        }
    }
}
