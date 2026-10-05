import Foundation
import InkuPersistence
import Observation

/// An editor's draft does not become authoring input until the author confirms it.
@MainActor @Observable
public final class DdlEditingSession: Identifiable {
    public nonisolated let id = UUID()
    public var draft: String
    private let initialText: String
    private let sourceWorkID: String?
    private let sourceRevision: String
    private let sourceWork: SavedWork?
    public var work: SavedWork? { sourceWork }

    public init(model: AppModel) {
        initialText = model.ddlText
        draft = initialText
        sourceWorkID = model.displayedWork?.id
        sourceRevision = model.authoringRevision
        sourceWork = nil
    }

    public init(work: SavedWork) {
        initialText = work.ddl ?? ""
        draft = initialText
        sourceWorkID = work.id
        sourceRevision = "0"
        sourceWork = work
    }

    public func canSubmit(to model: AppModel) -> Bool {
        if let sourceWork {
            return !model.isBusy && !sourceWork.trashed && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
        return model.canEditCurrentDDL && model.displayedWork?.id == sourceWorkID
            && model.authoringRevision == sourceRevision
            && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    public func insert(_ word: String) {
        guard !word.isEmpty else { return }
        if !draft.isEmpty, draft.last?.isWhitespace == false { draft += "\n" }
        draft += word
    }

    public func cancel() { draft = initialText }

    public func commit(to model: AppModel, wildOverride: Bool? = nil) async -> Bool {
        guard canSubmit(to: model) else { return false }
        if let sourceWork { return await model.drawEditedDDL(work: sourceWork, source: draft, wildOverride: wildOverride) }
        let previousInput = model.ddlText
        model.ddlText = draft
        guard model.canCommitDDL else { model.ddlText = previousInput; return false }
        await model.commitDDL(wildOverride: wildOverride)
        let committed = model.errorText == nil && model.visibleDDL == draft
        if !committed, model.displayedWork?.id == sourceWorkID, model.authoringRevision == sourceRevision {
            model.ddlText = previousInput
        }
        return committed
    }
}
