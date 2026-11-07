import Foundation
import SwiftUI

/// Web `click` and `dblclick` (HistoryManager.svelte:1202) on a library or lineage picture: the first click previews at
/// once and the second click of a double click opens the work. The count comes from the mouse-down that pressed this
/// very picture, recorded as it happens, not from whatever event is current when SwiftUI runs the button's action:
/// that event can be a later one (a move, or the press on another card), which would miscount the clicks.
enum LibraryClick {
    /// A left mouse-down: its click count, window, place in the window's base coordinates and time.
    struct Press: Equatable, Sendable {
        let clickCount: Int
        let windowNumber: Int
        let locationInWindow: CGPoint
        let time: TimeInterval
    }

    /// Opens only when the latest press was in the picture's window, inside the picture, recent enough to be the press
    /// that ran the action, and the second (or later) click. Anything else, a key or accessibility press among them,
    /// previews.
    static func opensWork(press: Press?, windowNumber: Int?, contains: (CGPoint) -> Bool, now: TimeInterval,
                          interval: TimeInterval) -> Bool {
        guard let press, let windowNumber, press.windowNumber == windowNumber,
              now - press.time >= 0, now - press.time <= interval, contains(press.locationInWindow) else { return false }
        return press.clickCount >= 2
    }

}


/// The picture button of a library or lineage card: one button, and the press that ran it.
/// `.buttonStyle` and `.disabled` set outside reach the button through the environment.
struct LibraryClickButton<Label: View>: View {
    let preview: () -> Void
    let open: () -> Void
    @ViewBuilder let label: () -> Label
    var body: some View {
        LibraryClickPlatform(preview: preview, open: open, label: label)
    }
}
