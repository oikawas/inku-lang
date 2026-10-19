package app.inku.mobile.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import app.inku.mobile.data.db.HistoryListItem
import app.inku.mobile.ui.i18n.UiLanguage
import app.inku.mobile.ui.i18n.savedWorkParityStrings
import app.inku.mobile.ui.theme.Dimens

/** The ViewModel owns the debounced search. Typing here only updates its query. */
@Composable
internal fun CanvasWorkSearchDialog(
    query: String,
    busy: Boolean,
    failed: Boolean,
    items: List<HistoryListItem>,
    language: UiLanguage,
    onQuery: (String) -> Unit,
    onSelect: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    val s = savedWorkParityStrings(language)
    val focusManager = LocalFocusManager.current
    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(
            modifier = Modifier.fillMaxWidth(0.94f).fillMaxHeight(0.88f).imePadding().testTag("CanvasWorkSearchDialog"),
            shape = RoundedCornerShape(Dimens.radiusCard),
            color = MaterialTheme.colorScheme.surface,
        ) {
            Column(Modifier.padding(Dimens.spaceL), verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(s.searchTitle, style = MaterialTheme.typography.titleMedium)
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick = onDismiss) { Text(s.close) }
                }
                OutlinedTextField(
                    value = query,
                    onValueChange = onQuery,
                    label = { Text(s.searchLabel) },
                    trailingIcon = {
                        if (query.isNotEmpty()) TextButton(onClick = { onQuery("") }, modifier = Modifier.testTag("CanvasWorkSearchClear")) {
                            Text(s.clear)
                        }
                    },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                    keyboardActions = KeyboardActions(onSearch = { focusManager.clearFocus() }),
                    modifier = Modifier.fillMaxWidth().testTag("CanvasWorkSearchQuery"),
                )
                if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
                if (failed) Text(
                    s.searchFailed,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                )
                if (!busy && !failed && items.isEmpty()) Text(
                    s.noWorks,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                LazyColumn(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
                    items(items, key = { it.id }) { item ->
                        Column(
                            modifier = Modifier.fillMaxWidth().clickable { onSelect(item.id) }
                                .padding(vertical = Dimens.spaceM).testTag("CanvasWorkSearchResult:${item.id}"),
                            verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs),
                        ) {
                            Text(item.originalInput.lineSequence().firstOrNull().orEmpty().ifBlank { item.id },
                                style = MaterialTheme.typography.bodyMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
                            Text("${item.renderHashShort} · ${item.id}", style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1,
                                overflow = TextOverflow.Ellipsis)
                        }
                        HorizontalDivider()
                    }
                }
            }
        }
    }
}

/** The two SVGs are the saved drawing and a new performance of its saved Score. */
@Composable
internal fun ReplayComparisonDialog(
    originalSvg: String,
    replayedSvg: String,
    recordedVersion: String?,
    currentVersion: String?,
    provisionalSeed: String?,
    saving: Boolean,
    saved: Boolean,
    error: String?,
    language: UiLanguage,
    onSave: () -> Unit,
    onDismiss: () -> Unit,
) {
    val s = savedWorkParityStrings(language)
    Dialog(
        onDismissRequest = { if (!saving) onDismiss() },
        properties = DialogProperties(usePlatformDefaultWidth = false, dismissOnBackPress = !saving, dismissOnClickOutside = !saving),
    ) {
        Surface(
            modifier = Modifier.fillMaxWidth(0.96f).fillMaxHeight(0.92f).testTag("ReplayComparisonDialog"),
            shape = RoundedCornerShape(Dimens.radiusCard), color = MaterialTheme.colorScheme.surface,
        ) {
            Column(Modifier.padding(Dimens.spaceL), verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                    Text(s.replayTitle, modifier = Modifier.weight(1f),
                        style = MaterialTheme.typography.titleMedium)
                    TextButton(onClick = onDismiss, enabled = !saving) { Text(s.close) }
                }
                if (provisionalSeed != null) Text(
                    s.provisionalSeed(provisionalSeed),
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                BoxWithConstraints(Modifier.fillMaxWidth().weight(1f)) {
                    val wide = maxWidth >= Dimens.replayComparisonSideBySideMinWidth
                    if (wide) {
                        Row(
                            Modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
                            horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
                        ) {
                            ReplayComparisonPane(originalSvg, s.original, recordedVersion,
                                s.versionUnrecorded, s, Modifier.weight(1f))
                            ReplayComparisonPane(replayedSvg, s.currentReplay, currentVersion,
                                s.versionUnknown, s, Modifier.weight(1f))
                        }
                    } else {
                        Column(
                            Modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
                            verticalArrangement = Arrangement.spacedBy(Dimens.spaceM),
                        ) {
                            ReplayComparisonPane(originalSvg, s.original, recordedVersion,
                                s.versionUnrecorded, s, Modifier.fillMaxWidth())
                            ReplayComparisonPane(replayedSvg, s.currentReplay, currentVersion,
                                s.versionUnknown, s, Modifier.fillMaxWidth())
                        }
                    }
                }
                error?.takeIf(String::isNotBlank)?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                if (saved) Text(s.replaySaved,
                    color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodySmall)
                Button(onClick = onSave, enabled = !saving && !saved, modifier = Modifier.fillMaxWidth().testTag("ReplaySaveChild")) {
                    if (saving) CircularProgressIndicator(strokeWidth = Dimens.hairline)
                    Text(if (saving) s.saving else s.saveReplayChild)
                }
            }
        }
    }
}

@Composable
private fun ReplayComparisonPane(svg: String, title: String, version: String?, unknownVersion: String,
    strings: app.inku.mobile.ui.i18n.SavedWorkParityStrings, modifier: Modifier) {
    val byteCount = remember(svg) { svg.toByteArray(Charsets.UTF_8).size }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
        Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
        Text(strings.engineVersion(version ?: unknownVersion), style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(strings.svgBytes(byteCount), style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        RefinementCandidateImage(renderHash = "replay:$title", svg = svg,
            modifier = Modifier.fillMaxWidth().aspectRatio(1f))
    }
}

/** Settings are edited only before start; opening the dialog has no side effect. */
@Composable
internal fun AutonomousRefinementDialog(
    settings: AutonomousRefinementSettings,
    status: AutonomousRefinementStatus,
    models: List<ParityModelChoice>,
    language: UiLanguage,
    onSettings: (AutonomousRefinementSettings) -> Unit,
    onStart: () -> Unit,
    onStop: () -> Unit,
    onDismiss: () -> Unit,
) {
    val s = savedWorkParityStrings(language)
    val busy = status.busy
    val canStart = !busy && settings.generations in 1..10 && settings.allowedKinds.isNotEmpty() &&
        models.any { it.id == settings.modelId }
    var modelMenuOpen by remember { mutableStateOf(false) }
    Dialog(
        onDismissRequest = { if (!busy) onDismiss() },
        properties = DialogProperties(usePlatformDefaultWidth = false, dismissOnBackPress = !busy, dismissOnClickOutside = !busy),
    ) {
        Surface(
            modifier = Modifier.fillMaxWidth(0.94f).fillMaxHeight(0.9f).imePadding().testTag("AutonomousRefinementDialog"),
            shape = RoundedCornerShape(Dimens.radiusCard), color = MaterialTheme.colorScheme.surface,
        ) {
            Column(Modifier.padding(Dimens.spaceL), verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(s.autonomousTitle, modifier = Modifier.weight(1f),
                        style = MaterialTheme.typography.titleMedium)
                    TextButton(onClick = onDismiss, enabled = !busy) { Text(s.close) }
                }
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(Dimens.spaceL)) {
                    // Vision is the only method (2026-10-18): its model and the
                    // direction are always asked for.
                    Text(s.vision, style = MaterialTheme.typography.titleSmall)
                    Text(s.visionHint, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    run {
                        Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
                            Text(s.visionModel,
                                style = MaterialTheme.typography.labelMedium)
                            OutlinedButton(onClick = { modelMenuOpen = true }, enabled = !busy && models.isNotEmpty(),
                                modifier = Modifier.fillMaxWidth().testTag("AutonomousVisionModel")) {
                                Text(models.firstOrNull { it.id == settings.modelId }?.let { "${it.label} · ${it.provider}" }
                                    ?: s.chooseModel, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            }
                            DropdownMenu(expanded = modelMenuOpen && !busy, onDismissRequest = { modelMenuOpen = false }) {
                                models.forEach { model ->
                                    DropdownMenuItem(text = { Text("${model.label} · ${model.provider}") }, onClick = {
                                        modelMenuOpen = false
                                        onSettings(settings.copy(modelId = model.id))
                                    })
                                }
                            }
                        }
                        OutlinedTextField(value = settings.direction, onValueChange = { onSettings(settings.copy(direction = it.take(160))) },
                            label = { Text(s.directionLabel) },
                            placeholder = { Text(s.directionPlaceholder) },
                            enabled = !busy, minLines = 2, maxLines = 3, modifier = Modifier.fillMaxWidth().testTag("AutonomousDirection"))
                    }
                    Text(s.generations, style = MaterialTheme.typography.titleSmall)
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                        OutlinedButton(onClick = { onSettings(settings.copy(generations = (settings.generations - 1).coerceAtLeast(1))) },
                            enabled = !busy && settings.generations > 1, modifier = Modifier.testTag("AutonomousGenerationsDecrease")) { Text("−") }
                        Text(settings.generations.coerceIn(1, 10).toString(), style = MaterialTheme.typography.titleMedium)
                        OutlinedButton(onClick = { onSettings(settings.copy(generations = (settings.generations + 1).coerceAtMost(10))) },
                            enabled = !busy && settings.generations < 10, modifier = Modifier.testTag("AutonomousGenerationsIncrease")) { Text("+") }
                    }
                    Text(s.elements, style = MaterialTheme.typography.titleSmall)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = settings.changeColor, onCheckedChange = { onSettings(settings.copy(changeColor = it)) }, enabled = !busy)
                        Text(s.color)
                        Checkbox(checked = settings.changeLayout, onCheckedChange = { onSettings(settings.copy(changeLayout = it)) }, enabled = !busy)
                        Text(s.layout)
                    }
                    Text(s.wild, style = MaterialTheme.typography.titleSmall)
                    Row(horizontalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
                        listOf(null to s.inherit, true to s.on, false to s.off).forEach { (value, label) ->
                            FilterChip(selected = settings.wildOverride == value,
                                onClick = { onSettings(settings.copy(wildOverride = value)) }, enabled = !busy,
                                label = { Text(label) })
                        }
                    }
                    if (busy) {
                        LinearProgressIndicator(Modifier.fillMaxWidth())
                        Text(s.generationStatus(status.step.coerceAtLeast(1), status.total.coerceAtLeast(1)),
                            style = MaterialTheme.typography.bodySmall)
                    }
                    status.message?.takeIf(String::isNotBlank)?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                    status.observation?.takeIf(String::isNotBlank)?.let {
                        Text(s.visionObservation, style = MaterialTheme.typography.titleSmall)
                        Text(it, style = MaterialTheme.typography.bodySmall)
                    }
                    status.nextDirection?.takeIf(String::isNotBlank)?.let {
                        Text(s.nextDirection, style = MaterialTheme.typography.titleSmall)
                        Text(it, style = MaterialTheme.typography.bodySmall)
                    }
                    status.error?.takeIf(String::isNotBlank)?.let {
                        Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                    }
                }
                if (busy) OutlinedButton(onClick = onStop, modifier = Modifier.fillMaxWidth().testTag("AutonomousStop")) {
                    Text(s.stop)
                } else Button(onClick = onStart, enabled = canStart, modifier = Modifier.fillMaxWidth().testTag("AutonomousStart")) {
                    Text(s.start)
                }
            }
        }
    }
}
