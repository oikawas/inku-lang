import InkuPersistence
import SwiftUI

@MainActor
struct CreationView: View {
    @Bindable var model: AppModel

    private var recentWorks: [SavedWork] {
        Array(model.works.filter { !$0.trashed && $0.historyVisibility == "normal" }.prefix(24))
    }

    var body: some View {
        GeometryReader { geometry in
            if geometry.size.width >= 850 {
                HStack(alignment: .top, spacing: 0) {
                    ScrollView { input.padding(20) }.frame(width: 340)
                    Divider()
                    workspace.padding(20)
                }
            } else {
                ScrollView {
                    VStack(spacing: 20) {
                        input
                        workspace.frame(minHeight: 460)
                    }
                    .padding(16)
                }
            }
        }
    }

    private var input: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("作品を作る").font(.title2.weight(.semibold))
            Picker("入力", selection: $model.inputMode) {
                Text("記述").tag("description")
                Text("DDL").tag("ddl")
            }
            .pickerStyle(.segmented)
            .disabled(model.isBusy)

            if model.inputMode == "description" {
                editor(text: $model.descriptionText, placeholder: "描きたいものや情景を記述")
            } else {
                editor(text: $model.ddlText, placeholder: "DDLを入力", monospaced: true)
            }

            Picker("言語", selection: $model.language) {
                Text("日本語").tag("ja")
                Text("English").tag("en")
            }
            .disabled(model.isBusy)
            Picker("配色", selection: $model.catalogID) {
                ForEach(model.catalogs, id: \.id) { item in Text(item.name).tag(item.id) }
            }
            .disabled(model.isBusy)
            Picker("用紙", selection: $model.canvasID) {
                ForEach(model.canvases, id: \.id) { item in Text(item.name).tag(item.id) }
            }
            .disabled(model.isBusy)
            TextField("シード（空欄で新規）", text: $model.seedText)
                .textFieldStyle(.roundedBorder)
                .disabled(model.isBusy)
            Toggle("暴れる", isOn: $model.wild).disabled(model.isBusy)

            if model.inputMode == "description" && model.providerModel.isEmpty {
                Label("記述から生成するには、設定で接続先とモデルを指定してください。", systemImage: "info.circle")
                    .font(.callout).foregroundStyle(.secondary)
            }
            if model.isBusy {
                Button("停止", systemImage: "stop.fill") { Task { await model.cancel() } }
                    .frame(maxWidth: .infinity)
            } else {
                Button("生成", systemImage: "play.fill") { Task { await model.generate() } }
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
                Text(placeholder).foregroundStyle(.tertiary).padding(12).allowsHitTesting(false)
            }
        }
        .frame(minHeight: 220, maxHeight: 300)
        .background(.background, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
        .accessibilityLabel(monospaced ? "DDL" : "記述")
    }

    private var workspace: some View {
        VStack(alignment: .leading, spacing: 16) {
            ArtworkCanvas(
                svg: model.currentSVG, renderer: model.renderer,
                caption: model.selectedWork?.effectiveSourceText ?? ""
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            DisclosureGroup("DDL・Score") {
                OutputView(ddl: model.visibleDDL, score: model.scoreJSON)
                    .frame(height: 180)
            }
            if !recentWorks.isEmpty {
                Text("最近の作品").font(.headline)
                ScrollView(.horizontal) {
                    LazyHStack(spacing: 12) {
                        ForEach(recentWorks, id: \.id) { work in
                            let title = work.effectiveSourceText.isEmpty ? "無題" : work.effectiveSourceText
                            Button {
                                Task { await model.selectWork(work) }
                            } label: {
                                VStack(alignment: .leading, spacing: 5) {
                                    ArtworkThumbnail(work: work, renderer: model.renderer)
                                        .frame(width: 100, height: 82)
                                    Text(title).lineLimit(1).frame(width: 100, alignment: .leading)
                                }
                                .font(.caption)
                            }
                            .buttonStyle(.plain)
                            .disabled(model.isBusy)
                            .accessibilityLabel("作品を開く: \(title)")
                        }
                    }
                }
            }
        }
    }
}

struct OutputView: View {
    let ddl: String
    let score: String
    @State private var tab = "ddl"

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Picker("出力", selection: $tab) {
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
