package app.inku.mobile.render

import app.inku.mobile.data.model.workColorSnapshot
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class WorkColorSnapshotTest {
    private fun metadata(
        renderCatalogId: String? = null,
        catalogId: String? = null,
        colorMap: JSONObject? = JSONObject().put("red", "#aa0000"),
    ): String = JSONObject().apply {
        renderCatalogId?.let { put("render_color_catalog_id", it) }
        catalogId?.let { put("catalog_id", it) }
        colorMap?.let { put("render_color_map", it) }
    }.toString()

    @Test
    fun missingOrEmptyColorMapMeansNoSnapshot() {
        assertNull(workColorSnapshot(metadata(colorMap = null)))
        assertNull(workColorSnapshot(metadata(colorMap = JSONObject())))
    }

    @Test
    fun renderedCatalogIdWinsThenStoredCatalogThenDefault() {
        assertEquals(
            "rendered-with",
            workColorSnapshot(metadata("rendered-with", "catalog"))?.catalogId,
        )
        assertEquals("catalog", workColorSnapshot(metadata(catalogId = "catalog"))?.catalogId)
        assertEquals("default", workColorSnapshot(metadata())?.catalogId)
    }

    @Test
    fun snapshotKeepsRecordedColorsAndLabels() {
        val value = JSONObject(metadata())
            .put("render_color_catalog_name", "Recorded Name")
            .put("render_color_catalog_sub", "Recorded Subtitle")
        val snapshot = workColorSnapshot(value.toString())

        assertEquals(mapOf("red" to "#aa0000"), snapshot?.colorMap)
        assertEquals("Recorded Name", snapshot?.catalogName)
        assertEquals("Recorded Subtitle", snapshot?.catalogSub)
    }
}
