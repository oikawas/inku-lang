import Foundation
import InkuHost
import InkuPersistence
import Observation

/// A replay compares an immutable saved work without adopting or saving its result.
@MainActor @Observable
public final class ReplayComparisonModel {
    public let work: SavedWork
    public private(set) var snapshot: ReplayComparisonSnapshot?
    public private(set) var running = false
    public private(set) var stopping = false
    public private(set) var closed = false
    public private(set) var status = "保存時と現行エンジンを比較中"
    public private(set) var errorText: String?
    @ObservationIgnored private var operation: Task<Void, Never>?
    @ObservationIgnored private var runID: UUID?
    @ObservationIgnored private var ownsAppOperation = false

    public init(work: SavedWork) { self.work = work }

    public func compare(app: AppModel) async {
        guard !closed, operation == nil, snapshot == nil else { return }
        guard !app.isBusy else {
            status = "再現の比較を開始できませんでした。"
            errorText = "ほかの処理が終わってから、もう一度比較してください。"
            return
        }
        let run = UUID()
        let original = work
        runID = run; running = true; stopping = false
        errorText = nil
        status = "保存時と現行エンジンを比較中"
        let pending = Task { @MainActor [weak self] in
            guard let self else { return }
            defer { self.finishOperation() }
            do {
                try Task.checkCancellation()
                guard self.runID == run, !self.closed else { throw CancellationError() }
                guard !app.isBusy else {
                    self.status = "再現の比較を開始できませんでした。"
                    self.errorText = "ほかの処理が終わってから、もう一度比較してください。"
                    return
                }
                var prepared: ReplayComparisonSnapshot?
                var preparationError: String?
                let succeeded = await app.performComparison(status: "保存時と現行エンジンを比較中", restoreDisplayStatus: true) { token in
                    self.ownsAppOperation = true
                    defer { self.ownsAppOperation = false }
                    try Task.checkCancellation()
                    guard self.runID == run, !self.closed, !self.stopping else { throw CancellationError() }
                    do {
                        let result = try await app.prepareReplayComparison(work: original, token: token)
                        try Task.checkCancellation()
                        guard self.runID == run, !self.closed, !self.stopping else { throw CancellationError() }
                        guard result.workID == original.id else {
                            throw HostError("再現の比較結果が元の作品と一致しません。")
                        }
                        guard !result.originalSVG.isEmpty, !result.replayedSVG.isEmpty else {
                            throw HostError("再現の比較に必要なSVGを取得できませんでした。")
                        }
                        prepared = result
                    } catch {
                        try Task.checkCancellation()
                        if error is CancellationError { throw error }
                        // Preparation errors belong to this sheet, not the main canvas's alert.
                        preparationError = error.localizedDescription
                    }
                }
                try Task.checkCancellation()
                guard self.runID == run, !self.closed, !self.stopping else { throw CancellationError() }
                guard succeeded, let prepared else {
                    self.status = "再現の比較を用意できませんでした。"
                    self.errorText = preparationError ?? app.errorText ?? "再現の比較を用意できませんでした。"
                    return
                }
                self.snapshot = prepared
                self.status = "保存時と現行エンジンの比較を用意しました。"
            } catch is CancellationError {
                self.status = "再現の比較を停止しました。"
            } catch {
                self.status = "再現の比較を用意できませんでした。"
                self.errorText = error.localizedDescription
            }
        }
        operation = pending
        await pending.value
    }

    public func stop(app: AppModel) async {
        guard let pending = operation else { return }
        if !stopping {
            stopping = true
            status = "停止中"
            runID = nil
            pending.cancel()
            if ownsAppOperation { await app.cancel() }
        }
        await pending.value
    }

    public func close(app: AppModel) async {
        closed = true
        await stop(app: app)
    }

    private func finishOperation() {
        operation = nil; runID = nil
        running = false; stopping = false
    }
}
