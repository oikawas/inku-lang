import InkuHost
import SwiftUI

@MainActor
struct DrawingLogView: View {
    @Bindable var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var records: [DrawingLogRecord] = []
    @State private var selectedID: String?
    @State private var loading = false
    @State private var loadError: String?
    @State private var hasLoaded = false

    private var selected: DrawingLogRecord? { records.first { $0.id == selectedID } }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(model.display.localized("描画ログ")).font(.title2.weight(.semibold))
                Spacer()
                Button(model.display.localized("記録を更新")) { Task { await load() } }.disabled(loading)
                    .help(model.display.tooltip("描画ログを読み直します。生成や再送信は行いません。"))
                Button(model.display.localized("閉じる")) { dismiss() }.keyboardShortcut(.cancelAction)
            }.padding()
            Divider()
            if let loadError {
                VStack(alignment: .leading, spacing: 8) {
                    Text(model.display.localized("描画ログを読み込めませんでした。") + "\n" + model.display.message(loadError))
                        .foregroundStyle(.red).textSelection(.enabled)
                    HStack {
                        Button(model.display.localized("もう一度読み込む")) { Task { await load() } }.disabled(loading)
                        Button(model.display.localized("エラーを閉じる")) { self.loadError = nil }
                    }
                    if hasLoaded { Text(model.display.localized("前回読み込めた記録を表示しています。")).font(.caption).foregroundStyle(.secondary) }
                }.padding().frame(maxWidth: .infinity, alignment: .leading)
                Divider()
            }
            if loading && records.isEmpty { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
            else if records.isEmpty {
                Text(model.display.localized(hasLoaded ? "描画の実行記録はまだありません。" : "記録を更新して描画ログを読み込んでください。"))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                HStack(spacing: 0) {
                    ScrollView {
                        LazyVStack(spacing: 6) {
                            ForEach(records) { record in
                                Button { selectedID = record.id } label: {
                                    VStack(alignment: .leading, spacing: 5) {
                                        HStack {
                                            Text(model.display.localized(phase(record.phase))).fontWeight(.semibold)
                                            Spacer()
                                            Text(record.startedAt.formatted(date: .numeric, time: .shortened)).font(.caption)
                                        }
                                        Text(record.description.isEmpty ? model.display.localized("DDLからの描画") : record.description)
                                            .lineLimit(3).font(.caption)
                                        Text(record.stage1Model).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                                    }.frame(maxWidth: .infinity, alignment: .leading).padding(10)
                                        .background(selectedID == record.id ? Color.accentColor.opacity(0.12) : Color.secondary.opacity(0.04),
                                                    in: RoundedRectangle(cornerRadius: 8))
                                }.buttonStyle(.plain)
                            }
                        }.padding(10)
                    }.frame(width: 280)
                    Divider()
                    ScrollView {
                        if let selected { details(selected).padding(18).frame(maxWidth: .infinity, alignment: .leading) }
                    }.frame(maxWidth: .infinity)
                }
            }
            Divider()
            Text(model.display.localized("直近100件の実行記録です。開いても描画や再送信は行いません。"))
                .font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading).padding(12)
        }
        #if os(macOS)
        .frame(minWidth: 760, idealWidth: 1040, minHeight: 480, idealHeight: 700)
        #endif
        .task { await load() }
    }

    private func details(_ record: DrawingLogRecord) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(model.display.localized(phase(record.phase))).font(.title3.weight(.semibold))
            Text(record.startedAt.formatted(date: .complete, time: .standard)).foregroundStyle(.secondary)
            if !record.description.isEmpty { Text(record.description).textSelection(.enabled) }
            Text(model.display.localizedFormat("解釈モデル: %@", record.stage1Model))
            Text(model.display.localizedFormat("補完モデル: %@", record.stage2Model))
            if let reason = record.failureReason {
                VStack(alignment: .leading, spacing: 5) {
                    Text(model.display.localized(failure(reason))).fontWeight(.semibold)
                    Text(reason).font(.caption.monospaced()).foregroundStyle(.secondary)
                    if let stage = record.failureStage { Text(model.display.localized(action(stage))) }
                    if record.providerMetrics.contains(where: { $0.failure != nil && $0.diagnostic == nil }) {
                        Text(model.display.localized("この実行は詳細な通信理由を保存する前の記録です。"))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            Divider()
            Text(model.display.localized("モデルの実測記録")).font(.headline)
            ForEach(Array(record.providerMetrics.enumerated()), id: \.offset) { _, metric in
                VStack(alignment: .leading, spacing: 5) {
                    Text(model.display.localized(action(metric.action))).fontWeight(.semibold)
                    Text(model.display.localizedFormat("呼出しモデル: %@", metric.requestedModelReference))
                    HStack {
                        Text(model.display.localizedFormat("試行 %d", Int(metric.identity.attempt)))
                        Text(model.display.localized(outcome(metric.outcome)))
                        if let elapsed = metric.elapsedMS { Text(model.display.localizedFormat("呼出し %.1f秒", Double(elapsed) / 1_000)) }
                        if let status = metric.httpStatus ?? metric.diagnostic?.httpStatus { Text("HTTP \(status)") }
                    }.font(.caption).monospacedDigit()
                    if !metric.sent {
                        Text(model.display.localized("送信状態不明／応答未確認")).font(.caption).foregroundStyle(.secondary)
                    }
                    if metric.failure != nil || metric.diagnostic != nil || metric.outcome == .failed || metric.outcome == .cancelled {
                        Text(model.display.localizedFormat("診断の操作: %@", model.display.localized(diagnosticOperation(metric.diagnostic?.operation))))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if let failureCode = metric.failure {
                        Text(model.display.localized(failure(failureCode)))
                        Text(failureCode).font(.caption.monospaced()).foregroundStyle(.secondary)
                    }
                    if let diagnostic = metric.diagnostic {
                        Text(model.display.localized(diagnosticReason(diagnostic.reason)))
                        if let endpoint = diagnostic.endpoint { Text(endpoint).font(.caption.monospaced()) }
                        if let domain = diagnostic.errorDomain, let code = diagnostic.errorCode {
                            Text("\(domain) \(code)").font(.caption.monospaced()).foregroundStyle(.secondary)
                        }
                        if let code = diagnostic.hostCode { Text(code).font(.caption.monospaced()).foregroundStyle(.secondary) }
                        if let message = diagnostic.providerMessage { Text(message).font(.caption) }
                        let codes = [diagnostic.providerCode, diagnostic.providerType, diagnostic.providerParameter, diagnostic.providerStatus].compactMap { $0 }
                        if !codes.isEmpty { Text(codes.joined(separator: " · ")).font(.caption.monospaced()).foregroundStyle(.secondary) }
                    }
                }.padding(10).frame(maxWidth: .infinity, alignment: .leading)
                    .background(.quaternary, in: RoundedRectangle(cornerRadius: 8)).textSelection(.enabled)
            }
            DisclosureGroup(model.display.localized("描画の経過")) {
                ForEach(record.events) { event in
                    HStack(alignment: .top) {
                        Text(event.sequence).monospacedDigit().foregroundStyle(.secondary).frame(width: 24, alignment: .trailing)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(model.display.localized(eventTitle(event)))
                            if let actionName = event.action ?? event.stage { Text(model.display.localized(action(actionName))) }
                            if let reason = event.reason { Text(reason).font(.caption.monospaced()).foregroundStyle(.secondary) }
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 3)
                }
            }
            DisclosureGroup(model.display.localized("実行ID")) { Text(record.id).font(.caption.monospaced()).textSelection(.enabled) }
        }
    }

    private func load() async {
        guard !loading else { return }
        loading = true
        defer { loading = false }
        do {
            let latest = try await model.drawingLogs()
            try Task.checkCancellation()
            records = latest
            hasLoaded = true
            loadError = nil
            if !records.contains(where: { $0.id == selectedID }) { selectedID = records.first?.id }
        } catch is CancellationError { }
        catch { loadError = error.localizedDescription }
    }

    private func phase(_ value: String) -> String {
        switch value { case "failed": "失敗"; case "completed": "完了"; case "cancelled": "停止済み"
        case "awaiting_patch_approval": "補完案の承認待ち"; case "needs_user_edit": "DDLを編集してください"
        default: "処理中" }
    }
    private func outcome(_ value: ProviderAttemptOutcome) -> String {
        switch value { case .failed: "失敗"; case .completed: "完了"; case .cancelled: "停止済み"; case .requestSaved: "応答未確定" }
    }
    private func diagnosticOperation(_ value: ProviderAttemptDiagnosticOperation?) -> String {
        switch value {
        case .some(.preparation): "準備"
        case .some(.admission): "受付待ち"
        case .some(.tokenCount): "トークン計数"
        case .some(.generation): "生成要求"
        case .none: "不明"
        }
    }
    private func failure(_ value: String) -> String {
        switch value {
        case "transport_unavailable": "モデルサービスに接続できませんでした。"
        case "transport_timeout": "モデルの応答が制限時間内に届きませんでした。"
        case "provider_rejected": "モデルサービスが要求を受け付けませんでした。"
        case "rate_limited": "モデルサービスの利用上限に達しました。"
        case "malformed_payload", "schema_violation": "モデルの応答を読み取れませんでした。"
        default: "描画を完了できませんでした。"
        }
    }
    private func action(_ value: String) -> String {
        switch value {
        case "select_description_catalog": "記述からの色カタログ選択"
        case "generate_sketch": "写生"
        case "generate_normalized_ddl": "記述からのDDL生成"
        case "read_composition": "構図の読み"
        case "complete_visible_ddl_holes": "指示書の補完"
        default: value
        }
    }
    private func eventTitle(_ event: DrawingLogEvent) -> String {
        switch event.tag {
        case "state_entered": phase(event.state ?? "")
        case "effect_requested": "モデルへ要求"
        case "retry_scheduled": "再試行"
        case "catalog_fallback": "既定カタログで続行"
        case "sketch_ready": "写生の処理を完了"
        case "failed": "失敗"; case "cancelled": "停止済み"; case "completed": "完了"
        default: event.tag
        }
    }

    private func diagnosticReason(_ value: String) -> String {
        switch value {
        case "Could not connect to the provider host.": "接続先のホストに接続できませんでした。"
        case "The provider host could not be found.": "接続先のホストが見つかりませんでした。"
        case "The provider request timed out.": "モデルへの要求がタイムアウトしました。"
        case "The network is unavailable.": "ネットワークを利用できません。"
        case "The connection to the provider was lost.": "モデルサービスへの接続が切断されました。"
        case "The secure connection to the provider could not be verified.": "モデルサービスへの安全な接続を確認できませんでした。"
        case "The provider network request failed.": "モデルサービスとの通信に失敗しました。"
        case "The provider returned an HTTP error.": "モデルサービスがHTTPエラーを返しました。"
        case "Choose a provider and model.": "サービスとモデルを選択してください。"
        case "The provider credential is unavailable.": "モデルサービスの認証情報を利用できません。"
        case "The provider endpoint is invalid.": "モデルサービスの接続先が無効です。"
        case "The provider request budget is exhausted.": "モデルサービスの利用枠を使い切りました。"
        case "The provider transport is unavailable.": "モデルサービスとの通信を利用できません。"
        case "The provider response could not be read.": "モデルサービスの応答を読み取れませんでした。"
        default: "モデルへの要求を完了できませんでした。"
        }
    }
}
