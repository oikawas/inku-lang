import InkuHost
import InkuPersistence
import SwiftUI

/// One description's works, in the core form order; inherited records keep their own marker.
@MainActor
struct DescriptionLibraryGroup: View {
    @Bindable var model: AppModel
    let group: LibraryGroup
    let members: [InkuPersistence.LibraryItem]
    let records: [String: CompositionRecordSnapshot]
    let onOpen: (SavedWork) -> Void
    let onPreview: (SavedWork) -> Void
    var selecting = false
    private var language: String { model.display.preferences.language }
    private var forms: [String] { CompositionNames.formIDs + [""] }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(group.representative.work.effectiveSourceText).inkuFont(13, weight: .semibold).lineLimit(2)
            ScrollView(.horizontal) {
                HStack(alignment: .top, spacing: 10) {
                    ForEach(forms, id: \.self) { form in
                        let items = members.filter { formID($0.work) == form }
                        if !items.isEmpty {
                            VStack(alignment: .leading, spacing: 6) {
                                Text(form.isEmpty ? model.display.webCopy("historyDescriptionNoRecord", "構図の記録なし") : CompositionNames.formName(form, language: language))
                                    .inkuFont(11, weight: .semibold).foregroundStyle(.secondary)
                                ForEach(items) { item in
                                    Button { onPreview(item.work) } label: {
                                        VStack(alignment: .leading, spacing: 4) {
                                            ArtworkThumbnail(work: item.work, thumbnails: model.thumbnails)
                                                .aspectRatio(item.work.renderCanvasAspectRatio ?? 1, contentMode: .fit)
                                                .frame(width: 110, height: 110)
                                                .overlay(alignment: .topTrailing) {
                                                    if selecting {
                                                        Image(systemName: model.library.selectedIDs.contains(item.id) ? "checkmark.circle.fill" : "circle")
                                                            .padding(5).background(.thinMaterial, in: Circle())
                                                    }
                                                }
                                            if let record = records[item.id], record.own == nil, record.inherited != nil {
                                                Text(childLabel(record.derivationKind)).inkuFont(10).foregroundStyle(.secondary)
                                            }
                                        }
                                    }.buttonStyle(.plain).onTapGesture(count: 2) { onOpen(item.work) }.id(item.id)
                                }
                            }.frame(width: 120, alignment: .topLeading)
                        }
                    }
                }
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    private func formID(_ work: SavedWork) -> String {
        guard let record = records[work.id], let form = (record.own ?? record.inherited)?["answer"]["form"].string,
              CompositionNames.formIDs.contains(form) else { return "" }
        return form
    }

    private func childLabel(_ kind: String?) -> String {
        let name: String
        switch kind {
        case "tool_change": name = model.display.label("てざわり", "Tool")
        case "ground_change": name = model.display.label("支持体", "Ground")
        case "catalog_change": name = model.display.label("色カタログ", "Catalog")
        case "color_arrangement_change": name = model.display.label("配色", "Colors")
        case "canvas_fit": name = model.display.label("紙にはめ込む", "Fit canvas")
        case "replay": name = model.display.label("再描画", "Replay")
        case "layout_change": name = model.display.label("配置", "Layout")
        default: name = kind ?? ""
        }
        return model.display.webCopyFormat("historyDescriptionChildOf", "%@の子", name)
    }
}
