import Foundation
import InkuHost
import InkuPersistence
import InkuUI

/// Host-side Server parity (Build1162) that needs the bundled Bootstrap or a whole failed run. Offline, temporary DB only.
@MainActor
func runServerHostParityChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-server-host-parity-" + UUID().uuidString)
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }

    // Failure (D13): every auto candidate for the default catalog says catalog_mode "default"; Server marks it so
    // only when default is the chosen catalog (the candidate shares the host it mutates).
    let app = AppModel(databaseURL: folder.appendingPathComponent("catalog.sqlite"), transport: ParityFailingProvider(mode: .network))
    await app.initialize()
    guard app.errorText == nil, let other = app.catalogs.first(where: { $0.id != "default" }) else {
        throw CheckFailure.message("Server host parity could not load the bundled catalogs: \(app.errorText ?? app.status)")
    }
    let service = ProviderSettings(id: "check", baseURL: URL(string: "http://127.0.0.1:1")!, requiresAPIKey: false,
                                   models: [ProviderModelSettings(id: "pinned", label: "pinned")])
    try await app.updateHostSettings(HostSettings(providers: [service], models: ModelSelection(stage1Model: "check:pinned", stage2Model: "check:pinned")))
    app.inputMode = "description"; app.descriptionText = "A red circle above black dots scattered at the bottom"
    app.seedText = "42"; app.sketchMode = "off"; app.catalogMode = "auto"
    var modes: [String: (host: String?, candidate: String?)] = [:]
    for chosen in ["default", other.id] {
        app.catalogID = chosen
        let config = try ExactJSON(data: app.requestForCurrentInput().configuration)
        let candidate = config["catalogs"].array?.first { $0["prompt"]["catalog_id"].string == "default" }
        modes[chosen] = (config["compiler"]["host"]["catalog_mode"].string, candidate?["resolved"]["catalog_mode"].string)
    }
    guard modes["default"]?.host == "default", modes["default"]?.candidate == "default",
          modes[other.id]?.host == "explicit", modes[other.id]?.candidate == "explicit" else {
        throw CheckFailure.message("Auto catalog modes differ from Server: \(modes)")
    }

    // Failure (D16): a failed drawing shows the native wording ("サービスが要求を拒否しました", "試行N") instead of
    // Web's pipelineAttentionText; the native diagnosis must stay as details.
    app.catalogMode = "fixed"; app.catalogID = "default"
    app.display.preferences.language = "ja"
    // The automation path (batch, demo, autonomous refinement) is where the native message is composed today.
    _ = await app.runAutomation(request: try app.requestForCurrentInput())
    let network = app.automationFailureMessage
    let expectedNetwork = "処理の結果を確認してください。 理由: 記述の解釈を完了できませんでした（モデルに接続できませんでした。4回試しました）"
        + " 詳細: 指示書生成処理・処理中に接続が失われました（生成要求、NSURLErrorDomain -1005、transport_unavailable）。"
    let keyless = AppModel(databaseURL: folder.appendingPathComponent("keyless.sqlite"), transport: ParityFailingProvider(mode: .credentials))
    await keyless.initialize()
    try await keyless.updateHostSettings(HostSettings(providers: [service], models: ModelSelection(stage1Model: "check:pinned", stage2Model: "check:pinned")))
    keyless.inputMode = "description"; keyless.descriptionText = app.descriptionText
    keyless.seedText = "42"; keyless.sketchMode = "off"; keyless.catalogMode = "fixed"
    keyless.display.preferences.language = "en"
    _ = await keyless.runAutomation(request: try keyless.requestForCurrentInput())
    let expectedKeyless = "Review the result of this operation. Reason: the description could not be interpreted (the model has no API key)"
        + " Details: DDL generation processing: The provider credential was unavailable (request preparation; credentials_unavailable; provider_rejected)."
    guard network == expectedNetwork, keyless.automationFailureMessage == expectedKeyless else {
        throw CheckFailure.message("Failure wording differs from Web: \(network ?? "nil") / \(keyless.automationFailureMessage ?? "nil")")
    }
    print("Server host parity passed: auto catalog_mode default only when chosen (2 selections); failed-run wording follows Web with native details (network, 4 attempts; missing key, 1 attempt). Temporary DB only, no provider sends.")
}

private actor ParityFailingProvider: ObservedProviderTransport {
    enum Mode { case network, credentials }
    let mode: Mode
    init(mode: Mode) { self.mode = mode }
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
            throw HostError("invalid_server_host_parity_action")
        }
        var metric = ProviderAttemptMetric(identity: try ProviderActionIdentity(action: action), action: tag, stage: stage,
            requestedModelReference: models.stage1Model, providerID: "check", model: "pinned", timeoutMS: timeout)
        try await willSend(.init(metric: metric))
        let failure: String
        switch mode {
        case .network:
            failure = "transport_unavailable"
            metric.diagnostic = .init(kind: .network, reason: "The connection to the provider was lost.", endpoint: "http://127.0.0.1:1",
                errorDomain: NSURLErrorDomain, errorCode: URLError.networkConnectionLost.rawValue, operation: .generation)
        case .credentials:
            failure = "provider_rejected"
            metric.diagnostic = .init(kind: .host, reason: "The provider credential is unavailable.", endpoint: "http://127.0.0.1:1",
                errorDomain: "InkuHost", hostCode: "credentials_unavailable", operation: .preparation)
        }
        metric.failure = failure; metric.outcome = .failed; metric.elapsedMS = 1
        try await didFinish(.init(metric: metric))
        return ExactJSON.object(["tag": .string("provider_failed"), "identity": input["identity"],
                                 "elapsed_ms": .string("1"), "failure": .string(failure)]).data
    }
}
