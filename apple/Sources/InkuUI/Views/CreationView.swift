import InkuPersistence
import SwiftUI

@MainActor
struct CreationView: View {
    @Bindable var model: AppModel
    @Bindable var history: HistoryModel
    @State private var showSaijiki = false
    @State private var workspaceTab = "artwork"
    @State private var sketchExpanded = false
    @State private var outputExpanded = false
    @State private var conditionsExpanded = false

    var body: some View {
        VStack(spacing: 0) {
          GeometryReader { geometry in
            if geometry.size.width >= 850 {
                HStack(alignment: .top, spacing: 0) {
                    ScrollView { VStack(alignment: .leading, spacing: 20) { input; authoringInspector }.padding(20) }.frame(width: 340)
                    Divider()
                    workspace.padding(20)
                }
            } else {
                ScrollView {
                    VStack(spacing: 20) {
                        input
                        authoringInspector
                        workspace.frame(minHeight: 460)
                    }
                    .padding(16)
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
                Button(model.display.localized("新規")) { model.newWork() }.disabled(model.isBusy)
            }
            Picker(model.display.localized("入力"), selection: $model.inputMode) {
                Text(model.display.localized("記述")).tag("description")
                Text("DDL").tag("ddl")
            }
            .pickerStyle(.segmented)
            .disabled(model.isBusy)

            if model.inputMode == "description" {
                editor(text: $model.descriptionText, placeholder: "描きたいものや情景を記述")
                DescriptionMeterView(model: model, text: model.descriptionText)
                if model.sourceLocked && model.selectedWork != nil {
                    Text(model.display.localized("この作品の記述はロックされています。別の記述で生成するには「新規」を選んでください。"))
                        .font(.caption).foregroundStyle(.secondary)
                }
            } else {
                editor(text: $model.ddlText, placeholder: "DDLを入力", monospaced: true)
                PluginReferenceView(model: model, text: model.ddlText)
                #if os(macOS)
                DDLImportButton(model: model)
                #endif
            }

            Text(model.display.localized("次の生成条件")).font(.headline)
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
            Picker(model.display.localized("配色"), selection: $model.catalogID) {
                ForEach(model.catalogs, id: \.id) { item in Text(item.name).tag(item.id) }
            }
            .disabled(model.isBusy)
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
                    editor(text: $model.sketchText, placeholder: "場所と光を補う写生")
                }
            }
            if model.display.visible("saijiki") {
                Button(model.display.localized("歳時記を開く"), systemImage: "book") { showSaijiki = true }
            }

            if model.inputMode == "description" && !model.hasConfiguredProviders {
                Label(model.display.localized("記述から生成するには、設定で接続先とモデルを指定してください。"), systemImage: "info.circle")
                    .font(.callout).foregroundStyle(.secondary)
            }
            if model.isBusy {
                Button(model.display.localized("停止"), systemImage: "stop.fill") { Task { await model.cancel() } }
                    .frame(maxWidth: .infinity)
            } else {
                Button(model.display.localized("生成"), systemImage: "play.fill") { Task { await model.generate() } }
                    .buttonStyle(.borderedProminent)
                    .frame(maxWidth: .infinity)
                    .disabled(!model.canGenerate)
            }
        }
    }

    private func editor(text: Binding<String>, placeholder: String, monospaced: Bool = false) -> some View {
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
        .frame(minHeight: 220, maxHeight: 300)
        .background(.background, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
        .accessibilityLabel(model.display.localized(monospaced ? "DDL" : "記述"))
    }

    private var workspace: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top) {
                Picker(model.display.localized("表示"), selection: $workspaceTab) { Text(model.display.localized("作品")).tag("artwork"); Text(model.display.localized("系譜")).tag("lineage") }
                    .pickerStyle(.segmented).frame(width: 145)
                Spacer()
                if let work = model.displayedWork {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 14) { displayedFacts(work) }
                        VStack(alignment: .trailing, spacing: 4) { displayedFacts(work) }
                    }.font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
            }
            if workspaceTab == "lineage" { LineageView(model: model) }
            else {
                ArtworkCanvas(svg: model.currentSVG, renderer: model.renderer, caption: model.displayedWork?.effectiveSourceText ?? "")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            if model.isPreview {
                HStack {
                    Label(model.display.localized("未保存の候補"), systemImage: "eye")
                    Spacer()
                    Button(model.display.localized("この候補を保存")) { Task { await model.savePreview() } }
                    Button(model.display.localized("候補を閉じる")) { Task { await model.clearPreview() } }
                }.disabled(model.isBusy)
            }
            if let work = model.selectedWork, !model.isPreview {
                HStack(spacing: 12) {
                    Button { Task { await model.library.toggleStar(work) } } label: { Image(systemName: work.starred ? "star.fill" : "star") }.accessibilityLabel(model.display.localized("スター"))
                    Button { Task { await model.library.toggleRevision(work) } } label: { Image(systemName: model.library.annotation(for: work.id).forRevision ? "pencil.circle.fill" : "pencil.circle") }.accessibilityLabel(model.display.localized("推敲の印"))
                    Button { Task { await model.library.toggleShare(work) } } label: { Image(systemName: model.library.annotation(for: work.id).forShare ? "square.and.arrow.up.fill" : "square.and.arrow.up") }.accessibilityLabel(model.display.localized("書き出し用の印"))
                    Button(model.display.localized("再演奏"), systemImage: "arrow.clockwise") { Task { await model.replay(work) } }
                    Spacer()
                    Button(model.display.localized("最新")) { Task { await history.navigate(app: model, boundary: "latest") } }
                    Button { Task { await history.navigate(app: model, delta: -1) } } label: { Image(systemName: "chevron.left") }.accessibilityLabel(model.display.localized("新しい作品"))
                    Button { Task { await history.navigate(app: model, delta: 1) } } label: { Image(systemName: "chevron.right") }.accessibilityLabel(model.display.localized("古い作品"))
                    Button(model.display.localized("最古")) { Task { await history.navigate(app: model, boundary: "oldest") } }
                }.controlSize(.small).disabled(model.isBusy)
            }
        }
    }

    @ViewBuilder private func displayedFacts(_ work: SavedWork) -> some View {
        Text(model.display.localized("表示中の作品")).fontWeight(.semibold)
        Text(work.stage1Model ?? "DDL")
        Text(work.renderColorCatalogName ?? work.renderColorCatalogID ?? work.catalogID ?? "—")
        Text(work.renderCanvasAspectID ?? "—")
        Text(ByteCountFormatter.string(fromByteCount: Int64(work.svg.utf8.count), countStyle: .file))
    }

    @ViewBuilder private var authoringInspector: some View {
        if let work = model.displayedWork {
            Divider()
            Text(model.display.localized("表示中作品の写生と指示書")).font(.headline)
            if model.display.visible("diagnostics"), model.authoringOrigin == "stage1_generated", let ddl = work.ddl {
                DescriptionFeedbackView(description: work.effectiveSourceText, ddl: ddl)
            }
            if let sketch = work.sketchText, !sketch.isEmpty {
                DisclosureGroup(model.display.localized("写生 (Stage 0.5)"), isExpanded: $sketchExpanded) { Text(sketch).font(.callout).textSelection(.enabled) }
            }
            if let grain = work.sketchGrain { Text(model.display.localizedFormat("旧写生の区切り: %@（保存記録）", grain)).font(.caption).foregroundStyle(.secondary) }
            if !model.visibleDDL.isEmpty && !model.isPreview { DdlAuthoringView(model: model) }
            if model.display.visible("diagnostics") {
                DisclosureGroup(model.display.localized("指示書・Score"), isExpanded: $outputExpanded) { OutputView(ddl: model.visibleDDL, score: model.scoreJSON).frame(height: 230) }
                DisclosureGroup(model.display.localized("保存条件"), isExpanded: $conditionsExpanded) {
                    Text(model.display.localizedFormat("シード: %@ · 暴れる: %@", work.renderSeed ?? model.display.localized("未記録"), model.display.localized(work.renderWild == true ? "オン" : "オフ")))
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            if !model.isPreview {
                Button(model.display.localized("次の条件で再演奏")) { Task { await model.replayWithCurrentOptions() } }.disabled(model.isBusy)
                DisclosureGroup(model.display.localized("DDLの変奏")) {
                    VStack(alignment: .leading, spacing: 8) {
                        Picker(model.display.localized("変奏の幅"), selection: $model.variationAmplitude) { Text(model.display.localized("小")).tag("small"); Text(model.display.localized("中")).tag("medium"); Text(model.display.localized("大")).tag("large") }
                        TextField(model.display.localized("変奏シード（空欄で新規）"), text: $model.variationSeedText).textFieldStyle(.roundedBorder)
                        Button(model.display.localized("変奏を保存")) { Task { await model.varySelectedWork() } }
                    }.disabled(model.isBusy || work.ddl == nil)
                }
            }
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
