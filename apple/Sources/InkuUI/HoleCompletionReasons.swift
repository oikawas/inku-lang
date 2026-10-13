import Foundation

/// Web `pipelineCompletionReason`: the plain reason a completion check gives for a hole it did not accept.
public enum HoleCompletionReasons {
    static let japanese: [String: String] = [
        "established_fact_changed": "元の文で読めた語（位置・個数・色・形・動作など）が案で消えた",
        "owner_association_changed": "語と形の結びつきが案で変わった",
        "target_unresolved": "案にも読めない語が残り、描ける文にならなかった",
        "new_diagnostic": "案に新しい読めない語句が入った",
        "numeric_range_outside_words": "数の範囲が、括弧の前の位置の語の範囲から外れた",
        "range_words_not_kept": "言葉を直した範囲の、括弧の前の言葉か範囲の形が案で変わった",
        "dependency_rejected": "一緒に直す別の文が補えなかった",
        "dependency_unresolved": "一緒に直す別の文が補えなかった",
        "outside_explicit_changed": "案が穴の外の書いた内容を変えた",
        "schema_violation": "モデルの答えが読めなかった",
        "unsupported": "今の文法では書けないと答えた",
        "ambiguous": "意味を一つに決められないと答えた",
        "context_limit": "文脈が長すぎて補えなかった",
    ]

    @MainActor public static func text(_ code: String, display: DisplaySettings) -> String {
        if let known = japanese[code] { return display.localized(known) }
        return display.localizedFormat("検査で断られた（%@）", code)
    }
}
