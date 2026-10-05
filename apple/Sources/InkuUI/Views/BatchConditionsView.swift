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

    private var disabled: Bool { automation.isOccupied || model.isBusy }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(model.display.localized("次のバッチの描画条件"))
                .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            conditionRow("モデル", value: modelSummary) { showModelPicker = true }
            .help(tip("次のバッチで使う描画モデルを選びます。"))
            Divider()
            conditionRow("色カタログ", value: catalogSummary) { showColorCatalogs = true }
            .disabled(model.catalogs.isEmpty)
            .help(tip("次のバッチで使う配色を選びます。"))
            Divider()
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 6) { compactControls }.fixedSize(horizontal: true, vertical: false)
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 8) { sketchControl; wildControl }
                    paperControl
                }
            }
            .controlSize(.small)
            HStack(alignment: .top, spacing: 8) {
                Text(model.display.localized("描画条件はバッチ開始時に固定します。再開には前回の条件を使います。"))
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
                Button(model.display.localized("詳細"), systemImage: "ellipsis") { showDetails = true }
                    .controlSize(.small)
                    .help(tip("言語とシードを確認して変更します。"))
                    .popover(isPresented: $showDetails) { details }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .disabled(disabled)
        .sheet(isPresented: $showModelPicker) {
            BatchModelPickerView(model: model).environment(model.display).disabled(disabled)
        }
        .sheet(isPresented: $showColorCatalogs) {
            ColorCatalogView(model: model, descriptionOnly: true).environment(model.display).disabled(disabled)
        }
        .onChange(of: disabled) { _, busy in
            if busy {
                showModelPicker = false; showColorCatalogs = false
                showSketchPicker = false; showPaperPicker = false; showDetails = false
            }
        }
    }

    private var catalogSummary: String {
        model.catalogMode == "auto"
            ? model.display.localized("記述から自動選択")
            : model.catalogs.first { $0.id == model.catalogID }?.name ?? model.catalogID
    }

    private var modelSummary: String {
        let reference = model.nextBatchDrawingModelReference
        guard let separator = reference.firstIndex(of: ":") else {
            return reference.isEmpty ? model.display.localized("選択してください") : reference
        }
        return String(reference[..<separator]) + " / " + String(reference[reference.index(after: separator)...])
    }

    private func conditionRow(_ key: String, value: String, action: @escaping () -> Void) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(alignment: .center, spacing: 12) {
                Text(model.display.localized(key)).font(.caption).foregroundStyle(.secondary)
                Spacer(minLength: 0)
                Button(model.display.localized("変更"), action: action)
                    .controlSize(.small)
                    .accessibilityLabel(model.display.localizedFormat("%@を変更", model.display.localized(key)))
                    .accessibilityValue(value)
            }
            Text(value).font(.callout).lineLimit(2).truncationMode(.middle).textSelection(.enabled)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder private var compactControls: some View {
        sketchControl
        wildControl
        paperControl
    }

    private var sketchControl: some View {
        Button { showSketchPicker = true } label: {
            Text(model.display.localized("写生") + ": " + model.display.localized(automation.batchSketchMode == "on" ? "あり" : "なし"))
        }
        .help(tip("次の作品で写生を使うかを選びます。"))
        .accessibilityLabel(model.display.localized("写生"))
        .accessibilityValue(model.display.localized(automation.batchSketchMode == "on" ? "あり" : "なし"))
        .popover(isPresented: $showSketchPicker) { sketchPicker }
    }

    private var sketchPicker: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(model.display.localized("写生")).font(.caption).foregroundStyle(.secondary)
            ForEach(["off", "on"], id: \.self) { mode in
                Button {
                    guard !disabled else { return }
                    automation.batchSketchMode = mode
                    showSketchPicker = false
                } label: {
                    HStack(alignment: .top, spacing: 10) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(model.display.localized(mode == "on" ? "あり" : "なし")).font(.callout.weight(.medium))
                            Text(model.display.localized(mode == "on"
                                ? "記述の横に、場所の広がりや季節・時刻の光を補って描く"
                                : "写生を通さず、記述だけで描く"))
                                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
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
            Text(model.display.localized("暴れる") + " " + model.display.localized(model.wild ? "入" : "切"))
                .padding(.horizontal, 8).padding(.vertical, 4)
                .background(model.wild ? Color.accentColor.opacity(0.20) : Color.secondary.opacity(0.06),
                            in: RoundedRectangle(cornerRadius: 4))
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(model.wild ? Color.accentColor : Color.secondary.opacity(0.25)))
        }
        .buttonStyle(.plain)
        .help(tip("次の作品の筆致を規則から外します。"))
        .accessibilityLabel(model.display.localized("暴れる"))
        .accessibilityValue(model.display.localized(model.wild ? "入" : "切"))
    }

    private var paperControl: some View {
        Button { showPaperPicker = true } label: {
            Text(model.display.localized("キャンバス") + ": " + (model.canvases.first { $0.id == model.canvasID }?.label ?? model.canvasID))
                .lineLimit(1)
        }
        .help(tip("用紙の形と意図を見て、次の作品の用紙を選びます。"))
        .popover(isPresented: $showPaperPicker) {
            CreationPaperPicker(model: model) { showPaperPicker = false }.environment(model.display).disabled(disabled)
        }
        .accessibilityValue(model.canvases.first { $0.id == model.canvasID }?.name ?? model.canvasID)
    }

    private var clearControl: some View {
        Button(model.display.localized("新規作成")) {
            guard !disabled else { return }
            automation.restoreBatchInput("")
        }
        .help(tip("バッチの入力欄を空にします。前回の実行記録と保存作品は残ります。"))
    }

    private var details: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(model.display.localized("生成条件の詳細")).font(.headline)
            TextField(model.display.localized("シード（空欄で新規）"), text: $model.seedText).textFieldStyle(.roundedBorder)
                .help(tip("空欄なら次の描画で新しいシードを使います。"))
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
