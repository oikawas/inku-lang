import Foundation

/// Local single-user aggregation of the Server's interpretation feedback ledger.
public struct UnreadWord: Sendable, Equatable, Identifiable {
    public let word: String
    public let frequency: Int
    public let firstAt: Int64
    public let lastAt: Int64
    public let contexts: [String]
    public var id: String { word }
}
