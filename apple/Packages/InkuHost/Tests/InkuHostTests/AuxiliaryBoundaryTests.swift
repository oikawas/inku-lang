import Foundation
import InkuPersistence
import Testing
@testable import InkuHost

private actor AuxiliaryCredentials: CredentialStore {
    func key(for credentialID: String) -> String? { nil }
}

private actor AuxiliaryProbe: AuxiliaryTransport {
    var prompts: [AuxiliaryPrompt] = []
    var responses: [String]
    let delayed: Bool
    private var started: CheckedContinuation<Void, Never>?
    private var pending: CheckedContinuation<String, Never>?

    init(responses: [String] = [], delayed: Bool = false) { self.responses = responses; self.delayed = delayed }
    func performAuxiliary(prompt: AuxiliaryPrompt, modelReference: String, settings: HostSettings,
                          credentials: any CredentialStore, onBytes: @escaping @Sendable (Int) -> Void) async throws -> String {
        prompts.append(prompt); started?.resume(); started = nil
        if delayed { return await withCheckedContinuation { pending = $0 } }
        guard !responses.isEmpty else { throw HostError("fake_response_missing") }
        return responses.removeFirst()
    }
    func waitForCall() async {
        if prompts.isEmpty { await withCheckedContinuation { started = $0 } }
    }
    func finish(_ text: String) { pending?.resume(returning: text); pending = nil }
}

struct AuxiliaryBoundaryTests {
    @Test func cancelledDemoRejectsLateUncooperativeAnswer() async throws {
        let transport = AuxiliaryProbe(delayed: true)
        let provider = AuxiliaryProvider(transport: transport, credentials: AuxiliaryCredentials())
        let settings = HostSettings(models: ModelSelection(stage1Model: "service:model"))
        let operation = Task { try await provider.demoInstruction(seedPhrase: "rain", language: "en", settings: settings) }
        await transport.waitForCall()
        operation.cancel()
        await transport.finish("a late answer that must not be adopted")
        await #expect(throws: CancellationError.self) { try await operation.value }
        let prompts = await transport.prompts
        #expect(prompts.count == 1)
        #expect(prompts[0].system == AuxiliaryProvider.demoSystem("en"))
        #expect(prompts[0].maximumTokens == 180 && prompts[0].temperature == 0.9 && prompts[0].timeoutSeconds == 120)
    }

    @Test func fencedAdviceAndActualVisionWireShape() throws {
        let answer = try AuxiliaryProvider.parseAdvice("before\n```json\n{\"observation\":\"red on the left\",\"next_direction\":\"try a narrower band\",\"suggested_kind\":\"rank\"}\n```after",
            kinds: ["layout_change", "touch_change"], model: "service:vision")
        #expect(answer.suggestedKind == "layout_change" && answer.nextDirection == "try a narrower band")
        #expect(throws: HostError("empty_refinement_advice")) {
            try AuxiliaryProvider.parseAdvice("{\"observation\":\"\",\"next_direction\":\"x\"}", kinds: ["layout_change"], model: "m")
        }
        let png = "data:image/png;base64," + Data([137, 80, 78, 71, 13, 10, 26, 10]).base64EncodedString()
        let prompt = AuxiliaryPrompt(system: "system", message: "message", images: [png], temperature: 0.35, maximumTokens: 320)
        let anthropic = ProviderSettings(id: "service", kind: .anthropic, baseURL: URL(string: "http://localhost:10001")!, requiresAPIKey: false)
        let request = try AuxiliaryWire.request(prompt: prompt, provider: anthropic, model: "vision", key: nil)
        let body = try ExactJSON(data: request.httpBody!)
        #expect(body["temperature"] == .null)
        #expect(body["messages"].array?.first?["content"].array?.first?["source"]["media_type"].string == "image/png")
        let raw = Data("{\"candidates\":[{\"content\":{\"parts\":[{\"text\":\"hidden thought\",\"thought\":true},{\"text\":\" actual answer \"}]}}]}".utf8)
        #expect(try AuxiliaryWire.responseText(raw, kind: .gemini) == "actual answer")
    }

    @Test func colophonReadsOnlyKnownPrefixAndMechanicalInvariants() async throws {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent("inku-auxiliary-\(UUID().uuidString)").appendingPathComponent("test.sqlite")
        defer { try? FileManager.default.removeItem(at: file.deletingLastPathComponent()) }
        let database = try InkuDatabase(url: file)
        let root = SavedWork(id: "root", at: 1, input: "EARLY CAPTION", score: "{\"instructions\":[{\"primitive\":\"circle\",\"color\":\"red\",\"center\":[0.5,0.5]}]}", svg: "first", lineageNodeID: "node-root")
        let child = SavedWork(id: "child", at: 2, input: "LATER CAPTION", score: "{\"instructions\":[{\"primitive\":\"circle\",\"color\":\"blue\",\"center\":[0.5,0.5]}]}", svg: "second", lineageNodeID: "node-child")
        try await database.save(root, node: LineageNode(id: "node-root", historyID: root.id, at: 1, rootNodeID: "node-root"))
        try await database.save(child, node: LineageNode(id: "node-child", historyID: child.id, at: 2, rootNodeID: "node-root"),
            edge: LineageEdge(id: "edge", parentNodeID: "node-root", childNodeID: "node-child", derivationKind: "catalog_change", at: 2))
        let optionalBranch = try await database.lineage(focusNodeID: "node-child", pathOnly: true)
        let branch = try #require(optionalBranch)
        let probe = AuxiliaryProbe(responses: ["red circle", "blue circle", "a circle remains"])
        let provider = AuxiliaryProvider(transport: probe, credentials: AuxiliaryCredentials())
        let draft = try await provider.colophon(branch: branch, language: "en", settings: HostSettings(models: ModelSelection(stage1Model: "service:vision")),
            png: { _ in Data([137, 80, 78, 71, 13, 10, 26, 10]) })
        let prompts = await probe.prompts
        #expect(prompts.count == 3)
        #expect(!prompts[0].message.contains("LATER CAPTION"))
        #expect(prompts[1].message.contains("LATER CAPTION") && prompts[1].message.contains("I see red circle"))
        #expect(prompts[2].images.isEmpty)
        #expect(draft.branchSnapshot == ["node-root", "node-child"])
        #expect(draft.generatedBody.hasPrefix("I see red circle") && draft.adoptedBody == nil)
        let facts = try ExactJSON(data: Data(draft.factSheetJSON.utf8))
        #expect(facts["invariants"]["primitives"] == .array([.string("circle")]))
        #expect(facts["invariants"]["colors"] == .array([]))
        #expect(facts["invariants"]["composition_family"].string == "central_stillness")
        #expect(try await database.work(id: root.id) == root)
        #expect(try await database.work(id: child.id) == child)
    }
}
