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

    var body: some View {
        Text(LibraryWorkPresentation.title(work, untitled: untitled))
            .font(LibraryWorkPresentation.usesDDLTitle(work) ? .system(.callout, design: .monospaced) : .body)
            .foregroundStyle(.primary)
            .lineLimit(lineLimit)
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
                .help(display.tooltipValue(display.localized(fact.label) + ": " + (fact.reference ?? display.localized("未記録"))))
            }
        }.font(compact ? .caption2 : .caption)
    }
}

@MainActor
struct LibraryWorkMarks: View {
    @Bindable var model: AppModel
    let work: SavedWork
    private var library: LibraryModel { model.library }

    var body: some View {
        HStack(spacing: 12) {
            Button { Task { await library.toggleStar(work) } } label: {
                Image(systemName: work.starred ? "star.fill" : "star")
                    .foregroundStyle(work.starred ? Color.accentColor : Color.secondary)
            }
            .accessibilityLabel(model.display.localized(work.starred ? "お気に入りを解除" : "お気に入り"))
            .help(model.display.tooltip(work.starred ? "スターを外す" : "スターを付ける",
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
        .help(markTooltip)
        .disabled(loading || marked == nil || library.mutating || model.isBusy)
    }
}

struct LibraryCardSurface: ViewModifier {
    var current = false
    var focused = false
    var tombstone = false

    func body(content: Content) -> some View {
        content
            .background(.background, in: RoundedRectangle(cornerRadius: 12))
            .overlay {
                RoundedRectangle(cornerRadius: 12)
                    .stroke(current || focused ? Color.accentColor : Color.secondary.opacity(0.18),
                            style: StrokeStyle(lineWidth: focused ? 2 : 1, dash: tombstone ? [5, 4] : []))
            }
    }
}
