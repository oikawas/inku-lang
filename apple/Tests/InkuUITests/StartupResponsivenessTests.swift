import Foundation
import InkuHost
import InkuPersistence
import XCTest
@testable import InkuUI

private final class StartupGate: @unchecked Sendable {
    private let lock = NSLock()
    private let semaphore = DispatchSemaphore(value: 0)
    private var entered = false
    private var released = false
    func open(_ url: URL) throws -> InkuDatabase {
        lock.lock(); entered = true; lock.unlock()
        semaphore.wait()
        return try InkuDatabase(url: url)
    }
    func state() -> (entered: Bool, released: Bool) {
        lock.lock(); defer { lock.unlock() }; return (entered, released)
    }
    func release() {
        lock.lock(); released = true; lock.unlock()
        semaphore.signal()
    }
}

@MainActor final class StartupResponsivenessTests: XCTestCase {
    func testMainActorRemainsResponsiveWhileDatabaseOpenIsBlocked() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-startup-responsive-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let reference = "fixture:model"
        let provider = ProviderSettings(id: "fixture", baseURL: URL(string: "http://127.0.0.1:1")!,
                                        requiresAPIKey: false, models: [.init(id: "model", purposes: ["llm"])])
        let store = ProviderSettingsStore(url: root.appendingPathComponent("providers.json"))
        try await store.save(.init(providers: [provider], models: .init(stage1Model: reference, stage2Model: reference)))
        var preferences = DisplayPreferences()
        preferences.drawDefaults = DrawOptionsCore.release
        preferences.drawDefaults?["describe"]?.sketch = "off"
        preferences.drawDefaults?["describe"]?.models.stage1 = reference
        try JSONEncoder().encode(preferences).write(to: root.appendingPathComponent("interface.json"))
        let gate = StartupGate()
        // A broken implementation must not hang the test process indefinitely.
        DispatchQueue.global().asyncAfter(deadline: .now() + 2) { gate.release() }
        let app = AppModel(databaseURL: root.appendingPathComponent("works.sqlite"), openDatabase: { try gate.open($0) })
        let initialization = Task { await app.initialize() }
        for _ in 0..<200 {
            if gate.state().entered { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        let duringOpen = gate.state()
        let restoredDefaults = app.drawDefaults["describe"]
        gate.release()
        await initialization.value
        XCTAssertTrue(duringOpen.entered)
        XCTAssertFalse(duringOpen.released, "the main actor could not run until the blocking open was released")
        XCTAssertEqual(restoredDefaults?.sketch, "off")
        XCTAssertEqual(restoredDefaults?.models.stage1, reference)
        XCTAssertNil(app.errorText)
    }
}
