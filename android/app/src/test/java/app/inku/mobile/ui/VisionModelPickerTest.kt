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
    fun onlyALabelThatKeepsItFromPublicationMakesItUnselectable() {
        assertTrue(isModelUnselectable(model("a", """{"purposes":["vision"]}""", eol)))
        // Answering neither purpose no longer does: it is not recommended (2026-10-26).
        assertFalse(isModelUnselectable(model("b", """{"purposes":[],"unsupported_purposes":["llm","vision"]}""")))
        assertFalse(isModelUnselectable(model("c", """{"purposes":["vision"]}""", old)))
        assertFalse(isModelUnselectable(model("d", """{"purposes":["vision"],"unsupported_purposes":["llm"]}""")))
    }

    @Test
    fun cardsAreOrderedSelectableFirstThenAnsweredThenByTheVisionLevelThenByName() {
        val models = listOf(
            model("retired", """{"purposes":["vision"],"recommendation_vision":5}""", eol),
            model("modest", """{"purposes":["vision"],"recommendation_vision":2}"""),
            model("legacy", """{"purposes":["vision"],"recommendation_level":4}"""),
            model("best", """{"purposes":["vision"],"recommendation_vision":5,"recommendation_llm":1}"""),
            model("alpha", """{"purposes":["vision"],"recommendation_vision":2}"""),
            // Chosen for Vision though it gave no Vision answer: after those that did.
            model("silent", """{"purposes":["llm"],"unsupported_purposes":["vision"],"recommendation_vision":5}"""),
        )
        assertEquals(listOf("best", "legacy", "alpha", "modest", "silent", "retired"),
            sortModels(models, "vision", { it }, { it.id }).map { it.id })
        assertEquals("★★★", modelRecommendationStars(models[3], "vision"))
        assertEquals("★☆☆", modelRecommendationStars(models[3], "llm"))
    }

    @Test
    fun theAuthorsTicksDecideThePurposesAndTheCatalogsLeaveOutOneTheModelDoesNotAnswer() {
        val both = model("a", """{"purposes":["llm","vision"]}""")
        assertEquals(listOf("llm", "vision"), modelPurposes(both))
        assertEquals(listOf("vision"), modelPurposes(both, listOf("vision")))
        assertEquals(emptyList<String>(), modelPurposes(both, emptyList()))
        // The catalog's never bring in a purpose measured not to answer; a tick does,
        // as Server's allowed_unsupported_purposes (2026-10-26).
        val mute = model("b", """{"purposes":["llm"],"unsupported_purposes":["vision"]}""")
        assertEquals(listOf("llm"), modelPurposes(mute))
        assertEquals(listOf("llm", "vision"), modelPurposes(mute, listOf("llm", "vision")))
        assertEquals(listOf("LLM" to true, "Vision" to true), modelPurposeBadges(mute, listOf("llm", "vision")))
        assertTrue(purposeUnsupported(mute, "vision"))
        val silent = model("s", """{"purposes":[],"unsupported_purposes":["llm","vision"]}""")
        assertEquals(emptyList<String>(), modelPurposes(silent))
        assertEquals(listOf("llm"), modelPurposes(silent, listOf("llm")))
        // A catalog row that names no purpose serves LLM, as Server normalises it.
        assertEquals(listOf("llm"), modelPurposes(model("c", """{"purposes":[]}""")))
        assertEquals(listOf("LLM" to false, "Vision" to true), modelPurposeBadges(both, listOf("vision")))
    }

    @Test
    fun theTicksReadBackPerConnectionAndAnythingElseIsNoTick() {
        assertEquals(mapOf("openai" to mapOf("gpt-vision" to listOf("vision"), "gpt-text" to listOf("llm", "vision"))),
            parseModelPurposes("""{"openai":{"gpt-vision":["vision","other"],"gpt-text":["llm","vision"]}}"""))
        assertEquals(emptyMap<String, Map<String, List<String>>>(), parseModelPurposes("not json"))
        assertEquals(emptyMap<String, Map<String, List<String>>>(), parseModelPurposes(null))
    }

    @Test
    fun theSettingsPickerTicksPurposesAndTheListsFollowThem() {
        fun source(name: String): String {
            val relative = "app/src/main/java/app/inku/mobile/ui/$name"
            val candidates = listOf(File(relative), File(relative.removePrefix("app/")), File("android", relative))
            return (candidates.firstOrNull(File::isFile) ?: candidates.first()).readText()
        }
        val app = source("InkuApp.kt")
        val picker = app.substring(app.indexOf("private fun ProviderModelPickerDialog("), app.indexOf("private fun LocalModelManagementDialog("))
        assertTrue(picker.contains("purposes = purposes,"))
        assertTrue(picker.contains("selected = if (next.isNotEmpty()) selected + id else selected - id"))
        assertTrue(picker.contains("onSave(published, published.associateWith { purposes[it].orEmpty() })"))
        // A red-framed purpose can be pressed except on a ChatGPT plan, and select-all never takes a model with none (2026-10-26).
        assertTrue(picker.contains("lockUnsupportedPurposes = provider.providerId == \"chatgpt\""))
        assertTrue(picker.contains("it.id in candidateIds && hasPurpose(it)"))
        // The drawing models that did not answer come after those that did.
        assertTrue(app.contains("}.sortedBy { it.notRecommended }"))
        assertEquals(2, Regex("saveModelPurposes\\(").findAll(app).count())
        assertTrue(app.contains("provider != \"local-litert-lm\" && \"vision\" in servedPurposes(state, provider, choice.id)"))
        // The camera reads the photo and draws with one model, so it offers those used for both (2026-10-21).
        assertTrue(app.contains("\"llm\" in purposes && (!state.modelSelectionForCamera || \"vision\" in purposes)"))
        assertTrue(app.contains("testTag(\"PublishedPurpose:\${provider.providerId}:\$purpose\")"))
    }

    @Test
    fun bothVisionDialogsUseTheOneChooserFedFromTheGroupedCatalog() {
        fun source(name: String): String {
            val relative = "app/src/main/java/app/inku/mobile/ui/$name"
            val candidates = listOf(File(relative), File(relative.removePrefix("app/")), File("android", relative))
            return (candidates.firstOrNull(File::isFile) ?: candidates.first()).readText()
        }
        assertTrue(source("JuxtaposeDialog.kt").contains("VisionModelPicker(label = s.model"))
        // The autonomous refinement's own label since its moves moved to the shared core (7dc4755f4).
        assertTrue(source("SavedWorkParityDialogs.kt").contains("VisionModelPicker(label = s[\"aiRefineModel\"]"))
        assertFalse(source("SavedWorkParityDialogs.kt").contains("DropdownMenu"))
        assertEquals(2, Regex("models = visionModelGroupsFor\\(state\\)").findAll(source("InkuApp.kt")).count())
    }
}
