import InkuHost
import InkuPersistence
import SwiftUI

public enum SavedWorkActionState: Sendable, Equatable {
    case description, lockedDescription, userDDL, image, unavailable

    init(_ context: SavedAuthoringContext) {
        if context.imageDDL != nil { self = .image }
        else { self.init(origin: context.origin, authority: context.authority) }
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
        ["info", "presentation", "copy-hash", "create", "lineage"].contains(action)
    }
}

/// Header popover using the same actions and availability as the native menus.
@MainActor
struct SavedWorkRefinementPopover: View {
    @Bindable var model: AppModel
    let work: SavedWork
    let title: String
    let onAction: (SavedWork, String) -> Void
    var writingLocked = false
    private var state: SavedWorkActionState? { model.workActionState(for: work) }
    private var disabled: Bool { model.isBusy || writingLocked || work.trashed }
    private var reason: String {
        if state == .lockedDescription { return model.display.webCopy("descriptionLockedReason", "編集した指示書で確定した作品です。記述を読み直す操作は使えません。") }
        if state == .image { return model.display.label("画像から作った作品では、記述から描き直せません。", "A work made from an image cannot be redrawn from a description.") }
        return model.display.localized(state == nil ? "保存条件を読み込み中です。" : "この作品には操作に必要な保存条件が記録されていません。")
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(title).inkuFont(12, weight: .bold).frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 13).padding(.vertical, 8).background(Color.accentColor.opacity(0.14))
                .overlay(alignment: .bottom) { Rectangle().fill(Color.accentColor).frame(height: 1) }
            group("workActionGroupLook", "色と質感") {
                item("canvasVaryColor", "色カタログを変える", "color")
                item("workActionColorArrangement", "配色を変える", "color-arrangement")
                item("workActionGround", "支持体を変える", "ground")
                item("workActionTool", "てざわりを変える", "tool")
            }
            Divider()
            group("workActionGroupForm", "形と指示書") {
                item("canvasVaryComposition", "配置を変える", "layout")
                item("workActionInstructions", "指示書エディタ", "ddl", held: work.ddl?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false)
            }
            if state?.showsDescriptionActions != false {
                Divider()
                group("workActionGroupDescription", "記述から描き直す") {
                    item("workActionDescription", "記述を変える", "description", llm: true, held: state?.canReadDescription != true)
                    item("workActionComposition", "構図と法則を変える", "composition-form", llm: true, held: state?.canReadDescription != true)
                    item("workActionSketchGrain", "写生なし／ありで描き直す", "sketch", llm: true, held: state?.canReadDescription != true)
                    item("workActionModels", "モデルを変える", "model", llm: true, held: state?.canReadDescription != true)
                    if state?.canReadDescription != true { Text(reason).inkuFont(10).foregroundStyle(.tertiary).padding(.horizontal, 13).padding(.vertical, 4) }
                }
            }
        }.padding(.bottom, 4).frame(width: 260).background(InkuColor.panel)
    }
    private func group<Content: View>(_ key: String, _ fallback: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(model.display.webCopy(key, fallback)).inkuFont(10, weight: .semibold).foregroundStyle(.tertiary).padding(.horizontal, 13).padding(.top, 7).padding(.bottom, 2)
            content()
        }.padding(.bottom, 4)
    }
    private func item(_ key: String, _ fallback: String, _ action: String, llm: Bool = false, held: Bool = false) -> some View {
        Button { onAction(work, action) } label: {
            HStack(spacing: 12) {
                Text(model.display.webCopy(key, fallback)).inkuFont(12).lineLimit(1)
                Spacer(minLength: 0)
                if llm { Text("LLM").inkuFont(9, weight: .semibold).foregroundStyle(.secondary).padding(.horizontal, 4).overlay(RoundedRectangle(cornerRadius: 3).stroke(InkuColor.border2)) }
            }.padding(.horizontal, 13).padding(.vertical, 6).frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
        }.buttonStyle(RefinementMenuRowStyle()).disabled(disabled || held).inkuTooltip(held ? reason : "")
    }
}

private struct RefinementMenuRowStyle: ButtonStyle {
    @State private var hovered = false
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.background(hovered || configuration.isPressed ? InkuColor.bg2 : .clear)
            .onHover { hovered = $0 }
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
        if state == .image {
            return model.display.label("画像から作った作品では、記述から描き直せません。", "A work made from an image cannot be redrawn from a description.")
        }
        return model.display.tooltip(state == nil ? "保存条件を読み込み中です。" : "この作品には操作に必要な保存条件が記録されていません。")
    }

    /// WorkActionMenu.svelte: the items that always call the LLM carry a small mark; layout and the instruction
    /// editor call it only to fill a hole, so they do not.
    /// The mark is part of the item's title text: `.badge` drew nothing in the popover's sections (web-parts step 2
    /// screen check, 2026-11-09), and a menu keeps the title's text.
    private func llm(_ title: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label {
                Text(title) + Text("  LLM").font(.system(size: 9 * model.display.preferences.textScale, weight: .semibold))
                    .foregroundStyle(.secondary)
            } icon: { Image(systemName: systemImage) }
        }
        .accessibilityLabel(title)
        .accessibilityHint(model.display.webCopy("workActionLlmMarkLabel", "LLMを呼びます"))
    }

    /// WorkActionMenu.svelte (2026-11-13, product a3a2ef002): three groups and ten items, lightest first, each under a
    /// small heading; a menu draws a separator between sections. A work drawn straight from DDL shows no "redraw from
    /// the description" group. The AI refinement process and the juxtaposition are gone (author 2026-11-13).
    var body: some View {
        Group {
            Group {
                Section(model.display.webCopy("workActionGroupLook", "色と質感")) {
                    Button(model.display.webCopy("canvasVaryColor", "色カタログを変える"), systemImage: "paintpalette") { onAction(work, "color") }
                    Button(model.display.webCopy("workActionColorArrangement", "配色を変える"), systemImage: "arrow.triangle.swap") { onAction(work, "color-arrangement") }
                    Button(model.display.webCopy("workActionGround", "支持体を変える"), systemImage: "square.on.square") { onAction(work, "ground") }
                    Button(model.display.webCopy("workActionTool", "てざわりを変える"), systemImage: "pencil.tip") { onAction(work, "tool") }
                }
                Section(model.display.webCopy("workActionGroupForm", "形と指示書")) {
                    // Layout keeps its own dialog after the reading and touch parameters are retired.
                    Button(model.display.webCopy("canvasVaryComposition", "配置を変える"), systemImage: "square.grid.2x2") { onAction(work, "layout") }
                    Button(model.display.webCopy("workActionInstructions", "指示書エディタ"), systemImage: "doc.text") { onAction(work, "ddl") }
                        .disabled(work.ddl?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false)
                }
                if state?.showsDescriptionActions != false {
                    Section(model.display.webCopy("workActionGroupDescription", "記述から描き直す")) {
                        llm(model.display.webCopy("workActionDescription", "記述を変える"), systemImage: "text.cursor") { onAction(work, "description") }
                            .disabled(state?.canReadDescription != true).help(state?.canReadDescription == true ? model.display.tooltip("記述を変える") : reason)
                        // WorkActionMenu.svelte:145: next to the description edit, with no tooltip of its own.
                        llm(model.display.webCopy("workActionComposition", "構図と法則を変える"), systemImage: "rectangle.3.group") { onAction(work, "composition-form") }
                            .disabled(state?.canReadDescription != true).help(state?.canReadDescription != true ? reason : "")
                        llm(model.display.webCopy("workActionSketchGrain", "写生なし／ありで描き直す"), systemImage: "pencil.and.outline") { onAction(work, "sketch") }
                            .disabled(state?.canReadDescription != true).help(state?.canReadDescription == true ? model.display.tooltip("写生なし／ありで描き直す") : reason)
                        llm(model.display.webCopy("workActionModels", "モデルを変える"), systemImage: "cpu") { onAction(work, "model") }
                            .disabled(state?.canReadDescription != true).help(state?.canReadDescription == true ? model.display.tooltip("モデルを変える") : reason)
                        if state?.canReadDescription != true { Text(reason) }
                    }
                }
            }.disabled(model.isBusy || writingLocked || work.trashed)
        }
    }
}
