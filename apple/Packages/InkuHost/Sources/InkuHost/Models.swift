import Foundation

public struct HostError: Error, LocalizedError, Sendable, Equatable {
    public let code: String
    public init(_ code: String) { self.code = code }
    public var errorDescription: String? { code }
}

public enum SketchRequest: Sendable {
    case off, on, supplied(String)
    var json: ExactJSON {
        switch self {
        case .off: .object(["mode": .string("off")])
        case .on: .object(["mode": .string("on")])
        case .supplied(let text): .object(["mode": .string("supplied"), "text": .string(text)])
        }
    }
}

public enum GenerationAuthoring: Sendable {
    case directDDL(String)
    case description(String, autoCatalog: Bool, sketch: SketchRequest = .off)
    var json: ExactJSON {
        switch self {
        case .directDDL(let source): .object(["tag": .string("direct_ddl"), "source": .string(source)])
        case .description(let text, let auto, let sketch):
            .object(["tag": .string("description"), "description": .string(text), "auto_catalog": .bool(auto), "sketch": sketch.json])
        }
    }
    var isDirect: Bool { if case .directDDL = self { true } else { false } }
}

public struct ModelSelection: Codable, Sendable, Equatable {
    public var stage1Model: String
    public var stage2Model: String
    public var stage1MaxTokens: Int
    public var holeMaxTokens: Int
    public init(stage1Model: String = "", stage2Model: String = "", stage1MaxTokens: Int = 2048, holeMaxTokens: Int = 2048) {
        self.stage1Model = stage1Model; self.stage2Model = stage2Model
        self.stage1MaxTokens = stage1MaxTokens; self.holeMaxTokens = holeMaxTokens
    }
}

public struct GenerationRequest: Sendable {
    public var authoring: GenerationAuthoring
    public var configuration: Data
    public var renderOptions: Data
    public var clipPolicy: Data
    public var models: ModelSelection
    public var providers: [ProviderSettings]
    public var renderColorMaps: [String: Data]
    public var description: String
    public var parentWorkID: String?
    public var derivationKind: String
    public init(authoring: GenerationAuthoring, configuration: Data, renderOptions: Data, clipPolicy: Data,
                models: ModelSelection = .init(), providers: [ProviderSettings] = [],
                renderColorMaps: [String: Data] = [:],
                description: String = "", parentWorkID: String? = nil, derivationKind: String = "new") {
        self.authoring = authoring; self.configuration = configuration; self.renderOptions = renderOptions
        self.clipPolicy = clipPolicy; self.models = models; self.providers = providers
        self.renderColorMaps = renderColorMaps
        if case .description(let text, _, _) = authoring { self.description = description.isEmpty ? text : description }
        else { self.description = description }
        self.parentWorkID = parentWorkID; self.derivationKind = derivationKind
    }
}

public enum PipelineCommand: Sendable {
    case commitUserDDL(expectedRevision: String, source: String)
    case generateFromDescription(expectedRevision: String, description: String, autoCatalog: Bool, sketch: SketchRequest = .off)
    case completeHoles(expectedRevision: String, holeIDs: [String])
    case approvePatch(expectedRevision: String, proposalDigest: String)
    case declinePatch(proposalDigest: String)
    case render(options: Data, clip: Data)
    case cancel
    func payload() throws -> ExactJSON {
        switch self {
        case .commitUserDDL(let revision, let source):
            return .object(["tag": .string("commit_user_ddl"), "expected_revision": .string(revision), "source": .string(source)])
        case .generateFromDescription(let revision, let text, let auto, let sketch):
            return .object(["tag": .string("generate_from_description"), "expected_revision": .string(revision), "description": .string(text), "auto_catalog": .bool(auto), "sketch": sketch.json])
        case .completeHoles(let revision, let holes):
            return .object(["tag": .string("complete_holes"), "expected_revision": .string(revision), "hole_ids": .array(holes.map(ExactJSON.string))])
        case .approvePatch(let revision, let digest):
            return .object(["tag": .string("approve_patch"), "expected_revision": .string(revision), "proposal_digest": .string(digest)])
        case .declinePatch(let digest): return .object(["tag": .string("decline_patch"), "proposal_digest": .string(digest)])
        case .render(let options, let clip): return .object(["tag": .string("render"), "options": try ExactJSON(data: options), "clip": try ExactJSON(data: clip)])
        case .cancel: return .object(["tag": .string("cancel")])
        }
    }
}

public struct PipelineView: Sendable {
    public let executionID: String
    public let variationID: String
    public let sequence: String
    public let revision: String
    public let phase: String
    public let authority: String
    public let origin: String
    public let visibleDDL: String?
    public let scoreJSON: Data?
    public let renderedJSON: Data?
    public let svg: String?
    public let savedWorkID: String?
    public let patchProposalJSON: Data?
    public let eventsJSON: Data
    public let busy: Bool
    public let interruptedProvider: Bool
    public let description: String
}

public enum PipelineProgress: Sendable {
    case changed(PipelineView)
    case providerAttempt(executionID: String, report: Data, beganAt: Date, deadline: Date)
    case transportBytes(executionID: String, count: Int)
    case saved(executionID: String, workID: String)
}

public typealias PipelineProgressHandler = @Sendable (PipelineProgress) -> Void
