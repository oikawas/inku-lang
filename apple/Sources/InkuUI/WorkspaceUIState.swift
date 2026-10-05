import Observation

/// Screen choices owned above the views, so rebuilding a view does not reset a tab or an open panel.
/// Web keeps the same choices on the page root (`+page.svelte` leftPanelCollapsed, outputTab, settings.opened).
@MainActor @Observable
final class WorkspaceUIState {
    /// AppRail.svelte `expanded`: 44pt rail, 164pt when expanded.
    var railExpanded = false
    /// `+page.svelte` leftPanelCollapsed, toggled by the 18pt bar beside the input panel.
    var leftPanelCollapsed = false
    /// CanvasPanel `outputTab`: "artwork" or "lineage".
    var workspaceTab = "artwork"
    /// HistoryManager `active`: the library covers the whole window.
    var libraryOpen = false
    var settingsOpen = false
    var settingsSection = SettingsSection.display
    /// CanvasGenerationInfo drawer over the canvas.
    var generationInfoOpen = false
    /// SaijikiDrawer at the window's right edge.
    var saijikiOpen = false
}
