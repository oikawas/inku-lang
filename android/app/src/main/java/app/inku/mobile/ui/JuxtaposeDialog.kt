package app.inku.mobile.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import app.inku.mobile.ui.i18n.UiLanguage
import app.inku.mobile.ui.i18n.juxtaposeStrings
import app.inku.mobile.ui.theme.Dimens
import kotlinx.coroutines.delay

/**
 * 取り合わせ (SPEC §7.8), laid out as Web's `JuxtaposeDialog.svelte`: the
 * description, the Vision model, the four picks with why, and the description
 * with the chosen one added. Drawing closes the dialog; the lineage shows the run.
 */
@Composable
internal fun JuxtaposeDialog(
    dialog: JuxtapositionDialogState,
    modelId: String,
    models: List<VisionModelGroup>,
    language: UiLanguage,
    onModel: (String) -> Unit,
    onAsk: () -> Unit,
    onChoose: (Int) -> Unit,
    onDraw: () -> Unit,
    onStop: () -> Unit,
    onDismiss: () -> Unit,
) {
    val s = juxtaposeStrings(language)
    val busy = dialog.busy
    val canAsk = !busy && models.any { group -> group.models.any { it.id == modelId && !isModelUnselectable(it.catalog) } }
    var elapsedMs by remember(dialog.startedAtMs) { mutableLongStateOf(0L) }
    LaunchedEffect(busy, dialog.startedAtMs) {
        while (busy) {
            elapsedMs = System.currentTimeMillis() - dialog.startedAtMs
            delay(JUXTAPOSE_TICK_MS)
        }
    }
    Dialog(
        onDismissRequest = { if (!busy) onDismiss() },
        properties = DialogProperties(usePlatformDefaultWidth = false, dismissOnBackPress = !busy, dismissOnClickOutside = !busy),
    ) {
        Surface(
            modifier = Modifier.fillMaxWidth(0.94f).imePadding().testTag(JUXTAPOSE_DIALOG_TAG),
            shape = RoundedCornerShape(Dimens.radiusCard), color = MaterialTheme.colorScheme.surface,
        ) {
            Column(Modifier.padding(Dimens.spaceL), verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(s.title, modifier = Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
                    TextButton(onClick = onDismiss, enabled = !busy) { Text(s.cancel) }
                }
                Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                    Text(s.help, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(s.description, style = MaterialTheme.typography.labelMedium)
                    JuxtaposeText(sourceTextOf(dialog.target))
                    VisionModelPicker(label = s.model, selectedModelId = modelId, groups = models, enabled = !busy,
                        onSelect = onModel, modifier = Modifier.testTag(JUXTAPOSE_MODEL_TAG))
                    dialog.result?.let { result ->
                        Text(s.choices(result.candidates), style = MaterialTheme.typography.labelMedium)
                        result.choices.forEachIndexed { index, item ->
                            Row(
                                Modifier.fillMaxWidth()
                                    .selectable(selected = dialog.chosen == index, enabled = !busy, role = Role.RadioButton,
                                        onClick = { onChoose(index) })
                                    .testTag(juxtaposeChoiceTag(index)),
                                verticalAlignment = Alignment.Top,
                            ) {
                                RadioButton(selected = dialog.chosen == index, onClick = null, enabled = !busy)
                                Column(Modifier.padding(start = Dimens.spaceM), verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
                                    Text(s.sentenceLabel, style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    Text(item.sentence, style = MaterialTheme.typography.bodyMedium)
                                    Text(s.reasonLabel, style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    Text(item.reason, style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }
                        }
                    }
                    dialog.choice?.let { choice ->
                        Text(s.joined, style = MaterialTheme.typography.labelMedium)
                        JuxtaposeText(choice.joined)
                    }
                    dialog.error?.takeIf(String::isNotBlank)?.let {
                        Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                    }
                }
                if (busy) {
                    LinearProgressIndicator(Modifier.fillMaxWidth())
                    Text(s.asking(formatDuration(elapsedMs)), style = MaterialTheme.typography.bodySmall)
                    OutlinedButton(onClick = onStop, modifier = Modifier.fillMaxWidth().testTag(JUXTAPOSE_STOP_TAG)) { Text(s.stop) }
                } else if (dialog.result == null) {
                    // Nothing can be drawn before four sentences are shown, so asking is the one action.
                    Button(onClick = onAsk, enabled = canAsk, modifier = Modifier.fillMaxWidth().testTag(JUXTAPOSE_ASK_TAG)) { Text(s.ask) }
                } else {
                    Row(horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                        OutlinedButton(onClick = onAsk, enabled = canAsk, modifier = Modifier.weight(1f).testTag(JUXTAPOSE_ASK_TAG)) {
                            Text(s.askAgain)
                        }
                        Button(onClick = onDraw, enabled = dialog.choice != null,
                            modifier = Modifier.weight(1f).testTag(JUXTAPOSE_DRAW_TAG)) { Text(s.draw) }
                    }
                }
            }
        }
    }
}

@Composable
private fun JuxtaposeText(text: String) {
    Surface(
        shape = RoundedCornerShape(Dimens.radiusCard),
        border = BorderStroke(Dimens.hairline, MaterialTheme.colorScheme.outlineVariant),
        color = MaterialTheme.colorScheme.surfaceContainerLow,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(text, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(Dimens.spaceM))
    }
}

private const val JUXTAPOSE_TICK_MS = 100L
internal const val JUXTAPOSE_DIALOG_TAG = "JuxtaposeDialog"
internal const val JUXTAPOSE_MODEL_TAG = "JuxtaposeModel"
internal const val JUXTAPOSE_ASK_TAG = "JuxtaposeAsk"
internal const val JUXTAPOSE_DRAW_TAG = "JuxtaposeDraw"
internal const val JUXTAPOSE_STOP_TAG = "JuxtaposeStop"
internal fun juxtaposeChoiceTag(index: Int): String = "JuxtaposeChoice$index"
