import InkuPersistence
import SwiftUI

/// HistoryManager.svelte's preview, separate from the lineage's saved-information sheet.
@MainActor
struct LibraryPreviewPanel: View {
    @Bindable var model: AppModel
    @Bindable var preview: LibraryPreviewModel
    @Bindable var comment: LibraryNoteEditorModel
    let work: SavedWork
    let naming: ModelNaming
    let onOpen: (SavedWork) -> Void
    let onLineage: (SavedWork) -> Void
    let onWorkAction: (SavedWork, String) -> Void
    var writingLocked = false
    var storedSVGBytes: Int64? = nil
    @State private var generation: Int?
    private var display: DisplaySettings { model.display }
    private var disabled: Bool { model.isBrowsingLocked || work.trashed }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ArtworkThumbnail(work: work, thumbnails: model.thumbnails)
                .frame(maxWidth: .infinity).frame(height: 236)
                .background(LibraryChrome.panel2, in: RoundedRectangle(cornerRadius: 4))
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(LibraryChrome.border))
                .contentShape(Rectangle()).onTapGesture(count: 2) { open() }
                .focusable().onKeyPress(.return) { open(); return .handled }
                .accessibilityElement(children: .ignore).accessibilityAddTraits(.isButton)
                .accessibilityLabel(display.webCopy("historyPreviewOpenArtwork", "作品で開く"))
                .accessibilityAction { open() }
                .inkuTooltip(display.tooltip("ダブルクリックで作品を開く", serverKey: "historyPreviewOpenHint"))
            Text(display.webCopy("historyPreviewOpenHint", "ダブルクリックで作品を開く"))
                .inkuFont(10).foregroundStyle(.tertiary).frame(maxWidth: .infinity, alignment: .trailing)
            Text(work.effectiveSourceText).inkuFont(14).lineSpacing(6).textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
            WrappingHStack(spacing: 6) {
                Button(display.webCopy("historyPreviewOpenLineage", "系譜で開く")) { onLineage(work) }
                    .disabled(disabled || work.lineageNodeID == nil)
                    .buttonStyle(LibraryGhostButtonStyle())
                Menu {
                    SavedWorkRefinementActions(model: model, work: work, onAction: onWorkAction, writingLocked: writingLocked)
                } label: { menuLabel(display.webCopy("historyPreviewRefine", "推敲する")) }
                .menuStyle(.borderlessButton).fixedSize().disabled(disabled || writingLocked)
                exportMenu
            }
            VStack(alignment: .leading, spacing: 0) {
                Text(display.webCopy("historyPreviewDetails", "作品情報")).inkuFont(12, weight: .semibold).padding(.bottom, 8)
                fact(display.webCopy("historyCreatedAtHeader", "作成日時"),
                     Date(timeIntervalSince1970: Double(work.at) / 1000).formatted(date: .numeric, time: .shortened))
                ForEach(Array(naming.cardLines(stage1: work.stage1Model, stage2: work.stage2Model).enumerated()), id: \.offset) { _, line in
                    fact(line.role == nil ? display.webCopy("historyModelHeader", "モデル")
                         : display.localized(line.role == .interpretation ? "解釈モデル" : "描画モデル"), line.full ?? display.localized("未記録"))
                }
                fact(display.webCopy("historyCatalogHeader", "色カタログ"), work.renderColorCatalogName
                     ?? model.catalogs.first { $0.id == work.catalogID }?.name ?? work.catalogID ?? display.localized("未記録"))
                if let canvas = work.renderCanvasAspectID ?? work.renderCanvasAspect {
                    fact(display.webCopy("historyCanvasHeader", "キャンバス"), model.canvases.first { $0.id == canvas }?.label ?? canvas)
                }
                if let elapsed = work.elapsedMS { fact(display.webCopy("historySecondsHeader", "秒数"), String(format: "%.1f s", Double(elapsed) / 1000)) }
                fact(display.webCopy("historySvgSizeHeader", "SVGサイズ"), byteSize)
                fact(display.webCopy("historyPreviewRenderVersion", "描画版"), work.renderEngineVersion ?? display.webCopy("historyVersionNotRecorded", "記録なし"))
                if let generation { fact(display.webCopy("historyStripFieldGeneration", "世代"), String(generation)) }
                if let hash = work.renderHash {
                    factRow(display.webCopy("historyHashHeader", "ハッシュ")) {
                        HStack(spacing: 8) {
                            Text("#" + hash.suffix(4).uppercased()).textSelection(.enabled)
                            Button { model.library.copyHash(hash) } label: { Image(systemName: "doc.on.doc").frame(width: 22, height: 22) }
                                .buttonStyle(.plain)
                                .accessibilityLabel(display.webCopy("historyHashCopyTitle", "描画ハッシュ全体をコピー"))
                                .inkuTooltip(model.library.copiedHash == hash ? display.webCopy("historyHashCopied", "コピーしました")
                                             : display.webCopy("historyHashCopyTitle", "描画ハッシュ全体をコピー"))
                        }
                    }
                }
                note.padding(.top, 10)
            }.padding(.top, 12).overlay(alignment: .top) { Divider() }.padding(.top, 8)
        }
        .task(id: work.id) {
            comment.receive(workID: work.id, state: preview.annotationState)
            generation = nil
            if let node = work.lineageNodeID {
                generation = try? await model.auxiliaryDatabase().lineageGenerations(nodeIDs: [node])[node]
            }
            await model.loadWorkActionState(work)
        }
        .onChange(of: preview.annotationState) { _, state in comment.receive(workID: work.id, state: state) }
    }

    private var byteSize: String {
        let bytes = Double(storedSVGBytes ?? SavedWorkFacts.svgBytes(work))
        if bytes < 1024 { return "\(Int(bytes)) B" }
        if bytes < 1024 * 1024 { return String(format: "%.1f KB", bytes / 1024) }
        return String(format: "%.1f MB", bytes / (1024 * 1024))
    }

    private var exportMenu: some View {
        Menu {
            Text(display.webCopy("savedWorkExportCurrentScope", "表示中の作品") + " · " + work.id.prefix(8))
            Section("SVG") {
                ForEach(["Display", "Editable", "Compat", "Live"], id: \.self) { profile in
                    Button(display.webCopy("svgExport" + profile + "Name", profile) + "　" + display.webCopy("svgExport" + profile + "Sub", "")) {
                        onWorkAction(work, "export-svg:" + profile.lowercased())
                    }
                    .help(display.webCopy("svgExport" + profile + "Feature", ""))
                }
            }
            Section("PNG") {
                ForEach([1080, 2160, 4320, 512, 768], id: \.self) { pixels in
                    Button("PNG \(pixels)px") { onWorkAction(work, "export-png:\(pixels)") }
                }
            }
            Button(display.localized("共有カード")) { onWorkAction(work, "export-format:shareCard") }
            Button(display.webCopy("savedWorkExportDdl", "DDL（プラグイン定義付き）")) { onWorkAction(work, "export-format:ddl") }
            Button(display.webCopy("savedWorkExportLayerAnimation", "レイヤーアニメーション")) { onWorkAction(work, "export-format:apng") }
        } label: { menuLabel(display.localized("書き出す")) }
        .menuStyle(.borderlessButton).fixedSize().disabled(disabled || writingLocked)
    }

    private func menuLabel(_ title: String) -> some View {
        Text(title).inkuFont(12).padding(.vertical, 4).padding(.horizontal, 8)
            .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 4))
            .overlay(RoundedRectangle(cornerRadius: 4).stroke(LibraryChrome.border))
    }

    private var note: some View {
        VStack(alignment: .leading, spacing: 5) {
            Divider().padding(.bottom, 3)
            Text(display.webCopy("historyPreviewCommentLabel", "作品へのコメント")).inkuFont(12).foregroundStyle(.secondary)
            TextField("", text: Binding(get: { comment.text }, set: { comment.text = LibraryNoteEditorModel.limited($0) }), axis: .vertical)
                .lineLimit(3...8).textFieldStyle(.plain).padding(.vertical, 5).padding(.horizontal, 6)
                .frame(minHeight: 64, alignment: .topLeading)
                .background(InkuColor.bg, in: RoundedRectangle(cornerRadius: 5))
                .overlay(RoundedRectangle(cornerRadius: 5).stroke(LibraryChrome.border))
                .accessibilityLabel(display.webCopy("historyPreviewCommentLabel", "作品へのコメント"))
                .disabled(writingLocked || model.library.mutating || preview.annotationState.annotation == nil || comment.saving)
            HStack {
                if let error = comment.errorText { Text(error).inkuFont(11).foregroundStyle(.red) }
                if preview.annotationState == .loading { ProgressView().controlSize(.small) }
                if preview.annotationState == .unavailable { Text(display.localized("コメントを取得できません")).inkuFont(11).foregroundStyle(.red) }
                Spacer(minLength: 0)
                Button(display.webCopy(comment.saving ? "historyPreviewCommentSaving" : "historyPreviewCommentSave", "保存")) { saveNote() }
                    .buttonStyle(LibraryGhostButtonStyle())
                    .disabled(writingLocked || model.library.mutating || !comment.canSave)
            }
        }.inkuFont(12)
    }

    private func fact(_ label: String, _ value: String) -> some View { factRow(label) { Text(value).textSelection(.enabled) } }
    private func factRow<Value: View>(_ label: String, @ViewBuilder value: () -> Value) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Text(label).foregroundStyle(.tertiary).frame(width: 86, alignment: .leading)
            value().frame(maxWidth: .infinity, alignment: .leading)
        }.inkuFont(12).padding(.vertical, 5).overlay(alignment: .top) { Divider() }
    }
    private func open() { if !disabled { onOpen(work) } }
    private func saveNote() {
        guard !writingLocked, !model.library.mutating else { return }
        Task {
            let value = await comment.save { id, submitted in
                await model.library.saveNote(id: id, note: submitted)
                if let error = model.library.errorText { throw NSError(domain: "InkuLibraryNote", code: 1, userInfo: [NSLocalizedDescriptionKey: error]) }
                return try await model.auxiliaryDatabase().libraryAnnotation(id: id)
            }
            if let value { preview.adoptAnnotation(value, workID: work.id) }
        }
    }
}
