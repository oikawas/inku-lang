import SwiftUI

@MainActor
public struct SaijikiView: View {
    @Bindable var model: AppModel
    private let onInsertWord: ((String) -> Void)?
    private let wordLanguage: String?
    @State private var search = ""
    @State private var selection: Selection?
    @FocusState private var focusedSelection: Selection?

    public init(model: AppModel, onInsertWord: ((String) -> Void)? = nil, wordLanguage: String? = nil) {
        self.model = model
        self.onInsertWord = onInsertWord
        self.wordLanguage = wordLanguage
    }

    public var body: some View {
        GeometryReader { geometry in
            VStack(alignment: .leading, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(copy?.text("saijikiTitle") ?? model.display.localized("歳時記"))
                        .font(.title2.weight(.semibold))
                    if let copy {
                        Text(copy.text("saijikiHint")).font(.caption).foregroundStyle(.secondary)
                    }
                }
                TextField(model.display.localized("語を探す"), text: $search)
                    .textFieldStyle(.roundedBorder)
                    .help(tip("語を探す"))
                if geometry.size.width >= 660 {
                    HStack(alignment: .top, spacing: 12) {
                        wordList.frame(maxWidth: .infinity, maxHeight: .infinity)
                        previewPane.frame(width: 280).frame(maxHeight: .infinity)
                    }
                } else {
                    VStack(spacing: 12) {
                        wordList.frame(maxWidth: .infinity, maxHeight: .infinity)
                        previewPane.frame(height: min(250, max(180, geometry.size.height * 0.4)))
                    }
                }
            }.padding(16)
        }
        .onChange(of: focusedSelection) { _, value in
            if let value { selection = value }
        }
    }

    private var uiLanguage: String { model.display.preferences.language }
    private var offeredLanguage: String { wordLanguage ?? uiLanguage }
    private var copy: ProductReferenceCopy? { model.productReference?.localized(language: uiLanguage) }

    private var wordList: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                ForEach(model.saijiki) { category in
                    let words = category.words.filter {
                        matches($0.japanese + " " + ($0.english ?? "") + " " + $0.detail + " " + ($0.englishDetail ?? ""))
                    }
                    if !words.isEmpty {
                        VStack(alignment: .leading, spacing: 7) {
                            Text(uiLanguage == "ja" ? category.name : category.englishName ?? category.name)
                                .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                            SaijikiFlowLayout {
                                ForEach(words) { word in
                                    wordChip(name(word), selection: .builtin(word.id))
                                }
                            }
                        }
                    }
                }
                let plugins = model.pluginWords.filter {
                    matches(($0.japanese + $0.english + $0.aliases + [$0.id, $0.note, $0.englishNote ?? ""]).joined(separator: " "))
                }
                if !plugins.isEmpty {
                    VStack(alignment: .leading, spacing: 7) {
                        Text(model.display.localized("プラグインの語"))
                            .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                        SaijikiFlowLayout {
                            ForEach(plugins) { word in
                                wordChip(word.displayName(language: offeredLanguage), selection: .plugin(word.id))
                            }
                        }
                    }
                }
            }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 4)
        }
    }

    private func wordChip(_ title: String, selection value: Selection) -> some View {
        Button {
            selection = value
            if let onInsertWord, let preview = selectedPreview, preview.insertable, !model.isBusy { onInsertWord(preview.title) }
        } label: {
            Text(title).font(.callout).multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 8).padding(.vertical, 5)
                .background(.quaternary.opacity(selection == value ? 0.5 : 0.2), in: RoundedRectangle(cornerRadius: 5))
                .overlay(RoundedRectangle(cornerRadius: 5)
                    .stroke(selection == value ? Color.accentColor : Color.secondary.opacity(0.3)))
        }
        .buttonStyle(.plain)
        .focused($focusedSelection, equals: value)
        .onHover { hovering in if hovering { selection = value } }
        .help(model.display.tooltip("語彙を選ぶと、描画への効き方と作例を表示します。", serverKey: "saijikiHint"))
        .accessibilityAddTraits(selection == value ? .isSelected : [])
    }

    private var previewPane: some View {
        VStack(alignment: .leading, spacing: 12) {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    if let preview = selectedPreview {
                        SaijikiPreviewView(svg: preview.svg, imageURL: preview.imageURL, renderer: model.renderer)
                            .frame(maxWidth: .infinity).frame(height: 92).id(preview.id)
                        Text(preview.title).font(.headline)
                            .fixedSize(horizontal: false, vertical: true)
                        if !preview.effect.isEmpty {
                            Text(preview.effect).font(.callout).foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        if !preview.example.isEmpty {
                            Text(preview.example).font(.caption.monospaced()).foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        if !preview.insertable {
                            Text(model.display.localized("この語は参照のみです。DDLに挿入する定義が同梱されていません。"))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    } else if let copy {
                        Text(copy.text("saijikiPreviewPlaceholder"))
                            .font(.callout).foregroundStyle(.secondary)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled)
            }
            if let onInsertWord, let preview = selectedPreview {
                Button(model.display.localized("DDLに挿入")) {
                    guard !model.isBusy, preview.insertable else { return }
                    onInsertWord(preview.title)
                }
                .buttonStyle(.bordered)
                .disabled(model.isBusy || !preview.insertable)
                .help(tip("選んだ語を編集中DDLの末尾に挿入します。"))
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
    private func matches(_ text: String) -> Bool { search.isEmpty || text.localizedCaseInsensitiveContains(search) }
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
