import SwiftUI

@MainActor
struct BatchConditionsView: View {
    @Bindable var model: AppModel
    @Bindable var automation: AutomationModel
    @State private var showModelPicker = false
    @State private var showColorCatalogs = false
    @State private var showPaperPicker = false
    @State private var showDetails = false

    private var disabled: Bool { automation.isOccupied || model.isBusy }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .center, spacing: 12) {
                Text(model.display.localized("次のバッチの描画条件"))
                    .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                Spacer(minLength: 0)
                Picker(model.display.localized("入力"), selection: inputMode) {
                    Text(model.display.localized("記述")).tag("description")
                    Text("DDL").tag("ddl")
                }
                .pickerStyle(.segmented).labelsHidden().frame(width: 120)
                .help(tip("各行を記述として解釈するか、DDLとして描くかを選びます。"))
            }
            conditionRow("モデル", value: modelSummary) { showModelPicker = true }
            .help(tip("次のバッチで使う描画モデルを選びます。"))
            .popover(isPresented: $showModelPicker) {
                CreationModelPicker(model: model)
                    .padding(16).frame(width: 380).environment(model.display).disabled(disabled)
            }
            Divider()
            conditionRow("色カタログ", value: catalogSummary) { showColorCatalogs = true }
            .disabled(model.catalogs.isEmpty)
            .help(tip("次のバッチで使う配色を選びます。"))
            Divider()
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 6) { compactControls }.fixedSize(horizontal: true, vertical: false)
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 8) { sketchControl; wildControl }
                    HStack(spacing: 8) { paperControl; clearControl }
                }
            }
            .controlSize(.small)
            HStack(alignment: .top, spacing: 8) {
                Text(model.display.localized("描画条件はバッチ開始時に固定します。再開には前回の条件を使います。"))
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
                Button(model.display.localized("詳細"), systemImage: "ellipsis") { showDetails = true }
                    .controlSize(.small)
                    .help(tip("言語・シード・指定する写生を確認して変更します。"))
                    .popover(isPresented: $showDetails) { details }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .disabled(disabled)
        .sheet(isPresented: $showColorCatalogs) {
            ColorCatalogView(model: model).environment(model.display).disabled(disabled)
        }
        .onChange(of: disabled) { _, busy in
            if busy {
                showModelPicker = false; showColorCatalogs = false
                showPaperPicker = false; showDetails = false
            }
        }
    }

    private var inputMode: Binding<String> {
        Binding(get: { model.inputMode }, set: { mode in
            guard !disabled else { return }
            model.inputMode = mode
            if mode == "ddl", model.catalogMode == "auto" { model.catalogMode = "fixed" }
        })
    }

    private var catalogSummary: String {
        model.catalogMode == "fixed"
            ? model.catalogs.first { $0.id == model.catalogID }?.name ?? model.catalogID
            : model.display.localized(model.catalogMode == "random" ? "ランダム" : "記述から自動選択")
    }

    private var modelSummary: String {
        let reference = model.nextDrawingModelReference
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
        clearControl
    }

    @ViewBuilder private var sketchControl: some View {
        if model.inputMode == "description" {
            Menu {
                Button(model.display.localized("使わない")) { if !disabled { model.sketchMode = "off" } }
                Button(model.display.localized("生成する")) { if !disabled { model.sketchMode = "on" } }
                Button(model.display.localized("指定する")) {
                    guard !disabled else { return }
                    model.sketchMode = "supplied"; showDetails = true
                }
            } label: {
                Text(model.display.localized("写生") + ": " + model.display.localized(
                    model.sketchMode == "on" ? "オン" : model.sketchMode == "supplied" ? "指定" : "オフ"))
            }
            .help(tip("次の作品で写生を使うかを選びます。"))
        }
    }

    private var wildControl: some View {
        Button(model.display.localized("暴れる") + ": " + model.display.localized(model.wild ? "オン" : "オフ")) {
            guard !disabled else { return }
            model.wild.toggle()
        }
        .help(tip("次の作品の筆致を規則から外します。"))
        .accessibilityValue(model.display.localized(model.wild ? "オン" : "オフ"))
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
            Picker(model.display.localized("言語"), selection: $model.language) {
                Text(model.display.localized("日本語")).tag("ja")
                Text("English").tag("en")
            }
            .help(tip("次の作品の指示書に使う言語を選びます。"))
            TextField(model.display.localized("シード（空欄で新規）"), text: $model.seedText).textFieldStyle(.roundedBorder)
                .help(tip("空欄なら次の描画で新しいシードを使います。"))
            if model.inputMode == "description", model.sketchMode == "supplied" {
                Text(model.display.localized("場所と光を補う写生")).font(.caption).foregroundStyle(.secondary)
                TextEditor(text: $model.sketchText).frame(height: 110)
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(.quaternary))
                    .accessibilityLabel(model.display.localized("場所と光を補う写生"))
            }
        }
        .padding(16).frame(width: 340).disabled(disabled)
    }

    private func tip(_ key: String) -> String {
        model.display.preferences.showTooltips ? model.display.localized(key) : ""
    }
}
