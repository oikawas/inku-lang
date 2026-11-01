import Foundation
import InkuHost
import InkuPersistence
import InkuUI

/// The creation panel must expose an unsaved proposal, and editor dismissal must reach that panel.
@MainActor func runCompletionApprovalChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-completion-approval-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let url = folder.appendingPathComponent("works.sqlite")
    let transport = ApprovalFixtureProvider()
    let app = AppModel(databaseURL: url, transport: transport)
    await app.initialize()
    let provider = ProviderSettings(id: "check", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false,
                                    models: [ProviderModelSettings(id: "m")])
    try await app.updateHostSettings(HostSettings(providers: [provider], models: ModelSelection(stage1Model: "check:m", stage2Model: "check:m")))
    let source = "scatter ten small orange circles randomly at the bottom right."
    let previous = app.patchReview
    let savedImmediately = await app.drawNewDDL(source)
    guard !savedImmediately, let review = app.patchReview, app.selectedWork == nil,
          review.committedDDL.contains("bottom right"), review.proposedDDL.contains("horizontal 2/3 to 1"),
          app.shouldReturnToCreation(afterSaving: savedImmediately, previousReview: previous, previousIssues: [], previousNoticeExecutionID: nil),
          !app.shouldReturnToCreation(afterSaving: false, previousReview: review, previousIssues: app.completionIssues, previousNoticeExecutionID: app.completionNoticeExecutionID) else {
        throw CheckFailure.message("Unsaved proposal is not exposed to the creation panel: \(app.authoringPhase) \(app.errorText ?? app.status)")
    }
    await app.approvePatch()
    guard app.patchReview == nil, let parent = app.selectedWork, let committed = parent.ddl,
          committed.contains("horizontal 2/3 to 1"), !parent.svg.isEmpty else {
        throw CheckFailure.message("Approval did not draw and save the candidate: \(app.errorText ?? app.status)")
    }
    let database = try InkuDatabase(url: url)
    guard try await database.work(id: parent.id) == parent else { throw CheckFailure.message("Approved work was not saved") }
    let session = DdlEditingSession(work: parent, draft: source)
    let before = app.patchReview
    let edited = await session.commit(to: app)
    guard !edited, let declinedReview = app.patchReview,
          declinedReview.proposedDDL.contains("horizontal 2/3 to 1"),
          app.shouldReturnToCreation(afterSaving: edited, previousReview: before, previousIssues: [], previousNoticeExecutionID: nil) else {
        throw CheckFailure.message("Saved-work editor did not expose its completion proposal: \(app.errorText ?? app.status)")
    }
    await app.declinePatch()
    guard app.patchReview == nil, app.visibleDDL == declinedReview.committedDDL,
          try await database.work(id: parent.id)?.ddl == committed,
          try await database.list().count == 1, await transport.calls == 2 else {
        throw CheckFailure.message("Declining changed the saved DDL or added a work")
    }
    // New DDL remains independent even if another saved work is currently selected.
    _ = await app.drawNewDDL(source)
    guard app.patchReview != nil else { throw CheckFailure.message("Second new-work proposal is missing") }
    await app.approvePatch()
    guard let independent = app.selectedWork, independent.id != parent.id, let nodeID = independent.lineageNodeID,
          try await database.edge(childNodeID: nodeID) == nil else {
        throw CheckFailure.message("Approving a new DDL proposal attached it to the previously selected work")
    }
    // An editor opened for another saved work must keep that work as the parent after approval.
    let otherSession = DdlEditingSession(work: parent, draft: source)
    _ = await otherSession.commit(to: app)
    guard app.patchReview != nil else { throw CheckFailure.message("Other saved-work proposal is missing") }
    await app.approvePatch()
    guard let child = app.selectedWork, let childNode = child.lineageNodeID,
          let edge = try await database.edge(childNodeID: childNode), edge.parentNodeID == parent.lineageNodeID else {
        throw CheckFailure.message("Approved editor proposal did not keep its original parent")
    }
    let unresolvedProvider = ApprovalFixtureProvider(unresolved: true)
    let unresolved = AppModel(databaseURL: folder.appendingPathComponent("unresolved/works.sqlite"), transport: unresolvedProvider)
    await unresolved.initialize()
    try await unresolved.updateHostSettings(HostSettings(providers: [provider], models: ModelSelection(stage1Model: "check:m", stage2Model: "check:m")))
    _ = await unresolved.drawNewDDL(source)
    guard unresolved.selectedWork == nil, !unresolved.completionIssues.isEmpty,
          unresolved.completionIssues.contains(where: { $0.reason == "unsupported" && !$0.source.isEmpty }),
          unresolved.shouldReturnToCreation(afterSaving: false, previousReview: nil, previousIssues: [], previousNoticeExecutionID: nil) else {
        throw CheckFailure.message("Unresolved completion was not exposed to the creation panel")
    }
    let oldIssues = unresolved.completionIssues, oldExecution = unresolved.completionNoticeExecutionID
    _ = await unresolved.drawNewDDL(source)
    guard unresolved.shouldReturnToCreation(afterSaving: false, previousReview: nil, previousIssues: oldIssues, previousNoticeExecutionID: oldExecution) else {
        throw CheckFailure.message("A repeated unresolved result remained hidden behind the editor")
    }
    print("Completion approval passed: unsaved creation panel state and editor return; approve draws and saves; saved-work editor decline retains the original DDL; unresolved issue exposed; fixture provider only.")
}

private actor ApprovalFixtureProvider: ProviderTransport {
    private(set) var calls = 0
    let unresolved: Bool
    init(unresolved: Bool = false) { self.unresolved = unresolved }
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        let value = try ExactJSON(data: action)
        guard value["tag"].string == "complete_visible_ddl_holes",
              let message = value["payload"]["prompt"]["message"].string.flatMap({ try? ExactJSON(data: Data($0.utf8)) }),
              let hole = message["selected_holes"].array?.first,
              let id = hole["id"].string, let source = hole["source"].string else { throw HostError("unexpected_completion_fixture") }
        let replacement = source.replacingOccurrences(of: " randomly", with: "")
            .replacingOccurrences(of: "at the bottom right", with: "at the bottom right (horizontal 2/3 to 1, vertical 2/3 to 1)")
        let item: ExactJSON = unresolved
            ? .object(["id": .string(id), "status": .string("unresolved"), "reason": .string("unsupported")])
            : .object(["id": .string(id), "status": .string("proposed"), "replacement": .string(replacement)])
        let response: ExactJSON = .object(["results": .array([item])])
        return ExactJSON.object(["tag": .string("visible_ddl_hole_patch_generated"), "identity": value["identity"],
            "response": .string(response.text), "elapsed_ms": .string("1")]).data
    }
}
