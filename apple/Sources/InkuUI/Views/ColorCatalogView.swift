import SwiftUI

@MainActor
struct ColorCatalogView: View {
    @Bindable var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var draftCatalogID: String
    @State private var draftMode: String

    init(model: AppModel) {
        self.model = model
        _draftCatalogID = State(initialValue: model.catalogID)
        _draftMode = State(initialValue: model.inputMode == "ddl" && model.catalogMode == "auto" ? "fixed" : model.catalogMode)
    }

    private var allowsDescriptionAuto: Bool { model.inputMode == "description" }
    private var selectedCatalog: ColorCatalogOption? { model.catalogs.first { $0.id == draftCatalogID } }
    private var canConfirm: Bool {
        !model.isBusy && selectedCatalog != nil && ["fixed", "random", "auto"].contains(draftMode)
            && (draftMode != "auto" || allowsDescriptionAuto)
    }

    var body: some View {
        VStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Label(model.display.localized("色カタログ"), systemImage: "paintpalette")
                        .font(.title2.weight(.semibold))
                    Spacer()
                    Button { dismiss() } label: { Image(systemName: "xmark") }
                        .buttonStyle(.plain)
                        .accessibilityLabel(model.display.localized("キャンセル"))
                        .help(model.display.preferences.showTooltips ? model.display.localized("キャンセル") : "")
                }
                Text(model.display.localized("次の生成に使う配色を選びます。"))
                    .font(.callout).foregroundStyle(.secondary)
                Picker(model.display.localized("配色の選び方"), selection: $draftMode) {
                    Text(model.display.localized("指定")).tag("fixed")
                    Text(model.display.localized("ランダム")).tag("random")
                    if allowsDescriptionAuto { Text(model.display.localized("記述から選択")).tag("auto") }
                }
                .pickerStyle(.segmented).disabled(model.isBusy)
                if draftMode == "random" || draftMode == "auto" {
                    Label(model.display.localized(draftMode == "random" ? "生成ごとに配色をランダムに選びます。" : "次の生成で、記述から配色を選びます。"),
                          systemImage: draftMode == "random" ? "shuffle" : "text.magnifyingglass")
                        .font(.callout).foregroundStyle(.secondary)
                }
            }
            .padding(20).background(.bar)
            Divider()
            GeometryReader { geometry in
                ScrollView {
                    LazyVStack(spacing: 12) {
                        ForEach(model.catalogs) { catalog in
                            catalogCard(catalog, horizontal: geometry.size.width >= 820)
                        }
                    }
                    .padding(20)
                }
            }
            Divider()
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 16) { selectionSummary; Spacer(); footerActions }
                VStack(alignment: .leading, spacing: 12) { selectionSummary; HStack { Spacer(); footerActions } }
            }
            .padding(20).background(.bar)
        }
        .background(.background)
        #if os(macOS)
        .frame(minWidth: 680, idealWidth: 960, maxWidth: 1100, minHeight: 520, idealHeight: 700, maxHeight: 820)
        #endif
        .onChange(of: model.inputMode) { _, mode in
            if mode == "ddl", draftMode == "auto" { draftMode = "fixed" }
        }
    }

    private var selectionSummary: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(model.display.localized("配色")).font(.caption).foregroundStyle(.secondary)
            Text(draftMode == "fixed" ? selectedCatalog?.name ?? "—" : model.display.localized(draftMode == "random" ? "ランダム" : "記述から選択"))
                .font(.headline).lineLimit(2)
        }
    }

    private var footerActions: some View {
        HStack(spacing: 10) {
            Button(model.display.localized("キャンセル")) { dismiss() }.keyboardShortcut(.cancelAction)
            Button(model.display.localized("決定")) {
                guard canConfirm else { return }
                model.catalogID = draftCatalogID
                model.catalogMode = draftMode
                dismiss()
            }
            .buttonStyle(.borderedProminent)
            .keyboardShortcut(.defaultAction)
            .disabled(!canConfirm)
        }.fixedSize(horizontal: true, vertical: false)
    }

    private func catalogCard(_ catalog: ColorCatalogOption, horizontal: Bool) -> some View {
        let selected = draftMode == "fixed" && draftCatalogID == catalog.id
        return Button {
            draftCatalogID = catalog.id
            draftMode = "fixed"
        } label: {
            Group {
                if horizontal {
                    HStack(alignment: .top, spacing: 20) {
                        catalogHeading(catalog, selected: selected).frame(width: 180, alignment: .leading)
                        catalogPalette(catalog)
                    }
                } else {
                    VStack(alignment: .leading, spacing: 14) {
                        catalogHeading(catalog, selected: selected)
                        catalogPalette(catalog)
                    }
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background {
                RoundedRectangle(cornerRadius: 12, style: .continuous).fill(.background)
                if selected {
                    RoundedRectangle(cornerRadius: 12, style: .continuous).fill(Color.accentColor.opacity(0.08))
                }
            }
            .overlay {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(selected ? Color.accentColor : Color.secondary.opacity(0.25), lineWidth: selected ? 2 : 1)
            }
            .contentShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
        .buttonStyle(.plain)
        .disabled(model.isBusy)
        .accessibilityLabel(catalogAccessibilityLabel(catalog))
        .accessibilityAddTraits(selected ? [.isSelected] : [])
    }

    private func catalogAccessibilityLabel(_ catalog: ColorCatalogOption) -> String {
        let colors = catalog.palette.map { swatch in
            [swatch.name, swatch.japaneseName, swatch.code].compactMap { $0 }.joined(separator: ", ")
        }
        return ([catalog.name, catalog.id, catalog.localizedDetail(language: model.display.preferences.language)] + colors)
            .joined(separator: ", ")
    }

    private func catalogHeading(_ catalog: ColorCatalogOption, selected: Bool) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(catalog.name).font(.headline)
                if selected { Image(systemName: "checkmark.circle.fill").foregroundStyle(.tint).accessibilityHidden(true) }
            }
            Text(catalog.id).font(.system(.caption, design: .monospaced)).foregroundStyle(.secondary)
            Text(catalog.localizedDetail(language: model.display.preferences.language))
                .font(.callout).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func catalogPalette(_ catalog: ColorCatalogOption) -> some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 90), spacing: 10, alignment: .top)], alignment: .leading, spacing: 14) {
            ForEach(Array(catalog.palette.enumerated()), id: \.offset) { _, swatch in
                VStack(alignment: .leading, spacing: 4) {
                    CatalogSwatchShape(swatch: swatch).frame(height: 38)
                    Text(swatch.code).font(.system(.caption, design: .monospaced)).foregroundStyle(.secondary)
                    Text(swatch.name).font(.caption).fixedSize(horizontal: false, vertical: true)
                    if let japaneseName = swatch.japaneseName, !japaneseName.isEmpty {
                        Text(japaneseName).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    }
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel([swatch.name, swatch.japaneseName, swatch.code].compactMap { $0 }.joined(separator: ", "))
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
