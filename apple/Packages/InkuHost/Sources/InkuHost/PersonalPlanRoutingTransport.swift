import Foundation

/// The pinned method is additive; existing ordinary provider transports remain source compatible.
public protocol ChatGPTPlanEffectTransport: ProviderTransport {
    func performPersonalPlan(action: Data, models: ModelSelection, providers: [ProviderSettings],
                             session: ChatGPTPlanSession?, argumentLimit: Int, credentials: any CredentialStore,
                             onBytes: @escaping @Sendable (Int) -> Void,
                             onDiagnostic: @escaping @Sendable (ChatGPTPlanDiagnostic) -> Void) async throws -> Data
}

public final class PersonalPlanRoutingTransport: ChatGPTPlanEffectTransport, AuxiliaryTransport, Sendable {
    private let ordinary: any ProviderTransport
    public let runtime: ChatGPTPlanRuntime
    public init(ordinary: any ProviderTransport, runtime: ChatGPTPlanRuntime) { self.ordinary = ordinary; self.runtime = runtime }

    public static func isPersonal(_ reference: String, providers: [ProviderSettings]) -> Bool {
        if reference == "chatgpt" || reference.hasPrefix("chatgpt:") { return true }
        return (try? personalModel(reference, providers: providers)) != nil
    }
    /// Matches the ordinary resolver's explicit service ID and one-provider bare-model rules.
    public static func personalModel(_ reference: String, providers: [ProviderSettings]) throws -> String? {
        if let colon = reference.firstIndex(of: ":") {
            let id = String(reference[..<colon]), model = String(reference[reference.index(after: colon)...])
            guard id == "chatgpt" || providers.contains(where: { $0.id == id && $0.kind == .chatGPTPlan }) else { return nil }
            guard let provider = providers.first(where: { $0.id == id && $0.kind == .chatGPTPlan }), !model.isEmpty else { throw HostError("chatgpt_provider_selection_required") }
            try provider.validate(); return model
        }
        if reference == "chatgpt" { throw HostError("chatgpt_provider_selection_required") }
        if providers.count == 1, providers[0].kind == .chatGPTPlan, !reference.isEmpty {
            try providers[0].validate(); return reference
        }
        return nil
    }
    public func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                        onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let effect = try ExactJSON(data: action)
        let reference = effect["tag"].string == "complete_visible_ddl_holes" ? models.stage2Model : models.stage1Model
        guard try Self.personalModel(reference, providers: providers) == nil else {
            throw HostError("chatgpt_session_pin_required")
        }
        return try await ordinary.perform(action: action, models: models, providers: providers, credentials: credentials, onBytes: onBytes)
    }
    public func performPersonalPlan(action: Data, models: ModelSelection, providers: [ProviderSettings], session: ChatGPTPlanSession?,
                                    argumentLimit: Int, credentials: any CredentialStore,
                                    onBytes: @escaping @Sendable (Int) -> Void,
                                    onDiagnostic: @escaping @Sendable (ChatGPTPlanDiagnostic) -> Void) async throws -> Data {
        let effect = try ExactJSON(data: action)
        let reference = effect["tag"].string == "complete_visible_ddl_holes" ? models.stage2Model : models.stage1Model
        guard let model = try Self.personalModel(reference, providers: providers) else {
            return try await perform(action: action, models: models, providers: providers, credentials: credentials, onBytes: onBytes)
        }
        guard let session else {
            throw HostError("chatgpt_session_pin_required")
        }
        let began = Date()
        var result: ExactJSON = .object(["identity": try effect.requiredObject("identity")])
        let results = ["generate_sketch": "sketch_generated", "select_description_catalog": "description_catalog_selected",
            "generate_normalized_ddl": "normalized_ddl_generated", "complete_visible_ddl_holes": "visible_ddl_hole_patch_generated"]
        guard let resultTag = results[try effect.requiredString("tag")] else { throw HostError("chatgpt_operation_not_supported") }
        do {
            let answer = try await runtime.perform(action: action, session: session,
                model: model, argumentLimit: argumentLimit, onBytes: onBytes)
            result["tag"] = .string(resultTag); result["response"] = .string(answer)
        } catch is CancellationError { throw CancellationError() }
        catch {
            if Task.isCancelled { throw CancellationError() }
            let diagnostic = ChatGPTPlanRuntime.diagnostic(error)
            onDiagnostic(diagnostic)
            result["tag"] = .string("provider_failed"); result["failure"] = .string(diagnostic.pipelineFailure)
        }
        result["elapsed_ms"] = .string(String(max(0, Int64(Date().timeIntervalSince(began) * 1000))))
        return result.data
    }
    public func performAuxiliary(prompt: AuxiliaryPrompt, modelReference: String, settings: HostSettings, credentials: any CredentialStore,
                                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> String {
        if try Self.personalModel(modelReference, providers: settings.providers) != nil { throw HostError("chatgpt_operation_not_supported") }
        guard let auxiliary = ordinary as? any AuxiliaryTransport else { throw HostError("auxiliary_transport_unavailable") }
        return try await auxiliary.performAuxiliary(prompt: prompt, modelReference: modelReference, settings: settings, credentials: credentials, onBytes: onBytes)
    }
}
