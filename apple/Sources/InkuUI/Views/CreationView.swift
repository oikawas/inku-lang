import InkuPersistence
import SwiftUI

@MainActor
struct CreationView: View {
    @Bindable var model: AppModel
    @Bindable var history: HistoryModel
    let onEditWork: (SavedWork, WorkEditMode) -> Void
    let onAdjustWork: (SavedWork) -> Void
    let onReplayWork: (SavedWork) -> Void
    @State private var showSaijiki = false
    @State private var workspaceTab = "artwork"
    @State private var sketchExpanded = false
    @State private var outputExpanded = false
    @State private var conditionsExpanded = false
    @State private var showWorkInfo = false
    @State private var showColorCatalogs = false
    #if os(macOS)
    @Environment(DDLImportController.self) private var importer
    #endif

    var body: some View {
        VStack(spacing: 0) {
          GeometryReader { geometry in
            if geometry.size.width >= 800 {
                HStack(alignment: .top, spacing: 0) {
                    VStack(spacing: 0) {
                        ScrollView {
                            VStack(alignment: .leading, spacing: 16) { input; nextConditions; authoringInspector }
                                .padding(16)
                        }
                        Divider()
                        generationAction.padding(16).background(.bar)
                    }
                    .frame(width: 340)
                    .background(.quaternary.opacity(0.16))
                    Divider()
                    workspace.padding(16)
                }
            } else {
                VStack(spacing: 0) {
                    ScrollView {
                        VStack(spacing: 16) {
                            input
                            nextConditions
                            authoringInspector
                            workspace.frame(height: max(480, geometry.size.height * 0.85))
                        }
                        .padding(16)
                    }
                    Divider()
                    generationAction.padding(16).background(.bar)
                }
            }
          }
          if model.display.visible("history") { Divider(); HistoryStripView(model: model, history: history) }
        }
        .sheet(isPresented: $showSaijiki) {
            VStack(spacing: 0) {
                HStack { Spacer(); Button(model.display.localized("閉じる")) { showSaijiki = false } }.padding(12)
                SaijikiView(model: model)
            }.frame(minWidth: 560, minHeight: 620)
        }
        .sheet(isPresented: $showColorCatalogs) { ColorCatalogView(model: model) }
        .onAppear {
            if model.inputMode == "ddl", model.catalogMode == "auto" { model.catalogMode = "fixed" }
        }
        .onChange(of: model.inputMode) { _, mode in
            if mode == "ddl", model.catalogMode == "auto" { model.catalogMode = "fixed" }
        }
        .onChange(of: model.displayedWork?.id) { _, _ in
            if !model.display.preferences.keepGenerationInfo {
                sketchExpanded = false; outputExpanded = false; conditionsExpanded = false
            }
        }
    }

    private var input: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text(model.display.localized("作品を作る")).font(.title2.weight(.semibold))
                Spacer()
                Button(model.display.localized("新規")) {
                    #if os(macOS)
                    importer.clearMessage()
                    #endif
                    model.newWork()
                }.disabled(model.isBusy)
            }
            Picker(model.display.localized("入力"), selection: $model.inputMode) {
                Text(model.display.localized("記述")).tag("description")
                Text("DDL").tag("ddl")
            }
            .pickerStyle(.segmented)
            .disabled(model.isBusy)

            if model.inputMode == "description" {
                editor(text: $model.descriptionText, placeholder: "描きたいものや情景を記述", height: 170)
                DescriptionMeterView(model: model, text: model.descriptionText)
                if model.sourceLocked && model.selectedWork != nil {
                    Text(model.display.localized("この作品の記述はロックされています。別の記述で生成するには「新規」を選んでください。"))
                        .font(.caption).foregroundStyle(.secondary)
                }
            } else {
                if !model.visibleDDL.isEmpty && !model.isPreview {
                    DdlAuthoringView(model: model)
                } else {
                    editor(text: $model.ddlText, placeholder: "DDLを入力", monospaced: true, height: 220)
                }
                PluginReferenceView(model: model, text: model.ddlText)
                #if os(macOS)
                DDLImportButton(model: model)
                #endif
            }
        }
        .creationPanel()
    }

    private var nextConditions: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label(model.display.localized("次の生成条件"), systemImage: "slider.horizontal.3")
                .font(.headline)
            CreationModelPicker(model: model)
            Divider()
            Picker(model.display.localized("言語"), selection: $model.language) {
                Text(model.display.localized("日本語")).tag("ja")
                Text("English").tag("en")
            }
            .disabled(model.isBusy)
            Picker(model.display.localized("配色の選び方"), selection: $model.catalogMode) {
                Text(model.display.localized("指定")).tag("fixed")
                Text(model.display.localized("ランダム")).tag("random")
                if model.inputMode == "description" { Text(model.display.localized("記述から選択")).tag("auto") }
            }.disabled(model.isBusy)
            Button { showColorCatalogs = true } label: {
                ColorCatalogPreview(catalog: model.catalogs.first { $0.id == model.catalogID }, mode: model.catalogMode, display: model.display)
            }
            .buttonStyle(.plain)
            .disabled(model.isBusy || model.catalogs.isEmpty)
            .accessibilityLabel(model.display.localized("色カタログを開く"))
            .accessibilityValue(model.catalogMode == "fixed" ? model.catalogs.first { $0.id == model.catalogID }?.name ?? model.catalogID : model.display.localized(model.catalogMode == "random" ? "ランダム" : "記述から選択"))
            .help(model.display.preferences.showTooltips ? model.display.localized("色カタログを開く") : "")
            Picker(model.display.localized("用紙"), selection: $model.canvasID) {
                ForEach(model.canvases, id: \.id) { item in Text(item.name).tag(item.id) }
            }
            .disabled(model.isBusy)
            TextField(model.display.localized("シード（空欄で新規）"), text: $model.seedText)
                .textFieldStyle(.roundedBorder)
                .disabled(model.isBusy)
            Toggle(model.display.localized("暴れる"), isOn: $model.wild).disabled(model.isBusy)
            if model.inputMode == "description" {
                Picker(model.display.localized("写生"), selection: $model.sketchMode) {
                    Text(model.display.localized("使わない")).tag("off")
                    Text(model.display.localized("生成する")).tag("on")
                    Text(model.display.localized("指定する")).tag("supplied")
                }.disabled(model.isBusy)
                if model.sketchMode == "supplied" {
                    editor(text: $model.sketchText, placeholder: "場所と光を補う写生", height: 110)
                }
            }
            if model.display.visible("saijiki") {
                Button(model.display.localized("歳時記を開く"), systemImage: "book") { showSaijiki = true }
            }
        }
        .creationPanel()
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
                .disabled(model.isBusy)
            }
            if model.isBusy {
                Button { Task { await model.cancel() } } label: {
                    Label(model.display.localized("停止"), systemImage: "stop.fill").frame(maxWidth: .infinity)
                }
                    .buttonStyle(.bordered)
                    .frame(maxWidth: .infinity)
            } else {
                Button { Task { await model.generate() } } label: {
                    Label(model.display.localized("生成"), systemImage: "play.fill").frame(maxWidth: .infinity)
                }
                    .buttonStyle(.borderedProminent)
                    .frame(maxWidth: .infinity)
                    .disabled(!model.canGenerate)
            }
        }
        .controlSize(.large)
    }

    private func editor(text: Binding<String>, placeholder: String, monospaced: Bool = false, height: CGFloat) -> some View {
        ZStack(alignment: .topLeading) {
            TextEditor(text: text)
                .font(monospaced ? .system(.body, design: .monospaced) : .body)
                .scrollContentBackground(.hidden)
                .padding(6)
                .disabled(model.isBusy)
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
              HStack(spacing: 12) {
                Picker(model.display.localized("表示"), selection: $workspaceTab) { Text(model.display.localized("作品")).tag("artwork"); Text(model.display.localized("系譜")).tag("lineage") }
                    .pickerStyle(.segmented).labelsHidden().frame(width: 150)
                    .accessibilityLabel(model.display.localized("表示"))
                Spacer()
                if let work = model.displayedWork {
                    Button { showWorkInfo = true } label: {
                        Label(model.display.localized("表示中の作品"), systemImage: "info.circle")
                            .font(.caption)
                    }
                    .buttonStyle(.plain)
                    .help(model.display.preferences.showTooltips ? model.display.localized("保存条件") : "")
                    .popover(isPresented: $showWorkInfo) { savedFacts(work).padding(20).frame(width: 320) }
                }
              }
              if let work = model.displayedWork {
                  Text(savedSummary(work))
                      .font(.caption).foregroundStyle(.secondary)
                      .lineLimit(1).truncationMode(.middle)
                      .frame(maxWidth: .infinity, alignment: .leading)
                      .help(model.display.preferences.showTooltips ? savedSummary(work) : "")
                      .accessibilityLabel(savedSummary(work))
              }
            }
            if workspaceTab == "lineage" { LineageView(model: model, onEditWork: onEditWork, onAdjustWork: onAdjustWork, onReplayWork: onReplayWork) }
            else {
                ArtworkCanvas(svg: model.currentSVG, renderer: model.renderer, caption: model.displayedWork?.effectiveSourceText ?? "")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            if model.isPreview {
                VStack(alignment: .leading, spacing: 8) {
                    Label(model.display.localized("未保存の候補"), systemImage: "eye")
                    HStack {
                        Button(model.display.localized("この候補を保存")) { Task { await model.savePreview() } }.buttonStyle(.borderedProminent)
                        Button(model.display.localized("候補を閉じる")) { Task { await model.clearPreview() } }
                    }
                }.disabled(model.isBusy)
            }
            if let work = model.selectedWork, !model.isPreview {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 16) { workActions(work); navigationActions }.fixedSize(horizontal: true, vertical: false)
                    VStack(alignment: .leading, spacing: 8) { workActions(work); navigationActions }
                }
                .controlSize(.small).disabled(model.isBusy)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private func savedSummary(_ work: SavedWork) -> String {
        [work.stage1Model ?? "DDL", work.renderColorCatalogName ?? work.renderColorCatalogID ?? work.catalogID ?? "—",
         work.renderCanvasAspectID ?? "—", ByteCountFormatter.string(fromByteCount: Int64(work.svg.utf8.count), countStyle: .file)].joined(separator: " · ")
    }

    private func savedFacts(_ work: SavedWork) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(model.display.localized("表示中の作品")).font(.headline)
            LabeledContent(model.display.localized("モデル"), value: work.stage1Model ?? "DDL")
            LabeledContent(model.display.localized("配色"), value: work.renderColorCatalogName ?? work.renderColorCatalogID ?? work.catalogID ?? "—")
            LabeledContent(model.display.localized("用紙"), value: work.renderCanvasAspectID ?? "—")
            LabeledContent(model.display.localized("ファイル容量"), value: ByteCountFormatter.string(fromByteCount: Int64(work.svg.utf8.count), countStyle: .file))
            Text(model.display.localizedFormat("シード: %@ · 暴れる: %@", work.renderSeed ?? model.display.localized("未記録"), model.display.localized(work.renderWild == true ? "オン" : "オフ")))
                .font(.caption).foregroundStyle(.secondary)
        }.textSelection(.enabled)
    }

    private func workActions(_ work: SavedWork) -> some View {
        HStack(spacing: 8) {
            Menu(model.display.localized("推敲する")) {
                Button(model.display.localized("描画パラメータの編集"), systemImage: "slider.horizontal.3") { onAdjustWork(work) }
                Button(model.display.localized("記述を変える"), systemImage: "text.cursor") { onEditWork(work, .description) }
                    .disabled(model.sourceLocked)
                Button(model.display.localized("写生なし／ありで描き直す"), systemImage: "pencil.and.outline") { onEditWork(work, .sketch) }
                    .disabled(model.sourceLocked)
            }
            Button { Task { await model.library.toggleStar(work) } } label: { Image(systemName: work.starred ? "star.fill" : "star") }
                .accessibilityLabel(model.display.localized("スター"))
                .accessibilityValue(model.display.localized(work.starred ? "オン" : "オフ"))
                .help(model.display.preferences.showTooltips ? model.display.localized("スター") : "")
            Button { Task { await model.library.toggleRevision(work) } } label: { Image(systemName: model.library.annotation(for: work.id).forRevision ? "pencil.circle.fill" : "pencil.circle") }
                .accessibilityLabel(model.display.localized("推敲の印"))
                .accessibilityValue(model.display.localized(model.library.annotation(for: work.id).forRevision ? "オン" : "オフ"))
                .help(model.display.preferences.showTooltips ? model.display.localized("推敲の印") : "")
            Button { Task { await model.library.toggleShare(work) } } label: { Image(systemName: model.library.annotation(for: work.id).forShare ? "square.and.arrow.up.fill" : "square.and.arrow.up") }
                .accessibilityLabel(model.display.localized("書き出し用の印"))
                .accessibilityValue(model.display.localized(model.library.annotation(for: work.id).forShare ? "オン" : "オフ"))
                .help(model.display.preferences.showTooltips ? model.display.localized("書き出し用の印") : "")
            Button(model.display.localized("再演奏"), systemImage: "arrow.clockwise") { onReplayWork(work) }.disabled(model.isBusy)
        }
    }

    private var navigationActions: some View {
        HStack(spacing: 8) {
            Button(model.display.localized("最新")) { Task { await history.navigate(app: model, boundary: "latest") } }
            Button { Task { await history.navigate(app: model, delta: -1) } } label: { Image(systemName: "chevron.left") }
                .accessibilityLabel(model.display.localized("新しい作品"))
                .help(model.display.preferences.showTooltips ? model.display.localized("新しい作品") : "")
            Button { Task { await history.navigate(app: model, delta: 1) } } label: { Image(systemName: "chevron.right") }
                .accessibilityLabel(model.display.localized("古い作品"))
                .help(model.display.preferences.showTooltips ? model.display.localized("古い作品") : "")
            Button(model.display.localized("最古")) { Task { await history.navigate(app: model, boundary: "oldest") } }
        }
    }

    @ViewBuilder private var authoringInspector: some View {
        if let work = model.displayedWork {
          VStack(alignment: .leading, spacing: 14) {
            Text(model.display.localized("表示中作品の写生と指示書")).font(.headline)
            if model.display.visible("diagnostics"), model.authoringOrigin == "stage1_generated", let ddl = work.ddl {
                DescriptionFeedbackView(description: work.effectiveSourceText, ddl: ddl)
            }
            if let sketch = work.sketchText, !sketch.isEmpty {
                DisclosureGroup(model.display.localized("写生 (Stage 0.5)"), isExpanded: $sketchExpanded) { Text(sketch).font(.callout).textSelection(.enabled) }
            }
            if let grain = work.sketchGrain { Text(model.display.localizedFormat("旧写生の区切り: %@（保存記録）", grain)).font(.caption).foregroundStyle(.secondary) }
            if model.inputMode == "description", !model.visibleDDL.isEmpty && !model.isPreview { DdlAuthoringView(model: model) }
            if model.display.visible("diagnostics") {
                ProviderObservationView(model: model, metrics: model.providerMetrics, workID: work.id)
                DisclosureGroup(model.display.localized("指示書・Score"), isExpanded: $outputExpanded) { OutputView(ddl: model.visibleDDL, score: model.scoreJSON).frame(height: 230) }
                DisclosureGroup(model.display.localized("保存条件"), isExpanded: $conditionsExpanded) {
                    savedFacts(work).padding(.top, 8)
                }
            }
            if !model.isPreview {
                Button(model.display.localized("次の条件で再演奏")) { Task { await model.replayWithCurrentOptions() } }.disabled(model.isBusy)
                DisclosureGroup(model.display.localized("変奏（いまは何も動かない）")) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(model.display.localized("動いたもの: なし")).font(.callout).foregroundStyle(.secondary)
                        Picker(model.display.localized("変奏の幅"), selection: $model.variationAmplitude) { Text(model.display.localized("小")).tag("small"); Text(model.display.localized("中")).tag("medium"); Text(model.display.localized("大")).tag("large") }
                        TextField(model.display.localized("変奏シード（空欄で新規）"), text: $model.variationSeedText).textFieldStyle(.roundedBorder)
                        Button(model.display.localized("変奏を保存")) { Task { await model.varySelectedWork() } }
                    }.disabled(model.isBusy || work.ddl == nil)
                }
            }
          }
          .creationPanel()
        }
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
