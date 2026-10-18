import CoreGraphics
import Observation
#if os(macOS)
import AppKit
#endif

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
    /// `+page.svelte` canvasViewMode: the work tab shows the experimental 3D view instead of the picture. For the
    /// session only, as on the Web; it starts in 2D.
    var canvasThreeDimensional = false
    /// The 3D view's full screen: the canvas area alone fills the window, which goes full screen.
    var canvasFullScreen = false
    /// The window was full screen before, so leaving the canvas full screen keeps the window's.
    var canvasFullScreenKeepsWindow = false
    #if os(macOS)
    /// The window the canvas full screen was entered in.
    @ObservationIgnored weak var canvasFullScreenWindow: NSWindow?
    #endif
    /// HistoryManager `active`: the library covers the whole window.
    var libraryOpen = false
    var settingsOpen = false
    var settingsSection = SettingsSection.display
    /// CanvasGenerationInfo drawer over the canvas.
    var generationInfoOpen = false
    var refinementMenuWorkID: String?
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
