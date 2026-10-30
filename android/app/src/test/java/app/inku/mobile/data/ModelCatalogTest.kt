package app.inku.mobile.data

import java.io.File
import app.inku.mobile.ui.modelRecommendationLevel
import app.inku.mobile.ui.purposeUnsupported
import app.inku.mobile.ui.isModelUnselectable
import app.inku.mobile.ui.sortModels
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ModelCatalogTest {
    private val source = JSONObject(File(System.getProperty("inku.modelCatalogSource")).readText())
    private val catalog = ModelCatalog(source)

    @Test fun sharedCasesHaveTheSameLabelsFoldAndPublishability() {
        val cases = JSONObject(File(System.getProperty("inku.modelCatalogCases")).readText()).getJSONArray("cases")
        assertEquals(15, cases.length())
        for (index in 0 until cases.length()) {
            val case = cases.getJSONObject(index)
            val actual = catalog.classify(case.getJSONObject("model"))
            val name = case.getString("name")
            assertEquals(name, case.getJSONArray("labels").strings(), actual.labels.map { it.id })
            assertEquals(name, if (case.isNull("fold")) null else case.getString("fold"), actual.fold)
            assertEquals(name, case.getBoolean("publishable"), actual.publishable)
        }
    }

    @Test fun sharedSelectionCasesUseTheCoreSelection() {
        val cases = JSONObject(File(System.getProperty("inku.modelCatalogCases")).readText()).getJSONArray("selection_cases")
        for (index in 0 until cases.length()) {
            val case = cases.getJSONObject(index)
            val model = catalog.classify(case.getJSONObject("model"))
            val purpose = case.getString("purpose")
            assertEquals(case.getString("name"), case.getBoolean("unselectable"), isModelUnselectable(model))
            assertEquals(case.getString("name"), case.getBoolean("unsupported"), purposeUnsupported(model, purpose))
            assertEquals(case.getString("name"), case.getDouble("level"), modelRecommendationLevel(model, purpose, case.getString("stage")), 0.0)
        }
    }

    @Test fun sharedSortCasesUseTheCoreSortKeys() {
        val cases = JSONObject(File(System.getProperty("inku.modelCatalogCases")).readText()).getJSONArray("sort_cases")
        for (index in 0 until cases.length()) {
            val case = cases.getJSONObject(index)
            val input = case.getJSONArray("models")
            val models = (0 until input.length()).map { catalog.classify(input.getJSONObject(it)) }
            assertEquals(case.getString("name"), case.getJSONArray("order").strings(),
                sortModels(models, "none", { it }, { it.name }).map { it.id })
        }
    }

    @Test fun canonicalDefaultsAndChatGptMeasurementsSurviveLocalObservations() {
        val before = source.toString()
        val providers = source.getJSONObject("providers")
        providers.keys().forEach { id -> assertEquals(providers.getJSONObject(id).getJSONArray("defaults").strings(), catalog.defaults(id)) }
        val chat = catalog.resolve("chatgpt", "chatgpt:gpt-6.1-sol")
        assertSame("unchanged observations use the cached core answer", chat, catalog.resolve("chatgpt", chat.id))
        assertEquals(30.4, chat.record.getDouble("speed_llm_seconds"), 0.0)
        assertEquals(3, chat.record.getInt("recommendation_vision"))
        val retired = catalog.resolve("chatgpt", chat.id, offered = emptySet())
        assertNotSame("changed observations have their own answer", chat, retired)
        assertSame("repeated observations reuse their answer", retired, catalog.resolve("chatgpt", chat.id, offered = emptySet()))
        assertEquals("eol", retired.fold)
        assertFalse(retired.publishable)
        assertTrue(catalog.resolve("chatgpt", chat.id, offered = setOf(chat.id)).publishable)
        val id = "kimi-k2.7-code"
        assertEquals("subscription", catalog.resolve("ollama-cloud", id).fold)
        assertTrue(catalog.resolve("ollama-cloud", id, accessible = true).publishable)
        assertEquals("subscription", catalog.resolve("ollama-cloud", id, accessible = false).fold)
        assertEquals(catalog.resolve("ollama-cloud", id).record.getString("comment_ja"), catalog.resolve("ollama-cloud", id, accessible = true).record.getString("comment_ja"))
        val staticEol = "mistralai/mistral-nemotron"
        assertEquals("eol", catalog.resolve("nvidia", staticEol).fold)
        assertTrue(catalog.resolve("nvidia", staticEol, offered = setOf(staticEol)).publishable)
        assertEquals(before, source.toString())
        assertEquals("subscription", catalog.resolve("ollama-cloud", id).fold)
        assertEquals("eol", catalog.resolve("nvidia", staticEol).fold)
    }
}
