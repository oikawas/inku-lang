import InkuHost
import InkuPersistence
import SwiftUI

@MainActor
public struct RefinementView: View {
    @Bindable private var model: AppModel
    @State private var refinement: RefinementModel
    @State private var closing = false
    @Environment(\.dismiss) private var dismiss
    private let onCommitted: @MainActor () -> Void
    private let onConfigureModels: @MainActor (String) -> Void

    public init(model: AppModel, work: SavedWork, onCommitted: @escaping @MainActor () -> Void = {},
                onConfigureModels: @escaping @MainActor (String) -> Void = { _ in }) {
        self.model = model
        self.onCommitted = onCommitted
        self.onConfigureModels = onConfigureModels
        _refinement = State(initialValue: RefinementModel(work: work))
    }

    public var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .firstTextBaseline) {
                Text(model.display.localized("描画要素を編集")).font(.title2.weight(.semibold))
                Spacer()
                Button { Task { await close() } } label: { Image(systemName: "xmark") }
                    .buttonStyle(.plain)
                    .accessibilityLabel(model.display.localized(refinement.hasUnsaved ? "破棄して閉じる" : "閉じる"))
                    .help(model.display.preferences.showTooltips ? model.display.localized(refinement.hasUnsaved ? "破棄して閉じる" : "閉じる") : "")
                    .disabled(closeDisabled)
            }.padding(20)
            Divider()
            ScrollViewReader { proxy in
              ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    parentCard
                    adjustmentControls
                    generationControls
                    if refinement.running { progressCard }
                    if !refinement.candidates.isEmpty { candidateSection.id("refinement-candidates") }
                    Text(model.display.message(refinement.status)).font(.callout).foregroundStyle(.secondary)
                    if let error = refinement.errorText {
                        Text(model.display.message(error)).foregroundStyle(.red).textSelection(.enabled)
                    }
                    ForEach(refinement.slots.filter { $0.error != nil }) { slot in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(model.display.localizedFormat("候補 %ld", slot.id)).font(.caption.weight(.semibold))
                            Text(model.display.message(slot.error ?? "")).font(.callout).textSelection(.enabled)
                        }.foregroundStyle(.red)
                    }
                }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
              }
              .onChange(of: refinement.candidates.count) { _, count in
                  if count > 0 { withAnimation { proxy.scrollTo("refinement-candidates", anchor: .top) } }
              }
            }
            Divider()
            footer.padding(20).background(.bar)
        }
        #if os(macOS)
        .frame(minWidth: 640, idealWidth: 880, minHeight: 550, idealHeight: 740)
        #endif
        .task { await refinement.initialize(app: model) }
        .interactiveDismissDisabled(refinement.running || refinement.hasUnsaved || model.isBusy || closing)
        .onDisappear {
            Task { _ = await refinement.close(app: model) }
        }
    }

    private var controlsDisabled: Bool { refinement.running || model.isBusy || closing || refinement.closed }
    private var closeDisabled: Bool { closing || refinement.stopping || model.isBusy && !refinement.running }

    private var parentCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(model.display.localized("元の作品")).font(.headline)
            HStack(alignment: .top, spacing: 14) {
                ArtworkThumbnail(work: refinement.work, renderer: model.renderer)
                    .frame(width: 120, height: 120).clipped()
                    .accessibilityLabel(model.display.localized("元の作品"))
                Text(refinement.work.effectiveSourceText).font(.callout).lineLimit(4)
                    .fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                    .help(model.display.preferences.showTooltips ? refinement.work.effectiveSourceText : "")
                    .frame(maxWidth: .infinity, minHeight: 72, alignment: .topLeading)
            }.frame(minHeight: 120, alignment: .top)
            workFacts(refinement.work)
            Text(model.display.localized("候補を用意しても、元の作品と履歴は変わりません。採用した候補だけを子として保存します。"))
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }.frame(minHeight: 210, alignment: .top).refinementPanel()
    }

    private var adjustmentControls: some View {
        @Bindable var refinement = refinement
        return VStack(alignment: .leading, spacing: 14) {
            Text(model.display.localized("変更する要素を1つ選択")).font(.headline)
            LazyVGrid(columns: [GridItem(.flexible(minimum: 120)), GridItem(.flexible(minimum: 120))], alignment: .leading, spacing: 10) {
                ForEach(RefinementKind.allCases.filter { !self.refinement.sourceIsDDLOrigin || $0 != .reading }, id: \.self) { kind in
                    kindButton(kind)
                }
            }
            if self.refinement.sourceIsLocked {
                Label(model.display.localized("この作品はDDLが確定しているため、記述を読み直せません。配置・変奏・タッチの候補は用意できます。"), systemImage: "lock")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Text(model.display.localized(kindDescription)).font(.callout).foregroundStyle(.secondary)
            if self.refinement.kind == .touch {
                TextField(model.display.localized("タッチへ託す言葉"), text: $refinement.words, axis: .vertical)
                    .lineLimit(1...3).textFieldStyle(.roundedBorder)
                    .accessibilityLabel(model.display.localized("タッチへ託す言葉"))
                    .disabled(controlsDisabled)
                Text(model.display.localized("タッチの変更では、元の配色・配置・ワイルド設定を保ちます。"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            if self.refinement.kind == .variation {
                Picker(model.display.localized("変奏の幅"), selection: $refinement.amplitude) {
                    Text(model.display.preferences.language == "en" ? model.display.localized("控えめな変奏") : model.display.localized("小")).tag("small")
                    Text(model.display.preferences.language == "en" ? model.display.localized("中程度の変奏") : model.display.localized("中")).tag("medium")
                    Text(model.display.preferences.language == "en" ? model.display.localized("大きな変奏") : model.display.localized("大")).tag("large")
                }.pickerStyle(.segmented).frame(maxWidth: 360).disabled(controlsDisabled)
                Text(model.display.localized("小・中・大のどれを選んでも、いまの変奏で動くものはありません。"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            if self.refinement.kind != .touch {
                Toggle(model.display.localized("元のワイルド設定を引き継ぐ"), isOn: $refinement.inheritWild)
                    .disabled(controlsDisabled)
                if !self.refinement.inheritWild {
                    Toggle(model.display.localized("ワイルド"), isOn: $refinement.wildOverride).disabled(controlsDisabled)
                    if self.refinement.kind == .variation {
                        Text(model.display.localized("変奏で動くものはありませんが、ワイルド設定は元の作品から変更します。"))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            Divider()
            if self.refinement.kind == .reading {
                VStack(alignment: .leading, spacing: 6) {
                    Text(model.display.localized("描画モデル")).font(.subheadline.weight(.semibold))
                    Text(model.display.localizedFormat("次のモデル: %@", readingModel.isEmpty ? model.display.localized("未設定") : readingModel))
                        .font(.callout).textSelection(.enabled)
                    Text(model.display.localized("制作で選んだ次の描画モデルを、読み取りと構造化の両方に使います。"))
                        .font(.caption).foregroundStyle(.secondary)
                    if !model.hasNextDrawingModel { settingsButton }
                }
            } else if self.refinement.kind == .layout {
                RefinementDrawingModelPicker(model: model, reference: $refinement.modelReference, disabled: controlsDisabled,
                    configurationDisabled: controlsDisabled || self.refinement.hasUnsaved,
                    onConfigureModels: { section in Task { await configureModels(section) } })
            } else if self.refinement.kind == .variation {
                Text(model.display.localized("変奏では元の作品のモデルを保ちます。"))
                    .font(.caption).foregroundStyle(.secondary)
            }
        }.refinementPanel()
    }

    private var readingModel: String {
        refinement.running || !refinement.candidates.isEmpty ? refinement.capturedStage1Model ?? "" : model.nextDrawingModelReference
    }

    private var kindDescription: String {
        switch refinement.kind {
        case .layout: "元の指示書を使い、配置を変えます。記述は読み直しません。"
        case .reading: "元の記述を読み直して描きます。"
        case .variation: "いまの変奏では、指示書・配色・タッチ・要素数は変わりません。"
        case .touch: "同じ言葉は同じタッチ（シード）になります。1案だけ用意できます。"
        }
    }

    private func kindButton(_ kind: RefinementKind) -> some View {
        let selected = refinement.kind == kind
        let locked = kind == .reading && refinement.sourceIsLocked
        return Button { refinement.kind = kind } label: {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: kind.symbol).frame(width: 18)
                Text(model.display.localized(kind.titleKey)).font(.callout.weight(.semibold))
                    .frame(maxWidth: .infinity, alignment: .leading).multilineTextAlignment(.leading)
                Image(systemName: selected ? "checkmark.circle.fill" : locked ? "lock.fill" : "circle")
                    .accessibilityHidden(true)
            }.padding(12).frame(maxWidth: .infinity, minHeight: 55, alignment: .leading)
                .background(selected ? Color.accentColor.opacity(0.12) : Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 10))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(selected ? Color.accentColor : Color.secondary.opacity(0.2)))
        }.buttonStyle(.plain).disabled(controlsDisabled || !refinement.initialized || locked)
            .accessibilityLabel(model.display.localized(kind.titleKey))
            .accessibilityValue(model.display.localized(selected ? "選択済み" : "未選択"))
            .accessibilityAddTraits(selected ? .isSelected : [])
    }

    private var generationControls: some View {
        VStack(alignment: .leading, spacing: 10) {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 12) { generateButton(count: 1); generateButton(count: 4) }.fixedSize(horizontal: true, vertical: false)
                VStack(alignment: .leading, spacing: 10) { generateButton(count: 1); generateButton(count: 4) }
            }
            if refinement.kind == .reading && !model.hasNextDrawingModel {
                Text(model.display.localized("描画モデルが未設定です。設定でAIサービスとモデルを選択してください。"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            if refinement.hasUnsaved {
                Text(model.display.localized("別の候補を描くには、今の候補を採用するか破棄してください。"))
                    .font(.caption).foregroundStyle(.secondary)
                Button(model.display.localized("候補を破棄"), role: .destructive) { refinement.discardCandidates() }
                    .disabled(controlsDisabled)
            }
        }
    }

    private func generateButton(count: Int) -> some View {
        Button(model.display.localized(count == 1 ? "1案を描く" : "4案を描く"), systemImage: count == 1 ? "paintbrush" : "square.grid.2x2") {
            Task { await refinement.generate(app: model, count: count) }
        }.buttonStyle(.bordered)
            .disabled(!refinement.canGenerate(count: count) || controlsDisabled || model.isPreview
                || refinement.kind == .reading && !model.hasNextDrawingModel)
            .help(model.display.preferences.showTooltips && count == 4 && refinement.kind == .touch
                ? model.display.localized("タッチの候補は1案だけ用意できます。") : "")
    }

    private var progressCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                ProgressView().controlSize(.small)
                Text(model.display.localized(refinement.saving ? "選択した候補を保存中" : "候補の準備中")).font(.headline)
                Spacer()
                Button(model.display.localized(refinement.stopping ? "停止中" : "停止"), role: .destructive) {
                    Task { await refinement.stop(app: model) }
                }.disabled(refinement.stopping || closing)
            }
            if !refinement.saving {
                ProgressView(value: Double(refinement.completedCount), total: Double(max(1, refinement.slots.count)))
                    .accessibilityLabel(model.display.localized("候補の進捗"))
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 140))], alignment: .leading, spacing: 8) {
                    ForEach(refinement.slots) { slot in
                        Label(model.display.localizedFormat("候補 %ld: %@", slot.id, model.display.localized(slotLabel(slot))), systemImage: slotSymbol(slot))
                            .font(.caption).foregroundStyle(slot.state == .failed ? Color.red : Color.secondary)
                    }
                }
            }
            if model.isBusy { Text(model.display.message(model.status)).font(.caption).foregroundStyle(.secondary) }
            if let stage1 = refinement.capturedStage1Model, !stage1.isEmpty {
                Text(model.display.localizedFormat("読み取りモデル: %@", stage1)).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
            }
            if let stage2 = refinement.capturedStage2Model, !stage2.isEmpty {
                Text(model.display.localizedFormat("構造化モデル: %@", stage2)).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
            }
        }.refinementPanel()
    }

    private func slotLabel(_ slot: RefinementSlot) -> String {
        switch slot.state { case .waiting: "待機中"; case .running: "描画中"; case .ready: "準備完了"; case .failed: "失敗" }
    }

    private func slotSymbol(_ slot: RefinementSlot) -> String {
        switch slot.state { case .waiting: "clock"; case .running: "paintbrush"; case .ready: "checkmark.circle"; case .failed: "exclamationmark.triangle" }
    }

    private var candidateSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(model.display.localized("候補を比較")).font(.headline)
                Spacer()
                if refinement.previewID != nil {
                    Button(model.display.localized("すべての候補を表示")) { refinement.preview(nil) }.disabled(controlsDisabled)
                }
            }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 220), spacing: 14)], alignment: .leading, spacing: 14) {
                ForEach(refinement.candidates.filter { refinement.previewID == nil || $0.id == refinement.previewID }) { candidate in
                    candidateCard(candidate)
                }
            }
        }
    }

    private func candidateCard(_ candidate: RefinementCandidate) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Button { refinement.preview(refinement.previewID == candidate.id ? nil : candidate.id) } label: {
                ArtworkThumbnail(work: candidate.work, renderer: model.renderer)
                    .frame(height: refinement.previewID == candidate.id ? 300 : 185)
            }.buttonStyle(.plain).disabled(controlsDisabled)
                .accessibilityLabel(model.display.localizedFormat(refinement.previewID == candidate.id ? "候補 %ld の拡大を戻す" : "候補 %ld を拡大", candidate.number))
            Text(model.display.localizedFormat("候補 %ld", candidate.number)).font(.headline)
            Text(model.display.localized(candidate.kind.titleKey)).font(.caption).foregroundStyle(.secondary)
            workFacts(candidate.work)
            if candidate.kind == .variation {
                Text(model.display.localized("動いたもの: なし")).font(.caption.weight(.semibold))
            }
            if candidate.savedWork != nil {
                Label(model.display.localized("保存済み"), systemImage: "checkmark.circle.fill").font(.callout).foregroundStyle(.secondary)
            } else {
                Toggle(model.display.localized("この候補を採用"), isOn: Binding(
                    get: { candidate.selected }, set: { refinement.selectCandidate(candidate.id, selected: $0) }))
                    .disabled(controlsDisabled)
                    .accessibilityLabel(model.display.localizedFormat("候補 %ld を採用", candidate.number))
                Text(model.display.localized("未保存")).font(.caption).foregroundStyle(.secondary)
            }
            if candidate.kind == .reading, let ddl = candidate.work.ddl, !ddl.isEmpty {
                DisclosureGroup(model.display.localized("指示書")) {
                    Text(ddl).font(.caption.monospaced()).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                }.font(.caption)
            }
        }.padding(14).frame(maxWidth: .infinity, alignment: .leading)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(candidate.selected ? Color.accentColor : Color.secondary.opacity(0.2), lineWidth: candidate.selected ? 2 : 1))
    }

    private func workFacts(_ work: SavedWork) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(model.display.localizedFormat("配色 %@ · シード %@", work.renderColorCatalogID ?? work.catalogID ?? model.display.localized("不明"), work.renderSeed ?? model.display.localized("不明")))
            Text(model.display.localizedFormat("配置シード: %@", work.compositionSeed ?? work.renderSeed ?? model.display.localized("不明")))
            if let seed = work.interpretationSeed, !seed.isEmpty {
                Text(model.display.localizedFormat("読み取りシード: %@", seed))
            }
            if let seedText = work.seedText, !seedText.isEmpty {
                Text(model.display.localizedFormat("タッチの言葉: %@", seedText))
            }
        }.font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
    }

    private var footer: some View {
        VStack(alignment: .leading, spacing: 10) {
            if !refinement.committedWorks.isEmpty {
                Text(model.display.localizedFormat("保存済み: %ld案", refinement.committedWorks.count)).font(.caption).foregroundStyle(.secondary)
            }
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 12) { discardButton; saveButton }.fixedSize(horizontal: true, vertical: false)
                VStack(alignment: .leading, spacing: 10) { saveButton; discardButton }
            }.frame(maxWidth: .infinity, alignment: .trailing)
        }
    }

    private var discardButton: some View {
        Button(model.display.localized(refinement.hasUnsaved ? "破棄して閉じる" : "閉じる"), role: refinement.hasUnsaved ? .destructive : nil) {
            Task { await close() }
        }.disabled(closeDisabled).keyboardShortcut(.cancelAction)
    }

    private var saveButton: some View {
        Button(model.display.localizedFormat("選択した%ld案を採用して閉じる", refinement.selectedCount), systemImage: "checkmark.circle") {
            Task {
                let before = refinement.committedWorks.count
                let succeeded = await refinement.saveSelected(app: model)
                if refinement.committedWorks.count > before { onCommitted() }
                if succeeded && !refinement.running && !refinement.hasUnsaved && !model.isBusy && !closing { dismiss() }
            }
        }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
            .disabled(!refinement.canSave || model.isBusy || model.isPreview || closing)
    }

    private var settingsButton: some View {
        Button(model.display.localized("モデル設定"), systemImage: "gearshape") {
            Task { await configureModels("models") }
        }.disabled(controlsDisabled || refinement.hasUnsaved)
    }

    private func configureModels(_ section: String) async {
        guard !closing, !refinement.running, !refinement.hasUnsaved, !model.isBusy else { return }
        closing = true
        if await refinement.close(app: model) {
            onConfigureModels(section)
            dismiss()
        } else { closing = false }
    }

    private func close() async {
        guard !closing else { return }
        closing = true
        let succeeded = await refinement.close(app: model)
        if succeeded { dismiss() }
        else { closing = false }
    }
}

private extension View {
    func refinementPanel() -> some View {
        padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(.quaternary))
    }
}

/// The sheet's Stage 2 choice is local; Settings remain authoritative.
@MainActor
private struct RefinementDrawingModelPicker: View {
    @Bindable var model: AppModel
    @Binding var reference: String
    let disabled: Bool
    let configurationDisabled: Bool
    let onConfigureModels: @MainActor (String) -> Void
    @State private var settings = SettingsModel()
    @State private var providerID: String?
    @State private var personalModels: [ProviderModelInfo] = []
    @State private var loadingPersonalModels = false
    @State private var catalogError: String?
    @State private var discovery: Task<Void, Never>?

    private var provider: ProviderSettings? { settings.host.providers.first { $0.id == providerID } }
    private var loading: Bool { settings.isLoadingModels || loadingPersonalModels }
    private var models: [ProviderModelInfo] {
        guard let provider else { return [] }
        var seen: Set<String> = []
        let configured = [reference, model.nextDrawingModelReference, settings.host.models.stage1Model, settings.host.models.stage2Model]
            .filter { $0.hasPrefix(provider.id + ":") && $0.count > provider.id.count + 1 }
            .map { ProviderModelInfo(id: $0, name: String($0.dropFirst(provider.id.count + 1)), contextLimit: nil, capabilities: []) }
        return ((provider.kind == .chatGPTPlan ? personalModels : settings.modelCatalog) + configured)
            .filter { $0.id.hasPrefix(provider.id + ":") && seen.insert($0.id).inserted }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(model.display.localized("描画モデル")).font(.subheadline.weight(.semibold))
            Text(model.display.localized("この操作では、選んだモデルを構造化に使います。"))
                .font(.caption).foregroundStyle(.secondary)
            if !settings.host.providers.isEmpty {
                Picker(model.display.localized("サービス"), selection: Binding(get: { providerID }, set: { selectProvider($0) })) {
                    ForEach(settings.host.providers) { item in Text(item.id).tag(Optional(item.id)) }
                }.disabled(disabled || loading)
                Picker(model.display.localized("モデル"), selection: Binding(
                    get: { models.contains(where: { $0.id == reference }) ? reference : "" }, set: { reference = $0 })) {
                    Text(model.display.localized("制作で選んだ次のモデルを使う")).tag("")
                    ForEach(models) { item in Text(item.name).tag(item.id) }
                }.disabled(disabled || loading || models.isEmpty)
                Text(model.display.localizedFormat("次のモデル: %@", reference.isEmpty ? model.nextDrawingModelReference : reference))
                    .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                Button {
                    discovery = Task { await discoverModels() }
                } label: {
                    Label(model.display.localized(loading ? "取得中…" : "接続先からモデル一覧を取得"), systemImage: "arrow.clockwise").font(.caption)
                }.disabled(disabled || loading || provider == nil)
            }
            Button(model.display.localized("モデル設定"), systemImage: "gearshape") {
                onConfigureModels(provider?.kind == .chatGPTPlan ? "personalPlan" : "models")
            }.disabled(configurationDisabled)
            if let catalogError { Text(model.display.message(catalogError)).font(.caption).foregroundStyle(.red) }
        }
        .task(id: model.providerSettingsRevision) {
            discovery?.cancel(); settings.cancelDiscovery()
            let revision = model.providerSettingsRevision
            let snapshot = await model.hostSettings()
            guard !Task.isCancelled, revision == model.providerSettingsRevision else { return }
            let refreshed = SettingsModel()
            refreshed.host = snapshot
            settings = refreshed; personalModels = []; catalogError = nil
            if !reference.isEmpty && !snapshot.providers.contains(where: { reference.hasPrefix($0.id + ":") }) { reference = "" }
            providerID = snapshot.providers.first(where: { reference.hasPrefix($0.id + ":") })?.id ?? snapshot.providers.first?.id
        }
        .onDisappear { discovery?.cancel(); settings.cancelDiscovery() }
    }

    private func selectProvider(_ id: String?) {
        guard !disabled, !loading else { return }
        discovery?.cancel(); settings.cancelDiscovery()
        providerID = id; personalModels = []; catalogError = nil
        if let id, !reference.hasPrefix(id + ":") { reference = "" }
    }

    private func discoverModels() async {
        guard !disabled, !model.isBusy, !loading, let provider else { return }
        let revision = model.providerSettingsRevision
        catalogError = nil
        if provider.kind == .chatGPTPlan {
            loadingPersonalModels = true
            defer { loadingPersonalModels = false }
            do {
                let offered = try await model.personalPlanRuntime().models(force: true)
                guard !Task.isCancelled, providerID == provider.id, revision == model.providerSettingsRevision else { return }
                personalModels = offered.map { ProviderModelInfo(id: provider.id + ":" + $0.id, name: $0.label, contextLimit: nil, capabilities: []) }
            } catch {
                guard !Task.isCancelled, revision == model.providerSettingsRevision else { return }
                catalogError = error.localizedDescription
            }
        } else {
            settings.selectedProviderID = provider.id
            await settings.discoverModels()
            guard !Task.isCancelled, providerID == provider.id, revision == model.providerSettingsRevision else { return }
            catalogError = settings.error
        }
    }
}
