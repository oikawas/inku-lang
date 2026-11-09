import Foundation

/// Web `score-version.ts`: a missing Score and an older Score without a recorded version are distinct.
/// The saved JSON is read as it is: decoding it through the core's `Score` would fill a missing version with 0.9.0.
enum ScoreVersionDisplay {
    /// nil when the work has no Score (shown as the absent mark), the recorded version, or `notRecorded`.
    static func text(scoreJSON: String, notRecorded: String) -> String? {
        let trimmed = scoreJSON.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, trimmed != "null" else { return nil }
        guard let object = (try? JSONSerialization.jsonObject(with: Data(trimmed.utf8))) as? [String: Any] else { return notRecorded }
        return object["version"] as? String ?? notRecorded
    }
}
