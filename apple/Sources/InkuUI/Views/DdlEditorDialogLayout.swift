import InkuHost
import InkuPersistence
import SwiftUI

/// DdlEditorDialog.svelte: a fixed target preview beside the editor, with all drawing controls below it.
@MainActor
struct DdlEditorDialogLayout<Footer: View>: View {
    @Bindable var model: AppModel
    let title: String
    let subtitle: String
    let work: SavedWork?
    @Binding var text: String
    @Binding var insertion: InkuEditorInsertion?
    let disabled: Bool
    let onClose: () -> Void
    let onRangeBlocked: (Bool) -> Void
    @ViewBuilder let footer: () -> Footer
    @State private var preview: CompositionRanges.Preview?

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .top, spacing: 16) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(title).inkuFont(16, weight: .medium)
                    Text(subtitle).inkuFont(12).foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
                Button(action: onClose) { Image(systemName: "xmark").frame(width: 26, height: 26) }
                    .buttonStyle(InkuGhostButtonStyle())
                    .accessibilityLabel(model.display.localized("閉じる")).disabled(disabled)
            }.padding(.horizontal, 18).padding(.vertical, 14)
            Divider()
            GeometryReader { geometry in
                if geometry.size.width > 760 {
                    HStack(alignment: .top, spacing: 16) {
                        editor
                        artworkPreview(compact: false).frame(width: min(210, geometry.size.width * 0.24))
                    }
                } else {
                    VStack(alignment: .leading, spacing: 8) {
                        editor
                        artworkPreview(compact: true).frame(height: 80)
                    }
                }
            }.padding(.horizontal, 18).padding(.vertical, 14)
            Divider()
            footer().padding(.horizontal, 18).padding(.top, 10).padding(.bottom, 14)
        }
        .background(InkuColor.panel)
        #if os(macOS)
        .frame(minWidth: 620, idealWidth: 1360, minHeight: 480, idealHeight: 940)
        #endif
    }

    private var editor: some View {
        DdlEditorPane(model: model, text: $text, disabled: disabled, insertion: $insertion,
            onRangeBlocked: onRangeBlocked, onRangePreview: { preview = $0 })
    }

    private func artworkPreview(compact: Bool) -> some View {
        GeometryReader { geometry in
            Group {
                if compact {
                    HStack(alignment: .top, spacing: 10) { previewImage(width: min(100, geometry.size.width * 0.25), height: 72); previewHint }
                } else {
                    VStack(alignment: .leading, spacing: 8) { previewImage(width: geometry.size.width, height: 150); previewHint }
                }
            }.inkuFont(12).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .topLeading)
        }
    }

    private var previewHint: some View {
        Text(model.display.webCopy("ddlEditorRangeHint", "下線の名前を押すか、カーソルを入れると数を編集できます。範囲から離れると名前が数に合わせて変わります。"))
    }

    @ViewBuilder private func previewImage(width: CGFloat, height: CGFloat) -> some View {
        if let work {
            let ratio = work.renderCanvasAspectRatio ?? 1
            let imageWidth = min(width, height * ratio)
            let imageHeight = imageWidth / ratio
            ArtworkThumbnail(work: work, thumbnails: model.thumbnails)
                .frame(width: imageWidth, height: imageHeight)
                .overlay {
                    if let preview, preview.bounds.count == 4 {
                        let bounds = preview.bounds
                        Rectangle().stroke(Color.accentColor, style: StrokeStyle(lineWidth: 2, dash: preview.invalid ? [2, 3] : [6, 4]))
                            .frame(width: imageWidth * (bounds[2] - bounds[0]), height: imageHeight * (bounds[3] - bounds[1]))
                            .position(x: imageWidth * (bounds[0] + bounds[2]) / 2, y: imageHeight * (bounds[1] + bounds[3]) / 2)
                            .allowsHitTesting(false)
                    }
                }
                .accessibilityLabel(model.display.webCopy("ddlEditorArtwork", "編集する作品"))
        } else {
            Text(model.display.webCopy("ddlEditorNoArtwork", "描画後に作品が表示されます"))
        }
    }
}

@MainActor
struct DdlDrawingModelCard: View {
    @Bindable var model: AppModel
    let reference: String
    let providers: [ProviderSettings]
    let onSelect: () -> Void

    var body: some View {
        let naming = ModelNaming(providers: providers)
        VStack(alignment: .leading, spacing: 5) {
            Text(model.display.webCopy("ddlDialogDrawingModel", "描画モデル")).inkuFont(12).foregroundStyle(.secondary)
            Button(action: onSelect) {
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(reference.isEmpty ? model.display.localized("描画モデルを選択") : naming.modelShortName(reference)).inkuFont(13)
                        if !reference.isEmpty {
                            Text(naming.providerLabel(naming.resolve(reference).provider)).inkuFont(11).foregroundStyle(.secondary)
                        }
                    }
                    Spacer(minLength: 8)
                    Text(model.display.webCopy("modelSelectButton", "モデル選択")).inkuFont(11).foregroundStyle(.secondary)
                }.padding(9).frame(minWidth: 160, maxWidth: .infinity, alignment: .leading)
                    .background(InkuColor.bg2).overlay(RoundedRectangle(cornerRadius: 4).stroke(InkuColor.border2))
            }.buttonStyle(.plain).accessibilityLabel(model.display.webCopy("ddlDialogDrawingModel", "描画モデル") + ": " + reference)
        }.frame(maxWidth: 520, alignment: .leading)
    }
}

@MainActor
struct DdlDialogFooter<Conditions: View, Actions: View>: View {
    @ViewBuilder let conditions: () -> Conditions
    @ViewBuilder let actions: () -> Actions

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .bottom, spacing: 18) {
                conditions().frame(minWidth: 240, maxWidth: .infinity, alignment: .leading)
                actions().fixedSize(horizontal: true, vertical: false)
            }
            VStack(alignment: .leading, spacing: 10) {
                conditions().frame(maxWidth: .infinity, alignment: .leading)
                actions().frame(maxWidth: .infinity, alignment: .trailing)
            }
        }
    }
}
