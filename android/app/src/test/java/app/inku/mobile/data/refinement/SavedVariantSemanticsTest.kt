package app.inku.mobile.data.refinement

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SavedVariantSemanticsTest {
    @Test
    fun colorPagesExcludeVisibleAssignmentAndComposePreviousRecolor() {
        val map = mapOf(
            "palette:a" to "#111111", "palette:b" to "#222222", "palette:c" to "#333333",
            "recolor:#111111" to "#222222",
        )
        // The style declaration wins over the direct fill, as it does in the saved SVG.
        val arrangements = SavedColorArrangements.fromSaved(
            "<svg><path fill=\"#111111\" style=\"fill:#222222\"/></svg>", map, "work",
        )
        assertEquals(ColorArrangementPage(listOf(0, 1), null, 2), arrangements.page())
        val recolors = (0..1).map { arrangements.colorMap(map, it)["recolor:#111111"] }.toSet()
        assertEquals(setOf(null, "#333333"), recolors)
        assertEquals("#111111", arrangements.colorMap(map, 0)["palette:a"])
    }

    @Test
    fun colorPageStopsAtEightAndContinuesWithoutRepeating() {
        val map = (1..4).associate { "palette:$it" to "#00000$it" }
        val arrangements = SavedColorArrangements.fromSaved(
            "<svg><path fill=\"#000001\" stroke=\"#000002\"/></svg>", map, "work",
        )
        assertEquals((0..7).toList(), arrangements.page().entries)
        assertEquals(8, arrangements.page().nextCursor)
        assertEquals((8..10).toList(), arrangements.page(8).entries)
        assertNull(arrangements.page(8).nextCursor)
        assertEquals(11, arrangements.total)
        val assignments = (0 until arrangements.total).map { index ->
            val colors = arrangements.colorMap(map, index)
            (colors["recolor:#000001"] ?: "#000001") to (colors["recolor:#000002"] ?: "#000002")
        }
        assertEquals(11, assignments.toSet().size)
        assertFalse(assignments.contains("#000001" to "#000002"))
    }

    @Test
    fun groundChangesOnlySavedSupportAndItsInstructionSentence() {
        val parent = """{"version":2,"canvas":{"aspect":"square","ground":{"material":"paper","tone":3}},"instructions":[{"kind":"line"}]}"""
        val plan = GroundVariants.plan(parent)
        assertEquals("paper", plan.current)
        assertEquals(6, plan.entries.size)
        assertFalse(plan.entries.any { it.material == "paper" })
        val changed = JSONObject(GroundVariants.scoreWithGround(parent, "washi"))
        assertEquals("washi", changed.getJSONObject("canvas").getJSONObject("ground").getString("material"))
        assertEquals(3, changed.getJSONObject("canvas").getJSONObject("ground").getInt("tone"))
        assertEquals("line", changed.getJSONArray("instructions").getJSONObject(0).getString("kind"))
        assertEquals("和紙。\n中央に一本。", GroundVariants.ddlWithGround("紙。\n中央に一本。", "washi", "ja"))
        assertTrue(GroundVariants.plan("""{"canvas":"square"}""").entries.any { it.material == "paper" })
    }
}
