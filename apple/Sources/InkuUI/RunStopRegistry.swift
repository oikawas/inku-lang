import Foundation
import Observation

/// An owner of a run that has its own "停止" (a batch, a comparison, a refinement, …). Stopping it through
/// `stop(app:)` is what pressing that owner's stop button does: a plain `AppModel.cancel()` would end only the
/// drawing in flight, and an owner with several lanes or rows would go on to the next one.
@MainActor
protocol StoppableRun: AnyObject {
    var isStoppableRunActive: Bool { get }
    /// Rows done and rows in all, for an owner that runs rows (the batch); nil for the others.
    var stoppableRunRows: (done: Int, total: Int)? { get }
    func stop(app: AppModel) async
}

extension StoppableRun {
    var stoppableRunRows: (done: Int, total: Int)? { nil }
}

/// Every owner that has started a run, held weakly, so one call can stop them all as their stop buttons would.
/// iOS uses it when the app has gone to the background and may not keep running (SWIFT_SPEC, iOS). The Mac never
/// calls `stopAll`; owners only register themselves when they start.
@MainActor @Observable
public final class RunStopRegistry {
    private struct Weak { weak var owner: (any StoppableRun)? }
    @ObservationIgnored private var owners: [ObjectIdentifier: Weak] = [:]
    /// Raised by `track`, so a view that reads `anyActive` is asked again when a new owner joins.
    private var revision = 0

    public init() {}

    func track(_ owner: some StoppableRun) {
        owners = owners.filter { $0.value.owner != nil }
        if owners[ObjectIdentifier(owner)] == nil {
            owners[ObjectIdentifier(owner)] = Weak(owner: owner)
            revision &+= 1
        }
    }

    private var active: [any StoppableRun] {
        _ = revision
        return owners.values.compactMap(\.owner).filter(\.isStoppableRunActive)
    }

    public var anyActive: Bool { !active.isEmpty }

    /// The first active owner's rows (the batch), if one runs rows.
    public var rows: (done: Int, total: Int)? { active.lazy.compactMap(\.stoppableRunRows).first }

    func stopAll(app: AppModel) async {
        for owner in active { await owner.stop(app: app) }
    }
}

extension RefinementModel: StoppableRun { var isStoppableRunActive: Bool { running } }
extension ComparisonModel: StoppableRun { var isStoppableRunActive: Bool { running } }
extension ToolChangeModel: StoppableRun { var isStoppableRunActive: Bool { running } }
extension SavedScoreVariantModel: StoppableRun { var isStoppableRunActive: Bool { running } }
extension WorkEditModel: StoppableRun { var isStoppableRunActive: Bool { running } }
extension AuxiliaryModel: StoppableRun { var isStoppableRunActive: Bool { running } }
extension AutonomousRefinementModel: StoppableRun { var isStoppableRunActive: Bool { running } }
extension JuxtaposeModel: StoppableRun { var isStoppableRunActive: Bool { busy } }
extension ImageFolderBatch: StoppableRun {
    var isStoppableRunActive: Bool { running }
    var stoppableRunRows: (done: Int, total: Int)? { (completed, total) }
}
extension AutomationModel: StoppableRun {
    var isStoppableRunActive: Bool { running }
    var stoppableRunRows: (done: Int, total: Int)? { mode == "batch" ? (completedCount, rows.count) : nil }
}

extension AppModel {
    /// A drawing, a batch, or any other run that has a stop button is going on.
    public var hasActiveRun: Bool { isBusy || runStops.anyActive }

    /// What pressing every visible stop button would do: each owner stops its own run, then a plain drawing (the
    /// creation panel's single run, whose stop is `cancel()`) is cancelled.
    public func stopEveryRun() async {
        await runStops.stopAll(app: self)
        await cancel()
    }
}
