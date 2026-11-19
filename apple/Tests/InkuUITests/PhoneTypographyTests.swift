import SwiftUI
import XCTest
@testable import InkuUI

final class PhoneTypographyTests: XCTestCase {
    func testMinimumFontSizeDefaultsToZeroAndClampsPhoneText() {
        let environment = EnvironmentValues()
        XCTAssertEqual(environment.inkuMinimumFontSize, 0)
        XCTAssertEqual(InkuTypography.size(10, scale: 1, minimum: environment.inkuMinimumFontSize), 10)
        XCTAssertEqual(InkuTypography.size(10, scale: InkuTypography.phoneTextScale, minimum: 13), 13)
        XCTAssertEqual(InkuTypography.size(14, scale: InkuTypography.phoneTextScale, minimum: 13), 17, accuracy: 0.0001)
    }
}
