import SwiftUI

/// Common saved-work formats. Native multi-work PNG remains in the supplemental export sheet.
@MainActor
struct SavedWorkExportMenu: View {
    @Bindable var model: AppModel
    let count: Int
    var title: String? = nil
    var symbolOnly = false
    let onAction: (String) -> Void

    var body: some View {
        Menu {
            if count == 1 {
                Section("SVG") {
                    Menu(model.display.webCopy("svgExportHelpTitle", "SVGの用途と特徴")) {
                        ForEach(["Display", "Editable", "Compat", "Live"], id: \.self) { profile in
                            Text(copy("svgExport" + profile + "Name", profile) + ": "
                                 + copy("svgExport" + profile + "Use", "") + " — "
                                 + copy("svgExport" + profile + "Feature", ""))
                        }
                    }
                    ForEach(["Display", "Editable", "Compat", "Live"], id: \.self) { profile in
                        Button(copy("svgExport" + profile + "Name", profile) + "　" + copy("svgExport" + profile + "Sub", "")) {
                            onAction("export-svg:" + profile.lowercased())
                        }
                    }
                }
                Section("PNG") {
                    ForEach(model.display.preferences.savedPNGTemplates) { template in
                        Button(template.name + "　\(template.pixelHeight)px") { onAction("export-png:\(template.pixelHeight)") }
                            .help(template.description)
                    }
                }
                Button(copy("historyCardExport", "共有カード")) { onAction("export-format:shareCard") }
                Button(copy("savedWorkExportDdl", "DDL（プラグイン定義付き）")) { onAction("export-format:ddl") }
            }
            Menu(copy(count == 1 ? "savedWorkExportLayerAnimation" : "savedWorkExportTransitionAnimation",
                      count == 1 ? "レイヤーアニメーション" : "作品の切り替えアニメーション")) {
                Button("APNG") { onAction("export-format:apng") }
                Button("GIF") { onAction("export-format:gif") }
            }
            if count > 1 {
                Button(copy("savedWorkExportContactSheet", "コンタクトシート（閲覧用）")) { onAction("export-format:reviewSheet") }
                Button(copy("savedWorkExportAiContactSheet", "コンタクトシート（AI用・説明付き）")) { onAction("export-format:aiSheet") }
            }
        } label: {
            if symbolOnly { Image(systemName: "square.and.arrow.down") }
            else { Text(title ?? model.display.localized("書き出す")) }
        }
        .menuStyle(.borderlessButton).fixedSize()
        .accessibilityLabel(title ?? model.display.localized("書き出す"))
        .disabled(count == 0)
    }
    private func copy(_ key: String, _ fallback: String) -> String { model.display.webCopy(key, fallback) }
}
