package app.inku.mobile.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import app.inku.mobile.data.CatalogModel
import app.inku.mobile.ui.i18n.LocalStrings
import app.inku.mobile.ui.theme.ActiveRowTint
import app.inku.mobile.ui.theme.Dimens

/** One Vision model offered by a connection, with its catalog record. */
internal data class VisionModelOption(
    val id: String,
    val label: String,
    val catalog: CatalogModel,
    /** What the model serves: the author's ticks in the model picker, else the catalog's. */
    val purposes: List<String> = modelPurposes(catalog),
)

/** One connection's Vision models, as a group of Web's `vision_catalog`. */
internal data class VisionModelGroup(val id: String, val label: String, val models: List<VisionModelOption>)

/**
 * The Vision model chooser of 取り合わせ and 自律推敲, as Web's
 * `ModelCardPicker` with `purpose="vision"`: a button naming the chosen model
 * and its connection, and a list grouped by connection. Each card shows the
 * Vision recommendation, the model's labels, the LLM and Vision badges (a
 * purpose it cannot be chosen for greyed out) and the catalog's figures. A
 * model a label keeps from publication is shown greyed and cannot be chosen.
 */
@Composable
internal fun VisionModelPicker(
    label: String,
    selectedModelId: String,
    groups: List<VisionModelGroup>,
    enabled: Boolean,
    onSelect: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val strings = LocalStrings.current
    var open by remember { mutableStateOf(false) }
    val selected = groups.firstNotNullOfOrNull { group -> group.models.firstOrNull { it.id == selectedModelId }?.let { group to it } }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
        Text(label, style = MaterialTheme.typography.labelMedium)
        Surface(
            onClick = { open = true }, enabled = enabled,
            shape = RoundedCornerShape(Dimens.radiusCard),
            border = BorderStroke(Dimens.hairline, MaterialTheme.colorScheme.outline),
            color = MaterialTheme.colorScheme.surface,
            modifier = Modifier.fillMaxWidth().alpha(if (enabled) 1f else 0.45f).testTag(VISION_MODEL_PICKER_TAG),
        ) {
            Row(Modifier.padding(horizontal = Dimens.spaceL, vertical = Dimens.spaceM),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                Column(Modifier.weight(1f)) {
                    Text(selected?.second?.label ?: selectedModelId, fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.bodyMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    val sub = selected?.first?.label ?: strings.modelPickerNotInList.takeIf { selectedModelId.isNotEmpty() }
                    if (sub != null) Text(sub, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Text(strings.modelSelection, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
            }
        }
    }
    if (open) Dialog(onDismissRequest = { open = false }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(shape = RoundedCornerShape(Dimens.radiusCard), color = MaterialTheme.colorScheme.surface,
            modifier = Modifier.fillMaxWidth(0.94f).testTag(VISION_MODEL_DIALOG_TAG)) {
            Column(Modifier.padding(Dimens.spaceL), verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(label, modifier = Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
                    TextButton(onClick = { open = false }) { Text(strings.close) }
                }
                Column(Modifier.heightIn(max = Dimens.providerModelDialogHeight).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(Dimens.spaceL)) {
                    if (groups.isEmpty()) Text(strings.noPublishedModelsLong, style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    groups.forEach { group ->
                        Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                            Text(group.label, style = MaterialTheme.typography.titleSmall)
                            sortModels(group.models, "vision", { it.catalog }, { it.label }).forEach { model ->
                                VisionModelCard(model, selected = model.id == selectedModelId) {
                                    onSelect(model.id)
                                    open = false
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun VisionModelCard(model: VisionModelOption, selected: Boolean, onClick: () -> Unit) {
    val strings = LocalStrings.current
    val unselectable = isModelUnselectable(model.catalog)
    Surface(
        onClick = onClick, enabled = !unselectable,
        shape = RoundedCornerShape(Dimens.radiusCard),
        border = BorderStroke(Dimens.hairline,
            if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outlineVariant),
        color = if (selected) ActiveRowTint else MaterialTheme.colorScheme.surface,
        modifier = Modifier.fillMaxWidth().alpha(if (unselectable) 0.55f else 1f).testTag(visionModelCardTag(model.id)),
    ) {
        Column(Modifier.padding(Dimens.spaceM), verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                Text(model.label, modifier = Modifier.weight(1f), fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.bodyMedium,
                    // Web strikes through a retired model only.
                    textDecoration = if (model.catalog.labels.any { it.id == "eol" }) TextDecoration.LineThrough else null)
                ModelRecommendationStars(model.catalog, "vision")
            }
            Row(horizontalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
                modelPurposeBadges(model.catalog, model.purposes).forEach { (badge, selectable) ->
                    Surface(shape = RoundedCornerShape(Dimens.radiusPill),
                        border = BorderStroke(Dimens.hairline, MaterialTheme.colorScheme.outline),
                        modifier = Modifier.alpha(if (selectable) 1f else 0.45f)
                            .semantics { contentDescription = if (selectable) badge else badge + strings.modelPurposeNotSelectable }
                            .testTag("VisionModelPurpose:${model.id}:$badge:$selectable")) {
                        Text(badge, style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier.padding(horizontal = Dimens.spaceM))
                    }
                }
            }
            ModelCatalogDetails(model.catalog, strings)
        }
    }
}

internal const val VISION_MODEL_PICKER_TAG = "VisionModelPicker"
internal const val VISION_MODEL_DIALOG_TAG = "VisionModelDialog"
internal fun visionModelCardTag(modelId: String): String = "VisionModelCard:$modelId"
