import Foundation
import SwiftUI
#if os(macOS)
import AppKit
#endif

/// The reviewed snapshot that apple/scripts/build-macos-notices.py writes from the locked inputs.
/// Identical license texts are stored once and referenced by key.
struct ThirdPartyNotices: Decodable, Sendable {
    struct LicenseText: Decodable, Sendable {
        let label: String
        let text: String
    }

    struct Component: Decodable, Sendable, Identifiable {
        let group: String
        let name: String
        let version: String
        let license: String
        let source: String
        let note: String
        let texts: [LicenseText]
        var id: String { "\(group)/\(name)/\(version)" }
    }

    let components: [Component]
    let texts: [String: String]

    static func bundled() -> ThirdPartyNotices? {
        guard let url = Bundle.module.url(forResource: "third-party-notices", withExtension: "json"),
              let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(ThirdPartyNotices.self, from: data)
    }

    func body(of component: Component) -> String {
        component.texts.map { "--- \($0.label) ---\n\n\(texts[$0.text] ?? "")" }.joined(separator: "\n\n")
    }
}

@MainActor
struct ThirdPartyNoticesView: View {
    let display: DisplaySettings
    @Environment(\.dismiss) private var dismiss
    @State private var notices: ThirdPartyNotices?
    @State private var loaded = false
    @State private var selection: ThirdPartyNotices.Component.ID?

    private static let groups = ["inku", "swift", "rust", "native", "resources", "ddl3d"]

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(display.webCopy("noticesTitle", "第三者ライセンス")).inkuFont(14, weight: .medium)
                Spacer()
                Button(display.localized("閉じる")) { dismiss() }.keyboardShortcut(.cancelAction)
            }
            .padding(.horizontal, 16).padding(.vertical, 10)
            Divider()
            if let notices {
                HStack(spacing: 0) {
                    List(selection: $selection) {
                        ForEach(Self.groups.filter { group in notices.components.contains { $0.group == group } }, id: \.self) { group in
                            Section(groupTitle(group)) {
                                ForEach(notices.components.filter { $0.group == group }) { component in
                                    VStack(alignment: .leading, spacing: 1) {
                                        Text(component.name).inkuFont(12)
                                        Text([component.version, component.license].filter { !$0.isEmpty }.joined(separator: " · "))
                                            .inkuFont(10).foregroundStyle(.secondary)
                                    }
                                    .tag(component.id)
                                    .listRowSeparator(.hidden)
                                }
                            }
                        }
                    }
                    .listStyle(.plain)
                    .accessibilityLabel(display.webCopy("noticesList", "ライセンスの一覧"))
                    .frame(width: 260)
                    Divider()
                    if let component = notices.components.first(where: { $0.id == selection }) {
                        detail(component, body: notices.body(of: component))
                    } else {
                        Text(display.localized("項目を選ぶと全文を表示します。"))
                            .inkuFont(12).foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                    }
                }
            } else if loaded {
                Text(display.localized("ライセンス一覧を読み込めません。"))
                    .inkuFont(12).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .frame(minWidth: 760, idealWidth: 960, minHeight: 520, idealHeight: 640)
        .task {
            guard !loaded else { return }
            notices = await Task.detached(priority: .userInitiated) { ThirdPartyNotices.bundled() }.value
            selection = notices?.components.first?.id
            loaded = true
        }
    }

    private func detail(_ component: ThirdPartyNotices.Component, body: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text([component.name, component.version].filter { !$0.isEmpty }.joined(separator: " "))
                .inkuFont(14, weight: .semibold)
            if !component.license.isEmpty {
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    Text(display.webCopy("appInfoLicenseTitle", "ライセンス")).foregroundStyle(.secondary)
                    Text(component.license)
                }.inkuFont(12)
            }
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                Text(display.webCopy("noticesSource", "入手先")).foregroundStyle(.secondary)
                if let url = URL(string: component.source) { Link(component.source, destination: url) }
                else { Text(component.source) }
            }.inkuFont(12)
            if !component.note.isEmpty {
                Text(component.note).inkuFont(12).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            NoticeTextView(text: body).frame(maxWidth: .infinity, maxHeight: .infinity)
                .accessibilityLabel(display.webCopy("noticesText", "通知とライセンスの全文"))
        }
        .textSelection(.enabled)
        .padding(16)
    }

    private func groupTitle(_ group: String) -> String {
        switch group {
        case "swift": display.localized("Swiftパッケージ")
        case "rust": display.localized("Rustクレート")
        case "native": display.localized("ネイティブライブラリ")
        case "resources": display.localized("同梱の辞書とフォント")
        // The bundled 3D viewer's own notices file (apple/scripts/build-macos-notices.py).
        case "ddl3d": display.webCopy("ddl3dTitle", "3D表示（実験）")
        default: "inku"
        }
    }
}

#if os(macOS)
/// Some notices (the Rust standard library's) are hundreds of kilobytes; a text view lays them out lazily.
private struct NoticeTextView: NSViewRepresentable {
    let text: String

    func makeNSView(context: Context) -> NSScrollView {
        let view = NSTextView.scrollableTextView()
        guard let textView = view.documentView as? NSTextView else { return view }
        textView.isEditable = false
        textView.isSelectable = true
        textView.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        textView.textContainerInset = NSSize(width: 10, height: 10)
        let paragraph = NSMutableParagraphStyle()
        paragraph.lineSpacing = 4
        textView.defaultParagraphStyle = paragraph
        view.borderType = .lineBorder
        return view
    }

    func updateNSView(_ view: NSScrollView, context: Context) {
        guard let textView = view.documentView as? NSTextView, textView.string != text else { return }
        textView.string = text
        textView.scrollToBeginningOfDocument(nil)
    }
}
#else
private struct NoticeTextView: View {
    let text: String
    var body: some View {
        ScrollView { Text(text).font(.system(size: 11, design: .monospaced)).frame(maxWidth: .infinity, alignment: .leading) }
    }
}
#endif
