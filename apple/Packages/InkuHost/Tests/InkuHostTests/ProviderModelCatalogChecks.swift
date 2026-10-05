import Foundation
import XCTest
@testable import InkuHost

private actor Pages {
    private(set) var urls: [URL] = []
    private var replies: [String]
    init(_ replies: [String]) { self.replies = replies }
    func send(_ request: URLRequest) -> (status: Int, data: Data) {
        urls.append(request.url!)
        // The last reply repeats, so one reply models a list that never ends.
        return (200, Data((replies.count > 1 ? replies.removeFirst() : replies.first ?? "{}").utf8))
    }
}

final class ProviderModelCatalogChecks: XCTestCase, @unchecked Sendable {
    private func provider(_ id: String, _ kind: ProviderKind, _ base: String) -> ProviderSettings {
        .init(id: id, kind: kind, baseURL: URL(string: base)!, requiresAPIKey: true)
    }
    private func query(_ url: URL) -> [String: String] {
        Dictionary(uniqueKeysWithValues: (URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []).map { ($0.name, $0.value ?? "") })
    }

    // Failure (D8): a model past the first page reads as withdrawn (and is retired) because only one page is read.
    func testEveryPageIsReadAndAnEndlessListIsRefused() async throws {
        let anthropic = Pages([#"{"data":[{"id":"a","display_name":"A"}],"has_more":true,"last_id":"a"}"#,
                               #"{"data":[{"id":"b"}],"has_more":false,"last_id":"b"}"#])
        let rows = try await ProviderModelCatalog.fetch(provider: provider("anthropic", .anthropic, "https://api.anthropic.com"),
            firstURL: URL(string: "https://api.anthropic.com/v1/models")!, key: "k") { await anthropic.send($0) }
        XCTAssertEqual(rows.map(\.id), ["a", "b"]); XCTAssertEqual(rows.map(\.label), ["A", "b"])
        let anthropicURLs = await anthropic.urls
        XCTAssertEqual(anthropicURLs.map(query), [["limit": "1000"], ["limit": "1000", "after_id": "a"]])

        let gemini = Pages([#"{"models":[{"name":"models/g1","displayName":"G1"}],"nextPageToken":"t2"}"#, #"{"models":[{"name":"models/g2"}]}"#])
        let geminiRows = try await ProviderModelCatalog.fetch(provider: provider("gemini", .gemini, "https://generativelanguage.googleapis.com"),
            firstURL: URL(string: "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000")!, key: nil) { await gemini.send($0) }
        XCTAssertEqual(geminiRows.map(\.id), ["g1", "g2"])
        let geminiURLs = await gemini.urls
        XCTAssertEqual(geminiURLs.map(query), [["pageSize": "1000"], ["pageSize": "1000", "pageToken": "t2"]])

        let endless = Pages([#"{"models":[{"name":"models/x"}],"nextPageToken":"again"}"#])
        do {
            _ = try await ProviderModelCatalog.fetch(provider: provider("gemini", .gemini, "https://g.invalid"),
                firstURL: URL(string: "https://g.invalid/v1beta/models")!, key: nil) { await endless.send($0) }
            XCTFail("An unfinished list must not be used")
        } catch { XCTAssertEqual((error as? HostError)?.code, "model_catalog_unfinished") }
        let endlessCount = await endless.urls.count
        XCTAssertEqual(endlessCount, 20)
        let empty = Pages([#"{"data":[]}"#])
        do {
            _ = try await ProviderModelCatalog.fetch(provider: provider("custom", .openAICompatible, "http://x.invalid/v1"),
                firstURL: URL(string: "http://x.invalid/v1/models")!, key: nil) { await empty.send($0) }
            XCTFail("An empty list must be refused")
        } catch { XCTAssertEqual((error as? HostError)?.code, "model_catalog_empty") }
    }

    // Failure (D8): fetched models are appended and switched on, and withdrawn models vanish; Server replaces the
    // list, saves new models switched off and keeps withdrawn ones as EOL (values from api_settings_fetch_provider_models).
    func testFetchedListFoldsIntoTheCatalogAsServerDoes() {
        let previous = [ProviderModelSettings(id: "keep", label: "Keep Label", recommendationLLM: 4),
                        ProviderModelSettings(id: "gone", label: "Gone"), ProviderModelSettings(id: "off", label: "off")]
        let fetched = [FetchedProviderModel(id: "keep", label: "keep"), FetchedProviderModel(id: "off", label: "Off"),
                       FetchedProviderModel(id: "new-vision", label: "new-vision")]
        let merged = ProviderModelCatalog.merge(fetched: fetched, previous: previous, previousEnabled: ["off": false], today: "2026-10-05")
        XCTAssertEqual(merged.models.map(\.id), ["keep", "off", "new-vision", "gone"])
        XCTAssertEqual(merged.models.map(\.label), ["Keep Label", "Off", "new-vision", "Gone"])
        XCTAssertEqual(merged.models.map(\.purposes), [["llm"], ["llm"], ["vision"], ["llm"]])
        XCTAssertEqual(merged.models[0].recommendationLLM, 4)
        XCTAssertEqual(merged.models.map { $0.eol == true }, [false, false, false, true])
        XCTAssertEqual(merged.models[3].eolDate, "2026-10-05")
        XCTAssertEqual(merged.models.map { merged.enabled[$0.id] }, [true, false, false, false])

        let probed = ProviderModelCatalog.merge(fetched: fetched, previous: previous, previousEnabled: nil,
            access: ["keep": .subscription(true), "off": .retired("2026-09-28")], today: "2026-10-05")
        XCTAssertEqual(probed.models[0].requiresSubscription, true)
        XCTAssertEqual(probed.models[1].eolDate, "2026-09-28")
        XCTAssertEqual(probed.models.map { probed.enabled[$0.id] }, [false, false, false, false])
    }

    // Failure (D8): Ollama Cloud models the plan cannot call stay selectable; Server asks /api/show (410) and a
    // one-token chat (403) two at a time.
    func testOllamaCloudAccessProbe() async {
        let cloud = ProviderSettings(id: "ollama-cloud", baseURL: URL(string: "https://ollama.com/v1")!, requiresAPIKey: true)
        let answers = await ProviderModelCatalog.probeAccess(provider: cloud, key: "k", modelIDs: ["old", "paid", "free", "busy"], today: "2026-10-05") { request in
            let body = (try? ExactJSON(data: request.httpBody ?? Data())) ?? .null
            let model = body["model"].string ?? ""
            if request.url!.path == "/api/show" { return model == "old" ? (410, "model retired at 2026-09-28") : (200, "") }
            XCTAssertEqual(request.url!.absoluteString, "https://ollama.com/v1/chat/completions")
            return model == "paid" ? (403, "") : model == "free" ? (200, "") : (nil, "")
        }
        XCTAssertEqual(answers, ["old": .retired("2026-09-28"), "paid": .subscription(true), "free": .subscription(false)])
        let other = ProviderSettings(id: "ollama", baseURL: URL(string: "http://localhost:11434/v1")!, requiresAPIKey: false)
        let skipped = await ProviderModelCatalog.probeAccess(provider: other, key: nil, modelIDs: ["x"], today: "2026-10-05") { _ in (403, "") }
        XCTAssertTrue(skipped.isEmpty)
    }
}
