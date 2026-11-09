import SwiftUI
import InkuHost

@MainActor struct DrawDefaultsSettingsView: View {
    @Bindable var model: AppModel
    @State private var draft: [String: DrawOptions] = [:]
    @State private var pickerTab: String?
    @State private var saved = false
    @State private var failed = false
    @State private var providers: [ProviderSettings] = []
    @State private var loaded = false
    @Environment(\.inkuPhoneLayout) private var phone
    private let tabs = ["describe", "image", "batch_text", "batch_image"]
    static func optionKeys(tab: String) -> [String] {
        let image = tab == "image" || tab == "batch_image"
        return DrawOptionsCore.keys.filter { !image || !["route", "sketch", "composition", "wild"].contains($0) }
    }
    private func imageTab(_ tab: String) -> Bool { tab == "image" || tab == "batch_image" }
    private func copy(_ key: String, _ fallback: String) -> String { model.display.webCopy(key, fallback) }
    private func binding<T>(_ tab: String, _ path: WritableKeyPath<DrawOptions, T>) -> Binding<T> {
        Binding(get: { options(tab)[keyPath: path] }, set: { value in
            if draft[tab] == nil { draft[tab] = options(tab) }
            draft[tab]?[keyPath: path] = value; saved = false
        })
    }
    private func options(_ tab: String) -> DrawOptions {
        draft[tab] ?? model.drawDefaults[tab] ?? DrawOptionsCore.release[tab] ?? .empty
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
        Group {
            if phone { phoneBody } else { wideBody }
        }
        // The unsaved edits are read once. On an iPhone the catalog and canvas lists are pages pushed over this one,
        // and coming back appears again; reading the saved defaults then threw the other edits away (author 2026-11-09).
        .onAppear { if !loaded { draft = model.drawDefaults; loaded = true } }
        .task(id: model.providerSettingsRevision) { providers = await model.hostSettings().providers }
        .sheet(isPresented: Binding(get: { pickerTab != nil }, set: { if !$0 { pickerTab = nil } })) {
            if let tab = pickerTab {
                BatchModelPickerView(model: model, initialReference: imageTab(tab) ? options(tab).models.vision : options(tab).models.stage1,
                    immediateSelection: true, purpose: imageTab(tab) ? "vision" : "llm", onSelection: { reference in
                        // A tab without an unsaved edit yet starts from what is shown, as the other controls do;
                        // before, the choice fell on nothing and was lost.
                        if draft[tab] == nil { draft[tab] = options(tab) }
                        if imageTab(tab) { draft[tab]?.models.vision = reference }
                        else { draft[tab]?.models.stage1 = reference; draft[tab]?.models.stage2 = reference }
                        saved = false
                    })
            }
        }
    }

    /// iPhone (ios-app step 7d, the author's request): one control per row, each in the form a choice of its kind
    /// takes on iOS — a switch for on and off, a segmented control for the two ways of drawing, a list page for
    /// the catalogs and the canvases, and a row that opens the model choice. One tab is one section.
    @ViewBuilder private var phoneBody: some View {
        ForEach(tabs, id: \.self) { tab in
            Section {
                if Self.optionKeys(tab: tab).contains("route") {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(copy("drawDefaultsRoute", "描き方"))
                        Picker(copy("drawDefaultsRoute", "描き方"), selection: binding(tab, \.route)) {
                            Text(copy("drawDefaultsRead", "言葉で描く")).tag("read_and_draw")
                            Text(copy("drawDefaultsStages", "型で描く")).tag("stages")
                        }.pickerStyle(.segmented).labelsHidden()
                    }
                    Toggle(copy("sketchLabel", "写生"), isOn: switchBinding(tab, \.sketch))
                    Toggle(copy("drawDefaultsComposition", "構図・法則・配色"), isOn: switchBinding(tab, \.composition))
                    Toggle(copy("wildButton", "筆致制限を外す"), isOn: switchBinding(tab, \.wild))
                }
                catalogPicker(tab).inkuListPickerStyle()
                canvasPicker(tab).inkuListPickerStyle()
                Button { pickerTab = tab } label: {
                    HStack {
                        Text(imageTab(tab) ? copy("drawDefaultsVision", "画像を読むモデル") : copy("drawDefaultsModel", "描画モデル"))
                            .foregroundStyle(.primary)
                        Spacer()
                        Text(modelName(shownModel(tab)))
                            .foregroundStyle(.secondary).lineLimit(1)
                        Image(systemName: "chevron.right").inkuFont(12).foregroundStyle(.tertiary)
                    }.contentShape(Rectangle())
                }.buttonStyle(.plain)
            } header: {
                Text(tabTitle(tab))
            } footer: {
                Text(hint(tab))
            }
        }
        Section {
            saveButton
            if saved { Text(copy("drawDefaultsSaved", "保存しました。左の欄には、次に「新規作成」を押したときに出ます。")) }
            if failed { Text(copy("drawDefaultsSaveFailed", "デフォルトを保存できませんでした。")).foregroundStyle(.red) }
        }
    }

    private var saveButton: some View {
        Button(copy("drawDefaultsSave", "デフォルトを保存")) {
            do { try model.saveDrawDefaults(draft); saved = true; failed = false }
            catch { failed = true; saved = false }
        }
    }

    private func switchBinding(_ tab: String, _ path: WritableKeyPath<DrawOptions, String>) -> Binding<Bool> {
        let value = binding(tab, path)
        return Binding(get: { value.wrappedValue == "on" }, set: { value.wrappedValue = $0 ? "on" : "off" })
    }

    private func catalogPicker(_ tab: String) -> some View {
        Picker(copy("colorCatalogButton", "色カタログ"), selection: Binding(get: {
            let catalog = options(tab).catalog
            return catalog.mode == "auto" ? "auto" : catalog.id
        }, set: { value in
            if draft[tab] == nil { draft[tab] = options(tab) }
            draft[tab]?.catalog.mode = value == "auto" ? "auto" : "fixed"
            if value != "auto" { draft[tab]?.catalog.id = value }
            saved = false
        })) {
            Text(copy("colorCatalogAuto", "記述から自動選択")).tag("auto")
            ForEach(model.catalogs) { Text($0.name).tag($0.id) }
        }
    }

    private func canvasPicker(_ tab: String) -> some View {
        Picker(copy("drawDefaultsCanvas", "キャンバス"), selection: binding(tab, \.canvasAspect)) {
            if imageTab(tab) { Text(copy("imageCanvasAspect", "画像に合わせる")).tag("image") }
            ForEach(model.canvases) { Text($0.name).tag($0.id) }
        }
    }

    private var wideBody: some View {
        Section {
            ForEach(tabs, id: \.self) { tab in
                VStack(alignment: .leading, spacing: 8) {
                    Text(tabTitle(tab)).inkuFont(14, weight: .semibold)
                    Text(hint(tab)).inkuFont(12).foregroundStyle(.secondary)
                    if Self.optionKeys(tab: tab).contains("route") {
                        Picker(copy("drawDefaultsRoute", "描き方"), selection: binding(tab, \.route)) {
                            Text(copy("drawDefaultsRead", "言葉で描く")).tag("read_and_draw")
                            Text(copy("drawDefaultsStages", "型で描く")).tag("stages")
                        }
                        togglePicker(copy("sketchLabel", "写生"), tab: tab, path: \.sketch)
                        togglePicker(copy("drawDefaultsComposition", "構図・法則・配色"), tab: tab, path: \.composition)
                        togglePicker(copy("wildButton", "筆致制限を外す"), tab: tab, path: \.wild)
                    }
                    Picker(copy("colorCatalogButton", "色カタログ"), selection: Binding(get: {
                        let catalog = options(tab).catalog
                        return catalog.mode == "auto" ? "auto" : catalog.id
                    }, set: { value in
                        if draft[tab] == nil { draft[tab] = options(tab) }
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
                        Text(modelName(shownModel(tab)))
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
    }
    /// The model the tab draws with: its unsaved edit, or else the saved or release default the other rows show.
    private func shownModel(_ tab: String) -> String {
        let models = options(tab).models
        return (imageTab(tab) ? models.vision : models.stage1) ?? ""
    }

    private func modelName(_ reference: String) -> String {
        ModelNaming(providers: providers, stageProvider: model.stageDefaultProviderID).displayName(reference)
    }
    private func togglePicker(_ title: String, tab: String, path: WritableKeyPath<DrawOptions, String>) -> some View {
        Picker(title, selection: binding(tab, path)) {
            Text(copy("drawDefaultsOff", "オフ")).tag("off")
            Text(copy("drawDefaultsOn", "オン")).tag("on")
        }
    }
}
