import InkuHost
import InkuPersistence
import SwiftUI

/// Web `RefinementCompositionFormView.svelte`: the target picture, the switch notice, the seven forms (name and
/// description, the work's own marked "current"), "one option" and "four options", the run's progress and lanes, and
/// the candidate grid with save and discard. The grid and saving are the model comparison's (`RefinementOptionsGrid`,
/// `saveComparisonCandidate`); no comparison logic is copied (SPEC.ja.md 663).
@MainActor
public struct CompositionFormView: View {
    @Bindable var model: AppModel
    @State private var form: CompositionFormModel
    @State private var showModelPicker = false
    @State private var choiceContentHeight: CGFloat = 322
    @FocusState private var thesisFocused: Bool
    @Environment(\.dismiss) private var dismiss
    @Environment(\.inkuWindowSize) private var windowSize
    private let onCommitted: (SavedWork) -> Void

    public init(model: AppModel, work: SavedWork? = nil, onCommitted: @escaping (SavedWork) -> Void = { _ in }) {
        self.model = model
        self.onCommitted = onCommitted
        _form = State(initialValue: CompositionFormModel(work: work))
    }

    public var body: some View {
        Group {
            if let work = form.original {
                RefinementDialog(model: model, title: model.display.webCopy("workActionComposition", "構図と法則を変える"), work: work,
                    closeDisabled: form.running || form.hasUnsaved || model.isBusy, onClose: { dismiss() },
                    targetTitle: model.display.webCopy("refineTargetTitle", "推敲対象"), columnWidth: 388,
                    bottomControls: AnyView(controlsFooter)) {
                    controls
                } options: {
                    RefinementOptionsGrid(model: model, options: form.candidates.map {
                        RefinementOption(id: $0.id, work: $0.work, label: $0.label, selected: $0.selected, saved: $0.savedWork != nil,
                            observation: $0.prepared)
                    }, previewID: form.previewID, maxColumns: 4, busy: form.running || model.isBusy,
                        placeholder: model.display.webCopy("refineCandidatePlaceholder", "候補はここに並びます。左の要素を選んで「1案を作る」または「4案を作る」を押してください。"),
                        errors: form.failures + [form.errorText].compactMap { $0 }, status: form.status,
                        compactPlaceholder: true,
                        targetWork: work, targetComposition: form.currentComposition,
                        onPreview: { form.preview($0) }, onSelect: { form.selectCandidate($0, selected: $1) },
                        onDiscard: { form.discardCandidates(); dismiss() },
                        onSave: { Task {
                            if await form.saveSelected(app: model) {
                                if let latest = form.candidates.compactMap(\.savedWork).last { onCommitted(latest) }
                                dismiss()
                            }
                        } })
                }
            } else {
                VStack {
                    if let error = form.errorText { Text(model.display.message(error)).foregroundStyle(.red) }
                    else { ProgressView() }
                    Button(model.display.localized("閉じる")) { dismiss() }
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .task { await form.initialize(app: model) }
        .sheet(isPresented: $showModelPicker) {
            BatchModelPickerView(model: model, initialReference: form.modelReference,
                onSelection: { form.modelReference = $0 })
                .environment(\.inkuWindowSize, windowSize).inkuDialogFrame(.modelSelection)
        }
        .interactiveDismissDisabled(form.running || form.hasUnsaved || model.isBusy)
        .onDisappear { Task { await form.stop(app: model); form.discardCandidates() } }
    }

    private var controls: some View {
        @Bindable var form = form
        let language = model.display.preferences.language
        let isThesis = form.change == .authorThesis || form.change == .proposedTheses
        let groups = Dictionary(grouping: CompositionNames.mainLawIDs) { CompositionNames.lawFamily($0, language: language) }
        let families = CompositionNames.mainLawIDs.reduce(into: [String]()) { result, law in
            let family = CompositionNames.lawFamily(law, language: language)
            if !result.contains(family) { result.append(family) }
        }
        return VStack(alignment: .leading, spacing: 12) {
            if form.switchesComposition {
                Text(model.display.webCopy("compositionFormSwitchNotice", "言葉で描く＋構図ありに切り替えて描きます")).inkuFont(12)
            }
            if form.sourceIsLocked {
                Text(model.display.tooltip("編集した指示書で確定した作品です。記述を読み直す操作は使えません。", serverKey: "descriptionLockedReason"))
                    .inkuFont(12).foregroundStyle(.secondary)
            }
            Text(model.display.webCopy("compositionWhatToChange", "何を変えるか")).inkuFont(12, weight: .semibold)
            HStack(spacing: 0) {
                choiceButton(model.display.webCopy("compositionFormTerm", "画の型"), selected: form.change == .form) { form.change = .form }
                choiceButton(model.display.webCopy("compositionMainLawTerm", "主の法則"), selected: form.change == .mainLaw) { form.change = .mainLaw }
                choiceButton(model.display.webCopy("compositionThesisLabel", "命題"), selected: isThesis) { if !isThesis { form.change = .authorThesis } }
            }.padding(2).background(InkuColor.bg, in: RoundedRectangle(cornerRadius: 6))
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(InkuColor.border2)).disabled(form.running || model.isBusy)
            ScrollView {
                VStack(alignment: .leading, spacing: 7) {
                    if form.change == .form {
                        ForEach(Array(CompositionForm.all.enumerated()), id: \.element) { index, id in formOption(id, index: index) }
                    } else if form.change == .mainLaw {
                        ForEach(families, id: \.self) { family in
                            HStack(alignment: .top, spacing: 6) {
                                Text(family).inkuFont(11).foregroundStyle(.secondary).frame(width: 54, alignment: .leading)
                                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 4), count: 4), spacing: 4) {
                                    ForEach(groups[family] ?? [], id: \.self) { law in lawOption(law) }
                                }
                            }
                        }
                    } else {
                        thesisChoice(.authorThesis, title: "compositionThesisWrite", fallback: "自分で命題を書く", note: "compositionThesisWriteNote")
                        TextEditor(text: Binding(get: { form.authorThesis }, set: { text in
                            form.authorThesis = ThesisInput.limited(text)
                        })).focused($thesisFocused).onChange(of: thesisFocused) { _, focused in
                            if focused { form.change = .authorThesis }
                        }.frame(height: 72).overlay(Rectangle().stroke(InkuColor.border2))
                            .disabled(form.running || model.isBusy)
                        thesisChoice(.proposedTheses, title: "compositionThesisPropose", fallback: "AI に別の命題を出させる", note: "compositionThesisProposeNote")
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
                    .fixedSize(horizontal: false, vertical: true)
                    .background {
                        GeometryReader { geometry in
                            Color.clear
                                .onAppear { choiceContentHeight = geometry.size.height }
                                .onChange(of: geometry.size.height) { _, height in choiceContentHeight = height }
                        }
                    }
            }.frame(height: min(322, max(0, choiceContentHeight)))
            if form.change == .mainLaw {
                HStack(spacing: 0) {
                    Rectangle().fill(Color.accentColor).frame(width: 2)
                    Text(CompositionNames.lawSummary(form.selectedMainLaw, language: language)).inkuFont(12).foregroundStyle(.secondary).padding(.horizontal, 10).padding(.vertical, 8).frame(maxWidth: .infinity, alignment: .leading)
                }.fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var controlsFooter: some View {
        let isThesis = form.change == .authorThesis || form.change == .proposedTheses
        return VStack(alignment: .leading, spacing: 8) {
            let keeps = isThesis ? "compositionThesisKeeps" : form.change == .mainLaw ? "compositionMainLawKeeps" : "compositionFormKeeps"
            let redecides = isThesis ? "compositionThesisRedecides" : form.change == .mainLaw ? "compositionMainLawRedecides" : "compositionFormRedecides"
            let keptText = form.change == .mainLaw ? form.currentForm.map {
                model.display.webCopyFormat(keeps, "記述・読み・記述が名指す物・画の型（%@）", CompositionNames.formName($0, language: model.display.preferences.language))
            } ?? model.display.label("記述・読み・記述が名指す物", "The description, the reading and the things the description names") : model.display.webCopy(keeps, "記述・読み・記述が名指す物")
            let redoneText = form.change == .mainLaw ? (form.currentForm == nil
                ? model.display.label("命題・画の型・ほかの法則・物の描き方・配色", "The thesis, the form, the other laws, how the things are drawn and the colors")
                : (ServerTips.template(redecides, language: model.display.preferences.language, argumentCount: 0) ?? model.display.label("命題・ほかの法則・物の描き方・配色", "The thesis, the other laws, how the things are drawn and the colors")))
                : model.display.webCopy(redecides, "画の型・法則・配色")
            Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 4) {
                GridRow { Text(model.display.webCopy("compositionKeepsTerm", "変わらないもの")).foregroundStyle(.tertiary); Text(keptText) }
                GridRow { Text(model.display.webCopy("compositionRedecidesTerm", "決め直すもの")).foregroundStyle(.tertiary); Text(redoneText) }
            }.inkuFont(12).foregroundStyle(.secondary).padding(10).frame(maxWidth: .infinity, alignment: .leading)
                .background(InkuColor.bg2).overlay(RoundedRectangle(cornerRadius: 6).stroke(InkuColor.border))
            DrawingConditionRow(display: model.display, label: model.display.webCopy("modelButton", "モデル"),
                value: DrawPresentation.modelReference(form.modelReference, empty: model.display.localized("選択してください")),
                help: model.display.tooltip("次の作品の描画モデルを選びます。", serverKey: "tooltipInputModel"),
                showsPlan: form.modelReference.hasPrefix("chatgpt:")) { showModelPicker = true }
                .disabled(form.running || model.isBusy)
            VStack(alignment: .leading, spacing: 8) {
                Button {
                    Task { await form.generate(app: model, count: 1) }
                } label: { Label(model.display.webCopy("refineSingleButton", "1案を作る"), systemImage: "play.fill").frame(maxWidth: .infinity) }
                    .buttonStyle(.borderedProminent).controlSize(.large).disabled(!form.canGenerate || model.isBusy || !model.refinementModelAvailable(form.modelReference) || form.change == .proposedTheses || (form.change == .authorThesis && (form.authorThesis.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || form.authorThesis.count > 400)))
                Button {
                    Task { await form.generate(app: model, count: 4) }
                } label: { Label(model.display.webCopy("variationGridDefault", "4案を作る"), systemImage: "play.fill").frame(maxWidth: .infinity) }
                    .buttonStyle(.borderedProminent).controlSize(.large).disabled(!form.canGenerate || model.isBusy || !model.refinementModelAvailable(form.modelReference) || form.change == .authorThesis)
            }
            if form.running {
                RunStatusView(display: model.display, label: form.status, stopping: form.stopping,
                    onStop: { Task { await form.stop(app: model) } }, journalModel: model, journalActive: !form.saving) {
                    if !form.saving { ProviderProgressView(model: model, embedded: true) }
                }
                if !form.saving {
                    VariationLanesView(display: model.display, states: form.laneStates.map {
                        switch $0 { case .waiting: .waiting; case .running: .running; case .done: .done }
                    }, labels: form.laneLabels, named: false)
                }
            }
        }
    }

    private func choiceButton(_ title: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) { Text(title).inkuFont(12, weight: selected ? .semibold : .regular).frame(maxWidth: .infinity).padding(.vertical, 5).background(selected ? InkuColor.bg2 : .clear, in: RoundedRectangle(cornerRadius: 4)) }
            .buttonStyle(.plain)
            .accessibilityAddTraits(selected ? [.isSelected] : [])
    }

    private func thesisChoice(_ choice: CompositionFormModel.Change, title: String, fallback: String, note: String) -> some View {
        Button { form.change = choice } label: {
            HStack(alignment: .top, spacing: 6) {
                Image(systemName: form.change == choice ? "largecircle.fill.circle" : "circle")
                VStack(alignment: .leading) {
                    Text(model.display.webCopy(title, fallback)).inkuFont(12, weight: .semibold)
                    Text(model.display.webCopy(note, "")).inkuFont(11).foregroundStyle(.secondary)
                }
            }.padding(.horizontal, 8).padding(.vertical, 5).frame(maxWidth: .infinity, alignment: .leading)
                .background(form.change == choice ? Color.accentColor.opacity(0.13) : .clear, in: RoundedRectangle(cornerRadius: 6))
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(form.change == choice ? Color.accentColor : .clear))
        }.buttonStyle(.plain).disabled(form.running || model.isBusy)
    }

    private func lawOption(_ law: String) -> some View {
        let selected = form.selectedMainLaw == law
        return Button { form.selectedMainLaw = law } label: {
            VStack(spacing: 3) {
                CompositionFigure(id: law).frame(width: 28, height: 28)
                Text(CompositionNames.lawName(law, language: model.display.preferences.language)).inkuFont(11).lineLimit(2)
            }.frame(maxWidth: .infinity, minHeight: 64)
                .background(selected ? Color.accentColor.opacity(0.13) : .clear, in: RoundedRectangle(cornerRadius: 5))
                .overlay(RoundedRectangle(cornerRadius: 5).stroke(selected ? Color.accentColor : InkuColor.border))
                .overlay(alignment: .topTrailing) { if law == form.currentMainLaw { Text(model.display.webCopy("compositionTargetNow", "今")).inkuFont(10).padding(3) } }
        }.buttonStyle(.plain).disabled(form.running || model.isBusy)
            .inkuTooltip(CompositionNames.lawSummary(law, language: model.display.preferences.language))
            .accessibilityAddTraits(selected ? [.isSelected] : [])
    }

    /// One radio row: the form's name (with "current" on the work's own form) over its description.
    private func formOption(_ id: String, index: Int) -> some View {
        let selected = form.selectedForm == id
        let name = model.display.webCopy("compositionFormNames.\(index)", id)
        let current = id == form.currentForm ? " (" + model.display.webCopy("compositionFormCurrent", "今の形") + ")" : ""
        return Button { form.selectedForm = id } label: {
            HStack(alignment: .top, spacing: 6) {
                Image(systemName: selected ? "largecircle.fill.circle" : "circle").foregroundStyle(selected ? Color.accentColor : .secondary)
                CompositionFigure(id: id).frame(width: 28, height: 28)
                VStack(alignment: .leading, spacing: 2) {
                    Text(name + current).inkuFont(12, weight: .semibold)
                    Text(model.display.webCopy("compositionFormDescriptions.\(index)", "")).inkuFont(12).foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
            }.padding(.horizontal, 8).padding(.vertical, 5).frame(maxWidth: .infinity, alignment: .leading)
                .background(selected ? Color.accentColor.opacity(0.13) : .clear, in: RoundedRectangle(cornerRadius: 6))
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(selected ? Color.accentColor : .clear)).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(form.running || model.isBusy)
        .accessibilityAddTraits(selected ? [.isSelected] : [])
    }
}
