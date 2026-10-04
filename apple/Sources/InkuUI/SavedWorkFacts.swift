import Foundation
import InkuPersistence

public struct SavedModelFact: Sendable, Equatable, Identifiable {
    public enum Role: String, Sendable { case interpretation, drawing }
    public let role: Role
    public let reference: String?
    public var id: String { role.rawValue }
    public var label: String { role == .interpretation ? "解釈モデル" : "描画モデル" }
}

public enum SavedWorkFacts {
    public static func recordedModel(_ value: String?) -> String? {
        guard let value, !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return value
    }

    public static func models(_ work: SavedWork) -> [SavedModelFact] {
        [SavedModelFact(role: .interpretation, reference: recordedModel(work.stage1Model)),
         SavedModelFact(role: .drawing, reference: recordedModel(work.stage2Model))]
    }

    public static func svgBytes(_ work: SavedWork) -> Int64 { Int64(work.svg.utf8.count) }
}
