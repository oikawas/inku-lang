package app.inku.mobile.render

import app.inku.mobile.data.model.ColorCatalog
import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.data.model.WorkColorSnapshot
import app.inku.mobile.data.model.workColorSnapshot
import app.inku.mobile.pipeline.LocalFallbackPipeline
import app.inku.mobile.pipeline.PaintRequest
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

    private fun request(snapshot: WorkColorSnapshot? = null) = PaintRequest(
        description = "red line",
        stage1Model = "stage1",
        stage2Model = "stage2",
        colorCatalogId = "default",
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

    @Test
    fun t5_renderCatalogIdWins() {
        assertEquals(
            "rendered-with",
            workColorSnapshot(metadata(renderCatalogId = "rendered-with", catalogId = "catalog"))?.catalogId,
        )
    }

    @Test
    fun t5_catalogIdIsTheFirstFallback() {
        assertEquals(
            "catalog",
            workColorSnapshot(metadata(catalogId = "catalog"))?.catalogId,
        )
    }

    @Test
    fun t5_defaultIsTheLastFallback() {
        assertEquals(
            "default",
            workColorSnapshot(metadata())?.catalogId,
        )
    }

    @Test
    fun t6_snapshotAndMatchingCurrentDefinitionUseTheSameSeedInputs() {
        val current = catalog("#aa0000")
        val pipeline = LocalFallbackPipeline(DefaultSvgRenderer { current })
        val currentDrawing = pipeline.renderFromScore(score, request())
        val snapshotDrawing = pipeline.renderFromScore(
            score,
            request(WorkColorSnapshot("default", current.renderMap)),
        )

        assertEquals(currentDrawing.displaySvg, snapshotDrawing.displaySvg)
    }

    @Test
    fun t7_newDrawingsStillReadTheCurrentCatalog() {
        var current = catalog("#aa0000")
        val pipeline = LocalFallbackPipeline(DefaultSvgRenderer { current })
        val before = pipeline.renderFromScore(score, request())

        current = catalog("#00aa00")
        val after = pipeline.renderFromScore(score, request())

        assertNotEquals(before.displaySvg, after.displaySvg)
    }
}
