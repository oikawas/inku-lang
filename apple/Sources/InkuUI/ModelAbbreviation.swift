import Foundation
import InkuHost

/// How a saved model reference is named on screen, ported from the Build1162 Web functions:
/// `shortModelName`/`shortModel` (routes/+page.svelte), `abbreviateStripModel` (lib/historyStripFields.ts),
/// and `providerLabel`/`modelDisplayName`/`modelShortName`/`resolveModelRefForDisplay` (lib/models.ts).
/// The configured services take the place of the Server catalog; the bundled Server defaults fill the rest.
public struct ModelNaming: Sendable {
    /// Web `DEFAULT_PROVIDER`, the stage default of rule 3.
    public static let defaultProvider = "nvidia"

    private let connections: [ProviderSettings]
    private let stageDefault: String

    public init(providers: [ProviderSettings] = [], stageProvider: String = defaultProvider) {
        connections = providers
        stageDefault = stageProvider
    }

    private func displayResolution(_ reference: String, defaultProvider: String? = nil) -> [String: Any] {
        (try? ProviderCoreSettings.call("resolve_display", ["ref": reference,
            "providers": ProviderModelReference.referenceProviders(connections), "default_provider": defaultProvider ?? stageDefault])) ?? [:]
    }

    // MARK: models.ts

    /// The provider's own name, falling back to its id when the catalog has none.
    public func providerLabel(_ provider: String) -> String {
        guard !provider.isEmpty else { return "" }
        return displayResolution(provider + ":_", defaultProvider: provider)["provider_label"] as? String ?? provider
    }

    private func modelLabel(provider: String, model: String) -> String? {
        guard connections.contains(where: { $0.id == provider && $0.kind != .chatGPTPlan })
                || ProviderModelReference.retiredProviderIDs.contains(provider) || provider == "chatgpt" else { return model }
        return displayResolution(provider + ":" + model, defaultProvider: provider)["model_label"] as? String
    }

    /// Web `resolveModelRefForDisplay`: explicit qualification, sole ownership, retired ownership, then the stage default.
    public func resolve(_ reference: String, stageProvider: String = ModelNaming.defaultProvider) -> (provider: String, model: String) {
        let answer = displayResolution(reference, defaultProvider: stageProvider == Self.defaultProvider ? stageDefault : stageProvider)
        return (answer["provider"] as? String ?? stageProvider, answer["model"] as? String ?? reference)
    }

    /// Web `modelDisplayName`: "<provider> / <model label>".
    public func displayName(_ reference: String?) -> String {
        let ref = (reference ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !ref.isEmpty else { return "" }
        let (provider, model) = resolve(ref)
        let name = modelLabel(provider: provider, model: model) ?? model
        let owner = providerLabel(provider)
        return owner.isEmpty ? name : "\(owner) / \(name)"
    }

    /// Web `modelShortName`: the label without its provider and without a vendor prefix before the first slash.
    public func modelShortName(_ reference: String?) -> String {
        let ref = (reference ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !ref.isEmpty else { return "" }
        let (provider, model) = resolve(ref)
        let name = modelLabel(provider: provider, model: model) ?? model
        guard let slash = name.firstIndex(of: "/") else { return name }
        return String(name[name.index(after: slash)...])
    }

    // MARK: +page.svelte

    /// Web `shortModelName`: a known family word, otherwise the first 8 characters after the last slash.
    public static func shortModelName(_ model: String) -> String {
        for family in ["opus", "haiku", "sonnet", "qwen3", "qwen", "gemma"] where model.contains(family) { return family }
        return String((model.components(separatedBy: "/").last ?? model).prefix(8))
    }

    /// Web `shortModel`, the library card form: "<provider label>/<short name>".
    public func shortModel(_ reference: String?) -> String {
        guard let reference, !reference.isEmpty else { return "" }
        let (provider, model) = resolve(reference)
        let owner = providerLabel(provider)
        let short = Self.shortModelName(model)
        return owner.isEmpty ? short : "\(owner)/\(short)"
    }

    /// Web `historyModelStage1Short`, the history strip form.
    public func stripModel(_ reference: String?) -> String {
        guard let reference, !reference.isEmpty else { return "-" }
        return Self.abbreviateStripModel(owner: providerLabel(resolve(reference).provider), name: modelShortName(reference))
    }

    // MARK: historyStripFields.ts

    /// Web historyStripFields.ts: compact recognizable words while retaining versions, sizes and variants.
    public static func abbreviateStripModel(owner: String, name: String) -> String {
        func replace(_ text: String, _ pattern: String, _ replacement: String) -> String {
            text.replacingOccurrences(of: pattern, with: replacement, options: [.regularExpression, .caseInsensitive])
        }
        let provider = owner.range(of: "ollama.*cloud", options: [.regularExpression, .caseInsensitive]) != nil
            ? "Oc" : String(owner.trimmingCharacters(in: .whitespacesAndNewlines).prefix(2))
        var model = replace(name.trimmingCharacters(in: .whitespacesAndNewlines), "^.*/", "")
        model = replace(model, "^(?:anthropic|google|meta|mistral\\s+ai)\\s+", "")
        model = replace(model, "\\s*\\([\\d.]+\\s*[GM]B\\)\\s*$", "")
        model = replace(model, "\\bdeepseek[-\\s]+v(?=\\d)", "deepseek-")
        model = replacingMatches(model, pattern: "(?i)\\bq(\\d+)[_-]k[_-]([a-z])\\b") { match, text in
            let bits = Range(match.range(at: 1), in: text).map { String(text[$0]) } ?? ""
            let suffix = Range(match.range(at: 2), in: text).map { String(text[$0]).uppercased() } ?? ""
            return "Q" + bits + "K" + suffix
        }
        if owner.range(of: "^claude\\b", options: [.regularExpression, .caseInsensitive]) != nil { model = replace(model, "^claude[\\s-]+", "") }
        if owner.range(of: "^gemini\\b", options: [.regularExpression, .caseInsensitive]) != nil { model = replace(model, "^gemini[\\s-]+", "") }
        let tokens = model.components(separatedBy: CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: ":_-")))
            .filter { !$0.isEmpty }.map { token in
                replacingMatches(token, pattern: "(?i)[a-z]+") { match, text in
                    let word = Range(match.range, in: text).map { String(text[$0]) } ?? ""
                    return stripWords[word.lowercased()] ?? word
                }
            }
        var compact = ""
        for (index, token) in tokens.enumerated() {
            if index > 0, tokens[index - 1].last.map({ $0.isASCII && $0.isNumber }) == true,
               token.first.map({ $0.isASCII && $0.isNumber }) == true { compact += "·" }
            compact += token
        }
        return [provider, compact].filter { !$0.isEmpty }.joined(separator: " ")
    }

    private static let stripWords = [
        "gpt": "GPT", "oss": "oss", "sol": "So", "luna": "Lu", "astra": "As", "terra": "Te",
        "claude": "Cl", "sonnet": "So", "opus": "Op", "haiku": "Ha", "fable": "Fa",
        "gemini": "Ge", "gemma": "Gm", "flash": "Fl", "lite": "L", "pro": "Pr", "mini": "Mi", "nano": "Na", "turbo": "T",
        "llama": "Ll", "qwen": "Qw", "deepseek": "DS", "minimax": "MM", "kimi": "Ki",
        "mistral": "Mi", "ministral": "Min", "mixtral": "Mx", "nemotron": "Nem", "granite": "Gr",
        "large": "Lg", "medium": "Md", "small": "Sm", "super": "Su", "ultra": "Ul",
        "instruct": "I", "it": "I", "vision": "V", "reasoning": "R", "thinking": "Th",
        "preview": "Pv", "latest": "Lt", "code": "Cd", "coder": "Cdr", "a": "A", "b": "B", "e": "E"
    ]

    private static func replacingMatches(_ text: String, pattern: String, replacement: (NSTextCheckingResult, String) -> String) -> String {
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return text }
        var result = text
        for match in regex.matches(in: text, range: NSRange(text.startIndex..., in: text)).reversed() {
            if let range = Range(match.range, in: result) { result.replaceSubrange(range, with: replacement(match, text)) }
        }
        return result
    }

    // MARK: HistoryManager.svelte

    public struct Line: Sendable, Equatable {
        public enum Role: Sendable { case interpretation, drawing }
        public let role: Role?
        /// nil when the stage's model was not recorded.
        public let compact: String?
        public let full: String?
    }

    /// Web `modelLines`: one unlabeled line when both stages used the same model, otherwise one line per stage.
    public func cardLines(stage1: String?, stage2: String?) -> [Line] {
        func recorded(_ value: String?) -> String? {
            guard let value, !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
            return value
        }
        let interpretation = recorded(stage1), drawing = recorded(stage2)
        if let interpretation, interpretation == drawing {
            return [Line(role: nil, compact: shortModel(interpretation), full: displayName(interpretation))]
        }
        return [Line(role: .interpretation, compact: interpretation.map(shortModel), full: interpretation.map(displayName)),
                Line(role: .drawing, compact: drawing.map(shortModel), full: drawing.map(displayName))]
    }
}
