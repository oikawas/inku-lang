import Foundation
import InkuHost
import InkuPersistence
import InkuUI

@MainActor func runBatchUIPresentationChecks() async throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent("inku-batch-ui-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let provider = BatchUIPresentationProvider()
    let app = AppModel(databaseURL: directory.appendingPathComponent("works.sqlite"), transport: provider)
    await app.initialize()
    let service = ProviderSettings(id: "check", baseURL: URL(string: "http://127.0.0.1:1/v1")!, requiresAPIKey: false,
                                   models: [.init(id: "pinned")])
    try await app.updateHostSettings(HostSettings(providers: [service], models: ModelSelection(stage1Model: "check:pinned", stage2Model: "check:pinned")))
    guard let catalog = app.catalogs.first(where: { $0.id != "default" }),
          let otherCatalog = app.catalogs.first(where: { $0.id != catalog.id }),
          let canvas = app.canvases.first, let otherCanvas = app.canvases.first(where: { $0.id != canvas.id }) else {
        throw CheckFailure.message("Batch UI check requires the bundled catalog and paper choices")
    }
    app.inputMode = "ddl"; app.language = "en"; app.seedText = "42"
    app.catalogMode = "auto"; app.catalogID = catalog.id; app.canvasID = canvas.id
    app.sketchMode = "supplied"; app.sketchText = "Creation sketch must not enter a batch"
    app.wild = false; app.display.preferences.batchRetries = 0
    // Failure: a saved unregistered fixture reference became a selectable new batch model.
    app.selectNextDrawingModel("check:mock-ui")
    guard !app.hasAvailableBatchDrawingModel, app.nextBatchDrawingModelReference.isEmpty,
          SettingsModel.batchModels(for: service).map(\.id) == ["pinned"] else {
        throw CheckFailure.message("Unregistered batch model leaked into choices or summary")
    }
    do {
        _ = try app.requestForBatchDescription("must not run", sketchMode: "off")
        throw CheckFailure.message("Unregistered batch model was accepted")
    } catch let error as HostError where error.code == "drawing_model_not_available" {}
    app.selectNextDrawingModel("check:pinned")
    let sketchRequest = try app.requestForBatchDescription("A moon over a hill", sketchMode: "on")
    guard case .description("A moon over a hill", true, .on) = sketchRequest.authoring,
          sketchRequest.parentWorkID == nil, sketchRequest.derivationKind == "new",
          app.inputMode == "ddl", app.sketchMode == "supplied", app.catalogMode == "auto" else {
        throw CheckFailure.message("Batch sketch/auto choice adopted or modified Creation conditions")
    }
    app.catalogMode = "random"
    let batch = AutomationModel()
    await batch.connect(app: app)
    let original = "\r\n  A red circle above black dots scattered at the bottom  \r\n\r\nA second red circle above black dots\r\n"
    batch.batchText = original
    // Failure: CRLF doubled row numbers, or the previous result was labelled as the next active row.
    guard BatchInputLines.physicalLines(in: original).count == 5, batch.nonEmptyBatchCount == 2 else {
        throw CheckFailure.message("Physical CRLF lines or nonempty input count changed")
    }
    let operation = Task { await batch.startBatch(app: app) }
    let deadline = Date().addingTimeInterval(15)
    while !(await provider.secondRowBegan), Date() < deadline { try await Task.sleep(for: .milliseconds(10)) }
    guard await provider.secondRowBegan, batch.running, batch.rows.map(\.line) == [2, 4],
          batch.activeRow?.line == 4, batch.observedRow?.line == 2,
          let firstWork = batch.observedWork, firstWork.id == batch.rows[0].workID,
          firstWork.ddl?.isEmpty == false, firstWork.svg.isEmpty == false,
          batch.batchConditions?.stage1Model == "check:pinned",
          batch.batchConditions?.inputMode == "description", batch.batchConditions?.sketchMode == "off",
          batch.batchConditions?.catalogMode == "fixed", batch.batchConditions?.wild == false,
          case .description(_, false, .off) = batch.rows[0].request.authoring,
          batch.rows[0].request.parentWorkID == nil, batch.rows[0].request.derivationKind == "new",
          batch.batchConditions?.catalogID == catalog.id, batch.batchConditions?.canvasID == canvas.id else {
        await provider.releaseSecondRow(); await operation.value
        throw CheckFailure.message("Batch observer/current row or captured choices changed: \(app.errorText ?? batch.status)")
    }
    let frozen = batch.rows.map(\.request)
    app.catalogID = otherCatalog.id; app.canvasID = otherCanvas.id; app.wild = true
    batch.restoreBatchInput("must not replace running input")
    guard batch.batchText == original, batch.observedRow?.line == 2, batch.observedWork == firstWork else {
        await provider.releaseSecondRow(); await operation.value
        throw CheckFailure.message("Running history restore or next-row progress changed the observed work")
    }
    await provider.releaseSecondRow(); await operation.value
    guard !batch.isOccupied, batch.successfulCount == 1, batch.failedCount == 1,
          batch.pendingCount == 1, batch.nextPendingLine == 4, batch.canResume,
          batch.rows[1].request.renderOptions == frozen[1].renderOptions,
          batch.rows[1].request.configuration == frozen[1].configuration,
          batch.batchPromptHistory == [BatchInputLines.normalizedText(original.trimmingCharacters(in: .whitespacesAndNewlines))] else {
        throw CheckFailure.message("Batch summary, request snapshot or saved input history changed")
    }

    // Failure: restoring input history rewrote the resume journal, or an older journal lost its original row conditions.
    let journalURL = directory.appendingPathComponent("batch-journal.json")
    var oldJournal = try JSONSerialization.jsonObject(with: Data(contentsOf: journalURL)) as! [String: Any]
    oldJournal.removeValue(forKey: "originalText"); oldJournal.removeValue(forKey: "conditions"); oldJournal.removeValue(forKey: "observedRowID")
    let oldBytes = try JSONSerialization.data(withJSONObject: oldJournal)
    try oldBytes.write(to: journalURL, options: .atomic)
    let recovered = AutomationModel()
    await recovered.connect(app: app)
    guard recovered.batchPromptHistory == batch.batchPromptHistory, recovered.observedRow?.line == 2,
          recovered.observedWork == firstWork, recovered.batchConditions?.catalogID == catalog.id,
          recovered.rows.map(\.line) == [2, 4] else {
        throw CheckFailure.message("History or frozen saved work did not reopen with the older journal")
    }
    recovered.restoreBatchInput("another editor draft")
    guard recovered.batchText == "another editor draft", recovered.rows.map(\.input) == batch.rows.map(\.input),
          try Data(contentsOf: journalURL) == oldBytes, app.works.count == 1 else {
        throw CheckFailure.message("History restore changed the saved journal or works")
    }
    app.selectNextDrawingModel("check:changed")
    await provider.allowResume()
    await recovered.resumeBatch(app: app)
    let modelReferences = await provider.modelReferences
    guard recovered.successfulCount == 2, recovered.failedCount == 0, !recovered.canResume,
          recovered.rows[0].workID == firstWork.id, recovered.rows[0].attempts == 1,
          recovered.rows[1].attempts == 2, recovered.observedRow?.line == 4,
          recovered.observedWork?.renderColorCatalogID == catalog.id,
          recovered.observedWork?.renderCanvasAspectID == canvas.id,
          recovered.rows[1].request.models == frozen[1].models,
          recovered.rows[1].request.configuration == frozen[1].configuration,
          recovered.rows[1].request.renderOptions == frozen[1].renderOptions,
          modelReferences.allSatisfy({ $0 == "check:pinned" }), app.works.count == 2,
          app.providerProgress?.tokensIn == nil, app.providerProgress?.tokensOut == nil,
          !app.isBusy, !recovered.isOccupied else {
        throw CheckFailure.message("Resume repainted a success, adopted next conditions, lost observation or invented usage: \(app.errorText ?? recovered.status)")
    }
    print("Batch UI passed: unregistered model rejected; description-only batch ignores Creation DDL/supplied sketch/random; explicit on/auto captured without changing Creation; CRLF rows 2/4; frozen model/catalog/paper/wild; row4 keeps row2 observation; history restores editor only; old journal resumes failed row with original conditions; missing usage stays unknown. Real shared Rust, temporary SQLite and offline provider mock only.")
}

private actor BatchUIPresentationProvider: ProviderTransport {
    private(set) var modelReferences: [String] = []
    private(set) var secondRowBegan = false
    private var completedFirstReading = false
    private var resumeAllowed = false
    private var secondRowReleased = false
    private var release: CheckedContinuation<Void, Never>?

    func releaseSecondRow() { secondRowReleased = true; release?.resume(); release = nil }
    func allowResume() { resumeAllowed = true }

    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let input = try ExactJSON(data: action)
        modelReferences.append(models.stage1Model)
        let tag = try input.requiredString("tag")
        let response: ExactJSON
        let resultTag: String
        switch tag {
        case "generate_normalized_ddl":
            if completedFirstReading, !resumeAllowed {
                if !secondRowBegan {
                    secondRowBegan = true
                    if !secondRowReleased { await withCheckedContinuation { release = $0 } }
                }
                throw HostError("bounded_batch_row_failure")
            }
            response = Self.plan; resultTag = "normalized_ddl_generated"
        case "read_composition":
            completedFirstReading = true; response = Self.reading; resultTag = "composition_read"
        default: throw HostError("unexpected_batch_ui_provider_action")
        }
        return ExactJSON.object(["tag": .string(resultTag), "identity": input["identity"],
            "response": .string(response.text), "elapsed_ms": .string("10")]).data
    }

    private static func layer(_ action: String, _ shape: String, _ count: Int, _ position: String, _ size: String, _ color: String) -> ExactJSON {
        var fields = Dictionary(uniqueKeysWithValues: ["angle", "bleeding", "continuity", "line_up_direction", "motion_amplitude",
            "motion_quality", "proportion", "thinness"].map { ($0, ExactJSON.string("unspecified")) })
        fields.merge(["action": .string(action), "shape": .string(shape), "count": .integer(count), "position": .string(position),
            "size": .string(size), "color": .string(color), "handling": .string("dense"), "tool": .string("pen"),
            "surface": .string(shape == "point" ? "empty" : "flat")]) { _, value in value }
        return .object(fields)
    }
    private static let plan: ExactJSON = .object(["ground": .string("paper"), "background": .string("white"), "plugins": .array([]),
        "layers": .array([layer("fill", "square", 1, "unspecified", "large", "gray"), layer("place", "circle", 1, "center", "small", "red"),
                          layer("scatter", "point", 12, "bottom", "very_small", "black")])])
    private static let reading: ExactJSON = .object(["thesis": .string("A red circle above black dots"),
        "roles": .array(["field", "focal", "scattered"].map(ExactJSON.string)),
        "relations": .array([.object(["type": .string("above"), "layers": .array([.integer(1), .integer(2)]),
            "side": .string("unspecified"), "toward": .string("unspecified")])]),
        "tension": .object(["motion": .string("still"), "focus": .string("unspecified"), "vertical": .string("unspecified"),
            "balance": .string("unspecified"), "symmetry": .string("unspecified"), "void": .string("unspecified")]),
        "stated_places": .array([.object(["layer": .integer(2), "words": .string("at the bottom"), "place": .string("bottom")])])])
}
