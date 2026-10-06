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

    private static let groups = ["inku", "swift", "rust", "native", "resources"]

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(display.localized("第三者ライセンス")).inkuFont(14, weight: .semibold)
                Spacer()
                Button(display.localized("閉じる")) { dismiss() }.keyboardShortcut(.cancelAction)
            }
            .padding(.horizontal, 16).padding(.vertical, 10)
            Divider()
            if let notices {
                HStack(spacing: 0) {
                    List(selection: $selection) {
                        ForEach(Self.groups, id: \.self) { group in
                            Section(groupTitle(group)) {
                                ForEach(notices.components.filter { $0.group == group }) { component in
                                    VStack(alignment: .leading, spacing: 1) {
                                        Text(component.name).inkuFont(12)
                                        Text([component.version, component.license].filter { !$0.isEmpty }.joined(separator: " · "))
                                            .inkuFont(10).foregroundStyle(.secondary)
                                    }
                                    .tag(component.id)
                                }
                            }
                        }
                    }
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
        .frame(minWidth: 760, idealWidth: 860, minHeight: 520, idealHeight: 640)
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
            LabeledContent(display.localized("ライセンス"), value: component.license).inkuFont(12)
            LabeledContent(display.localized("入手先")) {
                if let url = URL(string: component.source) { Link(component.source, destination: url) }
                else { Text(component.source) }
            }.inkuFont(12)
            if !component.note.isEmpty {
                Text(component.note).inkuFont(12).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            NoticeTextView(text: body).frame(maxWidth: .infinity, maxHeight: .infinity)
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
        textView.textContainerInset = NSSize(width: 6, height: 6)
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
