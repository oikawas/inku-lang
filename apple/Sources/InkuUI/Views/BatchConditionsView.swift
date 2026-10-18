import SwiftUI

@MainActor
struct BatchConditionsView: View {
    @Bindable var model: AppModel
    @Bindable var automation: AutomationModel
    @State private var showModelPicker = false
    @State private var showColorCatalogs = false
    @State private var showSketchPicker = false
    @State private var showPaperPicker = false
    @State private var showDetails = false
    @Environment(\.inkuWindowSize) private var windowSize

    private var disabled: Bool { automation.isOccupied || model.isBusy }
    private var frozen: BatchDrawingConditions? { automation.running ? automation.batchConditions : nil }
    private var shownSketchMode: String { frozen?.sketchMode ?? automation.batchSketchMode }
    private var shownWild: Bool? { if let frozen { frozen.wild } else { model.wild } }
    private var shownCanvasID: String? { if let frozen { frozen.canvasID } else { model.canvasID } }
    private var shownCanvas: String {
        guard let id = shownCanvasID else { return model.display.localized("未記録") }
        return model.canvases.first { $0.id == id }?.label ?? id
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(model.display.webCopy("batchNextConditionsLabel", "次のバッチの描画条件"))
                    .inkuFont(12).foregroundStyle(.secondary)
                Spacer(minLength: 0)
                Button { showDetails = true } label: { Image(systemName: "ellipsis") }
                    .buttonStyle(InkuGhostButtonStyle())
                    .accessibilityLabel(model.display.localized("生成条件の詳細"))
                    .popover(isPresented: $showDetails) { details }
            }.padding(.bottom, 2)
            conditionRow("モデル", value: modelSummary) { showModelPicker = true }
            .inkuTooltip(tip("次のバッチで使う描画モデルを選びます。"))
            Divider()
            conditionRow("色カタログ", value: catalogSummary) { showColorCatalogs = true }
            .disabled(model.catalogs.isEmpty)
            .inkuTooltip(tip("次のバッチで使う配色を選びます。"))
            Divider()
            WrappingHStack(spacing: 6) { compactControls }
            .buttonStyle(InkuGhostButtonStyle())
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .disabled(disabled)
        .sheet(isPresented: $showModelPicker) {
            BatchModelPickerView(model: model).environment(model.display).disabled(disabled)
                .environment(\.inkuWindowSize, windowSize).inkuDialogFrame(.modelSelection)
        }
        .sheet(isPresented: $showColorCatalogs) {
            ColorCatalogView(model: model, descriptionOnly: true).environment(model.display).disabled(disabled)
                .environment(\.inkuWindowSize, windowSize).inkuDialogFrame(.colorCatalog)
        }
        .onChange(of: disabled) { _, busy in
            if busy {
                showModelPicker = false; showColorCatalogs = false
                showSketchPicker = false; showPaperPicker = false; showDetails = false
            }
        }
    }

    private var catalogSummary: String {
        if let frozen {
            if frozen.catalogMode == "auto" { return model.display.webCopy("colorCatalogAuto", "記述から自動選択") }
            if frozen.catalogMode == "random" { return model.display.localized("ランダム") }
            guard let id = frozen.catalogID else { return model.display.localized("未記録") }
            return model.catalogs.first { $0.id == id }?.name ?? id
        }
        return model.catalogMode == "auto"
            ? model.display.webCopy("colorCatalogAuto", "記述から自動選択")
            : model.catalogs.first { $0.id == model.catalogID }?.name ?? model.catalogID
    }

    private var modelSummary: String {
        let reference = frozen.map { $0.stage1Model == $0.stage2Model ? $0.stage1Model : $0.stage1Model + " / " + $0.stage2Model }
            ?? model.nextBatchDrawingModelReference
        guard let separator = reference.firstIndex(of: ":") else {
            return reference.isEmpty ? model.display.localized("選択してください") : reference
        }
        return String(reference[..<separator]) + " / " + String(reference[reference.index(after: separator)...])
    }

    private func conditionRow(_ key: String, value: String, action: @escaping () -> Void) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(alignment: .center, spacing: 12) {
                Text(model.display.localized(key)).inkuFont(12, weight: .medium).foregroundStyle(.secondary)
                Spacer(minLength: 0)
                Button(model.display.webCopy("editButton", "変更"), action: action)
                    .buttonStyle(InkuGhostButtonStyle())
                    .accessibilityLabel(model.display.localizedFormat("%@を変更", model.display.localized(key)))
                    .accessibilityValue(value)
            }
            Text(value).inkuFont(14).lineLimit(2).truncationMode(.middle).textSelection(.enabled)
        }
        .frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 7)
    }

    @ViewBuilder private var compactControls: some View {
        sketchControl
        wildControl
        paperControl
        clearControl
    }

    private var sketchControl: some View {
        Button { showSketchPicker = true } label: {
            Text(model.display.localized("写生") + ": " + model.display.localized(shownSketchMode == "on" ? "あり" : shownSketchMode == "supplied" ? "指定" : "なし"))
        }
        .inkuTooltip(tip("次の作品で写生を使うかを選びます。"))
        .accessibilityLabel(model.display.localized("写生"))
        .accessibilityValue(model.display.localized(shownSketchMode == "on" ? "あり" : shownSketchMode == "supplied" ? "指定" : "なし"))
        .popover(isPresented: $showSketchPicker) { sketchPicker }
    }

    private var sketchPicker: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(model.display.localized("写生")).inkuFont(12).foregroundStyle(.secondary)
            ForEach(["off", "on"], id: \.self) { mode in
                Button {
                    guard !disabled else { return }
                    automation.batchSketchMode = mode
                    showSketchPicker = false
                } label: {
                    HStack(alignment: .top, spacing: 10) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(model.display.localized(mode == "on" ? "あり" : "なし")).inkuFont(13, weight: .medium)
                            Text(model.display.localized(mode == "on"
                                ? "記述の横に、場所の広がりや季節・時刻の光を補って描く"
                                : "写生を通さず、記述だけで描く"))
                                .inkuFont(12).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                        }
                        Spacer(minLength: 0)
                        if automation.batchSketchMode == mode {
                            Image(systemName: "checkmark").foregroundStyle(.secondary)
                        }
                    }
                    .padding(8).frame(maxWidth: .infinity, alignment: .leading)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .background(automation.batchSketchMode == mode ? Color.secondary.opacity(0.08) : .clear,
                            in: RoundedRectangle(cornerRadius: 6))
            }
        }
        .padding(10).frame(width: 310).disabled(disabled)
    }

    private var wildControl: some View {
        Button {
            guard !disabled else { return }
            model.wild.toggle()
        } label: {
            Text(model.display.localized("暴れる") + " " + model.display.localized(shownWild.map { $0 ? "入" : "切" } ?? "未記録"))
        }
        .buttonStyle(InkuGhostButtonStyle(active: shownWild == true))
        .inkuTooltip(tip("次の作品の筆致を規則から外します。"))
        .accessibilityLabel(model.display.localized("暴れる"))
        .accessibilityValue(model.display.localized(shownWild.map { $0 ? "入" : "切" } ?? "未記録"))
    }

    private var paperControl: some View {
        Button { showPaperPicker = true } label: {
            Text(model.display.localized("キャンバス") + (model.display.preferences.language == "ja" ? "：" : ": ")
                 + shownCanvas)
                .lineLimit(1)
        }
        .inkuTooltip(tip("用紙の形と意図を見て、次の作品の用紙を選びます。"))
        .popover(isPresented: $showPaperPicker) {
            CreationPaperPicker(model: model) { showPaperPicker = false }.environment(model.display).disabled(disabled)
        }
        .accessibilityValue(shownCanvas)
    }

    private var clearControl: some View {
        Button(model.display.webCopy("clearInputBtn", "新規作成")) {
            guard !disabled else { return }
            automation.restoreBatchInput("")
        }
        .inkuTooltip(model.display.tooltip("入力をクリアする", serverKey: "tooltipInputClear"))
    }

    private var details: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(model.display.localized("生成条件の詳細")).inkuFont(14, weight: .semibold)
            Text(model.display.localized("描画条件はバッチ開始時に固定します。再開には前回の条件を使います。"))
                .inkuFont(12).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            TextField(model.display.localized("シード（空欄で新規）"), text: $model.seedText).textFieldStyle(.roundedBorder)
                .inkuTooltip(tip("空欄なら次の描画で新しいシードを使います。"), focus: .text)
        }
        .padding(16).frame(width: 340).disabled(disabled)
    }

    private func tip(_ key: String) -> String {
        let serverKeys = ["次のバッチで使う描画モデルを選びます。": "tooltipInputModel", "次のバッチで使う配色を選びます。": "tooltipInputCatalog",
                          "次の作品で写生を使うかを選びます。": "tooltipInputSketch", "次の作品の筆致を規則から外します。": "tooltipInputWild",
                          "用紙の形と意図を見て、次の作品の用紙を選びます。": "tooltipInputCanvas"]
        return model.display.tooltip(key, serverKey: serverKeys[key])
    }
}
