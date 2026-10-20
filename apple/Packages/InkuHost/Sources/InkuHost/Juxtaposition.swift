import Foundation
import InkuCore

/// SPEC §7.8 juxtaposition (取り合わせ): a sentence from the author's other works, added after a work's description.
/// Every rule is the shared core's (`inku-pipeline/src/juxtaposition.rs`, `inku.juxtaposition.v1`): which sentences are
/// offered, the prompt, how an answer is checked and how the sentence is joined. The host collects the sources, draws the
/// image, sends the prompt and draws the child (Server `juxtaposition.py`).
public enum Juxtaposition {
    public static let schema = "inku.juxtaposition.v1"
    /// How many sentences the model picks.
    public static let choices = 4
    /// Server's `candidate_limit` default. macOS keeps no setting, so the default is the fixed limit.
    public static let candidateLimit = 400

    /// One of the model's picks, in its order, with the description it makes (`joined`, labels and all).
    public struct Choice: Sendable, Equatable {
        public let sentence: String
        public let reason: String
        public let historyIDs: [String]
        public let rank: Int
        /// Where the sentence stood in the shuffled list the model read (0 the head, 1 the tail), as the core wrote it.
        public let position: ExactJSON
        public let joined: String
    }

    public struct Result: Sendable, Equatable {
        public let choices: [Choice]
        public let candidates: Int
        public let model: String

        /// What the child's edge records (Web `juxtapositionMetadata`). Server reads `sentence` back from the lineage
        /// so that the same sentence is not offered again further down it.
        public func metadata(_ choice: Choice) -> ExactJSON {
            .object(["juxtaposition": .object([
                "sentence": .string(choice.sentence), "history_ids": .array(choice.historyIDs.map(ExactJSON.string)),
                "rank": .integer(choice.rank), "reason": .string(choice.reason), "position": choice.position,
                "candidates": .integer(candidates), "model": .string(model)])])
        }
    }

    public enum Checked: Sendable, Equatable {
        case choices([Choice], candidates: Int)
        /// Why the answer cannot be used, in the language the prompt was sent in; it goes into the one resend.
        case refused(reason: String, detail: String)
    }

    /// One request to the core. An unreadable request is this host's mistake, not the model's.
    public static func response(_ request: ExactJSON) throws -> ExactJSON {
        let result = try ExactJSON(data: InkuCore.juxtaposition(request.data))
        guard result["schema"].string == schema, ["ok", "refused"].contains(result["outcome"].string) else {
            throw HostError("invalid_juxtaposition_request")
        }
        return result
    }

    /// At most `limit` candidates in an order drawn from `seed`; each is handed back to the core unchanged.
    /// `sources` pair a work id with its description, labels already removed.
    public static func gather(sources: [(id: String, text: String)], description: String, lineage: [String],
                              added: [String], exclude: [String], seed: UInt64,
                              limit: Int = candidateLimit) throws -> [ExactJSON] {
        let answer = try response(.object([
            "action": .string("gather"),
            "sources": .array(sources.map { .object(["id": .string($0.id), "text": .string($0.text)]) }),
            "description": .string(description), "lineage": .array(lineage.map(ExactJSON.string)),
            "added": .array(added.map(ExactJSON.string)), "exclude": .array(exclude.map(ExactJSON.string)),
            // A decimal string carries all 64 bits.
            "seed": .string(String(seed)), "limit": .integer(limit)]))
        guard answer["outcome"].string == "ok", let candidates = answer["candidates"].array else {
            throw HostError("invalid_juxtaposition_request")
        }
        return candidates
    }

    /// The system prompt and the message beside the image. `resend` is why the previous answer could not be used.
    public static func prompt(language: String, description: String, lineage: [String], candidates: [ExactJSON],
                              resend: String?) throws -> (system: String, text: String) {
        let answer = try response(.object([
            "action": .string("prompt"), "language": .string(language), "description": .string(description),
            "lineage": .array(lineage.map(ExactJSON.string)), "candidates": .array(candidates),
            "resend": .optional(resend)]))
        guard answer["outcome"].string == "ok", let system = answer["system"].string, let text = answer["text"].string else {
            throw HostError("invalid_juxtaposition_request")
        }
        return (system, text)
    }

    /// The model's four picks, or why they cannot be used. `description` is the description as the work keeps it,
    /// labels and all: the child is drawn from `joined`, and a label-free text would drop the author's labels.
    public static func check(language: String, answer: String, candidates: [ExactJSON],
                             description: String) throws -> Checked {
        let result = try response(.object([
            "action": .string("check"), "language": .string(language), "answer": .string(answer),
            "candidates": .array(candidates), "description": .string(description)]))
        if result["outcome"].string == "refused" {
            return .refused(reason: try result.requiredString("reason"), detail: try result.requiredString("detail"))
        }
        guard let items = result["choices"].array, let count = result["candidates"].number.flatMap({ Int($0) }) else {
            throw HostError("invalid_juxtaposition_request")
        }
        let choices = try items.map { item -> Choice in
            guard let sentence = item["sentence"].string, let reason = item["reason"].string,
                  let ids = item["history_ids"].array?.compactMap(\.string), let rank = item["rank"].number.flatMap({ Int($0) }),
                  item["position"].number != nil, let joined = item["joined"].string else {
                throw HostError("invalid_juxtaposition_request")
            }
            return Choice(sentence: sentence, reason: reason, historyIDs: ids, rank: rank, position: item["position"], joined: joined)
        }
        return .choices(choices, candidates: count)
    }
}

/// The model named sentences that were not offered (or repeated one, or left a reason empty), and did so again when
/// told why. `detail` is the core's reason for the second answer.
public struct JuxtapositionAnswerError: Error, LocalizedError, Sendable, Equatable {
    public let detail: String
    public var errorDescription: String? { detail }
}
