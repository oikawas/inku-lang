/// Web `refinement-fanout.ts` `runRefinementFanout`: run indexed jobs at most `limit` at a time, starting them in
/// order and reporting each start, so every lane shows the job it is doing. A thrown error (a stop) cancels the rest.
enum RefinementFanout {
    /// Server `render_fanout_limit` defaults to 4 (`INKU_CLIENT_FANOUT_LIMIT`); Swift has no Server to set it.
    static let limit = 4

    @MainActor
    static func run(count: Int, limit: Int = RefinementFanout.limit, onStart: @MainActor (Int) -> Void,
                    job: @escaping @MainActor @Sendable (Int) async throws -> Void) async throws {
        let width = max(1, limit)
        try await withThrowingTaskGroup(of: Void.self) { group in
            var running = 0
            for index in 0..<count {
                if running == width { try await group.next(); running -= 1 }
                onStart(index)
                group.addTask { try await job(index) }
                running += 1
            }
            try await group.waitForAll()
        }
    }
}
