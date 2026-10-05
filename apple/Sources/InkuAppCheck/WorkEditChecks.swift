import Foundation
import InkuHost
import InkuPersistence
import InkuUI

@MainActor
func runWorkEditChecks(nativeFixtureURL: URL? = nil) async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-work-edit-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let databaseURL = folder.appendingPathComponent("inku.sqlite")
    let transport = WorkEditProvider()
    let app = AppModel(databaseURL: databaseURL, transport: transport)
    await app.initialize()
    let provider = ProviderSettings(id: "check", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false)
    let settings = HostSettings(providers: [provider], models: ModelSelection(stage1Model: "check:original", stage2Model: "check:original"))
    try await app.updateHostSettings(settings)
    app.inputMode = "description"
    app.descriptionText = "a red circle in an open field"
    app.sketchMode = "on"
    app.seedText = "42"
    app.wild = true
    await app.generate()
    guard app.errorText == nil, let first = app.selectedWork, first.sketchState == "supplemented" else {
        throw CheckFailure.message("Work-edit parent fixture did not draw: \(app.errorText ?? app.status)")
    }
    await app.replay(first)
    guard app.errorText == nil, let parent = app.selectedWork, parent.id != first.id else {
        throw CheckFailure.message("Work-edit saved replay fixture failed")
    }
    let reopened = AppModel(databaseURL: databaseURL, transport: transport)
    await reopened.initialize()
    await reopened.selectWork(parent)
    guard !reopened.sourceLocked, !reopened.canRegenerateDescription, await reopened.canEditSavedWork(parent) else {
        throw CheckFailure.message("Fixture must reopen a description-authoritative saved work without a live editor execution")
    }
    let database = try InkuDatabase(url: databaseURL)
    let sourceContext = try await reopened.savedConfiguration(workID: parent.id)
    let sourceConfiguration = try ExactJSON(data: sourceContext.configuration)
    let sourceOptions = try ExactJSON(data: sourceContext.renderOptions)
    let sourceDocument = try ExactJSON(data: sourceContext.document ?? Data("{}".utf8))
    guard sourceConfiguration["definitions"].array?.count == 7, sourceDocument["macro_locks"].array?.count == 7 else {
        throw CheckFailure.message("Work-edit fixture requires complete bundled plugin locks")
    }
    if let nativeFixtureURL {
        guard nativeFixtureURL.isFileURL, nativeFixtureURL.standardizedFileURL.path.hasPrefix("/private/tmp/") else {
            throw CheckFailure.message("Native work-edit fixture must stay under /private/tmp")
        }
        try FileManager.default.createDirectory(at: nativeFixtureURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        guard await reopened.backup(to: nativeFixtureURL) else { throw CheckFailure.message("Native work-edit fixture backup failed") }
        try JSONEncoder().encode(settings).write(to: nativeFixtureURL.deletingLastPathComponent().appendingPathComponent("providers.json"), options: .atomic)
        print("Native modal fixture: \(nativeFixtureURL.path); description-authoritative parent \(parent.id). Mock provider localhost:1; no real transport/auth.")
    }

    // Failure: reopened saved works had no description-edit flow and borrowed mutable next-work settings.
    var next = settings
    next.models.stage1Model = "check:pinned-drawing"
    next.models.stage2Model = "check:pinned-drawing"
    next.plugins = PluginPreferences(disabledPackageIDs: Set(reopened.pluginWords.compactMap(\.packageID)))
    try await reopened.updateHostSettings(next)
    reopened.canvasID = reopened.canvases.first(where: { $0.id != parent.renderCanvasAspectID })!.id
    reopened.catalogID = reopened.catalogs.first(where: { $0.id != parent.catalogID })!.id
    reopened.seedText = "999"
    reopened.wild = false
    let unchanged = try await reopened.makeSavedWorkEditRequest(work: parent, mode: .description, description: parent.effectiveSourceText)
    guard case .description(_, false, .supplied(let prose)) = unchanged.authoring, prose == parent.sketchText else {
        throw CheckFailure.message("Unchanged description did not preserve its saved sketch prose")
    }
    let edit = WorkEditModel(work: parent, mode: .description)
    await edit.initialize(app: reopened)
    edit.draftText = "  a blue square in the same open field  "
    let request = try await reopened.makeSavedWorkEditRequest(work: parent, mode: .description, description: edit.draftText)
    let configuration = try ExactJSON(data: request.configuration)
    guard configuration["definitions"] == sourceConfiguration["definitions"],
          configuration["macro_summaries"] == sourceConfiguration["macro_summaries"],
          configuration["compiler"]["hard_resource_policy"] == sourceConfiguration["compiler"]["hard_resource_policy"],
          configuration["compiler"]["operational_resource_budget"] == sourceConfiguration["compiler"]["operational_resource_budget"],
          try ExactJSON(data: request.renderOptions) == sourceOptions, request.clipPolicy == sourceContext.clipPolicy,
          request.models.stage1Model == "check:pinned-drawing", request.models.stage2Model == "check:pinned-drawing",
          request.parentWorkID == parent.id, request.derivationKind == "description_edit",
          case .description("a blue square in the same open field", false, .on) = request.authoring else {
        throw CheckFailure.message("Saved edit did not pin its parent configuration, models and exact child authoring")
    }
    guard await edit.draw(app: reopened), let edited = edit.result, edited.id != parent.id,
          edited.effectiveSourceText == "a blue square in the same open field", edited.sketchState == "supplemented",
          edited.stage1Model == "check:pinned-drawing", edited.stage2Model == "check:pinned-drawing",
          try await database.edge(childNodeID: edited.lineageNodeID!)?.derivationKind == "description_edit",
          try await database.edge(childNodeID: edited.lineageNodeID!)?.parentNodeID == parent.lineageNodeID,
          try await database.work(id: parent.id) == parent else {
        throw CheckFailure.message("Reopened saved description edit failed to create an immutable-parent child: \(edit.errorText ?? reopened.errorText ?? reopened.status)")
    }
    let editedContext = try await reopened.savedConfiguration(workID: edited.id)
    guard try ExactJSON(data: editedContext.document!)["macro_locks"] == sourceDocument["macro_locks"],
          try await reopened.savedConfiguration(workID: parent.id).configuration == sourceContext.configuration else {
        throw CheckFailure.message("Saved description edit changed or lost exact parent/plugin authority context")
    }

    // Failure: a sketch on/off action replayed stored prose instead of asking or dropping the layer.
    let without = WorkEditModel(work: parent, mode: .sketch)
    await without.initialize(app: reopened)
    guard without.sketchMode == "off", await without.draw(app: reopened), let off = without.result,
          off.sketchText == nil, off.sketchState == "off",
          try await database.edge(childNodeID: off.lineageNodeID!)?.derivationKind == "sketch_grain_change" else {
        throw CheckFailure.message("Sketch-off saved action did not drop the layer")
    }
    let with = WorkEditModel(work: parent, mode: .sketch)
    await with.initialize(app: reopened)
    with.sketchMode = "on"
    guard await with.draw(app: reopened), let on = with.result, on.sketchState == "supplemented",
          on.sketchText != parent.sketchText, on.effectiveSourceText == parent.effectiveSourceText,
          on.renderWild == parent.renderWild, await transport.sketchCalls == 3,
          try await database.edge(childNodeID: on.lineageNodeID!)?.parentNodeID == parent.lineageNodeID else {
        throw CheckFailure.message("Sketch-on saved action reused its old supplement or lost parent conditions")
    }
    reopened.ddlText = "place one green circle at center."
    await reopened.commitDDL()
    guard reopened.errorText == nil, let locked = reopened.selectedWork, locked.id != on.id,
          locked.ddl == reopened.ddlText, reopened.sourceLocked,
          try await database.edge(childNodeID: locked.lineageNodeID!)?.parentNodeID == on.lineageNodeID else {
        throw CheckFailure.message("Post-dialog DDL edit did not commit a source-authoritative child: \(reopened.errorText ?? reopened.status)")
    }
    let count = try await database.list().count
    let calls = await transport.calls
    guard !(await reopened.canEditSavedWork(locked)) else { throw CheckFailure.message("Locked saved source advertised description editing") }
    do {
        _ = try await reopened.makeSavedWorkEditRequest(work: locked, mode: .sketch, description: locked.effectiveSourceText, sketchMode: "on")
        throw CheckFailure.message("Locked saved source accepted sketch regeneration")
    } catch let error as HostError where error.code == "description_source_locked" { }
    guard await transport.calls == calls, try await database.list().count == count else {
        throw CheckFailure.message("Locked saved edit sent a request or added a child")
    }

    // Failure: closing/stopping a saved edit allowed a late provider answer to change selection or save.
    let stopped = WorkEditModel(work: parent, mode: .description)
    await stopped.initialize(app: reopened)
    stopped.draftText = "another reading of the open field"
    await transport.blockNextCall()
    let displayed = reopened.selectedWork
    let displayedSVG = reopened.currentSVG
    let displayedDDL = reopened.visibleDDL
    let drawing = Task { @MainActor in await stopped.draw(app: reopened) }
    try await transport.started.wait()
    let stopping = Task { @MainActor in await stopped.stop(app: reopened) }
    try await transport.cancelled.wait()
    guard stopped.running, stopped.stopping, reopened.isBusy, reopened.selectedWork == displayed else {
        await transport.releaseLateAnswer()
        throw CheckFailure.message("Work-edit stop released its controller before provider completion")
    }
    await transport.releaseLateAnswer()
    guard !(await drawing.value) else { throw CheckFailure.message("Stopped work edit reported a committed child") }
    await stopping.value
    guard !stopped.running, !stopped.stopping, !reopened.isBusy, stopped.result == nil,
          reopened.selectedWork == displayed, reopened.currentSVG == displayedSVG, reopened.visibleDDL == displayedDDL,
          try await database.list().count == count, try await database.work(id: parent.id) == parent else {
        throw CheckFailure.message("Late saved-edit completion changed the workspace or saved a child")
    }
    print("Work edit passed: reopened saved description child; exact parent configuration/plugin locks and pinned drawing models; fresh sketch on and omitted sketch off; locked source refusal; cancellation drains with no late child or workspace change. Mock transport + real Rust core only.")
}

private actor WorkEditSignal {
    private var fired = false
    private var waiter: CheckedContinuation<Void, Error>?
    private var deadline: Task<Void, Never>?
    func fire() { fired = true; deadline?.cancel(); deadline = nil; waiter?.resume(); waiter = nil }
    func wait() async throws {
        if fired { return }
        try await withCheckedThrowingContinuation { continuation in
            waiter = continuation
            deadline = Task {
                do { try await Task.sleep(for: .seconds(5)) } catch { return }
                self.timeout()
            }
        }
    }
    private func timeout() { waiter?.resume(throwing: CheckFailure.message("Work-edit cancellation boundary timed out")); waiter = nil; deadline = nil }
}

private actor WorkEditProvider: ProviderTransport {
    nonisolated let started = WorkEditSignal()
    nonisolated let cancelled = WorkEditSignal()
    private(set) var calls = 0
    private(set) var sketchCalls = 0
    private var blockNext = false
    private var blockedAction: ExactJSON?
    private var continuation: CheckedContinuation<Data, Never>?

    func blockNextCall() { blockNext = true }
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        let input = try ExactJSON(data: action)
        if blockNext {
            blockNext = false; blockedAction = input
            return await withTaskCancellationHandler {
                await withCheckedContinuation { continuation in
                    self.continuation = continuation
                    Task { await started.fire() }
                }
            } onCancel: { Task { await self.cancelled.fire() } }
        }
        return response(input)
    }
    func releaseLateAnswer() {
        guard let continuation, let action = blockedAction else { return }
        self.continuation = nil; blockedAction = nil
        continuation.resume(returning: response(action))
    }
    private func response(_ action: ExactJSON) -> Data {
        let isSketch = action["tag"].string == "generate_sketch"
        if isSketch { sketchCalls += 1 }
        let body = isSketch ? ExactJSON.object(["sketch": .string("An open field extends into distant light \(sketchCalls).")]).text
            : #"{"normalized_ddl":"place one red circle at center."}"#
        return ExactJSON.object(["tag": .string(isSketch ? "sketch_generated" : "normalized_ddl_generated"),
            "identity": action["identity"], "response": .string(body), "elapsed_ms": .string("1")]).data
    }
}
