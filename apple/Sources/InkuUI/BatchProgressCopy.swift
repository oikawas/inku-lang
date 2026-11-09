import Foundation

/// The words of the batch tiles (Web `BatchRunSummary.svelte`, `features/batch/elapsed.ts`).
@MainActor
enum BatchProgressCopy {
    /// `batchRowOfTotal`: the line tile's tooltip and spoken name.
    static func rowOfTotal(current: Int, total: Int, display: DisplaySettings) -> String {
        let english = display.preferences.language == "en"
        // The exported templates contain positional placeholders in display order.
        return display.webCopyFormat("batchRowOfTotal", english ? "line %@ of %@" : "%@ 行中 %@ 行目",
                                     english ? current : total, english ? total : current)
    }

    /// `batchElapsed(batchElapsedTime(...))`: the elapsed tile's tooltip.
    static func elapsed(_ elapsed: TimeInterval, display: DisplaySettings) -> String {
        let english = display.preferences.language == "en"
        return display.webCopyFormat("batchElapsed", english ? "%@ since the batch started" : "バッチ開始から %@",
                                     elapsedTime(elapsed, display: display))
    }

    /// `batchAverageWork(batchElapsedTime(...))`: the average tile's tooltip.
    static func average(_ average: TimeInterval, display: DisplaySettings) -> String {
        let english = display.preferences.language == "en"
        return display.webCopyFormat("batchAverageWork", english ? "avg %@ per work" : "1 枚 平均 %@",
                                     elapsedTime(average, display: display))
    }

    /// `batchElapsedTime`: seconds alone under a minute, then minutes and two-digit seconds, then hours.
    static func elapsedTime(_ elapsed: TimeInterval, display: DisplaySettings) -> String {
        let english = display.preferences.language == "en"
        let seconds = Int(max(0, elapsed))
        if seconds >= 3_600 {
            return display.webCopyFormat("elapsedHours", english ? "%@ h %@ min %@ s" : "%@ 時間 %@ 分 %@ 秒",
                                         seconds / 3_600, String(format: "%02d", seconds / 60 % 60), String(format: "%02d", seconds % 60))
        }
        if seconds >= 60 {
            return display.webCopyFormat("elapsedMinutes", english ? "%@ min %@ s" : "%@ 分 %@ 秒",
                                         seconds / 60, String(format: "%02d", seconds % 60))
        }
        return display.webCopyFormat("elapsedSeconds", english ? "%@ s" : "%@ 秒", seconds)
    }

    /// `batchClockTime`: m:ss, and h:mm:ss from an hour.
    nonisolated static func clock(_ elapsed: TimeInterval) -> String {
        let total = Int(max(0, elapsed))
        let seconds = String(format: "%02d", total % 60)
        let minutes = total / 60
        if total < 3_600 { return "\(minutes):\(seconds)" }
        return "\(minutes / 60):" + String(format: "%02d", minutes % 60) + ":\(seconds)"
    }
}
