#if os(macOS)
import AppKit
import UniformTypeIdentifiers

enum ExportKind { case svg, png }

@MainActor
enum NativeFilePanels {
    static func export(kind: ExportKind) -> URL? {
        let panel = NSSavePanel()
        panel.title = "作品を書き出す"
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

    static func backup() -> URL? {
        let panel = NSSavePanel()
        panel.title = "バックアップを保存"
        panel.allowedContentTypes = [UTType(filenameExtension: "sqlite") ?? .data]
        panel.nameFieldStringValue = "inku-backup.sqlite"
        return panel.runModal() == .OK ? panel.url : nil
    }

    static func restore() -> URL? {
        let panel = NSOpenPanel()
        panel.title = "復元するバックアップを選択"
        panel.allowedContentTypes = [UTType(filenameExtension: "sqlite") ?? .data]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        return panel.runModal() == .OK ? panel.url : nil
    }
}
#endif
