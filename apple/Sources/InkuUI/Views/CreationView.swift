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
    @State private var showWorkInfo = false
    @State private var showColorCatalogs = false
    @State private var showModelPicker = false
    @State private var showConditionDetails = false
    @State private var showPaperPicker = false
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
                            VStack(alignment: .leading, spacing: 14) { input; nextConditions }
                                .padding(12)
                        }
                        Divider()
                        generationAction.padding(12).background(.bar)
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
                            input
                            nextConditions
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
        .sheet(isPresented: $showWorkInfo) { CreationWorkInfoView(model: model).environment(model.display) }
        .onAppear {
            if model.inputMode == "ddl", model.catalogMode == "auto" { model.catalogMode = "fixed" }
        }
        .onChange(of: model.inputMode) { _, mode in
            if mode == "ddl", model.catalogMode == "auto" { model.catalogMode = "fixed" }
        }
    }

    private var input: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(model.display.localized("作品を作る")).font(.title2.weight(.semibold))
                Spacer()
                Button(model.display.localized("新規")) {
                    #if os(macOS)
                    importer.clearMessage()
                    #endif
                    model.newWork()
                }.disabled(model.isBusy)
                    .help(tip("入力をクリアして、新しい作品を始めます。"))
            }
            Picker(model.display.localized("入力"), selection: $model.inputMode) {
                Text(model.display.localized("記述")).tag("description")
                Text("DDL").tag("ddl")
            }
            .pickerStyle(.segmented)
            .disabled(model.isBusy)
            .help(tip("記述から描くか、DDLから描くかを選びます。"))

            if model.inputMode == "description" {
                editor(text: $model.descriptionText, placeholder: "描きたいものや情景を記述", height: 120,
                       readOnly: model.sourceLocked && model.selectedWork != nil)
                DescriptionMeterView(model: model, text: model.descriptionText)
                if model.sourceLocked && model.selectedWork != nil {
                    Text(model.display.localized("この作品の記述はロックされています。別の記述で生成するには「新規」を選んでください。"))
                        .font(.caption).foregroundStyle(.secondary)
                }
            } else {
                if !model.visibleDDL.isEmpty && !model.isPreview {
                    DdlAuthoringView(model: model, showsDiagnostics: false)
                } else {
                    editor(text: $model.ddlText, placeholder: "DDLを入力", monospaced: true, height: 140)
                }
                PluginReferenceView(model: model, text: model.ddlText)
                #if os(macOS)
                DDLImportButton(model: model)
                #endif
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var nextConditions: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(model.display.localized("次の生成条件"), systemImage: "slider.horizontal.3")
                .font(.subheadline.weight(.semibold))
            Button { showModelPicker = true } label: {
                conditionRow("モデル", value: model.nextDrawingModelReference.isEmpty ? model.display.localized("選択してください") : model.nextDrawingModelReference)
            }
            .buttonStyle(.plain).disabled(model.isBusy)
            .help(tip("次の作品の描画モデルを選びます。"))
            .popover(isPresented: $showModelPicker) {
                CreationModelPicker(model: model).padding(16).frame(width: 380).environment(model.display)
            }
            Button { showColorCatalogs = true } label: {
                conditionRow("色カタログ", value: catalogSummary)
            }
            .buttonStyle(.plain).disabled(model.isBusy || model.catalogs.isEmpty)
            .accessibilityLabel(model.display.localized("色カタログを開く"))
            .accessibilityValue(catalogSummary)
            .help(tip("次の作品の配色を選びます。"))
            Divider()
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 10) { compactConditionControls }
                VStack(alignment: .leading, spacing: 8) { compactConditionControls }
            }
            .controlSize(.small).disabled(model.isBusy)
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
            .controlSize(.small).disabled(model.isBusy)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var catalogSummary: String {
        model.catalogMode == "fixed" ? model.catalogs.first { $0.id == model.catalogID }?.name ?? model.catalogID
            : model.display.localized(model.catalogMode == "random" ? "ランダム" : "記述から選択")
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
        if model.inputMode == "description" {
            Menu {
                Button(model.display.localized("使わない")) { model.sketchMode = "off" }
                Button(model.display.localized("生成する")) { model.sketchMode = "on" }
                Button(model.display.localized("指定する")) { model.sketchMode = "supplied"; showConditionDetails = true }
            } label: {
                Text(model.display.localized("写生") + ": " + model.display.localized(model.sketchMode == "on" ? "オン" : model.sketchMode == "supplied" ? "指定" : "オフ"))
            }.help(tip("次の作品で写生を使うかを選びます。"))
        }
        Button(model.display.localized("暴れる") + ": " + model.display.localized(model.wild ? "オン" : "オフ")) { model.wild.toggle() }
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
            Picker(model.display.localized("言語"), selection: $model.language) {
                Text(model.display.localized("日本語")).tag("ja"); Text("English").tag("en")
            }.help(tip("次の作品の指示書に使う言語を選びます。"))
            Picker(model.display.localized("配色の選び方"), selection: $model.catalogMode) {
                Text(model.display.localized("指定")).tag("fixed")
                Text(model.display.localized("ランダム")).tag("random")
                if model.inputMode == "description" { Text(model.display.localized("記述から選択")).tag("auto") }
            }.help(tip("指定した配色・ランダム・記述からの選択を切り替えます。"))
            TextField(model.display.localized("シード（空欄で新規）"), text: $model.seedText).textFieldStyle(.roundedBorder)
                .help(tip("空欄なら次の描画で新しいシードを使います。"))
            if model.inputMode == "description", model.sketchMode == "supplied" {
                editor(text: $model.sketchText, placeholder: "場所と光を補う写生", height: 110)
            }
        }.padding(16).frame(width: 360).disabled(model.isBusy)
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
                    .help(tip("実行中の描画を停止します。"))
            } else {
                Button { Task { await model.generate() } } label: {
                    Label(model.display.localized("生成"), systemImage: "play.fill").frame(maxWidth: .infinity)
                }
                    .buttonStyle(.borderedProminent)
                    .frame(maxWidth: .infinity)
                    .disabled(!model.canGenerate)
                    .help(tip("入力と次の生成条件から作品を描きます。"))
            }
        }
        .controlSize(.large)
    }

    private func editor(text: Binding<String>, placeholder: String, monospaced: Bool = false, height: CGFloat, readOnly: Bool = false) -> some View {
        ZStack(alignment: .topLeading) {
            TextEditor(text: text)
                .font(monospaced ? .system(.body, design: .monospaced) : .body)
                .scrollContentBackground(.hidden)
                .padding(6)
                .disabled(model.isBusy || readOnly)
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
                if model.displayedWork != nil {
                    Button { showWorkInfo = true } label: {
                        Label(model.display.localized("生成情報"), systemImage: "info.circle")
                            .font(.caption)
                    }
                    .buttonStyle(.plain)
                    .help(tip("表示中作品の指示書と保存条件を表示します。"))
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
            LibraryAnnotationMarkButton(model: model, work: work, mark: .revision)
            LibraryAnnotationMarkButton(model: model, work: work, mark: .share)
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

    private func tip(_ key: String) -> String {
        model.display.preferences.showTooltips ? model.display.localized(key) : ""
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
