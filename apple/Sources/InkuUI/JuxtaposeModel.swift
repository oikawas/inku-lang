import Foundation
import InkuHost
import InkuPersistence
import Observation

/// What the shared core reads for one juxtaposition (`AppModel.juxtapositionInputs`).
public struct JuxtapositionInputs: Sendable, Equatable {
    /// The description the model reads, labels removed.
    public let description: String
    /// The description as the work keeps it, labels and all: each choice is joined to it.
    public let written: String
    /// The lineage's descriptions, root to the work, labels removed and repeats in a row kept once.
    public let lineage: [String]
    /// The sentences the lineage already added (`juxtaposition.sentence` of its edges).
    public let added: [String]
    public let sources: [(id: String, text: String)]

    public static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.description == rhs.description && lhs.written == rhs.written && lhs.lineage == rhs.lineage
            && lhs.added == rhs.added && lhs.sources.map(\.id) == rhs.sources.map(\.id)
            && lhs.sources.map(\.text) == rhs.sources.map(\.text)
    }
}

/// Web `JuxtaposeDialog.svelte`: ask a Vision model for four sentences from the author's other works, choose one, and
/// draw the work again from its description with the sentence after it, as the work's child.
@MainActor @Observable
public final class JuxtaposeModel {
    public let work: SavedWork
    public var modelReference = ""
    public private(set) var result: Juxtaposition.Result?
    public var chosen: Int?
    /// Every sentence shown in this dialog; "Pick again" leaves them out.
    public private(set) var shown: [String] = []
    public private(set) var asking = false
    public private(set) var drawing = false
    public private(set) var stopping = false
    public private(set) var startedAt: Date?
    public private(set) var errorText: String?
    @ObservationIgnored private var provider: AuxiliaryProvider?
    @ObservationIgnored private var language = "ja"
    @ObservationIgnored private var operation: Task<Bool, Never>?
    @ObservationIgnored private var ownsAppOperation = false

    public init(work: SavedWork, provider: AuxiliaryProvider? = nil) {
        self.work = work
        self.provider = provider
    }

    public var busy: Bool { asking || drawing }
    public var choice: Juxtaposition.Choice? { chosen.flatMap { index in result?.choices.indices.contains(index) == true ? result?.choices[index] : nil } }

    public func initialize(app: AppModel) async {
        if provider == nil {
            do { provider = try app.auxiliaryProvider() }
            catch { errorText = error.localizedDescription; return }
        }
        language = app.display.preferences.language
        if modelReference.isEmpty {
            modelReference = AuxiliaryModel.defaultVisionModel(saved: app.display.preferences.visionModelReference,
                                                               settings: await app.hostSettings())
        }
    }

    /// The auxiliary dialog's rule: choosing a model here also saves it as the settings' Vision model.
    public func selectModel(_ reference: String, app: AppModel) async throws {
        guard !busy, SettingsModel.isRegisteredModelAvailable(reference, purpose: "vision", settings: await app.hostSettings()) else {
            throw HostError("vision_model_not_available")
        }
        modelReference = reference
        app.display.preferences.visionModelReference = reference
    }

    @discardableResult public func ask(app: AppModel) async -> Bool {
        guard !busy, operation == nil, !app.isBusy, let provider else { return false }
        let reference = modelReference
        guard SettingsModel.isRegisteredModelAvailable(reference, purpose: "vision", settings: await app.hostSettings()) else {
            errorText = "画像を扱える登録モデルを選択してください。"; return false
        }
        let exclude = shown
        let language = language
        let work = work
        begin(asking: true)
        let pending = Task { @MainActor [weak self] in
            guard let self else { return false }
            defer { self.finish() }
            self.ownsAppOperation = true
            let before = self.shown.count
            let ran = await app.performSerialized(status: "一文を選んでいます…") { [self] _ in
                do {
                    let inputs = try await app.juxtapositionInputs(work: work)
                    let seed = UInt64.random(in: .min ... .max)
                    let candidates = try await Task.detached {
                        try Juxtaposition.gather(sources: inputs.sources, description: inputs.description,
                                                 lineage: inputs.lineage, added: inputs.added, exclude: exclude, seed: seed)
                    }.value
                    guard candidates.count >= Juxtaposition.choices else { throw HostError("juxtaposition_not_enough_sentences") }
                    guard let png = try await AuxiliaryModel.png(svgs: [work.svg], visionAdvice: true) else {
                        throw HostError("juxtaposition_source_has_no_image")
                    }
                    let asked = try await provider.juxtaposition(description: inputs.description, written: inputs.written,
                        lineage: inputs.lineage, candidates: candidates, png: png, modelReference: reference,
                        language: language, settings: await app.hostSettings())
                    try Task.checkCancellation()
                    self.result = asked
                    self.chosen = nil
                    self.shown += asked.choices.map(\.sentence)
                } catch is CancellationError {
                    throw CancellationError()
                } catch {
                    // The dialog says what went wrong; the main window keeps its own status.
                    self.errorText = Self.message(error)
                }
            }
            self.ownsAppOperation = false
            guard !Task.isCancelled, !self.stopping else { return false }
            if !ran, self.errorText == nil { self.errorText = app.errorText ?? "一文を選べませんでした。" }
            return self.shown.count > before
        }
        operation = pending
        return await pending.value
    }

    /// Draw the chosen description as the work's child, through the description edit's own path.
    @discardableResult public func draw(app: AppModel) async -> Bool {
        guard !busy, operation == nil, !app.isBusy, !app.isPreview, let result, let choice else { return false }
        let work = work
        begin(asking: false)
        let pending = Task { @MainActor [weak self] in
            guard let self else { return false }
            defer { self.finish() }
            do {
                // nil wild = inherit the parent work's setting, as the description edit does.
                let request = try await app.makeSavedWorkEditRequest(work: work, mode: .description, description: choice.joined,
                    wildOverride: nil, metadata: result.metadata(choice).object ?? [:])
                try Task.checkCancellation()
                guard !app.isBusy, !app.isPreview else { throw HostError("authoring_busy_or_unavailable") }
                self.ownsAppOperation = true
                defer { self.ownsAppOperation = false }
                let saved = await app.runSavedWorkEdit(request: request)
                try Task.checkCancellation()
                guard !self.stopping else { throw CancellationError() }
                guard saved != nil else {
                    self.errorText = app.errorText ?? "描画結果を保存できませんでした。DDLを確認してください。"
                    return false
                }
                return true
            } catch is CancellationError { return false }
            catch { self.errorText = Self.message(error); return false }
        }
        operation = pending
        return await pending.value
    }

    public func stop(app: AppModel) async {
        guard let operation else { return }
        stopping = true
        operation.cancel()
        if ownsAppOperation { await app.cancel() }
        _ = await operation.value
    }

    private func begin(asking: Bool) {
        self.asking = asking; drawing = !asking; stopping = false; errorText = nil; startedAt = Date()
    }

    private func finish() {
        operation = nil; asking = false; drawing = false; stopping = false; startedAt = nil
    }

    /// The failures a juxtaposition names in the dialog (Server `api_juxtaposition`'s refusals).
    static func message(_ error: Error) -> String {
        if let answer = error as? JuxtapositionAnswerError {
            return "モデルの答えを2回とも使えませんでした（\(answer.detail)）。"
        }
        switch (error as? HostError)?.code {
        case "juxtaposition_not_enough_sentences": return "ほかの作品の記述に、選べる一文が4つありません。"
        case "juxtaposition_source_has_no_description": return "この作品には記述がありません。"
        case "juxtaposition_source_has_no_image": return "この作品には画がありません。"
        case "description_source_locked": return "編集した指示書で確定した作品です。記述を読み直す操作は使えません。"
        case "vision_model_not_available": return "画像を扱える登録モデルを選択してください。"
        default: return error.localizedDescription
        }
    }
}
