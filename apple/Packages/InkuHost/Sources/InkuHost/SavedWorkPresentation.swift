import Foundation
import InkuCore

/// A save-identity snapshot. Missing legacy records stay missing; they are not
/// reconstructed from the latest execution or the current prompt edition.
public struct SavedWorkPresentation: Sendable {
    public let promptJSON: Data?
    public let deliveryJSON: Data?
    public let renderedJSON: Data?
    public let diagnosticsJSON: Data?
    public let eventsJSON: Data?
    public let provenance: GenerationProvenance?

    init(context: ExactJSON) throws {
        let record = context["presentation"]
        guard record != .null else {
            promptJSON = nil; deliveryJSON = nil; renderedJSON = nil
            diagnosticsJSON = nil; eventsJSON = nil
            provenance = nil
            return
        }
        guard record["schema"].string == "inku.swift-saved-presentation.v1",
              record["delivery"] == .null || record["delivery"].object != nil,
              record["prompts"] == .null || record["prompts"].array != nil,
              record["rendered"].object != nil,
              record["diagnostics"].object != nil, record["events"].array != nil,
              record.object != nil else { throw HostError("saved_presentation_invalid") }
        promptJSON = record["prompts"] == .null ? nil : record["prompts"].data
        deliveryJSON = record["delivery"] == .null ? nil : record["delivery"].data
        renderedJSON = record["rendered"].data
        diagnosticsJSON = record["diagnostics"].data
        eventsJSON = record["events"].data
        provenance = record["provenance"] == .null ? nil : try JSONDecoder().decode(GenerationProvenance.self, from: record["provenance"].data)
    }
}

enum SavedPresentation {
    static func replay(context: ExactJSON, rendered: ExactJSON) throws -> ExactJSON {
        _ = try SavedWorkPresentation(context: context)
        var record = context["presentation"]
        if record == .null {
            // No compiler or prompt facts can be recovered from an older Score.
            record = .object(["schema": .string("inku.swift-saved-presentation.v1"),
                "prompts": .null, "delivery": .null, "diagnostics": .object([:])])
        }
        let metadata = rendered["metadata"]
        record["rendered"] = .object(["metadata": metadata])
        record["diagnostics"]["render_diagnostics"] = metadata["execution"]
        record["diagnostics"]["resource_execution"] = metadata["resource_execution"]
        record["events"] = .array([])
        return record
    }

    static func capture(delivery: ExactJSON, rendered: ExactJSON, prompts: Data?, events: Data,
                        configuration: ExactJSON, document: ExactJSON, disabledPluginNames: [String] = [],
                        provenance: GenerationProvenance? = nil) throws -> ExactJSON {
        let records = try prompts.map { try ExactJSON(data: $0).array ?? [] } ?? []
        // Server records only the last actually requested prompt of each stage.
        let latest = ["generate_normalized_ddl", "complete_visible_ddl_holes"].compactMap { tag in
            records.last { $0["action"].string == tag }
        }
        let metadata = rendered["metadata"]
        var diagnostics: ExactJSON = .object([
            "upstream_diagnostics": delivery["upstream_diagnostics"],
            "downstream_diagnostics": delivery["downstream_diagnostics"],
            "resource_omissions": delivery["resource_omissions"],
            "relation_omissions": delivery["relation_omissions"],
            "render_diagnostics": metadata["execution"],
            "resource_execution": metadata["resource_execution"],
        ])
        let names = (configuration["definitions"].array ?? []).flatMap { definition -> [ExactJSON] in
            guard let namespace = definition["namespace"].string, let heading = definition["heading"].string else { return [] }
            return ([heading] + (definition["aliases"].array?.compactMap(\.string) ?? []))
                .map { .string(namespace + "." + $0) }
        }
        let pluginInput: ExactJSON = .object(["source": document["source"],
            "upstream_diagnostics": delivery["upstream_diagnostics"], "enabled": .array(names),
            "disabled": .array(disabledPluginNames.map(ExactJSON.string))])
        diagnostics["plugin_diagnostics"] = try ExactJSON(data: InkuCore.explainPluginDiagnostics(pluginInput.data))
        return .object(["schema": .string("inku.swift-saved-presentation.v1"),
            "prompts": .array(latest), "delivery": delivery,
            // The work owns its saved SVG; presentation keeps render diagnostics only.
            "rendered": .object(["metadata": metadata]), "diagnostics": diagnostics,
            "events": try ExactJSON(data: events),
            "provenance": try provenance.map { try ExactJSON(data: JSONEncoder().encode($0)) } ?? .null])
    }
}
