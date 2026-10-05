import Foundation
import InkuHost

/// Projects only closed failure facts from one execution's terminal view, without reading logs or raw IO.
enum DrawingFailureMessage {
    /// Web's pipelineAttentionText first ("Review the result… Reason: … (cause; tried N times)"), then the
    /// native diagnosis (stage, network/host reason, operation, HTTP status, URL error code) as details.
    static func text(for view: PipelineView, language: String) -> String? {
        guard view.phase == "failed" else { return nil }
        let english = language == "en"
        let events = (try? ExactJSON(data: view.eventsJSON).array) ?? []
        let failure = events.last { $0["tag"].string == "failed" }?["payload"]
        let action = failure?["stage"].string
        let reason = failure?["reason"].string
        // Metrics belong to this view's execution. A sketch/catalog failure must not explain a later DDL failure.
        let finalMetric = action.flatMap { action in view.providerMetrics.last { $0.action == action } }
        // A completed final response can fail core validation; never borrow an earlier retry's network error.
        let metric = finalMetric.flatMap { metric in
            metric.outcome == .failed && reason != nil && metric.failure == reason ? metric : nil
        }
        let stage = action.flatMap { stages[$0] }.map { english ? $0.1 : $0.0 }
            ?? (english ? "Drawing processing" : "描画処理")
        let diagnostic = metric?.diagnostic

        let phaseReason = action.flatMap { phaseReasons[$0] }.map { english ? $0.1 : $0.0 } ?? stage
        var web = (english ? "Review the result of this operation. Reason: " : "処理の結果を確認してください。 理由: ") + phaseReason
        let credentials = reason == "provider_rejected" && diagnostic?.hostCode == "credentials_unavailable"
        if let reason, let text = credentials ? (english ? "the model has no API key" : "モデルのAPIキーがありません")
            : causes[reason].map({ english ? $0.1 : $0.0 }) {
            let attempts = finalMetric.map { Int($0.identity.attempt) } ?? 1
            web += english ? " (" + text + (attempts > 1 ? "; tried \(attempts) times" : "") + ")"
                : "（" + text + (attempts > 1 ? "。\(attempts)回試しました" : "") + "）"
        }

        var details: [String] = []
        if let operation = diagnostic?.operation {
            let label: (String, String)
            switch operation {
            case .preparation: label = ("要求準備", "request preparation")
            case .admission: label = ("送信予算の確認・待機", "request-budget admission")
            case .tokenCount: label = ("入力token計測", "input-token counting")
            case .generation: label = ("生成要求", "generation request")
            }
            details.append(english ? label.1 : label.0)
        }
        if let status = metric?.httpStatus ?? diagnostic?.httpStatus, (100...599).contains(status) {
            details.append("HTTP \(status)")
        }
        if let diagnostic, diagnostic.kind == .network,
           diagnostic.errorDomain == NSURLErrorDomain, let code = diagnostic.errorCode {
            details.append("NSURLErrorDomain \(code)")
        }
        if let code = diagnostic?.hostCode, hostReasons[code] != nil { details.append(code) }
        if let reason, causes[reason] != nil, !details.contains(reason) { details.append(reason) }
        let nativeCause = diagnostic.flatMap { diagnosticReason($0, english: english) }
        let suffix = details.isEmpty ? "" : (english
            ? " (" + details.joined(separator: "; ") + ")"
            : "（" + details.joined(separator: "、") + "）")
        let supplement = stage + (nativeCause.map { (english ? ": " : "・") + $0 } ?? "") + suffix
        return web + (english ? " Details: " + supplement + "." : " 詳細: " + supplement + "。")
    }

    private static func diagnosticReason(_ diagnostic: ProviderAttemptDiagnostic, english: Bool) -> String? {
        if diagnostic.kind == .host, let code = diagnostic.hostCode, let text = hostReasons[code] {
            return english ? text.1 : text.0
        }
        guard diagnostic.kind == .network, diagnostic.errorDomain == NSURLErrorDomain,
              let code = diagnostic.errorCode else { return nil }
        let text: (String, String)
        switch code {
        case -1005: text = ("処理中に接続が失われました", "The connection was lost during this operation")
        case -1001: text = ("通信が期限を超えました", "The network request timed out")
        case -1004: text = ("接続先へ接続できませんでした", "Could not connect to the provider host")
        case -1003, -1006: text = ("接続先を見つけられませんでした", "Could not find the provider host")
        case -1009: text = ("ネットワークを利用できませんでした", "The network was unavailable")
        case -1200, -1201, -1202, -1203, -1204:
            text = ("安全な接続を確認できませんでした", "The secure connection could not be verified")
        case -999: text = ("通信が取り消されました", "The network request was cancelled")
        default: return nil
        }
        return english ? text.1 : text.0
    }

    private static let stages: [String: (String, String)] = [
        "generate_sketch": ("写生生成処理", "Sketch generation processing"),
        "select_description_catalog": ("配色選択処理", "Catalog selection processing"),
        "generate_normalized_ddl": ("指示書生成処理", "DDL generation processing"),
        "read_composition": ("構図読み取り処理", "Composition reading processing"),
        "complete_visible_ddl_holes": ("指示書補完処理", "DDL hole-completion processing"),
    ]
    /// Web ja.ts/en.ts pipelineAttentionReason for the phase a failed action stops.
    private static let phaseReasons: [String: (String, String)] = [
        "generate_sketch": ("記述の解釈を完了できませんでした", "the description could not be interpreted"),
        "select_description_catalog": ("記述の解釈を完了できませんでした", "the description could not be interpreted"),
        "generate_normalized_ddl": ("記述の解釈を完了できませんでした", "the description could not be interpreted"),
        "complete_visible_ddl_holes": ("DDLの補完候補を作れませんでした", "a DDL completion proposal could not be prepared"),
    ]
    /// Web ja.ts/en.ts pipelineFailureCause.
    private static let causes: [String: (String, String)] = [
        "transport_timeout": ("モデルの応答が制限時間内に返りませんでした", "the model did not answer within the time limit"),
        "transport_unavailable": ("モデルに接続できませんでした", "the model could not be reached"),
        "rate_limited": ("モデルの提供元が要求を制限しました", "the model provider rate-limited the request"),
        "provider_rejected": ("モデルの提供元が要求を断りました", "the model provider refused the request"),
        "malformed_payload": ("モデルの応答を読めませんでした", "the model's answer could not be read"),
        "schema_violation": ("モデルの応答が決まった形になっていませんでした", "the model's answer was not in the expected form"),
        "semantic_violation": ("モデルの応答を描画に使えませんでした", "the model's answer could not be used for the drawing"),
    ]
    private static let hostReasons: [String: (String, String)] = [
        "credentials_unavailable": ("認証情報を利用できませんでした", "The provider credential was unavailable"),
        "provider_selection_required": ("サービスとモデルの選択が必要です", "A provider and model must be selected"),
        "provider_base_url_invalid": ("接続先の設定が不正です", "The provider endpoint configuration is invalid"),
        "invalid_provider_rate_limits": ("レート制限の設定が不正です", "The provider rate-limit configuration is invalid"),
        "transport_timeout": ("応答が期限を超えました", "The provider request timed out"),
        "rate_limited": ("レート制限により処理できませんでした", "A request rate limit prevented completion"),
        "transport_unavailable": ("通信を完了できませんでした", "The provider connection could not be completed"),
        "malformed_payload": ("応答を読み取れませんでした", "The provider response could not be read"),
        "invalid_json": ("応答を読み取れませんでした", "The provider response could not be read"),
        "duplicate_json_key": ("応答を読み取れませんでした", "The provider response could not be read"),
        "provider_response_too_large": ("応答が上限の大きさを超えました", "The provider response exceeded the size limit"),
    ]
}
