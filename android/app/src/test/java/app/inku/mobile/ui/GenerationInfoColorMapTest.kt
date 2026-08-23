package app.inku.mobile.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class GenerationInfoColorMapTest {

    @Test
    fun savedColorMapIsSortedByWordAndPreservesCodesByteForByte() {
        val entries = generationInfoColorMapEntries(
            """
                {
                  "render_color_map": {
                    "sky": "not-a-color",
                    "accent": "#Aa00Ff",
                    "ground": " rgb(1, 2, 3) "
                  }
                }
            """.trimIndent(),
        )

        assertEquals(
            listOf(
                GenerationInfoColorMapEntry("accent", "#Aa00Ff"),
                GenerationInfoColorMapEntry("ground", " rgb(1, 2, 3) "),
                GenerationInfoColorMapEntry("sky", "not-a-color"),
            ),
            entries,
        )
    }

    @Test
    fun missingEmptyOrBrokenMetadataReturnsNoEntries() {
        assertTrue(generationInfoColorMapEntries("{}").isEmpty())
        assertTrue(generationInfoColorMapEntries("{\"render_color_map\":{}}").isEmpty())
        assertTrue(generationInfoColorMapEntries("{broken").isEmpty())
    }
}
