package app.inku.mobile.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import app.inku.mobile.data.CatalogModel
import app.inku.mobile.data.ModelCatalog
import app.inku.mobile.ui.i18n.InkuStrings
import app.inku.mobile.ui.theme.ActiveRowTint
import app.inku.mobile.ui.theme.Dimens
import java.util.Locale

/** Matches the Web picker: purpose first, then the legacy score for old catalog rows. */
internal fun modelRecommendationStars(model: CatalogModel, purpose: String? = null, stage: String? = null): String {
    val raw = modelRecommendationLevel(model, purpose, stage)
    val tier = when {
        raw >= 4.0 -> 3
        raw >= 3.0 -> 2
        raw >= 1.0 -> 1
        else -> 0
    }
    return if (tier == 0) "—" else "★".repeat(tier) + "☆".repeat(3 - tier)
}

/** Web `modelRecommendationLevel`: the stored 0-5 level that also orders the cards. */
internal fun modelRecommendationLevel(model: CatalogModel, purpose: String? = null, stage: String? = null): Double {
    val record = model.record
    fun score(key: String): Double? = if (record.has(key) && !record.isNull(key))
        record.optDouble(key).takeIf(Double::isFinite) else null
    val llm = score("recommendation_llm") ?: score("recommendation_level") ?: 0.0
    val vision = score("recommendation_vision") ?: score("recommendation_level") ?: 0.0
    val stageScores = listOfNotNull(score("recommendation_stage1"), score("recommendation_stage2"))
    val stagedLlm = when (stage) {
        "stage1" -> score("recommendation_stage1") ?: llm
        "stage2" -> score("recommendation_stage2") ?: llm
        "both" -> stageScores.minOrNull() ?: llm
        else -> llm
    }
    val purposes = record.optJSONArray("purposes")?.let { array ->
        (0 until array.length()).map(array::optString)
    } ?: listOf("llm")
    return when (purpose) {
        "llm" -> stagedLlm
        "vision" -> vision
        else -> maxOf(if ("llm" in purposes) stagedLlm else 0.0, if ("vision" in purposes) vision else 0.0)
    }.coerceIn(0.0, 5.0)
}

private fun CatalogModel.listed(key: String): List<String> =
    record.optJSONArray(key)?.let { array -> (0 until array.length()).map(array::optString) }.orEmpty()

/**
 * Web `purposeUnsupported`: the benchmark found the model does not answer this
 * purpose. It can be chosen, but the system does not recommend it: every
 * control that chooses it is framed in red (the author, 2026-10-26).
 */
internal fun purposeUnsupported(model: CatalogModel, purpose: String): Boolean =
    purpose in model.listed("unsupported_purposes")

/**
 * The purposes a published model serves, as Server normalises them: the ones
 * the author [ticked] in the model picker, or the catalog's when none were.
 * The catalog's leave out any purpose the model was measured not to answer;
 * a tick keeps it, as Server's `allowed_unsupported_purposes` (2026-10-26).
 * A catalog row with neither purpose and nothing measured serves LLM.
 */
internal fun modelPurposes(model: CatalogModel, ticked: List<String>? = null): List<String> {
    if (ticked != null) return listOf("llm", "vision").filter { it in ticked }
    val unsupported = model.listed("unsupported_purposes")
    val chosen = model.record.optJSONArray("purposes")?.let { model.listed("purposes") }
        ?.takeIf { it.isNotEmpty() || unsupported.isNotEmpty() } ?: listOf("llm")
    return listOf("llm", "vision").filter { it in chosen && it !in unsupported }
}

/**
 * Web `modelPurposeBadges`: LLM and Vision side by side, each selectable only
 * when the model serves it ([modelPurposes]).
 */
internal fun modelPurposeBadges(model: CatalogModel, ticked: List<String>? = null): List<Pair<String, Boolean>> {
    val purposes = modelPurposes(model, ticked)
    return listOf("llm" to "LLM", "vision" to "Vision").map { (purpose, label) -> label to (purpose in purposes) }
}

/**
 * Web `isModelUnselectable`: a label that keeps it from publication. No
 * response when measured no longer does (2026-10-26).
 */
internal fun isModelUnselectable(model: CatalogModel): Boolean = !model.publishable

/**
 * Web `sortModels`: selectable first, then those that answered the purpose when
 * measured, then by the purpose's level, then by name.
 */
internal fun <T> sortModels(models: List<T>, purpose: String, catalog: (T) -> CatalogModel, name: (T) -> String): List<T> =
    models.sortedWith(compareBy<T> { isModelUnselectable(catalog(it)) }
        .thenBy { purposeUnsupported(catalog(it), purpose) }
        .thenByDescending { modelRecommendationLevel(catalog(it), purpose) }
        .thenBy { name(it) })

/** Place beside ModelLabelWithSupportMark in a model choice heading. */
@Composable
internal fun ModelRecommendationStars(model: CatalogModel, purpose: String, modifier: Modifier = Modifier) {
    Text(modelRecommendationStars(model, purpose), modifier = modifier.testTag("ModelRecommendation:${model.id}"),
        style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
}

/** The drawing model chooser's details: the labels, then the catalog's figures. */
@Composable
internal fun ModelCatalogDetails(model: CatalogModel, strings: InkuStrings) {
    Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs), modifier = Modifier.testTag("CatalogDetails:${model.id}")) {
        model.labels.forEach { label -> ModelLabelText(label, strings) }
        ModelCatalogFigures(model, strings)
    }
}

/**
 * Web `modelStatusParts`: a label that keeps the model from publication in the
 * warning colour, the others muted. No response when measured is publishable
 * since 2026-10-26, as not recommended, and keeps the warning colour.
 */
@Composable
private fun ModelLabelText(label: app.inku.mobile.data.ModelCatalogLabel, strings: InkuStrings) {
    Text(label.name(strings.code == "en"), style = MaterialTheme.typography.labelSmall,
        color = if (label.publishable && label.id != "no_response") MaterialTheme.colorScheme.onSurfaceVariant
            else MaterialTheme.colorScheme.error)
}

/** Web's `model-metadata-editor` figures: recommendation, seconds, cost and comment. */
@Composable
private fun ModelCatalogFigures(model: CatalogModel, strings: InkuStrings) {
    Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
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

/**
 * Web's `model-purpose-controls`: LLM and Vision pressed or not for one model.
 * A pressed one is filled and ticked, an unpressed one only outlined, so the
 * two cannot be mistaken at a glance (the author, 2026-10-26: Material's tinted
 * FilterChip was hard to read). A purpose it was measured not to answer is
 * framed in red as not recommended, and says why. Where [lockUnsupported] (a
 * ChatGPT plan model, whose purposes are each person's own) it still cannot be
 * pressed.
 */
@Composable
internal fun ModelPurposeToggles(model: CatalogModel, ticked: List<String>, enabled: Boolean, strings: InkuStrings,
                                 lockUnsupported: Boolean = false, modifier: Modifier = Modifier, onToggle: (String) -> Unit) {
    Row(modifier, horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
        listOf("llm" to "LLM", "vision" to "Vision").forEach { (purpose, label) ->
            PurposeToggle(label, pressed = purpose in ticked, notRecommended = purposeUnsupported(model, purpose) && !lockUnsupported,
                enabled = enabled && !(lockUnsupported && purposeUnsupported(model, purpose)),
                modifier = Modifier.testTag("CatalogPurpose:${model.id}:$purpose")) { onToggle(purpose) }
        }
    }
}

/** The note under [ModelPurposeToggles] when a purpose gave no response. */
@Composable
internal fun ModelPurposeNote(model: CatalogModel, strings: InkuStrings, lockUnsupported: Boolean) {
    if (listOf("llm", "vision").none { purposeUnsupported(model, it) }) return
    Text(if (lockUnsupported) strings.modelPurposeNoResponse else strings.modelPurposeNotRecommended,
        style = MaterialTheme.typography.labelSmall,
        color = if (lockUnsupported) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.error)
}

@Composable
private fun PurposeToggle(label: String, pressed: Boolean, notRecommended: Boolean, enabled: Boolean,
                          modifier: Modifier = Modifier, onToggle: () -> Unit) {
    val scheme = MaterialTheme.colorScheme
    val accent = if (notRecommended) scheme.error else scheme.primary
    Surface(
        shape = RoundedCornerShape(Dimens.radiusPill),
        color = if (pressed) accent else Color.Transparent,
        contentColor = if (pressed) (if (notRecommended) scheme.onError else scheme.onPrimary)
            else if (notRecommended) scheme.error else scheme.onSurfaceVariant,
        border = BorderStroke(if (notRecommended) Dimens.notRecommendedFrame else Dimens.hairline,
            if (notRecommended) scheme.error else if (pressed) accent else scheme.outline),
        modifier = modifier.heightIn(min = Dimens.controlSizeSmall).alpha(if (enabled) 1f else 0.4f)
            .toggleable(value = pressed, enabled = enabled, role = Role.Checkbox, onValueChange = { onToggle() }),
    ) {
        Box(Modifier.padding(horizontal = Dimens.spaceL), contentAlignment = Alignment.Center) {
            Text(if (pressed) "✓ $label" else label, style = MaterialTheme.typography.labelLarge,
                fontWeight = if (pressed) FontWeight.Bold else FontWeight.Normal)
        }
    }
}

/**
 * One model of the publication picker, as Web's `model-picker-entry`: a card
 * with the publish box, the name, its ID and labels, then the purpose toggles
 * and the folded model details (figures and, where offered, the access check).
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ModelCatalogEntry(
    model: CatalogModel,
    name: String,
    checked: Boolean,
    selectable: Boolean,
    strings: InkuStrings,
    onSelect: (Boolean) -> Unit,
    detailsOpen: Boolean,
    onToggleDetails: () -> Unit,
    toggles: (@Composable (Modifier) -> Unit)?,
    note: (@Composable () -> Unit)?,
    accessCheck: (@Composable () -> Unit)?,
) {
    val scheme = MaterialTheme.colorScheme
    Surface(
        shape = RoundedCornerShape(Dimens.radiusCard),
        color = if (checked) ActiveRowTint else scheme.surface,
        border = BorderStroke(Dimens.hairline, if (checked) scheme.primary else scheme.outlineVariant),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(end = Dimens.spaceM, bottom = Dimens.spaceXs)) {
            Row(modifier = Modifier.fillMaxWidth().testTag("CatalogRow:${model.id}")
                .clickable(enabled = selectable) { onSelect(!checked) }.padding(top = Dimens.spaceXs),
                verticalAlignment = Alignment.Top) {
                Checkbox(checked = checked, enabled = selectable,
                    onCheckedChange = onSelect, modifier = Modifier.testTag("CatalogSelect:${model.id}"))
                Column(Modifier.weight(1f).padding(top = Dimens.spaceM), verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
                    Text(name, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Bold)
                    Text(model.id, style = MaterialTheme.typography.labelSmall, color = scheme.onSurfaceVariant)
                    if (model.labels.isNotEmpty()) FlowRow(Modifier.testTag("CatalogDetails:${model.id}"),
                        horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                        model.labels.forEach { label -> ModelLabelText(label, strings) }
                    }
                }
            }
            Column(Modifier.padding(start = Dimens.spaceL), verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    toggles?.invoke(Modifier.weight(1f))
                    if (toggles == null) Box(Modifier.weight(1f))
                    TextButton(onClick = onToggleDetails, modifier = Modifier.testTag("CatalogMore:${model.id}")) {
                        Text("${strings.modelDetails} ${if (detailsOpen) "▾" else "▸"}", style = MaterialTheme.typography.labelMedium)
                    }
                }
                note?.invoke()
                if (detailsOpen) {
                    ModelCatalogFigures(model, strings)
                    accessCheck?.invoke()
                }
            }
        }
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
    /** The purposes ticked per model (Server's model picker); null leaves the toggles out. */
    purposes: Map<String, List<String>>? = null,
    onTogglePurpose: ((String, String) -> Unit)? = null,
    /** A ChatGPT plan connection: a purpose measured without a response cannot be pressed. */
    lockUnsupportedPurposes: Boolean = false,
) {
    var expanded by remember(catalog) { mutableStateOf(emptySet<String>()) }
    // Web folds each model's details away; they open one model at a time here too.
    var detailsOpen by remember(catalog) { mutableStateOf(emptySet<String>()) }
    val grouped = models.groupBy { it.fold }
    LazyColumn(modifier = modifier, verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
        fun androidx.compose.foundation.lazy.LazyListScope.rows(rows: List<CatalogModel>) {
            items(rows, key = { "model:${it.id}" }) { model ->
                val checked = model.id in selected
                val offered = enabled && model.publishable && (offeredForSelection == null || model.id in offeredForSelection)
                // Web: a model with no purpose to serve is not published.
                val hasPurpose = purposes == null || purposes[model.id].orEmpty().isNotEmpty() || modelPurposes(model).isNotEmpty()
                val withToggles = purposes != null && onTogglePurpose != null
                ModelCatalogEntry(
                    model = model, name = names[model.id] ?: model.name, checked = checked,
                    selectable = offered && hasPurpose, strings = strings,
                    onSelect = { onSelect(model.id, it) },
                    detailsOpen = model.id in detailsOpen,
                    onToggleDetails = { detailsOpen = if (model.id in detailsOpen) detailsOpen - model.id else detailsOpen + model.id },
                    toggles = if (withToggles) { rowModifier ->
                        ModelPurposeToggles(model, purposes!![model.id].orEmpty(), enabled = offered, strings = strings,
                            lockUnsupported = lockUnsupportedPurposes, modifier = rowModifier) { purpose -> onTogglePurpose!!(model.id, purpose) }
                    } else null,
                    note = if (withToggles) { { ModelPurposeNote(model, strings, lockUnsupportedPurposes) } } else null,
                    accessCheck = if (onCheckAccess != null && model.fold != "eol") {
                        { TextButton(onClick = { onCheckAccess(model.id) }, enabled = enabled) { Text(strings.modelAccessCheck) } }
                    } else null,
                )
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
