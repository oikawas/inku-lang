package app.inku.mobile.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import app.inku.mobile.data.refinement.ToolChangeMode
import app.inku.mobile.ui.i18n.InkuStrings
import app.inku.mobile.ui.theme.Dimens

internal const val TOOL_CHANGE_ENTRY_TAG = "tool-change-entry"
internal const val TOOL_CHANGE_DIALOG_TAG = "tool-change-dialog"
internal const val TOOL_CHANGE_GENERATE_TAG = "tool-change-generate"
internal const val TOOL_CHANGE_DISCARD_ALL_TAG = "tool-change-discard-all"

@Composable
internal fun ToolChangeDialog(state: InkuUiState, viewModel: InkuViewModel, strings: InkuStrings) {
    val saving = state.refinementCandidates.any { it.saveState == RefinementSaveState.Saving }
    val busy = state.refinementBusy || saving
    Dialog(onDismissRequest = { viewModel.closeToolChange() }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(modifier = Modifier.fillMaxWidth().fillMaxHeight(.94f).testTag(TOOL_CHANGE_DIALOG_TAG)) {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()).padding(Dimens.spaceL),
                verticalArrangement = Arrangement.spacedBy(Dimens.spaceM),
            ) {
                Text(strings.workActionTool, style = MaterialTheme.typography.titleLarge)
                state.refinementParent?.let { Text(strings.editingWorkLabel(it.renderHashShort)) }
                Text(strings.toolChangeHint, style = MaterialTheme.typography.bodySmall)
                ToolChangeMode.entries.forEach { mode ->
                    val label = if (mode == ToolChangeMode.Uniform) strings.toolChangeUniform else strings.toolChangePerSentence
                    Row(
                        modifier = Modifier.fillMaxWidth().testTag("tool-mode-" + mode.id)
                            .selectable(selected = state.toolChangeMode == mode, enabled = !busy, role = Role.RadioButton) {
                                viewModel.setToolChangeMode(mode)
                            },
                    ) {
                        RadioButton(selected = state.toolChangeMode == mode, onClick = null, enabled = !busy)
                        Text(label, modifier = Modifier.padding(top = Dimens.spaceM))
                    }
                }
                Button(
                    onClick = viewModel::generateToolChangeCandidates,
                    enabled = !busy,
                    modifier = Modifier.testTag(TOOL_CHANGE_GENERATE_TAG),
                ) { Text(if (state.refinementBusy) strings.working else strings.toolChangeMakeFour) }
                if (state.refinementBusy) Text(strings.working)
                state.refinementStatus?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                if (state.refinementCandidates.isEmpty() && !state.refinementBusy) Text(strings.toolChangePlaceholder)
                state.refinementCandidates.chunked(2).forEach { row ->
                    Row(horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                        row.forEach { candidate ->
                            RefinementCandidateCard(
                                candidate, state.refinementPreviewId == candidate.id,
                                onSave = { if (!busy) viewModel.saveRefinementCandidate(candidate.id) },
                                onPreview = { if (!busy) viewModel.previewRefinementCandidate(candidate.id) },
                                modifier = Modifier.weight(1f),
                                onDiscard = { if (!busy) viewModel.discardToolChangeCandidate(candidate.id) },
                            )
                        }
                    }
                }
                TextButton(
                    onClick = { viewModel.closeToolChange(discard = true) }, enabled = !busy,
                    modifier = Modifier.testTag(TOOL_CHANGE_DISCARD_ALL_TAG),
                ) { Text(strings.toolChangeDiscardAndClose) }
                TextButton(onClick = { viewModel.closeToolChange() }, enabled = !busy) { Text(strings.close) }
            }
        }
    }
}
