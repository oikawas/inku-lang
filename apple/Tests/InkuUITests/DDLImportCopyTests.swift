import XCTest
@testable import InkuUI

@MainActor final class DDLImportCopyTests: XCTestCase {
    func testMigratedCountUsesWebCopyAndEnglishSingular() {
        let display = DisplaySettings()
        let fallback = "旧い歳時記から %@ 箇所を書き換えました。"
        XCTAssertEqual(display.webCopyFormat("ddlImportMigrated", fallback, 1), "旧い歳時記から 1 箇所を書き換えました。")
        display.preferences.language = "en"
        XCTAssertEqual(display.webCopyFormat("ddlImportMigrated", fallback, 1), "Migrated 1 change from the older Saijiki.")
        XCTAssertEqual(display.webCopyFormat("ddlImportMigrated", fallback, 0), "Migrated 0 changes from the older Saijiki.")
        XCTAssertEqual(display.webCopyFormat("ddlImportMigrated", fallback, 2), "Migrated 2 changes from the older Saijiki.")
    }
}
