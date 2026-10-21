import InkuHost
import InkuPersistence
import SwiftUI

/// Web AIRefineModal: the same order, picker, moves and journal. Dismissing leaves the app-owned task running.
@MainActor
public struct AutonomousRefinementView: View {
    @Bindable var model: AppModel
    @Bindable var refinement: AutonomousRefinementModel
    let work: SavedWork?
    @State private var showModels = false
    @Environment(\.dismiss) private var dismiss

    public init(model: AppModel, work: SavedWork?) {
        self.model = model; self.refinement = model.autonomousRefinement; self.work = work
    }

    public var body: some View {
        VStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(copy("aiRefineTitle")).inkuFont(16, weight: .semibold)
                    Spacer()
                    Button { dismiss() } label: { Image(systemName: "xmark") }.accessibilityLabel(model.display.localized("閉じる"))
                }
                Text(copy("aiRefineHelp")).inkuFont(12).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }.padding(20)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if let run = refinement.run {
                        Text(status(run)).fontWeight(.semibold).accessibilityAddTraits(.updatesFrequently)
                        ForEach(Array(run.turns.enumerated()), id: \.offset) { index, turn in
                            ForEach(Array((turn["attempts"].array ?? []).enumerated()), id: \.offset) { _, attempt in
                                attemptRow(turn: index + 1, attempt: attempt)
                            }
                        }
                        if refinement.running { Text(copy("aiRefineGoesOn")).inkuFont(12).foregroundStyle(.secondary) }
                        if let error = run.error { Text(error).foregroundStyle(.red).textSelection(.enabled) }
                    } else { controls }
                    if let error = refinement.errorText {
                        Text(error == "aiRefineKindsError" ? copy(error) : model.display.message(error)).foregroundStyle(.red).textSelection(.enabled)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading).padding(20)
            }
            Divider()
            HStack {
                Spacer()
                Button(model.display.localized("閉じる")) { dismiss() }
                if refinement.running {
                    Button(copy(refinement.stopping ? "aiRefineStopping" : "aiRefineStop")) { Task { await refinement.stop(app: model) } }
                        .disabled(refinement.stopping)
                } else if let run = refinement.run {
                    if run.lastKeptID != nil {
                        Button(copy("aiRefineOpenLast")) { Task { await refinement.openLast(app: model); dismiss() } }
                            .buttonStyle(.borderedProminent).disabled(model.isBusy)
                    }
                } else {
                    Button(copy("aiRefineStartButton")) { Task { await refinement.start(app: model) } }
                        .buttonStyle(.borderedProminent)
                        .disabled(model.isBusy || refinement.source == nil || refinement.source?.svg.isEmpty == true || refinement.enabledKinds.isEmpty || refinement.modelReference.isEmpty)
                }
            }.padding(20)
        }
        .frame(minWidth: 560, idealWidth: 720, minHeight: 440, idealHeight: 600)
        .task { await refinement.initialize(app: model, work: work) }
        .onChange(of: choices) { _, _ in if !refinement.running { refinement.remember(app: model) } }
        .sheet(isPresented: $showModels) {
            BatchModelPickerView(model: model, initialReference: refinement.modelReference, immediateSelection: true,
                title: copy("aiRefineModel"), purpose: "vision",
                onSelection: { reference in try await refinement.selectModel(reference, app: model) })
        }
    }

    private var choices: AutonomousRefineChoices {
        .init(moves: refinement.moves, kinds: AutonomousRefinementModel.kinds.filter(refinement.enabledKinds.contains), note: refinement.note)
    }

    private var controls: some View {
        VStack(alignment: .leading, spacing: 12) {
            if refinement.sourceLocked { Text(copy("aiRefineHeldNote")).inkuFont(12).foregroundStyle(.secondary) }
            Text(copy("aiRefineModel")).inkuFont(12, weight: .semibold)
            Button { showModels = true } label: {
                Label(refinement.modelReference.isEmpty ? model.display.localized("Visionモデルを選択") : refinement.modelReference, systemImage: "eye")
            }
            GroupBox(copy("aiRefineKindsLabel")) {
                HStack(spacing: 20) {
                    ForEach(AutonomousRefinementModel.kinds, id: \.self) { kind in
                        Toggle(kindLabel(kind), isOn: Binding(get: { refinement.enabledKinds.contains(kind) },
                            set: { if $0 { refinement.enabledKinds.insert(kind) } else { refinement.enabledKinds.remove(kind) } }))
                    }
                }.padding(6)
            }
            HStack(spacing: 24) {
                Stepper(copy("aiRefineMovesLabel") + ": \(refinement.moves)", value: $refinement.moves, in: 1...10)
                Toggle(model.display.localized("元のワイルド設定を引き継ぐ"), isOn: $refinement.inheritWild)
                if !refinement.inheritWild { Toggle(model.display.localized("ワイルド"), isOn: $refinement.wild) }
            }
            Text(copy("aiRefineDirectionLabel")).inkuFont(12, weight: .semibold)
            TextField(copy("aiRefineDirectionPlaceholder"), text: $refinement.note, axis: .vertical).lineLimit(3...5)
            Text("\(refinement.note.utf16.count) / 1000").inkuFont(12).foregroundStyle(.secondary)
        }.disabled(model.isBusy)
    }

    private func attemptRow(turn: Int, attempt: ExactJSON) -> some View {
        HStack(alignment: .top, spacing: 10) {
            if let id = attempt["history_id"].string, let child = refinement.children[id] {
                ArtworkThumbnail(work: child, thumbnails: model.thumbnails).frame(width: 56, height: 56)
            } else { Color.clear.frame(width: 56, height: 56) }
            VStack(alignment: .leading, spacing: 2) {
                Text(attemptHeading(turn: turn, attempt: attempt)).inkuFont(12, weight: .semibold)
                if let detail = attempt["sentence"].string ?? attempt["main_law"].string { Text(detail).fixedSize(horizontal: false, vertical: true) }
                if let reason = attempt["reason"].string { Text(reason).inkuFont(12).foregroundStyle(.secondary).textSelection(.enabled) }
            }.frame(maxWidth: .infinity, alignment: .leading)
        }.padding(8).overlay(RoundedRectangle(cornerRadius: 8).stroke(attempt["outcome"].string == "kept" ? Color.accentColor : InkuColor.border))
    }

    private func attemptHeading(turn: Int, attempt: ExactJSON) -> String {
        let outcomes = ["kept": "aiRefineOutcomeKept", "not_visible": "aiRefineOutcomeNotVisible", "unavailable": "aiRefineOutcomeUnavailable", "failed": "aiRefineOutcomeFailed"]
        var text = format("aiRefineTurn", [String(turn)]) + " · " + kindLabel(attempt["kind"].string ?? "") + " · " + copy(outcomes[attempt["outcome"].string ?? ""] ?? "aiRefineOutcomeFailed")
        if let share = attempt["share"].number.flatMap(Double.init) { text += " · " + format("aiRefineShare", [String(format: "%.1f", share * 100)]) }
        return text
    }
    private func status(_ run: AutonomousRun) -> String {
        if refinement.running {
            if refinement.stopping { return copy("aiRefineStopping") }
            if let current = run.current { return format("aiRefineTaking", [current["turn"].number ?? "", kindLabel(current["kind"].string ?? "")]) }
            return model.display.localized("処理中")
        }
        let keys = ["moves_done": "aiRefineEndedMovesDone", "nothing_available": "aiRefineEndedNothingAvailable", "stalled": "aiRefineEndedStalled",
                    "stopped": "aiRefineEndedStopped", "interrupted": "aiRefineEndedInterrupted", "failed": "aiRefineEndedFailed"]
        return copy(keys[run.stopReason ?? ""] ?? "aiRefineEndedFailed") + (run.lastKeptID == nil ? copy("aiRefineNoneKept") : "")
    }
    private func kindLabel(_ kind: String) -> String { copy(kind == "laws" ? "aiRefineKindLaws" : "aiRefineKindJuxtaposition") }
    private func copy(_ key: String) -> String {
        // The Web's process lives in the Server; this process lives in the app.
        model.display.webCopy(key, key).replacingOccurrences(of: "サーバー", with: "アプリ")
            .replacingOccurrences(of: "The Server", with: "The app").replacingOccurrences(of: "the Server", with: "the app")
    }
    private func format(_ key: String, _ arguments: [String]) -> String {
        guard let template = ServerTips.template(key, language: model.display.preferences.language, argumentCount: arguments.count) else { return arguments.joined(separator: " · ") }
        return String(format: template, arguments: arguments.map { $0 as CVarArg })
    }
}
