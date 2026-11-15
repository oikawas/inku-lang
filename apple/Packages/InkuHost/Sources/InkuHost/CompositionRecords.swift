import Foundation
import InkuCore
import InkuPersistence

/// A Score replay carries a copied authoring record; it is not this child's own execution.
public enum CompositionRecords {
    private static let copiedKinds: Set<String> = ["replay", "tool_change", "ground_change", "catalog_change", "color_arrangement_change", "canvas_fit"]

    public static func ownRecord(descriptionDDL: Data?, derivationKind: String?) throws -> ExactJSON? {
        guard !copiedKinds.contains(derivationKind ?? ""), let descriptionDDL else { return nil }
        let composition = try ExactJSON(data: descriptionDDL)["composition"]
        return composition.object == nil ? nil : composition
    }
}

public struct CompositionRecordSnapshot: Sendable {
    public let own: ExactJSON?
    public let inherited: ExactJSON?
    public let places: [ExactJSON]
    public let derivationKind: String?
    public let metadata: ExactJSON
}

extension PipelineHost {
    /// Read a library page's shared ancestry once, then let the same core walk decide each record.
    public func compositionRecords(works: [SavedWork]) async throws -> [String: CompositionRecordSnapshot] {
        let batch = try await database.compositionNodes(starts: works.compactMap(\.lineageNodeID),
            unlinkedWorkIDs: works.filter { $0.lineageNodeID == nil }.map(\.id))
        let stored = batch.nodes
        var result: [String: CompositionRecordSnapshot] = [:]
        for work in works {
          do {
            guard let start = work.lineageNodeID else {
                let own = try CompositionRecords.ownRecord(descriptionDDL: batch.unlinked[work.id], derivationKind: nil)
                result[work.id] = CompositionRecordSnapshot(own: own, inherited: nil, places: [], derivationKind: nil, metadata: .object([:]))
                continue
            }
            var nodes: [ExactJSON] = [], id: String? = start, seen = Set<String>()
            var own: ExactJSON?, ownKind: String?, ownMetadata: ExactJSON = .object([:])
            while let current = id, seen.insert(current).inserted, let row = stored[current] {
                let edge = row.edge
                let record = try CompositionRecords.ownRecord(descriptionDDL: row.descriptionDDL, derivationKind: edge?.derivationKind)
                let metadata = edge.flatMap { try? ExactJSON(data: Data($0.metadataJSON.utf8)) } ?? .object([:])
                if current == start { own = record; ownKind = edge?.derivationKind; ownMetadata = metadata }
                nodes.append(.object(["node_id": .string(current), "history_id": row.node.historyID.map(ExactJSON.string) ?? .null,
                    "at": .number(String(row.node.at)), "state": .string(row.node.state), "readable": .bool(row.readable),
                    "edge_readable": .bool(true), "parent_node_id": edge.map { .string($0.parentNodeID) } ?? .null,
                    "derivation_kind": edge.map { .string($0.derivationKind) } ?? .null, "ddl": row.ddl.map(ExactJSON.string) ?? .null,
                    "composition": record ?? .null, "metadata": metadata]))
                id = edge?.parentNodeID
            }
            let input: ExactJSON = .object(["action": .string("walk"), "start": .string(start), "nodes": .array(nodes)])
            let output = try ExactJSON(data: InkuCore.compositionRules(input.data))
            guard output["outcome"].string == "ok" else { throw HostError(output["reason"].string ?? "composition_walk_failed") }
            let inherited = output["result"]["composition_inherited"]
            result[work.id] = CompositionRecordSnapshot(own: own, inherited: inherited.object == nil ? nil : inherited,
                places: output["result"]["places"].array ?? [], derivationKind: ownKind, metadata: ownMetadata)
          } catch { continue }
        }
        return result
    }

    /// Assemble storage facts only; the core owns the traversal and inheritance rules.
    public func compositionRecord(work: SavedWork) async throws -> CompositionRecordSnapshot {
        guard let start = work.lineageNodeID else {
            let context = try? await savedAuthoringContext(workID: work.id)
            return try CompositionRecordSnapshot(own: CompositionRecords.ownRecord(descriptionDDL: context?.descriptionDDL, derivationKind: nil), inherited: nil, places: [], derivationKind: nil, metadata: .object([:]))
        }
        var nodes: [ExactJSON] = []
        var nodeID: String? = start
        var seen = Set<String>()
        var own: ExactJSON?
        var ownKind: String?
        var ownMetadata: ExactJSON = .object([:])
        while let id = nodeID, seen.insert(id).inserted, let node = try await database.node(id: id) {
            let edge = try await database.edge(childNodeID: id)
            let linked: SavedWork?
            if let historyID = node.historyID { linked = try await database.work(id: historyID) } else { linked = nil }
            let context: SavedAuthoringContext?
            if let historyID = node.historyID { context = try? await savedAuthoringContext(workID: historyID) } else { context = nil }
            let record = try CompositionRecords.ownRecord(descriptionDDL: context?.descriptionDDL, derivationKind: edge?.derivationKind)
            if id == start { own = record; ownKind = edge?.derivationKind }
            let metadata = edge.flatMap { try? ExactJSON(data: Data($0.metadataJSON.utf8)) } ?? .object([:])
            if id == start { ownMetadata = metadata }
            nodes.append(.object([
                "node_id": .string(id), "history_id": node.historyID.map(ExactJSON.string) ?? .null,
                "at": .number(String(node.at)), "state": .string(node.state),
                "readable": .bool(linked != nil && linked?.trashed == false && node.state == "active"),
                "edge_readable": .bool(true), "parent_node_id": edge.map { .string($0.parentNodeID) } ?? .null,
                "derivation_kind": edge.map { .string($0.derivationKind) } ?? .null,
                "ddl": linked?.ddl.map(ExactJSON.string) ?? .null,
                "composition": record ?? .null, "metadata": metadata
            ]))
            nodeID = edge?.parentNodeID
        }
        let input = ExactJSON.object(["action": .string("walk"), "start": .string(start), "nodes": .array(nodes)])
        let output = try ExactJSON(data: InkuCore.compositionRules(input.data))
        guard output["outcome"].string == "ok" else { throw HostError(output["reason"].string ?? "composition_walk_failed") }
        let inherited = output["result"]["composition_inherited"]
        return CompositionRecordSnapshot(own: own, inherited: inherited.object == nil ? nil : inherited,
                                         places: output["result"]["places"].array ?? [], derivationKind: ownKind, metadata: ownMetadata)
    }

    /// Use the saved work's configuration; an inherited answer alone omits the owner's sentence map.
    public func compositionWorkBoxes(work: SavedWork) async throws -> ExactJSON {
        let context = try await savedAuthoringContext(workID: work.id)
        let record = try await compositionRecord(work: work)
        var inheritedRecord: ExactJSON = .null
        if let historyID = record.inherited?["history_id"].string,
           let ancestor = try? await savedAuthoringContext(workID: historyID),
           let description = ancestor.descriptionDDL {
            inheritedRecord = try ExactJSON(data: description)["composition"]
        }
        let input: ExactJSON = .object([
            "action": .string("work_boxes"), "config": try ExactJSON(data: context.configuration),
            "ddl": .string(work.ddl ?? ""), "own_record": record.own ?? .null,
            "inherited_record": inheritedRecord, "derivation_kind": record.derivationKind.map(ExactJSON.string) ?? .null,
            "score": try ExactJSON(data: Data(work.score.utf8))
        ])
        let output = try ExactJSON(data: InkuCore.chunkMoves(input.data))
        guard output["outcome"].string == "ok" else { throw HostError(output["reason"].string ?? "composition_boxes_failed") }
        return output
    }

    public func compositionPlace(work: SavedWork, chunk: String, at: String) async throws -> ExactJSON {
        let context = try await savedAuthoringContext(workID: work.id)
        let record = try await compositionRecord(work: work)
        var source = record.own
        if source == nil, let historyID = record.inherited?["history_id"].string,
           let ancestor = try? await savedAuthoringContext(workID: historyID), let data = ancestor.descriptionDDL {
            source = try ExactJSON(data: data)["composition"]
        }
        var composition: ExactJSON = .null
        if let source, let owners = source["things"].array, let things = source["answer"]["things"].array {
            composition = .object(["owners": .array(owners), "things": .array(things)])
        }
        let input: ExactJSON = .object(["action": .string("place"), "config": try ExactJSON(data: context.configuration),
            "ddl": .string(work.ddl ?? ""), "composition": composition, "chunk": .string(chunk), "at": .string(at),
            "derivation_kind": record.derivationKind.map(ExactJSON.string) ?? .null,
            "score": try ExactJSON(data: Data(work.score.utf8))])
        let output = try ExactJSON(data: InkuCore.chunkMoves(input.data))
        guard output["outcome"].string == "ok" else { throw HostError(output["reason"].string ?? "composition_place_failed") }
        return output
    }
}
