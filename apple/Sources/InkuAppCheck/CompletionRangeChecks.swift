import Foundation
import InkuHost
import InkuPersistence
import InkuUI

/// A3 (CHANGELOG 2026-10-11): an approved completion's ranges stay with the saved work, read as three states, and
/// go with a direct DDL drawn from that work. Real core; the provider is a fixture answering the completion.
@MainActor func runCompletionRangeChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-completion-ranges-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let databaseURL = folder.appendingPathComponent("works.sqlite")
    let transport = CompletionRangeProvider()
    let provider = ProviderSettings(id: "check", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false,
                                    models: [ProviderModelSettings(id: "m")])
    let app = AppModel(databaseURL: databaseURL, transport: transport)
    await app.initialize()
    try await app.updateHostSettings(HostSettings(providers: [provider], models: ModelSelection(stage1Model: "check:m", stage2Model: "check:m")))

    // core focused_flow A3 (T5): the completion writes a range after the place words; the author approves it.
    _ = await app.drawNewDDL("scatter ten small orange circles randomly at the bottom right.")
    guard !app.patchProposalJSON.isEmpty else {
        throw CheckFailure.message("The completion proposal did not wait for approval: \(app.authoringPhase) \(app.errorText ?? app.status)")
    }
    await app.approvePatch()
    guard let saved = app.displayedWork, let ddl = saved.ddl, ddl.contains("(horizontal 2/3 to 1, vertical 2/3 to 1)") else {
        throw CheckFailure.message("Approving the completion did not save its range: \(app.errorText ?? app.status)")
    }
    // Failure: the saved work lost the record, so a later draw from it forgets which ranges the completion wrote.
    let context = try await app.savedConfiguration(workID: saved.id)
    guard let record = context.completionRanges.flatMap({ try? ExactJSON(data: $0) }),
          record["schema"].string == "inku.completion-ranges.v1", record["ranges"].array?.count == 1 else {
        throw CheckFailure.message("The saved work kept no completion range record")
    }
    // Failure: the states were misread or not asked from the work's own record.
    let numbers = ddl.replacingOccurrences(of: "horizontal 2/3 to 1", with: "horizontal 1/2 to 1")
    let words = ddl.replacingOccurrences(of: "the bottom right", with: "the top left")
    func states(_ model: AppModel, _ source: String) -> [CompletionRangeState.State] { model.completionRangeStates(source: source).map(\.state) }
    guard states(app, ddl) == [.completed], states(app, numbers) == [.numbersChanged], states(app, words) == [.wordsChanged] else {
        throw CheckFailure.message("Live states: \(states(app, ddl)) \(states(app, numbers)) \(states(app, words))")
    }

    // Failure: selecting the saved work afresh (no live execution) dropped the record, so a renamed range was drawn
    // with its old numbers instead of being completed again.
    let reopened = AppModel(databaseURL: databaseURL, transport: transport)
    await reopened.initialize()
    try await reopened.updateHostSettings(HostSettings(providers: [provider], models: ModelSelection(stage1Model: "check:m", stage2Model: "check:m")))
    guard let again = reopened.works.first(where: { $0.id == saved.id }) else { throw CheckFailure.message("Saved work missing after reopening") }
    await reopened.selectWork(again)
    guard states(reopened, ddl) == [.completed], states(reopened, words) == [.wordsChanged] else {
        throw CheckFailure.message("Saved states: \(states(reopened, ddl)) \(states(reopened, words))")
    }
    let before = await transport.completionKinds.count
    reopened.inputMode = "ddl"; reopened.ddlText = words
    await reopened.commitDDL()
    let kinds = await transport.completionKinds
    guard kinds.count == before + 1, kinds.last?.contains("range_words_changed") == true else {
        throw CheckFailure.message("Drawing renamed words from the saved work asked \(kinds.dropFirst(before)) instead of completing the range again")
    }
    print("Completion ranges passed: an approved completion's range is saved with the work (1 range); completed, numbers-changed and words-changed read from the live and the reopened work; a renamed range drawn from the reopened work is completed again (range_words_changed). Real core, fixture provider.")
}

private actor CompletionRangeProvider: ProviderTransport {
    private(set) var completionKinds: [[String]] = []
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let value = try ExactJSON(data: action)
        guard value["tag"].string == "complete_visible_ddl_holes",
              let message = value["payload"]["prompt"]["message"].string.flatMap({ try? ExactJSON(data: Data($0.utf8)) }),
              let hole = message["selected_holes"].array?.first else { throw HostError("unexpected_completion_range_effect") }
        completionKinds.append((message["selected_holes"].array ?? []).compactMap { $0["kind"].string })
        guard completionKinds.count == 1, let id = hole["id"].string, let source = hole["source"].string else {
            throw HostError("completion_range_fixture_done")
        }
        let replacement = source.replacingOccurrences(of: " randomly", with: "")
            .replacingOccurrences(of: "at the bottom right", with: "at the bottom right (horizontal 2/3 to 1, vertical 2/3 to 1)")
        let answer: ExactJSON = .object(["results": .array([.object(["id": .string(id), "status": .string("proposed"), "replacement": .string(replacement)])])])
        return ExactJSON.object(["tag": .string("visible_ddl_hole_patch_generated"), "identity": value["identity"],
            "response": .string(answer.text), "elapsed_ms": .string("1")]).data
    }
}
