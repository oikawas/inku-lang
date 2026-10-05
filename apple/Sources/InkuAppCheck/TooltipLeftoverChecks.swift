import Foundation
import InkuHost
import InkuPersistence
import InkuUI

/// The tooltip port against the Build1162 Web, and the leftover UI items, each against the failure it prevents.
/// Offline: temporary SQLite, offline provider mocks, and the Swift sources read as text.
@MainActor
func runTooltipAndLeftoverChecks() async throws {
    let sources = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("InkuUI", isDirectory: true)
    var cache: [String: [String]] = [:]
    func lines(_ path: String) throws -> [String] {
        if let cached = cache[path] { return cached }
        let read = try String(contentsOf: sources.appendingPathComponent(path), encoding: .utf8).components(separatedBy: "\n")
        cache[path] = read
        return read
    }

    // Failure (T2): a Web tooltip has no Swift counterpart, or the table stopped covering the Web's sites.
    let accepted = ["tooltip", "Tooltip", ".help(", "tip(", "title:", "hint:", "serverKey:", "tooltips:"]
    var counts: [String: (equal: Int, missing: Int, excluded: Int)] = [:]
    var missing: [String] = []
    for entry in tooltipParityTable {
        var row = counts[entry.component] ?? (0, 0, 0)
        if entry.excluded != nil {
            row.excluded += 1
        } else if let path = entry.swift, let marker = entry.marker,
                  try lines(path).contains(where: { line in line.contains(marker) && accepted.contains { line.contains($0) } }) {
            row.equal += 1
        } else {
            row.missing += 1
            missing.append("\(entry.web) → \(entry.swift ?? "-"): \(entry.marker ?? "-")")
        }
        counts[entry.component] = row
    }
    let equal = counts.values.map(\.equal).reduce(0, +)
    let excluded = counts.values.map(\.excluded).reduce(0, +)
    guard tooltipParityTable.count == 173, missing.isEmpty, excluded == 9, equal == 164 else {
        throw CheckFailure.message("Tooltip parity: \(tooltipParityTable.count) sites, \(equal) equal, \(excluded) excluded, missing \(missing)")
    }

    // Failure (T1): a `.help` (about 1 s, no focus, none on a disabled control) is left where the Web shows a bubble.
    // Menu items keep `.help`: AppKit draws them as menu item tool tips, and a bubble cannot sit inside an NSMenu.
    var helps: [String: Int] = [:]
    var bubbles = 0
    let files = FileManager.default.enumerator(at: sources, includingPropertiesForKeys: nil)?.compactMap { $0 as? URL }
        .filter { $0.pathExtension == "swift" } ?? []
    for file in files {
        let text = try String(contentsOf: file, encoding: .utf8)
        let help = text.components(separatedBy: ".help(").count - 1
        if help > 0 { helps[file.lastPathComponent] = help }
        bubbles += text.components(separatedBy: ".inkuTooltip(").count - 1
    }
    guard helps == ["SavedWorkActionState.swift": 3, "LineageView.swift": 3, "LibraryView.swift": 3] else {
        throw CheckFailure.message("`.help` outside menu items: \(helps)")
    }

    // Failure (T1): the bubble leaves the window, covers the element, or keeps a side that has no room.
    let window = CGRect(x: 0, y: 0, width: 800, height: 600)
    let size = CGSize(width: 120, height: 40)
    let middle = InkuTooltipLayout.place(size: size, anchor: CGRect(x: 380, y: 300, width: 40, height: 20), bounds: window,
                                         placement: .top, gap: 3)
    let atTop = InkuTooltipLayout.place(size: size, anchor: CGRect(x: 380, y: 570, width: 40, height: 20), bounds: window,
                                        placement: .top, gap: 3)
    let atLeft = InkuTooltipLayout.place(size: size, anchor: CGRect(x: 0, y: 300, width: 20, height: 20), bounds: window,
                                         placement: .top, gap: 3)
    let atRight = InkuTooltipLayout.place(size: size, anchor: CGRect(x: 760, y: 300, width: 30, height: 20), bounds: window,
                                          placement: .right, gap: 3)
    guard middle.frame == CGRect(x: 340, y: 323, width: 120, height: 40), middle.arrowEdge == .bottom,
          atTop.frame.maxY == 567, atTop.arrowEdge == .top,
          atLeft.frame.minX == 0, atLeft.arrowOffset == 10,
          atRight.frame.maxX == 757, atRight.arrowEdge == .trailing,
          [middle, atTop, atLeft, atRight].allSatisfy({ window.contains($0.frame) }) else {
        throw CheckFailure.message("Tooltip placement: \(middle) \(atTop) \(atLeft) \(atRight)")
    }

    // Failure (T4): the switch names the wrong action, or switching off leaves bubbles.
    let display = DisplaySettings()
    let shown = display.tooltip("ツールチップを非表示", serverKey: "tooltipsHide")
    display.preferences.showTooltips = false
    guard shown == "ツールチップを非表示", display.tooltip("ツールチップを表示", serverKey: "tooltipsShow").isEmpty,
          ServerTips.text("tooltipsShow", language: "ja") == "ツールチップを表示" else {
        throw CheckFailure.message("Tooltip switch copy: \(shown)")
    }

    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-tooltips-leftovers-" + UUID().uuidString)
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let service = ProviderSettings(id: "check", baseURL: URL(string: "http://127.0.0.1:1")!, requiresAPIKey: false,
                                   models: [ProviderModelSettings(id: "pinned", label: "pinned")])
    let settings = HostSettings(providers: [service], models: ModelSelection(stage1Model: "check:pinned", stage2Model: "check:pinned"))

    // Failure (1): an ordinary failed drawing shows only "生成できませんでした" instead of Web's pipelineAttentionText.
    let failing = AppModel(databaseURL: folder.appendingPathComponent("failing.sqlite"), transport: LeftoverFailingProvider())
    await failing.initialize()
    try await failing.updateHostSettings(settings)
    failing.display.preferences.language = "ja"
    failing.inputMode = "description"; failing.descriptionText = "A red circle above black dots scattered at the bottom"
    failing.seedText = "42"; failing.sketchMode = "off"; failing.catalogMode = "fixed"; failing.catalogID = "default"
    await failing.generate()
    let expectedFailure = "処理の結果を確認してください。 理由: 記述の解釈を完了できませんでした（モデルに接続できませんでした。4回試しました）"
        + " 詳細: 指示書生成処理・処理中に接続が失われました（生成要求、NSURLErrorDomain -1005、transport_unavailable）。"
    guard failing.status == expectedFailure else {
        throw CheckFailure.message("Failed drawing status differs from Web: \(failing.status)")
    }

    // Failure (2, 3): the demo interval stops at 999 s, or the demo draws with the app's wild switch.
    failing.wild = true
    let demo = try ExactJSON(data: failing.requestForDemoDescription("A red circle", sketchMode: "off").renderOptions)
    guard demo["wild"].bool == false, try lines("Views/AutomationView.swift").contains(where: { $0.contains("in: 1...3600)") }) else {
        throw CheckFailure.message("Demo must draw with wild off and allow 3600 s: wild \(demo["wild"])")
    }

    // Failure (4): the fetched-list message is the native count instead of the Web's notice.
    guard ServerTips.text("settingsModelFetchModelsSaved", language: "ja") == "モデルリストを取得しました。",
          try lines("Views/ModelSettingsDialogs.swift").contains(where: { $0.contains("webCopy(\"settingsModelFetchModelsSaved\"") }) else {
        throw CheckFailure.message("Model list fetch must say the Web's settingsModelFetchModelsSaved")
    }

    // Failure (5): a ChatGPT plan failure reads "ChatGPTプラン: code（action）" instead of Web chatgptStatus(code).
    let chatGPTSources = try lines("AppModel.swift") + lines("ChatGPTPlanSettingsModel.swift")
    guard ChatGPTStatusCopy.text("chatgpt_quota", language: "ja") == "プラン利用の上限に達しました。利用枠を確認してください。",
          ChatGPTStatusCopy.text("chatgpt_refused", language: "en") == "ChatGPT declined the request. Revise your description.",
          ChatGPTStatusCopy.text("chatgpt_unknown", language: "ja") == "ChatGPT接続を確認してください。",
          !chatGPTSources.contains(where: { $0.contains("ChatGPTプラン: \\(") }) else {
        throw CheckFailure.message("ChatGPT failure wording differs from Web chatgptStatus")
    }

    // Failure (6): a comment-only line is sent as a batch row, or a row loses the line it was written on.
    let batchFolder = folder.appendingPathComponent("batch", isDirectory: true)
    try FileManager.default.createDirectory(at: batchFolder, withIntermediateDirectories: true)
    let batchApp = AppModel(databaseURL: batchFolder.appendingPathComponent("inku.sqlite"), transport: LeftoverFailingProvider())
    await batchApp.initialize()
    try await batchApp.updateHostSettings(settings)
    batchApp.seedText = "42"; batchApp.catalogMode = "fixed"; batchApp.catalogID = "default"
    let automation = AutomationModel()
    await automation.connect(app: batchApp)
    automation.batchSketchMode = "off"
    automation.restoreBatchInput("[コメントだけ]\n赤い円\n\n1. \n青い四角 [注]")
    await automation.startBatch(app: batchApp)
    let reconnected = AutomationModel()
    await reconnected.connect(app: batchApp)
    guard automation.rows.map(\.line) == [2, 5], automation.rows.map(\.input) == ["赤い円", "青い四角 [注]"],
          reconnected.rows.map(\.line) == [2, 5] else {
        throw CheckFailure.message("Batch rows differ from Web numberedBatchLines: \(automation.rows.map(\.line)) / \(reconnected.rows.map(\.line))")
    }

    // Failure (7): the fork of a DDL-edited work starts an unrelated work, or a reworded description slips past the lock.
    let forkURL = folder.appendingPathComponent("fork.sqlite")
    let provider = LeftoverDrawingProvider()
    let app = AppModel(databaseURL: forkURL, transport: provider)
    await app.initialize()
    try await app.updateHostSettings(settings)
    app.inputMode = "description"; app.descriptionText = "a red circle in an open field"
    app.seedText = "42"; app.sketchMode = "off"; app.catalogMode = "fixed"; app.catalogID = "default"
    await app.generate()
    guard app.errorText == nil, let parent = app.selectedWork,
          await app.drawEditedDDL(work: parent, source: "place one blue circle at center."),
          let held = app.selectedWork, held.id != parent.id else {
        throw CheckFailure.message("Fork fixture did not draw: \(app.errorText ?? app.status)")
    }
    await app.selectWork(held)
    guard app.sourceLocked, app.canForkDescription else { throw CheckFailure.message("A DDL-edited work must offer the fork") }
    do {
        _ = try app.requestForCurrentInput(description: "a blue square", parentWorkID: held.id, derivationKind: "description_edit")
        throw CheckFailure.message("A reworded description was accepted under a held parent")
    } catch let error as HostError where error.code == "description_source_locked" { }
    await app.forkDescription()
    let database = try InkuDatabase(url: forkURL)
    guard app.errorText == nil, let forked = app.selectedWork, forked.id != held.id, !app.sourceLocked,
          forked.effectiveSourceText == held.effectiveSourceText, forked.ddl != held.ddl,
          let edge = try await database.edge(childNodeID: forked.lineageNodeID ?? ""),
          edge.parentNodeID == held.lineageNodeID, edge.derivationKind == "description_edit" else {
        throw CheckFailure.message("Fork is not a description_edit child of the held work: \(app.errorText ?? app.status)")
    }
    let calls = await provider.calls
    var reworded = try app.requestForCurrentInput(description: "a blue square")
    reworded.parentWorkID = held.id; reworded.derivationKind = "description_edit"; reworded.description = "a blue square"
    do {
        _ = try await PipelineHost(database: database, transport: provider).generate(reworded)
        throw CheckFailure.message("The host drew a reworded description under a held parent")
    } catch let error as HostError where error.code == "description_source_locked" { }
    guard await provider.calls == calls else { throw CheckFailure.message("The refused request reached the provider") }

    // Failure (8): a comparison model that is no longer offered stays in the saved choice until a checkbox moves.
    app.display.preferences.comparisonModels = ["check:pinned", "gone:model"]
    try await app.updateHostSettings(settings)
    guard app.display.preferences.comparisonModels == ["check:pinned"] else {
        throw CheckFailure.message("Saved comparison models kept an unavailable one: \(app.display.preferences.comparisonModels ?? [])")
    }

    let table = counts.keys.sorted().map { component -> String in
        let row = counts[component]!
        return "\(component) \(row.equal)/\(row.missing)/\(row.excluded)"
    }
    print("Tooltips and leftovers passed: 173 Web tooltip sites compared — \(equal) equal, 0 missing, \(excluded) excluded "
          + "(per component equal/missing/excluded: \(table.joined(separator: ", "))); \(bubbles) inkuTooltip calls, "
          + "9 menu-item .help; 4 placements inside the window; switch copy and off state; failed status text; demo wild off "
          + "and 3600 s; fetch notice; 3 chatgptStatus strings; batch rows [2, 5] kept after reconnect; fork edge and 2 refusals; "
          + "comparison choice pruned. Temporary SQLite and offline provider mocks only.")
}

private actor LeftoverFailingProvider: ObservedProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        throw HostError("observation_check_requires_observed_transport")
    }
    func performObserved(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                         observation: ProviderObservationOptions, willSend: @escaping ProviderObservationHandler,
                         didFinish: @escaping ProviderObservationHandler, onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let input = try ExactJSON(data: action)
        let tag = try input.requiredString("tag")
        guard let stage = ProviderObservationStage(action: tag), let timeout = input["timeout_ms"].string.flatMap(UInt64.init) else {
            throw HostError("invalid_leftover_action")
        }
        var metric = ProviderAttemptMetric(identity: try ProviderActionIdentity(action: action), action: tag, stage: stage,
            requestedModelReference: models.stage1Model, providerID: "check", model: "pinned", timeoutMS: timeout)
        try await willSend(.init(metric: metric))
        metric.diagnostic = .init(kind: .network, reason: "The connection to the provider was lost.", endpoint: "http://127.0.0.1:1",
            errorDomain: NSURLErrorDomain, errorCode: URLError.networkConnectionLost.rawValue, operation: .generation)
        metric.failure = "transport_unavailable"; metric.outcome = .failed; metric.elapsedMS = 1
        try await didFinish(.init(metric: metric))
        return ExactJSON.object(["tag": .string("provider_failed"), "identity": input["identity"],
                                 "elapsed_ms": .string("1"), "failure": .string("transport_unavailable")]).data
    }
}

private actor LeftoverDrawingProvider: ProviderTransport {
    private(set) var calls = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        let input = try ExactJSON(data: action)
        return ExactJSON.object(["tag": .string("normalized_ddl_generated"), "identity": input["identity"],
            "response": .string(#"{"normalized_ddl":"place one red circle at center."}"#), "elapsed_ms": .string("1")]).data
    }
}
