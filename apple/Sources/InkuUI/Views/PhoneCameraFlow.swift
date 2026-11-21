import SwiftUI

/// The iPhone tab bar's camera (author 2026-11-13, "andorid版と同じく、画面下のアイコンからカメラ撮影→画像から描く"): the
/// checks before the photo, the camera, and the drawing from the photo with the image defaults. The camera has no model
/// choice of its own. Progress and the result show as the image tab's drawing does (the author's choice).
@MainActor
struct PhoneCameraFlow: ViewModifier {
    @Bindable var model: AppModel
    let automation: AutomationModel
    let ui: WorkspaceUIState
    /// Bumped each time the tab bar's camera is pressed.
    let request: Int
    /// Another screen holds the app (a dialog, a DDL import or the presentation).
    let blocked: Bool
    let onOpenSettings: (SettingsSection) -> Void
    /// To the 制作 tab's work, with its input panel.
    let onShowCreation: () -> Void

    private enum Notice: Identifiable {
        case refusal(CameraDrawRefusal), upload, noCamera
        var id: String {
            switch self {
            case .refusal(let refusal): "refusal-\(refusal)"
            case .upload: "upload"
            case .noCamera: "no-camera"
            }
        }
    }

    @State private var notice: Notice?
    @State private var capturing = false
    @State private var cameraAfterNotice = false

    private var display: DisplaySettings { model.display }
    private var otherRunActive: Bool { blocked || automation.isOccupied || automation.imageFolderBatch.running }

    func body(content: Content) -> some View {
        content
            .onChange(of: request) { _, _ in Task { await start() } }
            // What the notice leads to opens once the notice has gone: shown from the button, the next window was
            // dropped while the notice was still closing (screen check 2026-11-13, step 8).
            .onChange(of: notice == nil) { _, closed in
                guard closed, cameraAfterNotice else { return }
                cameraAfterNotice = false
                Task {
                    try? await Task.sleep(for: .milliseconds(450))
                    openCamera()
                }
            }
            .inkuCameraCapture(isPresented: $capturing) { data in Task { await draw(data) } }
            .alert(title(notice), isPresented: Binding(get: { notice != nil }, set: { if !$0 { notice = nil } }),
                   presenting: notice) { shown in
                switch shown {
                case .upload:
                    Button(display.webCopy("imageUploadNoticeContinue", "了解して描画する")) {
                        model.imageWarningAcknowledged = true
                        cameraAfterNotice = true
                    }
                    Button(display.localized("キャンセル"), role: .cancel) {}
                case .refusal(let refusal):
                    if let section = settingsSection(refusal) {
                        Button(display.localized("設定を開く")) { onOpenSettings(section) }
                    }
                    Button(display.localized("閉じる"), role: .cancel) {}
                case .noCamera:
                    Button(display.localized("閉じる"), role: .cancel) {}
                }
            } message: { shown in
                Text(message(shown))
            }
    }

    /// Android's order: whether the camera may draw, then (once a launch) the upload notice, then the camera.
    private func start() async {
        if let refusal = await model.cameraDrawRefusal(otherRunActive: otherRunActive) {
            notice = .refusal(refusal)
        } else if !model.imageWarningAcknowledged {
            notice = .upload
        } else {
            openCamera()
        }
    }

    private func openCamera() {
        if InkuCamera.isAvailable { capturing = true } else { notice = .noCamera }
    }

    /// Straight to drawing, as Android does. The camera was open a while, so the checks run again; a photo the camera
    /// can no longer draw stays in the image tab rather than being lost.
    private func draw(_ data: Data) async {
        onShowCreation()
        automation.selectInputTab("image", app: model)
        do {
            let prepared = try model.preparedImage(data: data, fileName: nil)
            if let refusal = await model.cameraDrawRefusal(otherRunActive: otherRunActive) {
                if !model.isBusy {
                    model.setImageInput(prepared.image, fileName: display.localized("写真"), automaticProvenance: prepared.provenance)
                }
                await afterCameraCloses()
                notice = .refusal(refusal)
                return
            }
            model.prepareCameraDraw(prepared.image, provenance: prepared.provenance)
            guard model.canGenerate else { return }
            ui.scrollToImageRun = true
            await model.generate()
        } catch {
            await afterCameraCloses()
            model.errorText = model.failureMessage(error)
        }
    }

    /// A window shown while the camera's cover is still closing is dropped, as one shown from the notice's button was.
    private func afterCameraCloses() async {
        try? await Task.sleep(for: .milliseconds(450))
    }

    private func title(_ notice: Notice?) -> String {
        switch notice {
        case .upload: display.webCopy("imageTab", "画像")
        case .refusal(.noModel), .refusal(.modelUnavailable), .refusal(.keyMissing):
            display.localized("撮影の準備ができていません")
        default: display.localized("カメラ")
        }
    }

    private func message(_ notice: Notice) -> String {
        switch notice {
        case .upload:
            return display.webCopy("imageUploadNoticeMessage", "画像から描画を行う場合、画像データがAIにアップロードされます。アップロードされたデータの扱いは、ユーザーが指定したモデルと、それをホストするプロバイダの規約に準じます。\nセンシティブなデータをアップロードしないでください。")
        case .noCamera:
            return display.localized("この機器ではカメラを使えません。")
        case .refusal(let refusal):
            switch refusal {
            case .busy: return display.localized("描いている間は撮影できません。描き終わるか、停止してから押してください。")
            case .previewOpen: return display.localized("保存していない候補を表示している間は撮影できません。")
            case .noModel: return display.localized("「描くときのデフォルト」の「画像」で、画像を読むモデルを選んでください。")
            case .modelUnavailable:
                return display.localized("画像を読むモデルを使えません。描くときのデフォルトで選び直してください。")
            case .keyMissing:
                return display.localized("画像を読むモデルの接続先に、API キーがありません。")
            }
        }
    }

    private func settingsSection(_ refusal: CameraDrawRefusal) -> SettingsSection? {
        switch refusal {
        case .noModel, .modelUnavailable: .drawDefaults
        case .keyMissing: .models
        case .busy, .previewOpen: nil
        }
    }
}
