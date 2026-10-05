import Foundation
import InkuHost
import InkuPersistence
import Observation

public enum WorkEditMode: String, Sendable {
    case description, sketch
}

@MainActor @Observable
public final class WorkEditModel {
    public let work: SavedWork
    public let mode: WorkEditMode
    public var draftText: String
    public var sketchMode: String
    public var inheritWild = true
    public var wildOverride: Bool
    public private(set) var initialized = false
    public private(set) var sourceIsLocked = false
    public private(set) var running = false
    public private(set) var stopping = false
    public private(set) var errorText: String?
    public private(set) var result: SavedWork?
    @ObservationIgnored private var operation: Task<Bool, Never>?
    @ObservationIgnored private var ownsAppOperation = false

    public init(work: SavedWork, mode: WorkEditMode) {
        self.work = work
        self.mode = mode
        draftText = work.effectiveSourceText
        sketchMode = work.sketchText?.isEmpty == false ? "off" : "on"
        wildOverride = work.renderWild ?? false
    }

    public var canDraw: Bool {
        initialized && !sourceIsLocked && !running && result == nil
            && !(mode == .description ? draftText : work.effectiveSourceText).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    public func initialize(app: AppModel) async {
        guard !initialized else { return }
        do {
            let context = try await app.savedConfiguration(workID: work.id)
            try Task.checkCancellation()
            guard ["description_authoritative", "ddl_authoritative"].contains(context.authority) else { throw HostError("saved_authoring_context_unavailable") }
            sourceIsLocked = context.authority != "description_authoritative"
            if sourceIsLocked { errorText = "DDL を編集した作品は記述を読み直しません。色・配置・タッチ・変奏を元の DDL から描けます。" }
            initialized = true
        } catch is CancellationError { }
        catch { errorText = error.localizedDescription }
    }

    @discardableResult public func draw(app: AppModel) async -> Bool {
        guard canDraw, !app.isBusy, !app.isPreview, operation == nil else { return false }
        let text = draftText
        let sketch = sketchMode
        let wild: Bool? = inheritWild ? nil : wildOverride
        running = true
        stopping = false
        errorText = nil
        let pending = Task { @MainActor [weak self] in
            guard let self else { return false }
            defer { self.operation = nil; self.running = false; self.stopping = false }
            do {
                let request = try await app.makeSavedWorkEditRequest(work: self.work, mode: self.mode,
                    description: text, sketchMode: sketch, wildOverride: wild)
                try Task.checkCancellation()
                guard !app.isBusy, !app.isPreview else { throw HostError("authoring_busy_or_unavailable") }
                self.ownsAppOperation = true
                defer { self.ownsAppOperation = false }
                let saved = await app.runSavedWorkEdit(request: request)
                try Task.checkCancellation()
                guard !self.stopping else { throw CancellationError() }
                guard let saved else {
                    self.errorText = app.errorText ?? "描画結果を保存できませんでした。DDLを確認してください。"
                    return false
                }
                self.result = saved
                return true
            } catch is CancellationError { return false }
            catch { self.errorText = error.localizedDescription; return false }
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
}
