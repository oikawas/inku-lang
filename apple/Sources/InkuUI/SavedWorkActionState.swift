import InkuHost
import InkuPersistence
import SwiftUI

public enum SavedWorkActionState: Sendable, Equatable {
    case description, lockedDescription, userDDL, unavailable

    init(_ context: SavedAuthoringContext) {
        self.init(origin: context.origin, authority: context.authority)
    }

    init(origin: String, authority: String) {
        if origin == AuthoringOrigin.userAuthoredDDL.rawValue { self = .userDDL }
        else if origin == AuthoringOrigin.stage1Generated.rawValue {
            self = authority == "ddl_authoritative" ? .lockedDescription : .description
        } else { self = .unavailable }
    }

    var showsDescriptionActions: Bool { self != .userDDL }
    var canReadDescription: Bool { self == .description }

    static func isBrowsingAction(_ action: String) -> Bool {
        ["info", "presentation", "copy-hash", "create", "lineage", "ai"].contains(action)
    }
}

/// All entrances act on the saved work, without selecting it as the next input.
@MainActor
struct SavedWorkRefinementActions: View {
    @Bindable var model: AppModel
    let work: SavedWork
    let onAction: (SavedWork, String) -> Void
    var writingLocked = false
    private var state: SavedWorkActionState? { model.workActionState(for: work) }
    private var reason: String {
        if state == .lockedDescription {
            return model.display.tooltip("編集した指示書で確定した作品です。記述を読み直す操作は使えません。", serverKey: "descriptionLockedReason")
        }
        return model.display.tooltip(state == nil ? "保存条件を読み込み中です。" : "この作品には操作に必要な保存条件が記録されていません。")
    }

    /// WorkActionMenu.svelte: the items that always call the LLM carry a small mark; layout and the instruction
    /// editor call it only to fill a hole, so they do not.
    private func llm<Item: View>(_ item: Item) -> some View {
        item.badge(Text("LLM")).accessibilityHint(model.display.webCopy("workActionLlmMarkLabel", "LLMを呼びます"))
    }

    /// SPEC.ja.md:656 (2026-10-18): four groups, lightest first, each under a small heading; a menu draws a
    /// separator between sections. A work drawn straight from DDL shows no "redraw from the description" group.
    var body: some View {
        Group {
            Group {
                Section(model.display.webCopy("workActionGroupLook", "色と質感")) {
                    Button(model.display.localized("色カタログを変える"), systemImage: "paintpalette") { onAction(work, "color") }
                    Button(model.display.localized("配色を変える"), systemImage: "arrow.triangle.swap") { onAction(work, "color-arrangement") }
                    Button(model.display.localized("支持体を変える"), systemImage: "square.on.square") { onAction(work, "ground") }
                    Button(model.display.localized("てざわりを変える"), systemImage: "pencil.tip") { onAction(work, "tool") }
                }
                Section(model.display.webCopy("workActionGroupForm", "形と指示書")) {
                    // Layout keeps its own dialog after the reading and touch parameters are retired.
                    Button(model.display.localized("配置を変える"), systemImage: "square.grid.2x2") { onAction(work, "layout") }
                    Button(model.display.localized("指示書エディタ"), systemImage: "doc.text") { onAction(work, "ddl") }
                        .disabled(work.ddl?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false)
                }
                if state?.showsDescriptionActions != false {
                    Section(model.display.webCopy("workActionGroupDescription", "記述から描き直す")) {
                        llm(Button(model.display.localized("記述を変える"), systemImage: "text.cursor") { onAction(work, "description") }
                            .disabled(state?.canReadDescription != true).help(state?.canReadDescription == true ? model.display.tooltip("記述を変える") : reason))
                        llm(Button(model.display.localized("写生なし／ありで描き直す"), systemImage: "pencil.and.outline") { onAction(work, "sketch") }
                            .disabled(state?.canReadDescription != true).help(state?.canReadDescription == true ? model.display.tooltip("写生なし／ありで描き直す") : reason))
                        llm(Button(model.display.localized("モデルを変える"), systemImage: "cpu") { onAction(work, "model") }
                            .disabled(state?.canReadDescription != true).help(state?.canReadDescription == true ? model.display.tooltip("モデルを変える") : reason))
                        // WorkActionMenu.svelte:147: a sentence from another work, added after the description.
                        llm(Button(model.display.webCopy("workActionJuxtapose", "取り合わせ"), systemImage: "text.badge.plus") { onAction(work, "juxtapose") }
                            .disabled(state?.canReadDescription != true).help(state?.canReadDescription == true ? "" : reason))
                        if state?.canReadDescription != true { Text(reason) }
                    }
                }
            }.disabled(model.isBusy || writingLocked || work.trashed)
            Section(model.display.webCopy("workActionGroupAi", "AIに任せる")) {
                llm(Button(model.display.localized("AI自動推敲プロセス"), systemImage: "wand.and.stars") { onAction(work, "ai") })
            }.disabled(work.trashed || ((model.isBusy || writingLocked) && !model.autonomousRefinement.running))
        }
    }
}
