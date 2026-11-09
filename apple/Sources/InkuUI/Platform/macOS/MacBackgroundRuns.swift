#if os(macOS)
import SwiftUI

extension View {
    /// The Mac keeps running when the app is behind other windows, so nothing changes there (iOS:
    /// `IOSBackgroundRuns.swift`).
    func inkuBackgroundRuns(model: AppModel, onForeground: @escaping @MainActor () -> Void) -> some View { self }
}
#endif
