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
            .help(model.display.preferences.showTooltips ? model.display.localized("お気に入り") : "")
            Button { Task { await library.toggleRevision(work) } } label: {
                Image(systemName: library.annotation(for: work.id).forRevision ? "pencil.circle.fill" : "pencil.circle")
                    .foregroundStyle(library.annotation(for: work.id).forRevision ? Color.accentColor : Color.secondary)
            }
            .accessibilityLabel(model.display.localized("推敲の印"))
            .accessibilityValue(model.display.localized(library.annotation(for: work.id).forRevision ? "選択済み" : "未選択"))
            .help(model.display.preferences.showTooltips ? model.display.localized("推敲の印") : "")
            Button { Task { await library.toggleShare(work) } } label: {
                Image(systemName: library.annotation(for: work.id).forShare ? "square.and.arrow.up.fill" : "square.and.arrow.up")
                    .foregroundStyle(library.annotation(for: work.id).forShare ? Color.accentColor : Color.secondary)
            }
            .accessibilityLabel(model.display.localized("書き出し用の印"))
            .accessibilityValue(model.display.localized(library.annotation(for: work.id).forShare ? "選択済み" : "未選択"))
            .help(model.display.preferences.showTooltips ? model.display.localized("書き出し用の印") : "")
        }
        .buttonStyle(.borderless)
        .disabled(library.mutating || model.isBusy)
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
