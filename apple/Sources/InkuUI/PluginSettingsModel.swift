import Foundation
import InkuHost
import Observation

struct PluginPackageInfo: Identifiable, Sendable {
    let id: String
    let versions: [String]
    let sourceFiles: [String]
    let words: [PluginWord]
    let drawnNames: Set<String>
    var installed = false
    var rejectedProblems: [ExactJSON] = []
}

@MainActor @Observable
final class PluginSettingsModel {
    private(set) var packages: [PluginPackageInfo] = []
    private(set) var preferences = PluginPreferences()
    private(set) var isBusy = false
    var error: String?
    private(set) var status = ""
    private(set) var check: PluginPackageCheck?
    private(set) var fileName = ""
    private var pendingData: Data?
    private var pendingArchive = false

    func load(model: AppModel) async {
        guard !isBusy else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let host = await model.hostSettings()
            preferences = host.plugins ?? .init()
            let bootstrap = try Bootstrap(pluginDataDirectory: model.localDataDirectory())
            let catalog = try bootstrap.macroCatalog(language: model.instructionLanguage(for: ""))
            let entries = catalog["entries"] as? [[String: Any]] ?? []
            let grouped = Dictionary(grouping: bootstrap.bundledPluginWords, by: { $0.packageID ?? "" })
            packages = grouped.keys.filter { !$0.isEmpty }.sorted().map { packageID in
                let definitions = entries.filter { $0["source_id"] as? String == "bundled:" + packageID }
                return PluginPackageInfo(id: packageID,
                    versions: Set(definitions.compactMap { $0["version"] as? String }).sorted(),
                    sourceFiles: Set((grouped[packageID] ?? []).compactMap(\.sourceFile).filter { !$0.isEmpty }).sorted(),
                    words: grouped[packageID] ?? [],
                    drawnNames: Set(definitions.compactMap { $0["qualified_name"] as? String }))
            }
            packages += bootstrap.installedPluginPackages.map { package in
                PluginPackageInfo(id: package.id, versions: package.package?["version"].string.map { [$0] } ?? [],
                    sourceFiles: [], words: package.pluginWords(), drawnNames: Set(package.words.compactMap { $0["qualified_name"].string }),
                    installed: true, rejectedProblems: package.problems)
            }
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    func choose(_ url: URL, model: AppModel) async {
        guard !isBusy, !model.isBusy else { return }
        isBusy = true; defer { isBusy = false }
        check = nil; pendingData = nil; error = nil; status = ""
        do {
            let data = try Data(contentsOf: url)
            let archive = url.pathExtension.lowercased() == "zip"
            let result = try await model.checkPluginPackage(data: data, isArchive: archive)
            pendingData = data; pendingArchive = archive; fileName = url.lastPathComponent; check = result
        } catch { self.error = model.failureMessage(error) }
    }

    func install(model: AppModel) async {
        guard !isBusy, !model.isBusy, let pendingData, let check, check.ok else { return }
        isBusy = true
        do {
            let result = try await model.installPluginPackage(data: pendingData, isArchive: pendingArchive,
                                                               replace: check.report["exists"].bool == true)
            if result.ok { self.check = nil; self.pendingData = nil; status = model.display.webCopy("settingsPluginPackageInstalled", "{id} を追加しました。").replacingOccurrences(of: "{id}", with: result.id ?? "") }
            else { self.check = result }
            error = nil
        } catch { self.error = model.failureMessage(error) }
        isBusy = false
        if error == nil { await load(model: model) }
    }

    func delete(_ id: String, model: AppModel) async {
        guard !isBusy, !model.isBusy, packages.contains(where: { $0.id == id && $0.installed }) else { return }
        isBusy = true
        do { try await model.deletePluginPackage(id); status = model.display.preferences.language == "en" ? "Deleted \(id)." : "\(id) を削除しました。"; error = nil }
        catch { self.error = model.failureMessage(error) }
        isBusy = false
        if error == nil { await load(model: model) }
    }
    func clearCheck() { check = nil; pendingData = nil; fileName = "" }

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
