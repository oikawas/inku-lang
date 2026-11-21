#if os(iOS)
import UIKit
import OSLog
import UniformTypeIdentifiers

/// The system share sheet for files the app wrote (iOS plan step 2, author's choice 2026-11-08): "Save Image" puts an
/// exported picture in Photos, "Save to Files" and AirDrop take any format.
@MainActor
enum InkuShareSheet {
    /// Shows the sheet over the frontmost screen; true when the author completed an action, false when cancelled.
    static func present(_ urls: [URL], pngCard: Bool = false) async -> Bool {
        guard !urls.isEmpty else { return false }
        let folders = NativeFilePanels.beginSharing(urls)
        defer { NativeFilePanels.endSharing(folders) }
        // UIKit can take several seconds to construct the activity controller. A presenter selected before that
        // work can have left the window by the time presentation begins.
        let items: [Any] = pngCard ? urls.map { PNGShareItem(url: $0) } : urls
        let sheet = UIActivityViewController(activityItems: items, applicationActivities: nil)
        guard let top = await frontmost() else { return false }
        return await withCheckedContinuation { continuation in
            let completion = ShareSheetCompletion { continuation.resume(returning: $0) }
            let logger = Logger(subsystem: "app.inku", category: "share-sheet")
            sheet.completionWithItemsHandler = { activityType, completed, _, error in
                let activity = activityType?.rawValue ?? "none"
                let activityError = error.map { $0 as NSError }
                logger.notice("Activity completion (activityType: \(activity, privacy: .public), completed: \(completed), activityError: \(activityError?.domain ?? "none", privacy: .public)/\(activityError?.code ?? 0))")
                completion.finish(completed)
            }
            if let popover = sheet.popoverPresentationController {
                popover.sourceView = top.view
                popover.sourceRect = CGRect(x: top.view.bounds.midX, y: top.view.bounds.midY, width: 0, height: 0)
                popover.permittedArrowDirections = []
            }
            guard top.viewIfLoaded?.window != nil, !top.isBeingDismissed, top.presentedViewController == nil else {
                logger.debug("Activity presentation rejected before presenting")
                completion.presentationReturned(attached: false)
                return
            }
            top.present(sheet, animated: true)
            // UIKit installs the presentation relationship before animating. Once accepted, a
            // system activity may replace the sheet controller while it still needs the files.
            let attached = top.presentedViewController === sheet || sheet.presentingViewController != nil
            if !attached { logger.debug("Activity presentation was not attached") }
            completion.presentationReturned(attached: attached)
        }
    }

    /// Do not walk onto a disappearing or detached sheet. Re-read the hierarchy after its transition finishes.
    private static func frontmost() async -> UIViewController? {
        for _ in 0..<20 {
            let window = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
                .flatMap(\.windows).first(where: \.isKeyWindow)
            guard var top = window?.rootViewController else { return nil }
            var disappearing: UIViewController?
            while let presented = top.presentedViewController {
                if presented.isBeingDismissed || presented.viewIfLoaded?.window == nil {
                    disappearing = presented
                    break
                }
                top = presented
            }
            if let disappearing {
                if let transition = disappearing.transitionCoordinator ?? top.transitionCoordinator {
                    await waitForTransition(transition)
                } else {
                    try? await Task.sleep(for: .milliseconds(50))
                }
                continue
            }
            guard !top.isBeingDismissed, top.viewIfLoaded?.window != nil else { return nil }
            return top
        }
        return nil
    }

    private static func waitForTransition(_ transition: any UIViewControllerTransitionCoordinator) async {
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            var resumed = false
            func finish() {
                guard !resumed else { return }
                resumed = true
                continuation.resume(returning: ())
            }
            if !transition.animate(alongsideTransition: nil, completion: { _ in finish() }) { finish() }
            // A cancelled or interrupted transition must not leave sharing suspended forever.
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(1))
                finish()
            }
        }
    }
}
/// Provides the original named file with an explicit image type for share extensions and Photos.
private final class PNGShareItem: NSObject, UIActivityItemSource {
    let url: URL

    init(url: URL) { self.url = url }

    func activityViewControllerPlaceholderItem(_ activityViewController: UIActivityViewController) -> Any {
        url
    }

    func activityViewController(_ activityViewController: UIActivityViewController,
                                itemForActivityType activityType: UIActivity.ActivityType?) -> Any? {
        url
    }

    func activityViewController(_ activityViewController: UIActivityViewController,
                                dataTypeIdentifierForActivityType activityType: UIActivity.ActivityType?) -> String {
        UTType.png.identifier
    }
}
#endif
