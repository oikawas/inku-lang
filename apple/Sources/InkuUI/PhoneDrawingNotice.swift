import Foundation
#if os(iOS)
import UIKit
import UserNotifications
#endif

@MainActor
enum PhoneDrawingNotice {
    #if os(iOS)
    private static var requested = false
    #endif

    static var isOutsideApp: Bool {
        #if os(iOS)
        UIApplication.shared.applicationState == .background
        #else
        false
        #endif
    }

    static func requestPermission() {
        #if os(iOS)
        guard !requested else { return }
        requested = true
        Task {
            let center = UNUserNotificationCenter.current()
            guard await center.notificationSettings().authorizationStatus == .notDetermined else { return }
            _ = try? await center.requestAuthorization(options: [.alert])
        }
        #endif
    }

    static func announce(_ id: String, display: DisplaySettings) {
        #if os(iOS)
        if isOutsideApp {
            let content = UNMutableNotificationContent()
            content.title = display.localized("描き上がりました")
            Task {
                try? await UNUserNotificationCenter.current().add(
                    UNNotificationRequest(identifier: "drawing-" + id, content: content, trigger: nil))
            }
        } else {
            finishPicture()
        }
        #endif
    }

    static func finishPicture() {
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        #endif
    }
}
