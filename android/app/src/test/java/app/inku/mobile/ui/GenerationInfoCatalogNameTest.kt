package app.inku.mobile.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class GenerationInfoCatalogNameTest {

    @Test
    fun savedNameIsShownWithTheIdFromTheSameSnapshot() {
        assertEquals(
            "Lantern & Dew (ink_season)",
            generationInfoColorCatalogValue(
                metadata(name = "Lantern & Dew", id = "ink_season"),
                fallbackCatalogId = "fallback",
            ),
        )
    }

    @Test
    fun matchingOrMissingNameDoesNotDuplicateTheSnapshotId() {
        assertEquals(
            "ink_season",
            generationInfoColorCatalogValue(
                metadata(name = "ink_season", id = "ink_season"),
                fallbackCatalogId = "fallback",
            ),
        )
        assertEquals(
            "ink_season",
            generationInfoColorCatalogValue(
                metadata(name = "", id = "ink_season"),
                fallbackCatalogId = "fallback",
            ),
        )
    }

    @Test
    fun absentSnapshotKeepsTheExistingFallbackId() {
        assertEquals("fallback", generationInfoColorCatalogValue("{}", "fallback"))
        assertEquals(
            "fallback",
            generationInfoColorCatalogValue(
                """{"render_color_catalog_name":"Lantern & Dew","render_color_map":{}}""",
                "fallback",
            ),
        )
        assertEquals("fallback", generationInfoColorCatalogValue("{broken", "fallback"))
    }

    @Test
    fun catalogSubAloneAddsNoDisplayText() {
        assertEquals(
            "ink_season",
            generationInfoColorCatalogValue(
                metadata(name = null, id = "ink_season", sub = "night air, lantern, dew"),
                fallbackCatalogId = "fallback",
            ),
        )
    }

    private fun metadata(name: String?, id: String, sub: String? = null): String = buildString {
        append("{\"render_color_catalog_id\":\"")
        append(id)
        append("\"")
        if (name != null) {
            append(",\"render_color_catalog_name\":\"")
            append(name)
            append("\"")
        }
        if (sub != null) {
            append(",\"render_color_catalog_sub\":\"")
            append(sub)
            append("\"")
        }
        append(",\"render_color_map\":{\"ink\":\"#112233\"}}")
    }
}
