import Foundation
import XCTest
@testable import InkuHost

/// Failure: the macOS policy bridge changes a shared ChatGPT decision or bypasses InkuCore.
final class ChatGPTAuth1115Checks: XCTestCase {
    func testEverySharedAuthCaseThroughInkuCore() throws {
        var directory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        while directory.path != "/" {
            let file = directory.appendingPathComponent("server/tests/data/chatgpt-auth-11-15-cases.json")
            if FileManager.default.fileExists(atPath: file.path) {
                let rows = try ExactJSON(data: Data(contentsOf: file)).array ?? []
                // The closed parts' 17 rows moved to the core's own sign-in-part-cases.json (step 6).
                XCTAssertEqual(rows.count, 14)
                for row in rows {
                    var fields = row["request"].object ?? [:]
                    let action = fields.removeValue(forKey: "action")?.string ?? ""
                    let answer = try ChatGPTPolicy.result(action, fields)
                    for (key, value) in row["expect"].object ?? [:] {
                        XCTAssertEqual(answer[key], value, "\(row["name"].string ?? "case"): \(key)")
                    }
                }
                return
            }
            directory.deleteLastPathComponent()
        }
        XCTFail("Shared ChatGPT auth cases were not found")
    }
}
