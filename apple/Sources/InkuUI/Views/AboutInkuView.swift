import Foundation
import InkuCore
import SwiftUI

#if os(macOS)
@MainActor
public struct AboutInkuScreen: View {
    @Bindable private var model: AppModel

    public init(model: AppModel) { self.model = model }

    public var body: some View {
        Form {
            AboutInkuView(model: model)
        }
        .formStyle(.grouped)
        .environment(model.display)
        .environment(\.locale, Locale(identifier: model.display.preferences.language))
        .preferredColorScheme(model.display.colorScheme)
        .environment(\.inkuTextScale, model.display.preferences.textScale)
        .font(.system(size: 13 * model.display.preferences.textScale))
    }
}
#endif

@MainActor
struct AboutInkuView: View {
    @Bindable var model: AppModel
    @State private var showsLicenses = false

    private static let bindingReport: [String: String] = {
        (try? JSONSerialization.jsonObject(with: Data(InkuCore.versionReport.utf8)) as? [String: String]) ?? [:]
    }()

    var body: some View {
        Group {
            if let reference = model.productReference,
               let copy = reference.localized(language: model.display.preferences.language) {
                Section("inku") {
                    // The macOS application has its own version (apple/VERSION, apple/BUILD_NUMBER);
                    // the Server release it follows is shown beside it.
                    LabeledContent(copy.text("appInfoVersionLabel"), value: bundleValue("CFBundleShortVersionString"))
                    LabeledContent(copy.text("appInfoBuildLabel"), value: bundleValue("CFBundleVersion"))
                    LabeledContent(model.display.localized("対応するServerの版"),
                                   value: "\(reference.version) (\(copy.text("appInfoBuildLabel")) \(reference.build))")
                    LabeledContent(model.display.localized("対応するServerのビルド日時"), value: buildDate(reference.buildDate))
                    versionRow("DDL Spec. ver.", value: reference.versions["ddlSpec"],
                               hint: copy.text("appInfoHintDdlSpec"))
                    versionRow("DDL engine ver.", value: reference.versions["ddlEngine"],
                               hint: copy.text("appInfoHintDdlEngine"))
                    versionRow("Render engine ver.", value: reference.versions["renderEngine"],
                               hint: copy.text("appInfoHintRenderEngine"))
                    versionRow("Binding protocol ver.", value: Self.bindingReport["protocol_version"],
                               hint: copy.text("appInfoHintBindingProtocol"))
                    LabeledContent(copy.text("appInfoRepositoryLabel")) {
                        Link("https://github.com/oikawas/inku-lang", destination: URL(string: "https://github.com/oikawas/inku-lang")!)
                    }
                }
                Section(model.display.localized("ライセンス")) {
                    LabeledContent("inku", value: "MIT License")
                    Button(model.display.localized("第三者ライセンスを表示")) { showsLicenses = true }
                }
                Section(copy.text("appInfoConceptTitle")) {
                    Text(copy.text("appInfoConceptBody")).fixedSize(horizontal: false, vertical: true)
                }
                Section(copy.text("appInfoVocabTitle")) {
                    Text(copy.text("appInfoVocabIntro")).font(.callout).foregroundStyle(.secondary)
                    Grid(alignment: .topLeading, horizontalSpacing: 18, verticalSpacing: 12) {
                        GridRow {
                            Text(copy.text("appInfoVocabColTerm")).fontWeight(.semibold)
                            Text(copy.text("appInfoVocabColMeaning")).fontWeight(.semibold)
                        }
                        Divider().gridCellUnsizedAxes(.horizontal)
                        ForEach(Array(copy.vocabulary.enumerated()), id: \.offset) { _, row in
                            GridRow {
                                Text(row.term).fontWeight(.medium)
                                    .frame(maxWidth: 220, alignment: .leading)
                                    .fixedSize(horizontal: false, vertical: true)
                                Text(row.meaning).fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }.font(.callout).frame(maxWidth: .infinity, alignment: .leading)
                }
                Section(copy.text("appInfoCreatorTitle")) {
                    Text(copy.text("appInfoCreatorName")).font(.headline)
                    Text(copy.text("appInfoCreatorBody")).fixedSize(horizontal: false, vertical: true)
                }
            } else {
                Section("inku") { Text(model.display.localized("未記録")).foregroundStyle(.secondary) }
            }
        }
        .textSelection(.enabled)
        .sheet(isPresented: $showsLicenses) { ThirdPartyNoticesView(display: model.display) }
    }

    private func bundleValue(_ key: String) -> String {
        (Bundle.main.object(forInfoDictionaryKey: key) as? String).flatMap { $0.isEmpty ? nil : $0 }
            ?? model.display.localized("未記録")
    }

    private func versionRow(_ title: String, value: String?, hint: String) -> some View {
        LabeledContent {
            Text(value.flatMap { $0.isEmpty ? nil : $0 } ?? model.display.localized("未記録"))
                .monospacedDigit()
        } label: {
            Text(title).help(model.display.preferences.showTooltips ? hint : "")
        }
    }

    private func buildDate(_ value: String) -> String {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var date = iso.date(from: value)
        if date == nil { iso.formatOptions = [.withInternetDateTime]; date = iso.date(from: value) }
        guard let date else { return model.display.localized("未記録") }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: model.display.preferences.language == "en" ? "en_US" : "ja_JP")
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter.string(from: date)
    }
}
