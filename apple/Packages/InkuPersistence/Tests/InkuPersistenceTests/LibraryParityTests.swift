import Foundation
import GRDB
import Testing
@testable import InkuPersistence

struct LibraryParityTests {
    private func url() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("inku-library-parity-\(UUID().uuidString)")
            .appendingPathComponent("test.sqlite")
    }

    private func record(_ id: String, at: Int64, root: String? = nil) -> (SavedWork, LineageNode) {
        let nodeID = "node-\(id)"
        let hash = "rh3:" + String(repeating: "a", count: 60) + "abcd"
        let work = SavedWork(id: id, at: at, input: id, score: "{ \"future\": [1, null] }",
                             svg: "<svg>exact\r\n</svg>", ddl: "  exact\r\nDDL  ",
                             renderSeed: "18446744073709551615", compositionSeed: "0007",
                             renderHash: hash, descriptionHash: "dh1:exact", lineageNodeID: nodeID)
        return (work, LineageNode(id: nodeID, historyID: id, at: at, descriptionHash: work.descriptionHash,
                                  renderHash: hash, rootNodeID: root ?? nodeID))
    }

    @Test func databaseSearchBeyondRecentHundredAndIndependentFilters() async throws {
        let file = url()
        defer { try? FileManager.default.removeItem(at: file.deletingLastPathComponent()) }
        let db = try InkuDatabase(url: file)
        for index in 0...100 {
            let (work, node) = record("work-\(index)", at: Int64(index))
            try await db.save(work, node: node)
        }
        let oldest = try await db.libraryPage(query: LibraryQuery(text: "work-0"), limit: 1)
        #expect(oldest.total == 1)
        #expect(oldest.items.first?.id == "work-0")
        let boundary = try await db.libraryPage(limit: 1, offset: 100)
        #expect(boundary.total == 101)
        #expect(boundary.items.first?.id == "work-0")
        let shortHash = try await db.libraryPage(query: LibraryQuery(text: "ABCD"), limit: 1)
        #expect(shortHash.total == 101)
        let fullHash = "rh3:" + String(repeating: "a", count: 60) + "abcd"
        #expect(try await db.libraryPage(query: LibraryQuery(text: fullHash), limit: 1).total == 101)
        #expect(try await db.libraryPage(query: LibraryQuery(text: String(fullHash.dropFirst(4))), limit: 1).total == 101)

        try await db.setStarred(ids: ["work-0", "work-1"], starred: true)
        try await db.setAnnotation(id: "work-0", forRevision: true, forShare: true)
        try await db.setAnnotation(id: "work-2", forRevision: true)
        let both = try await db.libraryPage(query: LibraryQuery(starred: true, forRevision: true, forShare: true))
        #expect(both.items.map(\.id) == ["work-0"])
        try await db.setStarred(ids: ["work-0"], starred: false)
        #expect(try await db.libraryPage(query: LibraryQuery(forRevision: true)).total == 2)
        #expect(try await db.libraryPage(query: LibraryQuery(starred: true, forRevision: true)).total == 0)
        let ascending = try await db.libraryPage(query: LibraryQuery(order: .oldest), limit: 2)
        #expect(ascending.items.map(\.id) == ["work-0", "work-1"])
        try await db.setTrashed(ids: ["work-0"], trashed: true)
        #expect(try await db.libraryPage(query: LibraryQuery(text: "work-0")).total == 0)
        #expect(try await db.libraryPage(query: LibraryQuery(text: "work-0", trashed: true)).total == 1)
    }

    @Test func deletionPreservesOriginalLineageAndImmutableContent() async throws {
        let file = url()
        defer { try? FileManager.default.removeItem(at: file.deletingLastPathComponent()) }
        let db = try InkuDatabase(url: file)
        let (root, rootNode) = record("root", at: 1)
        let (child, childNode) = record("child", at: 2, root: rootNode.id)
        let edge = LineageEdge(id: "edge-child", parentNodeID: rootNode.id, childNodeID: childNode.id,
                               derivationKind: "ddl_edit", metadataJSON: "{\"private_source\":\"exact\"}", at: 2)
        try await db.save(root, node: rootNode)
        try await db.save(child, node: childNode, edge: edge)
        let note = " \n" + String(repeating: "e\u{301}", count: 140) + " \n"
        try await db.setAnnotation(id: root.id, note: note, forRevision: true, forShare: true)
        #expect(try await db.libraryPage(query: LibraryQuery(text: "root")).items.first?.annotation.note?.unicodeScalars.count == 240)
        #expect(try await db.work(id: root.id) == root)
        let groups = try await db.libraryGroups()
        #expect(groups.total == 1)
        #expect(groups.groups.first?.itemCount == 2)
        #expect(groups.groups.first?.representative.id == child.id)
        #expect(try await db.libraryGroups(minimumItemCount: 3).total == 0)
        #expect(try await db.libraryPage(rootNodeID: rootNode.id).total == 2)
        #expect(try await db.permanentlyDelete(ids: [root.id]) == 0)
        try await db.setTrashed(ids: [root.id], trashed: true)
        #expect(try await db.trashCount() == 1)
        await #expect(throws: PersistenceError.invalidRecord("selection is no longer exportable")) {
            try await db.exportWorks(ids: [root.id])
        }
        try await db.setTrashed(ids: [root.id], trashed: false)
        #expect(try await db.exportWorks(ids: [child.id, root.id]) == [child, root])
        try await db.setTrashed(ids: [root.id], trashed: true)
        #expect(try await db.permanentlyDelete(ids: [root.id], deletedAt: 99) == 1)
        #expect(try await db.work(id: root.id) == nil)
        #expect(try await db.work(id: child.id) == child)
        let tombstone = try await db.node(id: rootNode.id)
        #expect(tombstone?.id == rootNode.id && tombstone?.rootNodeID == rootNode.id && tombstone?.at == rootNode.at)
        #expect(tombstone?.state == "tombstone" && tombstone?.deletedAt == 99)
        #expect(tombstone?.historyID == nil && tombstone?.descriptionHash == nil && tombstone?.renderHash == nil)
        let keptEdge = try await db.edge(childNodeID: childNode.id)
        #expect(keptEdge?.id == edge.id && keptEdge?.parentNodeID == rootNode.id && keptEdge?.metadataJSON == "{}")
        let path = try await db.lineage(focusNodeID: childNode.id, pathOnly: true)
        #expect(path?.nodes.map(\.id) == [rootNode.id, childNode.id])
        #expect(path?.nodes.map(\.generation) == [1, 2])
        #expect(path?.nodes.first?.work == nil)
        #expect(try await db.libraryGroups().groups.first?.rootNodeID == rootNode.id)
    }

    @Test func historyGenerationProjectionCountsPrimaryParentsAndTombstones() async throws {
        let file = url()
        defer { try? FileManager.default.removeItem(at: file.deletingLastPathComponent()) }
        let db = try InkuDatabase(url: file)
        let (root, rootNode) = record("root", at: 1)
        let (child, childNode) = record("child", at: 2, root: rootNode.id)
        try await db.save(root, node: rootNode)
        try await db.save(child, node: childNode, edge: LineageEdge(id: "edge-child", parentNodeID: rootNode.id,
            childNodeID: childNode.id, derivationKind: "ddl_edit", at: child.at))
        let nodeIDs = [rootNode.id, childNode.id, "missing-node", childNode.id]
        #expect(try await db.lineageGenerations(nodeIDs: nodeIDs) == [rootNode.id: 1, childNode.id: 2])
        try await db.setTrashed(ids: [root.id], trashed: true)
        #expect(try await db.permanentlyDelete(ids: [root.id]) == 1)
        #expect(try await db.lineageGenerations(nodeIDs: nodeIDs) == [rootNode.id: 1, childNode.id: 2])
    }

    @Test func rootOverviewFromLeafIncludesSiblingBranches() async throws {
        let file = url()
        defer { try? FileManager.default.removeItem(at: file.deletingLastPathComponent()) }
        let db = try InkuDatabase(url: file)
        let (root, rootNode) = record("root", at: 1)
        let (branch, branchNode) = record("branch", at: 2, root: rootNode.id)
        let (leaf, leafNode) = record("leaf", at: 3, root: rootNode.id)
        let (sibling, siblingNode) = record("sibling", at: 4, root: rootNode.id)
        try await db.save(root, node: rootNode)
        try await db.save(branch, node: branchNode, edge: LineageEdge(id: "edge-branch", parentNodeID: rootNode.id,
            childNodeID: branchNode.id, derivationKind: "variation", at: branch.at))
        try await db.save(leaf, node: leafNode, edge: LineageEdge(id: "edge-leaf", parentNodeID: branchNode.id,
            childNodeID: leafNode.id, derivationKind: "variation", at: leaf.at))
        try await db.save(sibling, node: siblingNode, edge: LineageEdge(id: "edge-sibling", parentNodeID: rootNode.id,
            childNodeID: siblingNode.id, derivationKind: "variation", at: sibling.at))

        let overview = try await db.lineageOverview(focusNodeID: leafNode.id)
        #expect(overview?.focusNodeID == leafNode.id)
        #expect(Set(overview?.nodes.map(\.id) ?? []) == [rootNode.id, branchNode.id, leafNode.id, siblingNode.id])
        #expect(Set(overview?.edges.map(\.id) ?? []) == ["edge-branch", "edge-leaf", "edge-sibling"])
        let depthZero = try await db.lineage(focusNodeID: branchNode.id, descendantDepth: 0)
        #expect(Set(depthZero?.nodes.map(\.id) ?? []) == [rootNode.id, branchNode.id])
        let depthOne = try await db.lineage(focusNodeID: branchNode.id, descendantDepth: 1)
        #expect(Set(depthOne?.nodes.map(\.id) ?? []) == [rootNode.id, branchNode.id, leafNode.id])
        let path = try await db.lineage(focusNodeID: leafNode.id, pathOnly: true)
        #expect(path?.nodes.map(\.id) == [rootNode.id, branchNode.id, leafNode.id])
        let bounded = try await db.lineageOverview(focusNodeID: leafNode.id, nodeLimit: 2)
        #expect(bounded?.nodes.count == 2 && bounded?.truncated == true)
    }

    @Test func exactSchemaOneMigrationAndIsolatedLegacyRestore() async throws {
        let file = url()
        defer { try? FileManager.default.removeItem(at: file.deletingLastPathComponent()) }
        try FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
        let baseline = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("Sources/InkuPersistence/Resources/schema-v1.sql")
        let old = try DatabaseQueue(path: file.path)
        let (work, node) = record("legacy", at: 1)
        try await old.write { db in
            try db.execute(sql: String(contentsOf: baseline, encoding: .utf8))
            try work.insert(db); try node.insert(db)
            try db.execute(sql: "INSERT INTO execution_snapshots VALUES ('execution', 1, ?)", arguments: [Data([0, 255])])
            try db.execute(sql: "INSERT INTO effect_acknowledgements VALUES ('execution', 'effect', 1, ?, ?, ?)",
                           arguments: [Data([0, 255]), Data([9, 255]), Data([8])])
        }
        try old.close()
        let legacyBackup = file.deletingLastPathComponent().appendingPathComponent("legacy-backup.sqlite")
        try FileManager.default.copyItem(at: file, to: legacyBackup)
        let backupBytes = try Data(contentsOf: legacyBackup)
        let db = try InkuDatabase(url: file)
        #expect(try await db.work(id: work.id) == work)
        #expect(try await db.loadExecution(id: "execution")?.snapshot == Data([0, 255]))
        #expect(try await db.acknowledgement(executionID: "execution", effectID: "effect") == Data([9, 255]))
        try await db.setAnnotation(id: work.id, note: "local comment", forRevision: true)
        let modernBackup = file.deletingLastPathComponent().appendingPathComponent("modern-backup.sqlite")
        try await db.backup(to: modernBackup)
        try await db.restore(from: legacyBackup)
        #expect(try Data(contentsOf: legacyBackup) == backupBytes)
        #expect(try await db.work(id: work.id) == work)
        #expect(try await db.libraryPage().items.first?.annotation.note == nil)
        try await db.restore(from: modernBackup)
        #expect(try await db.libraryPage().items.first?.annotation.note == "local comment")
        let forged = try DatabaseQueue(path: legacyBackup.path)
        try await forged.write { try $0.execute(sql: "CREATE TABLE unexpected (id TEXT)") }
        try forged.close()
        let forgedBytes = try Data(contentsOf: legacyBackup)
        #expect(throws: PersistenceError.unknownSchema) { try InkuDatabase(url: legacyBackup) }
        #expect(try Data(contentsOf: legacyBackup) == forgedBytes)
        await #expect(throws: PersistenceError.unknownSchema) { try await db.restore(from: legacyBackup) }
        #expect(try await db.libraryPage().items.first?.annotation.note == "local comment")
    }
}
