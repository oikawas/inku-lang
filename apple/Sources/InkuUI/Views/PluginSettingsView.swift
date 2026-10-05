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
                            Text(package.id).inkuFont(14, weight: .semibold)
                            Text(package.versions.isEmpty ? model.display.localized("描画定義なし") : package.versions.map { "v" + $0 }.joined(separator: ", "))
                                .inkuFont(12).foregroundStyle(.secondary)
                            Spacer()
                            Toggle(model.display.localized("有効"), isOn: Binding(get: { settings.preferences.isEnabled(package.id) }, set: { value in
                                Task { await settings.setEnabled(value, packageID: package.id, model: model) }
                            })).fixedSize().disabled(package.versions.isEmpty)
                        }
                        DisclosureGroup(model.display.localizedFormat("収録語（%ld）", package.words.count)) {
                            ForEach(package.words) { word in
                                HStack(alignment: .top, spacing: 12) {
                                    if let url = word.previewURL { preview(url).frame(width: 64, height: 64) }
                                    VStack(alignment: .leading, spacing: 4) {
                                        HStack { Text(word.id).inkuFont(13, weight: .semibold); Text(model.display.localized(package.drawnNames.contains(word.id) ? "描画に使用" : "描画定義なし")).inkuFont(12).foregroundStyle(.secondary) }
                                        if !word.aliases.isEmpty { Text(word.aliases.joined(separator: ", ")).inkuFont(12) }
                                        Text((model.display.preferences.language == "en" ? word.english : word.japanese).joined(separator: " | ")).inkuFont(13)
                                        Text(word.note).inkuFont(12).foregroundStyle(.secondary)
                                    }
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
