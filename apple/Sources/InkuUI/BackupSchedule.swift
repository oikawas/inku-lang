import Foundation

public struct BackupSchedule: Codable, Sendable, Equatable {
    public var intervalDays = 7
    public var maxGenerations = 4
    public var hour = 3
    public var minute = 0
    public init() {}

    public func validate() throws {
        guard (1...365).contains(intervalDays), (1...100).contains(maxGenerations),
              (0...23).contains(hour), (0...59).contains(minute) else {
            throw BackupScheduleFailure.invalidValues
        }
    }

    public func nextDate(lastAutomaticSuccess: Date?, now: Date, calendar: Calendar) throws -> Date {
        try validate()
        guard let lastAutomaticSuccess else { return now }
        guard let day = calendar.date(byAdding: .day, value: intervalDays, to: calendar.startOfDay(for: lastAutomaticSuccess)),
              // bySettingHour drops the requested minute in a DST gap; nextDate preserves it.
              let due = calendar.nextDate(after: day.addingTimeInterval(-1),
                                          matching: DateComponents(hour: hour, minute: minute, second: 0),
                                          matchingPolicy: .nextTimePreservingSmallerComponents, repeatedTimePolicy: .first,
                                          direction: .forward) else { throw BackupScheduleFailure.invalidDate }
        return due
    }
}

public enum BackupScheduleFailure: LocalizedError {
    case invalidValues, invalidLegacyInterval, invalidDate
    public var errorDescription: String? {
        switch self {
        case .invalidValues: "バックアップは1〜365日、1〜100世代、時刻は0〜23時・0〜59分で指定してください。"
        case .invalidLegacyInterval: "旧バックアップの時間間隔が範囲外です。日数と時刻を指定して保存してください。"
        case .invalidDate: "バックアップの次回予定を計算できませんでした。"
        }
    }
}

extension DisplayPreferences {
    public var usesLegacyBackupInterval: Bool { backupScheduleMode == "legacyHours" }
    public var automaticBackupRetention: Int { usesLegacyBackupInterval ? backupGenerations : backupSchedule.maxGenerations }

    public mutating func applyBackupSchedule(_ schedule: BackupSchedule) throws {
        try schedule.validate()
        backupSchedule = schedule
        backupScheduleMode = "calendar"
        backupPreferencesVersion = 1
    }

    public func nextAutomaticBackupDate(lastSuccess: Date?, now: Date, calendar: Calendar) throws -> Date {
        if usesLegacyBackupInterval {
            guard (1...168).contains(backupIntervalHours), (1...100).contains(backupGenerations) else {
                throw BackupScheduleFailure.invalidLegacyInterval
            }
            return lastSuccess?.addingTimeInterval(TimeInterval(backupIntervalHours) * 3600) ?? now
        }
        return try backupSchedule.nextDate(lastAutomaticSuccess: lastSuccess, now: now, calendar: calendar)
    }
}
