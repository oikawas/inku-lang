import InkuHost
import SwiftUI

/// Save-frozen facts are ordinary generation information; raw bodies are loaded only on developer demand.
@MainActor
public struct ProviderObservationView: View {
    @Bindable private var model: AppModel
    private let metrics: [ProviderAttemptMetric]
    private let workID: String?
    private let executionID: String?
    @State private var expanded = false
    @State private var rawExpanded = false
    @State private var loading = false
    @State private var records: [ProviderAttemptObservation] = []
    @State private var loadFailed = false
    @State private var rawLoadID: UUID?
    private let previewLimit = 32_768

    public init(model: AppModel, metrics: [ProviderAttemptMetric], workID: String? = nil, executionID: String? = nil) {
        self.model = model; self.metrics = metrics; self.workID = workID; self.executionID = executionID
    }
    private var sourceID: String { workID ?? executionID ?? "" }

    public var body: some View {
        DisclosureGroup(model.display.localized("モデルの実測記録"), isExpanded: $expanded) {
            VStack(alignment: .leading, spacing: 10) {
                if metrics.isEmpty {
                    Text(model.display.localized("記録なし")).foregroundStyle(.secondary)
                }
                ForEach([ProviderObservationStage.stage1, .composition, .stage2], id: \.rawValue) { stage in
                    let attempts = metrics.filter { $0.stage == stage }
                    if !attempts.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(model.display.localized(title(stage))).font(.caption.weight(.semibold))
                            ForEach(Array(attempts.enumerated()), id: \.offset) { _, metric in
                                metricRow(metric)
                            }
                        }
                    }
                }
                if model.developerModeEnabled {
                    DisclosureGroup(model.display.localized("送受信の記録（開発用）"), isExpanded: $rawExpanded) {
                        rawContent
                    }
                    .onChange(of: rawExpanded) { _, opened in
                        if opened { Task { await loadRaw() } }
                        else { records = []; loadFailed = false; rawLoadID = nil; loading = false }
                    }
                }
            }.padding(.top, 6).font(.caption)
        }
        .onChange(of: sourceID) { _, _ in
            expanded = false; rawExpanded = false; records = []; loadFailed = false; rawLoadID = nil; loading = false
        }
    }

    private func metricRow(_ metric: ProviderAttemptMetric) -> some View {
        let absent = model.display.localized("記録なし")
        return VStack(alignment: .leading, spacing: 2) {
            Text(model.display.localizedFormat("呼出しモデル: %@", metric.requestedModelReference)).lineLimit(2)
            if let responseModel = metric.responseModel {
                Text(model.display.localizedFormat("応答モデル: %@", responseModel)).foregroundStyle(.secondary)
            }
            HStack(spacing: 8) {
                Text(model.display.localizedFormat("試行 %d", Int(metric.identity.attempt)))
                if let elapsed = metric.elapsedMS {
                    Text(model.display.localizedFormat("呼出し %.1f秒", Double(elapsed) / 1_000))
                } else { Text(model.display.localized("時間: 記録なし")) }
                Text(model.display.localized(outcome(metric.outcome)))
            }.foregroundStyle(.secondary).monospacedDigit()
            if let status = metric.httpStatus ?? metric.diagnostic?.httpStatus { Text("HTTP \(status)").font(.caption.monospaced()) }
            if let failure = metric.failure { Text(failure).font(.caption.monospaced()).foregroundStyle(.secondary) }
            if let diagnostic = metric.diagnostic {
                if let endpoint = diagnostic.endpoint { Text(endpoint).font(.caption.monospaced()) }
                if let domain = diagnostic.errorDomain, let code = diagnostic.errorCode {
                    Text("\(domain) \(code)").font(.caption.monospaced()).foregroundStyle(.secondary)
                }
                if let code = diagnostic.hostCode { Text(code).font(.caption.monospaced()).foregroundStyle(.secondary) }
                if let message = diagnostic.providerMessage { Text(message).font(.caption) }
            }
            Text(model.display.localizedFormat("トークン 入力 %@・出力 %@",
                metric.usage?.inputTokens.map(String.init) ?? absent,
                metric.usage?.outputTokens.map(String.init) ?? absent)).foregroundStyle(.secondary).monospacedDigit()
        }.textSelection(.enabled)
    }

    @ViewBuilder private var rawContent: some View {
        HStack {
            Button(model.display.localized("記録を更新")) { Task { await loadRaw() } }
                .disabled(loading)
            Spacer()
        }
        if loading { ProgressView().controlSize(.small) }
        else if loadFailed { Text(model.display.localized("送受信の記録を読み込めませんでした。")).foregroundStyle(.red) }
        else if records.isEmpty { Text(model.display.localized("送受信は記録されていません。")).foregroundStyle(.secondary) }
        else {
            ForEach(Array(records.enumerated()), id: \.offset) { _, record in
                if let raw = record.raw {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(model.display.localized(title(record.metric.stage))).fontWeight(.semibold)
                        Text(model.display.localizedFormat("試行 %d", Int(record.metric.identity.attempt)))
                        if raw.responseIncomplete || raw.requestTruncated || raw.responseTruncated || !raw.captureComplete {
                            Text(model.display.localized("この記録には途中までの応答、または省略された本文が含まれます。"))
                                .foregroundStyle(.secondary)
                        }
                        if let request = raw.requestBody { bodyRecord(request, title: "送った本文") }
                        if let response = raw.responseBody { bodyRecord(response, title: "受け取った応答") }
                    }.padding(.vertical, 6)
                }
            }
        }
    }

    private func bodyRecord(_ body: String, title: String) -> some View {
        DisclosureGroup(model.display.localized(title)) {
            VStack(alignment: .leading, spacing: 6) {
                ScrollView {
                    Text(String(decoding: body.utf8.prefix(previewLimit), as: UTF8.self)).font(.system(.caption2, design: .monospaced))
                        .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                }.frame(maxHeight: 180)
                if body.utf8.count > previewLimit {
                    Text(model.display.localized("表示は本文の先頭だけです。保存された全文は共有できます。"))
                        .foregroundStyle(.secondary)
                }
                ShareLink(item: body) { Label(model.display.localized("記録した本文を共有"), systemImage: "square.and.arrow.up") }
            }
        }
    }

    private func loadRaw() async {
        guard !loading, model.developerModeEnabled else { return }
        let identity = sourceID
        let loadID = UUID(); rawLoadID = loadID
        loading = true; loadFailed = false
        defer { if rawLoadID == loadID { loading = false } }
        do {
            let result: [ProviderAttemptObservation]
            if let workID { result = try await model.savedProviderObservations(workID: workID) }
            else if let executionID { result = try await model.providerObservations(executionID: executionID) }
            else { result = [] }
            guard rawLoadID == loadID, identity == sourceID, rawExpanded, model.developerModeEnabled else { return }
            records = result
        } catch {
            guard rawLoadID == loadID, identity == sourceID, rawExpanded else { return }
            loadFailed = true
        }
    }

    private func title(_ stage: ProviderObservationStage) -> String {
        switch stage { case .stage1: "解釈"; case .composition: "構図の読み"; case .stage2: "指示書の補完" }
    }
    private func outcome(_ outcome: ProviderAttemptOutcome) -> String {
        switch outcome { case .requestSaved: "応答未確定"; case .completed: "完了"; case .failed: "失敗"; case .cancelled: "停止済み" }
    }
}
