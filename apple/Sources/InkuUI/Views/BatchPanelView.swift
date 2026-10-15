import InkuPersistence
import SwiftUI

@MainActor
struct BatchPanelView: View {
    @Bindable var model: AppModel
    @Bindable var automation: AutomationModel
    var inputOnly = false
    var onObserveWork: ((SavedWork, String) -> Void)? = nil
    var followsLatestWork = true
    var selectedRowID: String? = nil
    var observationRevision: Binding<UUID>? = nil
    @State private var rowObservationID = UUID()
    @State private var replaceBatch = false
    /// The creation panel keeps these on WorkspaceUIState, so switching 記述／バッチ does not reset them.
    var ui: WorkspaceUIState? = nil
    @State private var localResultsExpanded = false
    @State private var localIssuesExpanded = false
    @State private var localConditionsExpanded = false
    @State private var localWorkspaceTab = "work"
    @State private var selectedHistoryPrompt = ""
    @State private var historyOpen = false
    @State private var editorHeight: CGFloat?
    @State private var resizeStartHeight: CGFloat?
    @Environment(\.inkuWindowSize) private var windowSize

    private var resultsExpanded: Binding<Bool> { kept(\.batchResultsExpanded, $localResultsExpanded) }
    private var issuesExpanded: Binding<Bool> { kept(\.batchIssuesExpanded, $localIssuesExpanded) }
    private var conditionsExpanded: Binding<Bool> { kept(\.batchConditionsExpanded, $localConditionsExpanded) }
    private var workspaceTab: Binding<String> { kept(\.batchWorkspaceTab, $localWorkspaceTab) }
    private func kept<Value>(_ path: ReferenceWritableKeyPath<WorkspaceUIState, Value>, _ local: Binding<Value>) -> Binding<Value> {
        guard let ui else { return local }
        return Binding(get: { ui[keyPath: path] }, set: { ui[keyPath: path] = $0 })
    }

    private var controlsDisabled: Bool { automation.isOccupied || model.isBusy }
    private var displayedRowID: String? { followsLatestWork ? automation.observedRow?.id : selectedRowID }
    private var canStartNewBatch: Bool {
        !controlsDisabled && automation.nonEmptyBatchCount > 0 && paintableCount > 0
            && model.hasAvailableBatchDrawingModel
    }
    /// Web `batchNonEmpty`: lines with something to draw besides numbers and comments.
    private var paintableCount: Int { BatchInputLines.paintableCount(in: automation.batchText) }
    private var inputHeight: CGFloat { editorHeight ?? min(220, max(140, (windowSize?.height ?? 880) * 0.22)) }
    private var issueRows: [BatchRow] { automation.rows.filter { $0.state == .uncertain } }
    private var displayedWork: SavedWork? {
        automation.observedWork ?? model.selectedWork
    }
    private var workspaceMinimumHeight: CGFloat {
        automation.running && conditionsExpanded.wrappedValue ? 620 : 500
    }

    var body: some View {
        Group {
          if inputOnly {
            inputContent
          } else {
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
        .onAppear { if automation.uncertainCount > 0 { issuesExpanded.wrappedValue = true } }
        .onChange(of: automation.running) { _, running in if running { rowObservationID = UUID() } }
        .onChange(of: automation.preparing) { _, preparing in if preparing { rowObservationID = UUID() } }
        .onDisappear { rowObservationID = UUID() }
        .onChange(of: automation.uncertainCount) { _, count in
            if count > 0 { issuesExpanded.wrappedValue = true }
        }
        .onChange(of: automation.isOccupied) { _, occupied in
            if occupied { replaceBatch = false; historyOpen = false }
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
            if model.display.visible("drawing_settings") {
                BatchConditionsView(model: model, automation: automation)
            } else {
                // Hiding native advanced conditions must not remove the batch's clear action.
                Button(model.display.webCopy("clearInputBtn", "新規作成")) { automation.restoreBatchInput("") }
                    .buttonStyle(InkuGhostButtonStyle()).disabled(controlsDisabled)
                    .inkuTooltip(model.display.tooltip("入力をクリアする", serverKey: "tooltipInputClear"))
            }
            actions
            if inputOnly && automation.running { BatchObservationCards(model: model, automation: automation) }
            if !automation.running, automation.failedCount > 0 { failureReport }
            if automation.uncertainCount > 0 { issueResults }
            if !automation.rows.isEmpty { allResults }
        }
        .frame(minWidth: 0, maxWidth: .infinity, alignment: .leading)
        .onChange(of: automation.batchText) { _, text in
            if text != selectedHistoryPrompt { selectedHistoryPrompt = "" }
        }
    }

    private var input: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                inputHeading
                Spacer(minLength: 0)
                if automation.canResume && !automation.isOccupied {
                    Text(model.display.webCopy("batchInterruptedLabel", "中断したバッチがあります"))
                        .inkuFont(12).foregroundStyle(.red)
                }
            }
            if automation.running, let row = automation.activeRow {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(String(row.line)).inkuFont(14).foregroundStyle(.tertiary).monospacedDigit()
                    Text(row.input).inkuFont(14).lineSpacing(8).textSelection(.enabled)
                }
                .padding(.horizontal, 10).padding(.vertical, 8).frame(maxWidth: .infinity, alignment: .leading)
                .background(InkuColor.bg2, in: RoundedRectangle(cornerRadius: 4))
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(InkuColor.border))
            } else {
                BatchInputEditor(text: $automation.batchText, isEditable: !controlsDisabled,
                                 accessibilityLabel: model.display.localized("バッチ入力"))
                    .overlay(alignment: .topLeading) {
                        // BatchPanel.svelte:191 `batchPlaceholder`: three example lines beside the gutter.
                        if automation.batchText.isEmpty {
                            Text(model.display.webCopy("batchPlaceholder", "山の向こうに月が昇る\n夜の霧が広がる\n青いクレヨンの線がゆっくり波打つ"))
                                .inkuFont(14).foregroundStyle(.tertiary).lineSpacing(6 * model.display.preferences.textScale)
                                .padding(.leading, 44).padding(.top, 9).allowsHitTesting(false)
                        }
                    }
                    .frame(height: inputHeight)
                    .clipShape(RoundedRectangle(cornerRadius: 4))
                    .overlay(RoundedRectangle(cornerRadius: 4).stroke(InkuColor.border2))
                    .overlay(alignment: .bottomTrailing) { resizeHandle }
                // BatchPanel.svelte:200: 「N 件」 while there is something to draw and no run.
                if paintableCount > 0 && !automation.running {
                    Text(model.display.preferences.language == "en" ? "\(paintableCount) items" : "\(paintableCount) 件")
                        .inkuFont(12).foregroundStyle(.secondary).monospacedDigit()
                }
                if !automation.batchPromptHistory.isEmpty { inputHistory }
            }
            if let error = automation.historyErrorText {
                Text(model.display.message(error)).inkuFont(12).foregroundStyle(.red).textSelection(.enabled)
            }
        }
    }

    private var resizeHandle: some View {
        Path { path in
            path.move(to: CGPoint(x: 3, y: 11)); path.addLine(to: CGPoint(x: 11, y: 3))
            path.move(to: CGPoint(x: 7, y: 11)); path.addLine(to: CGPoint(x: 11, y: 7))
        }.stroke(.secondary, lineWidth: 1)
            .frame(width: 14, height: 14).background(InkuColor.panel)
            .contentShape(Rectangle()).padding(2)
            .gesture(DragGesture(minimumDistance: 1)
                .onChanged { value in
                    if resizeStartHeight == nil { resizeStartHeight = inputHeight }
                    setInputHeight((resizeStartHeight ?? inputHeight) + value.translation.height)
                }.onEnded { _ in resizeStartHeight = nil })
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(model.display.label("入力欄の高さを変える", "Resize input"))
            .accessibilityValue(String(Int(inputHeight)))
            .accessibilityAdjustableAction { direction in
                setInputHeight(inputHeight + (direction == .increment ? 20 : -20))
            }
            .disabled(controlsDisabled)
    }

    private func setInputHeight(_ height: CGFloat) {
        guard !controlsDisabled else { return }
        editorHeight = min(max(120, height), max(220, (windowSize?.height ?? 880) * 0.7))
    }

    @ViewBuilder private var inputHeading: some View {
        HStack(alignment: .firstTextBaseline, spacing: 2) {
            Text(model.display.webCopy("batchSectionLabel", "バッチ")).inkuFont(14, weight: .semibold)
                .fixedSize(horizontal: true, vertical: false)
            Text(model.display.webCopy("batchSectionHint", "：一行に1作品分の記述を入力。"))
                .inkuFont(14).foregroundStyle(.secondary)
        }
    }

    private var inputHistory: some View {
        Button { historyOpen.toggle() } label: {
            HStack(spacing: 6) {
                Text(selectedHistoryPrompt.isEmpty ? model.display.webCopy("batchHistoryPlaceholder", "履歴から選択") : historyLabel(selectedHistoryPrompt))
                    .lineLimit(1).truncationMode(.tail)
                Spacer(minLength: 0)
                Image(systemName: "chevron.down").inkuFont(11)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 8).padding(.vertical, 6)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .frame(maxWidth: .infinity, minHeight: 28, alignment: .leading)
        .background(InkuColor.bg2, in: RoundedRectangle(cornerRadius: 4))
        .overlay(RoundedRectangle(cornerRadius: 4).stroke(InkuColor.border2))
        .inkuFont(12)
        .disabled(controlsDisabled || automation.batchPromptHistory.isEmpty)
        .accessibilityLabel(model.display.webCopy("batchHistoryLabel", "バッチ記述履歴"))
        .accessibilityValue(selectedHistoryPrompt.isEmpty ? model.display.localized("履歴から選択") : historyLabel(selectedHistoryPrompt))
        .inkuTooltip(tip("選んだ履歴をバッチ入力欄へ復元します。実行記録と保存作品は変わりません。"))
        .popover(isPresented: $historyOpen, arrowEdge: .bottom) {
            ScrollView {
                // At most 50 rows: eager layout also keeps macOS accessibility scroll actions stable.
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(automation.batchPromptHistory.enumerated()), id: \.offset) { _, text in
                        Button {
                            guard !controlsDisabled else { return }
                            selectedHistoryPrompt = text
                            automation.restoreBatchInput(text)
                            historyOpen = false
                        } label: {
                            Text(historyLabel(text)).inkuFont(13).lineLimit(1).truncationMode(.tail)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.horizontal, 10).padding(.vertical, 7)
                                .background(selectedHistoryPrompt == text ? Color.accentColor.opacity(0.15) : .clear)
                                .contentShape(Rectangle())
                        }.buttonStyle(.plain)
                            .accessibilityAddTraits(selectedHistoryPrompt == text ? .isSelected : [])
                    }
                }
            }.frame(width: 390, height: min(CGFloat(automation.batchPromptHistory.count) * 32 + 8, (windowSize?.height ?? 880) * 0.5))
                #if os(macOS)
                .onExitCommand { historyOpen = false }
                #endif
        }
    }

    private func historyLabel(_ text: String) -> String {
        text.components(separatedBy: .newlines).first ?? text
    }

    private var resumeCard: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 10) { resumeCopy; resumeButton.fixedSize() }
            VStack(alignment: .leading, spacing: 8) { resumeCopy; resumeButton }
        }
        .padding(10).frame(maxWidth: .infinity, alignment: .leading)
        .background(InkuColor.panel, in: RoundedRectangle(cornerRadius: 4))
        .overlay(RoundedRectangle(cornerRadius: 4).stroke(InkuColor.border2))
    }

    private var resumeCopy: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(model.display.webCopy("batchResumeTitle", "中断したバッチを再開")).inkuFont(13, weight: .semibold)
            if let line = automation.nextPendingLine {
                // Exported templates follow their visible placeholder order, which differs between JA and EN.
                Text(model.display.webCopyFormat("batchResumeKnown", "%@ / %@ / %@",
                    model.display.preferences.language == "ja" ? automation.rows.count : line,
                    model.display.preferences.language == "ja" ? line : automation.rows.count, automation.pendingCount))
                    .inkuFont(12).foregroundStyle(.secondary)
            }
            Text(model.display.webCopyFormat("batchResumeCompleted", "%@", automation.completedCount)).inkuFont(12).foregroundStyle(.secondary)
            Text(model.display.webCopy("batchResumeRestores", "再開時に元の入力と描画条件を復元します。完了済みの作品は描き直しません。"))
                .inkuFont(12).foregroundStyle(.secondary)
            if automation.uncertainCount > 0 {
                Text(model.display.localized("要確認の行を確認してから再開してください。"))
                    .inkuFont(12).foregroundStyle(.secondary)
            }
        }.fixedSize(horizontal: false, vertical: true)
    }

    private var resumeButton: some View {
        Button(model.display.webCopy("batchResumeBtn", "中断時点から再開")) { Task { await automation.resumeBatch(app: model) } }
            .buttonStyle(InkuGhostButtonStyle())
            .disabled(controlsDisabled || automation.uncertainCount > 0)
            .inkuTooltip(tip("前回の開始時の条件で、未処理の行と失敗した行を再開します。"))
    }

    private var actions: some View {
        VStack(alignment: .leading, spacing: 8) {
            if automation.preparing {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text(model.display.localized("バッチを準備中…")).inkuFont(13)
                }
            } else if automation.running {
                // BatchPanel.svelte:280: the running batch shows the drawing indicator with its progress.
                RunStatusView(display: model.display, label: runningLabel, stopping: automation.stopping,
                              stopTooltip: tip("実行中のバッチを停止します。未処理の行は後で再開できます。"),
                              onStop: { Task { await automation.stop(app: model) } }) { runProgress }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 8) { newBatchLabel; newBatchButton }
                    VStack(alignment: .leading, spacing: 6) { newBatchLabel; newBatchButton }
                }
                if !model.hasAvailableBatchDrawingModel {
                    Text(model.display.localized("使用中のLLMモデルを選択してから描いてください。"))
                        .inkuFont(12).foregroundStyle(.secondary)
                }
            }
            if let error = automation.errorText {
                Text(model.display.message(error)).inkuFont(12).foregroundStyle(.red).textSelection(.enabled)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var newBatchLabel: some View {
        Text(model.display.localized("新しいバッチ")).inkuFont(12).foregroundStyle(.secondary)
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
        .buttonStyle(InkuPaintButtonStyle())
        .disabled(!canStartNewBatch)
        .inkuTooltip(tip("入力欄と次のバッチの描画条件で、各行を独立した作品として描きます。"))
    }

    private func startNewBatch() {
        guard canStartNewBatch else { return }
        Task { await automation.startBatch(app: model) }
    }

    private var resultSummary: some View {
        Text(model.display.webCopyFormat("batchSummary", "%@ / %@ / %@",
            automation.successfulCount, automation.failedCount, automation.rows.count))
            .inkuFont(13).monospacedDigit()
    }

    private var runningLabel: String {
        let current = automation.activeRow.flatMap { active in automation.rows.firstIndex { $0.id == active.id } }.map { $0 + 1 }
            ?? (automation.completedCount + automation.failedCount)
        return automation.currentRetryRound > 0
            ? model.display.webCopyFormat("batchRetryProgress", "%@ / %@ / %@", automation.currentRetryRound, current, automation.rows.count)
            : model.display.webCopyFormat("batchProgress", "%@ / %@", current, automation.rows.count)
    }

    private var failureReport: some View {
        VStack(alignment: .leading, spacing: 8) {
            resultSummary
            if automation.canRetryFailures { retryFailuresButton }
            Text(model.display.webCopy("batchFailureTitle", "失敗した行")).inkuFont(12, weight: .semibold)
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(automation.rows.filter { $0.state == .failed }) { row in
                        HStack(alignment: .top, spacing: 8) {
                            Text(model.display.webCopyFormat("batchFailureLine", "%@", row.line))
                                .inkuFont(12).foregroundStyle(.secondary).frame(width: 48, alignment: .leading)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(row.input).inkuFont(12).lineLimit(1).truncationMode(.tail)
                                if let error = row.error {
                                    Text(model.display.message(error)).inkuFont(11).foregroundStyle(.red).textSelection(.enabled)
                                }
                            }.frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
            }.frame(height: min(190, CGFloat(automation.failedCount) * 64))
        }.padding(10).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.red.opacity(0.08), in: RoundedRectangle(cornerRadius: 4))
            .overlay(RoundedRectangle(cornerRadius: 4).stroke(Color.red.opacity(0.35)))
    }

    /// BatchPanel.svelte: the failure summary offers to draw the failed rows alone again.
    private var retryFailuresButton: some View {
        Button(model.display.webCopy("batchRetryFailuresBtn", "エラー作品を再描画"), systemImage: "arrow.clockwise") {
            Task { await automation.retryFailures(app: model) }
        }
        .buttonStyle(InkuGhostButtonStyle())
        .disabled(controlsDisabled)
        .inkuTooltip(tip("失敗した行だけを、元の本文・行番号・描画条件で描き直します。"))
    }

    private var issueResults: some View {
        DisclosureGroup(isExpanded: issuesExpanded) {
            rowList(issueRows, maxHeight: 220)
        } label: {
            Label(model.display.localizedFormat("失敗・要確認の行 (%ld)", issueRows.count), systemImage: "exclamationmark.circle")
                .inkuFont(12)
        }
    }

    private var allResults: some View {
        DisclosureGroup(isExpanded: resultsExpanded) {
            rowList(automation.rows, maxHeight: 260)
        } label: {
            Text(model.display.localizedFormat("全行の結果 (%ld)", automation.rows.count)).inkuFont(12)
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
                Text(model.display.localizedFormat("%ld行", row.line)).inkuFont(12, weight: .semibold).monospacedDigit()
                Spacer(minLength: 0)
                Text(model.display.localized(stateLabel(row.state))).inkuFont(12)
                    .foregroundStyle(row.state == .failed ? Color.red : Color.secondary)
                Text(model.display.localizedFormat("%ld回", row.attempts)).inkuFont(12).monospacedDigit().foregroundStyle(.secondary)
            }
            Text(row.input).inkuFont(13).textSelection(.enabled)
            if row.state == .succeeded, row.workID != nil {
                Button(model.display.localized(displayedRowID == row.id ? "表示中の作品" : "作品を表示"), systemImage: "paintpalette") {
                    let token = UUID(); rowObservationID = token
                    let revision = observationRevision?.wrappedValue
                    let selectedWorkID = model.selectedWorkID
                    Task {
                        guard let work = await automation.observeBatchRow(id: row.id, app: model),
                              rowObservationID == token, !model.isBrowsingLocked,
                              observationRevision?.wrappedValue == revision,
                              model.selectedWorkID == selectedWorkID,
                              work.id == row.workID, !Task.isCancelled else { return }
                        onObserveWork?(work, row.id)
                    }
                }.inkuFont(12).disabled(model.isBrowsingLocked)
            }
            if let error = row.error {
                Text(model.display.message(error)).inkuFont(12).foregroundStyle(.secondary).textSelection(.enabled)
            }
            if row.state == .uncertain {
                VStack(alignment: .leading, spacing: 6) {
                    Button(model.display.localized("履歴を確認")) { NotificationCenter.default.post(name: .inkuOpenSection, object: "library") }
                    HStack(spacing: 8) {
                        Button(model.display.localized("この行を再試行")) { Task { await automation.resolveUncertain(id: row.id, retry: true) } }
                        Button(model.display.localized("この行を省略")) { Task { await automation.resolveUncertain(id: row.id, retry: false) } }
                    }.disabled(controlsDisabled)
                }
                .buttonStyle(InkuGhostButtonStyle())
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var workspace: some View {
        VStack(alignment: .leading, spacing: 12) {
            if automation.running {
                runProgress
                DisclosureGroup(model.display.localized("開始時の描画条件"), isExpanded: conditionsExpanded) {
                    frozenConditions.padding(.top, 4)
                }
                .inkuFont(12)
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
                        .inkuFont(12, weight: .semibold).monospacedDigit()
                }
                Spacer(minLength: 0)
                if automation.currentRetryRound > 0 {
                    Text(model.display.localizedFormat("再試行 %ld巡目", automation.currentRetryRound))
                        .inkuFont(12).foregroundStyle(.secondary).monospacedDigit()
                }
            }
            if let startedAt = automation.batchRowStartedAt {
                TimelineView(.periodic(from: startedAt, by: 0.5)) { context in
                    Text(model.display.localizedFormat("この行の経過 %.1f秒", max(0, context.date.timeIntervalSince(startedAt))))
                        .inkuFont(12).foregroundStyle(.secondary).monospacedDigit()
                        .inkuTooltip(tip("この行を描き始めてからの時間です。写生・色カタログ・指示書生成と各応答待ちを含みます。"))
                }
            }
            ProviderProgressView(model: model)
        }
    }

    private var frozenConditions: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(model.display.localized("開始時の描画条件")).inkuFont(12, weight: .semibold)
            if let conditions = automation.batchConditions {
                Text(conditionsSummary(conditions)).inkuFont(12).foregroundStyle(.secondary).textSelection(.enabled)
            } else {
                Text(model.display.localized("未記録")).inkuFont(12).foregroundStyle(.secondary)
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
                Text(model.display.localized(observationTitle)).inkuFont(12, weight: .semibold)
                if automation.observedWork != nil, let row = automation.observedRow {
                    Text(model.display.localizedFormat("%ld行", row.line)).inkuFont(12).monospacedDigit()
                }
                Spacer(minLength: 0)
                if displayedWork != nil {
                    Label(model.display.localized("保存済み"), systemImage: "checkmark.circle").inkuFont(12).foregroundStyle(.secondary)
                }
            }
            InkuSegmentedButtons(options: [("work", model.display.localized("作品")), ("ddl", "DDL"), ("sketch", model.display.localized("写生"))],
                                 selection: workspaceTab)
            .accessibilityLabel(model.display.localized("表示する内容"))
            if let work = displayedWork {
                if automation.observedWork == nil {
                    Text(model.display.localized("このバッチの成功作品はまだありません。前に表示した保存作品を表示しています。"))
                        .inkuFont(12).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
                Text(savedSummary(work)).inkuFont(12).foregroundStyle(.secondary)
                    .lineLimit(2).textSelection(.enabled)
                if workspaceTab.wrappedValue == "work" {
                    ArtworkCanvas(svg: work.svg, renderer: model.displayRenderer, caption: work.effectiveSourceText)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if workspaceTab.wrappedValue == "ddl" {
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
        workspaceTab.wrappedValue == "ddl" ? "表示中のDDL" : workspaceTab.wrappedValue == "sketch" ? "表示中の写生" : "表示中の作品"
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
        model.display.tooltip(key)
    }
}
