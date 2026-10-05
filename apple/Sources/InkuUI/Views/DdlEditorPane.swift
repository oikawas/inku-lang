import SwiftUI

/// Web `DdlEditor.svelte`: the language the DDL is read in, the quick-guide switch and 「N 行・N 文字」 above a
/// numbered, highlighted editor, then the names this installation does not hold and the guide.
/// The vocabulary stays in the native Saijiki sheet; a chosen word goes in at the caret.
@MainActor
struct DdlEditorPane: View {
    @Bindable var model: AppModel
    @Binding var text: String
    var disabled = false
    @Binding var insertion: InkuEditorInsertion?
    var onShowSaijiki: (() -> Void)?
    @State private var showGuide = false
    @State private var highlighter: DdlHighlighter
    private let plugins: PluginNameIndex

    init(model: AppModel, text: Binding<String>, disabled: Bool = false, insertion: Binding<InkuEditorInsertion?>,
         onShowSaijiki: (() -> Void)? = nil) {
        self.model = model
        _text = text
        self.disabled = disabled
        _insertion = insertion
        self.onShowSaijiki = onShowSaijiki
        let plugins = PluginNameIndex(words: model.pluginWords)
        self.plugins = plugins
        _highlighter = State(initialValue: DdlHighlighter(saijiki: model.saijiki, plugins: plugins))
    }

    private var display: DisplaySettings { model.display }
    private var english: Bool { display.preferences.language == "en" }
    private var unknownNames: [PluginNameIndex.Unknown] { plugins.unknownNames(in: text) }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            toolbar
            editor.frame(maxHeight: .infinity)
            if !unknownNames.isEmpty || showGuide { support }
        }
    }

    /// `.ddl-editor-toolbar`: the language label with its tooltip, the switches, and the status at the right.
    private var toolbar: some View {
        let lines = text.components(separatedBy: "\n").count
        let characters = text.utf16.count
        return HStack(spacing: 8) {
            Text(display.localized(model.instructionLanguage(for: text) == "ja" ? "指示書（日本語DDL）" : "指示書（英語DDL）"))
                .inkuFont(12, weight: .medium).foregroundStyle(.secondary).lineLimit(1)
                .inkuTooltip(display.tooltip("指示書はこの言語の文法で読みます。", serverKey: "tooltipDdlLang"))
            if let onShowSaijiki {
                Button(display.webCopy("ddlEditorVocabulary", "歳時記の語彙"), action: onShowSaijiki)
                    .buttonStyle(InkuGhostButtonStyle()).disabled(disabled)
                    .inkuTooltip(display.tooltip("選んだ語を編集中DDLのカーソル位置に挿入します。"))
            }
            Button(display.webCopy("ddlEditorSyntaxGuideToggle", "簡易ガイド")) { showGuide.toggle() }
                .buttonStyle(InkuGhostButtonStyle(active: showGuide))
                .accessibilityValue(display.localized(showGuide ? "オン" : "オフ"))
            Spacer(minLength: 8)
            Text(english ? "\(lines) lines · \(characters) characters" : "\(lines) 行・\(characters) 文字")
                .inkuFont(12).monospacedDigit().foregroundStyle(.tertiary).lineLimit(1)
        }
    }

    private var editor: some View {
        ZStack(alignment: .topLeading) {
            InkuTextEditor(text: $text, isEditable: !disabled, accessibilityLabel: display.webCopy("ddlEditorInstructions", "指示書"),
                           style: .ddl, marks: { [highlighter] in highlighter.marks($0) }, insertion: $insertion)
            if text.isEmpty {
                Text(display.webCopy("ddlEditPlaceholder", "背景を白で埋める。青い細い線を左下から右上へ三本引く。赤い小さな円を余白を残して配置する。"))
                    .inkuFont(14).foregroundStyle(.tertiary).lineSpacing(14 * 0.7)
                    .padding(.leading, 34 + 11).padding(.trailing, 11).padding(.top, 10)
                    .allowsHitTesting(false)
            }
        }
        .background(InkuColor.panel, in: RoundedRectangle(cornerRadius: 4))
        .clipShape(RoundedRectangle(cornerRadius: 4))
        .overlay(RoundedRectangle(cornerRadius: 4).stroke(Color.accentColor.opacity(0.7)))
    }

    /// `.ddl-editor-support`: unknown names in amber with what each would fire as, then the guide.
    private var support: some View {
        VStack(alignment: .leading, spacing: 8) {
            if !unknownNames.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text(display.webCopy("ddlUnknownNameTitle", "このサーバーにない名前")).inkuFont(12, weight: .semibold)
                    ForEach(unknownNames, id: \.text) { unknown in
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(unknown.text).inkuFont(12, design: .monospaced).foregroundStyle(Self.unknownColor).textSelection(.enabled)
                            Text(firingHint(unknown)).inkuFont(12).foregroundStyle(.secondary)
                        }
                    }
                }
                .padding(.vertical, 6).padding(.horizontal, 10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Self.unknownColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 4))
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(Self.unknownColor.opacity(0.42)))
            }
            if showGuide {
                ScrollView {
                    Text(display.webCopy("ddlSyntaxGuide", "指示書（DDL）簡易ガイド")).inkuFont(12).foregroundStyle(.secondary)
                        .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxHeight: 180)
                .padding(10)
                .background(InkuColor.bg2, in: RoundedRectangle(cornerRadius: 4))
            }
        }
    }

    private static let unknownColor = Color(red: 0xbf / 255, green: 0x88 / 255, blue: 0x20 / 255)

    /// ja.ts:378-379, en.ts:378-379.
    private func firingHint(_ unknown: PluginNameIndex.Unknown) -> String {
        guard let word = unknown.firesAs else { return display.webCopy("ddlUnknownNameUnregistered", "この名前は登録されていません") }
        return english ? "Drop the “\(unknown.namespace).” and it fires as “\(word)”"
            : "「\(unknown.namespace).」を外すと「\(word)」として効きます"
    }
}
