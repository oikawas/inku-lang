import InkuHost
import InkuPersistence
import SwiftUI
#if os(macOS)
import AppKit
#endif

@MainActor
struct CreationWorkInfoView: View {
    @Bindable var model: AppModel
    @Environment(\.dismiss) private var dismiss
    private let work: SavedWork?
    @State private var information: SavedGenerationInformation?
    @State private var loading = true
    @State private var loadError: String?
    @State private var tab = "details"
    @State private var expandedPrompts: Set<String> = []
    @State private var copied: String?

    /// Set when the view is the drawer over the canvas rather than a sheet.
    private let onClose: (() -> Void)?

    init(model: AppModel, work: SavedWork? = nil, onClose: (() -> Void)? = nil) {
        self.model = model
        self.work = work ?? model.displayedWork
        self.onClose = onClose
    }

    private func close() {
        if let onClose { onClose() } else { dismiss() }
    }

    var body: some View {
        VStack(spacing: 14) {
            HStack {
                Text(model.display.localized("生成情報")).inkuFont(13, weight: .semibold)
                Spacer()
                if loading { ProgressView().controlSize(.small) }
                Button(model.display.localized("閉じる")) { close() }.keyboardShortcut(.cancelAction)
                    .buttonStyle(InkuGhostButtonStyle())
                    .help(model.display.tooltip("閉じる"))
            }
            if let work {
                Text(LibraryWorkPresentation.title(work, untitled: model.display.localized("無題")))
                    .inkuFont(13).lineLimit(2).frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled)
                // CanvasGenerationInfo `.generation-info-tabs`: underline text tabs over the page.
                VStack(spacing: 0) {
                    HStack(spacing: 0) {
                        InkuTextTab(title: model.display.localized("詳細"), selected: tab == "details", compact: true) { tab = "details" }
                        InkuTextTab(title: copy("tabPrompts", "プロンプト"), selected: tab == "prompts", compact: true) { tab = "prompts" }
                        InkuTextTab(title: copy("tabScore", "Score (JSON)"), selected: tab == "score", compact: true) { tab = "score" }
                        Spacer(minLength: 0)
                    }
                    .overlay(alignment: .bottom) { Rectangle().fill(InkuColor.border).frame(height: 1) }
                    Group {
                        switch tab {
                        case "prompts": prompts(work)
                        case "score": score(work)
                        default: details(work)
                        }
                    }
                    .padding(.top, 10)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                }
            } else {
                ContentUnavailableView(model.display.localized("作品がありません"), systemImage: "doc")
            }
            if let loadError {
                HStack(alignment: .top) {
                    Text(loadError).foregroundStyle(.red).textSelection(.enabled)
                    Spacer()
                    Button(model.display.localized("再読込")) { Task { await load() } }.disabled(loading)
                        .help(model.display.tooltip("作品の保存記録を再読み込みします。"))
                }.inkuFont(13)
            }
        }
        .padding(onClose == nil ? 20 : 16)
        .frame(minWidth: onClose == nil ? 660 : nil, idealWidth: onClose == nil ? 760 : nil,
               minHeight: onClose == nil ? 520 : nil, idealHeight: onClose == nil ? 740 : nil)
        .task { await load() }
    }

    private var absent: String { copy("historyVersionNotRecorded", "記録なし") }
    private var provenance: GenerationProvenance? { information?.presentation?.provenance }

    private func details(_ work: SavedWork) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if work.sketchGrain != nil || work.sketchState != nil {
                    group(copy("sketchLabel", "写生")) {
                        if let grain = work.sketchGrain { row(copy("sketchGrainLabel", "区切り"), grain, hint: "provenanceHintSketchGrain") }
                        row(copy("provenanceLabelSketchRecord", "写生の記録"), work.sketchState, hint: "provenanceHintSketchRecord")
                    }
                }
                group(copy("provenanceSectionInterpretation", "解釈")) {
                    row("Stage 1 (" + copy("provenanceSectionInterpretation", "解釈") + ")", work.stage1Model, hint: "provenanceHintStage1Model")
                    row(model.display.localized("Stage 1 言語"), languageName(work.instructionLangResolved), hint: "provenanceHintStage1Lang")
                    row(copy("provenanceLabelLangRequested", "要求した言語"), languageName(work.instructionLangRequested), hint: "provenanceHintLangRequested")
                    row(model.display.localized("解釈 seed"), work.interpretationSeed, hint: "provenanceHintInterpretationSeed")
                    if let reason = work.interpretFallback, !reason.isEmpty {
                        row(copy("provenanceLabelInterpretFallback", "解釈フォールバック"), reason, hint: "provenanceHintInterpretFallback")
                    }
                    row(copy("provenanceLabelComposeFallback", "作曲フォールバック"), composeFallback(work), hint: "provenanceHintComposeFallback")
                }
                group(copy("provenanceSectionPerformance", "演奏")) {
                    row("Stage 2 (" + model.display.localized("描画") + ")", work.stage2Model, hint: "provenanceHintStage2Model")
                    row(model.display.localized("Stage 2 言語"), languageName(work.instructionLangResolved), hint: "provenanceHintStage2Lang")
                    if let amplitude = work.variationAmplitude { row(copy("provenanceLabelVariation", "変奏"), amplitude, hint: "provenanceHintVariation") }
                    if let seed = work.variationSeed { row(copy("provenanceLabelVariationSeed", "変奏 seed"), seed, hint: "provenanceHintVariationSeed") }
                    row(model.display.localized("配置 seed"), work.compositionSeed, hint: "provenanceHintCompositionSeed")
                    row("render seed", work.renderSeed, hint: "provenanceHintRenderSeed")
                    row(copy("provenanceLabelSeedText", "種テキスト"), work.seedText, hint: "provenanceHintSeedText")
                    row(copy("provenanceLabelWild", "暴れる"), work.renderWild.map { copy($0 ? "provenanceWildOn" : "provenanceWildOff", $0 ? "あり" : "なし") }, hint: "provenanceHintWild")
                    row(model.display.localized("色カタログ"), work.renderColorCatalogName ?? work.renderColorCatalogID ?? work.catalogID, hint: "provenanceHintCatalog")
                    colorMap(work)
                    row(model.display.localized("キャンバス"), work.renderCanvasAspect ?? work.renderCanvasAspectID, hint: "provenanceHintCanvas")
                    row(copy("provenanceLabelCanvasRatio", "キャンバスの比率"), work.renderCanvasAspectRatio.map { String(format: "%.3f", $0) }, hint: "provenanceHintCanvasRatio")
                    let weight = SavedSVGWeight(work.svg)
                    row(model.display.localized("SVG サイズ"), ByteCountFormatter.string(fromByteCount: Int64(weight.bytes), countStyle: .file), hint: "provenanceHintSvgSize")
                    row(model.display.localized("SVG オブジェクト数"), weight.objects.formatted(), hint: "provenanceHintSvgObjects")
                    row(model.display.localized("SVG 点数"), weight.points.formatted(), hint: "provenanceHintSvgPoints")
                }
                group(copy("provenanceSectionIdentity", "同一性")) {
                    hashRow("rh", work.renderHash, hint: "provenanceHintRenderHash", copyable: true)
                    hashRow("dh", work.descriptionHash, hint: "provenanceHintDescriptionHash", copyable: false)
                    row("Render engine version", work.renderEngineVersion, hint: "provenanceHintRenderEngine")
                    row(copy("provenanceLabelDdlSpec", "DDL version"), provenance?.ddlVersion, hint: "provenanceHintDdlSpec")
                    row(copy("provenanceLabelTransformLayer", "DDL engine version"), provenance?.ddlEngineVersion, hint: "provenanceHintTransformLayer")
                    row(copy("provenanceLabelStage1PromptDigest", "Stage 1 プロンプト digest"), information?.prompt("generate_normalized_ddl")?["prompt_digest"].string, hint: "provenanceHintStage1PromptDigest")
                    row(copy("provenanceLabelStage1PromptBaseDigest", "Stage 1 プロンプト基底 digest"), nil, hint: "provenanceHintStage1PromptBaseDigest")
                    row(copy("provenanceLabelStage2PromptDigest", "Stage 2 プロンプト digest"), information?.prompt("complete_visible_ddl_holes")?["prompt_digest"].string, hint: "provenanceHintStage2PromptDigest")
                    row("Build", provenance?.build, hint: "provenanceHintBuild")
                }
                group(copy("provenanceSectionOrigin", "由来")) {
                    row(copy("provenanceLabelGeneration", "世代"), information?.generation.map(String.init), hint: "provenanceHintGeneration")
                    row(copy("provenanceLabelDerivation", "派生"), information.map { derivation($0.edge?.derivationKind) }, hint: "provenanceHintDerivation")
                    if let run = provenance?.batchRunID { row(copy("provenanceLabelBatchRun", "バッチ実行 ID"), run, hint: "provenanceHintBatchRun") }
                    if let line = provenance?.batchLineNumber { row(copy("provenanceLabelBatchLine", "バッチ行番号"), String(line), hint: "provenanceHintBatchLine") }
                    if let note = information?.annotation.note, !note.isEmpty { row(copy("provenanceLabelComment", "コメント"), note, hint: "provenanceHintComment") }
                }
                group(copy("provenanceSectionRun", "実行")) {
                    row(model.display.localized("作成日"), Date(timeIntervalSince1970: Double(work.at) / 1000).formatted(date: .numeric, time: .standard), hint: "provenanceHintCreated")
                    row(model.display.localized("処理時間"), work.elapsedMS.map { $0 > 0 ? String(format: "%.1fs", Double($0) / 1000) : copy("provenanceElapsedNotRecorded", "記録なし") }, hint: "provenanceHintElapsed")
                    row("tokens in / out", (information?.tokenTotal(input: true) ?? absent) + " / " + (information?.tokenTotal(input: false) ?? absent), hint: "provenanceHintTokens")
                    row(copy("provenanceLabelUiLang", "UI 言語"), languageName(provenance?.uiLanguage), hint: "provenanceHintUiLang")
                    if let information { ProviderObservationView(model: model, metrics: information.metrics, workID: work.id) }
                }
            }.padding(14).textSelection(.enabled)
        }
    }

    private func prompts(_ work: SavedWork) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                promptText(copy("promptStage1Input", "Stage 1 ユーザー入力"), work.effectiveSourceText, id: "stage1-input")
                systemPrompt("generate_normalized_ddl", title: copy("promptStage1System", "Stage 1 システムプロンプト"))
                if let ddl = work.ddl, !ddl.isEmpty { promptText(copy("promptStage2Input", "Stage 2 ユーザー入力 (正規化DDL)"), ddl, id: "stage2-input") }
                systemPrompt("complete_visible_ddl_holes", title: copy("promptStage2System", "Stage 2 システムプロンプト"))
            }.padding(14)
        }
    }

    private func score(_ work: SavedWork) -> some View {
        VStack(spacing: 0) {
            HStack { Spacer(); copyButton(prettyScore(work.score), id: "score") }.padding(8)
            Divider()
            ScrollView([.horizontal, .vertical]) {
                let lines = prettyScore(work.score).components(separatedBy: "\n")
                HStack(alignment: .top, spacing: 12) {
                    Text((1...max(1, lines.count)).map(String.init).joined(separator: "\n")).foregroundStyle(.secondary)
                    Text(lines.joined(separator: "\n")).textSelection(.enabled)
                }.inkuFont(12, design: .monospaced).padding(12).frame(maxWidth: .infinity, alignment: .leading)
            }
        }.background(.background)
    }

    private func group<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 10, content: content).frame(maxWidth: .infinity, alignment: .leading).padding(6)
        } label: { Text(title).inkuFont(12, weight: .semibold).foregroundStyle(.secondary) }
    }

    private func row(_ label: String, _ value: String?, hint: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 16) {
            Text(label).foregroundStyle(.secondary).frame(width: 190, alignment: .leading)
                .help(model.display.tooltip(label, serverKey: hint))
            Text(value.flatMap { $0.isEmpty ? nil : $0 } ?? absent).frame(maxWidth: .infinity, alignment: .leading)
        }.inkuFont(13)
    }

    private func hashRow(_ label: String, _ hash: String?, hint: String, copyable: Bool) -> some View {
        HStack(alignment: .top) {
            row(SavedWorkFacts.hashLabel(label, value: hash), hash.map(SavedWorkFacts.hashDigest), hint: hint)
            if copyable, let hash { copyButton(SavedWorkFacts.hashDigest(hash), id: "hash") }
        }
    }

    @ViewBuilder private func colorMap(_ work: SavedWork) -> some View {
        if let raw = work.renderColorMap, let fields = try? ExactJSON(data: Data(raw.utf8)).object, !fields.isEmpty {
            HStack(alignment: .top, spacing: 16) {
                Text(copy("provenanceLabelColorMap", "色の対応")).foregroundStyle(.secondary).frame(width: 190, alignment: .leading)
                    .help(model.display.tooltip("色の対応", serverKey: "provenanceHintColorMap"))
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 110), alignment: .leading)], alignment: .leading, spacing: 6) {
                    ForEach(fields.keys.sorted(), id: \.self) { key in
                        let code = fields[key]?.string ?? ""
                        HStack(spacing: 5) {
                            RoundedRectangle(cornerRadius: 2).fill(swatch(code)).frame(width: 12, height: 12)
                            Text(key).inkuFont(12)
                        }.help(model.display.tooltipValue(code))
                    }
                }
            }
        }
    }

    private func promptText(_ title: String, _ text: String, id: String, collapsible: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(title).inkuFont(12, weight: .semibold).foregroundStyle(.secondary)
                Spacer()
                if collapsible {
                    Button(copy(expandedPrompts.contains(id) ? "promptCollapse" : "promptExpand", expandedPrompts.contains(id) ? "折りたたむ" : "展開")) {
                        if !expandedPrompts.insert(id).inserted { expandedPrompts.remove(id) }
                    }.buttonStyle(.borderless).help(model.display.tooltip("プロンプトの表示を切り替えます。"))
                }
                copyButton(text, id: id)
            }
            ScrollView {
                Text(text).inkuFont(12, design: .monospaced).textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(10)
            }.frame(height: collapsible && !expandedPrompts.contains(id) ? 70 : 180)
                .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 6))
        }
    }

    @ViewBuilder private func systemPrompt(_ action: String, title: String) -> some View {
        if let system = information?.prompt(action)?["system"].string {
            promptText(title, system, id: action, collapsible: true)
        } else {
            VStack(alignment: .leading, spacing: 6) {
                Text(title).inkuFont(12, weight: .semibold).foregroundStyle(.secondary)
                Text(loading ? copy("promptLoading", "読み込み中…") : loadError != nil ? copy("promptSystemUnavailable", "読み込めませんでした。")
                    : information?.prompts == nil ? copy("promptSystemNotRecorded", "この作品は、送った内容を記録する前に描かれたため、記録がありません。")
                    : copy("promptSystemNotSent", "この作品では、このStageはモデルを呼んでいません。"))
                    .inkuFont(13).foregroundStyle(.secondary)
            }
        }
    }

    private func copyButton(_ text: String, id: String) -> some View {
        Button {
            #if os(macOS)
            NSPasteboard.general.clearContents(); NSPasteboard.general.setString(text, forType: .string)
            #endif
            copied = id
        } label: { Label(copy(copied == id ? "promptCopied" : "promptCopy", copied == id ? "コピーしました" : "コピー"), systemImage: "doc.on.doc") }
            .buttonStyle(.borderless).inkuFont(12)
            .help(model.display.tooltip("内容をコピーします。", serverKey: "promptCopy"))
    }

    private func copy(_ key: String, _ fallback: String) -> String {
        model.productReference?.localized(language: model.display.preferences.language)?.texts[key] ?? model.display.localized(fallback)
    }
    private func languageName(_ value: String?) -> String? {
        switch value { case "ja": model.display.localized("日本語"); case "en": model.display.localized("英語"); case "auto": model.display.localized("自動"); default: value }
    }
    private func composeFallback(_ work: SavedWork) -> String {
        guard let raw = work.composeFallback?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else { return absent }
        return raw == "none" ? model.display.localized("なし") : raw
    }
    private func derivation(_ kind: String?) -> String {
        let titles = ["touch_change": "タッチ", "layout_change": "構図", "catalog_change": "色", "reinterpretation": "解釈",
            "model_comparison": "モデル", "language_comparison": "言語", "ddl_edit": "DDL編集", "description_edit": "記述編集",
            "replay": "再描画", "canvas_aspect_change": "キャンバス変更", "variation": "変奏（旧）", "sketch_grain_change": "写生の有無"]
        guard let kind, kind != "new" else { return model.display.localized("起点") }
        return model.display.localized(titles[kind] ?? kind)
    }
    private func swatch(_ code: String) -> Color {
        let hex = code.hasPrefix("#") ? String(code.dropFirst()) : code
        guard hex.count == 6, let value = UInt32(hex, radix: 16) else { return .clear }
        return Color(red: Double((value >> 16) & 255) / 255, green: Double((value >> 8) & 255) / 255, blue: Double(value & 255) / 255)
    }
    private func prettyScore(_ raw: String) -> String {
        guard let data = raw.data(using: .utf8), let json = try? JSONSerialization.jsonObject(with: data),
              let pretty = try? JSONSerialization.data(withJSONObject: json, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]) else { return raw }
        return String(decoding: pretty, as: UTF8.self)
    }
    private func load() async {
        guard let work else { loading = false; return }
        loading = true; loadError = nil
        defer { loading = false }
        do { information = try await model.savedGenerationInformation(work: work) }
        catch is CancellationError { }
        catch { loadError = error.localizedDescription }
    }
}
