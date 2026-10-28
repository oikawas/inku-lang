import Foundation
import InkuCore

/// The core owns model labels, recommendations and ordering. Cache its answer for each input record.
public enum SharedModelCatalog {
    public struct Decision: Decodable, Sendable {
        public struct Selection: Decodable, Sendable {
            public let unselectable: Bool
            public let unsupported: [String: Bool]
            public let levels: [String: [String: Double]]
            public let sortKeys: [String: [String: String]]
            private enum CodingKeys: String, CodingKey { case unselectable, unsupported, levels; case sortKeys = "sort_keys" }
        }
        public let labels: [String]
        public let fold: String?
        public let selection: Selection
    }
    private struct Info: Decodable {
        let schema: String
        let outcome: String
        let catalog: Catalog
        let measurementKeys: [String]
        struct Catalog: Decodable { let schema: String; let labels: [ModelCatalogLabelDefinition] }
        enum CodingKeys: String, CodingKey { case schema, outcome, catalog; case measurementKeys = "measurement_keys" }
    }
    private struct Response: Decodable { let outcome: String; let model: Decision }
    private final class Cache: @unchecked Sendable {
        let lock = NSLock()
        var answers: [Data: Decision] = [:]
    }
    private static let cache = Cache()
    private static let infoData: Data = {
        let request = Data(#"{"schema":"inku.model-catalog-request.v1","action":"catalog"}"#.utf8)
        return InkuCore.modelCatalog(request)
    }()
    private static let info: Info = {
        do {
            let result = try JSONDecoder().decode(Info.self, from: infoData)
            precondition(result.schema == "inku.model-catalog.v1" && result.outcome == "ok"
                         && result.catalog.schema == "inku.model-catalog.v2" && !result.catalog.labels.isEmpty
                         && Set(result.catalog.labels.map(\.id)).count == result.catalog.labels.count
                         && !result.measurementKeys.isEmpty, "Core model catalog schema invalid")
            return result
        }
        catch { preconditionFailure("Core model catalog unavailable: \(error)") }
    }()
    public static let labels = info.catalog.labels
    public static let measurementKeys = Set(info.measurementKeys)
    public static let catalogData: Data = {
        do { return try ExactJSON.rawMember("catalog", in: infoData) }
        catch { preconditionFailure("Core model catalog invalid: \(error)") }
    }()

    public static func decision(for model: ProviderModelSettings) -> Decision {
        let record = model.coreCatalogRecord
        let request: [String: Any] = ["schema": "inku.model-catalog-request.v1", "action": "label", "model": record]
        do {
            let bytes = try JSONSerialization.data(withJSONObject: request, options: [.sortedKeys])
            return cache.lock.withLock {
                if let answer = cache.answers[bytes] { return answer }
                do {
                    let response = try JSONDecoder().decode(Response.self, from: InkuCore.modelCatalog(bytes))
                    precondition(response.outcome == "ok", "Core refused model catalog input")
                    if cache.answers.count >= 4096 { cache.answers.removeAll(keepingCapacity: true) }
                    cache.answers[bytes] = response.model
                    return response.model
                } catch { preconditionFailure("Core model catalog response invalid: \(error)") }
            }
        } catch { preconditionFailure("Model catalog input invalid: \(error)") }
    }
}
