import InkuHost
import InkuPersistence
import SwiftUI

public enum SavedWorkActionState: Sendable, Equatable {
    case description, lockedDescription, userDDL, unavailable

    init(_ context: SavedAuthoringContext) {
        if context.originKind == .userAuthoredDDL { self = .userDDL }
        else if context.originKind == .stage1Generated {
            self = context.authority == "ddl_authoritative" ? .lockedDescription : .description
        } else { self = .unavailable }
    }

    var showsDescriptionActions: Bool { self != .userDDL }
    var canReadDescription: Bool { self == .description }
}

/// All entrances act on the saved work, without selecting it as the next input.
@MainActor
struct SavedWorkRefinementActions: View {
    @Bindable var model: AppModel
    let work: SavedWork
    let onAction: (SavedWork, String) -> Void
    private var state: SavedWorkActionState? { model.workActionState(for: work) }
    private var reason: String {
        if state == .lockedDescription {
            return model.display.tooltip("編集した指示書で確定した作品です。記述を読み直す操作は使えません。", serverKey: "descriptionLockedReason")
        }
        return model.display.tooltip(state == nil ? "保存条件を読み込み中です。" : "この作品には操作に必要な保存条件が記録されていません。")
    }

    var body: some View {
        Group {
            Button(model.display.localized("描画パラメータの編集"), systemImage: "slider.horizontal.3") { onAction(work, "parameters") }
            Button(model.display.localized("色カタログを変える"), systemImage: "paintpalette") { onAction(work, "color") }
            if state?.showsDescriptionActions != false {
                Button(model.display.localized("記述を変える"), systemImage: "text.cursor") { onAction(work, "description") }
                    .disabled(state?.canReadDescription != true).help(state?.canReadDescription == true ? model.display.tooltip("記述を変える") : reason)
            }
            Button(model.display.localized("指示書を編集"), systemImage: "doc.text") { onAction(work, "ddl") }
                .disabled(work.ddl?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false)
            if state?.showsDescriptionActions != false {
                Button(model.display.localized("写生なし／ありで描き直す"), systemImage: "pencil.and.outline") { onAction(work, "sketch") }
                    .disabled(state?.canReadDescription != true).help(state?.canReadDescription == true ? model.display.tooltip("写生なし／ありで描き直す") : reason)
                Button(model.display.localized("モデルを変える"), systemImage: "cpu") { onAction(work, "model") }
                    .disabled(state?.canReadDescription != true).help(state?.canReadDescription == true ? model.display.tooltip("モデルを変える") : reason)
                if state?.canReadDescription != true { Text(reason) }
            }
            Button(model.display.localized("AIプロセス"), systemImage: "wand.and.stars") { onAction(work, "ai") }
        }.disabled(model.isBusy || work.trashed)
    }
}
