import Foundation
import InkuHost
import Observation

struct PluginPackageInfo: Identifiable, Sendable {
    let id: String
    let versions: [String]
    let words: [PluginWord]
    let drawnNames: Set<String>
}

@MainActor @Observable
final class PluginSettingsModel {
    private(set) var packages: [PluginPackageInfo] = []
    private(set) var preferences = PluginPreferences()
    private(set) var isBusy = false
    var error: String?
    private(set) var status = ""

    func load(model: AppModel) async {
        guard !isBusy else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let host = await model.hostSettings()
            preferences = host.plugins ?? .init()
            let bootstrap = try Bootstrap()
            let catalog = try bootstrap.macroCatalog(language: model.instructionLanguage(for: ""))
            let entries = catalog["entries"] as? [[String: Any]] ?? []
            let grouped = Dictionary(grouping: bootstrap.pluginWords, by: { $0.packageID ?? "" })
            packages = grouped.keys.filter { !$0.isEmpty }.sorted().map { packageID in
                let definitions = entries.filter { $0["source_id"] as? String == "bundled:" + packageID }
                return PluginPackageInfo(id: packageID,
                    versions: Set(definitions.compactMap { $0["version"] as? String }).sorted(),
                    words: grouped[packageID] ?? [],
                    drawnNames: Set(definitions.compactMap { $0["qualified_name"] as? String }))
            }
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    func setEnabled(_ enabled: Bool, packageID: String, model: AppModel) async {
        guard !isBusy, !model.isBusy, packages.contains(where: { $0.id == packageID }) else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            // Read the latest provider/model settings so a plugin switch cannot overwrite them.
            var host = await model.hostSettings()
            var changed = host.plugins ?? .init()
            changed.setEnabled(enabled, packageID: packageID)
            host.plugins = changed
            try await model.updateHostSettings(host)
            preferences = changed
            status = enabled ? "次に作る作品で有効にしました。" : "次に作る作品で無効にしました。"
            error = nil
        } catch { self.error = error.localizedDescription }
    }
}
