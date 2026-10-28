import SwiftUI
import InkuHost
#if os(macOS)
import AppKit
import UniformTypeIdentifiers
#else
import UIKit
#endif

@MainActor
struct PluginSettingsView: View {
    @Bindable var model: AppModel
    @State private var settings = PluginSettingsModel()
    @State private var confirmingDelete: String?

    var body: some View {
        Group {
            Section(model.display.localized("語彙プラグイン")) {
                Text(model.display.localized("有効なプラグインを次に作る作品で使います。保存作品は保存時の定義と版を使います。"))
                    .inkuFont(13).foregroundStyle(.secondary)
                #if os(macOS)
                Button(model.display.webCopy("settingsUserPluginsAddTitle", "プラグインを追加")) { chooseFile() }
                Text(model.display.webCopy("settingsUserPluginsAddDescription", "JSON または zip を選ぶと検査します。"))
                    .inkuFont(12).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                if let check = settings.check { reportView(check) }
                #endif
                ForEach(settings.packages) { package in
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Text(package.id).inkuFont(14, weight: .semibold).fixedSize()
                            ForEach(package.versions, id: \.self) { version in
                                Text("v" + version).inkuFont(11).monospacedDigit()
                                    .fixedSize()
                                    .padding(.horizontal, 6).padding(.vertical, 2)
                                    .background(InkuColor.bg, in: Capsule())
                                    .overlay(Capsule().stroke(InkuColor.border2))
                            }
                            Text(model.display.webCopy(package.versions.isEmpty ? "settingsPluginNotDrawn" : "settingsPluginDrawn",
                                                       package.versions.isEmpty ? "描画には使われない" : "描画に使う"))
                                .inkuFont(11).foregroundStyle(.secondary).fixedSize()
                            Spacer()
                            if package.rejectedProblems.isEmpty {
                            Toggle(model.display.webCopy(settings.preferences.isEnabled(package.id) ? "settingsPluginEnabled" : "settingsPluginDisabled",
                                                         settings.preferences.isEnabled(package.id) ? "有効" : "無効"), isOn: Binding(get: { settings.preferences.isEnabled(package.id) }, set: { value in
                                Task { await settings.setEnabled(value, packageID: package.id, model: model) }
                            })).fixedSize().disabled(package.versions.isEmpty)
                            }
                        }
                        if !package.rejectedProblems.isEmpty {
                            Text(model.display.preferences.language == "en" ? "Could not load this package" : "このパッケージを読み込めません").foregroundStyle(.red)
                            ForEach(Array(package.rejectedProblems.enumerated()), id: \.offset) { _, problem in problemView(problem) }
                        }
                        #if os(macOS)
                        if package.installed {
                            if confirmingDelete == package.id {
                                Text(model.display.webCopy("settingsPluginPackageDeleteHint", "保存済みの作品は、保存した定義でそのまま描けます。"))
                                    .inkuFont(12).foregroundStyle(.secondary)
                                HStack {
                                    Button(model.display.webCopy("settingsPluginDeleteConfirm", "削除する"), role: .destructive) {
                                        confirmingDelete = nil; Task { await settings.delete(package.id, model: model) }
                                    }
                                    Button(model.display.webCopy("confirmCancel", "キャンセル")) { confirmingDelete = nil }
                                }
                            } else {
                                Button(model.display.webCopy("settingsPluginDelete", "削除"), role: .destructive) { confirmingDelete = package.id }
                            }
                        }
                        #endif
                        ForEach(package.sourceFiles, id: \.self) { source in
                            Text(source).inkuFont(12).foregroundStyle(.secondary).textSelection(.enabled)
                        }
                        Text(model.display.webCopy(package.versions.isEmpty ? "settingsPluginNotDrawnHint" : "settingsPluginDrawnHint",
                                                   "定義を持つプラグインの語を、次に作る作品で使います。"))
                            .inkuFont(12).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                        DisclosureGroup(model.display.webCopy("settingsPluginWords", "語の一覧") + "（\(package.words.count)）") {
                            ForEach(package.words) { word in
                                HStack(alignment: .top, spacing: 10) {
                                    Group {
                                        if let url = word.previewURL { preview(url) }
                                        else { Color.clear }
                                    }
                                    .frame(width: 96, height: 44)
                                    .background(InkuColor.bg, in: RoundedRectangle(cornerRadius: 4))
                                    .overlay(RoundedRectangle(cornerRadius: 4).stroke(InkuColor.border))
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(word.id).inkuFont(12, weight: .semibold)
                                        if !word.aliases.isEmpty { Text(word.aliases.joined(separator: ", ")).inkuFont(12) }
                                        Text((model.display.preferences.language == "en" ? word.english : word.japanese).joined(separator: " | ")).inkuFont(12)
                                        let note = model.display.preferences.language == "en" ? word.englishNote ?? "" : word.note
                                        if !note.isEmpty { Text(note).inkuFont(12).foregroundStyle(.secondary) }
                                    }.frame(maxWidth: .infinity, alignment: .leading)
                                        .fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                                }.padding(.vertical, 4)
                            }
                        }
                    }.padding(.vertical, 6)
                }
                if settings.packages.isEmpty, !settings.isBusy { Text(model.display.localized("収録プラグインはありません。")).foregroundStyle(.secondary) }
                if settings.isBusy { ProgressView().controlSize(.small) }
                if !settings.status.isEmpty { Text(model.display.message(settings.status)).foregroundStyle(.secondary) }
                if let error = settings.error { Text(error).foregroundStyle(.red).textSelection(.enabled) }
                Button(model.display.localized("再読込")) { Task { await settings.load(model: model) } }
            }.disabled(settings.isBusy || model.isBusy)
        }.task { await settings.load(model: model) }
    }

    private func problemView(_ problem: ExactJSON) -> some View {
        Text(PluginPackageProblems.text(problem, language: model.display.preferences.language))
            .inkuFont(12).foregroundStyle(.red).fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
    }

    #if os(macOS)
    private func chooseFile() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.json, .zip]
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        Task { await settings.choose(url, model: model) }
    }

    private func reportView(_ check: PluginPackageCheck) -> some View {
        let words = check.report["words"].array ?? []
        let japanese = model.display.preferences.language != "en"
        return VStack(alignment: .leading, spacing: 8) {
            Text(check.id ?? settings.fileName).inkuFont(14, weight: .semibold)
            if check.report["exists"].bool == true {
                Text(model.display.webCopy("settingsPluginPackageReplaceHint", "同じ名前のプラグインを置き換えます。"))
                    .inkuFont(12).foregroundStyle(.secondary)
            }
            Text(model.display.webCopy(check.ok ? "settingsPluginPackageCheckPassed" : "settingsPluginPackageCheckFailed",
                                       check.ok ? "検査に通りました" : "直すところがあります"))
                .foregroundStyle(check.ok ? Color.secondary : Color.red)
            ForEach(Array((check.report["problems"].array ?? []).enumerated()), id: \.offset) { _, problem in problemView(problem) }
            ForEach(Array(words.enumerated()), id: \.offset) { index, word in
                HStack(alignment: .top, spacing: 8) {
                    if let data = check.preview(at: index), let image = NSImage(data: data) {
                        Image(nsImage: image).resizable().scaledToFit().frame(width: 108, height: 46)
                    }
                    VStack(alignment: .leading, spacing: 3) {
                        Text(word["qualified_name"].string ?? "").inkuFont(12, weight: .semibold)
                        let aliases = (word["aliases"].array ?? []).compactMap(\.string)
                        if !aliases.isEmpty { Text(aliases.joined(separator: ", ")).inkuFont(12) }
                        let note = word[japanese ? "note_ja" : "note_en"].string ?? ""
                        if !note.isEmpty { Text(note).inkuFont(12) }
                        Text(word[japanese ? "example_ja" : "example_en"].string ?? "").inkuFont(12)
                        Text(word[japanese ? "summary_ja" : "summary_en"].string ?? "").inkuFont(12).foregroundStyle(.secondary)
                        if check.preview(at: index) != nil {
                            Text(model.display.webCopy(word["preview_source"].string == "file" ? "settingsPluginPictureFromFile" : "settingsPluginPictureDrawn", "絵"))
                                .inkuFont(11).foregroundStyle(.secondary)
                        }
                        ForEach(Array((word["problems"].array ?? []).enumerated()), id: \.offset) { _, problem in problemView(problem) }
                    }
                }
            }
            HStack {
                if check.ok {
                    Button(model.display.webCopy(check.report["exists"].bool == true ? "settingsPluginPackageReplace" : "settingsPluginPackageInstall", "追加する")) {
                        Task { await settings.install(model: model) }
                    }
                }
                Button(model.display.webCopy("settingsPluginPackageChooseAgain", "別のファイルを選ぶ")) { chooseFile() }
                Button(model.display.webCopy("confirmCancel", "キャンセル")) { settings.clearCheck() }
            }
        }.padding(10).background(InkuColor.bg, in: RoundedRectangle(cornerRadius: 6))
    }
    #endif

    @ViewBuilder private func preview(_ url: URL) -> some View {
        #if os(macOS)
        if let image = NSImage(contentsOf: url) {
            Image(nsImage: image).resizable().scaledToFit()
        } else { Image(systemName: "leaf").foregroundStyle(.secondary) }
        #else
        if let image = UIImage(contentsOfFile: url.path) {
            Image(uiImage: image).resizable().scaledToFit()
        } else { Image(systemName: "leaf").foregroundStyle(.secondary) }
        #endif
    }
}
