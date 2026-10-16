import Foundation
import InkuHost
import InkuPersistence
import InkuUI

/// Failures: invalid/changed fanout exceeds its captured cap; cancellation launches more lanes;
/// legacy demo seconds disappear; a next-four request loses checked options before their commits.
@MainActor
func runFanoutDemoParityChecks() async throws {
    try await checkCapturedFanout()
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-fanout-demo-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    try await checkDemoInterval(folder: folder.appendingPathComponent("demo"))
    try await checkNextFour(folder: folder.appendingPathComponent("next"))
    print("Fanout/demo parity passed: 1/4/16 caps, invalid 0/17 refused, ordered starts, captured setting, cancellation; UI seconds 1...999 and persisted 1...3600; layout/tool save-before-next-four with partial failure, trashed-parent refusal retaining options, retry without duplicate commits, and immutable parents independent of displayed selection. Offline isolated fixtures only.")
}

@MainActor private func checkCapturedFanout() async throws {
    for limit in [1, 4, 16] {
        var preference = limit
        let captured = try RefinementFanout.validatedLimit(preference)
        var active = 0, peak = 0
        var starts: [Int] = [], finished: [Int] = []
        try await RefinementFanout.run(count: 19, limit: captured, onStart: { starts.append($0) }) { index in
            active += 1; peak = max(peak, active)
            defer { active -= 1 }
            preference = 16
            try await Task.sleep(for: .milliseconds((19 - index) % 3 + 1))
            finished.append(index)
        }
        guard peak <= limit, active == 0, starts == Array(0..<19), Set(finished) == Set(0..<19), preference == 16 else {
            throw CheckFailure.message("Fanout ignored cap/order/frozen value: \(limit), peak \(peak)")
        }
    }
    for invalid in [0, 17] {
        var starts = 0, jobs = 0
        do {
            try await RefinementFanout.run(count: 3, limit: invalid, onStart: { _ in starts += 1 }) { _ in jobs += 1 }
            throw CheckFailure.message("Invalid fanout \(invalid) was accepted")
        } catch let error as HostError where error.code == "invalid_refinement_fanout_limit" { }
        guard starts == 0, jobs == 0 else { throw CheckFailure.message("Invalid fanout started jobs") }
    }
    var starts: [Int] = [], jobs: [Int] = []
    let pending = Task { @MainActor in
        try await RefinementFanout.run(count: 20, limit: 4, onStart: { starts.append($0) }) { index in
            jobs.append(index)
            try await Task.sleep(for: .seconds(5))
        }
    }
    for _ in 0..<1000 where starts.count < 4 { await Task.yield() }
    let startsAtCancellation = starts
    pending.cancel()
    do { try await pending.value; throw CheckFailure.message("Cancelled fanout succeeded") }
    catch is CancellationError { }
    guard startsAtCancellation == [0, 1, 2, 3], starts == startsAtCancellation, jobs.count <= 4 else {
        throw CheckFailure.message("Cancellation started additional fanout lanes: \(starts)")
    }
}

@MainActor private func checkDemoInterval(folder: URL) async throws {
    for stored in [999, 1000, 3600] {
        let directory = folder.appendingPathComponent(String(stored))
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let url = directory.appendingPathComponent("demo-settings.json")
        try Data("{\"interval\":\(stored),\"duration\":7200}".utf8).write(to: url)
        let app = AppModel(databaseURL: directory.appendingPathComponent("works.sqlite"), transport: ParityNoProvider())
        await app.initialize()
        let model = AutomationModel()
        await model.connect(app: app)
        guard model.demoInterval == stored, !model.setDemoIntervalFromUI(1000), model.demoInterval == stored else {
            throw CheckFailure.message("Demo did not preserve legacy seconds or refused UI edit mutated them")
        }
        model.demoSaveWorks.toggle()
        let saved = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: Any]
        guard saved["interval"] as? Int == stored else { throw CheckFailure.message("Unmodified demo interval changed on save") }
        guard model.setDemoIntervalFromUI(1), model.demoInterval == 1,
              model.setDemoIntervalFromUI(999), model.demoInterval == 999,
              !model.setDemoIntervalFromUI(0), model.demoInterval == 999,
              DemoIntervalPolicy.acceptsStoredValue(stored), !DemoIntervalPolicy.acceptsStoredValue(3601) else {
            throw CheckFailure.message("Demo UI and stored boundaries were conflated")
        }
    }
}

@MainActor private func checkNextFour(folder: URL) async throws {
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    let transport = ParityNoProvider()
    let url = folder.appendingPathComponent("works.sqlite")
    let app = AppModel(databaseURL: url, transport: transport)
    await app.initialize()
    app.language = "ja"; app.seedText = "42"
    guard await app.drawNewDDL("背景を白で埋める。\n青の細筆の線を3個引く。\n赤の大きな円を1個置く。"), let parent = app.selectedWork else {
        throw CheckFailure.message("Next-four parent failed: \(app.errorText ?? app.status)")
    }
    let database = try InkuDatabase(url: url)
    let layout = RefinementModel(work: parent)
    await layout.initialize(app: app)
    await layout.generate(app: app, count: 4)
    guard layout.candidates.count == 4 else { throw CheckFailure.message("Layout fixture did not prepare four") }
    let originalLayoutIDs = layout.candidates.map(\.id)
    for id in originalLayoutIDs.prefix(2) { layout.selectCandidate(id, selected: true) }
    let badLayout = layout.candidates[1].prepared.executionID
    let layoutSnapshot = try await corruptCandidate(database: database, id: badLayout)
    let beforeLayout = try await database.listExecutionIDs()
    await layout.generate(app: app, count: 4)
    guard layout.candidates.map(\.id) == originalLayoutIDs, layout.selectedCount == 1,
          layout.candidates[0].savedWork != nil, layout.candidates[1].selected,
          layout.errorText != nil, try await database.listExecutionIDs() == beforeLayout,
          try await database.list().count == 2 else {
        throw CheckFailure.message("Layout replaced options/generated after partial save failure")
    }
    let firstLayoutSaved = try await database.loadExecution(id: layout.candidates[0].prepared.executionID)!
    layout.preview(originalLayoutIDs[1])
    _ = try await database.setTrashed(ids: [parent.id], trashed: true)
    let beforeTrashedLayout = try await database.list().count
    await layout.generate(app: app, count: 4)
    guard layout.candidates.map(\.id) == originalLayoutIDs, layout.selectedCount == 1,
          layout.candidates[1].selected, layout.previewID == originalLayoutIDs[1], layout.errorText != nil,
          layout.committedWorks.count == 1, try await database.list().count == beforeTrashedLayout,
          try await database.listExecutionIDs() == beforeLayout,
          try await database.loadExecution(id: firstLayoutSaved.id) == firstLayoutSaved else {
        throw CheckFailure.message("Trashed layout parent lost options, generated or duplicated a prior commit")
    }
    _ = try await database.setTrashed(ids: [parent.id], trashed: false)
    try await restoreCandidate(database: database, record: layoutSnapshot)
    await app.showSavedRefinement(layout.committedWorks[0])
    await layout.generate(app: app, count: 4)
    guard layout.candidates.count == 4, layout.candidates.allSatisfy({ !originalLayoutIDs.contains($0.id) }),
          layout.committedWorks.count == 2, try await database.list().count == 3,
          try await database.loadExecution(id: firstLayoutSaved.id) == firstLayoutSaved else {
        throw CheckFailure.message("Layout retry resaved a committed candidate or did not replace after all saves")
    }
    layout.selectCandidate(layout.candidates[0].id, selected: true)
    await layout.generate(app: app, count: 1)
    guard layout.candidates.count == 1, try await database.list().count == 3 else {
        throw CheckFailure.message("Single layout option unexpectedly autosaved its prior selection")
    }
    let touch = ToolChangeModel(work: parent)
    await touch.generate(app: app)
    guard touch.candidates.count == 4 else { throw CheckFailure.message("Touch fixture did not prepare four") }
    let originalTouchIDs = touch.candidates.map(\.id)
    for id in originalTouchIDs.prefix(2) { touch.selectCandidate(id, selected: true) }
    let touchSnapshot = try await corruptCandidate(database: database, id: touch.candidates[1].prepared.executionID)
    let beforeTouch = try await database.listExecutionIDs()
    await touch.generate(app: app)
    guard touch.candidates.map(\.id) == originalTouchIDs, touch.selectedCount == 1,
          touch.candidates[0].savedWork != nil, touch.candidates[1].selected, touch.errorText != nil,
          try await database.listExecutionIDs() == beforeTouch, try await database.list().count == 4 else {
        throw CheckFailure.message("Touch replaced options/generated after partial save failure")
    }
    let firstTouchSaved = try await database.loadExecution(id: touch.candidates[0].prepared.executionID)!
    touch.preview(originalTouchIDs[1])
    _ = try await database.setTrashed(ids: [parent.id], trashed: true)
    let beforeTrashedTouch = try await database.list().count
    await touch.generate(app: app)
    guard touch.candidates.map(\.id) == originalTouchIDs, touch.selectedCount == 1,
          touch.candidates[1].selected, touch.previewID == originalTouchIDs[1], touch.errorText != nil,
          touch.committedWorks.count == 1, try await database.list().count == beforeTrashedTouch,
          try await database.listExecutionIDs() == beforeTouch,
          try await database.loadExecution(id: firstTouchSaved.id) == firstTouchSaved else {
        throw CheckFailure.message("Trashed touch parent lost options, generated or duplicated a prior commit")
    }
    _ = try await database.setTrashed(ids: [parent.id], trashed: false)
    try await restoreCandidate(database: database, record: touchSnapshot)
    await app.showSavedRefinement(touch.committedWorks[0])
    await touch.generate(app: app)
    guard touch.candidates.count == 4, touch.candidates.allSatisfy({ !originalTouchIDs.contains($0.id) }),
          touch.committedWorks.count == 2, try await database.list().count == 5,
          try await database.loadExecution(id: firstTouchSaved.id) == firstTouchSaved,
          try await database.work(id: parent.id) == parent,
          layout.work.id == parent.id, touch.work.id == parent.id, await transport.calls == 0 else {
        throw CheckFailure.message("Touch retry duplicated a save, lost its immutable parent or called a provider")
    }
    for saved in layout.committedWorks + touch.committedWorks {
        guard let node = saved.lineageNodeID, let edge = try await database.edge(childNodeID: node),
              edge.parentNodeID == parent.lineageNodeID else { throw CheckFailure.message("Next-four adopted a child as its new parent") }
    }
}

private func corruptCandidate(database: InkuDatabase, id: String) async throws -> ExecutionSnapshot {
    guard let record = try await database.loadExecution(id: id) else { throw CheckFailure.message("Candidate snapshot missing") }
    _ = try await database.compareAndSwapExecution(id: id, expectedRevision: record.revision, snapshot: Data("{}".utf8))
    return record
}

private func restoreCandidate(database: InkuDatabase, record: ExecutionSnapshot) async throws {
    let current = try await database.loadExecution(id: record.id)!
    _ = try await database.compareAndSwapExecution(id: record.id, expectedRevision: current.revision, snapshot: record.snapshot)
}

private actor ParityNoProvider: ProviderTransport {
    private(set) var calls = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        throw CheckFailure.message("Fanout/demo fixtures must not call a provider")
    }
}
