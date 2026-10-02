import Foundation

/// Installation choices apply to new works; saved performance definitions stay pinned.
public struct PluginPreferences: Codable, Sendable, Equatable {
    public var disabledPackageIDs: Set<String>
    public init(disabledPackageIDs: Set<String> = []) { self.disabledPackageIDs = disabledPackageIDs }
    public func isEnabled(_ packageID: String) -> Bool { !disabledPackageIDs.contains(packageID) }
    public mutating func setEnabled(_ enabled: Bool, packageID: String) {
        if enabled { disabledPackageIDs.remove(packageID) } else { disabledPackageIDs.insert(packageID) }
    }
}
