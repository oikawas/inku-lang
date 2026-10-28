import Foundation
import InkuHost

@MainActor func chunkMoveText(_ record: ExactJSON, display: DisplaySettings) -> String? {
    guard let move = record["move"].string, !move.isEmpty else { return nil }
    let name = display.webCopy("chunkMove." + move, move)
    let targets = record["targets"].array?.compactMap(\.string) ?? []
    let title = record["title"].string?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if display.preferences.language == "en" {
        return name + (targets.isEmpty ? "" : " " + targets.map { "“\($0)”" }.joined(separator: " and ")) + (title.isEmpty ? "" : " → “\(title)”")
    }
    return name + targets.map { "『\($0)』" }.joined() + (title.isEmpty ? "" : "→『\(title)』")
}
