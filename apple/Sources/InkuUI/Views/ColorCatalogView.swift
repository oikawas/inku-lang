import SwiftUI
#if os(macOS)
import AppKit
#endif

@MainActor
struct ColorCatalogView: View {
    @Bindable var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var draftCatalogID: String
    @State private var draftMode: String
    private let descriptionOnly: Bool
    #if os(macOS)
    private let sheetSize: CGSize
    #endif

    init(model: AppModel, descriptionOnly: Bool = false) {
        self.model = model
        self.descriptionOnly = descriptionOnly
        _draftCatalogID = State(initialValue: model.catalogID)
        _draftMode = State(initialValue: model.catalogMode == "auto" && (descriptionOnly || model.inputMode == "description") ? "auto" : "fixed")
        #if os(macOS)
        let available = NSApp.keyWindow?.contentView?.bounds.size ?? CGSize(width: 1212, height: 868)
        sheetSize = CGSize(width: min(1180, max(640, available.width - 32)), height: min(820, max(440, available.height - 48)))
        #endif
    }

    private var allowsDescriptionAuto: Bool { descriptionOnly || model.inputMode == "description" }
    private var selectedCatalog: ColorCatalogOption? { model.catalogs.first { $0.id == draftCatalogID } }
    private var canConfirm: Bool {
        !model.isBusy && selectedCatalog != nil && ["fixed", "auto"].contains(draftMode)
            && (draftMode != "auto" || allowsDescriptionAuto)
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(model.display.localized("色カタログ")).font(.headline)
                Spacer()
                Button { confirm() } label: { Image(systemName: "xmark") }
                    .buttonStyle(.plain)
                    .disabled(!canConfirm)
                    .accessibilityLabel(model.display.localized("閉じる"))
                    .help(model.display.preferences.showTooltips ? model.display.localized("閉じる") : "")
            }
            .padding(.horizontal, 18).padding(.vertical, 14).background(.bar)
            Divider()
            GeometryReader { geometry in
                ScrollView {
                    LazyVStack(spacing: 8) {
                        if allowsDescriptionAuto { automaticCard }
                        ForEach(model.catalogs) { catalog in
                            catalogCard(catalog, width: geometry.size.width)
                        }
                    }
                    .padding(10)
                }
            }
            Divider()
            HStack { Spacer(); footerActions }
                .padding(.horizontal, 18).padding(.vertical, 12).background(.bar)
        }
        .background(.background)
        #if os(macOS)
        .frame(width: sheetSize.width, height: sheetSize.height)
        #endif
        .onChange(of: model.inputMode) { _, mode in
            if !descriptionOnly, mode == "ddl", draftMode == "auto" { draftMode = "fixed" }
        }
    }

    private func confirm() {
        guard canConfirm else { return }
        model.catalogID = draftCatalogID
        model.catalogMode = draftMode
        dismiss()
    }

    private var footerActions: some View {
        HStack(spacing: 10) {
            Button(model.display.localized("キャンセル")) { dismiss() }.keyboardShortcut(.cancelAction)
            Button(model.display.localized("決定")) { confirm() }
            .buttonStyle(.borderedProminent)
            .keyboardShortcut(.defaultAction)
            .disabled(!canConfirm)
        }.fixedSize(horizontal: true, vertical: false)
    }

    private var automaticCard: some View {
        Button { draftMode = "auto" } label: {
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 5) {
                    Text(model.display.localized("記述から自動選択")).font(.system(size: 12, weight: .semibold))
                    if draftMode == "auto" { Image(systemName: "checkmark").foregroundStyle(.tint) }
                }
                Text(model.display.localized("描くたびに記述を読んで選ぶ")).font(.system(size: 10)).foregroundStyle(.secondary)
            }
            .padding(10).frame(maxWidth: .infinity, alignment: .leading)
            .background(draftMode == "auto" ? Color.accentColor.opacity(0.10) : Color.secondary.opacity(0.03),
                        in: RoundedRectangle(cornerRadius: 6))
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(draftMode == "auto" ? Color.accentColor : Color.secondary.opacity(0.25)))
            .contentShape(RoundedRectangle(cornerRadius: 6))
        }
        .buttonStyle(.plain).disabled(model.isBusy)
        .accessibilityAddTraits(draftMode == "auto" ? [.isSelected] : [])
    }

    private func catalogCard(_ catalog: ColorCatalogOption, width: CGFloat) -> some View {
        let selected = draftMode == "fixed" && draftCatalogID == catalog.id
        return Button {
            draftCatalogID = catalog.id
            draftMode = "fixed"
        } label: {
            Group {
                if width >= 640 {
                    HStack(alignment: .top, spacing: 12) {
                        catalogHeading(catalog, selected: selected).frame(width: max(112, (width - 52) * 0.16), alignment: .leading)
                        catalogPalette(catalog, columns: width >= 980 ? 10 : 5)
                    }
                } else {
                    VStack(alignment: .leading, spacing: 7) {
                        catalogHeading(catalog, selected: selected)
                        catalogPalette(catalog, columns: 5)
                    }
                }
            }
            .padding(8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background {
                RoundedRectangle(cornerRadius: 6, style: .continuous).fill(.background)
                if selected {
                    RoundedRectangle(cornerRadius: 6, style: .continuous).fill(Color.accentColor.opacity(0.10))
                }
            }
            .overlay {
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                    .stroke(selected ? Color.accentColor : Color.secondary.opacity(0.25))
            }
            .contentShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
        }
        .buttonStyle(.plain)
        .disabled(model.isBusy)
        .accessibilityLabel(catalogAccessibilityLabel(catalog))
        .accessibilityAddTraits(selected ? [.isSelected] : [])
    }

    private func catalogAccessibilityLabel(_ catalog: ColorCatalogOption) -> String {
        let colors = catalog.palette.map { swatch in
            [swatch.name, model.display.preferences.language == "ja" ? swatch.japaneseName : nil, swatch.code].compactMap { $0 }.joined(separator: ", ")
        }
        return ([catalog.name, catalog.id, catalog.localizedDetail(language: model.display.preferences.language)] + colors)
            .joined(separator: ", ")
    }

    private func catalogHeading(_ catalog: ColorCatalogOption, selected: Bool) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(alignment: .firstTextBaseline, spacing: 5) {
                Text(catalog.name).font(.system(size: 12, weight: .semibold))
                if selected { Image(systemName: "checkmark").foregroundStyle(.tint).accessibilityHidden(true) }
            }
            Text(catalog.id).font(.system(size: 9, design: .monospaced)).foregroundStyle(.secondary)
            Text(catalog.localizedDetail(language: model.display.preferences.language))
                .font(.system(size: 10)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func catalogPalette(_ catalog: ColorCatalogOption, columns: Int) -> some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(minimum: 0), spacing: 5, alignment: .top), count: columns), spacing: 8) {
            ForEach(Array(catalog.palette.enumerated()), id: \.offset) { _, swatch in
                VStack(spacing: 2) {
                    CatalogSwatchShape(swatch: swatch).frame(height: 38)
                    Text(swatch.code).font(.system(size: 8, design: .monospaced)).foregroundStyle(.secondary).lineLimit(1)
                    Text(swatch.name).font(.system(size: 9)).lineLimit(1)
                    if model.display.preferences.language == "ja", let japaneseName = swatch.japaneseName, !japaneseName.isEmpty {
                        Text(japaneseName).font(.system(size: 8)).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel([swatch.name, model.display.preferences.language == "ja" ? swatch.japaneseName : nil, swatch.code].compactMap { $0 }.joined(separator: ", "))
            }
        }
    }
}

@MainActor
struct ColorCatalogPreview: View {
    let catalog: ColorCatalogOption?
    let mode: String
    let display: DisplaySettings

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label(display.localized("色カタログ"), systemImage: "paintpalette").font(.subheadline.weight(.semibold))
                Spacer()
                Image(systemName: "chevron.right").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            }
            if mode == "fixed" {
                if let catalog {
                    Text(catalog.name).font(.callout.weight(.medium))
                    HStack(spacing: 3) {
                        ForEach(Array(catalog.palette.enumerated()), id: \.offset) { _, swatch in
                            CatalogSwatchShape(swatch: swatch)
                        }
                    }
                    .frame(height: 18).accessibilityHidden(true)
                    Text(catalog.localizedDetail(language: display.preferences.language)).font(.caption).foregroundStyle(.secondary)
                } else {
                    Text(display.localized("選択してください")).font(.caption).foregroundStyle(.secondary)
                }
            } else {
                Text(display.localized(mode == "random" ? "生成ごとに配色をランダムに選びます。" : "次の生成で、記述から配色を選びます。"))
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.background, in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(.quaternary))
    }
}

private struct CatalogSwatchShape: View {
    let swatch: ColorCatalogSwatch

    private var color: Color {
        let hex = swatch.code.dropFirst()
        guard swatch.code.first == "#", hex.count == 6, let rgb = UInt32(hex, radix: 16) else { return .clear }
        return Color(.sRGB, red: Double((rgb >> 16) & 255) / 255,
                     green: Double((rgb >> 8) & 255) / 255, blue: Double(rgb & 255) / 255, opacity: 1)
    }

    var body: some View {
        RoundedRectangle(cornerRadius: 4)
            .fill(color)
            .overlay(RoundedRectangle(cornerRadius: 4).stroke(.secondary.opacity(0.3)))
            .accessibilityHidden(true)
    }
}
