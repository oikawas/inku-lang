import InkuPersistence
import SwiftUI

struct BatchWorkspaceSelection {
    private enum Display { case history, latest, row(SavedWork, String) }
    private var display = Display.history
    var revision = UUID()
    init() {}

    var followsLatest: Bool { if case .latest = display { true } else { false } }
    var pinnedWork: SavedWork? { if case .row(let work, _) = display { work } else { nil } }
    var rowID: String? { if case .row(_, let id) = display { id } else { nil } }

    mutating func showHistory() { display = .history; revision = UUID() }
    mutating func followLatest() { display = .latest; revision = UUID() }
    mutating func pin(_ work: SavedWork, rowID: String) { display = .row(work, rowID); revision = UUID() }
    mutating func invalidateReads() { revision = UUID() }
}

@MainActor
struct CreationView: View {
    @Bindable var model: AppModel
    @Bindable var history: HistoryModel
    @Bindable var automation: AutomationModel
    @Binding var batchWorkspace: BatchWorkspaceSelection
    let onEditWork: (SavedWork, WorkEditMode) -> Void
    let onAdjustWork: (SavedWork) -> Void
    let onReplayWork: (SavedWork) -> Void
    let onWorkAction: (SavedWork, String) -> Void
    let onLineageExport: (String) -> Void
    var onWorkspaceWorkChange: (SavedWork?) -> Void = { _ in }
    private var controlsDisabled: Bool { model.isBusy || automation.isOccupied }
    private var browsingDisabled: Bool { model.isBrowsingLocked }
    @State private var showSaijiki = false
    @State private var workspaceTab = "artwork"
    @State private var showColorCatalogs = false
    @State private var showModelPicker = false
    @State private var showConditionDetails = false
    @State private var showPaperPicker = false
    @State private var showNewDDL = false
    private var isBatch: Bool { automation.workspaceInputMode == "batch" }
    private var batchWork: SavedWork? { batchWorkspace.pinnedWork ?? (batchWorkspace.followsLatest ? automation.observedWork : nil) }
    private var usesBatchWork: Bool { isBatch && batchWork != nil }
    private var workspaceWork: SavedWork? { usesBatchWork ? batchWork : model.displayedWork }
    private var workspaceIsPreview: Bool { !usesBatchWork && model.isPreview }
    private var hasSavedWorkspaceWork: Bool { workspaceWork?.trashed == false && !workspaceIsPreview }
    #if os(macOS)
    @Environment(DDLImportController.self) private var importer
    #endif

    var body: some View {
        VStack(spacing: 0) {
          if model.display.visible("input_modes") || model.display.visible("ddl_tools") {
          HStack(spacing: 16) {
            if model.display.visible("input_modes") {
                Picker(model.display.localized("入力"), selection: $automation.workspaceInputMode) {
                    Text(model.display.localized("記述")).tag("description")
                    Text(model.display.localized("バッチ")).tag("batch")
                }.pickerStyle(.segmented).frame(width: 260)
                    .disabled(browsingDisabled)
            }
            Spacer()
            if model.display.visible("ddl_tools") {
                Button(model.display.localized("指示書の新規作成"), systemImage: "doc.badge.plus") { showNewDDL = true }
                    .disabled(model.isBusy || automation.isOccupied)
            }
          }.padding(.horizontal, 16).padding(.vertical, 10).background(.bar)
          Divider()
          }
          GeometryReader { geometry in
            if geometry.size.width >= 800 {
                HStack(alignment: .top, spacing: 0) {
                    VStack(spacing: 0) {
                        ScrollView {
                            inputContents.padding(12)
                        }
                        if !isBatch {
                            Divider()
                            generationAction.padding(12).background(.bar)
                        }
                    }
                    .frame(width: 360)
                    .background(.quaternary.opacity(0.16))
                    Divider()
                    workspace.padding(16)
                }
            } else {
                VStack(spacing: 0) {
                    ScrollView {
                        VStack(spacing: 16) {
                            inputContents
                            workspace.frame(height: max(480, geometry.size.height * 0.85))
                        }
                        .padding(16)
                    }
                    if !isBatch {
                        Divider()
                        generationAction.padding(16).background(.bar)
                    }
                }
            }
          }
          if model.display.visible("history") { Divider(); HistoryStripView(model: model, history: history, displayedWorkID: workspaceWork?.id, onSelectWork: { _ in batchWorkspace.showHistory() }) }
        }
        .sheet(isPresented: $showSaijiki) {
            VStack(spacing: 0) {
                HStack { Spacer(); Button(model.display.localized("閉じる")) { showSaijiki = false } }.padding(12)
                SaijikiView(model: model)
            }.frame(minWidth: 560, minHeight: 620)
        }
        .sheet(isPresented: $showColorCatalogs) { ColorCatalogView(model: model, descriptionOnly: true) }
        .sheet(isPresented: $showModelPicker) { BatchModelPickerView(model: model) }
        .sheet(isPresented: $showNewDDL) { NewDdlAuthoringSheet(model: model) }
        .onChange(of: automation.workspaceInputMode) { _, _ in batchWorkspace.invalidateReads() }
        .onChange(of: workspaceTab) { _, tab in
            batchWorkspace.invalidateReads()
            if tab == "lineage", isBatch, batchWorkspace.followsLatest,
               let work = batchWork, let rowID = automation.observedRow?.id {
                batchWorkspace.pin(work, rowID: rowID)
            }
        }
        .onDisappear { batchWorkspace.invalidateReads() }
        .onChange(of: workspaceWork?.id) { _, _ in
            onWorkspaceWorkChange(workspaceWork)
        }
        .onAppear {
            model.inputMode = "description"
            if !["off", "on"].contains(model.sketchMode) { model.sketchMode = "off" }
            if !["auto", "fixed"].contains(model.catalogMode) { model.catalogMode = "fixed" }
            onWorkspaceWorkChange(workspaceWork)
        }
    }

    private var inputContents: some View {
        VStack(alignment: .leading, spacing: 14) {
            if isBatch {
                BatchPanelView(model: model, automation: automation, inputOnly: true,
                               onObserveWork: { work, rowID in batchWorkspace.pin(work, rowID: rowID) },
                               followsLatestWork: batchWorkspace.followsLatest,
                               selectedRowID: batchWorkspace.rowID, observationRevision: $batchWorkspace.revision)
            } else {
                input
                if model.display.visible("drawing_settings") { nextConditions }
                if let work = workspaceWork {
                    CreationDisplayedProcess(model: model, work: work, saved: hasSavedWorkspaceWork,
                                             disabled: controlsDisabled, onWorkAction: onWorkAction)
                }
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    private var input: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(model.display.localized("作品を作る")).font(.title2.weight(.semibold))
                Spacer()
                Button(model.display.localized("新規")) {
                    batchWorkspace.showHistory()
                    #if os(macOS)
                    importer.clearMessage()
                    #endif
                    model.newWork()
                }.disabled(controlsDisabled)
                    .help(tip("入力をクリアして、新しい作品を始めます。"))
            }
                editor(text: $model.descriptionText, placeholder: "描きたいものや情景を記述", height: 120,
                       readOnly: model.sourceLocked && model.selectedWork != nil)
                DescriptionMeterView(model: model, text: model.descriptionText)
                if model.sourceLocked && model.selectedWork != nil {
                    Text(model.display.localized("この作品の記述はロックされています。別の記述で生成するには「新規」を選んでください。"))
                        .font(.caption).foregroundStyle(.secondary)
                }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var nextConditions: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(model.display.localized("次の生成条件"), systemImage: "slider.horizontal.3")
                .font(.subheadline.weight(.semibold))
            Button { showModelPicker = true } label: {
                conditionRow("モデル", value: model.nextBatchDrawingModelReference.isEmpty ? model.display.localized("選択してください") : model.nextBatchDrawingModelReference)
            }
            .buttonStyle(.plain).disabled(controlsDisabled)
            .help(tip("次の作品の描画モデルを選びます。"))
            Button { showColorCatalogs = true } label: {
                conditionRow("色カタログ", value: catalogSummary)
            }
            .buttonStyle(.plain).disabled(controlsDisabled || model.catalogs.isEmpty)
            .accessibilityLabel(model.display.localized("色カタログを開く"))
            .accessibilityValue(catalogSummary)
            .help(tip("次の作品の配色を選びます。"))
            Divider()
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 10) { compactConditionControls }
                VStack(alignment: .leading, spacing: 8) { compactConditionControls }
            }
            .controlSize(.small).disabled(controlsDisabled)
            HStack {
                Button(model.display.localized("生成条件の詳細"), systemImage: "ellipsis.circle") { showConditionDetails = true }
                    .help(tip("言語・シード・配色の選び方を確認して変更します。"))
                    .popover(isPresented: $showConditionDetails) { conditionDetails }
                Spacer(minLength: 0)
                if model.display.visible("saijiki") {
                    Button { showSaijiki = true } label: { Image(systemName: "book") }
                        .accessibilityLabel(model.display.localized("歳時記を開く"))
                        .help(tip("歳時記の語と説明を参照します。"))
                }
            }
            .controlSize(.small).disabled(controlsDisabled)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var catalogSummary: String {
        model.catalogMode == "auto" ? model.display.localized("記述から選択")
            : model.catalogs.first { $0.id == model.catalogID }?.name ?? model.catalogID
    }

    private func conditionRow(_ key: String, value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(model.display.localized(key)).font(.caption).foregroundStyle(.secondary)
                Text(value).font(.callout).lineLimit(1).truncationMode(.middle)
            }
            Spacer(minLength: 0)
            Text(model.display.localized("変更")).font(.caption).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
    }

    @ViewBuilder private var compactConditionControls: some View {
            Menu {
                Button(model.display.localized("なし")) { model.sketchMode = "off" }
                Button(model.display.localized("あり")) { model.sketchMode = "on" }
            } label: {
                Text(model.display.localized("写生") + ": " + model.display.localized(model.sketchMode == "on" ? "あり" : "なし"))
            }.help(tip(model.sketchMode == "on" ? "記述の横に、場所の広がりや季節・時刻の光を補って描く" : "写生を通さず、記述だけで描く"))
        Button(model.display.localized("暴れる") + " " + model.display.localized(model.wild ? "入" : "切")) { model.wild.toggle() }
            .buttonStyle(.bordered).tint(model.wild ? .accentColor : .secondary)
            .help(tip("次の作品の筆致を規則から外します。"))
        Button { showPaperPicker = true } label: {
            Label(model.display.localized("用紙") + ": " + (model.canvases.first { $0.id == model.canvasID }?.label ?? model.canvasID),
                  systemImage: "rectangle.portrait")
        }
        .help(tip("用紙の形と意図を見て、次の作品の用紙を選びます。"))
        .popover(isPresented: $showPaperPicker) {
            CreationPaperPicker(model: model) { showPaperPicker = false }.environment(model.display)
        }
        .accessibilityValue(model.canvases.first { $0.id == model.canvasID }?.name ?? model.canvasID)
    }

    private var conditionDetails: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(model.display.localized("生成条件の詳細")).font(.headline)
            Picker(model.display.localized("配色の選び方"), selection: $model.catalogMode) {
                Text(model.display.localized("指定")).tag("fixed")
                Text(model.display.localized("記述から選択")).tag("auto")
            }.help(tip("次の作品の配色を選びます。"))
            TextField(model.display.localized("シード（空欄で新規）"), text: $model.seedText).textFieldStyle(.roundedBorder)
                .help(tip("空欄なら次の描画で新しいシードを使います。"))
        }.padding(16).frame(width: 360).disabled(controlsDisabled)
    }

    private var generationAction: some View {
        VStack(alignment: .leading, spacing: 10) {
            if model.inputMode == "description" && !model.hasNextDrawingModel {
                Button {
                    NotificationCenter.default.post(name: .inkuOpenSection, object: "settings", userInfo: ["settingsSection": "models"])
                } label: {
                    Label(model.display.localized("記述から生成するには、設定で接続先とモデルを指定してください。"), systemImage: "gearshape")
                        .font(.callout).multilineTextAlignment(.leading)
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
                .disabled(browsingDisabled)
            }
            if automation.isOccupied {
                Button { Task { await automation.stop(app: model) } } label: {
                    Label(model.display.localized(automation.stopping ? "停止中" : "停止"), systemImage: "stop.fill").frame(maxWidth: .infinity)
                }.buttonStyle(.bordered).disabled(!automation.running || automation.stopping)
            } else if model.isBusy {
                Button { Task { await model.cancel() } } label: {
                    Label(model.display.localized("停止"), systemImage: "stop.fill").frame(maxWidth: .infinity)
                }
                    .buttonStyle(.bordered)
                    .frame(maxWidth: .infinity)
                    .help(tip("実行中の描画を停止します。"))
            } else {
                Button { batchWorkspace.showHistory(); Task { await model.generateDescription() } } label: {
                    Label(model.display.localized("生成"), systemImage: "play.fill").frame(maxWidth: .infinity)
                }
                    .buttonStyle(.borderedProminent)
                    .frame(maxWidth: .infinity)
                    .disabled(!model.canGenerateDescription || automation.isOccupied)
                    .help(tip("入力と次の生成条件から作品を描きます。"))
            }
            if model.isBusy && !automation.isOccupied { ProviderProgressView(model: model) }
        }
        .controlSize(.large)
    }

    private func editor(text: Binding<String>, placeholder: String, monospaced: Bool = false, height: CGFloat, readOnly: Bool = false) -> some View {
        ZStack(alignment: .topLeading) {
            TextEditor(text: text)
                .font(monospaced ? .system(.body, design: .monospaced) : .body)
                .scrollContentBackground(.hidden)
                .padding(6)
                .disabled(controlsDisabled || readOnly)
            if text.wrappedValue.isEmpty {
                Text(model.display.localized(placeholder)).foregroundStyle(.tertiary).padding(12).allowsHitTesting(false)
            }
        }
        .frame(height: height)
        .background(.background, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
        .accessibilityLabel(model.display.localized(monospaced ? "DDL" : "記述"))
    }

    private var workspace: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
              if model.display.visible("work_tools") {
              HStack(spacing: 12) {
                Picker(model.display.localized("表示"), selection: $workspaceTab) { Text(model.display.localized("作品")).tag("artwork"); Text(model.display.localized("系譜")).tag("lineage") }
                    .pickerStyle(.segmented).labelsHidden().frame(width: 150)
                    .accessibilityLabel(model.display.localized("表示"))
                    .disabled(workspaceWork == nil || browsingDisabled)
                Spacer()
                if let work = workspaceWork, hasSavedWorkspaceWork {
                    Menu(model.display.localized("推敲する")) {
                        SavedWorkRefinementActions(model: model, work: work, onAction: onWorkAction)
                    }.disabled(controlsDisabled)
                }
              }
              }
              if let work = workspaceWork, model.display.visible("detail_status") {
                  Text(model.display.localized("表示中作品の描画条件"))
                      .font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
                  Text(savedSummary(work))
                      .font(.caption).foregroundStyle(.secondary)
                      .lineLimit(1).truncationMode(.middle)
                      .frame(maxWidth: .infinity, alignment: .leading)
                      .help(model.display.tooltipValue(savedSummary(work)))
                      .accessibilityLabel(savedSummary(work))
              }
            }
            if workspaceTab == "lineage" && model.display.visible("work_tools") {
                LineageView(model: model, onEditWork: onEditWork, onAdjustWork: onAdjustWork, onReplayWork: onReplayWork,
                            onWorkAction: onWorkAction, onExport: onLineageExport, initialWork: workspaceWork,
                            writingLocked: controlsDisabled, onBrowseWork: { _ in batchWorkspace.showHistory() })
            }
            else {
                ArtworkCanvas(svg: workspaceWork?.svg ?? model.currentSVG, renderer: model.renderer,
                              caption: workspaceWork?.effectiveSourceText ?? "")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            if workspaceTab == "artwork" || !model.display.visible("work_tools") {
                CreationCanvasControls(model: model, work: workspaceWork, saved: hasSavedWorkspaceWork,
                                       disabled: controlsDisabled, browsingDisabled: browsingDisabled, onReplayWork: onReplayWork,
                                       onWorkAction: onWorkAction, onShowSaijiki: { showSaijiki = true })
            }
            if workspaceIsPreview {
                VStack(alignment: .leading, spacing: 8) {
                    Label(model.display.localized("未保存の候補"), systemImage: "eye")
                    HStack {
                        Button(model.display.localized("この候補を保存")) { Task { await model.savePreview() } }.buttonStyle(.borderedProminent)
                        Button(model.display.localized("候補を閉じる")) { Task { await model.clearPreview() } }
                    }
                }.disabled(controlsDisabled)
            }
            if model.display.visible("history") {
                navigationActions.controlSize(.small).disabled(browsingDisabled)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .task(id: workspaceWork?.id) {
            guard let work = workspaceWork, hasSavedWorkspaceWork, !Task.isCancelled else { return }
            await history.locate(app: model, workID: work.id)
            guard !Task.isCancelled, workspaceWork?.id == work.id else { return }
            await model.loadWorkActionState(work)
        }
    }

    private func savedSummary(_ work: SavedWork) -> String {
        [work.stage1Model ?? "DDL", work.renderColorCatalogName ?? work.renderColorCatalogID ?? work.catalogID ?? "—",
         work.renderCanvasAspectID ?? "—", ByteCountFormatter.string(fromByteCount: Int64(work.svg.utf8.count), countStyle: .file)].joined(separator: " · ")
    }

    private var navigationActions: some View {
        HStack(spacing: 8) {
            Button(model.display.localized("最新")) { navigateHistory(boundary: "latest") }
                .disabled(!history.canMoveNewer)
                .help(model.display.tooltip("最新の履歴", serverKey: "tooltipCanvasNavLatest"))
            Button { navigateHistory(delta: -1) } label: { Image(systemName: "chevron.left") }
                .disabled(!history.canMoveNewer)
                .accessibilityLabel(model.display.localized("新しい作品"))
                .help(model.display.tooltip("新しい作品", serverKey: "tooltipCanvasNavNewer"))
            Button { navigateHistory(delta: 1) } label: { Image(systemName: "chevron.right") }
                .disabled(!history.canMoveOlder)
                .accessibilityLabel(model.display.localized("古い作品"))
                .help(model.display.tooltip("古い作品", serverKey: "tooltipCanvasNavOlder"))
            Button(model.display.localized("最古")) { navigateHistory(boundary: "oldest") }
                .disabled(!history.canMoveOlder)
                .help(model.display.tooltip("最古の履歴", serverKey: "tooltipCanvasNavOldest"))
        }
    }

    private func navigateHistory(delta: Int = 0, boundary: String? = nil) {
        guard !browsingDisabled else { return }
        let workID = workspaceWork?.id
        batchWorkspace.invalidateReads()
        let revision = batchWorkspace.revision
        Task {
            guard let work = await history.navigate(app: model, fromWorkID: workID, delta: delta,
                                                   boundary: boundary, selectWork: false) else { return }
            guard batchWorkspace.revision == revision, !browsingDisabled else {
                await history.locate(app: model, workID: workspaceWork?.id)
                return
            }
            batchWorkspace.showHistory()
            await model.selectWork(work)
        }
    }

    private func tip(_ key: String) -> String {
        let serverKeys = ["次の作品の描画モデルを選びます。": "tooltipInputModel", "次の作品の配色を選びます。": "tooltipInputCatalog",
                          "次の作品の指示書に使う言語を選びます。": "tooltipInputLang", "次の作品の筆致を規則から外します。": "tooltipInputWild",
                          "用紙の形と意図を見て、次の作品の用紙を選びます。": "tooltipInputCanvas", "入力と次の生成条件から作品を描きます。": "tooltipSubmit",
                          "歳時記の語と説明を参照します。": "tooltipSaijikiToggle"]
        return model.display.tooltip(key, serverKey: serverKeys[key])
    }
}

struct OutputView: View {
    @Environment(\.locale) private var locale
    let ddl: String
    let score: String
    @State private var tab = "ddl"

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Picker(InkuLocalization.string("出力", locale: locale), selection: $tab) {
                Text("DDL").tag("ddl")
                Text("Score").tag("score")
            }
            .pickerStyle(.segmented)
            ScrollView {
                Text(tab == "ddl" ? ddl : score)
                    .font(.system(.caption, design: .monospaced))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
            }
            .background(.background, in: RoundedRectangle(cornerRadius: 6))
        }
    }
}
