import Foundation
import InkuCore
import InkuPersistence
import InkuUI
import InkuHost

@main
struct AppCheck {
    @MainActor
    static func main() async throws {
        if let index = CommandLine.arguments.firstIndex(of: "--raster-only"), CommandLine.arguments.indices.contains(index + 1) {
            try await runRasterChecks(fixtureURL: URL(fileURLWithPath: CommandLine.arguments[index + 1]))
            return
        }
        if CommandLine.arguments.contains("--authoring-only") {
            try await runAuthoringChecks()
            return
        }
        if CommandLine.arguments.contains("--comparison-only") {
            try await runComparisonChecks()
            return
        }
        if CommandLine.arguments.contains("--automation-only") {
            try await runAutomationChecks()
            return
        }
        if CommandLine.arguments.contains("--model-selection-only") {
            try await runModelSelectionChecks()
            return
        }
        if CommandLine.arguments.contains("--plugin-only") {
            try await runPluginChecks()
            return
        }
        if CommandLine.arguments.contains("--cancel-only") {
            try await checkControllerCancellation()
            return
        }
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("inku-app-check-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let databaseURL = directory.appendingPathComponent("inku.sqlite")
        let model = AppModel(databaseURL: databaseURL)
        await model.initialize()
        guard model.canvases.count == 11, !model.catalogs.isEmpty, model.canGenerate else {
            throw CheckFailure.message("Bundled Server defaults or Rust registry failed: \(model.errorText ?? model.status)")
        }
        model.seedText = "42"
        await model.generate()
        guard model.errorText == nil, model.works.count == 1, let work = model.selectedWork,
              !work.svg.isEmpty, !work.score.isEmpty, work.renderSeed == "42" else {
            throw CheckFailure.message("App DDL pipeline did not save: \(model.errorText ?? model.status)")
        }
        let frame = try await model.renderer.image(svg: work.svg, targetWidth: 128)
        guard frame.width > 0, frame.height > 0 else { throw CheckFailure.message("Native frame missing") }
        let recreated = AppModel(databaseURL: databaseURL)
        await recreated.initialize()
        guard recreated.works == model.works else { throw CheckFailure.message("Restart changed canonical saved values") }
        let exportURL = directory.appendingPathComponent("work.svg")
        await model.exportSVG(to: exportURL)
        guard try String(contentsOf: exportURL, encoding: .utf8) == work.svg else {
            throw CheckFailure.message("Export changed canonical SVG")
        }
        print("App pipeline passed: DDL → Score/SVG → SQLite → restart; native \(frame.width)×\(frame.height); canonical SVG export.")
        print("Artifacts: \(directory.path)")
    }

    @MainActor
    private static func checkControllerCancellation() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("inku-controller-cancel-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let databaseURL = directory.appendingPathComponent("inku.sqlite")
        let provider = ProviderSettings(id: "local", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false)
        let settings = HostSettings(providers: [provider], models: ModelSelection(stage1Model: "local:boundary-check", stage2Model: "local:boundary-check"))
        try JSONEncoder().encode(settings).write(to: directory.appendingPathComponent("providers.json"), options: .atomic)

        // A valid backup with a sentinel makes an accidental restore observable.
        let restoreSource = try InkuDatabase(url: directory.appendingPathComponent("restore-source.sqlite"))
        let sentinel = SavedWork(id: "restore-sentinel", at: 1, input: "sentinel", score: "{}", svg: "<svg/>", lineageNodeID: "restore-sentinel-node")
        try await restoreSource.save(sentinel, node: LineageNode(id: "restore-sentinel-node", historyID: sentinel.id, at: 1))
        let restoreURL = directory.appendingPathComponent("restore.sqlite")
        try await restoreSource.backup(to: restoreURL)

        let transport = DelayedControllerProvider()
        let model = AppModel(databaseURL: databaseURL, transport: transport)
        await model.initialize()
        model.inputMode = "description"
        model.descriptionText = "a red circle"
        model.seedText = "42"
        guard model.errorText == nil, model.canGenerate else {
            throw CheckFailure.message("Cancellation fixture did not initialize: \(model.errorText ?? model.status)")
        }
        let generationFinished = BoundedSignal()
        let generation = Task { @MainActor in
            await model.generate()
            await generationFinished.fire()
        }
        try await transport.started.wait()
        let cancelFinished = BoundedSignal()
        let cancellation = Task { @MainActor in
            await model.cancel()
            await cancelFinished.fire()
        }
        try await transport.cancelled.wait()
        guard model.isBusy, !model.canGenerate, model.status == "停止中" else {
            await transport.releaseLateAnswer()
            throw CheckFailure.message("Stop released the controller before its provider task completed")
        }
        // Both entry points must stay closed while the cancelled task is still draining.
        await model.generate()
        await model.restore(from: restoreURL)
        let callsWhileStopping = await transport.calls
        let inspection = try InkuDatabase(url: databaseURL)
        let rowsWhileStopping = try await inspection.list()
        guard model.isBusy, !model.canGenerate, model.errorText == nil,
              model.status == "停止中", callsWhileStopping == 1, rowsWhileStopping.isEmpty else {
            await transport.releaseLateAnswer()
            throw CheckFailure.message("A new generation or restore entered while the operation was stopping")
        }
        await transport.releaseLateAnswer()
        try await generationFinished.wait()
        try await cancelFinished.wait()
        await generation.value
        await cancellation.value
        let finalRows = try await inspection.list()
        guard !model.isBusy, model.canGenerate, model.errorText == nil,
              model.status == "停止しました", model.works.isEmpty, finalRows.isEmpty,
              await transport.calls == 1 else {
            throw CheckFailure.message("Late provider completion changed the stopped controller or saved a work")
        }
        print("Controller cancellation passed: busy retained until completion; generation/restore denied; late response/progress rejected; no saved work.")
    }
}

enum CheckFailure: Error {
    case message(String)
}

/// The deadline releases the waiter rather than waiting for an uncooperative provider task.
private actor BoundedSignal {
    private var fired = false
    private var waiter: CheckedContinuation<Void, Error>?
    private var deadline: Task<Void, Never>?
    func fire() {
        fired = true
        deadline?.cancel(); deadline = nil
        waiter?.resume(); waiter = nil
    }
    func wait() async throws {
        if fired { return }
        try await withCheckedThrowingContinuation { continuation in
            waiter = continuation
            deadline = Task {
                do { try await Task.sleep(for: .seconds(5)) }
                catch { return }
                self.timeout()
            }
        }
    }
    private func timeout() {
        waiter?.resume(throwing: CheckFailure.message("Controller cancellation check timed out"))
        waiter = nil; deadline = nil
    }
}

/// Intentionally ignores task cancellation until the check releases its final answer.
private actor DelayedControllerProvider: ProviderTransport {
    nonisolated let started = BoundedSignal()
    nonisolated let cancelled = BoundedSignal()
    private(set) var calls = 0
    private var action: Data?
    private var continuation: CheckedContinuation<Data, Never>?
    private var progress: (@Sendable (Int) -> Void)?
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1; self.action = action; self.progress = onBytes
        return await withTaskCancellationHandler {
            await withCheckedContinuation { continuation in
                self.continuation = continuation
                Task { await started.fire() }
            }
        } onCancel: {
            Task { await self.cancelled.fire() }
        }
    }
    func releaseLateAnswer() {
        guard let continuation, let action,
              let effect = try? ExactJSON(data: action) else { return }
        self.continuation = nil
        progress?(4096)
        let result = ExactJSON.object(["tag": .string("normalized_ddl_generated"), "identity": effect["identity"],
                                        "response": .string(#"{"normalized_ddl":"place one red circle at center."}"#), "elapsed_ms": .string("1")])
        continuation.resume(returning: result.data)
    }
}
