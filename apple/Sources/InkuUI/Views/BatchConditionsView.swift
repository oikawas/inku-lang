import InkuHost
import SwiftUI

@MainActor
struct BatchConditionsView: View {
    @Bindable var model: AppModel
    @Bindable var automation: AutomationModel
    @State private var showModelPicker = false
    @State private var showColorCatalogs = false
    @State private var showPaperPicker = false
    @State private var showDetails = false
    @Environment(\.inkuWindowSize) private var windowSize

    private var disabled: Bool { automation.isOccupied || model.isBusy }
    private var frozen: BatchDrawingConditions? { automation.running ? automation.batchConditions : nil }
    private var shownSketchMode: String { frozen?.sketchMode ?? model.sketchMode }
    private var shownWild: Bool? { if let frozen { frozen.wild } else { model.wild } }
    private var shownCanvasID: String? { if let frozen { frozen.canvasID } else { model.canvasID } }
    private var frozenRequest: GenerationRequest? { frozen == nil ? nil : automation.rows.first?.request }

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
            DrawingConditionRow(display: model.display, label: model.display.webCopy("modelButton", "モデル"), value: modelSummary,
                                help: tip("次のバッチで使う描画モデルを選びます。")) { showModelPicker = true }
            Rectangle().fill(InkuColor.border).frame(height: 1)
            DrawingConditionRow(display: model.display, label: model.display.webCopy("colorCatalogButton", "色カタログ"), value: catalogSummary,
                                help: tip("次のバッチで使う配色を選びます。")) { showColorCatalogs = true }
            .disabled(model.catalogs.isEmpty)
            Rectangle().fill(InkuColor.border).frame(height: 1)
            DrawConditionsView(model: model, sketch: shownSketchMode, onSketch: { model.sketchMode = $0 },
                               frozenRoute: frozen == nil ? nil : (frozenRequest?.drawRoute ?? "stages"),
                               frozenComposition: frozen == nil ? nil : (frozenRequest?.descriptionComposition ?? false))
                .padding(.bottom, 8)
            Rectangle().fill(InkuColor.border).frame(height: 1)
            DrawingCompactConditions(model: model, wild: shownWild, canvasID: shownCanvasID, showPaperPicker: $showPaperPicker)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .disabled(disabled)
        .sheet(isPresented: $showModelPicker) {
            BatchModelPickerView(model: model).environment(model.display).disabled(disabled)
                .environment(\.inkuWindowSize, windowSize).inkuDialogFrame(.modelSelection)
        }
        .sheet(isPresented: $showColorCatalogs) {
            ColorCatalogView(model: model).environment(model.display).disabled(disabled)
                .environment(\.inkuWindowSize, windowSize).inkuDialogFrame(.colorCatalog)
        }
        .onChange(of: disabled) { _, busy in
            if busy {
                showModelPicker = false; showColorCatalogs = false
                showPaperPicker = false; showDetails = false
            }
        }
    }

    private var catalogSummary: String {
        DrawPresentation.catalogSummary(mode: frozen?.catalogMode ?? model.catalogMode,
            id: frozen == nil ? model.catalogID : frozen?.catalogID, catalogs: model.catalogs,
            auto: model.display.webCopy("colorCatalogAuto", "記述から自動選択"),
            random: model.display.localized("ランダム"), missing: model.display.localized("未記録"))
    }

    private var modelSummary: String {
        let empty = model.display.localized("選択してください")
        if let frozen {
            let first = DrawPresentation.modelReference(frozen.stage1Model, empty: empty)
            return frozen.stage1Model == frozen.stage2Model ? first
                : first + " / " + DrawPresentation.modelReference(frozen.stage2Model, empty: empty)
        }
        return DrawPresentation.modelReference(model.nextBatchDrawingModelReference, empty: empty)
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
