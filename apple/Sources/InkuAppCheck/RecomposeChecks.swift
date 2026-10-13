import Foundation
import InkuHost
import InkuPersistence
import InkuUI

/// Server `_recompose` / Web layout options: numeric composition ranges chosen again by principle or by chance
/// with the real core, drawn as direct DDL children; ranges that cannot move keep the saved document.
@MainActor func runRecomposeChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-recompose-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let databaseURL = folder.appendingPathComponent("works.sqlite")
    let app = AppModel(databaseURL: databaseURL, transport: RecomposeNoProvider())
    await app.initialize()
    let provider = ProviderSettings(id: "check", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false,
                                    models: [ProviderModelSettings(id: "m")])
    try await app.updateHostSettings(HostSettings(providers: [provider], models: ModelSelection(stage1Model: "check:m", stage2Model: "check:m")))

    // Failure: the parameters dialog still offered layout, which now has its own dialog (WorkActionMenu).
    guard RefinementKind.availableKinds == [.reading, .touch] else { throw CheckFailure.message("Parameters still offer \(RefinementKind.availableKinds)") }

    let ranged = """
    Paper.
    Fill the background with white.
    Fill one gray pen dense flat large square at the left half (horizontal 0 to 1/2, vertical 0 to 1).
    Place one red pen dense flat small circle at the upper left quarter (horizontal 0 to 1/2, vertical 0 to 1/2).
    """
    guard await app.drawNewDDL(ranged), let parent = app.displayedWork, let parentDDL = parent.ddl else {
        throw CheckFailure.message("Ranged parent failed: \(app.errorText ?? app.status)")
    }
    guard await app.drawNewDDL("place one red circle at center."), let still = app.displayedWork else {
        throw CheckFailure.message("Unranged parent failed: \(app.errorText ?? app.status)")
    }
    var report: [String] = []
    let succeeded = await app.performComparison(status: "recompose check") { token in
        // Failure: an option drew the saved ranges again instead of choosing them by principle.
        let principled = try await app.makeDrawingAdjustmentPlans(work: parent, kind: "layout_change", count: 4)
        var candidates: [PreparedCandidate] = []
        for plan in principled {
            guard let recomposition = plan.recomposition, recomposition.mode == .principled, recomposition.recomposed,
                  !recomposition.moves.isEmpty, let source = recomposition.source, source != parentDDL else {
                throw CheckFailure.message("Principled option did not recompose: \(String(describing: plan.recomposition))")
            }
            let candidate = try await app.prepareDrawingAdjustmentCandidate(plan: plan, token: token)
            guard candidate.work.ddl == source else { throw CheckFailure.message("Option drew \(candidate.work.ddl ?? "-") instead of the chosen source") }
            candidates.append(candidate)
        }
        report.append("principled moves " + principled.map { String($0.recomposition!.moves.count) }.joined(separator: "/"))
        // Failure: the adopted child forgot how its ranges were chosen.
        let saved = try await app.adoptDrawingAdjustmentCandidate(candidate: candidates[0], token: token)
        guard let node = saved.lineageNodeID, let edge = try await InkuDatabase(url: databaseURL).edge(childNodeID: node),
              edge.derivationKind == "layout_change",
              let metadata = try? ExactJSON(data: Data(edge.metadataJSON.utf8)),
              metadata["recompose_mode"].string == "principled", metadata["composition_seed"].number != nil else {
            throw CheckFailure.message("Adopted layout child lost recompose_mode or composition_seed")
        }
        // Failure: chance was not asked, or answered outside recomposed / same_ranges.
        let chance = try await app.makeDrawingAdjustmentPlans(work: parent, kind: "layout_change", count: 4, recomposeMode: .chance)
        guard chance.allSatisfy({ plan in plan.recomposition.map { $0.mode == .chance && ($0.recomposed || $0.reason == "same_ranges") } ?? false }) else {
            throw CheckFailure.message("Chance options: \(chance.map { String(describing: $0.recomposition) })")
        }
        report.append("chance recomposed \(chance.filter { $0.recomposition!.recomposed }.count)/4")
        // Failure: a work without ranges did not say why, or did not keep its document.
        let kept = try await app.makeDrawingAdjustmentPlans(work: still, kind: "layout_change", count: 1)
        guard let recomposition = kept[0].recomposition, !recomposition.recomposed, recomposition.reason == "nothing_to_move",
              recomposition.lines(display: app.display) == ["この作品には構図の範囲が無い。", "構図の範囲を保って描き直しました。"] else {
            throw CheckFailure.message("Unranged option: \(String(describing: kept[0].recomposition))")
        }
        let keptCandidate = try await app.prepareDrawingAdjustmentCandidate(plan: kept[0], token: token)
        guard keptCandidate.work.ddl == still.ddl else { throw CheckFailure.message("Kept ranges changed the DDL") }
        // Failure: the AI process drew a layout generation without choosing its ranges again.
        let generation = try await app.makeRefinementRequest(work: parent, kind: "layout_change")
        guard case .directDDL(let chosen) = generation.authoring, chosen != parentDDL, generation.retainedDocument == nil,
              let generationMetadata = generation.derivationMetadata.flatMap({ try? ExactJSON(data: $0) }),
              generationMetadata["recompose_mode"].string == "principled" else {
            throw CheckFailure.message("AI process layout did not recompose by principle")
        }
    }
    guard succeeded else { throw CheckFailure.message("Recompose check failed: \(app.errorText ?? app.status)") }
    print("Recompose passed: parameters offer reading and touch only; 4 principled options recomposed (\(report[0])) and drew the chosen sources; the adopted child records recompose_mode; chance options (\(report[1])); a work without ranges keeps its DDL with nothing_to_move; the AI process layout recomposes by principle. Real core, no provider.")
}

private actor RecomposeNoProvider: ProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        throw HostError("recompose_check_sends_nothing")
    }
}
