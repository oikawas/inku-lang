import Foundation
import OSLog

/// The host logs the core's cut record; it owns no model or response rules.
enum ProviderOutputLimit {
    private static let logger = Logger(subsystem: "app.inku", category: "provider")

    static func record(_ value: ExactJSON, kind: ProviderKind, responses: Bool) -> ExactJSON? {
        guard let format = try? ProviderWire.format(kind),
              let result = try? ProviderWire.readResponse(value.data, format: responses ? "openai_responses" : format),
              result["cut"].object != nil else { return nil }
        return result["cut"]
    }

    static func line(action: String, provider: String, model: String, outputBudget: ExactJSON, cut: ExactJSON) -> String {
        var fields = cut.object ?? [:]
        fields.merge(["action": .string(action), "provider": .string(provider), "model": .string(model),
                      "max_tokens": outputBudget]) { _, value in value }
        return "provider_output_limit " + ExactJSON.object(fields).text
    }

    static func log(_ result: ExactJSON, outputBudget: ExactJSON, provider: String, model: String, action: String) {
        guard result["cut"].object != nil else { return }
        let text = line(action: action, provider: provider, model: model, outputBudget: outputBudget, cut: result["cut"])
        logger.warning("\(text, privacy: .public)")
    }
}
