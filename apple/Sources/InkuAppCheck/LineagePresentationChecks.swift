import Foundation
import InkuPersistence
import InkuUI

@MainActor
func runLineagePresentationChecks() async throws {
    // Mapped failure: cards lacked connections; expanding a branch replaced the focus;
    // opening the map changed normal browsing and had no bounded zoom/return path.
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-lineage-presentation-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let database = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
    let root = "lineage-root"
    let ids = [root, "lineage-branch", "lineage-sibling", "lineage-deleted", "lineage-star"]
    let parents: [String: String] = [ids[1]: root, ids[2]: root, ids[3]: ids[1], ids[4]: ids[3]]
    for (index, id) in ids.enumerated() {
        let work = SavedWork(id: "work-\(id)", at: Int64(index + 1), input: "saved \(id)", score: "{}",
                             svg: "<svg xmlns=\"http://www.w3.org/2000/svg\"><desc>\(id)</desc></svg>",
                             starred: index == 4, lineageNodeID: id)
        let edge = parents[id].map { LineageEdge(id: "edge-\(id)", parentNodeID: $0, childNodeID: id,
                                               derivationKind: "variation", at: work.at) }
        try await database.save(work, node: LineageNode(id: id, historyID: work.id, at: work.at,
            descriptionHash: index < 3 ? "dh1:shared-text" : nil,
            renderHash: index < 2 ? "rh3:shared-edition" : "rh3:\(id)", rootNodeID: root), edge: edge)
    }
    _ = try await database.permanentlyDelete(ids: ["work-\(ids[3])"], requireTrashed: false, deletedAt: 10)
    let savedBefore = try await database.list()
    guard let lineageBefore = try await database.lineageOverview(focusNodeID: root),
          lineageBefore.nodes.count == 5, lineageBefore.edges.count == 4 else {
        throw CheckFailure.message("Lineage fixture must retain exactly five nodes/four edges, including the deleted middle node")
    }
    let reader = LineageCountingReader(database: database)
    let library = LibraryModel(lineageReader: reader)
    await library.connect(database: database)
    library.selectedIDs = ["work-\(root)"]
    await library.loadLineage(nodeID: root)
    guard library.lineageVertical, let initial = library.lineageDisplayGraph,
          initial.focusNodeID == root,
          LineagePresentation.visibleIDs(initial, browsing: library.lineageBrowsing) == Set(ids.prefix(3)),
          initial.nodes.count == 4 else {
        throw CheckFailure.message("Normal lineage must start vertically with focus children visible and deeper branches collapsed")
    }
    await library.toggleLineageBranch(ids[1]) // Already read: no branch query.
    await library.toggleLineageBranch(ids[3]) // Missing child: exactly one SQLite branch query.
    guard let expanded = library.lineageDisplayGraph, expanded.focusNodeID == root,
          LineagePresentation.visibleIDs(expanded, browsing: library.lineageBrowsing) == Set(ids),
          library.selectedIDs == ["work-\(root)"], await reader.branchReads == [ids[3]: 1] else {
        throw CheckFailure.message("Branch expansion changed the focus/selection or failed to read only the missing child once")
    }
    let edges = LineagePresentation.edges(expanded, visibleIDs: Set(ids))
    guard Set(edges.map(\.id)) == Set(lineageBefore.edges.map(\.id)),
          Set(edges.filter(\.starredPath).map(\.id)) == Set([ids[1], ids[3], ids[4]].map { "edge-\($0)" }),
          Set(edges.filter(\.tombstone).map(\.id)) == Set([ids[3], ids[4]].map { "edge-\($0)" }) else {
        throw CheckFailure.message("Lineage connections lost the favorite ancestor route or the two edges incident to the tombstone")
    }
    let parent = CGRect(x: 10, y: 20, width: 100, height: 80)
    let vertical = LineagePresentation.connection(parent: parent, child: CGRect(x: 240, y: 180, width: 60, height: 100), vertical: true)
    let horizontal = LineagePresentation.connection(parent: parent, child: CGRect(x: 200, y: 240, width: 80, height: 100), vertical: false)
    guard vertical.start == CGPoint(x: 60, y: 101), vertical.end == CGPoint(x: 270, y: 173),
          horizontal.start == CGPoint(x: 111, y: 60), horizontal.end == CGPoint(x: 193, y: 290) else {
        throw CheckFailure.message("Parent-to-child arrows must attach outside the card's bottom/top or right/left edges")
    }
    await library.toggleLineageBranch(ids[3])
    await library.toggleLineageBranch(ids[3])
    await library.toggleLineageBranch(ids[3])
    guard let normal = library.lineageDisplayGraph,
          LineagePresentation.visibleIDs(normal, browsing: library.lineageBrowsing) == Set(ids.prefix(4)),
          await reader.branchReads == [ids[3]: 1] else {
        throw CheckFailure.message("Collapsing/reopening an already read branch must preserve ancestors and avoid another read")
    }
    library.lineageBrowsing.normalScroll = LineageScrollPosition(x: 17, y: 42)
    let normalBrowsing = library.lineageBrowsing
    let depth = library.lineageDepth
    let pathOnly = library.lineagePathOnly
    await library.loadLineageOverview()
    guard library.lineageBrowsing.overviewOpen, let overview = library.lineageDisplayGraph,
          overview.focusNodeID == root, LineagePresentation.visibleIDs(overview, browsing: library.lineageBrowsing) == Set(ids) else {
        throw CheckFailure.message("The independent overview must show every saved/tombstone node without moving the focus")
    }
    library.lineageBrowsing.setOverviewScale(0)
    guard library.lineageBrowsing.overviewScale == 0.4 else { throw CheckFailure.message("Map zoom must stop at 40 percent") }
    library.lineageBrowsing.setOverviewScale(2)
    guard library.lineageBrowsing.overviewScale == 1.4 else { throw CheckFailure.message("Map zoom must stop at 140 percent") }
    library.lineageBrowsing.overviewScroll = LineageScrollPosition(x: 71, y: 99)
    library.closeLineageOverview()
    guard !library.lineageBrowsing.overviewOpen, library.lineageDisplayGraph == normal,
          library.lineageBrowsing.expandedNodeIDs == normalBrowsing.expandedNodeIDs,
          library.lineageBrowsing.scroll == normalBrowsing.normalScroll,
          library.lineageBrowsing.overviewScroll == LineageScrollPosition(x: 71, y: 99),
          library.lineageDepth == depth, library.lineagePathOnly == pathOnly,
          library.selectedIDs == ["work-\(root)"], library.lineageError == nil,
          await reader.baseReads == 1, await reader.overviewReads == 1,
          await reader.branchReads == [ids[3]: 1],
          try await database.list() == savedBefore,
          try await database.lineageOverview(focusNodeID: root) == lineageBefore else {
        throw CheckFailure.message("Closing the map must restore normal browsing without another read or any saved-work/lineage mutation")
    }
    // Failure: lineage exports borrow the library's checkboxes or lose the origin-to-focus order.
    let selected = LineageSnapshot(lineageBefore, focusNodeID: ids[4])
    guard LineageWorkScope.focused(selected).workIDs == ["work-\(ids[4])"],
          LineageWorkScope.path(selected) == LineageExportRequest(workIDs: ["work-\(root)", "work-\(ids[1])", "work-\(ids[4])"], preserveOrder: true),
          LineageWorkScope.checked(selected, ids: ["work-\(ids[2])", "unrelated-library-id"]).workIDs == ["work-\(ids[2])"],
          library.selectedIDs == ["work-\(root)"] else {
        throw CheckFailure.message("Lineage export scopes mixed in library checks, missing work, or another branch")
    }
    // Failure: missing hashes or the focus itself receive a false same-text/edition badge.
    let byID = Dictionary(uniqueKeysWithValues: selected.nodes.map { ($0.id, $0) })
    guard LineageWorkScope.sameText(byID[root]!, focus: byID[ids[1]]),
          LineageWorkScope.sameEdition(byID[root]!, focus: byID[ids[1]]),
          LineageWorkScope.sameText(byID[ids[2]]!, focus: byID[ids[1]]),
          !LineageWorkScope.sameEdition(byID[ids[2]]!, focus: byID[ids[1]]),
          !LineageWorkScope.sameText(byID[ids[1]]!, focus: byID[ids[1]]),
          !LineageWorkScope.sameText(byID[ids[3]]!, focus: byID[ids[4]]) else {
        throw CheckFailure.message("Lineage identity badges inferred equality from absent hashes or the displayed work itself")
    }
    // Failure: closing the map drops checked descendants which the normal query did not load.
    let selectionLibrary = LibraryModel()
    await selectionLibrary.connect(database: database)
    await selectionLibrary.loadLineage(nodeID: root)
    guard selectionLibrary.lineageDisplayGraph?.nodes.contains(where: { $0.id == ids[4] }) == false else {
        throw CheckFailure.message("The map-only selection fixture must begin with its deep work unloaded")
    }
    await selectionLibrary.loadLineageOverview()
    selectionLibrary.closeLineageOverview()
    guard let known = selectionLibrary.lineageSelectionGraph,
          LineageWorkScope.checked(known, ids: ["work-\(ids[4])"]).workIDs == ["work-\(ids[4])"],
          selectionLibrary.lineageDisplayGraph?.nodes.contains(where: { $0.id == ids[4] }) == false else {
        throw CheckFailure.message("Map-only selection vanished or changed the normal branch snapshot")
    }
    // Failure: starting a new root erases the draft or leaves a saved parent selected.
    let app = AppModel(databaseURL: folder.appendingPathComponent("works.sqlite"))
    await app.initialize()
    await app.selectWork(savedBefore[0])
    app.descriptionText = "Detached description draft"; app.ddlText = "Another global instruction draft"
    app.setDdlBoxText("Detached instruction draft", for: savedBefore[0])
    app.sketchText = "Detached sketch draft"
    let nextSeed = app.seedText
    app.detachLineage()
    guard app.selectedWork == nil, app.selectedWorkID == nil, app.previewWork == nil,
          app.descriptionText == "Detached description draft", app.ddlText == "Detached instruction draft",
          app.sketchText == "Detached sketch draft", app.seedText == nextSeed,
          try await database.list() == savedBefore,
          try await database.lineageOverview(focusNodeID: root) == lineageBefore else {
        throw CheckFailure.message("Starting a new root lost the draft/conditions, kept a parent, or changed saved history")
    }
    print("Lineage presentation passed: five SQLite nodes/four edges; favorite route/tombstone arrows, cached branches, 40–140% map return; isolated focus/path/checked export scopes; recorded-hash badges; detach preserves description/DDL/sketch and clears parent. Saved works/lineage unchanged.")
}

private actor LineageCountingReader: LineageReading {
    let database: InkuDatabase
    private(set) var baseReads = 0
    private(set) var branchReads: [String: Int] = [:]
    private(set) var overviewReads = 0
    init(database: InkuDatabase) { self.database = database }
    func read(focusNodeID: String, depth: Int, pathOnly: Bool) async throws -> LineageGraph? {
        baseReads += 1
        return try await database.lineage(focusNodeID: focusNodeID, descendantDepth: depth, nodeLimit: 200, pathOnly: pathOnly)
    }
    func readBranch(nodeID: String) async throws -> LineageGraph? {
        branchReads[nodeID, default: 0] += 1
        return try await database.lineage(focusNodeID: nodeID, descendantDepth: 1, nodeLimit: 200)
    }
    func readOverview(focusNodeID: String) async throws -> LineageGraph? {
        overviewReads += 1
        return try await database.lineageOverview(focusNodeID: focusNodeID)
    }
}
