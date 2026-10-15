import InkuHost
import InkuPersistence
import SwiftUI

/// The compact saved-facts table in Web LineagePanel, with the author's refine entrance retained.
@MainActor
struct LineageDetailsView: View {
    @Bindable var model: AppModel
    let item: LineageItem
    let operation: String
    let naming: ModelNaming
    @Bindable var note: LibraryNoteEditorModel
    let writingLocked: Bool
    let onAction: (SavedWork, String) -> Void
    let onClose: () -> Void
    @State private var information: SavedGenerationInformation?
    @State private var error: String?

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(model.display.localized("作品の詳細")).inkuFont(16, weight: .semibold)
                    Text(operation).inkuFont(12).foregroundStyle(.secondary)
                }
                Spacer()
                Button(model.display.localized("閉じる"), systemImage: "xmark", action: onClose)
                    .labelStyle(.iconOnly).keyboardShortcut(.cancelAction)
            }.padding(20)
            Divider()
            ScrollView {
                if let work = item.work {
                    VStack(alignment: .leading, spacing: 12) {
                        Text(model.display.localized("記述")).foregroundStyle(.secondary)
                        ScrollView { Text(work.effectiveSourceText).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }
                            .frame(maxHeight: 135)
                        Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 8) {
                            hashRow("dh", item.node.descriptionHash ?? work.descriptionHash)
                            hashRow("rh", item.node.renderHash ?? work.renderHash)
                            row("Render engine version", work.renderEngineVersion)
                            row(model.display.webCopy("provenanceLabelTransformLayer", "DDL engine version"), information?.presentation?.provenance?.ddlEngineVersion)
                            row("Build", information?.presentation?.provenance?.build)
                            row("Stage 1", work.stage1Model.map(naming.displayName))
                            row("Stage 2", work.stage2Model.map(naming.displayName))
                            row("seed", [work.renderSeed, work.compositionSeed, work.interpretationSeed].map { $0 ?? "—" }.joined(separator: " / "))
                            row(model.display.localized("派生"), operation)
                        }.frame(maxWidth: .infinity, alignment: .leading)
                        Divider()
                        Text(model.display.localized("作品へのコメント")).foregroundStyle(.secondary)
                        TextEditor(text: Binding(get: { note.text }, set: { note.text = LibraryNoteEditorModel.limited($0) }))
                            .frame(height: 70).border(InkuColor.border)
                            .disabled(note.state.annotation == nil || note.saving || writingLocked || work.trashed)
                            .accessibilityLabel(model.display.localized("作品へのコメント"))
                        HStack {
                            Menu(model.display.localized("推敲する"), systemImage: "slider.horizontal.3") {
                                SavedWorkRefinementActions(model: model, work: work, onAction: onAction, writingLocked: writingLocked)
                            }.disabled(writingLocked || work.trashed)
                            Spacer()
                            Button(model.display.localized(note.saving ? "保存中…" : "保存")) { Task { await save(work) } }
                                .disabled(!note.canSave || note.text.trimmingCharacters(in: .whitespacesAndNewlines) == note.savedText.trimmingCharacters(in: .whitespacesAndNewlines) || writingLocked || work.trashed)
                        }
                        if let error = note.errorText ?? error { Text(error).foregroundStyle(.red).textSelection(.enabled) }
                    }.inkuFont(13).padding(20)
                } else {
                    Text(model.display.localized("元の節点と接続を保持しています。作品本文は削除されています。"))
                        .foregroundStyle(.secondary).padding(20)
                }
            }
        }
        .frame(minWidth: 480, idealWidth: 640, minHeight: 420, idealHeight: 620)
        .task(id: item.work?.id) {
            guard let work = item.work else { return }
            await model.loadWorkActionState(work)
            do {
                let saved = try await model.savedGenerationInformation(work: work)
                guard !Task.isCancelled else { return }
                information = saved; note.receive(workID: work.id, state: .available(saved.annotation))
            } catch {
                self.error = error.localizedDescription
                note.receive(workID: work.id, state: .unavailable)
            }
        }
    }

    private func row(_ label: String, _ value: String?) -> some View {
        GridRow {
            Text(label).foregroundStyle(.secondary).frame(minWidth: 135, alignment: .leading)
            Text(value ?? "—").textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func hashRow(_ prefix: String, _ hash: String?) -> some View {
        GridRow {
            Text(hash.flatMap { value in value.firstIndex(of: ":").map { String(value[..<$0]) } } ?? prefix)
                .foregroundStyle(.secondary).frame(minWidth: 135, alignment: .leading)
            HStack(spacing: 10) {
                Text(hash.flatMap { $0.isEmpty ? nil : "…" + SavedWorkFacts.hashDigest($0).suffix(4) } ?? "—").monospaced()
                if let hash, !hash.isEmpty {
                    Button(model.display.localized(model.library.copiedHash == hash ? "コピーしました" : "コピー")) { model.library.copyHash(hash) }
                        .inkuTooltip(model.display.tooltip("描画ハッシュ全体をコピー", serverKey: "historyHashCopyTitle"))
                }
            }
        }
    }

    private func save(_ work: SavedWork) async {
        _ = await note.save { id, text in
            await model.library.saveNote(id: id, note: text.trimmingCharacters(in: .whitespacesAndNewlines))
            if let error = model.library.errorText { throw HostError(error) }
            return try await model.auxiliaryDatabase().libraryAnnotation(id: id)
        }
    }
}
