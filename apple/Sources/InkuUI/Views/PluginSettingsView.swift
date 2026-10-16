import SwiftUI
#if os(macOS)
import AppKit
#else
import UIKit
#endif

@MainActor
struct PluginSettingsView: View {
    @Bindable var model: AppModel
    @State private var settings = PluginSettingsModel()

    var body: some View {
        Group {
            Section(model.display.localized("語彙プラグイン")) {
                Text(model.display.localized("有効なプラグインを次に作る作品で使います。保存作品は保存時の定義と版を使います。"))
                    .inkuFont(13).foregroundStyle(.secondary)
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
                                .inkuFont(11).foregroundStyle(.secondary)
                            Spacer()
                            Toggle(model.display.webCopy(settings.preferences.isEnabled(package.id) ? "settingsPluginEnabled" : "settingsPluginDisabled",
                                                         settings.preferences.isEnabled(package.id) ? "有効" : "無効"), isOn: Binding(get: { settings.preferences.isEnabled(package.id) }, set: { value in
                                Task { await settings.setEnabled(value, packageID: package.id, model: model) }
                            })).fixedSize().disabled(package.versions.isEmpty)
                        }
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
