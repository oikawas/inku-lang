import Foundation
import InkuHost
import InkuPersistence
import InkuUI

/// Server `test_a_composed_description_takes_the_laws_a_reader_chose.py` and
/// `test_a_run_asked_for_its_colors_prints_the_colors_a_reader_chose.py`, through the native host and the real core.
@MainActor func runLawsColorsHostChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-laws-colors-host-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let app = AppModel(databaseURL: folder.appendingPathComponent("bootstrap.sqlite"), transport: LawsColorsCheckProvider(refuseColors: true))
    await app.initialize()
    guard app.errorText == nil, !app.catalogs.isEmpty, !app.canvases.isEmpty else {
        throw CheckFailure.message("Laws/colors host fixture could not load bundled defaults: \(app.errorText ?? app.status)")
    }
    let service = ProviderSettings(id: "laws-check", baseURL: URL(string: "http://127.0.0.1:1/v1")!, requiresAPIKey: false,
                                   models: [ProviderModelSettings(id: "pinned")])
    let models = ModelSelection(stage1Model: "laws-check:pinned", stage2Model: "laws-check:pinned")
    try await app.updateHostSettings(HostSettings(providers: [service], models: models))
    app.inputMode = "description"; app.language = "ja"; app.seedText = "7"
    let database = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
    let credentials = LawsColorsEmptyCredentials()
    var report: [String] = []

    // (a) The color stage refuses once: the run commits the document the laws printed.
    app.descriptionText = "赤い円がひとつ浮かび、下に黒い点が散らばる"
    let refusedRequest = try app.requestForCurrentInput()
    let config = try ExactJSON(data: refusedRequest.configuration)
    let palette = config["compiler"]["host"]["palette"]
    guard config["laws"] == .object([:]), config["colors"] == .object(["render_seed": .string("7")]),
          let paints = palette["paints"].array, paints.count == palette["observations"].array?.count, !paints.isEmpty else {
        throw CheckFailure.message("P1: the new work's settings lack laws, the colors' render seed or the paints: laws=\(config["laws"].text) colors=\(config["colors"].text) paints=\(palette["paints"].text)")
    }
    report.append("P1 paints \(paints.count)")
    let refusing = LawsColorsCheckProvider(refuseColors: true)
    let host = PipelineHost(database: database, transport: refusing, credentials: credentials)
    let refused = try await host.generate(refusedRequest)
    let sent = await refusing.actions
    guard refused.phase == "completed", let refusedID = refused.savedWorkID,
          sent.map({ $0["tag"].string ?? "" }) == ["generate_normalized_ddl", "read_composition", "choose_laws", "choose_colors"],
          await refusing.selectedModels == Array(repeating: "laws-check:pinned", count: 4) else {
        let asked = sent.filter { $0["tag"].string == "choose_laws" }.dropFirst().map { String(($0["payload"]["prompt"]["message"].string ?? "").suffix(400)) }
        throw CheckFailure.message("P2: the sends were \(sent.map { $0["tag"].string ?? "" }) in phase \(refused.phase); asked again with:\n\(asked.joined(separator: "\n---\n"))")
    }
    let colorsMessage = sent[3]["payload"]["prompt"]["message"].string ?? ""
    guard let lawsEvent = try lawsColorsEvent(refused, tag: "laws_chosen"),
          lawsEvent.object?["main_layer"] == ExactJSON.null,
          let refusedDDL = refused.visibleDDL, !refusedDDL.isEmpty,
          try await host.restoreSavedWork(workID: refusedID).ddl == refusedDDL,
          colorsMessage.contains(#""name":"black","paint":"黒""#) else {
        throw CheckFailure.message("P3: the host lost the laws event's null main_layer, the core's document or the color table")
    }
    report.append("P3 events \(lawsColorsEventTags(refused).filter { $0.hasPrefix("laws") || $0.hasPrefix("colors") })")

    // P5: the prompt tab keeps both stages with what they were sent, and the metrics time them apart from Stage 1.
    let presentation = try await host.savedWorkPresentation(workID: refusedID)
    let savedPrompts = try presentation.promptJSON.map { try ExactJSON(data: $0).array ?? [] } ?? []
    let lawsPrompt = savedPrompts.first { $0["action"].string == "choose_laws" }
    let colorsPrompt = savedPrompts.first { $0["action"].string == "choose_colors" }
    let metrics = try await host.savedProviderMetrics(workID: refusedID)
    guard presentation.promptStages == ["sketch", "stage1", "composition", "laws", "colors", "stage2"],
          lawsPrompt?["prompt"]["message"].string == sent[2]["payload"]["prompt"]["message"].string,
          lawsPrompt?["prompt"]["system"].string == sent[2]["payload"]["prompt"]["system"].string,
          colorsPrompt?["prompt"]["message"].string == colorsMessage,
          metrics.map(\.stage) == [.stage1, .composition, .laws, .colors] else {
        throw CheckFailure.message("P5: stages \(presentation.promptStages), prompts \(savedPrompts.map { $0["action"].string ?? "" }), metrics \(metrics.map(\.stage))")
    }

    // P6: the work keeps its laws records, and a child drawn without a run keeps the parent's.
    let saved = try await host.savedAuthoringContext(workID: refusedID)
    guard let records = try saved.lawsRecords.map(ExactJSON.init(data:)),
          records["laws_layers"].object != nil,
          records["laws_basis"].object?["main_layer"] == ExactJSON.null else {
        throw CheckFailure.message("P6: the saved work lacks laws_layers or its basis's explicit null main_layer")
    }
    let page = try await host.makeColorArrangementPage(workID: refusedID, cursor: 0)
    guard let arrangement = page.plans.first else { throw CheckFailure.message("P6: no color arrangement was offered") }
    let arranged = try await host.saveCandidate(executionID: try await host.previewSavedScoreVariant(arrangement).executionID)
    guard try await host.savedAuthoringContext(workID: arranged.id).lawsRecords.map(ExactJSON.init(data:)) == records else {
        throw CheckFailure.message("P6: the color arrangement child lost its parent's laws records")
    }
    // The core takes the records on a direct DDL drawn from the work and keeps them while the DDL is the same.
    var redraw = GenerationRequest(authoring: .directDDL(refused.visibleDDL ?? ""), configuration: saved.configuration,
        renderOptions: saved.renderOptions, clipPolicy: saved.clipPolicy, models: models, providers: [service],
        description: app.descriptionText, parentWorkID: refusedID, derivationKind: "ddl_edit")
    redraw.lawsRecords = saved.lawsRecords
    let redrawn = try await host.generate(redraw)
    guard redrawn.phase == "completed", let redrawnID = redrawn.savedWorkID,
          let kept = try await host.savedAuthoringContext(workID: redrawnID).lawsRecords.map(ExactJSON.init(data:)),
          kept["laws_layers"] == records["laws_layers"], await refusing.actions.count == 4 else {
        throw CheckFailure.message("The direct DDL child did not keep its parent's laws_layers, or it sent to a model")
    }
    // Older works keep their numbered basis; loading one does not rewrite the saved parent's record.
    var oldRecords = records
    oldRecords["laws_basis"]["main_layer"] = .integer(1)
    var oldRedraw = redraw; oldRedraw.lawsRecords = oldRecords.data
    let oldChild = try await host.generate(oldRedraw)
    guard oldChild.phase == "completed", let oldChildID = oldChild.savedWorkID,
          let oldKept = try await host.savedAuthoringContext(workID: oldChildID).lawsRecords.map(ExactJSON.init(data:)),
          oldKept["laws_basis"]["main_layer"] == .integer(1),
          try await host.savedAuthoringContext(workID: refusedID).lawsRecords.map(ExactJSON.init(data:)) == records,
          await refusing.actions.count == 4 else {
        throw CheckFailure.message("The old numbered basis was lost, its parent changed, or a direct child sent to a model")
    }

    // (b) The color stage answers with its own target layer; the host keeps the core's result.
    app.descriptionText = "円がひとつ浮かび、下に点が散らばる"
    let answering = LawsColorsCheckProvider(refuseColors: false)
    let answeringHost = PipelineHost(database: database, transport: answering, credentials: credentials)
    let colored = try await answeringHost.generate(try app.requestForCurrentInput())
    guard colored.phase == "completed", let coloredID = colored.savedWorkID,
          await answering.actions.map({ $0["tag"].string ?? "" }) == ["generate_normalized_ddl", "read_composition", "choose_laws", "choose_colors"],
          let colorsEvent = try lawsColorsEvent(colored, tag: "colors_chosen"),
          colorsEvent.object?["main_layer"] == ExactJSON.null, colorsEvent.object?["ground"] == ExactJSON.null,
          let coloredDDL = colored.visibleDDL, !coloredDDL.isEmpty,
          try await answeringHost.restoreSavedWork(workID: coloredID).ddl == coloredDDL else {
        throw CheckFailure.message("P4: the host lost the colors event's null fields or the core's saved document: \(colored.visibleDDL ?? "")")
    }
    print("Laws/colors host passed: \(report.joined(separator: "; ")); real core Stage 1 -> read -> laws -> colors with Stage 1's model; fallback and answered documents saved; prompt tab and metrics keep laws and colors apart; explicit null main_layer in events and basis, null ground when unchanged; records carried by color arrangement and direct DDL children; old numbered basis and saved parent preserved without sends. Temporary DB only.")
}

/// Failure: the colors' ground or the core's resulting document is lost at the host/save/replay boundary.
@MainActor func runColorsGroundHostCheck() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-colors-ground-host-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let provider = LawsColorsCheckProvider(refuseColors: false, ground: "black")
    let app = AppModel(databaseURL: folder.appendingPathComponent("bootstrap.sqlite"), transport: provider)
    await app.initialize()
    let service = ProviderSettings(id: "laws-check", baseURL: URL(string: "http://127.0.0.1:1/v1")!, requiresAPIKey: false,
        models: [.init(id: "pinned")])
    try await app.updateHostSettings(HostSettings(providers: [service], models: .init(stage1Model: "laws-check:pinned", stage2Model: "laws-check:pinned")))
    app.inputMode = "description"; app.descriptionText = "円がひとつ浮かび、下に点が散らばる"
    app.language = "ja"; app.seedText = "7"; app.sketchMode = "off"
    let database = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
    let host = PipelineHost(database: database, transport: provider, credentials: LawsColorsEmptyCredentials())
    let colored = try await host.generate(try app.requestForCurrentInput())
    guard colored.phase == "completed", let id = colored.savedWorkID, let ddl = colored.visibleDDL, !ddl.isEmpty,
          let event = try lawsColorsEvent(colored, tag: "colors_chosen"), event["ground"].string == "black",
          event.object?["main_layer"] == ExactJSON.null,
          await provider.actions.map({ $0["tag"].string ?? "" }) == ["generate_normalized_ddl", "read_composition", "choose_laws", "choose_colors"] else {
        throw CheckFailure.message("The chosen ground did not reach the host: \(String(decoding: colored.eventsJSON, as: UTF8.self).suffix(2000))")
    }
    let saved = try await host.restoreSavedWork(workID: id)
    let replayed = try await host.replay(workID: id)
    guard saved.ddl == ddl, replayed.ddl == ddl, replayed.score == saved.score,
          try await host.restoreSavedWork(workID: id) == saved, await provider.actions.count == 4 else {
        throw CheckFailure.message("The ground's core document or Score changed during save/replay, or replay called a provider")
    }
    print("Colors ground host passed: optional ground=black accepted; colors_chosen keeps ground and explicit null main_layer; core document and Score saved and replayed unchanged; replay sends=0. Fake provider and temporary SQLite only.")
}

private func lawsColorsEvent(_ view: PipelineView, tag: String) throws -> ExactJSON? {
    let events = try ExactJSON(data: view.eventsJSON).array ?? []
    return events.first(where: { $0["tag"].string == tag })?["payload"]
}

private func lawsColorsEventTags(_ view: PipelineView) -> [String] {
    (try? ExactJSON(data: view.eventsJSON).array?.compactMap { $0["tag"].string }) ?? []
}

actor LawsColorsCheckProvider: ObservedProviderTransport {
    private var refuseColors: Bool
    private let ground: String?
    private(set) var actions: [ExactJSON] = []
    private(set) var selectedModels: [String] = []
    init(refuseColors: Bool, ground: String? = nil) { self.refuseColors = refuseColors; self.ground = ground }
    func allowColors() { refuseColors = false }
    /// Records each attempt under the stage the host names for its action, as the native transport does.
    func performObserved(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                         observation: ProviderObservationOptions, willSend: @escaping ProviderObservationHandler,
                         didFinish: @escaping ProviderObservationHandler, onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let input = try ExactJSON(data: action)
        let tag = try input.requiredString("tag")
        guard let stage = ProviderObservationStage(action: tag), let timeout = input["timeout_ms"].string.flatMap(UInt64.init) else {
            throw HostError("invalid_laws_colors_check_action")
        }
        var metric = ProviderAttemptMetric(identity: try ProviderActionIdentity(action: action), action: tag, stage: stage,
            requestedModelReference: models.stage1Model, providerID: "laws-check", model: "pinned", timeoutMS: timeout)
        try await willSend(.init(metric: metric, raw: nil))
        let result = try await perform(action: action, models: models, providers: providers, credentials: credentials, onBytes: onBytes)
        metric.elapsedMS = 10; metric.sent = true; metric.httpStatus = 200
        metric.outcome = try ExactJSON(data: result)["tag"].string == "provider_failed" ? .failed : .completed
        try await didFinish(.init(metric: metric, raw: nil))
        return result
    }
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let action = try ExactJSON(data: action)
        actions.append(action); selectedModels.append(models.stage1Model)
        let answers: [String: (String, ExactJSON)] = ["generate_normalized_ddl": ("normalized_ddl_generated", Self.plan),
            "read_composition": ("composition_read", Self.reading), "choose_laws": ("laws_chosen", Self.laws),
            "choose_colors": ("colors_chosen", Self.colors)]
        let tag = try action.requiredString("tag")
        if tag == "choose_colors" && refuseColors {
            return ExactJSON.object(["tag": .string("provider_failed"), "identity": action["identity"],
                "failure": .string("provider_rejected"), "elapsed_ms": .string("0")]).data
        }
        guard let (resultTag, response) = answers[tag] else { throw HostError("unexpected_laws_colors_check_effect") }
        var answer = response
        if tag == "choose_colors", let ground { answer["ground"] = .string(ground) }
        return ExactJSON.object(["tag": .string(resultTag), "identity": action["identity"],
            "response": .string(answer.text), "elapsed_ms": .string("10")]).data
    }
    private static func layer(_ action: String, _ shape: String, _ count: Int, _ position: String, _ size: String, _ color: String) -> ExactJSON {
        var fields = Dictionary(uniqueKeysWithValues: ["angle", "bleeding", "continuity", "line_up_direction", "motion_amplitude", "motion_quality", "proportion", "thinness"].map { ($0, ExactJSON.string("unspecified")) })
        fields.merge(["action": .string(action), "shape": .string(shape), "count": .integer(count), "position": .string(position),
            "size": .string(size), "color": .string(color), "handling": .string("dense"), "tool": .string("pen"),
            "surface": .string(shape == "point" ? "empty" : "flat")]) { _, value in value }
        return .object(fields)
    }
    private static let plan: ExactJSON = .object(["ground": .string("paper"), "background": .string("white"), "plugins": .array([]),
        "layers": .array([layer("fill", "square", 1, "unspecified", "large", "gray"), layer("place", "circle", 1, "center", "small", "red"),
                          layer("scatter", "point", 12, "bottom", "very_small", "black")])])
    private static let reading: ExactJSON = .object(["thesis": .string("ひとつの円が点の床の上に浮かぶ"),
        "roles": .array(["field", "focal", "scattered"].map(ExactJSON.string)),
        "relations": .array([.object(["type": .string("above"), "layers": .array([.integer(1), .integer(2)]),
            "side": .string("unspecified"), "toward": .string("unspecified")])]),
        "tension": .object(["motion": .string("still"), "focus": .string("unspecified"), "vertical": .string("unspecified"),
            "balance": .string("unspecified"), "symmetry": .string("unspecified"), "void": .string("unspecified")]),
        "stated_places": .array([.object(["layer": .integer(2), "words": .string("下に"), "place": .string("bottom")])])])
    // The circle goes to the golden section's upper left crossing; the dots keep their hand.
    private static let laws: ExactJSON = .object(["main_law": .string("B1"),
        "description_counts": .array([.object(["layer": .integer(1), "words": .string("円がひとつ")])]),
        "laws": .object(["B1": .object(["targets": .array([.object(["layer": .integer(1), "at": .string("point_ul")])])]),
                         "B21": .object(["targets": .array([.object(["layer": .integer(2), "hand": .string("still")])])])]),
        "reason": .string("円を黄金分割の左上の交点に置く。")])
    // D5 names the circle's layer itself; the laws stage no longer supplies a main layer.
    private static let colors: ExactJSON = .object(["main_law": .string("D5"), "laws": .object(["D5": .object(["hue": .string("blue"), "layer": .integer(1)])]),
        "reason": .string("青を軸に近い色でまとめる。")])
}

private actor LawsColorsEmptyCredentials: CredentialStore {
    func key(for credentialID: String) async throws -> String? { nil }
}
