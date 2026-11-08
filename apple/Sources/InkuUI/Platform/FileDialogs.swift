import SwiftUI
import UniformTypeIdentifiers

/// What one file dialog chooses: the kinds it accepts and the sentence shown at its top (the old panel's message, or
/// its title where it had no message; a panel with neither shows none).
struct InkuFileRequest: Equatable {
    let types: [UTType]
    var message: String? = nil

    static func folder(message: String? = nil) -> InkuFileRequest { InkuFileRequest(types: [.folder], message: message) }
}

/// The viewer's PNG or GLB, handed to `fileExporter`, which writes it. Like the old save panel it names no file
/// type; the suggested name keeps the extension.
struct InkuExportedFile: Transferable {
    let data: Data

    static var transferRepresentation: some TransferRepresentation {
        DataRepresentation(exportedContentType: .data) { $0.data }
    }
}

/// The file dialogs of one window or sheet (PLAN §5). `inkuFileDialogs` at its root shows them, so no view stacks
/// several `fileImporter`s; the views below ask through `choose` and `save` and wait for the answer.
@MainActor
@Observable
final class InkuFileDialogs {
    fileprivate var importing = false
    fileprivate var exporting = false
    fileprivate private(set) var request: InkuFileRequest?
    fileprivate private(set) var exported: InkuExportedFile?
    fileprivate private(set) var exportedName = ""
    @ObservationIgnored private var chosen: CheckedContinuation<URL?, Never>?
    @ObservationIgnored private var saved: CheckedContinuation<Bool, Never>?

    /// The chosen file or folder; nil when it is cancelled, or when this window already shows a dialog.
    func choose(_ request: InkuFileRequest) async -> URL? {
        guard chosen == nil, saved == nil else { return nil }
        return await withCheckedContinuation { continuation in
            chosen = continuation
            self.request = request
            importing = true
        }
    }

    /// Writes `data` where the author chooses; false when it is cancelled or the write fails.
    func save(_ data: Data, suggestedName: String) async -> Bool {
        guard chosen == nil, saved == nil else { return false }
        return await withCheckedContinuation { continuation in
            saved = continuation
            exported = InkuExportedFile(data: data)
            exportedName = suggestedName
            exporting = true
        }
    }

    #if os(iOS)
    fileprivate var moving = false
    fileprivate private(set) var movedFiles: [URL] = []
    @ObservationIgnored private var moved: CheckedContinuation<[URL]?, Never>?

    /// Moves files the app made in its temporary folder to where the author chooses (iOS plan §3 #6); the new
    /// places, or nil when it is cancelled, fails, or this window already shows a dialog.
    func move(_ urls: [URL]) async -> [URL]? {
        guard chosen == nil, saved == nil, moved == nil, !urls.isEmpty else { return nil }
        return await withCheckedContinuation { continuation in
            moved = continuation
            movedFiles = urls
            moving = true
        }
    }

    fileprivate func finishMoving(_ urls: [URL]?) {
        guard let moved else { return }
        self.moved = nil
        movedFiles = []
        moved.resume(returning: urls)
    }
    #endif

    /// Closes the open dialog as cancelled (the DDL import's cancel, the view leaving).
    func cancel() {
        importing = false
        exporting = false
        finishChoosing(nil)
        finishSaving(false)
        #if os(iOS)
        moving = false
        finishMoving(nil)
        #endif
    }

    fileprivate func finishChoosing(_ url: URL?) {
        guard let chosen else { return }
        self.chosen = nil
        request = nil
        chosen.resume(returning: url)
    }

    fileprivate func finishSaving(_ done: Bool) {
        guard let saved else { return }
        self.saved = nil
        exported = nil
        saved.resume(returning: done)
    }
}

private struct InkuFileDialogsModifier: ViewModifier {
    let given: InkuFileDialogs?
    @State private var own = InkuFileDialogs()

    func body(content: Content) -> some View {
        let dialogs = given ?? own
        #if os(iOS)
        @Bindable var bound = dialogs
        dialogContent(content, dialogs: dialogs)
            .fileMover(isPresented: $bound.moving, files: dialogs.movedFiles) { result in
                if case .failure = result { InkuFeedback.beep() }
                dialogs.finishMoving(try? result.get())
            } onCancellation: {
                // The mover reports a cancel itself, so closing does not race its result.
                dialogs.finishMoving(nil)
            }
        #else
        dialogContent(content, dialogs: dialogs)
        #endif
    }

    private func dialogContent(_ content: Content, dialogs: InkuFileDialogs) -> some View {
        @Bindable var bound = dialogs
        return content
            .environment(dialogs)
            .fileImporter(isPresented: $bound.importing, allowedContentTypes: dialogs.request?.types ?? [.item]) { result in
                dialogs.finishChoosing(try? result.get())
            }
            .fileDialogMessage(dialogs.request?.message.map { Text($0) })
            // A cancelled dialog reports nothing; it only closes.
            .onChange(of: dialogs.importing) { _, shown in if !shown { dialogs.finishChoosing(nil) } }
            .fileExporter(isPresented: $bound.exporting, item: dialogs.exported,
                          contentTypes: [.data],
                          defaultFilename: dialogs.exportedName) { result in
                if case .failure = result { InkuFeedback.beep() }
                dialogs.finishSaving((try? result.get()) != nil)
            } onCancellation: {
                dialogs.finishSaving(false)
            }
            .onChange(of: dialogs.exporting) { _, shown in if !shown { dialogs.finishSaving(false) } }
    }
}

extension View {
    /// The window's or sheet's file dialogs: `dialogs` when the root also asks itself, else its own.
    func inkuFileDialogs(_ dialogs: InkuFileDialogs? = nil) -> some View {
        modifier(InkuFileDialogsModifier(given: dialogs))
    }
}
