import CryptoKit
import Foundation
import InkuCore
import InkuHost

/// Server `_recompose` / Web `recomposition.ts`: the numeric ranges of a saved DDL chosen again before it is drawn.
public struct Recomposition: Sendable, Equatable {
    public enum Mode: String, Sendable, CaseIterable { case principled, chance }
    public struct Move: Sendable, Equatable {
        public let layer: Int
        public let from: String
        public let to: String
    }
    public let mode: Mode
    public let recomposed: Bool
    public let moves: [Move]
    public let reason: String?
    /// The chosen source when recomposed; nil when the ranges stay.
    public let source: String?

    static func unchanged(_ mode: Mode, _ reason: String) -> Self {
        Self(mode: mode, recomposed: false, moves: [], reason: reason, source: nil)
    }

    /// Asks the shared core with the run's exact configuration; a failure keeps the ranges, as Server does.
    static func choose(configuration: ExactJSON, source: String, mode: Mode, seed: String) -> Self {
        let digest = SHA256.hash(data: Data(source.utf8)).map { String(format: "%02x", $0) }.joined()
        let request: ExactJSON = .object(["config": configuration, "source": .string(source), "mode": .string(mode.rawValue),
                                          "seed": .string(seed), "work_id": .string("sha256:" + digest)])
        guard let value = try? ExactJSON(data: InkuCore.recompose(request.data)) else { return .unchanged(mode, "recompose_failed") }
        if let error = value["error"].string {
            return ["invalid_request", "internal_invariant", "internal"].contains(error) ? .unchanged(mode, error) : .unchanged(mode, "invalid_response")
        }
        guard value["schema"].string == "inku.composition-recompose.v1", let outcome = value["outcome"].string,
              ["recomposed", "unchanged"].contains(outcome) else { return .unchanged(mode, "invalid_response") }
        if outcome == "unchanged" { return .unchanged(mode, value["reason"].string ?? "invalid_response") }
        guard let chosen = value["source"].string, !chosen.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return .unchanged(mode, "invalid_response")
        }
        let moves = (value["moves"].array ?? []).compactMap { move -> Move? in
            guard let layer = move["layer"].number.flatMap(Int.init), let from = move["from"].string, let to = move["to"].string else { return nil }
            return Move(layer: layer, from: from, to: to)
        }
        return Self(mode: mode, recomposed: true, moves: moves, reason: nil, source: chosen)
    }

    static let reasons: [String: String] = [
        "nothing_to_move": "この作品には構図の範囲が無い。",
        "not_canonical": "指示書に未確定の部分があるため、構図を動かせない。",
        "unsupported_sentence": "この指示書には構図の変更に対応していない文がある。",
        "unplaced_sentence": "配置を読み戻せない文があるため、構図を動かせない。",
        "author_range": "作者が指定した範囲を保つため、構図を動かせない。",
        "no_other_answer": "今と違う構図が見つからない。",
        "same_ranges": "偶然が今と同じ構図の範囲を選んだ。",
        "unsolved": "組み合わせが多すぎて別の構図を探せない。",
        "not_canonical_after": "変更後の指示書を確かめられないため、構図を動かせない。",
    ]

    /// Web `recompositionLines`: core layers are zero based; the author sees layers from one.
    @MainActor public func lines(display: DisplaySettings) -> [String] {
        guard recomposed else {
            return [display.localized(Self.reasons[reason ?? ""] ?? "別の構図を使えないため、構図の範囲を保つ。"),
                    display.localized("構図の範囲を保って描き直しました。")]
        }
        return moves.map { "\($0.layer + 1): \($0.from) → \($0.to)" }
    }
}
