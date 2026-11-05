import SwiftUI

@MainActor struct DrawDefaultsSettingsView: View {
    @Bindable var model: AppModel
    @State private var draft: [String: DrawOptions] = [:]
    @State private var pickerTab: String?
    @State private var saved = false
    @State private var failed = false
    private let tabs = ["describe", "image", "batch_text", "batch_image"]
    private func imageTab(_ tab: String) -> Bool { tab == "image" || tab == "batch_image" }
    private func copy(_ key: String, _ fallback: String) -> String { model.display.webCopy(key, fallback) }
    private func binding<T>(_ tab: String, _ path: WritableKeyPath<DrawOptions, T>) -> Binding<T> {
        Binding(get: { (draft[tab] ?? model.drawDefaults[tab]!)[keyPath: path] }, set: { value in
            if draft[tab] == nil { draft[tab] = model.drawDefaults[tab] }
            draft[tab]?[keyPath: path] = value; saved = false
        })
    }
    private func tabTitle(_ tab: String) -> String {
        switch tab {
        case "describe": copy("drawDefaultsDescribe", "記述")
        case "image": copy("drawDefaultsImage", "画像")
        case "batch_text": copy("drawDefaultsBatchText", "記述のバッチ")
        default: copy("drawDefaultsBatchImage", "画像フォルダ")
        }
    }
    private func hint(_ tab: String) -> String {
        switch tab {
        case "describe": copy("drawDefaultsHintDescribe", "「記述」タブで 1 作品を描くとき。")
        case "image": copy("drawDefaultsHintImage", "「画像」タブで 1 枚の画像から描くとき。")
        case "batch_text": copy("drawDefaultsHintBatchText", "「バッチ」タブで記述を 1 行ずつ描くとき。")
        default: copy("drawDefaultsHintBatchImage", "「バッチ」タブで画像フォルダの画像を順に描くとき。")
        }
    }
    var body: some View {
        Section {
            Text(copy("drawDefaultsHint", "新規作成で使う条件をタブごとに設定します。"))
                .foregroundStyle(.secondary)
            ForEach(tabs, id: \.self) { tab in
                VStack(alignment: .leading, spacing: 8) {
                    Text(tabTitle(tab)).inkuFont(14, weight: .semibold)
                    Text(hint(tab)).inkuFont(12).foregroundStyle(.secondary)
                    if !imageTab(tab) {
                        Picker(copy("drawDefaultsRoute", "描き方"), selection: binding(tab, \.route)) {
                            Text(copy("drawDefaultsRead", "言葉で描く")).tag("read_and_draw")
                            Text(copy("drawDefaultsStages", "型で描く")).tag("stages")
                        }
                        togglePicker(copy("sketchLabel", "写生"), tab: tab, path: \.sketch)
                        togglePicker(copy("drawDefaultsComposition", "構図・法則・配色"), tab: tab, path: \.composition)
                        togglePicker(copy("wildButton", "筆致制限を外す"), tab: tab, path: \.wild)
                    }
                    Picker(copy("colorCatalogButton", "色カタログ"), selection: Binding(get: {
                        let catalog = (draft[tab] ?? model.drawDefaults[tab]!).catalog
                        return catalog.mode == "auto" ? "auto" : catalog.id
                    }, set: { value in
                        if draft[tab] == nil { draft[tab] = model.drawDefaults[tab] }
                        draft[tab]?.catalog.mode = value == "auto" ? "auto" : "fixed"
                        if value != "auto" { draft[tab]?.catalog.id = value }
                        saved = false
                    })) {
                        Text(copy("colorCatalogAuto", "記述から自動選択")).tag("auto")
                        ForEach(model.catalogs) { Text($0.name).tag($0.id) }
                    }
                    Picker(copy("drawDefaultsCanvas", "キャンバス"), selection: binding(tab, \.canvasAspect)) {
                        if imageTab(tab) { Text(copy("imageCanvasAspect", "画像に合わせる")).tag("image") }
                        ForEach(model.canvases) { Text($0.name).tag($0.id) }
                    }
                    HStack {
                        Text(imageTab(tab) ? copy("drawDefaultsVision", "画像を読むモデル") : copy("drawDefaultsModel", "描画モデル"))
                        Spacer()
                        Text((imageTab(tab) ? draft[tab]?.models.vision : draft[tab]?.models.stage1) ?? "")
                            .foregroundStyle(.secondary)
                        Button(copy("editButton", "変更")) { pickerTab = tab }
                    }
                }.padding(.vertical, 8)
            }
            Button(copy("drawDefaultsSave", "デフォルトを保存")) {
                do { try model.saveDrawDefaults(draft); saved = true; failed = false }
                catch { failed = true; saved = false }
            }
            if saved { Text(copy("drawDefaultsSaved", "保存しました。左の欄には、次に「新規作成」を押したときに出ます。")) }
            if failed { Text(copy("drawDefaultsSaveFailed", "デフォルトを保存できませんでした。")).foregroundStyle(.red) }
        }
        .onAppear { draft = model.drawDefaults }
        .sheet(isPresented: Binding(get: { pickerTab != nil }, set: { if !$0 { pickerTab = nil } })) {
            if let tab = pickerTab {
                BatchModelPickerView(model: model, initialReference: imageTab(tab) ? draft[tab]?.models.vision : draft[tab]?.models.stage1,
                    immediateSelection: true, purpose: imageTab(tab) ? "vision" : "llm", onSelection: { reference in
                        if imageTab(tab) { draft[tab]?.models.vision = reference }
                        else { draft[tab]?.models.stage1 = reference; draft[tab]?.models.stage2 = reference }
                        saved = false
                    })
            }
        }
    }
    private func togglePicker(_ title: String, tab: String, path: WritableKeyPath<DrawOptions, String>) -> some View {
        Picker(title, selection: binding(tab, path)) {
            Text(copy("drawDefaultsOff", "オフ")).tag("off")
            Text(copy("drawDefaultsOn", "オン")).tag("on")
        }
    }
}
