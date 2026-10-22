import SwiftUI

@MainActor
public struct SaijikiView: View {
    @Bindable var model: AppModel
    private let onInsertWord: ((String) -> Void)?
    private let wordLanguage: String?
    private let inline: Bool
    private let onClose: (() -> Void)?
    @State private var selection: Selection?
    @FocusState private var focusedSelection: Selection?

    public init(model: AppModel, onInsertWord: ((String) -> Void)? = nil, wordLanguage: String? = nil, inline: Bool = false,
                onClose: (() -> Void)? = nil) {
        self.model = model
        self.onInsertWord = onInsertWord
        self.wordLanguage = wordLanguage
        self.inline = inline
        self.onClose = onClose
    }

    public var body: some View {
        Group {
            if inline { inlineBody } else { fullBody }
        }
        .onChange(of: focusedSelection) { _, value in
            if let value { selection = value }
        }
    }

    private var fullBody: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(copy?.text("saijikiTitle") ?? model.display.localized("歳時記"))
                        .inkuFont(17, weight: .light)
                    Text(hint)
                        .inkuFont(10).foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
                if let onClose {
                    Button(action: onClose) { Image(systemName: "xmark").inkuFont(16).frame(width: 24, height: 24) }
                        .buttonStyle(.plain).foregroundStyle(.secondary)
                        .accessibilityLabel(model.display.localized("閉じる"))
                }
            }.padding(.horizontal, 18).padding(.top, 16).padding(.bottom, 12)
            Divider()
            drawerPreview.padding(.horizontal, 12).padding(.top, 8).padding(.bottom, 8)
            wordList.frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    /// The drawer keeps the paper example above its vocabulary; the editor retains its own layout.
    private var drawerPreview: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let preview = selectedPreview {
                SaijikiPreviewView(svg: preview.svg, imageURL: preview.imageURL, renderer: model.renderer)
                    .frame(width: 216, height: 92).frame(maxWidth: .infinity).id(preview.id)
                Text(preview.title).inkuFont(13, weight: .semibold)
                if !preview.effect.isEmpty { Text(preview.effect).inkuFont(11).foregroundStyle(.secondary) }
                if !preview.example.isEmpty {
                    Text(model.display.webCopy("saijikiPreviewExampleLabel", "例文：") + preview.example)
                        .inkuFont(10).foregroundStyle(.secondary)
                }
                if !preview.insertable {
                    Text(model.display.localized("この語は参照のみです。DDLに挿入する定義が同梱されていません。"))
                        .inkuFont(10).foregroundStyle(.secondary)
                }
            } else {
                Text(model.display.webCopy("saijikiPreviewPlaceholder", "語を選ぶと、描画への効き方と作例を表示します。"))
                    .inkuFont(11).foregroundStyle(.secondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
        .padding(10).frame(maxWidth: .infinity, alignment: .leading)
        .background(.background, in: RoundedRectangle(cornerRadius: 4))
        .overlay(RoundedRectangle(cornerRadius: 4).stroke(InkuColor.border))
        .environment(\.colorScheme, .light)
    }

    /// SaijikiInline.svelte: grouped words and a nearby example, inside the editor rather than another window.
    private var inlineBody: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(copy?.text("saijikiTitle") ?? model.display.localized("歳時記")).inkuFont(12, weight: .semibold)
                Text(hint)
                    .inkuFont(11).foregroundStyle(.secondary)
            }.padding(.horizontal, 10).padding(.top, 8)
            Divider()
            GeometryReader { geometry in
                if geometry.size.width >= 580 {
                    let previewWidth = min(220, geometry.size.width * 0.25)
                    HStack(alignment: .top, spacing: 10) {
                        inlineWords(columns: min(4, max(1, Int((geometry.size.width - previewWidth - 20) / 145))))
                        previewPane.frame(width: previewWidth)
                    }
                } else {
                    VStack(spacing: 8) {
                        inlineWords(columns: max(1, Int(geometry.size.width / 155)))
                        previewPane.frame(height: min(140, geometry.size.height * 0.4))
                    }
                }
            }.padding(.horizontal, 10).padding(.bottom, 8)
        }
        .background(InkuColor.bg2, in: RoundedRectangle(cornerRadius: 4))
        .overlay(RoundedRectangle(cornerRadius: 4).stroke(InkuColor.border2))
    }

    private func inlineWords(columns: Int) -> some View {
        ScrollView {
            HStack(alignment: .top, spacing: 8) {
                ForEach(0..<columns, id: \.self) { column in
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(model.saijiki.indices.filter { $0 % columns == column }, id: \.self) { index in
                            let category = model.saijiki[index]
                            VStack(alignment: .leading, spacing: 6) {
                                Text(uiLanguage == "ja" ? category.name : category.englishName ?? category.name)
                                    .inkuFont(12, weight: .medium)
                                SaijikiFlowLayout {
                                    ForEach(category.words) { word in wordChip(name(word), selection: .builtin(word.id)) }
                                }
                            }.padding(8).frame(maxWidth: .infinity, alignment: .leading)
                                .overlay(RoundedRectangle(cornerRadius: 4).stroke(InkuColor.border2))
                        }
                        if column == columns - 1, !model.pluginWords.isEmpty {
                            VStack(alignment: .leading, spacing: 6) {
                                Text("Plugin").inkuFont(12, weight: .medium)
                                SaijikiFlowLayout {
                                    ForEach(model.pluginWords) { word in wordChip(word.displayName(language: offeredLanguage), selection: .plugin(word.id)) }
                                }
                            }.padding(8).frame(maxWidth: .infinity, alignment: .leading)
                                .overlay(RoundedRectangle(cornerRadius: 4).stroke(InkuColor.border2))
                        }
                    }.frame(maxWidth: .infinity, alignment: .topLeading)
                }
            }.padding(1)
        }
    }

    private var uiLanguage: String { model.display.preferences.language }
    private var offeredLanguage: String { wordLanguage ?? uiLanguage }
    private var copy: ProductReferenceCopy? { model.productReference?.localized(language: uiLanguage) }
    private var hint: String {
        if onInsertWord != nil {
            return model.display.localized("語にマウスを重ねると作例を表示します。クリックすると、挿入できる語を編集中の指示書に入れます。")
        }
        return model.display.webCopy("saijikiHint", "語彙を選ぶと、描画への効き方と作例を表示します。")
    }

    private var wordList: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0) {
                ForEach(model.saijiki) { category in
                    let words = category.words
                    if !words.isEmpty {
                        VStack(alignment: .leading, spacing: 7) {
                            HStack(alignment: .firstTextBaseline, spacing: 7) {
                                Text(category.name).inkuFont(13)
                                if let english = category.englishName, !english.isEmpty {
                                    Text(english).inkuFont(9, weight: .medium).foregroundStyle(.secondary)
                                }
                            }
                            SaijikiFlowLayout {
                                ForEach(words) { word in
                                    wordChip(name(word), selection: .builtin(word.id))
                                }
                            }
                        }.padding(.horizontal, 18).padding(.vertical, 10)
                        Divider()
                    }
                }
                let plugins = model.pluginWords
                if !plugins.isEmpty {
                    VStack(alignment: .leading, spacing: 7) {
                        HStack(alignment: .firstTextBaseline, spacing: 7) {
                            Text("Plugin").inkuFont(13)
                            Text("namespaced vocabulary").inkuFont(9, weight: .medium).foregroundStyle(.secondary)
                        }
                        SaijikiFlowLayout {
                            ForEach(plugins) { word in
                                wordChip(word.displayName(language: offeredLanguage), selection: .plugin(word.id))
                            }
                        }
                    }.padding(.horizontal, 18).padding(.vertical, 10)
                }
            }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 4)
        }
    }

    private func wordChip(_ title: String, selection value: Selection) -> some View {
        Button {
            selection = value
            if let onInsertWord, let preview = selectedPreview, preview.insertable, !model.isBusy { onInsertWord(preview.title) }
        } label: {
            Text(title).inkuFont(inline ? 12 : 13).multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, inline ? 5 : 8).padding(.vertical, inline ? 3 : 5)
                .background(.quaternary.opacity(selection == value ? 0.5 : 0.2), in: RoundedRectangle(cornerRadius: 5))
                .overlay(RoundedRectangle(cornerRadius: 5)
                    .stroke(selection == value ? Color.accentColor : Color.secondary.opacity(0.3)))
        }
        .buttonStyle(.plain)
        .focused($focusedSelection, equals: value)
        .onHover { hovering in if hovering { selection = value } }
        .inkuTooltip(model.display.tooltipValue(hint))
        .accessibilityAddTraits(selection == value ? .isSelected : [])
    }

    private var previewPane: some View {
        VStack(alignment: .leading, spacing: 12) {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    if let preview = selectedPreview {
                        SaijikiPreviewView(svg: preview.svg, imageURL: preview.imageURL, renderer: model.renderer)
                            .frame(maxWidth: .infinity).frame(height: 92).id(preview.id)
                        Text(preview.title).inkuFont(14, weight: .semibold)
                            .fixedSize(horizontal: false, vertical: true)
                        if !preview.effect.isEmpty {
                            Text(preview.effect).inkuFont(13).foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        if !preview.example.isEmpty {
                            Text((copy?.text("saijikiPreviewExampleLabel") ?? (uiLanguage == "ja" ? "例文：" : "Example: ")) + preview.example)
                                .inkuFont(12, design: .monospaced).foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        if !preview.insertable {
                            Text(model.display.localized("この語は参照のみです。DDLに挿入する定義が同梱されていません。"))
                                .inkuFont(12).foregroundStyle(.secondary)
                        }
                    } else if let copy {
                        Text(copy.text("saijikiPreviewPlaceholder"))
                            .inkuFont(13).foregroundStyle(.secondary)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled)
            }
            if !inline, let onInsertWord, let preview = selectedPreview {
                Button(model.display.localized("DDLに挿入")) {
                    guard !model.isBusy, preview.insertable else { return }
                    onInsertWord(preview.title)
                }
                .buttonStyle(.bordered)
                .disabled(model.isBusy || !preview.insertable)
                .inkuTooltip(tip("選んだ語を編集中DDLの末尾に挿入します。"))
            }
        }
        .padding(12).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(.quaternary.opacity(0.15), in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
    }

    private var selectedPreview: Preview? {
        switch selection {
        case .builtin(let id):
            guard let word = model.saijiki.lazy.flatMap(\.words).first(where: { $0.id == id }) else { return nil }
            return Preview(id: id, title: name(word),
                effect: word.preview?.effect(language: uiLanguage) ?? (uiLanguage == "ja" ? word.detail : word.englishDetail ?? ""),
                example: word.preview?.example(language: offeredLanguage) ?? "", svg: word.preview?.svg,
                imageURL: nil, insertable: true)
        case .plugin(let id):
            guard let word = model.pluginWords.first(where: { $0.id == id }) else { return nil }
            return Preview(id: id, title: word.displayName(language: offeredLanguage),
                effect: uiLanguage == "ja" ? word.note : word.englishNote ?? "",
                example: (offeredLanguage == "ja" ? word.firesOnJapanese : word.firesOnEnglish).first ?? "",
                svg: nil, imageURL: word.previewURL, insertable: word.packageID != nil)
        case nil: return nil
        }
    }

    private func name(_ word: SaijikiWord) -> String {
        offeredLanguage == "ja" ? word.japanese : word.english ?? word.japanese
    }
    private func tip(_ key: String) -> String {
        model.display.tooltip(key)
    }

    private enum Selection: Hashable { case builtin(String), plugin(String) }
    private struct Preview {
        let id: String
        let title: String
        let effect: String
        let example: String
        let svg: String?
        let imageURL: URL?
        let insertable: Bool
    }
}

/// Measures every chip within the available width so long qualified names wrap.
private struct SaijikiFlowLayout: Layout {
    private let spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let naturalWidth = subviews.reduce(0) { $0 + $1.sizeThatFits(.unspecified).width + spacing }
        let width = proposal.width.flatMap { $0.isFinite ? $0 : nil } ?? naturalWidth
        return arrangement(subviews, width: max(1, width)).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let layout = arrangement(subviews, width: max(1, bounds.width))
        for (index, subview) in subviews.enumerated() {
            subview.place(at: CGPoint(x: bounds.minX + layout.positions[index].x, y: bounds.minY + layout.positions[index].y),
                          anchor: .topLeading, proposal: ProposedViewSize(layout.sizes[index]))
        }
    }

    private func arrangement(_ subviews: Subviews, width: CGFloat) -> (size: CGSize, sizes: [CGSize], positions: [CGPoint]) {
        var sizes: [CGSize] = [], positions: [CGPoint] = []
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0
        for subview in subviews {
            let ideal = subview.sizeThatFits(.unspecified)
            let size = subview.sizeThatFits(ProposedViewSize(width: min(width, ideal.width), height: nil))
            if x > 0, x + size.width > width { x = 0; y += rowHeight + spacing; rowHeight = 0 }
            sizes.append(size); positions.append(CGPoint(x: x, y: y))
            x += size.width + spacing; rowHeight = max(rowHeight, size.height)
        }
        return (CGSize(width: width, height: y + rowHeight), sizes, positions)
    }
}
