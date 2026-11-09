import Foundation
import SwiftUI

/// The reviewed snapshot that apple/scripts/build-macos-notices.py writes from the locked inputs, followed by the
/// bundled 3D viewer's own notices file, read from the app's copy (`Ddl3DViewerNotices`; never in the snapshot).
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
              let data = try? Data(contentsOf: url),
              let snapshot = try? JSONDecoder().decode(ThirdPartyNotices.self, from: data) else { return nil }
        // An app built without the viewer's copy (a plain `swift build`) ships none of it, so it lists no 3D entry.
        guard let registration = Ddl3DInstallation.registered,
              let viewer = Ddl3DViewerNotices(registration: registration) else { return snapshot }
        let key = "ddl3d/\(viewer.build)"
        let component = Component(group: "ddl3d", name: Ddl3DViewerNotices.name, version: viewer.build, license: viewer.license,
                                  source: Ddl3DViewerNotices.source, note: viewer.note,
                                  texts: [LicenseText(label: "THIRD_PARTY_NOTICES.txt", text: key)])
        return ThirdPartyNotices(components: snapshot.components + [component], texts: snapshot.texts.merging([key: viewer.text]) { $1 })
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
    @State private var phoneDetailShown = false
    @Environment(\.inkuPhoneLayout) private var phone

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
            if let notices, phone {
                // iPhone (ios-app step 7c): the list, then one notice on the whole width with a way back.
                if phoneDetailShown, let component = notices.components.first(where: { $0.id == selection }) {
                    VStack(alignment: .leading, spacing: 0) {
                        Button { phoneDetailShown = false } label: {
                            Label(display.localized("一覧"), systemImage: "chevron.left")
                        }.padding(.horizontal, 14).padding(.vertical, 8)
                        Divider()
                        detail(component, body: notices.body(of: component))
                    }
                } else {
                    List {
                        ForEach(Self.groups.filter { group in notices.components.contains { $0.group == group } }, id: \.self) { group in
                            Section(groupTitle(group)) {
                                ForEach(notices.components.filter { $0.group == group }) { component in
                                    Button { selection = component.id; phoneDetailShown = true } label: {
                                        VStack(alignment: .leading, spacing: 1) {
                                            Text(component.name).inkuFont(12)
                                            Text([component.version, component.license].filter { !$0.isEmpty }.joined(separator: " · "))
                                                .inkuFont(10).foregroundStyle(.secondary)
                                        }.frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
                                    }.buttonStyle(.plain)
                                }
                            }
                        }
                    }
                    .listStyle(.plain)
                    .accessibilityLabel(display.webCopy("noticesList", "ライセンスの一覧"))
                }
            } else if let notices {
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
        .inkuWideFrame(minWidth: 760, idealWidth: 960, minHeight: 520, idealHeight: 640)
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
        // The bundled 3D viewer's own notices file, read from the app's copy (Ddl3DViewerNotices).
        case "ddl3d": display.webCopy("ddl3dTitle", "3D表示（実験）")
        default: "inku"
        }
    }
}

/// Some notices (the Rust standard library's, 1.4 MB) are long: a lazy stack lays out only the paragraphs on screen
/// (PLAN §7: 0.08 s to show, where the text view took 0.01 s). A selection stays inside one paragraph.
private struct NoticeTextView: View {
    let text: String
    @State private var paragraphs: [String] = []

    var body: some View {
        ScrollView {
            // About one line between paragraphs, where the text had an empty line.
            LazyVStack(alignment: .leading, spacing: 15) {
                ForEach(paragraphs.indices, id: \.self) { index in
                    Text(paragraphs[index]).font(.system(size: 11, design: .monospaced)).lineSpacing(4)
                        .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding(10)
        }
        // Another component's notices start at the top.
        .id(text)
        .background(.background)
        .border(Color.secondary.opacity(0.5))
        .onChange(of: text, initial: true) { _, now in paragraphs = now.components(separatedBy: "\n\n") }
    }
}
