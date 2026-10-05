import Foundation
import InkuHost
import InkuPersistence

/// The same display vocabulary and greedy interpretation feedback as Web.
public enum DescriptionFeedback {
    private static let vocabulary: Result<[FeedbackLexeme], Error> = Result {
        guard let url = Bundle.module.url(forResource: "saijiki", withExtension: "json"),
              let root = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any],
              let categories = root["categories"] as? [[String: Any]],
              let relations = root["relations"] as? [[String: Any]],
              let relationOrder = root["relation_display_order"] as? [String] else {
            throw HostError("feedback_vocabulary_unavailable")
        }
        var japanese: [FeedbackLexeme] = []
        var english: [FeedbackLexeme] = []
        for category in categories {
            guard let ja = category["name_ja"] as? String, let en = category["name_en"] as? String,
                  let words = category["words"] as? [[String: Any]] else { throw HostError("feedback_vocabulary_invalid") }
            for word in words where word["display"] as? Bool == true {
                if let surface = word["surface_ja"] as? String { japanese.append(FeedbackLexeme(surface: surface, category: ja)) }
                if let surface = word["surface_en"] as? String { english.append(FeedbackLexeme(surface: surface, category: en)) }
            }
        }
        for relationType in relationOrder {
            guard let relation = relations.first(where: { $0["relation_type"] as? String == relationType }),
                  let ja = relation["surface_ja"] as? String, let en = relation["surface_en"] as? String else { throw HostError("feedback_vocabulary_invalid") }
            japanese.append(FeedbackLexeme(surface: ja, category: "あいだ"))
            english.append(FeedbackLexeme(surface: en, category: "relations"))
        }
        return japanese + english
    }

    public static func parts(description: String, ddl: String) throws -> [FeedbackPart] {
        InterpretationFeedback.parts(description: description, ddl: ddl, vocabulary: try vocabulary.get())
    }

    public static func record(description: String, ddl: String, database: InkuDatabase) async throws {
        let words = InterpretationFeedback.unreadWords(description: description, ddl: ddl, vocabulary: try vocabulary.get())
        try await database.recordUnreadWords(words, context: description, at: Int64(Date().timeIntervalSince1970 * 1000))
    }
}
