import SwiftUI
#if os(macOS)
import AppKit
#else
import UIKit
#endif

@MainActor
public struct SaijikiView: View {
    @Bindable var model: AppModel
    @State private var search = ""

    public init(model: AppModel) { self.model = model }

    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(model.display.localized("歳時記")).font(.title2.weight(.semibold))
            TextField(model.display.localized("語を探す"), text: $search).textFieldStyle(.roundedBorder)
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 16) {
                    ForEach(model.saijiki) { category in
                        let words = category.words.filter { matches($0.japanese + " " + ($0.english ?? "")) }
                        if !words.isEmpty {
                            Text(category.name).font(.headline)
                            LazyVGrid(columns: [GridItem(.adaptive(minimum: 150))], alignment: .leading, spacing: 10) {
                                ForEach(words) { word in
                                    Button {
                                        append(model.language == "ja" ? word.japanese : word.english ?? word.japanese)
                                    } label: {
                                        VStack(alignment: .leading, spacing: 4) {
                                            Text(word.japanese + (word.isDefault ? model.display.localized("（既定）") : ""))
                                            if let english = word.english { Text(english).font(.caption).foregroundStyle(.secondary) }
                                            if !word.detail.isEmpty { Text(word.detail).font(.caption).foregroundStyle(.secondary) }
                                        }.frame(maxWidth: .infinity, alignment: .leading).padding(8)
                                    }.buttonStyle(.bordered).disabled(model.isBusy)
                                }
                            }
                        }
                    }
                    let plugins = model.pluginWords.filter { matches(($0.japanese + $0.english + [$0.id]).joined(separator: " ")) }
                    if !plugins.isEmpty {
                        Text(model.display.localized("プラグインの語")).font(.headline)
                        ForEach(plugins) { word in
                            HStack(alignment: .top, spacing: 12) {
                                preview(word).frame(width: 90, height: 80)
                                VStack(alignment: .leading, spacing: 5) {
                                    Text(word.japanese.first ?? word.id).font(.headline)
                                    Text(word.id).font(.caption.monospaced()).textSelection(.enabled)
                                    Text(word.note).font(.callout).foregroundStyle(.secondary)
                                    Button(model.display.localized("DDLに挿入")) { append(word.id) }.disabled(model.isBusy || word.packageID == nil)
                                    if word.packageID == nil {
                                        Text(model.display.localized("旧Markdownの語です。共通コアの定義がないため描画では省略されます。"))
                                            .font(.caption).foregroundStyle(.secondary)
                                    }
                                }
                            }
                        }
                    }
                }.padding(.vertical, 4)
            }
        }.padding(16)
    }

    private func matches(_ text: String) -> Bool { search.isEmpty || text.localizedCaseInsensitiveContains(search) }
    private func append(_ text: String) {
        if !model.ddlText.isEmpty && !model.ddlText.hasSuffix(" ") && !model.ddlText.hasSuffix("\n") { model.ddlText += " " }
        model.ddlText += text
    }
    @ViewBuilder private func preview(_ word: PluginWord) -> some View {
        #if os(macOS)
        if let url = word.previewURL, let image = NSImage(contentsOf: url) {
            Image(nsImage: image).resizable().scaledToFit()
        } else { Image(systemName: "leaf").foregroundStyle(.secondary) }
        #else
        if let url = word.previewURL, let image = UIImage(contentsOfFile: url.path) {
            Image(uiImage: image).resizable().scaledToFit()
        } else { Image(systemName: "leaf").foregroundStyle(.secondary) }
        #endif
    }
}
