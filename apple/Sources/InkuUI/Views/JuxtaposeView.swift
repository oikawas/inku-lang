import InkuHost
import InkuPersistence
import SwiftUI

/// Web `JuxtaposeDialog.svelte`: the description, the Vision model that picks, the four sentences with why, and the
/// description with the chosen one after it. Opening sends nothing; drawing makes the work's child.
@MainActor
public struct JuxtaposeView: View {
    @Bindable private var model: AppModel
    @State private var juxtapose: JuxtaposeModel
    @State private var showModels = false
    @Environment(\.dismiss) private var dismiss
    private let onCommitted: @MainActor () -> Void

    public init(model: AppModel, work: SavedWork, onCommitted: @escaping @MainActor () -> Void = {}) {
        self.model = model
        self.onCommitted = onCommitted
        _juxtapose = State(initialValue: JuxtaposeModel(work: work))
    }

    public var body: some View {
        VStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(model.display.webCopy("juxtaposeTitle", "取り合わせ")).inkuFont(16, weight: .semibold)
                    Spacer()
                    Button { dismiss() } label: { Image(systemName: "xmark") }
                        .accessibilityLabel(model.display.localized("閉じる")).disabled(juxtapose.busy)
                }
                Text(model.display.webCopy("juxtaposeHelp",
                    "ほかの作品の記述から、AIが一文を4つ選びます。1つを選ぶと、今の記述の後ろに足して、選択した作品の子を描画します。"))
                    .inkuFont(12).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }.frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 20).padding(.top, 18).padding(.bottom, 14)
            Divider()
            ScrollView { content.padding(.horizontal, 20).padding(.vertical, 18) }
            Divider()
            footer.padding(.horizontal, 20).padding(.top, 12).padding(.bottom, 16)
        }
        #if os(macOS)
        .frame(minWidth: 560, idealWidth: 780, minHeight: 380, idealHeight: 560)
        #endif
        .task { await juxtapose.initialize(app: model) }
        .sheet(isPresented: $showModels) {
            BatchModelPickerView(model: model, initialReference: juxtapose.modelReference, immediateSelection: true,
                                 title: model.display.webCopy("juxtaposeModel", "一文を選ぶVisionモデル"), purpose: "vision",
                                 onSelection: { reference in try await juxtapose.selectModel(reference, app: model) })
        }
        .interactiveDismissDisabled(juxtapose.busy || model.isBusy)
        .onDisappear { Task { await juxtapose.stop(app: model) } }
    }

    private var content: some View {
        VStack(alignment: .leading, spacing: 8) {
            label(model.display.webCopy("inputSectionLabel", "記述"))
            textBox(juxtapose.work.effectiveSourceText)
            label(model.display.webCopy("juxtaposeModel", "一文を選ぶVisionモデル"))
            Button { showModels = true } label: {
                Label(juxtapose.modelReference.isEmpty ? model.display.localized("Visionモデルを選択") : juxtapose.modelReference,
                      systemImage: "eye")
            }.disabled(juxtapose.busy)
            if let result = juxtapose.result { choices(result) }
            if let choice = juxtapose.choice {
                label(model.display.webCopy("juxtaposeJoined", "足した後の記述"))
                textBox(choice.joined, emphasized: true)
            }
            if let error = juxtapose.errorText {
                Text(model.display.message(error)).inkuFont(12).foregroundStyle(.red).textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    private func choices(_ result: Juxtaposition.Result) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            label(model.display.webCopy("juxtaposeChoices", "{count}文から選んだ4つ")
                .replacingOccurrences(of: "{count}", with: String(result.candidates)))
            ForEach(Array(result.choices.enumerated()), id: \.element.sentence) { index, item in
                Button { juxtapose.chosen = index } label: {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Image(systemName: juxtapose.chosen == index ? "largecircle.fill.circle" : "circle")
                            .foregroundStyle(juxtapose.chosen == index ? Color.accentColor : .secondary)
                        Grid(alignment: .leadingFirstTextBaseline, horizontalSpacing: 8, verticalSpacing: 2) {
                            GridRow {
                                Text(model.display.webCopy("juxtaposeSentenceLabel", "選択文")).inkuFont(12).foregroundStyle(.tertiary)
                                Text(item.sentence).fixedSize(horizontal: false, vertical: true)
                            }
                            GridRow {
                                Text(model.display.webCopy("juxtaposeReasonLabel", "選択理由")).inkuFont(12).foregroundStyle(.tertiary)
                                Text(item.reason).inkuFont(12).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 6).padding(.horizontal, 8)
                        .background(juxtapose.chosen == index ? InkuColor.bg2 : Color.clear, in: RoundedRectangle(cornerRadius: 6))
                        .contentShape(Rectangle())
                }.buttonStyle(.plain)
                    .accessibilityAddTraits(juxtapose.chosen == index ? .isSelected : [])
            }
        }.padding(.horizontal, 12).padding(.vertical, 10)
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(InkuColor.border))
            .disabled(juxtapose.busy)
    }

    private var footer: some View {
        HStack {
            if juxtapose.busy {
                Spacer()
                RunStatusView(display: model.display,
                              label: juxtapose.asking ? model.display.webCopy("juxtaposeAsking", "一文を選んでいます…")
                                  : (model.isBusy ? model.status : "生成の準備中"),
                              variant: .inline, stopping: juxtapose.stopping,
                              onStop: { Task { await juxtapose.stop(app: model) } }) {
                    if let startedAt = juxtapose.startedAt {
                        TimelineView(.periodic(from: startedAt, by: 0.1)) { context in
                            Text(model.display.webCopyFormat("runStatusElapsed", "経過 %@s",
                                 String(format: "%.1f", max(0, context.date.timeIntervalSince(startedAt)))))
                                .inkuFont(11).foregroundStyle(.secondary).monospacedDigit()
                        }
                    }
                }
            } else {
                Spacer()
                Button(model.display.webCopy("pipelineCancel", "キャンセル")) { dismiss() }
                    .disabled(model.isBusy).keyboardShortcut(.cancelAction)
                if juxtapose.result != nil {
                    Button(model.display.webCopy("juxtaposeAskAgain", "選び直す")) { Task { await juxtapose.ask(app: model) } }
                        .disabled(juxtapose.modelReference.isEmpty || model.isBusy)
                    Button(model.display.webCopy("juxtaposeDraw", "この記述で描く")) {
                        Task { if await juxtapose.draw(app: model) { onCommitted(); dismiss() } }
                    }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                        .disabled(juxtapose.choice == nil || model.isBusy || model.isPreview || !model.hasNextDrawingModel)
                } else {
                    // Nothing can be drawn before four sentences are shown, so asking is the one action.
                    Button(model.display.webCopy("juxtaposeAsk", "一文を選ばせる")) { Task { await juxtapose.ask(app: model) } }
                        .buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                        .disabled(juxtapose.modelReference.isEmpty || model.isBusy)
                }
            }
        }
    }

    private func label(_ text: String) -> some View {
        Text(text).inkuFont(12, weight: .semibold).foregroundStyle(.secondary)
    }

    private func textBox(_ text: String, emphasized: Bool = false) -> some View {
        Text(text).frame(maxWidth: .infinity, alignment: .leading).fixedSize(horizontal: false, vertical: true)
            .textSelection(.enabled).lineSpacing(3)
            .padding(.horizontal, 10).padding(.vertical, 8)
            .background(InkuColor.bg, in: RoundedRectangle(cornerRadius: 6))
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(emphasized ? InkuColor.border2 : InkuColor.border))
    }
}
