import Foundation

@MainActor
enum BatchProgressCopy {
    static func line(current: Int, total: Int, elapsed: TimeInterval, display: DisplaySettings) -> String {
        let english = display.preferences.language == "en"
        // The exported templates contain positional placeholders in display order.
        let row = display.webCopyFormat("batchRowOfTotal", english ? "row %@ of %@" : "%@ 行中 %@ 行目",
                                        english ? current : total, english ? total : current)
        let seconds = Int(max(0, elapsed))
        let time: String
        if seconds >= 3_600 {
            time = display.webCopyFormat("elapsedHours", english ? "%@ h %@ min %@ s" : "%@ 時間 %@ 分 %@ 秒",
                                         seconds / 3_600, String(format: "%02d", seconds / 60 % 60), String(format: "%02d", seconds % 60))
        } else if seconds >= 60 {
            time = display.webCopyFormat("elapsedMinutes", english ? "%@ min %@ s" : "%@ 分 %@ 秒",
                                         seconds / 60, String(format: "%02d", seconds % 60))
        } else {
            time = display.webCopyFormat("elapsedSeconds", english ? "%@ s" : "%@ 秒", seconds)
        }
        let elapsedText = display.webCopyFormat("batchElapsed", english ? "Since batch start %@" : "バッチ開始から %@", time)
        return row + "　" + elapsedText
    }
}
