import CryptoKit
import Darwin
import Foundation
import Security

/// Only this nonsecret identity is persisted in queued requests and executions.
public struct ChatGPTPlanSession: Codable, Sendable, Equatable {
    public let profileID: String
    public let generation: Int64
    public init(profileID: String, generation: Int64) { self.profileID = profileID; self.generation = generation }
}

public struct ChatGPTPlanProfile: Identifiable, Sendable, Equatable {
    public let id: String
    public let label: String
    public let email: String?
    public let clientID: String
    public let state: String
    public let generation: Int64
    public let scopes: [String]
    public let expiresAt: Date
}

public struct ChatGPTPlanState: Sendable {
    public let enabled: Bool
    public let activeProfileID: String?
    public let profiles: [ChatGPTPlanProfile]
    public let pendingRegistrations: [String]
}

public struct ChatGPTPlanModel: Identifiable, Codable, Sendable, Equatable {
    public let id: String
    public let label: String
    public init(id: String, label: String) { self.id = id; self.label = label }
}

struct ChatGPTStoredProfile: Codable, Sendable {
    var id: String
    var issuer: String
    var subject: String
    var email: String?
    var clientID: String
    var label: String
    var state: String
    var generation: Int64
    var accessToken: String?
    var refreshToken: String?
    var idToken: String?
    var scopes: [String]
    var expiresAt: Date
    var earliestRefreshAt: Date
    var models: [ChatGPTPlanModel]?
    var modelsExpireAt: Date?
    var publicValue: ChatGPTPlanProfile {
        .init(id: id, label: label, email: email, clientID: clientID, state: state,
              generation: generation, scopes: scopes, expiresAt: expiresAt)
    }
    mutating func removeTokens() { accessToken = nil; refreshToken = nil; idToken = nil; models = nil; modelsExpireAt = nil }
}

struct ChatGPTVaultState: Codable, Sendable {
    var schema = "inku.chatgpt-plan.v1"
    var enabled = false
    var hostID: String?
    var activeProfileID: String?
    var profiles: [String: ChatGPTStoredProfile] = [:]
    var pendingRegistrations: [String: String] = [:]
    var publicValue: ChatGPTPlanState {
        .init(enabled: enabled, activeProfileID: activeProfileID,
              profiles: profiles.values.map(\.publicValue).sorted { $0.id < $1.id },
              pendingRegistrations: pendingRegistrations.keys.filter { profiles[$0] == nil }.sorted())
    }
}

/// A synchronous, atomic Keychain item is the vault key, never a plaintext token fallback.
protocol ChatGPTVaultKeyStore: Sendable {
    func readKey() throws -> Data?
    func saveKey(_ key: Data) throws
}

struct ChatGPTKeychainVaultKeyStore: ChatGPTVaultKeyStore {
    let account: String
    private var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: "app.inku.chatgpt-plan.vault-key",
         kSecAttrAccount as String: account, kSecAttrSynchronizable as String: false]
    }
    func readKey() throws -> Data? {
        var query = query; query[kSecReturnData as String] = true; query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = result as? Data, data.count == 32 else { throw HostError("chatgpt_credentials_unavailable") }
        return data
    }
    func saveKey(_ key: Data) throws {
        var query = query; query[kSecValueData as String] = key
        query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else { throw HostError("chatgpt_credentials_write_failed") }
    }
}

/// Profiles, identity and rotated tokens have a single atomic encrypted-file commit.
struct ChatGPTPlanStore: Sendable {
    private static let maximumBytes = 1_048_576
    let directory: URL
    let keys: any ChatGPTVaultKeyStore
    var stateURL: URL { directory.appendingPathComponent("profiles.sealed") }
    init(directory: URL, keys: (any ChatGPTVaultKeyStore)? = nil) {
        self.directory = directory
        let account = SHA256.hash(data: Data(directory.standardizedFileURL.path.utf8)).map { String(format: "%02x", $0) }.joined()
        self.keys = keys ?? ChatGPTKeychainVaultKeyStore(account: account)
    }
    func load() throws -> ChatGPTVaultState {
        guard FileManager.default.fileExists(atPath: stateURL.path) else { return .init() }
        try checkDirectory()
        let descriptor = Darwin.open(stateURL.path, O_RDONLY | O_NOFOLLOW)
        guard descriptor >= 0 else { throw HostError("chatgpt_credentials_unavailable") }
        defer { Darwin.close(descriptor) }
        var info = stat()
        guard fstat(descriptor, &info) == 0, info.st_mode & S_IFMT == S_IFREG,
              info.st_mode & 0o077 == 0, info.st_uid == getuid(), info.st_size <= Self.maximumBytes,
              let key = try keys.readKey() else { throw HostError("chatgpt_credentials_unavailable") }
        var data = Data(); var buffer = [UInt8](repeating: 0, count: 16384)
        while true {
            let count = Darwin.read(descriptor, &buffer, buffer.count)
            guard count >= 0 else { throw HostError("chatgpt_credentials_unavailable") }
            if count == 0 { break }
            guard data.count + count <= Self.maximumBytes else { throw HostError("chatgpt_storage_full") }
            data.append(contentsOf: buffer.prefix(count))
        }
        do {
            let value = try JSONDecoder().decode(ChatGPTVaultState.self,
                from: AES.GCM.open(AES.GCM.SealedBox(combined: data), using: SymmetricKey(data: key)))
            guard value.schema == "inku.chatgpt-plan.v1", value.profiles.count <= 8, value.pendingRegistrations.count <= 8 else {
                throw HostError("chatgpt_credentials_unavailable")
            }
            return value
        } catch { throw HostError("chatgpt_credentials_unavailable") }
    }
    func write(_ value: ChatGPTVaultState) throws {
        try ensureDirectory()
        guard value.profiles.count <= 8, value.pendingRegistrations.count <= 8 else { throw HostError("chatgpt_profile_limit") }
        let key: Data
        if let existing = try keys.readKey() { key = existing }
        else {
            var bytes = [UInt8](repeating: 0, count: 32)
            guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else { throw HostError("chatgpt_credentials_write_failed") }
            key = Data(bytes); try keys.saveKey(key)
        }
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
        guard let data = try AES.GCM.seal(encoder.encode(value), using: SymmetricKey(data: key)).combined,
              data.count <= Self.maximumBytes else { throw HostError("chatgpt_storage_full") }
        let temporary = directory.appendingPathComponent(".profiles-" + UUID().uuidString)
        let descriptor = Darwin.open(temporary.path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0o600)
        guard descriptor >= 0 else { throw HostError("chatgpt_credentials_write_failed") }
        defer { Darwin.close(descriptor); try? FileManager.default.removeItem(at: temporary) }
        try data.withUnsafeBytes { bytes in
            var offset = 0
            while offset < bytes.count {
                let count = Darwin.write(descriptor, bytes.baseAddress!.advanced(by: offset), bytes.count - offset)
                guard count > 0 else { throw HostError("chatgpt_credentials_write_failed") }; offset += count
            }
        }
        guard fsync(descriptor) == 0, Darwin.rename(temporary.path, stateURL.path) == 0 else { throw HostError("chatgpt_credentials_write_failed") }
        let directoryFD = Darwin.open(directory.path, O_RDONLY | O_NOFOLLOW)
        guard directoryFD >= 0 else { throw HostError("chatgpt_credentials_write_failed") }
        defer { Darwin.close(directoryFD) }
        guard fsync(directoryFD) == 0 else { throw HostError("chatgpt_credentials_write_failed") }
    }
    func ensureDirectory() throws {
        if !FileManager.default.fileExists(atPath: directory.path) {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                attributes: [.posixPermissions: 0o700])
        }
        try checkDirectory()
    }
    private func checkDirectory() throws {
        var info = stat()
        guard lstat(directory.path, &info) == 0, info.st_mode & S_IFMT == S_IFDIR,
              info.st_mode & 0o077 == 0, info.st_uid == getuid() else { throw HostError("chatgpt_credentials_unavailable") }
    }
    func lease(_ name: String, deadline: Date, check: @escaping @Sendable () async throws -> Void = {}) async throws -> ChatGPTFileLease {
        guard name.range(of: "^[A-Za-z0-9-]{1,80}$", options: .regularExpression) != nil else { throw HostError("chatgpt_session_stale") }
        try ensureDirectory()
        let location = directory.appendingPathComponent(name + ".lock")
        let descriptor = Darwin.open(location.path, O_RDWR | O_CREAT | O_NOFOLLOW, 0o600)
        guard descriptor >= 0 else { throw HostError("chatgpt_credentials_unavailable") }
        var adopted = false; defer { if !adopted { Darwin.close(descriptor) } }
        var info = stat()
        guard fstat(descriptor, &info) == 0, info.st_mode & S_IFMT == S_IFREG,
              info.st_mode & 0o077 == 0, info.st_uid == getuid() else { throw HostError("chatgpt_credentials_unavailable") }
        while true {
            try Task.checkCancellation(); try await check()
            guard Date() < deadline else { throw HostError("chatgpt_transport_timeout") }
            if flock(descriptor, LOCK_EX | LOCK_NB) == 0 { adopted = true; return ChatGPTFileLease(descriptor) }
            guard errno == EWOULDBLOCK || errno == EAGAIN else { throw HostError("chatgpt_credentials_unavailable") }
            try await Task.sleep(for: .milliseconds(100))
        }
    }
}

final class ChatGPTFileLease: @unchecked Sendable {
    private let descriptor: Int32
    init(_ descriptor: Int32) { self.descriptor = descriptor }
    deinit { flock(descriptor, LOCK_UN); Darwin.close(descriptor) }
}
