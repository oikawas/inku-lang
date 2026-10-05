import Foundation
import InkuExport
import Observation
import SwiftUI

public struct DisplayPreferences: Codable, Sendable, Equatable {
    public var language = "ja"
    /// Web `theme` starts dark; a saved choice is kept.
    public var theme = "dark"
    public var textSizeStep = 1
    public var uiMode = "simple"
    public var settingsDetail: String?
    public var customFeatures: Set<String> = ["history"]
    public var captionVisible = true
    public var captionVertical = false
    public var captionPosition = "left"
    public var historyFields: Set<String> = ["generation", "model"]
    public var keepGenerationInfo = true
    public var sketchExpanded: Bool?
    public var showTooltips = true
    public var mascot = "incu"
    public var batchRetries = 0
    public var clipboardHeight = 1080
    public var clipboardBackground = "original"
    public var clipboardFormat: String?
    public var visionModelReference: String?
    public var colophonModelReference: String?
    public var automaticBackup = false
    public var backupIntervalHours = 24
    public var backupGenerations = 7
    public var exportHeight = 2160
    public var exportProfile = "display"
    public var exportConfiguration: ExportConfiguration?
    public var exportTemplates: [ExportTemplate]?
    public var saveResultLog = false
    /// Older preference files omit this field. Capture always starts disabled.
    public var captureProviderIO: Bool?
    public var includeThinking: Bool?
    /// Next-work conditions (Web `color_catalog_id` with its `auto` sentinel, `plugin_storage[canvas-aspect].selected`,
    /// `inku-wild`). A catalog or paper that no longer exists falls back to the default when read.
    public var nextCatalogID: String?
    public var nextCatalogMode: String?
    public var nextCanvasID: String?
    public var nextWild: Bool?
    /// Screen choices (Web `settings_tab`, `inku-history-display-mode`), restored on the next launch.
    public var settingsTab: String?
    public var workspaceTab: String?
    public var inputTab: String?
    public var libraryLayout: String?
    public var libraryGrouped: Bool?
    /// Dialog choices (Web `inku-refine-kind`, `model_inspection_selected_models`, `inku-ai-refine-settings`).
    public var refineKind: String?
    public var comparisonModels: [String]?
    public var aiRefine: AIRefineChoices?
    /// Web `inku-result-log-open`: the result log under the input starts closed.
    public var resultLogOpen: Bool?
    public init() {}

    /// Web `normalizeHistoryStripFields`: the declared order, whichever order the boxes were ticked, at most three.
    public var historyStripFields: [String] {
        Array(["generation", "model", "engine", "size"].filter { historyFields.contains($0) }.prefix(3))
    }

    public var textScale: Double { [0.9, 1, 1.1, 1.2, 1.3][min(4, max(0, textSizeStep))] }
}

/// Web `ai-refine-settings.ts`: the autonomous refinement dialog opens with the last choices. Wild is not kept.
public struct AIRefineChoices: Codable, Sendable, Equatable {
    public var visionMode: Bool
    public var generations: Int
    public var kinds: [String]
    public var direction: String
    public init(visionMode: Bool, generations: Int, kinds: [String], direction: String) {
        self.visionMode = visionMode; self.generations = generations; self.kinds = kinds; self.direction = direction
    }
}

/// Local interface preferences are independent of the immutable work records.
@MainActor @Observable
public final class DisplaySettings {
    public var preferences = DisplayPreferences() { didSet { persist() } }
    public private(set) var saveError: String?
    @ObservationIgnored private var fileURL: URL?
    @ObservationIgnored private var previewingTextSize = false
    public init() {}

    public func connect(directory: URL?) {
        guard let directory else { return }
        let url = directory.appendingPathComponent("interface.json")
        do {
            if FileManager.default.fileExists(atPath: url.path) {
                preferences = try TolerantPreferences.decode(DisplayPreferences.self, from: Data(contentsOf: url),
                                                             defaults: DisplayPreferences())
            }
            saveError = nil
        } catch {
            TolerantPreferences.setAside(url)
            saveError = "表示設定を読み込めませんでした: \(error.localizedDescription)"
        }
        fileURL = url
    }

    public var colorScheme: ColorScheme? {
        switch preferences.theme { case "dark": .dark; case "light": .light; default: nil }
    }
    public func visible(_ feature: String) -> Bool {
        if preferences.uiMode == "full" { return true }
        guard preferences.uiMode == "custom" else { return feature == "history" }
        let aliases = ["detail_status": "diagnostics", "input_modes": "automation", "auxiliary": "saijiki"]
        let canonical = aliases.first(where: { $0.value == feature })?.key ?? feature
        return preferences.customFeatures.contains(canonical)
            || aliases[canonical].map { preferences.customFeatures.contains($0) } == true
    }
    public func label(_ japanese: String, _ english: String) -> String {
        preferences.language == "en" ? english : japanese
    }
    public func previewTextSize(_ step: Int) {
        previewingTextSize = true
        preferences.textSizeStep = min(4, max(0, step))
        previewingTextSize = false
    }
    public func saveTextSize() { persist() }
    public func resetTextSize() { preferences.textSizeStep = 1 }
    public func retrySave() { persist() }
    private func persist() {
        guard !previewingTextSize, let fileURL else { return }
        do {
            try JSONEncoder().encode(preferences).write(to: fileURL, options: .atomic)
            saveError = nil
        } catch { saveError = "表示設定を保存できませんでした: \(error.localizedDescription)" }
    }
}
