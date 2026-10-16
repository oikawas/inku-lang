import Foundation
import InkuUI

/// Failure: hourly settings are rounded on read, calendar days become elapsed hours, a manual/failed
/// snapshot advances the auto deadline, or concurrent checks prune old copies before a verified replacement.
@MainActor
func runBackupScheduleParityChecks() async throws {
    let parser = ISO8601DateFormatter()
    func date(_ value: String) throws -> Date {
        guard let result = parser.date(from: value) else { throw CheckFailure.message("Invalid backup fixture date") }
        return result
    }
    var local = Calendar(identifier: .gregorian)
    local.timeZone = TimeZone(identifier: "America/Los_Angeles")!
    let west = local
    let now = try date("2026-10-16T04:00:00-07:00")
    var schedule = BackupSchedule()
    schedule.intervalDays = 1; schedule.hour = 2; schedule.minute = 30
    let springLast = try date("2026-03-07T23:50:00-08:00")
    let springDue = try schedule.nextDate(lastAutomaticSuccess: springLast, now: now, calendar: west)
    guard springDue == (try date("2026-03-08T03:30:00-07:00")),
          try schedule.nextDate(lastAutomaticSuccess: nil, now: now, calendar: west) == now else {
        throw CheckFailure.message("Calendar backup did not use the next local date and DST-adjusted time: \(parser.string(from: springDue))")
    }
    schedule.hour = 1; schedule.minute = 30
    guard try schedule.nextDate(lastAutomaticSuccess: date("2026-10-31T23:50:00-07:00"), now: now, calendar: west)
            == date("2026-11-01T01:30:00-07:00") else { throw CheckFailure.message("Repeated backup time did not use its first occurrence") }
    var east = west
    east.timeZone = TimeZone(identifier: "Asia/Tokyo")!
    schedule.hour = 2; schedule.minute = 30
    guard try schedule.nextDate(lastAutomaticSuccess: springLast, now: now, calendar: east)
            == date("2026-03-09T02:30:00+09:00"), springDue < now else {
        throw CheckFailure.message("Time zone change or overdue resume did not recalculate the local date")
    }
    var preferences = try DisplayPreferences.decodeInterfaceFile(Data(#"{"backupIntervalHours":27,"backupGenerations":9}"#.utf8))
    guard preferences.usesLegacyBackupInterval, preferences.backupIntervalHours == 27, preferences.automaticBackupRetention == 9,
          try preferences.nextAutomaticBackupDate(lastSuccess: springLast, now: now, calendar: west) == springLast.addingTimeInterval(27 * 3600) else {
        throw CheckFailure.message("Legacy backup hours were rounded to days")
    }
    for _ in 0..<2 { preferences = try DisplayPreferences.decodeInterfaceFile(JSONEncoder().encode(preferences)) }
    guard preferences.usesLegacyBackupInterval, preferences.backupIntervalHours == 27 else { throw CheckFailure.message("Backup migration repeated") }
    for invalid in [0, 366] {
        var rejected = schedule; rejected.intervalDays = invalid
        do { try preferences.applyBackupSchedule(rejected); throw CheckFailure.message("Invalid backup days were accepted") }
        catch BackupScheduleFailure.invalidValues { }
    }
    for (generations, hour, minute) in [(0, 3, 0), (101, 3, 0), (4, 24, 0), (4, 3, 60)] {
        var rejected = schedule; rejected.maxGenerations = generations; rejected.hour = hour; rejected.minute = minute
        do { try preferences.applyBackupSchedule(rejected); throw CheckFailure.message("Invalid backup retention/time were accepted") }
        catch BackupScheduleFailure.invalidValues { }
    }
    guard preferences.usesLegacyBackupInterval, preferences.backupIntervalHours == 27 else { throw CheckFailure.message("Invalid backup edit mutated legacy settings") }
    let fresh = DisplayPreferences()
    let oldMissing = try DisplayPreferences.decodeInterfaceFile(Data("{}".utf8))
    guard !fresh.usesLegacyBackupInterval, fresh.backupSchedule.intervalDays == 7, fresh.automaticBackupRetention == 4,
          fresh.backupSchedule.hour == 3, oldMissing.usesLegacyBackupInterval, oldMissing.backupIntervalHours == 24 else {
        throw CheckFailure.message("New backup defaults or old missing fields were not distinguished")
    }

    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-backup-schedule-" + UUID().uuidString)
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let maintenance = LocalMaintenance(directory: folder, now: { now }, calendar: { west })
    await maintenance.refreshBackupInfo()
    guard try FileManager.default.contentsOfDirectory(atPath: folder.path).isEmpty else { throw CheckFailure.message("Reading backup information created files") }
    let copies = folder.appendingPathComponent("automatic-backups", isDirectory: true)
    try FileManager.default.createDirectory(at: copies, withIntermediateDirectories: true)
    let oldNames = ["inku-auto-1.sqlite", "inku-auto-2.sqlite"]
    for name in oldNames { try Data("old automatic fixture".utf8).write(to: copies.appendingPathComponent(name)) }
    let unowned = copies.appendingPathComponent("inku-auto-unowned.sqlite")
    let manual = folder.appendingPathComponent("manual.sqlite")
    try Data("unowned fixture".utf8).write(to: unowned)
    try Data("manual fixture".utf8).write(to: manual)
    let last = try date("2026-10-14T22:00:00-07:00")
    let manifestURL = folder.appendingPathComponent("automatic-backups.json")
    let manifest = try JSONSerialization.data(withJSONObject: ["lastSuccess": last.timeIntervalSinceReferenceDate, "files": oldNames], options: .sortedKeys)
    try manifest.write(to: manifestURL)
    await maintenance.refreshBackupInfo()
    guard maintenance.backupLastSuccess == last, maintenance.backupGenerations.count == 2,
          try Data(contentsOf: manifestURL) == manifest else { throw CheckFailure.message("Reading/manual fixture changed the automatic manifest") }
    schedule.hour = 3; schedule.minute = 0; schedule.maxGenerations = 1
    try preferences.applyBackupSchedule(schedule)
    preferences.automaticBackup = true
    guard !preferences.usesLegacyBackupInterval, preferences.backupIntervalHours == 27 else { throw CheckFailure.message("Saving a calendar schedule changed the stored legacy interval") }
    await maintenance.checkAutomaticBackup(preferences: preferences) { url in
        try Data("partial snapshot".utf8).write(to: url)
        return false
    }
    guard maintenance.backupError != nil, try Data(contentsOf: manifestURL) == manifest,
          oldNames.allSatisfy({ FileManager.default.fileExists(atPath: copies.appendingPathComponent($0).path) }) else {
        throw CheckFailure.message("A failed automatic snapshot advanced the date or pruned old generations")
    }
    await maintenance.checkAutomaticBackup(preferences: preferences) { _ in throw BackupScheduleFailure.invalidDate }
    guard try Data(contentsOf: manifestURL) == manifest else { throw CheckFailure.message("A thrown snapshot changed the automatic manifest") }
    await maintenance.checkAutomaticBackup(preferences: preferences) { _ in true }
    guard try Data(contentsOf: manifestURL) == manifest else { throw CheckFailure.message("A missing replacement was recorded as successful") }
    var creates = 0
    var duplicates = 0
    await maintenance.checkAutomaticBackup(preferences: preferences) { url in
        creates += 1
        await maintenance.checkAutomaticBackup(preferences: preferences) { _ in duplicates += 1; return false }
        try Data("verified automatic fixture".utf8).write(to: url)
        return true
    }
    guard creates == 1, duplicates == 0, maintenance.backupLastSuccess == now,
          maintenance.backupGenerations.count == 1, maintenance.backupError == nil,
          oldNames.allSatisfy({ !FileManager.default.fileExists(atPath: copies.appendingPathComponent($0).path) }),
          FileManager.default.fileExists(atPath: unowned.path), FileManager.default.fileExists(atPath: manual.path) else {
        throw CheckFailure.message("Automatic backup reentered, pruned unowned/manual files, or failed to retain its verified replacement")
    }
    await maintenance.checkAutomaticBackup(preferences: preferences) { _ in creates += 1; return false }
    guard creates == 1 else { throw CheckFailure.message("An automatic snapshot repeated before its next local deadline") }
    let retainedName = maintenance.backupGenerations[0].name
    let successfulRecord = try Data(contentsOf: manifestURL)
    let future = now.addingTimeInterval(3 * 86400)
    let blockedRecord = LocalMaintenance(directory: folder, now: { future }, calendar: { west })
    let parkedManifest = folder.appendingPathComponent("manifest-fixture.json")
    await blockedRecord.checkAutomaticBackup(preferences: preferences) { url in
        try Data("verified but unrecorded fixture".utf8).write(to: url)
        // The record becomes unavailable after the snapshot, before its success can be committed.
        try FileManager.default.moveItem(at: manifestURL, to: parkedManifest)
        try FileManager.default.createDirectory(at: manifestURL, withIntermediateDirectories: false)
        return true
    }
    guard blockedRecord.backupError != nil, try Data(contentsOf: parkedManifest) == successfulRecord,
          FileManager.default.fileExists(atPath: copies.appendingPathComponent(retainedName).path),
          FileManager.default.fileExists(atPath: unowned.path), FileManager.default.fileExists(atPath: manual.path) else {
        throw CheckFailure.message("A manifest failure pruned a previous or unowned backup")
    }
    print("Backup schedule passed: legacy preservation, day/time bounds, new defaults, DST and time zone dates, read-only status, manual/failed/missing replacement isolation, manifest failure, reentry exclusion, owned-only retention after success. Fixed clocks and temporary files only; no database backup/restore.")
}
