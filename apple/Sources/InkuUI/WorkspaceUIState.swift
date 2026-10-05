import CoreGraphics
import Observation

/// The workspace canvas's zoom and pan, kept while its view is rebuilt (Web `canvasViewport` lives on the page).
/// `svgKey` names the picture it belongs to; another picture starts fitted.
struct CanvasViewport: Equatable {
    var scale: CGFloat = 1
    var offset = CGSize.zero
    var svgKey = 0
}

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
    /// Kept for the session only, as the Web keeps them: zoom, the batch panel's sections and tab, the drawer's tab.
    var canvasViewport = CanvasViewport()
    var batchResultsExpanded = false
    var batchIssuesExpanded = false
    var batchConditionsExpanded = false
    var batchWorkspaceTab = "work"
    var generationInfoTab = "details"
    /// The next drawing model's service needs an API key that is not stored (first launch guidance).
    var drawingKeyMissing = false
}
