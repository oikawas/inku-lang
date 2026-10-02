import Foundation
import InkuExport
import Observation
import SwiftUI

public struct DisplayPreferences: Codable, Sendable, Equatable {
    public var language = "ja"
    public var theme = "system"
    public var textSizeStep = 1
    public var uiMode = "full"
    public var customFeatures: Set<String> = ["history", "diagnostics", "automation", "saijiki"]
    public var captionVisible = true
    public var captionVertical = false
    public var captionPosition = "left"
    public var historyFields: Set<String> = ["generation", "model"]
    public var keepGenerationInfo = true
    public var showTooltips = true
    public var mascot = "incu"
    public var batchRetries = 0
    public var clipboardHeight = 2160
    public var clipboardBackground = "original"
    public var automaticBackup = false
    public var backupIntervalHours = 24
    public var backupGenerations = 7
    public var exportHeight = 2160
    public var exportProfile = "display"
    public var exportConfiguration: ExportConfiguration?
    public var exportTemplates: [ExportTemplate]?
    public var saveResultLog = false
    public init() {}

    public var textScale: Double { [0.9, 1, 1.1, 1.2, 1.3][min(4, max(0, textSizeStep))] }
}

/// Local interface preferences are independent of the immutable work records.
@MainActor @Observable
public final class DisplaySettings {
    public var preferences = DisplayPreferences() { didSet { persist() } }
    public private(set) var saveError: String?
    @ObservationIgnored private var fileURL: URL?
    public init() {}

    public func connect(directory: URL?) {
        guard let directory else { return }
        let url = directory.appendingPathComponent("interface.json")
        do {
            if FileManager.default.fileExists(atPath: url.path) {
                preferences = try JSONDecoder().decode(DisplayPreferences.self, from: Data(contentsOf: url))
            }
            fileURL = url
            saveError = nil
        } catch { saveError = "表示設定を読み込めませんでした: \(error.localizedDescription)" }
    }

    public var colorScheme: ColorScheme? {
        switch preferences.theme { case "dark": .dark; case "light": .light; default: nil }
    }
    public func visible(_ feature: String) -> Bool {
        preferences.uiMode == "full" || (preferences.uiMode == "custom" && preferences.customFeatures.contains(feature))
    }
    public func label(_ japanese: String, _ english: String) -> String {
        preferences.language == "en" ? english : japanese
    }
    private func persist() {
        guard let fileURL else { return }
        do {
            try JSONEncoder().encode(preferences).write(to: fileURL, options: .atomic)
            saveError = nil
        } catch { saveError = "表示設定を保存できませんでした: \(error.localizedDescription)" }
    }
}
