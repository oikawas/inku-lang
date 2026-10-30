import SwiftUI
import InkuHost

/// Web `DdlEditor.svelte`: the language the DDL is read in, the quick-guide switch and 「N 行・N 文字」 above a
/// numbered, highlighted editor, then the names this installation does not hold and the guide.
/// The inline vocabulary inserts a chosen word at the caret, without opening another sheet.
@MainActor
struct DdlEditorPane: View {
    @Bindable var model: AppModel
    @Binding var text: String
    var disabled = false
    @Binding var insertion: InkuEditorInsertion?
    @State private var showVocabulary = true
    @State private var showGuide = false
    @State private var completionStates: [CompletionRangeState] = []
    @State private var completionSource = ""
    @State private var pluginCalls: [PluginCall] = []
    @State private var pluginSource = ""
    @State private var hoverIndex: Int?
    @Environment(\.inkuTooltipsCovered) private var tooltipsCovered
    @State private var rangeStatus = RangeEditorStatus()
    /// Web DdlEditorDialog: an invalid range or an IME composition holds the draw back.
    var onRangeBlocked: ((Bool) -> Void)?
    var onRangePreview: ((CompositionRanges.Preview?) -> Void)?
    private var invalidSource: Bool { rangeStatus.invalid || CompositionRanges.scan(text).contains { $0.bounds == nil } }
    private var highlighter: DdlHighlighter { DdlHighlighter(saijiki: model.saijiki, calls: pluginSource == text ? pluginCalls : []) }

    init(model: AppModel, text: Binding<String>, disabled: Bool = false, insertion: Binding<InkuEditorInsertion?>,
         onRangeBlocked: ((Bool) -> Void)? = nil, onRangePreview: ((CompositionRanges.Preview?) -> Void)? = nil) {
        self.onRangeBlocked = onRangeBlocked
        self.onRangePreview = onRangePreview
        self.model = model
        _text = text
        self.disabled = disabled
        _insertion = insertion
    }

    private var display: DisplaySettings { model.display }
    private var english: Bool { display.preferences.language == "en" }
    private var unknownNames: [PluginCall] { pluginSource == text ? pluginCalls.filter { $0.status != "resolved" } : [] }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            toolbar
            GeometryReader { geometry in
                VStack(alignment: .leading, spacing: 10) {
                    VStack(alignment: .leading, spacing: 6) {
                        editor.frame(minHeight: 80)
                        if completionSource == text { CompletionRangeSummary(display: display, states: completionStates) }
                        if invalidSource {
                            Text(display.localized("横1/3〜2/3、縦2/3〜1 の形で、0〜1の数を、始まりを終わりより小さく書いてください。「-」「－」も使えます。枠は最後の有効な範囲です"))
                                .inkuFont(12).foregroundStyle(.red).fixedSize(horizontal: false, vertical: true)
                        }
                        if !unknownNames.isEmpty || showGuide { support.frame(maxHeight: min(150, geometry.size.height * 0.24)) }
                    }.frame(height: showVocabulary ? max(160, geometry.size.height * (showGuide || !unknownNames.isEmpty ? 0.46 : 0.50)) : nil)
                    if showVocabulary {
                        SaijikiView(model: model, onInsertWord: { insertion = InkuEditorInsertion(text: $0) },
                            wordLanguage: model.instructionLanguage(for: text), inline: true)
                            .disabled(disabled)
                    }
                }
            }
        }
        .onChange(of: invalidSource || rangeStatus.composing, initial: true) { _, blocked in onRangeBlocked?(blocked) }
        .onDisappear { onRangePreview?(nil) }
    }

    /// `.ddl-editor-toolbar`: the language label with its tooltip, the switches, and the status at the right.
    private var toolbar: some View {
        let lines = text.components(separatedBy: "\n").count
        let characters = text.utf16.count
        return HStack(spacing: 8) {
            Text(display.localized(model.instructionLanguage(for: text) == "ja" ? "指示書（日本語DDL）" : "指示書（英語DDL）"))
                .inkuFont(12, weight: .medium).foregroundStyle(.secondary).lineLimit(1)
                .inkuTooltip(display.tooltip("指示書はこの言語の文法で読みます。", serverKey: "tooltipDdlLang"))
            Button(display.webCopy("ddlEditorVocabulary", "歳時記の語彙")) { showVocabulary.toggle() }
                .buttonStyle(InkuGhostButtonStyle(active: showVocabulary))
                .accessibilityValue(display.localized(showVocabulary ? "オン" : "オフ"))
                .inkuTooltip(display.tooltip("選んだ語を編集中DDLのカーソル位置に挿入します。"))
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
                           style: .ddl, marks: { [highlighter, completionStates, completionSource] source in
                               // Tags describe the text they were read for and vanish once it changes (Web).
                               highlighter.marks(source) + (source == completionSource ? CompletionRangeStyle.marks(completionStates) : [])
                           }, insertion: $insertion,
                           rangeTable: CompositionRanges.table,
                           onRangeStatus: { status in
                               rangeStatus = status
                               onRangePreview?(status.preview)
                           },
                           completions: model.ddlCompletions, onCharacterHover: { hoverIndex = $0 })
            if text.isEmpty {
                Text(display.webCopy("ddlEditPlaceholder", "背景を白で埋める。青い細い線を左下から右上へ三本引く。赤い小さな円を余白を残して配置する。"))
                    .inkuFont(14).foregroundStyle(.tertiary).lineSpacing(14 * 0.7)
                    .padding(.leading, 34 + 11).padding(.trailing, 11).padding(.top, 10)
                    .allowsHitTesting(false)
            }
        }
        .background(InkuColor.panel, in: RoundedRectangle(cornerRadius: 4))
        .overlay(alignment: .topTrailing) {
            if !tooltipsCovered, display.preferences.showTooltips, pluginSource == text,
               let hoverIndex, let call = pluginCalls.first(where: { NSLocationInRange(hoverIndex, $0.range) }) {
                PluginCallPreview(call: call, model: model, language: model.instructionLanguage(for: text))
                    .allowsHitTesting(false).padding(8)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 4))
        .overlay(RoundedRectangle(cornerRadius: 4).stroke(Color.accentColor.opacity(0.7)))
        // Web DdlEditor: the states are asked 180 ms after the text settles.
        .task(id: [text, model.completionRecordKey]) {
            try? await Task.sleep(for: .milliseconds(180))
            guard !Task.isCancelled else { return }
            let source = text
            let calls = await model.pluginCalls(source: source)
            guard !Task.isCancelled, text == source else { return }
            pluginCalls = calls; pluginSource = source
            completionStates = model.completionRangeStates(source: source)
            completionSource = source
        }
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
    private func firingHint(_ unknown: PluginCall) -> String {
        switch unknown.status {
        case "plugin_disabled": return english ? "This plugin is disabled." : "このプラグインは無効です。"
        case "plugin_name_mismatch":
            let suggested = unknown.suggestion ?? ""
            let name = suggested.hasPrefix("{") || suggested.hasPrefix("｛") ? suggested
                : (model.instructionLanguage(for: text) == "en" ? "{\(suggested)}" : "｛\(suggested)｝")
            return english ? "Did you mean \(name)?" : "\(name) ではありませんか。"
        case "plugin_name_ambiguous":
            return (english ? "More than one word matches: " : "複数の語に一致します：") + unknown.candidates.joined(separator: ", ")
        default: return display.webCopy("ddlUnknownNameUnregistered", "この名前は登録されていません")
        }
    }
}

@MainActor
struct PluginCallPreview: View {
    let call: PluginCall
    let model: AppModel
    let language: String
    private var japanese: Bool { model.display.preferences.language != "en" }
    private var word: PluginWord? { model.pluginWords.first { $0.id == call.qualifiedName } }
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if call.status == "resolved" {
                Text((language == "en" ? call.writtenEnglish : call.writtenJapanese) ?? word?.displayName(language: language) ?? "").inkuFont(12, weight: .semibold)
                if let word {
                    let others = Array(word.japanese.dropFirst()) + Array(word.english.dropFirst())
                    if !others.isEmpty { Text(others.joined(separator: " / ")).inkuFont(11) }
                    Text(word.kind == "object" ? model.display.label("物の語", "Object word") : model.display.label("情景の語", "Scene word")).inkuFont(11)
                }
                let note = japanese ? (word?.note ?? call.noteJapanese ?? "") : (word?.englishNote ?? call.noteEnglish ?? "")
                if !note.isEmpty { Text(note).inkuFont(11) }
                let example = language == "en" ? (word?.exampleEnglish ?? call.exampleEnglish) : (word?.exampleJapanese ?? call.exampleJapanese)
                if let example, !example.isEmpty { Text(example).inkuFont(11) }
                if let word, word.previewData != nil || word.previewURL != nil {
                    SaijikiPreviewView(svg: nil, imageURL: word.previewURL, imageData: word.previewData, renderer: model.renderer).frame(width: 180, height: 80)
                }
            } else {
                Text(call.text).inkuFont(12, weight: .semibold)
                Text(reason).inkuFont(11)
            }
        }
        .padding(10).frame(maxWidth: 260, alignment: .leading)
        .background(InkuColor.panel, in: RoundedRectangle(cornerRadius: 6))
        .overlay(RoundedRectangle(cornerRadius: 6).stroke(InkuColor.border))
        .shadow(radius: 4)
    }
    private var reason: String {
        switch call.status {
        case "plugin_disabled": return japanese ? "このプラグインは無効です。" : "This plugin is disabled."
        case "plugin_name_mismatch":
            let value = call.suggestion ?? ""
            let name = value.hasPrefix("{") || value.hasPrefix("｛") ? value : (language == "en" ? "{\(value)}" : "｛\(value)｝")
            return japanese ? "\(name) ではありませんか。" : "Did you mean \(name)?"
        case "plugin_name_ambiguous": return (japanese ? "複数の語に一致します：" : "More than one word matches: ") + call.candidates.joined(separator: ", ")
        default: return japanese ? "この名前は登録されていません。" : "This name is not registered."
        }
    }
}
