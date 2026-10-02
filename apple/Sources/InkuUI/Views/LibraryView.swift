import InkuPersistence
import SwiftUI

@MainActor
struct LibraryView: View {
    @Bindable var model: AppModel
    @State private var query = ""

    private var visibleWorks: [SavedWork] {
        model.works.filter { work in
            !work.trashed && work.historyVisibility == "normal"
                && (query.isEmpty || work.effectiveSourceText.localizedCaseInsensitiveContains(query)
                || (work.ddl ?? "").localizedCaseInsensitiveContains(query)
                || (work.renderColorCatalogName ?? "").localizedCaseInsensitiveContains(query))
        }
    }

    var body: some View {
        GeometryReader { geometry in
            if geometry.size.width >= 850 {
                HStack(spacing: 0) {
                    list.frame(width: 310)
                    Divider()
                    selected.padding(20)
                }
            } else {
                VStack(spacing: 0) {
                    list.frame(maxHeight: 240)
                    Divider()
                    selected.padding(16)
                }
            }
        }
        .searchable(text: $query, prompt: "作品を検索")
    }

    private var list: some View {
        List {
            if visibleWorks.isEmpty {
                ContentUnavailableView(
                    query.isEmpty ? "保存作品がありません" : "一致する作品がありません",
                    systemImage: "square.grid.2x2",
                    description: Text(query.isEmpty ? "生成した作品はここに保存されます。" : "検索語を変えてください。")
                )
            }
            ForEach(visibleWorks, id: \.id) { work in
                Button {
                    Task { await model.selectWork(work) }
                } label: {
                    HStack(spacing: 12) {
                        ArtworkThumbnail(work: work, renderer: model.renderer)
                            .frame(width: 68, height: 64)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(work.effectiveSourceText.isEmpty ? "無題" : work.effectiveSourceText)
                                .lineLimit(2).foregroundStyle(.primary)
                            Text(Date(timeIntervalSince1970: Double(work.at) / 1000), format: .dateTime.month().day().hour().minute())
                                .font(.caption).foregroundStyle(.secondary)
                            if let name = work.renderColorCatalogName {
                                Text(name).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                            }
                        }
                        if work.starred { Image(systemName: "star.fill").accessibilityLabel("お気に入り") }
                    }
                    .padding(.vertical, 4)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(model.isBusy)
                .listRowBackground(model.selectedWorkID == work.id ? Color.accentColor.opacity(0.12) : Color.clear)
            }
        }
        .listStyle(.inset)
    }

    @ViewBuilder
    private var selected: some View {
        if let work = model.selectedWork {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("保存作品").font(.title2.weight(.semibold))
                        Text(Date(timeIntervalSince1970: Double(work.at) / 1000), format: .dateTime)
                            .font(.callout).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("再演奏", systemImage: "arrow.clockwise") { Task { await model.replay(work) } }
                        .disabled(model.isBusy)
                }
                ArtworkCanvas(svg: model.currentSVG, renderer: model.renderer, caption: work.effectiveSourceText)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                DisclosureGroup("DDL・Score") {
                    OutputView(ddl: work.ddl ?? "", score: work.score).frame(height: 180)
                }
                HStack(spacing: 16) {
                    if let format = work.renderCanvasAspectID { Text("用紙: \(format)") }
                    if let seed = work.renderSeed { Text("シード: \(seed)") }
                }
                .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
            }
        } else {
            ContentUnavailableView("作品を選択", systemImage: "photo", description: Text("一覧から保存作品を選択してください。"))
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }
}
