import Foundation

/// A file or folder the author chose outside the app (iOS plan §3 #5). iOS lends access to it only while it is
/// opened, and an iCloud file may still be in the cloud; macOS runs without the sandbox, so opening its URLs does
/// nothing and its files are read as before.
enum InkuSecurityScope {
    /// Runs `body` while the URL's access is open, and closes it afterwards.
    static func access<T>(_ url: URL, _ body: () throws -> T) rethrows -> T {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        return try body()
    }

    /// The whole file. On iOS a coordinated read first brings a file iCloud has not downloaded onto the device.
    static func read(_ url: URL) throws -> Data {
        try access(url) {
            #if os(iOS)
            try coordinatedRead(url) { try Data(contentsOf: $0) }
            #else
            try Data(contentsOf: url)
            #endif
        }
    }

    /// Brings the file onto the device before a reader that opens it itself (the restore, the DDL import).
    static func download(_ url: URL) throws {
        #if os(iOS)
        try access(url) { try coordinatedRead(url) { _ in } }
        #endif
    }

    #if os(iOS)
    private static func coordinatedRead<T>(_ url: URL, _ body: (URL) throws -> T) throws -> T {
        var result: Result<T, Error>?
        var coordinationError: NSError?
        NSFileCoordinator().coordinate(readingItemAt: url, options: [], error: &coordinationError) { readable in
            result = Result { try body(readable) }
        }
        if let coordinationError { throw coordinationError }
        guard let result else { throw CocoaError(.fileReadUnknown) }
        return try result.get()
    }
    #endif
}
