#if os(iOS)
import BackgroundTasks
import SwiftUI
import UIKit

extension View {
    /// iOS plan §3 #17–#19 (SWIFT_SPEC, iOS): while a run goes on, the screen does not dim; on iOS 26 and later the run
    /// keeps going in the background as a continued-processing task with the system's progress; when that is not
    /// granted (the simulator, iOS 18–25, or the system ends it), the run is stopped about 30 seconds after the app
    /// leaves, as its stop button would. A memory warning drops the work area's kept pictures. `onForeground` runs
    /// when the app comes back (the automatic backup that was due while it was away).
    func inkuBackgroundRuns(model: AppModel, onForeground: @escaping @MainActor () -> Void) -> some View {
        modifier(IOSBackgroundRunsModifier(model: model, onForeground: onForeground))
    }
}

private struct IOSBackgroundRunsModifier: ViewModifier {
    let model: AppModel
    let onForeground: @MainActor () -> Void
    @Environment(\.scenePhase) private var phase
    @State private var keeper = IOSBackgroundRunKeeper()

    func body(content: Content) -> some View {
        content
            .onChange(of: model.hasActiveRun, initial: true) { _, active in
                UIApplication.shared.isIdleTimerDisabled = active
                if active { keeper.runStarted(model: model) } else { keeper.runEnded() }
            }
            .onChange(of: phase) { old, new in
                switch new {
                case .background: keeper.enteredBackground(model: model)
                case .active:
                    keeper.becameActive()
                    if old == .background || old == .inactive { onForeground() }
                default: break
                }
            }
            .onReceive(NotificationCenter.default.publisher(for: UIApplication.didReceiveMemoryWarningNotification)) { _ in
                model.displayRenderer.purgeCaches()
                Task { await model.renderer.purge() }
            }
    }
}

@MainActor
final class IOSBackgroundRunKeeper {
    /// Info-iOS.plist `BGTaskSchedulerPermittedIdentifiers` allows `app.inku.ios.continued.*`; each run takes a new
    /// name, because a name is registered once for the app's life.
    private static let identifierPrefix = "app.inku.ios.continued."
    /// Without a continued task, the run is stopped this long after the app leaves (the system allows about 30 s).
    static let graceSeconds = 25

    private var continued: AnyObject?
    private var continuedLoop: Task<Void, Never>?
    /// Submitted, and the system has not started it yet (with the `.fail` strategy it starts at once or not at all).
    private var continuedPending = false
    private var backgroundTask: UIBackgroundTaskIdentifier = .invalid
    private var graceStop: Task<Void, Never>?

    /// A continued task can only be asked for while the app is in front, so it is asked for when the run starts.
    func runStarted(model: AppModel) {
        guard continued == nil, !continuedPending else { return }
        if #available(iOS 26.0, *) { submitContinued(model: model) }
    }

    func runEnded() {
        if continued == nil { continuedPending = false }
        graceStop?.cancel(); graceStop = nil
        endBackgroundTask()
    }

    func enteredBackground(model: AppModel) {
        guard model.hasActiveRun, continued == nil, graceStop == nil else { return }
        backgroundTask = UIApplication.shared.beginBackgroundTask(withName: "inku.stop") { [weak self] in
            Task { @MainActor in
                await model.stopEveryRun()
                self?.endBackgroundTask()
            }
        }
        graceStop = Task { @MainActor [weak self] in
            do { try await Task.sleep(for: .seconds(Self.graceSeconds)) } catch { return }
            await model.stopEveryRun()
            self?.graceStop = nil
            self?.endBackgroundTask()
        }
    }

    func becameActive() {
        graceStop?.cancel(); graceStop = nil
        endBackgroundTask()
    }

    private func endBackgroundTask() {
        guard backgroundTask != .invalid else { return }
        UIApplication.shared.endBackgroundTask(backgroundTask)
        backgroundTask = .invalid
    }

    @available(iOS 26.0, *)
    private func submitContinued(model: AppModel) {
        let identifier = Self.identifierPrefix + UUID().uuidString.lowercased()
        let title = model.display.localized("inkuで描画しています")
        let registered = BGTaskScheduler.shared.register(forTaskWithIdentifier: identifier, using: .main) { [weak self] task in
            MainActor.assumeIsolated {
                guard let self, let task = task as? BGContinuedProcessingTask else { task.setTaskCompleted(success: false); return }
                self.follow(task, model: model, title: title)
            }
        }
        guard registered else { return }
        let request = BGContinuedProcessingTaskRequest(identifier: identifier, title: title, subtitle: "")
        request.strategy = .fail
        // The simulator answers "not available on this platform"; the run then falls back to the grace stop.
        do { try BGTaskScheduler.shared.submit(request) } catch { return }
        continuedPending = true
    }

    @available(iOS 26.0, *)
    private func follow(_ task: BGContinuedProcessingTask, model: AppModel, title: String) {
        continued = task; continuedPending = false
        task.expirationHandler = { [weak self] in
            Task { @MainActor in
                await model.stopEveryRun()
                task.setTaskCompleted(success: false)
                self?.continued = nil; self?.continuedLoop = nil
            }
        }
        continuedLoop = Task { @MainActor [weak self] in
            var state = ContinuedRunProgress()
            while model.hasActiveRun, !Task.isCancelled {
                let progress = Self.progress(model: model, state: &state)
                task.progress.totalUnitCount = progress.total
                task.progress.completedUnitCount = progress.done
                task.updateTitle(title, subtitle: progress.subtitle)
                try? await Task.sleep(for: .seconds(1))
            }
            task.progress.completedUnitCount = task.progress.totalUnitCount
            task.setTaskCompleted(success: true)
            self?.continued = nil; self?.continuedLoop = nil
        }
    }

    static func progress(model: AppModel, state: inout ContinuedRunProgress, now: Date = Date()) -> (done: Int64, total: Int64, subtitle: String) {
        let rows = model.runStops.rows.flatMap { $0.total > 0 ? $0 : nil } ?? (done: 0, total: 1)
        let row = rows.total > 1 ? "\(min(rows.done + 1, rows.total)) / \(rows.total)  " : ""
        let done = state.advance(rowsDone: rows.done, now: now)
        return (done, Int64(rows.total * ContinuedRunProgress.unitsPerRow), row + model.display.message(model.status))
    }
}
#endif
