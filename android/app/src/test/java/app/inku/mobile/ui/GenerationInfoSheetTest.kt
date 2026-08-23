package app.inku.mobile.ui

import app.inku.mobile.data.db.HistoryItemEntity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class GenerationInfoSheetTest {

    @Test
    fun existingHistoryFieldsAreGroupedWithoutLineageOrTokenRows() {
        val item = historyItem(
            renderMetadataJson = """
                {
                  "render_engine_id": "inku-svg",
                  "render_engine_version": "38",
                  "render_canvas_aspect_ratio": 1.5
                }
            """.trimIndent(),
        )

        val sections = generationInfoSections(item)
        assertEquals(
            listOf(
                GenerationInfoSectionId.Sketch,
                GenerationInfoSectionId.Interpretation,
                GenerationInfoSectionId.Performance,
                GenerationInfoSectionId.Identity,
                GenerationInfoSectionId.Run,
            ),
            sections.map { it.id },
        )
        val rows = sections.flatMap { it.rows }.associate { it.field to it.value }
        assertEquals("fine", rows[GenerationInfoField.SketchGrain])
        assertEquals("fine", rows[GenerationInfoField.SketchState])
        assertEquals("stage-1-model", rows[GenerationInfoField.Stage1Model])
        assertEquals("stage-2-model", rows[GenerationInfoField.Stage2Model])
        assertEquals("auto", rows[GenerationInfoField.LanguageRequested])
        assertEquals("ja", rows[GenerationInfoField.LanguageResolved])
        assertEquals("101", rows[GenerationInfoField.InterpretationSeed])
        assertEquals("medium", rows[GenerationInfoField.VariationAmplitude])
        assertEquals("202", rows[GenerationInfoField.VariationSeed])
        assertEquals("303", rows[GenerationInfoField.CompositionSeed])
        assertEquals("404", rows[GenerationInfoField.RenderSeed])
        assertEquals("seed words", rows[GenerationInfoField.SeedText])
        assertEquals("true", rows[GenerationInfoField.RenderWild])
        assertEquals("default", rows[GenerationInfoField.ColorCatalog])
        assertEquals("landscape", rows[GenerationInfoField.CanvasAspect])
        assertEquals("1.5", rows[GenerationInfoField.CanvasRatio])
        assertEquals("render-hash", rows[GenerationInfoField.RenderHash])
        assertEquals("inku-svg", rows[GenerationInfoField.RenderEngineId])
        assertEquals("38", rows[GenerationInfoField.RenderEngineVersion])
        assertEquals("2500 ms", rows[GenerationInfoField.Elapsed])

        val fieldNames = rows.keys.map { it.name.lowercase() }
        listOf("generation", "derivation", "comment", "batch", "token").forEach { excluded ->
            assertFalse(fieldNames.any { excluded in it })
        }
    }

    @Test
    fun brokenMetadataReturnsFallbacksWithoutDroppingTheSections() {
        val sections = generationInfoSections(
            historyItem(
                renderMetadataJson = "{broken",
                stage1Model = null,
                renderWild = null,
                elapsedMs = null,
            ),
        )
        val rows = sections.flatMap { it.rows }.associate { it.field to it.value }

        assertEquals(5, sections.size)
        assertEquals("—", rows[GenerationInfoField.Stage1Model])
        assertEquals("—", rows[GenerationInfoField.RenderWild])
        assertEquals("—", rows[GenerationInfoField.RenderEngineId])
        assertEquals("—", rows[GenerationInfoField.RenderEngineVersion])
        assertEquals("—", rows[GenerationInfoField.CanvasRatio])
        assertEquals("—", rows[GenerationInfoField.Elapsed])
        assertTrue(rows.values.none { it.contains("broken") })
    }

    private fun historyItem(
        renderMetadataJson: String,
        stage1Model: String? = "stage-1-model",
        renderWild: Boolean? = true,
        elapsedMs: Long? = 2500L,
    ): HistoryItemEntity = HistoryItemEntity(
        id = "history-id",
        createdAt = 1_722_470_400_000L,
        updatedAt = 1_722_470_400_000L,
        originalInput = "雲を描く",
        normalizedDdl = "雲",
        expandedDdl = null,
        scoreJson = "{}",
        displaySvg = "<svg/>",
        stage1Model = stage1Model,
        stage2Model = "stage-2-model",
        renderMetadataJson = renderMetadataJson,
        renderHash = "render-hash",
        renderHashShort = "HASH",
        colorCatalogId = "default",
        canvasAspect = "landscape",
        starred = false,
        trashed = false,
        elapsedMs = elapsedMs,
        tokenMetadataJson = "{\"input\":12,\"output\":34}",
        renderWild = renderWild,
        renderSeed = "404",
        compositionSeed = "303",
        interpretationSeed = "101",
        variationAmplitude = "medium",
        variationSeed = "202",
        seedText = "seed words",
        instructionLangRequested = "auto",
        instructionLangResolved = "ja",
        sketchGrain = "fine",
        sketchState = "fine",
    )
}
