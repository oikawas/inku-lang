import InkuPersistence
import SwiftUI

/// Library labels are projections of saved facts, never replacements for source text.
enum LibraryWorkPresentation {
    static func usesDDLTitle(_ work: SavedWork) -> Bool {
        work.effectiveSourceText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !(work.ddl ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    static func title(_ work: SavedWork, untitled: String) -> String {
        if !work.effectiveSourceText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return work.effectiveSourceText
        }
        return work.ddl?.split(whereSeparator: \.isNewline)
            .first(where: { !$0.trimmingCharacters(in: .whitespaces).isEmpty })
            .map(String.init) ?? untitled
    }
}

struct LibraryWorkTitle: View {
    let work: SavedWork
    let untitled: String
    var lineLimit = 2
    /// The Web px size of a description; a DDL line is set one step smaller in monospace.
    var size: Double = 13

    var body: some View {
        Text(LibraryWorkPresentation.title(work, untitled: untitled))
            .inkuFont(LibraryWorkPresentation.usesDDLTitle(work) ? size - 1 : size, design: LibraryWorkPresentation.usesDDLTitle(work) ? .monospaced : .default)
            .foregroundStyle(.primary)
            .lineLimit(lineLimit)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// Web HistoryDescription.svelte: three lines, then a 全文 / 折りたたむ button when the text is cut, whose title says
/// which way it goes.
@MainActor
struct LibraryExpandableTitle: View {
    let work: SavedWork
    let display: DisplaySettings
    var size: Double = 13
    @State private var expanded = false
    @State private var shownHeight: CGFloat = 0
    @State private var fullHeight: CGFloat = 0

    private var title: String { LibraryWorkPresentation.title(work, untitled: display.localized("無題")) }
    private var ddl: Bool { LibraryWorkPresentation.usesDDLTitle(work) }

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            text.lineLimit(expanded ? nil : 3)
                .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { shownHeight = $0 }
                .background(alignment: .topLeading) {
                    text.fixedSize(horizontal: false, vertical: true).hidden()
                        .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { fullHeight = $0 }
                }
            if expanded || fullHeight > shownHeight + 1 {
                Button(display.webCopy(expanded ? "historyDescriptionCollapse" : "historyDescriptionExpand",
                                       fallback: expanded ? "折りたたむ" : "全文")) { expanded.toggle() }
                    .buttonStyle(.borderless).inkuFont(11).foregroundStyle(Color.accentColor)
                    .accessibilityValue(display.localized(expanded ? "展開中" : "折りたたみ中"))
                    .inkuTooltip(display.tooltip(expanded ? "記述を折りたたむ" : "記述の全文を表示",
                                                 serverKey: expanded ? "historyDescriptionCollapseTitle" : "historyDescriptionExpandTitle"))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .onChange(of: work.id) { expanded = false }
    }

    private var text: some View {
        Text(title)
            .inkuFont(ddl ? size - 1 : size, design: ddl ? .monospaced : .default)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

@MainActor
struct LibraryModelFactsView: View {
    let work: SavedWork
    let display: DisplaySettings
    var compact = false

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            ForEach(SavedWorkFacts.models(work)) { fact in
                HStack(alignment: .firstTextBaseline, spacing: 5) {
                    Text(display.localized(fact.label)).foregroundStyle(.secondary)
                    Text(fact.reference ?? display.localized("未記録"))
                        .foregroundStyle(fact.reference == nil ? Color.secondary : Color.primary)
                        .lineLimit(compact ? 1 : nil)
                        .textSelection(.enabled)
                }
                .inkuTooltip(display.tooltipValue(display.localized(fact.label) + ": " + (fact.reference ?? display.localized("未記録"))))
            }
        }.inkuFont(compact ? 10 : 12)
    }
}

/// Web `modelLines` on a library card: "解釈:" / "描画:" only when the two stages differ (HistoryManager.svelte:364-374).
@MainActor
struct LibraryModelLinesView: View {
    let work: SavedWork
    let display: DisplaySettings
    let naming: ModelNaming

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(naming.cardLines(stage1: work.stage1Model, stage2: work.stage2Model).enumerated()), id: \.offset) { _, line in
                let role = line.role.map { display.webCopy($0 == .interpretation ? "historyModelInterpretation" : "historyModelDrawing",
                                                            fallback: $0 == .interpretation ? "解釈" : "描画") }
                let unrecorded = display.webCopy("historyModelUnrecorded", fallback: "未記録")
                (Text(role.map { $0 + ":" } ?? "").foregroundStyle(.secondary) + Text(line.compact ?? unrecorded))
                    .lineLimit(1).truncationMode(.tail)
                    .inkuTooltip(display.tooltipValue((role.map { $0 + ": " } ?? "") + (line.full ?? unrecorded)))
            }
        }
        .inkuFont(12).lineSpacing(3)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

@MainActor
struct LibraryWorkMarks: View {
    @Bindable var model: AppModel
    let work: SavedWork
    var spacing: CGFloat = 12
    private var library: LibraryModel { model.library }

    var body: some View {
        HStack(spacing: spacing) {
            Button { Task { await library.toggleStar(work) } } label: {
                Image(systemName: work.starred ? "star.fill" : "star")
                    .foregroundStyle(work.starred ? Color.accentColor : Color.secondary)
            }
            .accessibilityLabel(model.display.localized(work.starred ? "お気に入りを解除" : "お気に入り"))
            .inkuTooltip(model.display.tooltip(work.starred ? "スターを外す" : "スターを付ける",
                                        serverKey: work.starred ? "starOn" : "starOff"))
            LibraryAnnotationMarkButton(model: model, work: work, mark: .revision)
            LibraryAnnotationMarkButton(model: model, work: work, mark: .share)
        }
        .buttonStyle(.borderless)
        .disabled(library.mutating || model.isBusy)
    }
}

@MainActor
struct LibraryAnnotationMarkButton: View {
    @Bindable var model: AppModel
    let work: SavedWork
    let mark: LibraryAnnotationMark
    private var library: LibraryModel { model.library }
    private var loading: Bool { library.isAnnotationLoading(for: work.id) }
    private var marked: Bool? {
        guard let annotation = library.loadedAnnotation(for: work.id) else { return nil }
        switch mark {
        case .revision: return annotation.forRevision
        case .share: return annotation.forShare
        }
    }
    private var title: String {
        switch mark {
        case .revision: return "推敲の印"
        case .share: return "書き出し用の印"
        }
    }
    private var symbol: String {
        guard let marked else { return "questionmark.circle" }
        switch mark {
        case .revision: return marked ? "pencil.circle.fill" : "pencil.circle"
        case .share: return marked ? "square.and.arrow.up.fill" : "square.and.arrow.up"
        }
    }
    private var accessibilityState: String {
        if loading { return "印を読み込み中" }
        guard let marked else { return "印を取得できません" }
        return marked ? "オン" : "オフ"
    }

    private var markTooltip: String {
        guard !loading, let marked else { return model.display.tooltip(accessibilityState) }
        switch mark {
        case .revision:
            return model.display.tooltip(marked ? "推敲マークを外す" : "推敲マークを付ける",
                                         serverKey: marked ? "forRevisionOn" : "forRevisionOff")
        case .share:
            return model.display.tooltip(marked ? "書き出しの印を外す" : "書き出しの印を付ける",
                                         serverKey: marked ? "shareTargetOn" : "shareTargetOff")
        }
    }

    var body: some View {
        Button {
            Task {
                switch mark {
                case .revision: await library.toggleRevision(work)
                case .share: await library.toggleShare(work)
                }
            }
        } label: {
            if loading {
                ProgressView().controlSize(.small).frame(width: 16, height: 16)
            } else {
                Image(systemName: symbol)
                    .foregroundStyle(marked == true ? Color.accentColor : Color.secondary)
            }
        }
        .accessibilityLabel(model.display.localized(title))
        .accessibilityValue(model.display.localized(accessibilityState))
        .disabled(loading || marked == nil || library.mutating || model.isBusy)
        .inkuTooltip(markTooltip)
    }
}

struct LibraryCardSurface: ViewModifier {
    var current = false
    var focused = false
    var tombstone = false
    var cornerRadius: CGFloat = 12

    func body(content: Content) -> some View {
        content
            .background(.background, in: RoundedRectangle(cornerRadius: cornerRadius))
            .overlay {
                RoundedRectangle(cornerRadius: cornerRadius)
                    .stroke(current || focused ? Color.accentColor : Color.secondary.opacity(0.18),
                            style: StrokeStyle(lineWidth: focused ? 2 : 1, dash: tombstone ? [5, 4] : []))
            }
    }
}

/// Web `historyGridPageSize` (lib/historyManagerSizing.ts): the complete rows that fit, times the columns.
public enum LibraryGridPaging {
    public static let minCardWidth: Double = 142
    public static let gap: Double = 8
    /// Web `HISTORY_MANAGER_DEFAULT_PAGE_SIZE` and the ceiling of `setPageSize`.
    public static let initialPageSize = 24
    public static let maximumPageSize = 100

    public static func pageSize(width: Double, height: Double, gap: Double = gap, minCardWidth: Double = minCardWidth,
                                cardHeights: [Double]) -> Int {
        guard width > 0, height > 0 else { return 1 }
        let columns = max(1, Int(((width + gap) / (minCardWidth + gap)).rounded(.down)))
        let measured = cardHeights.reduce(0) { $1.isFinite && $1 > 0 ? max($0, $1) : $0 }
        let cardWidth = max(minCardWidth, (width - gap * Double(columns - 1)) / Double(columns))
        let cardHeight = measured > 0 ? measured : max(1, cardWidth - 12) * 58 / 82 + 75
        let rows = max(1, Int(((height + gap) / (cardHeight + gap)).rounded(.down)))
        return columns * rows
    }
}

/// Web palette roles used by the library overlay and the history strip.
enum LibraryChrome {
    static let border = Color.secondary.opacity(0.28)
    static var panel2: Color {
        #if os(macOS)
        Color(nsColor: .windowBackgroundColor)
        #else
        Color(uiColor: .secondarySystemBackground)
        #endif
    }
}

/// Web `.ghost-btn` at `--btn-sm-*`: 12px, padding 4×10, radius 4, 1px border; `active` is `.ghost-active`.
struct LibraryGhostButtonStyle: ButtonStyle {
    var active = false
    var minWidth: CGFloat? = nil
    var minHeight: CGFloat? = nil
    /// Web `.danger-btn`.
    var danger = false
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .inkuFont(12)
            .lineLimit(1).fixedSize()
            .padding(.vertical, 4).padding(.horizontal, 10)
            .frame(minWidth: minWidth, minHeight: minHeight)
            .foregroundStyle(active || danger ? Color.white : Color.primary)
            .background(danger ? Color.red : active ? Color.accentColor : Color.primary.opacity(configuration.isPressed ? 0.12 : 0.04),
                        in: RoundedRectangle(cornerRadius: 4))
            .overlay(RoundedRectangle(cornerRadius: 4).stroke(danger ? Color.red : active ? Color.accentColor : LibraryChrome.border))
            .opacity(isEnabled ? 1 : 0.45)
            .contentShape(RoundedRectangle(cornerRadius: 4))
    }
}

/// Web `.settings-tabs`: connected small buttons, 12px, padding 4×10, one frame; the chosen one takes the
/// panel background and weight 500. No icons.
struct LibrarySegmentTabs<Value: Hashable>: View {
    let options: [(value: Value, title: String, tooltip: String)]
    @Binding var selection: Value

    var body: some View {
        HStack(spacing: 0) {
            ForEach(Array(options.enumerated()), id: \.offset) { index, option in
                if index > 0 { Rectangle().fill(LibraryChrome.border).frame(width: 1) }
                Button { selection = option.value } label: {
                    Text(option.title)
                        .inkuFont(12, weight: selection == option.value ? .medium : .regular)
                        .foregroundStyle(selection == option.value ? Color.primary : Color.secondary)
                        .lineLimit(1)
                        .padding(.vertical, 4).padding(.horizontal, 10)
                        .background(selection == option.value ? AnyShapeStyle(.background) : AnyShapeStyle(Color.clear))
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .inkuTooltip(option.tooltip, placement: .bottom)
                .accessibilityAddTraits(selection == option.value ? .isSelected : [])
            }
        }
        .fixedSize()
        .background(LibraryChrome.panel2)
        .clipShape(RoundedRectangle(cornerRadius: 4))
        .overlay(RoundedRectangle(cornerRadius: 4).stroke(LibraryChrome.border))
    }
}

/// A selection box drawn like Web `.selection-checkbox` (20×20, radius 3, ✓ in the accent).
struct LibrarySelectionBox: View {
    let selected: Bool

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 3).fill(.background.opacity(0.92))
            RoundedRectangle(cornerRadius: 3).stroke(selected ? Color.accentColor : Color.primary.opacity(0.32))
            if selected { Text("✓").font(.system(size: 12, weight: .bold)).foregroundStyle(Color.accentColor) }
        }
        .frame(width: 20, height: 20)
        .shadow(color: .black.opacity(0.16), radius: 1.5, y: 1)
    }
}

extension DisplaySettings {
    /// Web copy by its i18n key, from the bundled Server reference; the native string when the key is absent.
    func webCopy(_ key: String, fallback: String) -> String {
        ServerTips.text(key, language: preferences.language) ?? localized(fallback)
    }
}
