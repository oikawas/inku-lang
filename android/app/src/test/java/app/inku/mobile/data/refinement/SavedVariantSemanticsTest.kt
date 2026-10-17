package app.inku.mobile.data.refinement

import java.math.BigInteger
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SavedVariantSemanticsTest {
    @Test
    fun groundAdapterMapsPlanAndKeepsRenderScoreAndMetadataFromCore() {
        val score = """{"canvas":{"ground":{"material":"paper"}},"large":18446744073709551615}"""
        val binding = RecordingVariantsBinding { request ->
            if (request.contains("\"action\":\"ground_plan\""))
                """{"schema":"inku.saved-variants.v1","outcome":"ok","current":"paper",
                    "current_label_ja":"紙","current_label_en":"paper",
                    "entries":[{"material":"washi","label_ja":"和紙","label_en":"washi"}]}"""
            else """{"schema":"inku.saved-variants.v1","outcome":"ok","score":$score,
                "ddl":"和紙。\n中央に一本。","derivation_metadata":{"ground_material":"washi","parent_ground_material":"paper"}}"""
        }
        val plan = GroundVariants.plan(score, binding)
        assertEquals("paper", plan.current)
        assertEquals("紙", plan.currentLabelJa)
        assertEquals(listOf(GroundVariantEntry("washi", "和紙", "washi")), plan.entries)
        val rendered = GroundVariants.render(score, "紙。\n中央に一本。", "washi", "ja", binding)
        assertEquals(score, rendered.scoreJson)
        assertEquals("和紙。\n中央に一本。", rendered.ddl)
        assertEquals(mapOf("ground_material" to "washi", "parent_ground_material" to "paper"),
            rendered.derivationMetadata)
        assertTrue(binding.requests.last().contains("\"score\":$score"))
    }

    @Test
    fun colorAdapterKeepsWidePageIndicesAndMetadataNumberOrString() {
        val largestU64 = BigInteger("18446744073709551615")
        val beyondU64 = BigInteger("184467440737095516160")
        var render = false
        val binding = RecordingVariantsBinding { request ->
            if (request.contains("\"action\":\"color_plan\""))
                """{"schema":"inku.saved-variants.v1","outcome":"ok",
                    "entries":[{"index":18446744073709551615},{"index":"184467440737095516160"}],
                    "next_cursor":18446744073709551615,"total":"184467440737095516160"}"""
            else {
                render = true
                val indexValue = if (request.contains("\"index\":\"18446744073709551615\""))
                    "18446744073709551615" else "\"184467440737095516160\""
                """{"schema":"inku.saved-variants.v1","outcome":"ok",
                    "color_map":{"palette:a":"#112233"},
                    "derivation_metadata":{"color_arrangement_index":$indexValue,"catalog_id":"ink_season"}}"""
            }
        }
        val arrangements = SavedColorArrangements.fromSaved("<svg/>", mapOf("palette:a" to "#112233"), "work", binding)
        val page = arrangements.page(largestU64)
        assertEquals(listOf(largestU64, beyondU64), page.entries)
        assertEquals(largestU64, page.nextCursor)
        assertEquals(beyondU64, page.total)
        assertTrue(binding.requests.first().contains("\"cursor\":\"18446744073709551615\""))
        val numeric = arrangements.render(largestU64, "ink_season")
        assertEquals(largestU64, numeric.derivationMetadata["color_arrangement_index"])
        assertEquals("ink_season", numeric.derivationMetadata["catalog_id"])
        assertEquals("#112233", numeric.colorMap["palette:a"])
        val text = arrangements.render(beyondU64, "ink_season")
        assertEquals(beyondU64.toString(), text.derivationMetadata["color_arrangement_index"])
        assertTrue(render)
    }

    @Test
    fun missingGroundLabelsRemainNull() {
        val binding = RecordingVariantsBinding {
            """{"schema":"inku.saved-variants.v1","outcome":"ok","current":"unknown",
                "current_label_ja":null,"current_label_en":null,"entries":[]}"""
        }
        val plan = GroundVariants.plan("{}", binding)
        assertNull(plan.currentLabelJa)
        assertNull(plan.currentLabelEn)
    }
}
