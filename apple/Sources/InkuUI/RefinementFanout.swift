/// Web `refinement-fanout.ts` `runRefinementFanout`: run indexed jobs at most `limit` at a time, starting them in
/// order and reporting each start, so every lane shows the job it is doing. A thrown error (a stop) cancels the rest.
import InkuHost

public enum RefinementFanout {
    public static let defaultLimit = 4

    public static func validatedLimit(_ value: Int) throws -> Int {
        guard (1...16).contains(value) else { throw HostError("invalid_refinement_fanout_limit") }
        return value
    }

    @MainActor
    public static func run(count: Int, limit: Int, onStart: @MainActor (Int) -> Void,
                    job: @escaping @MainActor @Sendable (Int) async throws -> Void) async throws {
        let width = try validatedLimit(limit)
        guard count >= 0 else { throw HostError("invalid_refinement_fanout_count") }
        try Task.checkCancellation()
        try await withThrowingTaskGroup(of: Void.self) { group in
            var running = 0
            for index in 0..<count {
                if running == width { try await group.next(); running -= 1 }
                try Task.checkCancellation()
                onStart(index)
                try Task.checkCancellation()
                group.addTask { try Task.checkCancellation(); try await job(index) }
                running += 1
            }
            try await group.waitForAll()
        }
    }
}
