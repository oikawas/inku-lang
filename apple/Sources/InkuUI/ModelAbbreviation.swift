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

    public init(providers: [ProviderSettings] = []) {
        var seen = Set(providers.map(\.id))
        connections = providers + Self.bundledProviders.filter { seen.insert($0.id).inserted }
    }

    private static let bundledProviders: [ProviderSettings] = (try? BundledProviderDefaults.loadBundled()) ?? []

    /// Web `RETIRED_PROVIDER_GROUPS`: named, never routed.
    private static let retiredLabels = ["ovms": "Intel OVMS"]
    private static let retiredModels: [String: [String: String]] = [
        "ovms": ["qwen3-api": "Qwen3 8B Instruct", "qwen-api": "Qwen2.5 7B Instruct",
                 "gemma3-12b-api": "Google Gemma 3 12B Instruct", "gemma3-4b-api": "Google Gemma 3 4B Instruct"],
    ]

    // MARK: models.ts

    /// The provider's own name, falling back to its id when the catalog has none.
    public func providerLabel(_ provider: String) -> String {
        guard !provider.isEmpty else { return "" }
        if let label = connections.first(where: { $0.id == provider })?.label, !label.isEmpty { return label }
        return Self.retiredLabels[provider] ?? provider
    }

    private func modelLabel(provider: String, model: String) -> String? {
        if let connection = connections.first(where: { $0.id == provider }) {
            let models = connection.models ?? ModelGuidanceCatalog.bundled?.registeredModelSettings(for: connection) ?? []
            if let label = models.first(where: { $0.id == model })?.label, !label.isEmpty { return label }
        }
        return Self.retiredModels[provider]?[model]
    }

    private var knownProviders: Set<String> { Set(connections.map(\.id)).union(["chatgpt"]).union(Self.retiredLabels.keys) }

    private func owners(of model: String) -> Set<String> {
        Set(connections.filter { connection in
            connection.id != "chatgpt"
                && (connection.models ?? ModelGuidanceCatalog.bundled?.registeredModelSettings(for: connection) ?? []).contains { $0.id == model }
        }.map(\.id))
    }

    /// Web `resolveModelRefForDisplay`: explicit qualification, sole ownership, retired ownership, then the stage default.
    public func resolve(_ reference: String, stageProvider: String = ModelNaming.defaultProvider) -> (provider: String, model: String) {
        if let colon = reference.firstIndex(of: ":"), colon > reference.startIndex {
            let head = String(reference[..<colon])
            let rest = String(reference[reference.index(after: colon)...])
            if !rest.isEmpty, knownProviders.contains(head) { return (head, rest) }
        }
        let owned = owners(of: reference)
        if owned.count == 1, let only = owned.first { return (only, reference) }
        let retired = Self.retiredModels.filter { $0.value[reference] != nil }.map(\.key)
        if retired.count == 1 { return (retired[0], reference) }
        return (stageProvider, reference)
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

    /// The provider's first two characters, then the family (the word before the first number) and that number,
    /// three characters each. A name with no number prints its first word alone.
    public static func abbreviateStripModel(owner: String, name: String) -> String {
        let separators: (Character) -> Bool = { $0.isWhitespace || "-_/:".contains($0) }
        let words = name.trimmingCharacters(in: .whitespacesAndNewlines)
            .split(whereSeparator: separators)
            .flatMap(splitLetterDigit)
            .filter { !$0.isEmpty }
        let startsWithDigit: (String) -> Bool = { $0.first.map(isASCIIDigit) ?? false }
        let at = words.firstIndex(where: startsWithDigit)
        let family = at.map { $0 > 0 ? words[$0 - 1] : (words.first { !startsWithDigit($0) } ?? "") }
            ?? (words.first { !startsWithDigit($0) } ?? "")
        let version = at.map { words[$0] } ?? ""
        return [String(owner.trimmingCharacters(in: .whitespacesAndNewlines).prefix(2)), String(family.prefix(3)), String(version.prefix(3))]
            .filter { !$0.isEmpty }.joined(separator: " ")
    }

    /// `word.split(/(?<=[A-Za-z])(?=\d)/)`: "gemma4" is a family and a version run together.
    private static func splitLetterDigit(_ word: Substring) -> [String] {
        var parts: [String] = []
        var current = ""
        var previous: Character?
        for character in word {
            if let previous, isASCIILetter(previous), isASCIIDigit(character) { parts.append(current); current = "" }
            current.append(character)
            previous = character
        }
        parts.append(current)
        return parts
    }

    private static func isASCIILetter(_ character: Character) -> Bool { character.isASCII && character.isLetter }
    private static func isASCIIDigit(_ character: Character) -> Bool { character.isASCII && character.isNumber }

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
