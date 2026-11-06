import Foundation
import InkuHost
import XCTest
@testable import InkuUI

@MainActor final class SettingsReviewStep1Tests: XCTestCase {
    func testDrawingGuidanceRoutesByConnection() {
        XCTAssertEqual(SettingsSection.drawingGuidance(hasConnection: false), .models)
        XCTAssertEqual(SettingsSection.drawingGuidance(hasConnection: true), .drawDefaults)
        XCTAssertEqual(SettingsSection.demoGuidance(hasConnection: false), .models)
        XCTAssertNil(SettingsSection.demoGuidance(hasConnection: true))
    }

    func testSavingTokenLimitsPreservesUnavailableModels() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-token-limits-\(UUID())")
        defer { try? FileManager.default.removeItem(at: folder) }
        let app = AppModel(databaseURL: folder.appendingPathComponent("works.sqlite"))
        await app.initialize()
        var initial = await app.hostSettings()
        initial.models.stage1Model = "unavailable:first"
        initial.models.stage2Model = "unavailable:second"
        try await app.updateHostSettings(initial)
        let before = await app.hostSettings()
        let settings = SettingsModel(credentials: EmptyReviewCredentials())
        try await settings.saveTokenLimits(stage1: 4096, hole: 3072, model: app)
        let saved = await app.hostSettings()
        XCTAssertEqual(saved.models.stage1Model, before.models.stage1Model)
        XCTAssertEqual(saved.models.stage2Model, before.models.stage2Model)
        XCTAssertEqual(saved.models.stage1MaxTokens, 4096)
        XCTAssertEqual(saved.models.holeMaxTokens, 3072)
    }

    func testReloadPreservesPersonalPlanSelection() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-selected-plan-\(UUID())")
        defer { try? FileManager.default.removeItem(at: folder) }
        let app = AppModel(databaseURL: folder.appendingPathComponent("works.sqlite"))
        await app.initialize()
        var host = await app.hostSettings()
        if !host.providers.contains(where: { $0.id == "chatgpt" }) { host.providers.append(.personalPlan) }
        try await app.updateHostSettings(host)
        let settings = SettingsModel(credentials: EmptyReviewCredentials())
        settings.selectedProviderID = "chatgpt"
        await settings.load(model: app)
        XCTAssertEqual(settings.selectedProviderID, "chatgpt")
    }
}

private actor EmptyReviewCredentials: ProviderCredentialStore {
    func key(for credentialID: String) async throws -> String? { nil }
    func isConfigured(for credentialID: String) async throws -> Bool { false }
    func setKey(_ key: String?, for credentialID: String) async throws {}
}
