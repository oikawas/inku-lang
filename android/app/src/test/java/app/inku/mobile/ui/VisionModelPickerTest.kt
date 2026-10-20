package app.inku.mobile.ui

import app.inku.mobile.data.CatalogModel
import app.inku.mobile.data.ModelCatalogLabel
import java.io.File
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The Vision chooser follows Web's `ModelCardPicker` and `modelMeta` (purpose badges, selectability, order). */
class VisionModelPickerTest {
    private val eol = ModelCatalogLabel("eol", "提供終了", "End of life", publishable = false)
    private val old = ModelCatalogLabel("older", "旧世代", "Older", publishable = true)

    private fun model(id: String, record: String, vararg labels: ModelCatalogLabel) =
        CatalogModel(id, JSONObject(record), labels.toList())

    @Test
    fun aPurposeTheModelCannotBeChosenForIsGreyed() {
        assertEquals(listOf("LLM" to false, "Vision" to true),
            modelPurposeBadges(model("a", """{"purposes":["vision"],"unsupported_purposes":["llm"]}""")))
        assertEquals(listOf("LLM" to true, "Vision" to true),
            modelPurposeBadges(model("b", """{"purposes":["llm","vision"]}""")))
        // Measured not to answer Vision: offered for it or not, it cannot be chosen.
        assertEquals(listOf("LLM" to true, "Vision" to false),
            modelPurposeBadges(model("c", """{"purposes":["llm","vision"],"unsupported_purposes":["vision"]}""")))
        // No purposes written reads as LLM, as on Web.
        assertEquals(listOf("LLM" to true, "Vision" to false), modelPurposeBadges(model("d", "{}")))
    }

    @Test
    fun aLabelThatKeepsItFromPublicationOrNoPurposeMakesItUnselectable() {
        assertTrue(isModelUnselectable(model("a", """{"purposes":["vision"]}""", eol)))
        assertTrue(isModelUnselectable(model("b", """{"purposes":[],"unsupported_purposes":["llm","vision"]}""")))
        assertFalse(isModelUnselectable(model("c", """{"purposes":["vision"]}""", old)))
        assertFalse(isModelUnselectable(model("d", """{"purposes":["vision"],"unsupported_purposes":["llm"]}""")))
    }

    @Test
    fun cardsAreOrderedSelectableFirstThenByTheVisionLevelThenByName() {
        val models = listOf(
            model("retired", """{"purposes":["vision"],"recommendation_vision":5}""", eol),
            model("modest", """{"purposes":["vision"],"recommendation_vision":2}"""),
            model("legacy", """{"purposes":["vision"],"recommendation_level":4}"""),
            model("best", """{"purposes":["vision"],"recommendation_vision":5,"recommendation_llm":1}"""),
            model("alpha", """{"purposes":["vision"],"recommendation_vision":2}"""),
        )
        assertEquals(listOf("best", "legacy", "alpha", "modest", "retired"),
            sortModels(models, "vision", { it }, { it.id }).map { it.id })
        assertEquals("★★★", modelRecommendationStars(models[3], "vision"))
        assertEquals("★☆☆", modelRecommendationStars(models[3], "llm"))
    }

    @Test
    fun bothVisionDialogsUseTheOneChooserFedFromTheGroupedCatalog() {
        fun source(name: String): String {
            val relative = "app/src/main/java/app/inku/mobile/ui/$name"
            val candidates = listOf(File(relative), File(relative.removePrefix("app/")), File("android", relative))
            return (candidates.firstOrNull(File::isFile) ?: candidates.first()).readText()
        }
        assertTrue(source("JuxtaposeDialog.kt").contains("VisionModelPicker(label = s.model"))
        assertTrue(source("SavedWorkParityDialogs.kt").contains("VisionModelPicker(label = s.visionModel"))
        assertFalse(source("SavedWorkParityDialogs.kt").contains("DropdownMenu"))
        assertEquals(2, Regex("models = visionModelGroupsFor\\(state\\)").findAll(source("InkuApp.kt")).count())
    }
}
