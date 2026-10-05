import Foundation

extension GenerationRequest {
    /// Normalize only this operation's copy. Saved configuration and a frozen
    /// batch journal remain readable without rewriting either record.
    func normalizedForNewWork() throws -> Self {
        guard derivationKind != "variation" else { throw HostError("variation_retired") }
        var result = self
        if retainedDocument == nil, !authoring.isDirect || parentWorkID == nil {
            result.models = models.normalizedForNewWork(stage2Only: authoring.isDirect)
        }
        var config = try ExactJSON(data: configuration)
        var compiler = try config.requiredObject("compiler").object!
        compiler.removeValue(forKey: "stage15_variation")
        let composition = compiler["composition_seed"] ?? .null
        try Self.validateSeed(composition, required: false, code: "invalid_composition_seed")
        config["compiler"] = .object(compiler)
        var options = try ExactJSON(data: renderOptions)
        try Self.validateSeed(options["render_seed"], required: true, code: "invalid_render_seed")
        let suppliedComposition = options["composition_seed"]
        try Self.validateSeed(suppliedComposition, required: false, code: "invalid_composition_seed")
        guard suppliedComposition == composition else { throw HostError("composition_seed_mismatch") }
        options["composition_seed"] = composition
        result.configuration = config.data; result.renderOptions = options.data
        return result
    }

    private static func validateSeed(_ value: ExactJSON, required: Bool, code: String) throws {
        if value == .null, !required { return }
        guard let text = value.string, let number = UInt64(text), String(number) == text else {
            throw HostError(code)
        }
    }
}
