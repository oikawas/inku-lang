package app.inku.mobile.ui

import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.foundation.layout.Column
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.Modifier
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import app.inku.mobile.data.ModelCatalog
import app.inku.mobile.ui.i18n.InkuStringsJa
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ModelCatalogDeviceTest {
    @get:Rule val rule = createAndroidComposeRule<ComponentActivity>()

    @Test fun blockingLabelColorsEveryLabelInTheRow() {
        val catalog = ModelCatalog.load(rule.activity)
        val models = listOf(
            catalog.classify(JSONObject().put("id", "mixed").put("labels", JSONArray(listOf("legacy", "eol")))),
            catalog.classify(JSONObject().put("id", "muted").put("labels", JSONArray(listOf("legacy")))),
        )
        val scheme = lightColorScheme()
        rule.setContent { MaterialTheme(colorScheme = scheme) { Column {
            models.forEach { ModelCatalogDetails(it, InkuStringsJa) }
        } } }
        models.forEach { model ->
            val expected = if (model.id == "mixed") scheme.error else scheme.onSurfaceVariant
            model.labels.forEach { label ->
                val results = mutableListOf<TextLayoutResult>()
                rule.onNode(hasText(label.ja) and hasAnyAncestor(hasTestTag("CatalogDetails:${model.id}")), useUnmergedTree = true)
                    .performSemanticsAction(SemanticsActions.GetTextLayoutResult) { action -> assertTrue(action(results)) }
                assertEquals("${model.id}/${label.id}", expected, results.single().layoutInput.style.color)
            }
        }
    }

    @Test fun sixClosedFoldsShowCanonicalLabelsAndBlockUnpublishableModels() {
        val catalog = ModelCatalog.load(rule.activity)
        val models = catalog.labels.map { label ->
            val record = JSONObject().put("id", label.id)
            if (label.id != "unmeasured") record.put("labels", JSONArray().put(label.id)).put("comment_ja", "確認用コメント")
            if (label.id == "no_response") record.put("purposes", JSONArray())
            if (label.id == "legacy") record.put("recommendation_llm", 4).put("speed_llm_seconds", 2.8).put("cost_usd_llm", 0.00007)
            if (label.id == "eol") record.put("labels", JSONArray(listOf("legacy", "not_supported", "eol")))
            catalog.classify(record)
        }
        val selected = mutableSetOf<String>()
        rule.setContent { MaterialTheme { ModelCatalogRows(catalog, models, emptySet(), InkuStringsJa,
            onSelect = { id, checked -> if (checked) selected.add(id) else selected.remove(id) },
            modifier = Modifier.fillMaxSize().testTag("CatalogList")) } }
        val positions = catalog.labels.map { label ->
            rule.onNodeWithTag("CatalogFold:${label.id}").assertTextEquals("▶ ${label.ja} (1)")
            rule.onNodeWithTag("CatalogRow:${label.id}").assertDoesNotExist()
            rule.onNodeWithTag("CatalogFold:${label.id}").fetchSemanticsNode().boundsInRoot.top
        }
        assertEquals(positions.sorted(), positions)
        catalog.labels.forEach { label ->
            rule.onNodeWithTag("CatalogList").performScrollToNode(hasTestTag("CatalogFold:${label.id}"))
            rule.onNodeWithTag("CatalogFold:${label.id}").performClick()
            rule.onNodeWithTag("CatalogList").performScrollToNode(hasTestTag("CatalogRow:${label.id}"))
            rule.onNodeWithTag("CatalogDetails:${label.id}", useUnmergedTree = true).assert(hasAnyDescendant(hasText(label.ja)))
            models.first { it.id == label.id }.labels.forEach { stored ->
                rule.onNodeWithTag("CatalogDetails:${label.id}", useUnmergedTree = true).assert(hasAnyDescendant(hasText(stored.ja)))
            }
            val checkbox = rule.onNodeWithTag("CatalogSelect:${label.id}")
            if (label.publishable) {
                checkbox.assertIsEnabled().performClick()
                assertTrue(label.id in selected)
            } else checkbox.assertIsNotEnabled()
            if (label.id == "legacy") {
                rule.onNodeWithText("推奨度 LLM: ★★★★").assertExists()
                rule.onNodeWithText("平均秒数 LLM: 2.8 s").assertExists()
                rule.onNodeWithText("概算コスト LLM: USD 0.000070").assertExists()
                rule.onNodeWithText("確認用コメント").assertExists()
            }
            rule.onNodeWithTag("CatalogList").performScrollToNode(hasTestTag("CatalogFold:${label.id}"))
            rule.onNodeWithTag("CatalogFold:${label.id}").performClick()
        }
        assertEquals(setOf("unmeasured", "legacy"), selected)
    }
}
