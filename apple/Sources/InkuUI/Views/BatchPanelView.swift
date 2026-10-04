import InkuPersistence
import SwiftUI

@MainActor
struct BatchPanelView: View {
    @Bindable var model: AppModel
    @Bindable var automation: AutomationModel
    @State private var replaceBatch = false
    @State private var resultsExpanded = false
    @State private var issuesExpanded = false
    @State private var conditionsExpanded = false
    @State private var workspaceTab = "work"
    @State private var selectedHistoryPrompt = ""

    private var controlsDisabled: Bool { automation.isOccupied || model.isBusy }
    private var canStartNewBatch: Bool {
        !controlsDisabled && automation.nonEmptyBatchCount > 0
            && model.hasAvailableBatchDrawingModel
    }
    private var issueRows: [BatchRow] { automation.rows.filter { $0.state == .failed || $0.state == .uncertain } }
    private var displayedWork: SavedWork? {
        automation.observedWork ?? model.selectedWork
    }
    private var workspaceMinimumHeight: CGFloat {
        automation.running && conditionsExpanded ? 620 : 500
    }

    var body: some View {
        GeometryReader { geometry in
            if geometry.size.width >= 840 {
                HStack(alignment: .top, spacing: 16) {
                    inputPane.frame(width: 410)
                    Divider()
                    workspacePane(height: geometry.size.height)
                }
                .frame(width: geometry.size.width, height: geometry.size.height, alignment: .topLeading)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        inputContent
                        Divider()
                        workspace.frame(height: max(workspaceMinimumHeight, geometry.size.height * 0.85))
                    }
                    .frame(minWidth: 0, maxWidth: .infinity, alignment: .leading)
                    .padding(.bottom, 12)
                }
                .frame(width: geometry.size.width, height: geometry.size.height, alignment: .topLeading)
            }
        }
        .clipped()
        .confirmationDialog(model.display.localized("前回のバッチ記録を新しいバッチで置き換えます"),
                            isPresented: $replaceBatch, titleVisibility: .visible) {
            Button(model.display.localized("新しいバッチを描く")) { startNewBatch() }
                .disabled(!canStartNewBatch)
            Button(model.display.localized("キャンセル"), role: .cancel) {}
        } message: {
            Text(model.display.localized("保存済み作品は残ります。未処理の行を再開する場合は「前回のバッチを再開」を選んでください。"))
        }
        .onAppear { if automation.uncertainCount > 0 { issuesExpanded = true } }
        .onChange(of: automation.uncertainCount) { _, count in
            if count > 0 { issuesExpanded = true }
        }
        .onChange(of: automation.isOccupied) { _, occupied in
            if occupied { replaceBatch = false }
        }
    }

    private var inputPane: some View {
        ScrollView {
            inputContent.padding(.trailing, 2).padding(.bottom, 12)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .clipped()
    }

    private var inputContent: some View {
        VStack(alignment: .leading, spacing: 12) {
            input
            if automation.canResume && !automation.running { resumeCard }
            Divider()
            BatchConditionsView(model: model, automation: automation)
            actions
            if !automation.rows.isEmpty { resultSummary }
            if !issueRows.isEmpty { issueResults }
            if !automation.rows.isEmpty { allResults }
        }
        .frame(minWidth: 0, maxWidth: .infinity, alignment: .leading)
    }

    private var input: some View {
        VStack(alignment: .leading, spacing: 8) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .firstTextBaseline, spacing: 8) { inputHeading }
                VStack(alignment: .leading, spacing: 4) { inputHeading }
            }
            if automation.running, let row = automation.activeRow {
                VStack(alignment: .leading, spacing: 6) {
                    Label(model.display.localizedFormat("処理中: %ld行", row.line), systemImage: "play.fill")
                        .font(.caption.weight(.semibold)).monospacedDigit()
                    Text(row.input).font(.callout).lineLimit(4).textSelection(.enabled)
                }
                .padding(10).frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 8))
            } else {
                BatchInputEditor(text: $automation.batchText, isEditable: !controlsDisabled,
                                 accessibilityLabel: model.display.localized("バッチ入力"))
                    .frame(height: 220)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
                if automation.nonEmptyBatchCount > 0 {
                    Text(model.display.localizedFormat("空行を除く入力: %ld件", automation.nonEmptyBatchCount))
                        .font(.caption).foregroundStyle(.secondary).monospacedDigit()
                }
                if !automation.batchPromptHistory.isEmpty {
                    inputHistory
                }
            }
            Text(model.display.localized("空行を除き、元の行番号を保持して順に描きます。"))
                .font(.caption).foregroundStyle(.secondary)
            if let error = automation.historyErrorText {
                Text(model.display.message(error)).font(.caption).foregroundStyle(.red).textSelection(.enabled)
            }
        }
    }

    @ViewBuilder private var inputHeading: some View {
        Text(model.display.localized("バッチ")).font(.callout.weight(.semibold))
        Text(model.display.localized("1行に1つの記述を入力"))
            .font(.caption).foregroundStyle(.secondary)
    }

    private var inputHistory: some View {
        Menu {
            ForEach(Array(automation.batchPromptHistory.enumerated()), id: \.offset) { _, text in
                Button(historyLabel(text)) {
                    guard !controlsDisabled else { return }
                    selectedHistoryPrompt = text
                    automation.restoreBatchInput(text)
                }
            }
        } label: {
            HStack(spacing: 6) {
                Text(selectedHistoryPrompt.isEmpty ? model.display.localized("履歴から選択") : historyLabel(selectedHistoryPrompt))
                    .lineLimit(1).truncationMode(.tail)
                Spacer(minLength: 0)
                Image(systemName: "chevron.down").font(.caption2)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 8).padding(.vertical, 6)
            .contentShape(Rectangle())
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .frame(maxWidth: .infinity, minHeight: 28, alignment: .leading)
        .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 6))
        .overlay(RoundedRectangle(cornerRadius: 6).stroke(.quaternary))
        .controlSize(.small)
        .disabled(controlsDisabled || automation.batchPromptHistory.isEmpty)
        .accessibilityLabel(model.display.localized("入力履歴"))
        .accessibilityValue(selectedHistoryPrompt.isEmpty ? model.display.localized("履歴から選択") : historyLabel(selectedHistoryPrompt))
        .help(tip("選んだ履歴をバッチ入力欄へ復元します。実行記録と保存作品は変わりません。"))
    }

    private func historyLabel(_ text: String) -> String {
        let first = text.components(separatedBy: .newlines).first { !$0.trimmingCharacters(in: .whitespaces).isEmpty } ?? text
        return first.count > 70 ? String(first.prefix(70)) + "…" : first
    }

    private var resumeCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(model.display.localized("前回のバッチを再開"), systemImage: "arrow.clockwise")
                .font(.subheadline.weight(.semibold))
            if let line = automation.nextPendingLine {
                Text(model.display.localizedFormat("次は%ld行・残り%ld件（全%ld件）", line, automation.pendingCount, automation.rows.count))
                    .font(.caption).monospacedDigit()
            } else {
                Text(model.display.localizedFormat("残り%ld件（全%ld件）", automation.pendingCount, automation.rows.count))
                    .font(.caption).monospacedDigit()
            }
            frozenConditions
            if automation.uncertainCount > 0 {
                Text(model.display.localized("要確認の行を確認してから再開してください。"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            Button(model.display.localized("前回のバッチを再開")) { Task { await automation.resumeBatch(app: model) } }
                .frame(maxWidth: .infinity, alignment: .leading)
                .disabled(controlsDisabled || automation.uncertainCount > 0)
                .help(tip("前回の開始時の条件で、未処理の行と失敗した行を再開します。"))
        }
        .padding(12).frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(.quaternary))
    }

    private var actions: some View {
        VStack(alignment: .leading, spacing: 8) {
            if automation.preparing {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text(model.display.localized("バッチを準備中…")).font(.callout)
                }
            } else if automation.running {
                Button(model.display.localized(automation.stopping ? "停止中" : "停止"), systemImage: "stop.fill") {
                    Task { await automation.stop(app: model) }
                }
                .buttonStyle(.bordered).disabled(automation.stopping)
                .help(tip("実行中のバッチを停止します。未処理の行は後で再開できます。"))
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 8) { newBatchLabel; newBatchButton }
                    VStack(alignment: .leading, spacing: 6) { newBatchLabel; newBatchButton }
                }
                if !model.hasAvailableBatchDrawingModel {
                    Text(model.display.message("drawing_model_not_available"))
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            if !automation.status.isEmpty && !automation.preparing {
                Text(model.display.message(automation.status)).font(.caption).foregroundStyle(.secondary)
                    .lineLimit(3).textSelection(.enabled)
            }
            if let error = automation.errorText {
                Text(model.display.message(error)).font(.caption).foregroundStyle(.red).textSelection(.enabled)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .controlSize(.large)
    }

    private var newBatchLabel: some View {
        Text(model.display.localized("新しいバッチ")).font(.caption).foregroundStyle(.secondary)
            .fixedSize(horizontal: true, vertical: false)
    }

    private var newBatchButton: some View {
        Button {
            guard canStartNewBatch else { return }
            if automation.canResume { replaceBatch = true }
            else { startNewBatch() }
        } label: {
            Label(model.display.localized("新しいバッチを描く"), systemImage: "play.fill")
                .frame(maxWidth: .infinity, minHeight: 28)
        }
        .buttonStyle(.borderedProminent)
        .disabled(!canStartNewBatch)
        .help(tip("入力欄と次のバッチの描画条件で、各行を独立した作品として描きます。"))
    }

    private func startNewBatch() {
        guard canStartNewBatch else { return }
        Task { await automation.startBatch(app: model) }
    }

    private var resultSummary: some View {
        Text(model.display.localizedFormat("成功 %ld・失敗 %ld・全 %ld件",
            automation.successfulCount, automation.failedCount, automation.rows.count))
            .font(.callout).monospacedDigit()
    }

    private var issueResults: some View {
        DisclosureGroup(isExpanded: $issuesExpanded) {
            rowList(issueRows, maxHeight: 220)
        } label: {
            Label(model.display.localizedFormat("失敗・要確認の行 (%ld)", issueRows.count), systemImage: "exclamationmark.circle")
                .font(.subheadline)
        }
    }

    private var allResults: some View {
        DisclosureGroup(isExpanded: $resultsExpanded) {
            rowList(automation.rows, maxHeight: 260)
        } label: {
            Text(model.display.localizedFormat("全行の結果 (%ld)", automation.rows.count)).font(.subheadline)
        }
    }

    private func rowList(_ rows: [BatchRow], maxHeight: CGFloat) -> some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 10) {
                ForEach(rows) { row in
                    resultRow(row)
                    if row.id != rows.last?.id { Divider() }
                }
            }.padding(.top, 8).padding(.trailing, 4)
        }
        .frame(height: min(maxHeight, CGFloat(rows.count) * 160))
    }

    private func resultRow(_ row: BatchRow) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text(model.display.localizedFormat("%ld行", row.line)).font(.caption.weight(.semibold)).monospacedDigit()
                Spacer(minLength: 0)
                Text(model.display.localized(stateLabel(row.state))).font(.caption)
                    .foregroundStyle(row.state == .failed ? Color.red : Color.secondary)
                Text(model.display.localizedFormat("%ld回", row.attempts)).font(.caption).monospacedDigit().foregroundStyle(.secondary)
            }
            Text(row.input).font(.callout).textSelection(.enabled)
            if let error = row.error {
                Text(model.display.message(error)).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
            }
            if row.state == .uncertain {
                VStack(alignment: .leading, spacing: 6) {
                    Button(model.display.localized("履歴を確認")) { NotificationCenter.default.post(name: .inkuOpenSection, object: "library") }
                    HStack(spacing: 8) {
                        Button(model.display.localized("この行を再試行")) { Task { await automation.resolveUncertain(id: row.id, retry: true) } }
                        Button(model.display.localized("この行を省略")) { Task { await automation.resolveUncertain(id: row.id, retry: false) } }
                    }
                }
                .controlSize(.small).disabled(controlsDisabled)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var workspace: some View {
        VStack(alignment: .leading, spacing: 12) {
            if automation.running {
                runProgress
                DisclosureGroup(model.display.localized("開始時の描画条件"), isExpanded: $conditionsExpanded) {
                    frozenConditions.padding(.top, 4)
                }
                .font(.caption)
            }
            observation
        }
        .frame(minWidth: 0, maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    @ViewBuilder private func workspacePane(height: CGFloat) -> some View {
        if height < workspaceMinimumHeight {
            ScrollView {
                workspace.frame(height: workspaceMinimumHeight)
            }
            .frame(minWidth: 0, maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        } else {
            workspace
        }
    }

    private var runProgress: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                if let row = automation.activeRow {
                    Text(model.display.localizedFormat("処理中: %ld行", row.line))
                        .font(.subheadline.weight(.semibold)).monospacedDigit()
                }
                Spacer(minLength: 0)
                if automation.currentRetryRound > 0 {
                    Text(model.display.localizedFormat("再試行 %ld巡目", automation.currentRetryRound))
                        .font(.caption).foregroundStyle(.secondary).monospacedDigit()
                }
            }
            ProviderProgressView(model: model)
        }
    }

    private var frozenConditions: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(model.display.localized("開始時の描画条件")).font(.caption.weight(.semibold))
            if let conditions = automation.batchConditions {
                Text(conditionsSummary(conditions)).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
            } else {
                Text(model.display.localized("未記録")).font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func conditionsSummary(_ conditions: BatchDrawingConditions) -> String {
        let catalog: String
        if conditions.catalogMode == "fixed" {
            catalog = conditions.catalogID.map { id in model.catalogs.first { $0.id == id }?.name ?? id }
                ?? model.display.localized("未記録")
        } else {
            catalog = model.display.localized(conditions.catalogMode == "random" ? "ランダム" : "記述から選択")
        }
        let paper = conditions.canvasID.map { id in model.canvases.first { $0.id == id }?.label ?? id }
            ?? model.display.localized("未記録")
        let reference = conditions.inputMode == "ddl" ? "DDL" : conditions.stage1Model == conditions.stage2Model
            ? conditions.stage1Model : [conditions.stage1Model, conditions.stage2Model].joined(separator: " / ")
        let sketch = model.display.localized(conditions.sketchMode == "on" ? "あり" : conditions.sketchMode == "supplied" ? "指定" : "なし")
        let wild = conditions.wild.map { model.display.localized($0 ? "入" : "切") } ?? model.display.localized("未記録")
        return [model.display.localized("入力") + ": " + model.display.localized(conditions.inputMode == "ddl" ? "DDL" : "記述"),
                model.display.localized("モデル") + ": " + reference,
                model.display.localized("色カタログ") + ": " + catalog,
                model.display.localized("用紙") + ": " + paper,
                model.display.localized("写生") + ": " + sketch,
                model.display.localized("暴れる") + ": " + wild].joined(separator: " · ")
    }

    private var observation: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                Text(model.display.localized(observationTitle)).font(.subheadline.weight(.semibold))
                if automation.observedWork != nil, let row = automation.observedRow {
                    Text(model.display.localizedFormat("%ld行", row.line)).font(.caption).monospacedDigit()
                }
                Spacer(minLength: 0)
                if displayedWork != nil {
                    Label(model.display.localized("保存済み"), systemImage: "checkmark.circle").font(.caption).foregroundStyle(.secondary)
                }
            }
            Picker(model.display.localized("表示"), selection: $workspaceTab) {
                Text(model.display.localized("作品")).tag("work")
                Text("DDL").tag("ddl")
                Text(model.display.localized("写生")).tag("sketch")
            }
            .pickerStyle(.segmented).labelsHidden().frame(maxWidth: 300)
            .accessibilityLabel(model.display.localized("表示する内容"))
            if let work = displayedWork {
                Text(savedSummary(work)).font(.caption).foregroundStyle(.secondary)
                    .lineLimit(2).textSelection(.enabled)
                if workspaceTab == "work" {
                    ArtworkCanvas(svg: work.svg, renderer: model.renderer, caption: work.effectiveSourceText)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if workspaceTab == "ddl" {
                    observedText(work.ddl, empty: "この作品には保存されたDDLがありません。", monospaced: true)
                } else {
                    observedText(work.sketchText, empty: "この作品には保存された写生がありません。", monospaced: false)
                }
            } else {
                ContentUnavailableView(model.display.localized("バッチの作品"), systemImage: "paintpalette",
                    description: Text(model.display.localized("このバッチで保存できた作品と、その行のDDL・写生を表示します。")))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private var observationTitle: String {
        workspaceTab == "ddl" ? "表示中のDDL" : workspaceTab == "sketch" ? "表示中の写生" : "表示中の作品"
    }

    private func observedText(_ text: String?, empty: String, monospaced: Bool) -> some View {
        ScrollView(monospaced ? [.horizontal, .vertical] : [.vertical]) {
            Text(text.flatMap { $0.isEmpty ? nil : $0 } ?? model.display.localized(empty))
                .font(monospaced ? .system(.callout, design: .monospaced) : .callout)
                .fixedSize(horizontal: monospaced, vertical: true)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .topLeading)
                .padding(12)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(.quaternary))
    }

    private func savedSummary(_ work: SavedWork) -> String {
        [work.stage1Model ?? model.display.localized("未記録"), work.renderColorCatalogName ?? work.renderColorCatalogID ?? work.catalogID ?? model.display.localized("未記録"),
         work.renderCanvasAspectID ?? model.display.localized("未記録")].joined(separator: " · ")
    }

    private func stateLabel(_ state: BatchRow.State) -> String {
        switch state {
        case .waiting: "待機"; case .running: "生成中"; case .succeeded: "成功"
        case .failed: "失敗"; case .uncertain: "要確認"; case .skipped: "省略"
        }
    }

    private func tip(_ key: String) -> String {
        model.display.preferences.showTooltips ? model.display.localized(key) : ""
    }
}
