#if os(iOS)
import UIKit

/// The system share sheet for files the app wrote (iOS plan step 2, author's choice 2026-11-08): "Save Image" puts an
/// exported picture in Photos, "Save to Files" and AirDrop take any format.
@MainActor
enum InkuShareSheet {
    /// Shows the sheet over the frontmost screen; true when the author completed an action, false when cancelled.
    static func present(_ urls: [URL]) async -> Bool {
        guard !urls.isEmpty, let top = frontmost() else { return false }
        return await withCheckedContinuation { continuation in
            var resumed = false
            let sheet = UIActivityViewController(activityItems: urls, applicationActivities: nil)
            sheet.completionWithItemsHandler = { _, completed, _, _ in
                guard !resumed else { return }
                resumed = true
                continuation.resume(returning: completed)
            }
            if let popover = sheet.popoverPresentationController {
                popover.sourceView = top.view
                popover.sourceRect = CGRect(x: top.view.bounds.midX, y: top.view.bounds.midY, width: 0, height: 0)
                popover.permittedArrowDirections = []
            }
            top.present(sheet, animated: true)
        }
    }

    private static func frontmost() -> UIViewController? {
        let window = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
            .flatMap(\.windows).first(where: \.isKeyWindow)
        var top = window?.rootViewController
        while let presented = top?.presentedViewController { top = presented }
        return top
    }
}
#endif
