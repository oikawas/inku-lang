import InkuHost
import InkuPersistence
import SwiftUI

/// Browsing stays separate from the work selected by the creation workspace.
@MainActor
struct PhoneWorkViewer: View {
    @Bindable var model: AppModel
    let work: SavedWork
    let isTrash: Bool
    let writingLocked: Bool
    let sharing: Bool
    let runStatus: String
    let onClose: () -> Void
    let onMove: (Int) -> Void
    let onFirst: () -> Void
    let onLast: () -> Void
    let onRun: () -> Void
    let onShare: (SavedWork) -> Void
    let onRefine: (SavedWork) -> Void
    let onInfo: (SavedWork) -> Void
    let onAction: (SavedWork, String) -> Void
    let onLineage: (SavedWork) -> Void
    let onCreate: (SavedWork) -> Void
    let onDelete: (SavedWork, Bool) -> Void
    @State private var viewport = CanvasViewport()
    @State private var overlayVisible = true
    @State private var threeDimensional = false
    @State private var controller = Ddl3DController()
    @State private var starOverride: Bool?
    private var display: DisplaySettings { model.display }
    private var starred: Bool { starOverride ?? model.library.works.first(where: { $0.id == work.id })?.starred ?? work.starred }
    private var permissions: PhoneViewingPermissions {
        PhoneViewingPermissions(browsingLocked: model.isBrowsingLocked, writingLocked: writingLocked || model.isBusy,
                                mutating: model.library.mutating, trashed: work.trashed, sharing: sharing)
    }

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                Color.black.ignoresSafeArea()
                if threeDimensional, let registration = Ddl3DInstallation.registered {
                    Ddl3DCanvas(controller: controller, registration: registration, work: work,
                                initialView: Ddl3DInitialView(pixelWidth: geometry.size.width, pixelHeight: geometry.size.height,
                                                              panX: 0, panY: 0, zoom: 1),
                                onReturn: { threeDimensional = false }, onEscape: { false })
                        .padding(.top, model.hasActiveRun ? 100 : 48)
                } else {
                    ArtworkCanvas(svg: work.svg, renderer: model.displayRenderer, caption: work.effectiveSourceText,
                                  style: .viewer, showsZoomControls: false, aspectRatio: work.renderCanvasAspectRatio,
                                  viewport: $viewport)
                        .contentShape(Rectangle())
                        .simultaneousGesture(SpatialTapGesture(count: 2).exclusively(before: SpatialTapGesture()).onEnded { tap in
                            switch tap {
                            case .first(let value):
                                guard acceptsTap(value.location, height: geometry.size.height) else { return }
                                if Ddl3DInstallation.available { threeDimensional = true; overlayVisible = true }
                            case .second(let value):
                                guard acceptsTap(value.location, height: geometry.size.height) else { return }
                                withAnimation(.easeInOut(duration: 0.15)) { overlayVisible.toggle() }
                            }
                        })
                        .simultaneousGesture(DragGesture(minimumDistance: 35).onEnded { value in
                            guard viewport.scale <= 1.01 else { return }
                            let dx = value.translation.width, dy = value.translation.height
                            if dy > 90 && dy > abs(dx) * 1.4 { onClose() }
                            else if abs(dx) > 70 && abs(dx) > abs(dy) * 1.4 { onMove(dx < 0 ? 1 : -1) }
                        })
                }
                if overlayVisible || threeDimensional {
                    VStack(spacing: 0) {
                        topBar
                        if model.hasActiveRun { PhoneRunStatusRow(model: model, status: runStatus, onOpen: onRun) }
                        Spacer()
                        bottomBar
                    }
                }
            }
        }
        .navigationBarBackButtonHidden(true)
        .toolbar(.hidden)
        .inkuPhoneTabBarHidden()
        .onChange(of: work.id) { _, _ in viewport = CanvasViewport(); threeDimensional = false; starOverride = nil }
        .task(id: work.id) { await model.loadWorkActionState(work) }
    }

    private func acceptsTap(_ location: CGPoint, height: CGFloat) -> Bool {
        guard overlayVisible else { return true }
        return location.y >= (model.hasActiveRun ? 100 : 44) && location.y < height - 58
    }

    private var topBar: some View {
        HStack {
            Button(action: onClose) { Image(systemName: "chevron.left").frame(width: 44, height: 44) }
                .accessibilityLabel(display.localized("閉じる"))
            Spacer()
            if threeDimensional {
                Button(display.webCopy("ddl3dReturn", "2Dに戻る")) { threeDimensional = false }.frame(minHeight: 44)
            }
            Menu { menu } label: { Image(systemName: "ellipsis").frame(width: 44, height: 44) }
                .accessibilityLabel(display.localized("作品の操作"))
        }.foregroundStyle(.white).padding(.horizontal, 8).background(.black.opacity(0.55))
    }

    @ViewBuilder private var bottomBar: some View {
        if isTrash {
            HStack {
                Button(display.localized("戻す")) { onDelete(work, false) }
                Spacer()
                Button(display.localized("完全に削除"), role: .destructive) { onDelete(work, true) }
            }.disabled(writingLocked || model.isBusy || model.library.mutating)
                .frame(minHeight: 54).padding(.horizontal, 20).background(.black.opacity(0.65))
        } else {
            HStack(spacing: 16) {
                Button {
                    var target = work; target.starred = starred
                    Task {
                        await model.library.toggleStar(target)
                        if let saved = try? await model.auxiliaryDatabase().work(id: work.id) { starOverride = saved.starred }
                    }
                } label: { Label(display.label("スター", "Star"), systemImage: starred ? "star.fill" : "star") }
                    .disabled(!permissions.canStar)
                Spacer()
                Button(display.webCopy("historyPreviewRefine", "推敲する")) { onRefine(work) }.disabled(!permissions.canWrite)
                Button { onShare(work) } label: {
                    HStack { if sharing { ProgressView() }; Text(display.label("共有", "Share")) }
                        .frame(minWidth: 76, minHeight: 44)
                }.buttonStyle(.borderedProminent).disabled(!permissions.canShare)
            }.foregroundStyle(.white).frame(minHeight: 58).padding(.horizontal, 16).background(.black.opacity(0.65))
        }
    }

    @ViewBuilder private var menu: some View {
        Section(display.label("詞書", "Caption")) {
            Toggle(display.webCopy("canvasCaptionToggle", "詞書の表示"), isOn: Bindable(display).preferences.captionVisible)
            Toggle(display.webCopy("canvasCaptionWritingMode", "詞書の書字方向"), isOn: Bindable(display).preferences.captionVertical)
            Picker(display.webCopy("settingsCaptionPosition", "詞書の表示位置"), selection: Bindable(display).preferences.captionPosition) {
                Text(display.localized("左")).tag("left")
                Text(display.localized("右")).tag("right")
            }
        }
        Button(display.webCopy("historyPreviewDetails", "作品情報")) { onInfo(work) }
        Button(display.localized("生成情報")) { onAction(work, "info") }.disabled(model.isBrowsingLocked || work.trashed)
        Button(display.localized("系譜")) { onLineage(work) }.disabled(!permissions.canBrowse || work.lineageNodeID == nil)
        Button(display.localized("制作で開く")) { onCreate(work) }.disabled(!permissions.canBrowse)
        SavedWorkExportMenu(model: model, count: 1) { onAction(work, $0) }.disabled(!permissions.canWrite)
        Button(display.localized("クリップボードにコピー")) { Task { await model.copyImage(work: work) } }.disabled(!permissions.canWrite)
        Button(display.localized("推敲の印")) { Task { await model.library.toggleRevision(work) } }.disabled(!permissions.canWrite || model.library.mutating)
        Button(display.label("作品 UUID をコピー", "Copy work UUID")) { model.library.copyHash(work.id) }
        Button(display.localized("最新へ"), action: onFirst)
        Button(display.localized("最古へ"), action: onLast)
        if !isTrash { Button(display.localized("ごみ箱へ"), role: .destructive) { onDelete(work, false) }.disabled(!permissions.canWrite) }
    }
}

@MainActor
struct PhoneWorkInformation: View {
    @Bindable var model: AppModel
    let work: SavedWork
    let writingLocked: Bool
    @State private var preview = LibraryPreviewModel()
    @State private var comment = LibraryNoteEditorModel()
    @State private var providers: [ProviderSettings] = []
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            ScrollView {
                LibraryPreviewPanel(model: model, preview: preview, comment: comment, work: work,
                                    naming: ModelNaming(providers: providers, stageProvider: model.stageDefaultProviderID,
                                                        language: model.display.preferences.language),
                                    onOpen: { _ in }, onLineage: { _ in }, onWorkAction: { _, _ in },
                                    writingLocked: writingLocked, informationOnly: true).padding(16)
            }
            .navigationTitle(model.display.webCopy("historyPreviewDetails", "作品情報"))
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(model.display.localized("閉じる")) { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(model.display.webCopy("historyPreviewCommentSave", "保存")) { saveNote() }
                        .disabled(writingLocked || model.library.mutating || !comment.canSave)
                }
            }
        }
        .task {
            preview.show(work)
            providers = await model.hostSettings().providers
            await preview.loadAnnotation(using: { try await model.auxiliaryDatabase().libraryAnnotation(id: $0) })
        }
    }

    private func saveNote() {
        Task {
            let value = await comment.save { id, submitted in
                await model.library.saveNote(id: id, note: submitted)
                if let error = model.library.errorText {
                    throw NSError(domain: "InkuLibraryNote", code: 1, userInfo: [NSLocalizedDescriptionKey: error])
                }
                return try await model.auxiliaryDatabase().libraryAnnotation(id: id)
            }
            if let value { preview.adoptAnnotation(value, workID: work.id) }
        }
    }
}
