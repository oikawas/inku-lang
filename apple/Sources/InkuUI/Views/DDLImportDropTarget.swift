import SwiftUI
#if os(macOS)

@MainActor
struct DDLImportDropTarget: ViewModifier {
    @Bindable var model: AppModel
    let enabled: Bool
    var onImported: @MainActor () -> Void
    @Environment(DDLImportController.self) private var importer
    @State private var isTargeted = false
    @State private var isMounted = false
    @State private var contextEnabled = false

    private var acceptsDrop: Bool { isMounted && contextEnabled && !model.isBusy && !importer.isReading }

    func body(content: Content) -> some View {
        content
            .dropDestination(for: URL.self) { urls, _ in
                // Transferable URL loading may finish after the scene changes. Consult
                // the current mounted/authorized state before starting an owned read.
                guard acceptsDrop else { return false }
                guard urls.count == 1, let url = urls.first else {
                    importer.rejectDrop(app: model)
                    return false
                }
                return importer.read(url: url, app: model, enabled: contextEnabled, onImported: onImported)
            } isTargeted: { targeted in isTargeted = targeted }
            .overlay {
                if isTargeted && acceptsDrop { dropHighlight.allowsHitTesting(false) }
            }
            .overlay(alignment: .topTrailing) {
                if isMounted && importer.isReading { readingStatus.padding(16) }
            }
            .onAppear { isMounted = true; contextEnabled = enabled }
            .onChange(of: enabled) { _, value in
                contextEnabled = value
                if !value { isTargeted = false; importer.cancel() }
            }
            .onChange(of: importer.isReading) { _, reading in if reading { isTargeted = false } }
            .onChange(of: model.selectedWorkID) { _, workID in if workID != nil { importer.clearMessage() } }
            .onDisappear { isMounted = false; contextEnabled = false; importer.cancel() }
    }

    private var dropHighlight: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 18)
                .fill(Color.accentColor.opacity(0.08))
                .overlay {
                    RoundedRectangle(cornerRadius: 18)
                        .stroke(Color.accentColor, style: StrokeStyle(lineWidth: 2, dash: [8, 5]))
                }
            VStack(spacing: 12) {
                Image(systemName: "doc.badge.arrow.up").font(.system(size: 36)).foregroundStyle(Color.accentColor)
                Text(model.display.localized("DDLファイルをここにドロップ")).font(.title2.weight(.semibold))
                Text(model.display.localized("1ファイル、4MiBまで。プラグイン定義は64件まで。"))
                    .font(.callout).foregroundStyle(.secondary)
            }
            .padding(24).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
        }.padding(12)
    }

    private var readingStatus: some View {
        HStack(spacing: 10) {
            ProgressView().controlSize(.small)
            Text(model.display.localized(importer.isCancelling ? "読み込みを中止しています…" : "DDLファイルを読み込み中"))
                .font(.callout)
            Button(model.display.localized("中止")) { importer.cancel() }
                .disabled(importer.isCancelling).keyboardShortcut(.escape, modifiers: [])
        }
        .padding(12).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10))
    }
}

extension View {
    @MainActor
    func ddlImportDropTarget(model: AppModel, enabled: Bool, onImported: @escaping @MainActor () -> Void = {}) -> some View {
        modifier(DDLImportDropTarget(model: model, enabled: enabled, onImported: onImported))
    }
}
#endif
