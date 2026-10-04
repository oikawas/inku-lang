import Foundation
import Observation

/// An editor's draft does not become authoring input until the author confirms it.
@MainActor @Observable
public final class DdlEditingSession: Identifiable {
    public nonisolated let id = UUID()
    public var draft: String
    private let initialText: String
    private let sourceWorkID: String?
    private let sourceRevision: String

    public init(model: AppModel) {
        initialText = model.ddlText
        draft = initialText
        sourceWorkID = model.displayedWork?.id
        sourceRevision = model.authoringRevision
    }

    public func canSubmit(to model: AppModel) -> Bool {
        model.canEditCurrentDDL && model.displayedWork?.id == sourceWorkID
            && model.authoringRevision == sourceRevision
            && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && draft != model.visibleDDL
    }

    public func insert(_ word: String) {
        guard !word.isEmpty else { return }
        if !draft.isEmpty, draft.last?.isWhitespace == false { draft += "\n" }
        draft += word
    }

    public func cancel() { draft = initialText }

    public func commit(to model: AppModel) async -> Bool {
        guard canSubmit(to: model) else { return false }
        let previousInput = model.ddlText
        model.ddlText = draft
        guard model.canCommitDDL else { model.ddlText = previousInput; return false }
        await model.commitDDL()
        let committed = model.errorText == nil && model.visibleDDL == draft
        if !committed, model.displayedWork?.id == sourceWorkID, model.authoringRevision == sourceRevision {
            model.ddlText = previousInput
        }
        return committed
    }
}
