package app.inku.mobile.ui

import app.inku.mobile.data.db.HistoryItemEntity

/** The saved work a description run starts from, independent of its displayed result. */
internal val InkuUiState.descriptionDrawingParent: HistoryItemEntity?
    get() = (selectedHistory ?: pendingDescriptionParent).takeUnless { lineageDetached }

/** Clear the displayed result when Stage 1 starts. */
internal fun InkuUiState.beginDescriptionDrawing(
    parent: HistoryItemEntity? = descriptionDrawingParent,
    message: String? = null,
): InkuUiState = copy(
    isDrawing = true,
    pendingDescriptionParent = parent,
    selectedHistory = null,
    ddl = "",
    ddlEditedAfterGeneration = false,
    confirmDdlOverwrite = false,
    pipelineView = null,
    historyAuthority = null,
    historyDescriptionLocked = null,
    message = message,
)
