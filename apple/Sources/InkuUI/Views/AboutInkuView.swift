import Foundation
import InkuCore
import SwiftUI

#if os(macOS)
@MainActor
public struct AboutInkuScreen: View {
    @Bindable private var model: AppModel

    public init(model: AppModel) { self.model = model }

    public var body: some View {
        ScrollView {
            AboutInkuView(model: model).padding(20)
        }
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
                VStack(alignment: .leading, spacing: 12) {
                    Text(copy.text("appInfoTitle")).inkuFont(20, weight: .light)
                    // The macOS application has its own version (apple/VERSION, apple/BUILD_NUMBER);
                    // the Server release it follows is shown beside it.
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(spacing: 18) {
                            versionRow(copy.text("appInfoVersionLabel"), value: bundleValue("CFBundleShortVersionString"))
                            versionRow(copy.text("appInfoBuildLabel"), value: bundleValue("CFBundleVersion"))
                        }
                        ViewThatFits(in: .horizontal) {
                            HStack(spacing: 18) { layerVersions(reference, copy: copy) }
                            VStack(alignment: .leading, spacing: 6) { layerVersions(reference, copy: copy) }
                        }
                        versionRow(model.display.localized("対応するServerの版"),
                                   value: "\(reference.version) (\(copy.text("appInfoBuildLabel")) \(reference.build))")
                        versionRow(model.display.preferences.language == "en" ? "Reference exported" : "参照資料の生成日時",
                                   value: buildDate(reference.buildDate))
                        HStack(spacing: 8) {
                            Text(copy.text("appInfoRepositoryLabel")).foregroundStyle(.secondary)
                            Link("https://github.com/oikawas/inku-lang", destination: URL(string: "https://github.com/oikawas/inku-lang")!)
                        }.inkuFont(12)
                    }
                    Divider()
                    aboutSection(copy.text("appInfoLicenseTitle")) {
                        Text("inku · MIT License")
                        Button(copy.text("appInfoShowNotices")) { showsLicenses = true }
                    }
                    aboutSection(copy.text("appInfoConceptTitle")) {
                        Text(copy.text("appInfoConceptBody")).fixedSize(horizontal: false, vertical: true)
                    }
                    aboutSection(copy.text("appInfoVocabTitle")) {
                        Text(copy.text("appInfoVocabIntro")).foregroundStyle(.secondary)
                        Grid(alignment: .topLeading, horizontalSpacing: 18, verticalSpacing: 8) {
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
                        }.frame(maxWidth: .infinity, alignment: .leading)
                    }
                    aboutSection(copy.text("appInfoCreatorTitle")) {
                        Text(copy.text("appInfoCreatorName")).fontWeight(.medium)
                        Text(copy.text("appInfoCreatorBody")).fixedSize(horizontal: false, vertical: true)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading).inkuFont(13)
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

    private func versionRow(_ title: String, value: String?, hint: String = "") -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text(title).foregroundStyle(.secondary)
                .inkuTooltip(model.display.preferences.showTooltips ? hint : "")
            Text(value.flatMap { $0.isEmpty ? nil : $0 } ?? model.display.localized("未記録"))
                .monospacedDigit()
        }.inkuFont(12).fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder private func layerVersions(_ reference: ProductReference, copy: ProductReferenceCopy) -> some View {
        versionRow("DDL Spec. ver.", value: reference.versions["ddlSpec"], hint: copy.text("appInfoHintDdlSpec"))
        versionRow("DDL engine ver.", value: reference.versions["ddlEngine"], hint: copy.text("appInfoHintDdlEngine"))
        versionRow("Render engine ver.", value: reference.versions["renderEngine"], hint: copy.text("appInfoHintRenderEngine"))
        versionRow("Binding protocol ver.", value: Self.bindingReport["protocol_version"], hint: copy.text("appInfoHintBindingProtocol"))
    }

    private func aboutSection<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).inkuFont(14, weight: .medium)
            content()
        }.padding(.vertical, 6).frame(maxWidth: .infinity, alignment: .leading)
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
