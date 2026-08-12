package app.inku.mobile.render

import app.inku.mobile.data.model.ColorCatalog
import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.data.model.WorkColorSnapshot
import app.inku.mobile.data.model.workColorSnapshot
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import app.inku.mobile.pipeline.LocalFallbackPipeline
import app.inku.mobile.pipeline.PaintRequest
import app.inku.mobile.pipeline.RenderRequest
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Test

class WorkColorSnapshotTest {
    private val score = """
        {"version":"0.1.0","canvas":"square","background":"custom","instructions":[
          {"primitive":"line","from":[0.2,0.5],"to":[0.8,0.5],"color":"custom","weight":"rotring"}
        ]}
    """.trimIndent()

    private fun catalog(red: String): ColorCatalog {
        val base = ColorCatalogs.get("default")
        return base.copy(map = base.map + ("custom" to red))
    }

    private fun request(
        snapshot: WorkColorSnapshot? = null,
        catalogId: String = "default",
    ) = PaintRequest(
        description = "red line",
        stage1Model = "stage1",
        stage2Model = "stage2",
        colorCatalogId = catalogId,
        canvasAspect = "square",
        autoRepair = false,
        renderSeed = 4242L,
        workColorSnapshot = snapshot,
    )

    private fun metadata(
        renderCatalogId: String? = null,
        catalogId: String? = null,
        colorMap: JSONObject? = JSONObject(ColorCatalogs.get("default").renderMap),
    ): String = JSONObject().apply {
        if (renderCatalogId != null) put("render_color_catalog_id", renderCatalogId)
        if (catalogId != null) put("catalog_id", catalogId)
        if (colorMap != null) put("render_color_map", colorMap)
    }.toString()

    @Test
    fun t1_catalogChangesDoNotChangeAWorkWithAColorSnapshot() {
        var current = catalog("#aa0000")
        val pipeline = LocalFallbackPipeline(DefaultSvgRenderer { current })
        val snapshot = WorkColorSnapshot("default", current.renderMap)
        val before = pipeline.renderFromScore(score, request(snapshot))

        current = catalog("#00aa00")
        val after = pipeline.renderFromScore(score, request(snapshot))

        assertEquals(before.displaySvg, after.displaySvg)
    }

    @Test
    fun t2_changingTheWorkSnapshotChangesTheDrawing() {
        val current = catalog("#aa0000")
        val pipeline = LocalFallbackPipeline(DefaultSvgRenderer { current })
        val before = pipeline.renderFromScore(
            score,
            request(WorkColorSnapshot("default", current.renderMap)),
        )
        val changed = pipeline.renderFromScore(
            score,
            request(WorkColorSnapshot("default", catalog("#00aa00").renderMap)),
        )

        assertNotEquals(before.displaySvg, changed.displaySvg)
    }

    @Test
    fun t3_missingColorMapMeansNoSnapshot() {
        assertNull(workColorSnapshot(metadata(colorMap = null)))
    }

    @Test
    fun t4_emptyColorMapMeansNoSnapshot() {
        assertNull(workColorSnapshot(metadata(colorMap = JSONObject())))
    }

private fun renderRequest(
    scoreJson: String = score,
    catalogId: String = "default",
    snapshot: WorkColorSnapshot? = null,
) = RenderRequest(
    scoreJson = scoreJson,
    colorCatalogId = catalogId,
    canvasAspect = "square",
    svgProfile = "display",
    renderSeed = 4242L,
    workColorSnapshot = snapshot,
)

private fun assertRenderedCatalogId(expected: String, storedMetadata: String) {
    val rendered = DefaultSvgRenderer().render(
        renderRequest(snapshot = workColorSnapshot(storedMetadata)),
    )
    assertEquals(expected, JSONObject(rendered.metadataJson).getString("render_color_catalog_id"))
}
    
    @Test
    fun t5_renderCatalogIdWins() {
        assertRenderedCatalogId("rendered-with", metadata(renderCatalogId = "rendered-with", catalogId = "catalog"))
    }
    
    @Test
    fun t5_catalogIdIsTheFirstFallback() {
        assertRenderedCatalogId("catalog", metadata(catalogId = "catalog"))
    }
    
    @Test
    fun t5_defaultIsTheLastFallback() {
        assertRenderedCatalogId("default", metadata())
    }
    
@Test
fun t6_snapshotAndMatchingCurrentDefinitionUseTheSameSeedInputs() {
    val current = ColorCatalogs.get("ink_season")
    val abstractScore = score.replace("custom", "red")
    val renderer = DefaultSvgRenderer { current }
    val currentDrawing = renderer.render(renderRequest(abstractScore, current.id))
    val snapshotDrawing = renderer.render(
        renderRequest(abstractScore, current.id, WorkColorSnapshot(current.id, current.renderMap)),
    )

    assertEquals(currentDrawing.svg, snapshotDrawing.svg)
}
    
    @Test
    fun t7_newDrawingRoutesDoNotReadAWorkSnapshot() {
        val provider = object : ModelProvider {
            override val providerId = "test"
            override suspend fun generate(request: ModelRequest) = ModelResponse("", request.modelId)
        }
        val pipeline = LocalFallbackPipeline(modelProvider = provider)
        val withoutSnapshot = runBlocking { pipeline.composeFromDdl("中央に赤い線を一本引く。", request()) }
        val changedMap = ColorCatalogs.get("default").renderMap.mapValues { "#00aa00" }
        val withSnapshot = runBlocking {
            pipeline.composeFromDdl(
                "中央に赤い線を一本引く。",
                request(WorkColorSnapshot("default", changedMap)),
            )
        }
    
        assertEquals(withoutSnapshot.displaySvg, withSnapshot.displaySvg)
    }

}
