import Foundation
import InkuPersistence

public struct AuxiliaryPrompt: Sendable, Equatable {
    public enum Purpose: Sendable { case demo, vision }
    public let system: String
    public let message: String
    public let images: [String]
    public let temperature: Double
    public let maximumTokens: Int
    public let timeoutSeconds: Double
    public let purpose: Purpose

    public init(system: String, message: String, images: [String] = [], temperature: Double,
                maximumTokens: Int, timeoutSeconds: Double = 180, purpose: Purpose = .vision) {
        self.system = system; self.message = message; self.images = images
        self.temperature = temperature; self.maximumTokens = maximumTokens
        self.timeoutSeconds = timeoutSeconds; self.purpose = purpose
    }
}

public protocol AuxiliaryTransport: Sendable {
    func performAuxiliary(prompt: AuxiliaryPrompt, modelReference: String, settings: HostSettings,
                          credentials: any CredentialStore,
                          onBytes: @escaping @Sendable (Int) -> Void) async throws -> String
}

extension URLSessionProviderTransport: AuxiliaryTransport {}

public struct AuxiliaryAdvice: Codable, Sendable, Equatable {
    public let observation: String
    public let nextDirection: String
    public let suggestedKind: String
    public let model: String
}

public typealias ColophonDraft = ColophonRecord

/// The auxiliary reader never mutates a work or selects a preferred generation.
public actor AuxiliaryProvider {
    public static let allowedKinds = ["reinterpretation", "catalog_change", "layout_change", "touch_change", "variation"]
    private let transport: any AuxiliaryTransport
    private let credentials: any CredentialStore
    private var observationsCache: [(key: String, at: Date, response: String)] = []

    public init(transport: any AuxiliaryTransport = URLSessionProviderTransport(),
                credentials: any CredentialStore = KeychainCredentialStore()) {
        self.transport = transport; self.credentials = credentials
    }

    public func demoInstruction(seedPhrase: String, modelReference: String? = nil, language: String,
                                settings: HostSettings) async throws -> String {
        guard !seedPhrase.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw HostError("empty_demo_seed") }
        let model = try Self.model(modelReference, settings: settings)
        let prompt = AuxiliaryPrompt(system: Self.demoSystem(language), message: seedPhrase, temperature: 0.9,
                                     maximumTokens: 180, timeoutSeconds: 120, purpose: .demo)
        let raw = try await transport.performAuxiliary(prompt: prompt, modelReference: model,
                                                      settings: settings, credentials: credentials, onBytes: { _ in })
        try Task.checkCancellation()
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "\"'“”‘’"))
        guard !text.isEmpty else { throw HostError("empty_demo_instruction") }
        return text
    }

    public func refineAdvice(instruction: String, direction: String, enabledKinds: [String], png: Data,
                             modelReference: String? = nil, language: String, settings: HostSettings) async throws -> AuxiliaryAdvice {
        let kinds = enabledKinds.filter(Self.allowedKinds.contains)
        guard !kinds.isEmpty, enabledKinds.allSatisfy(Self.allowedKinds.contains),
              !instruction.isEmpty, instruction.unicodeScalars.count <= 100_000,
              direction.unicodeScalars.count <= 2000, png.starts(with: [137, 80, 78, 71, 13, 10, 26, 10]) else {
            throw HostError("invalid_refinement_advice_request")
        }
        let model = try Self.model(modelReference, settings: settings)
        let payload: ExactJSON = .object([
            "instruction": .string(instruction), "user_direction": .string(direction),
            "allowed_suggested_kinds": .array(kinds.map(ExactJSON.string)),
            "constraints": .object(["no_score": .bool(true), "no_ranking": .bool(true),
                                    "no_accept_reject": .bool(true), "human_makes_final_choice": .bool(true)])])
        let message = (language == "en" ? "Observe this generation and return bounded refinement advice. Context:\n"
                       : "この世代を観察し、限定された推敲助言を返してください。文脈:\n") + payload.text
        let prompt = AuxiliaryPrompt(system: Self.adviceSystem(language), message: message,
                                     images: [Self.imageURL(png)], temperature: 0.35, maximumTokens: 320)
        let raw = try await transport.performAuxiliary(prompt: prompt, modelReference: model,
                                                      settings: settings, credentials: credentials, onBytes: { _ in })
        try Task.checkCancellation()
        return try Self.parseAdvice(raw, kinds: kinds, model: model)
    }

    /// Reads each prefix before the next one exists in a prompt, including deleted nodes.
    public func colophon(branch: LineageGraph, modelReference: String? = nil, language: String,
                         settings: HostSettings,
                         png: @escaping @Sendable ([String]) async throws -> Data?) async throws -> ColophonDraft {
        guard branch.pathOnly, let target = branch.nodes.last, target.id == branch.focusNodeID,
              !branch.nodes.isEmpty else { throw HostError("colophon_requires_root_path") }
        let model = try Self.model(modelReference, settings: settings)
        let at = Int64(Date().timeIntervalSince1970 * 1000)
        let facts = try Self.factSheet(branch)
        let generations = facts["generations"].array!
        var observations: [String] = []
        for (index, node) in branch.nodes.enumerated() {
            try Task.checkCancellation()
            let request: ExactJSON = .object([
                "generation_index": .integer(index), "known_generations": .array(Array(generations.prefix(index + 1))),
                "prior_observations": .array(observations.map(ExactJSON.string)), "current": generations[index]])
            var svgs: [String] = []
            if index > 0, let previous = branch.nodes[index - 1].work?.svg, !previous.isEmpty { svgs.append(previous) }
            if let current = node.work?.svg, !current.isEmpty { svgs.append(current) }
            let image = try await png(svgs)
            try Task.checkCancellation()
            let images = image.map { [Self.imageURL($0)] } ?? []
            let message = Self.generationMessage(request, language: language, hasImage: !images.isEmpty)
            let observation = try await cachedRead(prompt: AuxiliaryPrompt(system: Self.colophonSystem(language),
                message: message, images: images, temperature: 0.35, maximumTokens: 260),
                model: model, language: language, settings: settings)
            try Task.checkCancellation()
            observations.append(Self.firstPerson(observation, language: language))
        }
        let invariantPrompt = Self.invariantMessage(facts["invariants"], language: language)
        let conclusion = try await cachedRead(prompt: AuxiliaryPrompt(system: Self.colophonSystem(language),
            message: invariantPrompt, temperature: 0.35, maximumTokens: 260), model: model,
            language: language, settings: settings)
        try Task.checkCancellation()
        let formatter = DateFormatter(); formatter.dateFormat = "yyyy-MM-dd"
        formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.timeZone = TimeZone(identifier: "Asia/Tokyo")
        let date = formatter.string(from: Date(timeIntervalSince1970: Double(at) / 1000))
        let signature = language == "en" ? "Reader: \(model) / \(date)" : "読み手: \(model) / \(date)"
        let body = (observations + [Self.firstPerson(conclusion, language: language), signature]).joined(separator: "\n\n")
        return ColophonDraft(id: UUID().uuidString, targetNodeID: target.id, branchSnapshot: branch.nodes.map(\.id),
            model: model, at: at, language: language, generatedBody: body, adoptedBody: nil,
            signature: signature, warnings: Self.evaluationWarnings(body, language: language), factSheetJSON: facts.text)
    }

    private func cachedRead(prompt: AuxiliaryPrompt, model: String, language: String, settings: HostSettings) async throws -> String {
        // Requests include only public configuration, never a key or another branch's future.
        let key = model + "\n" + language + "\n" + prompt.system + "\n" + prompt.message + "\n" + prompt.images.joined(separator: "\n")
            + "\n" + settings.providers.map { $0.id + ":" + $0.baseURL.absoluteString }.joined(separator: "\n")
        observationsCache.removeAll { Date().timeIntervalSince($0.at) > 1800 }
        if let cached = observationsCache.first(where: { $0.key == key }) { return cached.response }
        let response = try await transport.performAuxiliary(prompt: prompt, modelReference: model,
            settings: settings, credentials: credentials, onBytes: { _ in })
        try Task.checkCancellation()
        if !response.isEmpty {
            observationsCache.append((key, Date(), response))
            if observationsCache.count > 256 { observationsCache.removeFirst(observationsCache.count - 256) }
        }
        return response
    }

    private static func model(_ explicit: String?, settings: HostSettings) throws -> String {
        let model = (explicit ?? "").isEmpty ? settings.models.stage1Model : explicit!
        guard !model.isEmpty else { throw HostError("provider_selection_required") }
        return model
    }
    private static func imageURL(_ png: Data) -> String { "data:image/png;base64," + png.base64EncodedString() }

    public static func parseAdvice(_ raw: String, kinds: [String], model: String) throws -> AuxiliaryAdvice {
        let body: Substring
        if let first = raw.firstIndex(of: "{"), let last = raw.lastIndex(of: "}"), first < last { body = raw[first...last] }
        else { body = Substring(raw) }
        let parsed = try ExactJSON(data: Data(body.utf8))
        guard parsed.object != nil, let firstKind = kinds.first else { throw HostError("invalid_refinement_advice") }
        let observation = (parsed["observation"].string ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let direction = (parsed["next_direction"].string ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let suggested = (parsed["suggested_kind"].string ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !observation.isEmpty, !direction.isEmpty else { throw HostError("empty_refinement_advice") }
        return AuxiliaryAdvice(observation: scalarPrefix(observation, 2000), nextDirection: scalarPrefix(direction, 2000),
                               suggestedKind: kinds.contains(suggested) ? suggested : firstKind, model: model)
    }

    private static func scalarPrefix(_ text: String, _ length: Int) -> String {
        String(String.UnicodeScalarView(text.unicodeScalars.prefix(length)))
    }

    public static func demoSystem(_ language: String) -> String {
        language == "en"
            ? "Generate one short, concrete visual prompt for inku. Return only the prompt text. Keep it under 40 words. Use sensory detail and a clear scene, but do not explain."
            : "inkuのデモ描画に使う短い指示文を1つ生成してください。返答は指示文のみ。40語以内。情景、質感、動きが感じられる具体的な文章にし、説明は不要です。"
    }

    public static func adviceSystem(_ language: String) -> String {
        language == "en"
            ? "You are a visual adviser in a bounded artwork-refinement loop. Observe only visible facts and alignment with the supplied instruction. Never score, rank, accept, reject, praise, or condemn. Suggest one concrete direction to try next without claiming it is better. Return JSON only with observation, next_direction, and suggested_kind."
            : "あなたは世代数を限定した作品推敲ループの視覚的助言者です。画像に見える事実と、与えられた指示との対応だけを観察してください。点数、順位、合否、称賛、否定を行わず、より良いと断定せずに次に試す具体的な方向を一つ提案してください。observation、next_direction、suggested_kindを持つJSONだけを返してください。"
    }

    public static func colophonSystem(_ language: String) -> String {
        language == "en"
            ? "You are a first-person reader of an artwork lineage. Describe only visible, observable changes. Use 'I see' or 'it appears to me'. Never score, rank, recommend, praise, condemn, infer authorial intent or emotion, or describe this generation as progress toward a later result. Captions are context only: never quote, paraphrase, or narrate them. Name concrete shapes, colors, positions, density, and movement. Return one short paragraph only."
            : "あなたは作品系譜を読む一人称の鑑賞者です。見える物理と観察できる変化だけを、「私には〜と見える」「私は〜と読んだ」の形で述べてください。評価、点数、順位、推薦、作者の意図や感情の断定、後の完成へ向かう目的論を含めないでください。詞書は補助情報に限り、引用・言い換え・物語化をせず、形、色、位置、密度、動きの見える差を具体的に述べ、短い一段落だけを返してください。"
    }

    private static func generationMessage(_ request: ExactJSON, language: String, hasImage: Bool) -> String {
        let paired = hasImage && (request["generation_index"].number.flatMap(Int.init) ?? 0) > 0
        if language == "en" {
            return (paired ? "The image places the previous generation on the left and the current generation on the right. Describe their visible difference."
                    : "The image is the current generation. Describe only its visible physical features.")
                + "\nFacts available up to this generation:\n" + request.text
        }
        return (paired ? "画像は左が前世代、右が現世代です。両者の見える差を読んでください。"
                : "画像は現世代です。見える物理だけを読んでください。") + "\n現在までに知り得る事実:\n" + request.text
    }

    private static func invariantMessage(_ invariants: ExactJSON, language: String) -> String {
        (language == "en"
         ? "In one first-person paragraph, verbalize only the following mechanically computed invariants. Do not add causality, intent, evaluation, scores, or a story of progress. Facts:\n"
         : "次の機械抽出された不変量だけを、一人称の短い結びとして言語化してください。因果、意図、評価、点数、進歩の物語を加えないでください。\n") + invariants.text
    }

    private static func firstPerson(_ text: String, language: String) -> String {
        var clean = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let echoed = ["画像は左が前世代、右が現世代です。両者の見える差を読んでください。", "画像は現世代です。見える物理だけを読んでください。",
                      "The image places the previous generation on the left and the current generation on the right. Describe their visible difference.",
                      "The image is the current generation. Describe only its visible physical features."]
        if let prefix = echoed.first(where: clean.hasPrefix) { clean = String(clean.dropFirst(prefix.count)).trimmingCharacters(in: .whitespacesAndNewlines) }
        if clean.isEmpty { clean = language == "en" ? "no visible difference could be identified." : "見える差を特定できなかった。" }
        if language == "en" {
            return clean.range(of: "\\bI\\b|\\bme\\b|\\bmy\\b", options: [.regularExpression, .caseInsensitive]) != nil ? clean : "I see " + clean
        }
        return clean.contains("私") || clean.contains("わたし") ? clean : "私には、" + clean
    }

    public static func evaluationWarnings(_ body: String, language: String) -> [String] {
        let words = language == "en" ? ["good", "beautiful", "successful", "failure", "refined", "superior", "inferior", "best", "worst", "perfect"]
            : ["良い", "美しい", "成功", "失敗", "洗練", "優れ", "劣る", "最高", "最悪", "完成"]
        var warnings = words.filter { body.lowercased().contains($0.lowercased()) }.map { "evaluation_word:" + $0 }
        if body.range(of: "\\b\\d+(?:\\.\\d+)?\\s*(?:/|点|stars?|score)", options: [.regularExpression, .caseInsensitive]) != nil {
            warnings.append("numeric_evaluation")
        }
        return warnings
    }

    private static let featureSets = ["primitives", "colors", "densities", "angles", "arrangement_paths", "score_elements"]

    public static func factSheet(_ branch: LineageGraph) throws -> ExactJSON {
        var generations: [ExactJSON] = []
        for (index, item) in branch.nodes.enumerated() {
            let features = try item.work.map { try instructionFeatures(ExactJSON(data: Data($0.score.utf8))) }
            let caption = item.work.map { ($0.sourceText?.isEmpty == false ? $0.sourceText : nil) ?? $0.input }
            var generation: ExactJSON = .object([
                "index": .integer(index), "node_id": .string(item.id), "state": .string(item.node.state),
                "at": .integer(item.node.at), "child_count": .integer(item.childCount),
                "branch_split": .bool(item.childCount > 1), "caption": .optional(caption), "features": features ?? .null])
            if index > 0, let edge = branch.edges.first(where: { $0.childNodeID == item.id }) {
                generation["derivation"] = .object(["kind": .string(edge.derivationKind),
                                                    "metadata": try ExactJSON(data: Data(edge.metadataJSON.utf8))])
                if let features, generations[index - 1]["features"].object != nil {
                    generation["feature_delta"] = delta(generations[index - 1]["features"], features)
                }
            }
            generations.append(generation)
        }
        let available = generations.map { $0["features"] }.filter { $0.object != nil }
        var invariants: ExactJSON = .object([:])
        if let first = available.first {
            if available.allSatisfy({ $0["composition_family"] == first["composition_family"] }) {
                invariants["composition_family"] = first["composition_family"]
            }
            for key in featureSets {
                var common = Set(first[key].array?.compactMap(\.string) ?? [])
                for feature in available.dropFirst() { common.formIntersection(feature[key].array?.compactMap(\.string) ?? []) }
                invariants[key] = .array(common.sorted().map(ExactJSON.string))
            }
            if available.allSatisfy({ $0["instruction_count"] == first["instruction_count"] }) {
                invariants["instruction_count"] = first["instruction_count"]
            }
        }
        return .object(["target_node_id": .optional(branch.nodes.last?.id),
                        "branch_snapshot": .array(branch.nodes.map { .string($0.id) }),
                        "generations": .array(generations), "invariants": invariants])
    }

    private static func delta(_ before: ExactJSON, _ after: ExactJSON) -> ExactJSON {
        var result: ExactJSON = .object([
            "composition_family": .object(["before": before["composition_family"], "after": after["composition_family"],
                                            "changed": .bool(before["composition_family"] != after["composition_family"])]),
            "instruction_count": .object(["before": before["instruction_count"], "after": after["instruction_count"]])])
        for key in featureSets {
            let old = Set(before[key].array?.compactMap(\.string) ?? [])
            let new = Set(after[key].array?.compactMap(\.string) ?? [])
            result[key] = .object(["added": .array(new.subtracting(old).sorted().map(ExactJSON.string)),
                                   "removed": .array(old.subtracting(new).sorted().map(ExactJSON.string)),
                                   "retained": .array(old.intersection(new).sorted().map(ExactJSON.string))])
        }
        return result
    }

    private static func instructionFeatures(_ score: ExactJSON) -> ExactJSON {
        let instructions = (score["instructions"].array ?? []).filter { $0.object != nil }
        var sets = Dictionary(uniqueKeysWithValues: featureSets.map { ($0, Set<String>()) })
        for item in instructions {
            let primitive = nonempty(item["primitive"].string) ?? "unknown"
            let color = nonempty(item["color"].string) ?? "unknown"
            let density = nonempty(item["arrangement"]["density"].string) ?? "none"
            let path = nonempty(item["arrangement"]["path"].string) ?? nonempty(item["arrangement"]["layout"].string) ?? "none"
            sets["primitives"]!.insert(primitive); sets["colors"]!.insert(color)
            sets["densities"]!.insert(density); sets["arrangement_paths"]!.insert(path)
            sets["score_elements"]!.insert("\(primitive):\(color):\(density):\(path)")
            if let rawRotation = item["rotation"].number.flatMap(Double.init) {
                let rotation = (rawRotation.truncatingRemainder(dividingBy: 360) + 360).truncatingRemainder(dividingBy: 360)
                sets["angles"]!.insert("rotation:" + String(format: "%g", locale: Locale(identifier: "en_US_POSIX"), rotation))
            }
            if let start = pair(item["from"]), let end = pair(item["to"]) {
                let dx = abs(end.0 - start.0), dy = abs(end.1 - start.1)
                sets["angles"]!.insert(dx > dy ? "horizontal" : dy > dx ? "vertical" : "diagonal")
            }
        }
        var result = ExactJSON.object(sets.mapValues { .array($0.sorted().map(ExactJSON.string)) })
        result["composition_family"] = .string(compositionFamily(instructions))
        result["instruction_count"] = .integer(instructions.count)
        return result
    }

    private static func nonempty(_ value: String?) -> String? { value?.isEmpty == false ? value : nil }
    private static func number(_ value: ExactJSON) -> Double? { (value.number ?? value.string).flatMap(Double.init) }
    private static func pair(_ value: ExactJSON) -> (Double, Double)? {
        guard let array = value.array, array.count >= 2, let x = number(array[0]), let y = number(array[1]) else { return nil }
        return (x, y)
    }
    private static func center(_ item: ExactJSON) -> (Double, Double)? {
        if let center = pair(item["center"]) { return center }
        if let position = pair(item["position"]) {
            let size = pair(item["size"])
            return (position.0 + (size?.0 ?? 0) / 2, position.1 + (size?.1 ?? 0) / 2)
        }
        if let start = pair(item["from"]), let end = pair(item["to"]) { return ((start.0 + end.0) / 2, (start.1 + end.1) / 2) }
        if let region = item["at"]["region"].array, region.count == 4,
           let x0 = number(region[0]), let y0 = number(region[1]), let x1 = number(region[2]), let y1 = number(region[3]) {
            return ((x0 + x1) / 2, (y0 + y1) / 2)
        }
        return nil
    }
    private static func compositionFamily(_ instructions: [ExactJSON]) -> String {
        var votes: [String: Int] = [:]
        var order: [String] = []
        var centers: [(Double, Double)] = []
        func vote(_ name: String, _ count: Int) {
            if votes[name] == nil { order.append(name) }
            votes[name, default: 0] += count
        }
        for item in instructions {
            if let location = center(item) { centers.append(location) }
            guard item["arrangement"].object != nil else { continue }
            switch item["arrangement"]["path"].string {
            case "diagonal": vote("diagonal_band", 2)
            case "right_half": vote("one_sided_focus", 2)
            case "top_to_bottom": vote("vertical_rhythm", 2)
            case "left_to_right": vote("horizontal_strata", 2)
            case "wave": vote("dispersal", 1)
            default: break
            }
            switch item["arrangement"]["layout"].string {
            case "vertical": vote("vertical_rhythm", 1)
            case "horizontal": vote("horizontal_strata", 1)
            case "radial": vote("radial_concentric", 2)
            case "scatter", "grid": vote("dispersal", 1)
            default: break
            }
        }
        if !centers.isEmpty {
            let x = centers.reduce(0) { $0 + $1.0 } / Double(centers.count)
            let y = centers.reduce(0) { $0 + $1.1 } / Double(centers.count)
            if (0.42...0.58).contains(x), (0.42...0.58).contains(y) { vote("central_stillness", 2) }
            if x < 0.25 || x > 0.75 || y < 0.25 || y > 0.75 { vote("edge_retreat", 2) }
            else if x < 0.4 || x > 0.6 { vote("one_sided_focus", 2) }
        }
        return order.dropFirst().reduce(order.first ?? "dispersal") { best, name in
            (votes[name] ?? 0) > (votes[best] ?? 0) ? name : best
        }
    }
}

/// Mirrors Server vision_client.py and public.py, including provider-specific sampling.
public enum AuxiliaryWire {
    public static func request(prompt: AuxiliaryPrompt, provider: ProviderSettings, model: String, key: String?) throws -> URLRequest {
        try provider.validate()
        guard !model.isEmpty, prompt.maximumTokens > 0, prompt.timeoutSeconds > 0, prompt.timeoutSeconds.isFinite else {
            throw HostError("invalid_auxiliary_request")
        }
        if provider.requiresAPIKey && (key ?? "").isEmpty { throw HostError("credentials_unavailable") }
        let base = provider.baseURL.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        var endpoint: String
        var headers = ["Content-Type": "application/json"]
        var body: ExactJSON
        switch provider.kind {
        case .chatGPTPlan: throw HostError("chatgpt_operation_not_supported")
        case .openAICompatible:
            endpoint = base + "/chat/completions"
            headers["Authorization"] = "Bearer " + ((key ?? "").isEmpty ? "none" : key!)
            let content: ExactJSON = prompt.purpose == .demo ? .string(prompt.message) : .array(
                [.object(["type": .string("text"), "text": .string(prompt.message)])]
                + prompt.images.map { .object(["type": .string("image_url"), "image_url": .object(["url": .string($0)])]) })
            body = .object(["model": .string(model), "stream": .bool(false),
                "messages": .array([.object(["role": .string("system"), "content": .string(prompt.system)]),
                                     .object(["role": .string("user"), "content": content])])])
            if provider.baseURL.host?.lowercased() == "api.openai.com" {
                body["max_completion_tokens"] = .integer(prompt.maximumTokens)
                if !(model.hasPrefix("gpt-5") || model.range(of: "^o[0-9]", options: .regularExpression) != nil) {
                    body["temperature"] = .number(String(prompt.temperature))
                }
                if model.range(of: "^gpt-5\\.[0-9]", options: .regularExpression) != nil { body["reasoning_effort"] = .string("none") }
            } else {
                body["max_tokens"] = .integer(prompt.maximumTokens); body["temperature"] = .number(String(prompt.temperature))
                if provider.apiProfile == "mlx" {
                    body["enable_thinking"] = .bool(false)
                    let name = model.split(separator: "/").last.map(String.init) ?? model
                    if name.range(of: "^gemma[-_]?4(?:[-_]|$)", options: [.regularExpression, .caseInsensitive]) != nil {
                        body["temperature"] = .number("1.0"); body["top_p"] = .number("0.95"); body["top_k"] = .integer(64)
                    }
                }
            }
        case .anthropic:
            endpoint = base + "/v1/messages"
            headers["x-api-key"] = key ?? ""; headers["anthropic-version"] = "2023-06-01"
            var blocks: [ExactJSON] = try prompt.images.map { image in
                let (type, data) = try imageParts(image)
                return .object(["type": .string("image"), "source": .object([
                    "type": .string("base64"), "media_type": .string(type), "data": .string(data)])])
            }
            blocks.append(.object(["type": .string("text"), "text": .string(prompt.message)]))
            body = .object(["model": .string(model), "max_tokens": .integer(prompt.maximumTokens), "system": .string(prompt.system),
                "messages": .array([.object(["role": .string("user"), "content": .array(blocks)])])])
            if prompt.purpose == .demo { body["temperature"] = .number(String(prompt.temperature)) }
        case .gemini:
            let segment = model.addingPercentEncoding(withAllowedCharacters: CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~"))!
            endpoint = base + "/v1beta/models/" + segment + ":generateContent"
            headers["x-goog-api-key"] = key ?? ""
            var parts: [ExactJSON] = [.object(["text": .string(prompt.message)])]
            for image in prompt.images {
                let (type, data) = try imageParts(image)
                parts.append(.object(["inlineData": .object(["mimeType": .string(type), "data": .string(data)])]))
            }
            var configuration: ExactJSON = .object(["temperature": .number(String(prompt.temperature)), "maxOutputTokens": .integer(prompt.maximumTokens)])
            if prompt.purpose == .vision { configuration["thinkingConfig"] = .object(["thinkingLevel": .string("minimal")]) }
            body = .object(["systemInstruction": .object(["parts": .array([.object(["text": .string(prompt.system)])])]),
                "contents": .array([.object(["role": .string("user"), "parts": .array(parts)])]), "generationConfig": configuration])
        }
        guard let url = URL(string: endpoint) else { throw HostError("provider_base_url_invalid") }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"; request.httpBody = body.data; request.allHTTPHeaderFields = headers
        request.timeoutInterval = prompt.timeoutSeconds
        return request
    }

    private static func imageParts(_ image: String) throws -> (String, String) {
        guard let comma = image.firstIndex(of: ",") else { throw HostError("invalid_auxiliary_image") }
        let header = String(image[..<comma]), data = String(image[image.index(after: comma)...])
        guard header.hasPrefix("data:image/"), header.hasSuffix(";base64"), !data.isEmpty,
              Data(base64Encoded: data) != nil else { throw HostError("invalid_auxiliary_image") }
        return (String(header.dropFirst(5).dropLast(7)), data)
    }

    public static func responseText(_ data: Data, kind: ProviderKind) throws -> String {
        let value = try ExactJSON(data: data)
        let text: String
        switch kind {
        case .chatGPTPlan: throw HostError("chatgpt_operation_not_supported")
        case .openAICompatible:
            guard let content = value["choices"].array?.first?["message"]["content"].string else { throw HostError("malformed_payload") }
            text = content
        case .anthropic:
            guard let blocks = value["content"].array else { throw HostError("malformed_payload") }
            text = blocks.filter { $0["type"].string == "text" }.compactMap { $0["text"].string }.joined(separator: "\n")
        case .gemini:
            guard let parts = value["candidates"].array?.first?["content"]["parts"].array else { throw HostError("malformed_payload") }
            text = parts.filter { $0["thought"].bool != true }.compactMap { $0["text"].string }.joined(separator: "\n")
        }
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
