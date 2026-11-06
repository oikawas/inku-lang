import XCTest
import InkuHost
@testable import InkuUI

@MainActor final class DDLImportCopyTests: XCTestCase {
    func testImportFailureCodesHaveLocalizedMessages() {
        let display = DisplaySettings()
        let codes = ["ddl_import_too_large", "ddl_import_invalid_utf8", "ddl_export_without_ddl", "ddl_export_requires_v2", "ddl_export_too_many_plugins", "ddl_export_invalid", "ddl_export_invalid_plugin", "imported_macro_catalog_incomplete", "authoring_busy", "ddl_import_busy_or_unavailable", "ddl_import_context_changed"]
        for language in ["ja", "en"] {
            display.preferences.language = language
            for code in codes {
                let message = DDLImportErrorText.message(HostError(code), display: display)
                XCTAssertFalse(message.contains(code), "\(language): \(code)")
                XCTAssertFalse(message.isEmpty)
            }
        }
        XCTAssertEqual(DDLImportErrorText.message(HostError("ddl_export_requires_v2"), display: display), "Export the original work again in v2 format.")
    }
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
