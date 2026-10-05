import Foundation
import InkuHost

/// Projects only closed failure facts from one execution's terminal view, without reading logs or raw IO.
enum DrawingFailureMessage {
    /// Web's pipelineAttentionText first ("Review the result… Reason: … (cause; tried N times)"), then the
    /// native diagnosis (stage, network/host reason, operation, HTTP status, URL error code) as details.
    /// `chatGPTCode` is the ChatGPT plan diagnostic this execution reported; Web `pipelineAttentionText` then names it
    /// with `chatgptStatus(code)` instead of the generic cause.
    static func text(for view: PipelineView, language: String, chatGPTCode: String? = nil) -> String? {
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
        if let chatGPTCode, finalMetric?.outcome != .completed {
            web += " " + ChatGPTStatusCopy.text(chatGPTCode, language: language)
        } else if let reason, let text = credentials ? (english ? "the model has no API key" : "モデルのAPIキーがありません")
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

/// Web `chatgptStatus(code)` (i18n ja.ts/en.ts:25-54). The exported reference keeps only the fallback, so the table
/// is copied here; a ChatGPT plan failure is worded with it in the drawing status and the plan settings.
public enum ChatGPTStatusCopy {
    public static func text(_ code: String, language: String) -> String {
        let entry = table[code] ?? ("ChatGPT接続を確認してください。", "Check the ChatGPT connection.")
        return language == "en" ? entry.1 : entry.0
    }

    private static let table: [String: (String, String)] = [
        "chatgpt_models_loading": ("モデル一覧を取得しています…",
            "Loading models…"),
        "chatgpt_connected": ("接続済み",
            "Connected"),
        "chatgpt_signed_out": ("未接続",
            "Not connected"),
        "chatgpt_exported": ("この登録の更新は移送先が担当します。",
            "The receiving host renews this account."),
        "chatgpt_scope_required": ("接続済みですが、プラン利用の許可が必要です。",
            "Connected. Plan usage needs your permission."),
        "chatgpt_mode_not_allowed": ("デベロッパーモードまたはシングルユーザーモードが必要です。",
            "Developer mode or single-user mode is required."),
        "chatgpt_disabled": ("ChatGPT接続は無効です。",
            "ChatGPT connection is disabled."),
        "chatgpt_owner_not_allowed": ("このアカウントは接続の所有者ではありません。",
            "This account does not own the connection."),
        "chatgpt_startup_unverified": ("ChatGPT対応の起動入口を使用してください。",
            "Use the ChatGPT-enabled startup command."),
        "chatgpt_local_authorization_required": ("Macの専用アプリで認証し、保護された経路で登録を移送してください。",
            "Sign in with the Mac helper, then transfer the account through the protected connection."),
        "chatgpt_helper_requested": ("ブラウザの確認画面で「inku ChatGPT」を開いてください。開かない場合は下のリンクで再度開くか、このMacに専用アプリをセットアップしてください。",
            "Allow your browser to open inku ChatGPT. If it does not open, use the link below or set up the dedicated helper on this Mac."),
        "chatgpt_browser_unavailable": ("設定を始めたブラウザを開けませんでした。ブラウザの状態を確認してから、もう一度接続してください。",
            "The browser where you started setup could not be opened. Check it before connecting again."),
        "chatgpt_browser_required": ("このMacのChromeまたはBraveで認証してください。",
            "Authorize using Chrome or Brave on this Mac."),
        "chatgpt_reauthentication_required": ("保存した登録で再認証してください。",
            "Sign in again with the saved account."),
        "chatgpt_session_changed": ("登録が変更されました。状態を確認してください。",
            "The account changed. Check the connection."),
        "chatgpt_not_connected": ("ChatGPTへ接続してください。",
            "Connect to ChatGPT."),
        "chatgpt_quota": ("プラン利用の上限に達しました。利用枠を確認してください。",
            "Plan usage reached its limit. Check your usage."),
        "subscription_sharing_usage_limit_exceeded": ("プラン利用の上限に達しました。利用枠を確認してください。",
            "Plan usage reached its limit. Check your usage."),
        "subscription_sharing_user_not_eligible": ("このアカウントではプランを利用できません。",
            "Plan usage is unavailable for this account."),
        "subscription_sharing_usage_unavailable": ("利用枠を確認できませんでした。時間を置いて再試行してください。",
            "Usage could not be checked. Try again later."),
        "chatgpt_admission_rejected": ("ChatGPTが要求を受け付けませんでした。認証情報を保持しています。接続を確認してください。",
            "ChatGPT could not admit this request. Check the connection; credentials were retained."),
        "chatpass_v2_invalid_authorization_context": ("ChatGPTの認可状態が拒否されました。接続を確認してください。",
            "The ChatGPT authorization context was rejected. Check the connection."),
        "chatpass_v2_scope_not_authorized": ("プラン利用の許可がありません。明示的に利用を許可してください。",
            "Plan usage permission is missing. Grant permission explicitly."),
        "subscription_sharing_unsupported_capability": ("この要求にはChatGPTプラン共有で未対応の機能があります。",
            "This request uses a capability unsupported by ChatGPT plan sharing."),
        "subscription_sharing_route_not_supported": ("この経路はChatGPTプラン共有では未対応です。",
            "This route is unsupported by ChatGPT plan sharing."),
        "subscription_sharing_user_unavailable": ("アカウントを確認できませんでした。時間を置いて再試行してください。",
            "The account could not be checked. Try again later."),
        "chatgpt_transport_unavailable": ("ChatGPTとの通信が途切れました。時間を置いて再試行してください。",
            "The ChatGPT connection was interrupted. Try again later."),
        "chatgpt_response_incomplete": ("応答が完了しませんでした。途中の出力は採用していません。",
            "The response did not finish. Partial output was discarded."),
        "chatgpt_model_not_offered": ("選択したモデルは利用できません。モデル設定で一覧を取得し、公開するモデルを選んで保存してください。",
            "The selected model is unavailable. Fetch the list in Model settings, select models to publish and save."),
        "chatgpt_unexpected_tool": ("ChatGPTの応答が描画用の関数呼出し形式と一致しませんでした。応答形式の診断が必要です。",
            "The ChatGPT response did not match the drawing function-call format. Response diagnostics are needed."),
        "chatgpt_refused": ("ChatGPTが要求を拒否しました。記述を見直してください。",
            "ChatGPT declined the request. Revise your description."),
        "chatgpt_revocation_unconfirmed": ("ローカル接続は解除しました。ChatGPT側の解除は未確認です。ChatGPT設定で確認してください。",
            "Signed out locally. Remote revocation is unconfirmed. Check ChatGPT settings."),
        "chatgpt_cancelled": ("接続操作を中止しました。",
            "Connection cancelled."),
    ]
}
