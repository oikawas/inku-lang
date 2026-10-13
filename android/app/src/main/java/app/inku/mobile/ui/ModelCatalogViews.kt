package app.inku.mobile.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import app.inku.mobile.data.CatalogModel
import app.inku.mobile.data.ModelCatalog
import app.inku.mobile.ui.i18n.InkuStrings
import java.util.Locale

/** Used by both the publication picker and the drawing model chooser. */
@Composable
internal fun ModelCatalogDetails(model: CatalogModel, strings: InkuStrings) {
    Column(verticalArrangement = Arrangement.spacedBy(2.dp), modifier = Modifier.testTag("CatalogDetails:${model.id}")) {
        model.labels.forEach { label ->
            Text(label.name(strings.code == "en"), style = MaterialTheme.typography.labelSmall,
                color = if (label.publishable) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.error)
        }
        val record = model.record
        listOf("llm" to "LLM", "stage1" to "Stage 1", "stage2" to "Stage 2", "vision" to "Vision").forEach { (key, name) ->
            if (record.has("recommendation_$key")) Text("${strings.modelRecommendation} $name: ${"★".repeat(record.optInt("recommendation_$key").coerceIn(0, 5))}", style = MaterialTheme.typography.labelSmall)
        }
        if (record.has("recommendation_level")) Text("${strings.modelRecommendation}: ${record.get("recommendation_level")}", style = MaterialTheme.typography.labelSmall)
        listOf("llm" to "LLM", "vision" to "Vision").forEach { (key, name) ->
            if (record.has("speed_${key}_seconds")) Text("${strings.modelAverageSeconds} $name: ${record.get("speed_${key}_seconds")} s", style = MaterialTheme.typography.labelSmall)
            if (record.has("cost_usd_$key")) Text("${strings.modelEstimatedCost} $name: USD ${String.format(Locale.ROOT, "%.6f", record.optDouble("cost_usd_$key"))}", style = MaterialTheme.typography.labelSmall)
        }
        val speed = record.optString("speed_label")
        if (speed.isNotBlank()) Text(speed, style = MaterialTheme.typography.labelSmall)
        val comment = record.optString(if (strings.code == "en") "comment_en" else "comment_ja")
        if (comment.isNotBlank()) Text(comment, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

/** Folds come only from the canonical label table and start closed. */
@Composable
internal fun ModelCatalogRows(
    catalog: ModelCatalog,
    models: List<CatalogModel>,
    selected: Set<String>,
    strings: InkuStrings,
    onSelect: (String, Boolean) -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    names: Map<String, String> = emptyMap(),
    offeredForSelection: Set<String>? = null,
    onCheckAccess: ((String) -> Unit)? = null,
) {
    var expanded by remember(catalog) { mutableStateOf(emptySet<String>()) }
    val grouped = models.groupBy { it.fold }
    LazyColumn(modifier = modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        fun androidx.compose.foundation.lazy.LazyListScope.rows(rows: List<CatalogModel>) {
            items(rows, key = { "model:${it.id}" }) { model ->
                Column {
                    val checked = model.id in selected
                    val selectable = enabled && model.publishable && (offeredForSelection == null || model.id in offeredForSelection)
                    Row(modifier = Modifier.fillMaxWidth().testTag("CatalogRow:${model.id}")
                        .clickable(enabled = selectable) { onSelect(model.id, !checked) }.padding(vertical = 4.dp),
                        verticalAlignment = Alignment.Top) {
                        Checkbox(checked = checked, enabled = selectable,
                            onCheckedChange = { onSelect(model.id, it) }, modifier = Modifier.testTag("CatalogSelect:${model.id}"))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(names[model.id] ?: model.name, style = MaterialTheme.typography.bodySmall)
                            Text(model.id, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            ModelCatalogDetails(model, strings)
                        }
                    }
                    if (onCheckAccess != null && model.fold != "eol") TextButton(onClick = { onCheckAccess(model.id) }, enabled = enabled) { Text(strings.modelAccessCheck) }
                }
            }
        }
        rows(grouped[null].orEmpty())
        catalog.labels.forEach { label ->
            val rows = grouped[label.id].orEmpty()
            item(key = "fold:${label.id}") {
                TextButton(onClick = { expanded = if (label.id in expanded) expanded - label.id else expanded + label.id },
                    modifier = Modifier.fillMaxWidth().testTag("CatalogFold:${label.id}")) {
                    Text("${if (label.id in expanded) "▼" else "▶"} ${label.name(strings.code == "en")} (${rows.size})")
                }
            }
            if (label.id in expanded) rows(rows)
        }
    }
}
