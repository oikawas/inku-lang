#if os(macOS)
import AppKit
import UniformTypeIdentifiers

enum ExportKind { case svg, png }

@MainActor
enum NativeFilePanels {
    static func export(kind: ExportKind, language: String = "ja") -> URL? {
        let panel = NSSavePanel()
        panel.title = InkuLocalization.string("作品を書き出す", language: language)
        switch kind {
        case .svg:
            panel.allowedContentTypes = [.svg]
            panel.nameFieldStringValue = "inku-作品.svg"
        case .png:
            panel.allowedContentTypes = [.png]
            panel.nameFieldStringValue = "inku-作品.png"
        }
        return panel.runModal() == .OK ? panel.url : nil
    }

    static func backup(language: String = "ja") -> URL? {
        let panel = NSSavePanel()
        panel.title = InkuLocalization.string("バックアップを保存", language: language)
        panel.allowedContentTypes = [UTType(filenameExtension: "sqlite") ?? .data]
        panel.nameFieldStringValue = "inku-backup.sqlite"
        return panel.runModal() == .OK ? panel.url : nil
    }

    static func restore(language: String = "ja") -> URL? {
        let panel = NSOpenPanel()
        panel.title = InkuLocalization.string("復元するバックアップを選択", language: language)
        panel.allowedContentTypes = [UTType(filenameExtension: "sqlite") ?? .data]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        return panel.runModal() == .OK ? panel.url : nil
    }
}
#endif
