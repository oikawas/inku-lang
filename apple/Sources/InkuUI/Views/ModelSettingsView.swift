import InkuHost
import SwiftUI

@MainActor
struct ModelSettingsView: View {
    @Bindable var model: AppModel
    @Bindable var settings: SettingsModel
    @Bindable var automation: AutomationModel

    @State private var serviceDrafts: [String: ServiceDraft] = [:]
    @State private var drawingDraft: ModelSelection?
    @State private var sheetRoute: SheetRoute?
    @State private var confirmation: Confirmation?
    @State private var saving = false
    @State private var rateHelp: String?

    private var actionsDisabled: Bool { model.isBrowsingLocked || saving }
    private var credentialsLocked: Bool { model.isBusy || automation.isOccupied }
    private var credentialActionsDisabled: Bool { actionsDisabled || credentialsLocked }
    private var drawingModels: ModelSelection { drawingDraft ?? settings.host.models }
    private var drawingChoices: [DrawingChoice] {
        settings.orderedProviders.flatMap { provider in
            SettingsModel.batchModels(for: provider).map {
                DrawingChoice(provider: provider, model: ProviderModelInfo(id: provider.id + ":" + $0.id,
                    name: $0.label, contextLimit: nil, capabilities: []))
            }
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(model.display.localized("AIサービス接続")).inkuFont(16, weight: .semibold)
                serviceCards
                if let provider = settings.selectedProvider {
                    serviceEditor(provider)
                } else {
                    Text(model.display.localized("サービスを追加してください。"))
                        .foregroundStyle(.secondary)
                }
                if !settings.status.isEmpty {
                    Text(model.display.message(settings.status)).inkuFont(13).foregroundStyle(.secondary)
                }
                HStack {
                    Spacer()
                    Button(model.display.localized("サービス追加")) { sheetRoute = .service(.add) }
                }
                drawingDefaults
            }
            .padding(20)
            .frame(maxWidth: .infinity, alignment: .leading)
            .disabled(actionsDisabled)
        }
        .sheet(item: $sheetRoute) { route in
            switch route {
            case .service(let mode):
                ProviderServiceEditorSheet(mode: mode, model: model, settings: settings,
                                           automation: automation)
            case .models(let providerID):
                ProviderModelsSheet(providerID: providerID, model: model, settings: settings)
            }
        }
        .confirmationDialog(confirmationTitle, isPresented: Binding(
            get: { confirmation != nil },
            set: { if !$0 { confirmation = nil } }), titleVisibility: .visible) {
                if let action = confirmation {
                    Button(model.display.localized(action.buttonTitle), role: .destructive) {
                        confirmation = nil
                        confirm(action)
                    }
                    .disabled(confirmationDisabled(action))
                }
                Button(model.display.localized("キャンセル"), role: .cancel) { confirmation = nil }
            } message: {
                if let action = confirmation {
                    Text(model.display.localizedFormat("サービスID: %@", action.providerID))
                }
            }
        .task {
            let persisted = await model.hostSettings()
            for provider in persisted.providers where provider.kind != .chatGPTPlan {
                if serviceDrafts[provider.id] == nil { serviceDrafts[provider.id] = ServiceDraft(provider: provider) }
            }
            if drawingDraft == nil { drawingDraft = persisted.models }
        }
        .onChange(of: settings.host.providers) { _, providers in
            for provider in providers where provider.kind != .chatGPTPlan {
                if serviceDrafts[provider.id] == nil { serviceDrafts[provider.id] = ServiceDraft(provider: provider) }
            }
        }
        .onDisappear {
            for id in serviceDrafts.keys { serviceDrafts[id]?.credential = "" }
        }
    }

    private var serviceCards: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 10, alignment: .leading)],
                  alignment: .leading, spacing: 10) {
            ForEach(settings.orderedProviders) { provider in
                let selected = settings.selectedProviderID == provider.id
                Button {
                    settings.selectedProviderID = provider.id
                } label: {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(provider.displayName).inkuFont(13, weight: .semibold).lineLimit(2)
                        Text(provider.id).inkuFont(12).foregroundStyle(.secondary).lineLimit(1)
                        Text(model.display.localized(credentialStatus(provider.id)))
                            .inkuFont(12).foregroundStyle(.secondary)
                        Text(model.display.localizedFormat("使用モデル: %ld個", settings.publishedModels(for: provider).count))
                            .inkuFont(12).foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, minHeight: 90, alignment: .topLeading)
                    .padding(12)
                    .background(selected ? Color.accentColor.opacity(0.10) : Color.primary.opacity(0.025),
                                in: RoundedRectangle(cornerRadius: 10))
                    .overlay {
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(selected ? Color.accentColor : Color.primary.opacity(0.15), lineWidth: selected ? 2 : 1)
                    }
                    .contentShape(RoundedRectangle(cornerRadius: 10))
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(selected ? [.isSelected] : [])
            }
        }
    }

    private func serviceEditor(_ provider: ProviderSettings) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(provider.displayName).inkuFont(14, weight: .semibold)
                    Text(model.display.localizedFormat("サービスID: %@", provider.id))
                        .inkuFont(12, design: .monospaced).foregroundStyle(.secondary).textSelection(.enabled)
                }
                Spacer(minLength: 8)
                Button(model.display.localized("名前変更")) { sheetRoute = .service(.rename(provider.id)) }
            }
            modelSummary(provider)
            Divider()
            DisclosureGroup(model.display.localized("レート制限")) {
                rateSettings(provider).padding(.top, 10)
            }
            .id("rate-" + provider.id)
            Divider()
            DisclosureGroup(model.display.localized("接続設定")) {
                connectionSettings(provider).padding(.top, 10)
            }
            .id("connection-" + provider.id)
        }
        .padding(16)
        .background(Color.primary.opacity(0.025), in: RoundedRectangle(cornerRadius: 12))
        .overlay { RoundedRectangle(cornerRadius: 12).stroke(Color.primary.opacity(0.15)) }
    }

    private func modelSummary(_ provider: ProviderSettings) -> some View {
        let selectedModels = settings.publishedModels(for: provider)
        return VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .center, spacing: 12) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(model.display.localized("使用するモデル")).inkuFont(13).foregroundStyle(.secondary)
                    Text(model.display.localizedFormat("使用モデル: %ld個", selectedModels.count))
                        .inkuFont(13, weight: .semibold)
                }
                Spacer(minLength: 8)
                Button(model.display.localized("モデル選択")) { sheetRoute = .models(provider.id) }
            }
            if selectedModels.isEmpty {
                Text(model.display.localized("使用するモデルはありません。"))
                    .inkuFont(13).foregroundStyle(.secondary)
            } else {
                ViewThatFits(in: .vertical) {
                    modelGroups(provider)
                    ScrollView { modelGroups(provider) }.frame(height: 220)
                }
                .frame(maxHeight: 220)
            }
        }
        .padding(13)
        .background(Color.primary.opacity(0.03), in: RoundedRectangle(cornerRadius: 10))
    }

    private func modelGroups(_ provider: ProviderSettings) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(["llm", "vision"], id: \.self) { purpose in
                let models = settings.publishedModels(for: provider, purpose: purpose)
                if !models.isEmpty {
                    HStack(alignment: .top, spacing: 10) {
                        HStack(spacing: 4) {
                            Text(purpose == "llm" ? "LLM" : "Vision").fontWeight(.semibold)
                            Text("\(models.count)").foregroundStyle(.secondary)
                        }
                        .inkuFont(12).frame(width: 68, alignment: .leading).padding(.top, 5)
                        ModelSettingsChipLayout(spacing: 6) {
                            ForEach(models) { item in
                                Text(item.label).inkuFont(12)
                                    .padding(.horizontal, 9).padding(.vertical, 5)
                                    .background(Color.primary.opacity(0.04), in: Capsule())
                                    .overlay { Capsule().stroke(Color.primary.opacity(0.15)) }
                            }
                        }
                    }
                }
            }
        }
    }

    private func rateSettings(_ provider: ProviderSettings) -> some View {
        let draft = draft(for: provider)
        return VStack(alignment: .leading, spacing: 12) {
            rateField("毎分の要求数（RPM）", help: "このアプリが同じ接続先へ送る要求数です。写生文・解釈・辞書選択・構図・補完・再試行を含みます。0は上限なしです。",
                      provider: provider, key: \.rpm)
            rateField("毎分の入力トークン数（TPM）", help: "指示・記述・応答の型を含む入力の上限です。Geminiは送る前に計測し、ほかの接続先は安全側に見積もります。0は上限なしです。",
                      provider: provider, key: \.tpm)
            rateField("日次の要求数（RPD）", help: "再試行を含む1日当たりの要求数です。Geminiは太平洋時間、ほかの接続先はUTCの0時にリセットします。0は上限なしです。",
                      provider: provider, key: \.rpd)
            Text(model.display.localized("0は上限なし。毎分の枠を待ち、日次上限では生成を開始しません。"))
                .inkuFont(12).foregroundStyle(.secondary)
            Text(model.display.localized("未設定の標準Gemini接続は30／16,000／14,400、ほかの接続先は0が初期値です。契約の利用枠に合わせて設定してください。"))
                .inkuFont(12).foregroundStyle(.secondary)
            if draft.limits == nil {
                Text(model.display.localized("レート制限には0から1,000,000,000までの整数を設定してください。"))
                    .inkuFont(12).foregroundStyle(.red)
            }
            HStack {
                Spacer()
                Button(model.display.localized("保存")) { saveRates(provider) }
                    .disabled(draft.limits == nil || !draft.ratesChanged(from: provider))
            }
        }
    }

    private func rateField(_ title: String, help: String, provider: ProviderSettings,
                           key: WritableKeyPath<ServiceDraft, String>) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 6) {
                Text(model.display.localized(title)).inkuFont(13)
                Button { rateHelp = title } label: { Image(systemName: "info.circle") }
                    .buttonStyle(.plain).foregroundStyle(.secondary)
                    .accessibilityLabel(model.display.localizedFormat("%@の説明", model.display.localized(title)))
                    .inkuTooltip(model.display.preferences.showTooltips ? model.display.localized(help) : "")
                    .popover(isPresented: Binding(get: { rateHelp == title }, set: { if !$0 { rateHelp = nil } })) {
                        Text(model.display.localized(help)).inkuFont(13).padding()
                            .frame(maxWidth: 320).fixedSize(horizontal: false, vertical: true)
                    }
            }
            TextField(model.display.localized(title), text: draftBinding(provider, key))
                .textFieldStyle(.roundedBorder).autocorrectionDisabled()
                .accessibilityHint(model.display.localized(help))
        }
    }

    private func connectionSettings(_ provider: ProviderSettings) -> some View {
        let draft = draft(for: provider)
        let configured = settings.credentialStates[provider.id]
        return VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 5) {
                Text(model.display.localized("接続先URL")).inkuFont(13)
                HStack(spacing: 8) {
                    TextField(model.display.localized("接続先URL"), text: draftBinding(provider, \.url))
                        .textFieldStyle(.roundedBorder).autocorrectionDisabled()
                    Button(model.display.localized("保存")) { saveURL(provider) }
                        .disabled(draft.url == provider.baseURL.absoluteString)
                }
            }
            VStack(alignment: .leading, spacing: 5) {
                Text(model.display.localized("APIキー")).inkuFont(13)
                HStack(spacing: 8) {
                    SecureField(model.display.localized(configured == true ? "設定済みのAPIキーを保持" : "APIキー"),
                                text: configured == true ? .constant("") : draftBinding(provider, \.credential))
                        .textFieldStyle(.roundedBorder).autocorrectionDisabled()
                        .disabled(configured != false || credentialActionsDisabled)
                    if configured == true {
                        Button(model.display.localized("削除…"), role: .destructive) {
                            confirmation = .clearCredential(provider.id)
                        }.disabled(credentialActionsDisabled)
                    } else if configured == false {
                        Button(model.display.localized("保存")) { saveCredential(provider) }
                            .disabled(credentialActionsDisabled || draft.credential.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    } else {
                        Button(model.display.localized("状態を確認")) {
                            Task { await settings.inspectAllCredentials() }
                        }
                    }
                }
                Text(model.display.localized("APIキーはKeychainに保存します。設定済みのキーは表示しません。変更するには先に削除してください。"))
                    .inkuFont(12).foregroundStyle(.secondary)
            }
            HStack(spacing: 10) {
                Spacer()
                Button(model.display.localized("サービスメモ")) { sheetRoute = .service(.memo(provider.id)) }
                Button(model.display.localized("サービスを削除…"), role: .destructive) {
                    confirmation = .deleteService(provider.id)
                }
            }
        }
    }

    private var drawingDefaults: some View {
        DisclosureGroup(model.display.localized("描画の既定値")) {
            VStack(alignment: .leading, spacing: 12) {
                if !drawingChoices.isEmpty {
                    Picker(model.display.localized("描画モデル"), selection: Binding(
                        get: { drawingChoices.contains(where: { $0.id == drawingModels.stage1Model }) ? drawingModels.stage1Model : "" },
                        set: { drawingBinding(\.stage1Model).wrappedValue = $0 })) {
                        Text(model.display.localized("選択してください")).tag("")
                        ForEach(drawingChoices) { choice in
                            Text("\(choice.provider.displayName) / \(choice.model.name)").tag(choice.id)
                                .disabled(!settings.isModelAvailable(choice.id))
                        }
                    }
                } else {
                    Text(model.display.localized("使用中のLLMモデルを設定してください。")).inkuFont(12).foregroundStyle(.secondary)
                }
                if !drawingModels.stage1Model.isEmpty {
                    ModelGuidanceView(reference: drawingModels.stage1Model, providers: settings.host.providers,
                                      discovered: settings.modelCatalog.first { $0.id == drawingModels.stage1Model },
                                      display: model.display)
                }
                Stepper(model.display.localizedFormat("解釈の出力上限: %ld", drawingModels.stage1MaxTokens),
                        value: drawingBinding(\.stage1MaxTokens), in: 256...65536, step: 256)
                Stepper(model.display.localizedFormat("補完の出力上限: %ld", drawingModels.holeMaxTokens),
                        value: drawingBinding(\.holeMaxTokens), in: 256...65536, step: 256)
                Text(model.display.localized("解釈と構造化に同じモデルを使います。接続設定の保存では生成を開始しません。"))
                    .inkuFont(13).foregroundStyle(.secondary)
                HStack {
                    Spacer()
                    Button(model.display.localized("取消")) { drawingDraft = settings.host.models }.disabled(!drawingChanged)
                    Button(model.display.localized("既定値を保存")) { saveDrawingDefaults() }
                        .disabled(!drawingChanged || !SettingsModel.isBatchModelAvailable(drawingModels.stage1Model, settings: settings.host))
                }
            }
            .padding(.top, 10)
            .disabled(drawingDraft == nil)
        }
        .padding(16)
        .background(Color.primary.opacity(0.025), in: RoundedRectangle(cornerRadius: 12))
        .overlay { RoundedRectangle(cornerRadius: 12).stroke(Color.primary.opacity(0.15)) }
    }

    private var drawingChanged: Bool {
        let saved = settings.host.models
        return drawingDraft != nil && (drawingModels.stage1Model != saved.stage1Model
            || drawingModels.stage1MaxTokens != saved.stage1MaxTokens || drawingModels.holeMaxTokens != saved.holeMaxTokens)
    }

    private var confirmationTitle: String {
        model.display.localized(confirmation?.title ?? "")
    }

    private func credentialStatus(_ providerID: String) -> String {
        switch settings.credentialStates[providerID] {
        case true: "APIキー設定済み"
        case false: "APIキー未設定"
        case nil: "APIキー未確認"
        }
    }

    private func draft(for provider: ProviderSettings) -> ServiceDraft {
        serviceDrafts[provider.id] ?? ServiceDraft(provider: provider)
    }

    private func draftBinding(_ provider: ProviderSettings, _ key: WritableKeyPath<ServiceDraft, String>) -> Binding<String> {
        Binding(get: { draft(for: provider)[keyPath: key] }, set: { value in
            var next = draft(for: provider)
            next[keyPath: key] = value
            serviceDrafts[provider.id] = next
        })
    }

    private func drawingBinding<Value>(_ key: WritableKeyPath<ModelSelection, Value>) -> Binding<Value> {
        Binding(get: { drawingModels[keyPath: key] }, set: { value in
            var next = drawingModels
            next[keyPath: key] = value
            drawingDraft = next
        })
    }

    private func saveURL(_ provider: ProviderSettings) {
        let value = draft(for: provider).url
        perform {
            try await settings.saveProviderURL(providerID: provider.id, value: value, model: model)
            if let saved = settings.host.providers.first(where: { $0.id == provider.id }) {
                var next = draft(for: saved)
                next.url = saved.baseURL.absoluteString
                serviceDrafts[provider.id] = next
            }
        }
    }

    private func saveRates(_ provider: ProviderSettings) {
        guard let limits = draft(for: provider).limits else { return }
        perform {
            try await settings.saveProviderRateLimits(providerID: provider.id, limits: limits, model: model)
            if let saved = settings.host.providers.first(where: { $0.id == provider.id }) {
                var next = draft(for: saved)
                let effective = saved.effectiveRateLimits
                next.rpm = String(effective.requestsPerMinute)
                next.tpm = String(effective.tokensPerMinute)
                next.rpd = String(effective.requestsPerDay)
                serviceDrafts[provider.id] = next
            }
        }
    }

    private func saveCredential(_ provider: ProviderSettings) {
        guard !credentialActionsDisabled, settings.credentialStates[provider.id] == false else { return }
        let key = draft(for: provider).credential
        perform {
            guard !credentialsLocked else { throw HostError("settings_busy_or_unavailable") }
            try await settings.saveProviderCredential(providerID: provider.id, key: key, model: model)
            if var next = serviceDrafts[provider.id] {
                next.credential = ""
                serviceDrafts[provider.id] = next
            }
        }
    }

    private func saveDrawingDefaults() {
        var next = drawingModels
        next.stage2Model = next.stage1Model
        let models = next
        perform {
            try await settings.saveDrawingDefaults(models: models, model: model)
            drawingDraft = models
        }
    }

    private func confirm(_ action: Confirmation) {
        guard !confirmationDisabled(action) else { return }
        perform {
            switch action {
            case .clearCredential(let providerID):
                guard !credentialsLocked else { throw HostError("settings_busy_or_unavailable") }
                try await settings.clearProviderCredential(providerID: providerID, model: model)
                if var next = serviceDrafts[providerID] {
                    next.credential = ""
                    serviceDrafts[providerID] = next
                }
            case .deleteService(let providerID):
                try await settings.deleteProvider(providerID: providerID, model: model)
                serviceDrafts[providerID] = nil
                if var next = drawingDraft {
                    if next.stage1Model.hasPrefix(providerID + ":") { next.stage1Model = "" }
                    if next.stage2Model.hasPrefix(providerID + ":") { next.stage2Model = "" }
                    drawingDraft = next
                }
            }
        }
    }

    private func confirmationDisabled(_ action: Confirmation) -> Bool {
        switch action {
        case .clearCredential: credentialActionsDisabled
        case .deleteService: actionsDisabled
        }
    }

    private func perform(_ operation: @escaping @MainActor () async throws -> Void) {
        guard !actionsDisabled else { return }
        saving = true
        Task {
            do { try await operation() }
            catch { settings.error = errorMessage(error) }
            saving = false
        }
    }

    private func errorMessage(_ error: Error) -> String {
        switch (error as? HostError)?.code {
        case "provider_base_url_invalid":
            "接続先URLには認証情報・クエリ・フラグメントを含まないhttpまたはhttpsのURLを指定してください。"
        case "invalid_provider_rate_limits":
            "レート制限には0から1,000,000,000までの整数を設定してください。"
        case "credentials_unavailable":
            "APIキーの状態を確認できません。"
        case "credentials_write_failed":
            "APIキーを保存または削除できませんでした。"
        default:
            error.localizedDescription
        }
    }

    private struct ServiceDraft {
        var url: String
        var rpm: String
        var tpm: String
        var rpd: String
        var credential = ""

        init(provider: ProviderSettings) {
            url = provider.baseURL.absoluteString
            let limits = provider.effectiveRateLimits
            rpm = String(limits.requestsPerMinute)
            tpm = String(limits.tokensPerMinute)
            rpd = String(limits.requestsPerDay)
        }

        var limits: ProviderRateLimits? {
            guard let rpm = Self.integer(rpm), let tpm = Self.integer(tpm), let rpd = Self.integer(rpd) else { return nil }
            return .init(requestsPerMinute: rpm, tokensPerMinute: tpm, requestsPerDay: rpd)
        }

        func ratesChanged(from provider: ProviderSettings) -> Bool {
            guard let limits else { return true }
            let saved = provider.effectiveRateLimits
            return limits.requestsPerMinute != saved.requestsPerMinute || limits.tokensPerMinute != saved.tokensPerMinute
                || limits.requestsPerDay != saved.requestsPerDay
        }

        private static func integer(_ value: String) -> Int? {
            let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty, trimmed.allSatisfy({ "0123456789".contains($0) }),
                  let parsed = Int(trimmed), (0...1_000_000_000).contains(parsed) else { return nil }
            return parsed
        }
    }

    private struct DrawingChoice: Identifiable {
        let provider: ProviderSettings
        let model: ProviderModelInfo
        var id: String { model.id }
    }

    private enum SheetRoute: Identifiable {
        case service(ProviderServiceEditorMode)
        case models(String)
        var id: String {
            switch self {
            case .service(let mode): "service-" + mode.id
            case .models(let providerID): "models-" + providerID
            }
        }
    }

    private enum Confirmation {
        case clearCredential(String)
        case deleteService(String)
        var providerID: String {
            switch self { case .clearCredential(let id), .deleteService(let id): id }
        }
        var title: String {
            switch self {
            case .clearCredential: "この接続のAPIキーを削除します"
            case .deleteService: "このサービスを削除します"
            }
        }
        var buttonTitle: String {
            switch self {
            case .clearCredential: "APIキーを削除"
            case .deleteService: "サービスを削除"
            }
        }
    }
}

private struct ModelSettingsChipLayout: Layout {
    let spacing: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        arrange(subviews, width: proposal.width ?? .infinity).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let placement = arrange(subviews, width: bounds.width)
        for (index, point) in placement.points.enumerated() {
            subviews[index].place(at: CGPoint(x: bounds.minX + point.x, y: bounds.minY + point.y),
                                 anchor: .topLeading, proposal: ProposedViewSize(placement.sizes[index]))
        }
    }

    private func arrange(_ subviews: Subviews, width: CGFloat) -> (size: CGSize, points: [CGPoint], sizes: [CGSize]) {
        var points: [CGPoint] = []
        var sizes: [CGSize] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        var measuredWidth: CGFloat = 0
        let available = max(0, width)
        for subview in subviews {
            let size = subview.sizeThatFits(ProposedViewSize(width: available.isFinite ? available : nil, height: nil))
            if x > 0, x + size.width > available {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            points.append(CGPoint(x: x, y: y))
            sizes.append(size)
            measuredWidth = max(measuredWidth, x + size.width)
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
        }
        return (CGSize(width: available.isFinite ? available : measuredWidth, height: y + rowHeight), points, sizes)
    }
}
