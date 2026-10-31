import XCTest
@testable import InkuUI

final class CompositionScanCacheTests: XCTestCase {
    func testRepeatedLongTextScanKeepsRangesAndAvoidsRepeatedParsing() {
        let body = String(repeating: "at left (horizontal 0 to 1/2, vertical 0 to 1).\n", count: 500)
        var cold: [Double] = [], warm: [Double] = []
        for index in 0..<10 {
            let source = body + " #\(index)"
            var start = ContinuousClock.now
            let first = CompositionRanges.scan(source)
            var duration = start.duration(to: .now).components
            cold.append(Double(duration.seconds) * 1000 + Double(duration.attoseconds) / 1e15)
            start = .now
            let second = CompositionRanges.scan(source)
            duration = start.duration(to: .now).components
            warm.append(Double(duration.seconds) * 1000 + Double(duration.attoseconds) / 1e15)
            XCTAssertEqual(first, second)
            XCTAssertEqual(first.count, 500)
        }
        cold.sort(); warm.sort()
        print("Synthetic range scan: rounds=10 ranges=500 cold_median_ms=\((cold[4]+cold[5])/2) warm_median_ms=\((warm[4]+warm[5])/2) warm_p95_ms=\(warm[9])")
    }

    func testCanonicallyEquivalentTextKeepsExactUTF16Offsets() throws {
        let suffix = " at left (horizontal 0 to 1, vertical 0 to 1)"
        let composed = "é" + suffix
        let decomposed = "e\u{301}" + suffix
        let first = try XCTUnwrap(CompositionRanges.scan(composed).first)
        let second = try XCTUnwrap(CompositionRanges.scan(decomposed).first)
        XCTAssertEqual(second.start, first.start + 1)
        XCTAssertEqual(CompositionRanges.scan(composed).first, first)
        XCTAssertEqual(CompositionRanges.scan(decomposed).first, second)
    }
}
