import Foundation
import InkuPersistence

public struct HostError: Error, LocalizedError, Sendable, Equatable {
    public let code: String
    public init(_ code: String) { self.code = code }
    public var errorDescription: String? { code }
}

public enum SketchRequest: Codable, Sendable {
    case off, on, supplied(String)
    var json: ExactJSON {
        switch self {
        case .off: .object(["mode": .string("off")])
        case .on: .object(["mode": .string("on")])
        case .supplied(let text): .object(["mode": .string("supplied"), "text": .string(text)])
        }
    }
}

public enum GenerationAuthoring: Codable, Sendable {
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

public struct GenerationRequest: Codable, Sendable {
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
    public var derivationMetadata: Data?
    public var interpretationSeed: String?
    public var saveHistory: Bool
    public var historyVisibility: String
    public var retainedDocument: Data?
    public var retainedAuthority: Data?
    public var chatGPTSession: ChatGPTPlanSession?
    public init(authoring: GenerationAuthoring, configuration: Data, renderOptions: Data, clipPolicy: Data,
                models: ModelSelection = .init(), providers: [ProviderSettings] = [],
                renderColorMaps: [String: Data] = [:],
                description: String = "", parentWorkID: String? = nil, derivationKind: String = "new",
                saveHistory: Bool = true, historyVisibility: String = "normal",
                retainedDocument: Data? = nil, retainedAuthority: Data? = nil, chatGPTSession: ChatGPTPlanSession? = nil,
                derivationMetadata: Data? = nil, interpretationSeed: String? = nil) {
        self.authoring = authoring; self.configuration = configuration; self.renderOptions = renderOptions
        self.clipPolicy = clipPolicy; self.models = models; self.providers = providers
        self.renderColorMaps = renderColorMaps
        if case .description(let text, _, _) = authoring { self.description = description.isEmpty ? text : description }
        else { self.description = description }
        self.parentWorkID = parentWorkID; self.derivationKind = derivationKind
        self.derivationMetadata = derivationMetadata; self.interpretationSeed = interpretationSeed
        self.saveHistory = saveHistory; self.historyVisibility = historyVisibility
        self.retainedDocument = retainedDocument; self.retainedAuthority = retainedAuthority
        self.chatGPTSession = chatGPTSession
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
    public let configurationJSON: Data
    public let documentJSON: Data?
    public let deliveryJSON: Data?
    public let promptJSON: Data?
    public let holeIDs: [String]
    public let candidateWork: SavedWork?
}

public struct PreparedCandidate: Identifiable, Sendable {
    public let executionID: String
    public let work: SavedWork
    public let authority: String
    public var id: String { executionID }
    public init(executionID: String, work: SavedWork, authority: String) {
        self.executionID = executionID; self.work = work; self.authority = authority
    }
}

/// A read-only comparison of the saved SVG and the same Score rendered by the current engine.
public struct ReplayComparisonSnapshot: Sendable {
    public let workID: String
    public let originalSVG: String
    public let replayedSVG: String
    public let recordedVersion: String?
    public let currentVersion: String
    public let provisionalSeed: String?
    public init(workID: String, originalSVG: String, replayedSVG: String, recordedVersion: String?,
                currentVersion: String, provisionalSeed: String?) {
        self.workID = workID; self.originalSVG = originalSVG; self.replayedSVG = replayedSVG
        self.recordedVersion = recordedVersion; self.currentVersion = currentVersion
        self.provisionalSeed = provisionalSeed
    }
}

/// An owned saved-Score snapshot. Only the host constructs or interprets its payload.
public struct SavedScoreReplayPlan: Sendable {
    let work: SavedWork
    let parentNode: LineageNode
    let context: Data
    let renderRequest: Data
    let derivationKind: String
    let derivationMetadata: Data?
    let seedText: String?
    let variationAmplitude: String?
    let variationSeed: String?
}

/// Owned saved input data. Export and derivation never receive a mutable database handle.
public struct SavedAuthoringContext: Sendable {
    public let configuration: Data
    public let renderOptions: Data
    public let clipPolicy: Data
    public let document: Data?
    public let authority: String
    public let origin: String
    public let revision: String
    public let authorityJSON: Data
}

public struct ReplayOptions: Sendable {
    public let catalogID: String
    public let colorMap: Data
    public let canvasID: String
    public let widthRatio: UInt32
    public let heightRatio: UInt32
    public init(catalogID: String, colorMap: Data, canvasID: String, widthRatio: UInt32, heightRatio: UInt32) {
        self.catalogID = catalogID; self.colorMap = colorMap; self.canvasID = canvasID
        self.widthRatio = widthRatio; self.heightRatio = heightRatio
    }
}

public enum PipelineProgress: Sendable {
    case changed(PipelineView)
    case providerAttempt(executionID: String, report: Data, beganAt: Date, deadline: Date)
    case transportBytes(executionID: String, count: Int)
    case providerDiagnostic(executionID: String, diagnostic: ChatGPTPlanDiagnostic)
    case saved(executionID: String, workID: String)
}

public typealias PipelineProgressHandler = @Sendable (PipelineProgress) -> Void
