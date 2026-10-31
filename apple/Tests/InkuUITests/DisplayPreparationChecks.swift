import Foundation
import XCTest
@testable import InkuUI

final class DisplayPreparationChecks: XCTestCase, @unchecked Sendable {
    func testConcurrentIdenticalWorksRemainRenderable() async throws {
        let elements = (0..<4000).map { index in
            "<rect x=\"\(index % 64)\" y=\"\((index / 64) % 64)\" width=\"1\" height=\"1\" fill=\"#568\"/>"
        }.joined()
        let svg = "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"64\" height=\"64\">\(elements)</svg>"
        var times: [Double] = []
        var preparations = 0, reuses = 0
        for _ in 0..<10 {
            let renderer = DisplayRenderer(windows: .cpu)
            let start = ContinuousClock.now
            let completed = try await withThrowingTaskGroup(of: Bool.self, returning: [Bool].self) { group in
                for _ in 0..<6 {
                    group.addTask {
                        var full = false
                        for try await frame in renderer.whole(svg: svg, width: 64, height: 64) { if !frame.coarse { full = true } }
                        return full
                    }
                }
                var result: [Bool] = []
                for try await value in group { result.append(value) }
                return result
            }
            let duration = start.duration(to: .now).components
            times.append(Double(duration.seconds) * 1000 + Double(duration.attoseconds) / 1e15)
            XCTAssertEqual(completed, [true, true, true, true, true, true])
            let diagnostics = renderer.diagnostics()
            XCTAssertTrue(diagnostics.failures.isEmpty)
            if diagnostics.scenePreparations > 1 { XCTAssertGreaterThan(diagnostics.scenePreparationReuses, 0) }
            preparations += diagnostics.scenePreparations
            reuses += diagnostics.scenePreparationReuses
        }
        times.sort()
        let median = (times[4] + times[5]) / 2
        print("Synthetic identical SVG: rounds=10 requests_per_round=6 elements=4000 preparations=\(preparations) reused=\(reuses) median_ms=\(median) p95_ms=\(times[9])")
    }
}
