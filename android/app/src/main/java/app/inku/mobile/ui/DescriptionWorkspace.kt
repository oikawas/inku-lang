package app.inku.mobile.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.Dp
import app.inku.mobile.ui.theme.Dimens

internal const val DESCRIPTION_ARTWORK_TAG = "DescriptionArtwork"

/** Switching destinations is not a request to discard the work or its description. */
internal fun InkuUiState.returnToDescriptionWorkspace(): InkuUiState = copy(
    tab = AppTab.Compose, composeMode = ComposeMode.Write,
    descriptionFocused = false, lineageLoading = false,
    canvasPresentationMode = false, presentationHistory = null,
    presentationSequence = emptyList(), workActionsTarget = null, workSketchTarget = null,
    ddlEditorOpen = false, confirmDdlOverwrite = false,
    refinementOpen = false, refinementParent = null, refinementCandidates = emptyList(),
    refinementPreviewId = null, refinementStatus = null, message = null,
)

/** The artwork has its own space, so scrolling or focusing the editor never removes it. */
@Composable
internal fun DescriptionWorkspace(
    showArtwork: Boolean,
    artwork: @Composable (Dp) -> Unit,
    editor: @Composable () -> Unit,
) {
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val viewportHeight = maxHeight
        if (!showArtwork) {
            editor()
        } else if (maxWidth >= Dimens.descriptionSideBySideMinWidth) {
            Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                Box(Modifier.weight(1f).testTag(DESCRIPTION_ARTWORK_TAG)) { artwork(viewportHeight) }
                Box(Modifier.weight(1f)) { editor() }
            }
        } else {
            val artworkHeight = (maxHeight * 0.38f).coerceAtMost(Dimens.heroPreviewMaxHeight)
            Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                Box(Modifier.height(artworkHeight).testTag(DESCRIPTION_ARTWORK_TAG)) { artwork(artworkHeight) }
                Box(Modifier.weight(1f)) { editor() }
            }
        }
    }
}
